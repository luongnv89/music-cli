"""FFplay-based audio player implementation."""

import asyncio
import logging
import os
import shlex
import shutil
import signal

from ..platform import get_player_controller, is_windows
from ..platform.player_control import PlayerController
from .base import Player, PlayerState, TrackInfo

logger = logging.getLogger(__name__)


class FFplayPlayer(Player):
    """Audio player using ffplay (part of FFmpeg).

    Uses platform-appropriate pause/resume:
    - Linux/macOS: SIGSTOP/SIGCONT signals
    - Windows: stdin 'p' command
    """

    def __init__(self):
        super().__init__()
        self._process: asyncio.subprocess.Process | None = None
        self._monitor_task: asyncio.Task | None = None
        self._paused = False
        self._is_process_group = False
        # Platform-specific player controller for pause/resume
        self._controller: PlayerController = get_player_controller()
        self._is_windows = is_windows()

        # Verify ffplay is available
        if not shutil.which("ffplay"):
            logger.warning("ffplay not found in PATH. Please install FFmpeg.")

    async def play(self, track: TrackInfo, loop: bool = False) -> bool:
        """Start playing a track using ffplay.

        Args:
            track: Track information to play
            loop: If True, loop the track indefinitely (useful for AI-generated short clips)
        """
        # Stop any current playback
        await self.stop()

        self._state = PlayerState.LOADING
        self._current_track = track

        try:
            # For YouTube sources, try piping yt-dlp to ffplay (Unix only)
            youtube_url = track.metadata.get("youtube_url") if track.metadata else None
            if track.source_type == "youtube" and youtube_url:
                if await self._play_youtube_pipe(youtube_url):
                    return True
                # Fallback: play extracted URL directly (Windows or pipe failure)

            # Build ffplay command
            cmd = [
                "ffplay",
                "-nodisp",  # No display window
                "-loglevel",
                "quiet",  # Suppress output
                "-volume",
                str(self._volume),
            ]

            # Loop mode for AI tracks or explicit loop request
            if loop or track.source_type == "ai":
                cmd.extend(["-loop", "0"])  # 0 = infinite loop
            else:
                cmd.append("-autoexit")  # Exit when done (for files)

            # For streams, add reconnect options
            if track.source_type in ("radio", "youtube"):
                cmd.extend(
                    [
                        "-reconnect",
                        "1",
                        "-reconnect_streamed",
                        "1",
                        "-reconnect_delay_max",
                        "5",
                    ]
                )

            cmd.append(track.source)

            logger.info(f"Starting playback: {track.source}")

            # Windows needs stdin=PIPE for pause/resume via 'p' command
            # Unix uses SIGSTOP/SIGCONT so stdin can be DEVNULL
            stdin_mode = asyncio.subprocess.PIPE if self._is_windows else asyncio.subprocess.DEVNULL

            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=stdin_mode,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )

            self._state = PlayerState.PLAYING
            self._paused = False
            # Reset controller state for new playback
            self._controller.reset()

            # Start monitoring for process end
            self._monitor_task = asyncio.create_task(self._monitor_playback())

            return True

        except Exception as e:
            logger.error(f"Failed to start playback: {e}")
            self._state = PlayerState.ERROR
            return False

    async def _play_youtube_pipe(self, youtube_url: str) -> bool:
        """Play YouTube audio by piping yt-dlp output to ffplay.

        This is more reliable for live streams as yt-dlp handles reconnection
        and URL refresh automatically. Only supported on Unix systems.
        """
        if self._is_windows:
            logger.warning("YouTube pipe not supported on Windows, falling back to direct URL")
            return False  # Caller will fall back to direct URL playback

        yt_dlp_path = shutil.which("yt-dlp")
        if not yt_dlp_path:
            logger.error("yt-dlp not found in PATH")
            self._state = PlayerState.ERROR
            return False

        logger.info(f"Starting YouTube pipe playback: {youtube_url}")

        try:
            # Use shell pipe: yt-dlp streams to ffplay
            # Format priority: audio-only, format 91 (lowest quality for live), or best available
            cmd = (
                f"{shlex.quote(yt_dlp_path)} -f 'bestaudio/91/best' -q -o - {shlex.quote(youtube_url)} | "
                f"ffplay -nodisp -loglevel quiet -volume {self._volume} -"
            )

            self._process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                preexec_fn=os.setsid,
            )
            self._is_process_group = True

            self._state = PlayerState.PLAYING
            self._paused = False
            self._controller.reset()

            self._monitor_task = asyncio.create_task(self._monitor_playback())

            return True

        except Exception as e:
            logger.error(f"Failed to start YouTube playback: {e}")
            self._state = PlayerState.ERROR
            return False

    async def _monitor_playback(self) -> None:
        """Monitor the ffplay process and handle completion."""
        if self._process is None:
            return

        try:
            await self._process.wait()

            # Only trigger callback if we weren't stopped manually
            if self._state == PlayerState.PLAYING:
                self._state = PlayerState.STOPPED
                self._current_track = None

                if self._on_track_end:
                    self._on_track_end()

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error monitoring playback: {e}")

    async def stop(self) -> None:
        """Stop playback."""
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

        if self._process:
            try:
                if self._is_process_group:
                    os.killpg(self._process.pid, signal.SIGTERM)
                else:
                    self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                if self._is_process_group:
                    os.killpg(self._process.pid, signal.SIGKILL)
                else:
                    self._process.kill()
                await self._process.wait()
            except (ProcessLookupError, OSError):
                pass
            self._process = None
            self._is_process_group = False
        self._state = PlayerState.STOPPED
        self._current_track = None
        self._paused = False

    async def pause(self) -> None:
        """Pause playback.

        Uses platform-appropriate method:
        - Linux/macOS: SIGSTOP signal
        - Windows: stdin 'p' command
        """
        if self._process and self._state == PlayerState.PLAYING:
            success = await self._controller.pause(self._process)
            if success:
                self._state = PlayerState.PAUSED
                self._paused = True

    async def resume(self) -> None:
        """Resume playback.

        Uses platform-appropriate method:
        - Linux/macOS: SIGCONT signal
        - Windows: stdin 'p' command (toggle)
        """
        if self._process and self._state == PlayerState.PAUSED:
            success = await self._controller.resume(self._process)
            if success:
                self._state = PlayerState.PLAYING
                self._paused = False

    async def set_volume(self, volume: int) -> None:
        """Set volume. Note: ffplay doesn't support runtime volume changes.

        Volume will apply to the next track.
        """
        self._volume = max(0, min(100, volume))
        # ffplay doesn't support dynamic volume changes
        # The volume will be applied when the next track starts
        logger.info(f"Volume set to {self._volume}% (applies to next track)")

    async def get_position(self) -> float:
        """Get current playback position.

        Note: ffplay doesn't provide easy position tracking.
        This is a limitation of the ffplay approach.
        """
        # ffplay doesn't expose position information easily
        # For accurate position tracking, we'd need mpv or VLC
        return 0.0

    def get_status(self) -> dict:
        """Get current player status."""
        status = super().get_status()
        status["backend"] = "ffplay"
        return status


def check_ffplay_available() -> bool:
    """Check if ffplay is available in PATH."""
    return shutil.which("ffplay") is not None
