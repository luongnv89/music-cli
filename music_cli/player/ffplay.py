"""FFplay-based audio player implementation."""

import asyncio
import logging
import shutil
import signal

from .base import Player, PlayerState, TrackInfo

logger = logging.getLogger(__name__)


class FFplayPlayer(Player):
    """Audio player using ffplay (part of FFmpeg)."""

    def __init__(self):
        super().__init__()
        self._process: asyncio.subprocess.Process | None = None
        self._monitor_task: asyncio.Task | None = None
        self._paused = False

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
            if track.source_type == "radio":
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

            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )

            self._state = PlayerState.PLAYING
            self._paused = False

            # Start monitoring for process end
            self._monitor_task = asyncio.create_task(self._monitor_playback())

            return True

        except Exception as e:
            logger.error(f"Failed to start playback: {e}")
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
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    self._process.kill()
                    await self._process.wait()
            except ProcessLookupError:
                pass  # Process already ended
            self._process = None

        self._state = PlayerState.STOPPED
        self._current_track = None
        self._paused = False

    async def pause(self) -> None:
        """Pause playback by sending SIGSTOP to ffplay."""
        if self._process and self._state == PlayerState.PLAYING:
            try:
                self._process.send_signal(signal.SIGSTOP)
                self._state = PlayerState.PAUSED
                self._paused = True
            except ProcessLookupError:
                pass

    async def resume(self) -> None:
        """Resume playback by sending SIGCONT to ffplay."""
        if self._process and self._state == PlayerState.PAUSED:
            try:
                self._process.send_signal(signal.SIGCONT)
                self._state = PlayerState.PLAYING
                self._paused = False
            except ProcessLookupError:
                pass

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
