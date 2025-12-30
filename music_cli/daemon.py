"""Background daemon for music-cli."""

import asyncio
import json
import logging
import os
import signal

from .config import get_config
from .context.mood import Mood, MoodContext
from .context.temporal import TemporalContext
from .history import get_history
from .player.base import TrackInfo
from .player.ffplay import FFplayPlayer
from .sources.local import LocalSource
from .sources.radio import RadioSource

logger = logging.getLogger(__name__)


class MusicDaemon:
    """Background daemon that handles music playback."""

    def __init__(self):
        self.config = get_config()
        self.player = FFplayPlayer()
        self.local_source = LocalSource()
        self.radio_source = RadioSource()
        self.history = get_history()
        self.temporal = TemporalContext()

        self._server: asyncio.Server | None = None
        self._running = False
        self._current_mood: Mood | None = None
        self._auto_play = False  # For infinite/context-aware mode

    async def start(self) -> None:
        """Start the daemon server."""
        socket_path = self.config.socket_path

        # Clean up stale socket
        if socket_path.exists():
            socket_path.unlink()

        self._running = True

        # Set up signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

        # Start Unix socket server
        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=str(socket_path),
        )

        # Set socket permissions
        socket_path.chmod(0o600)

        # Write PID file
        self.config.pid_file.write_text(str(os.getpid()))

        logger.info(f"Daemon started, listening on {socket_path}")

        async with self._server:
            await self._server.serve_forever()

    async def stop(self) -> None:
        """Stop the daemon."""
        logger.info("Stopping daemon...")
        self._running = False

        await self.player.stop()

        if self._server:
            self._server.close()
            await self._server.wait_closed()

        # Clean up files
        if self.config.socket_path.exists():
            self.config.socket_path.unlink()
        if self.config.pid_file.exists():
            self.config.pid_file.unlink()

        logger.info("Daemon stopped")

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle a client connection."""
        try:
            data = await reader.read(4096)
            if not data:
                return

            try:
                request = json.loads(data.decode())
            except json.JSONDecodeError:
                response = {"error": "Invalid JSON"}
                writer.write(json.dumps(response).encode())
                await writer.drain()
                return

            command = request.get("command", "")
            args = request.get("args", {})

            response = await self._process_command(command, args)

            writer.write(json.dumps(response).encode())
            await writer.drain()

        except Exception as e:
            logger.error(f"Error handling client: {e}")
        finally:
            writer.close()
            await writer.wait_closed()

    async def _process_command(self, command: str, args: dict) -> dict:
        """Process a command and return response."""
        handlers = {
            "play": self._cmd_play,
            "stop": self._cmd_stop,
            "pause": self._cmd_pause,
            "resume": self._cmd_resume,
            "status": self._cmd_status,
            "next": self._cmd_next,
            "volume": self._cmd_volume,
            "list_radios": self._cmd_list_radios,
            "list_history": self._cmd_list_history,
            "ping": self._cmd_ping,
        }

        handler = handlers.get(command)
        if handler:
            try:
                return await handler(args)
            except Exception as e:
                logger.error(f"Error processing {command}: {e}")
                return {"error": str(e)}
        else:
            return {"error": f"Unknown command: {command}"}

    async def _cmd_ping(self, args: dict) -> dict:
        """Health check."""
        return {"status": "ok", "message": "pong"}

    async def _cmd_play(self, args: dict) -> dict:
        """Play music based on arguments."""
        mode = args.get("mode", "radio")
        source = args.get("source")
        mood = args.get("mood")
        self._auto_play = args.get("auto", False)

        track: TrackInfo | None = None

        if mood:
            self._current_mood = MoodContext.parse_mood(mood)

        if mode == "local":
            if source:
                track = self.local_source.get_track(source)
            else:
                track = self.local_source.get_random_track()

        elif mode == "radio":
            if source:
                # Try as station name first
                track = self.radio_source.get_station_by_name(source)
                if not track:
                    # Try as URL
                    track = self.radio_source.get_track(source)
            elif mood and self._current_mood:
                track = self.radio_source.get_mood_station(self._current_mood.value)
            else:
                # Use temporal context
                time_period = self.temporal.get_time_period()
                track = self.radio_source.get_time_station(time_period.value)
                if not track:
                    track = self.radio_source.get_random_station()

        elif mode == "ai":
            # Try to use AI generation
            try:
                from .sources.ai_generator import AIGenerator, is_ai_available

                if not is_ai_available():
                    return {
                        "error": "AI generation not available. Install with: pip install 'music-cli[ai]'"
                    }

                # Use persistent AI music directory from config
                generator = AIGenerator(output_dir=self.config.ai_music_dir)

                # Build prompt
                temporal_prompt = self.temporal.get_music_prompt()
                mood_prompt = None
                if self._current_mood:
                    mood_prompt = MoodContext.get_prompt(self._current_mood)

                duration = args.get("duration", 30)
                track = generator.generate_for_context(mood_prompt, temporal_prompt, duration)

            except ImportError:
                return {
                    "error": "AI generation not available. Install with: pip install 'music-cli[ai]'"
                }

        elif mode == "context":
            # Context-aware mode: use radio with mood/time awareness
            if self._current_mood:
                track = self.radio_source.get_mood_station(self._current_mood.value)
            else:
                time_period = self.temporal.get_time_period()
                track = self.radio_source.get_time_station(time_period.value)

            if not track:
                track = self.radio_source.get_random_station()

        elif mode == "history":
            # Play from history
            index = args.get("index", 1)
            entry = self.history.get_by_index(index)
            if entry:
                if entry.source_type == "local":
                    track = self.local_source.get_track(entry.source)
                else:
                    track = self.radio_source.get_track(entry.source, entry.title)

        if not track:
            return {"error": "Could not find track to play"}

        # Set up callback for auto-play
        if self._auto_play and track.source_type == "local":
            self.player.set_on_track_end(self._on_track_end)
        else:
            self.player.set_on_track_end(None)

        success = await self.player.play(track)

        if success:
            # Log to history
            self.history.log(
                source=track.source,
                source_type=track.source_type,
                title=track.title,
                artist=track.artist,
                mood=self._current_mood.value if self._current_mood else None,
                context=self.temporal.get_time_period().value,
            )

            return {
                "status": "playing",
                "track": track.to_dict(),
            }
        else:
            return {"error": "Failed to start playback"}

    def _on_track_end(self) -> None:
        """Called when a track ends in auto-play mode."""
        if self._auto_play:
            asyncio.create_task(self._play_next())

    async def _play_next(self) -> None:
        """Play the next track in auto-play mode."""
        track = self.local_source.get_random_track()
        if track:
            await self.player.play(track)
            self.history.log(
                source=track.source,
                source_type=track.source_type,
                title=track.title,
                artist=track.artist,
                mood=self._current_mood.value if self._current_mood else None,
                context=self.temporal.get_time_period().value,
            )

    async def _cmd_stop(self, args: dict) -> dict:
        """Stop playback."""
        self._auto_play = False
        await self.player.stop()
        return {"status": "stopped"}

    async def _cmd_pause(self, args: dict) -> dict:
        """Pause playback."""
        await self.player.pause()
        return {"status": "paused"}

    async def _cmd_resume(self, args: dict) -> dict:
        """Resume playback."""
        await self.player.resume()
        return {"status": "playing"}

    async def _cmd_status(self, args: dict) -> dict:
        """Get current status."""
        status = self.player.get_status()
        status["auto_play"] = self._auto_play
        status["mood"] = self._current_mood.value if self._current_mood else None
        status["context"] = self.temporal.get_info().to_dict()
        return status

    async def _cmd_next(self, args: dict) -> dict:
        """Skip to next track (for auto-play mode)."""
        if self._auto_play:
            await self._play_next()
            return {"status": "playing_next"}
        else:
            return {"error": "Auto-play not enabled"}

    async def _cmd_volume(self, args: dict) -> dict:
        """Set volume."""
        volume = args.get("level")
        if volume is None:
            return {"volume": self.player.volume}
        await self.player.set_volume(int(volume))
        return {"volume": self.player.volume}

    async def _cmd_list_radios(self, args: dict) -> dict:
        """List available radio stations."""
        return {"stations": self.radio_source.list_stations()}

    async def _cmd_list_history(self, args: dict) -> dict:
        """List playback history."""
        limit = args.get("limit", 20)
        entries = self.history.get_all(limit=limit)
        return {"history": [{"index": i + 1, **e.to_dict()} for i, e in enumerate(entries)]}


def run_daemon() -> None:
    """Run the daemon (entry point)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    daemon = MusicDaemon()
    asyncio.run(daemon.start())


def get_daemon_pid() -> int | None:
    """Get the PID of the running daemon.

    Returns the PID if daemon is running, None otherwise.
    Also cleans up stale PID/socket files if the daemon is not running.
    """
    config = get_config()

    if not config.pid_file.exists():
        return None

    try:
        pid = int(config.pid_file.read_text().strip())
        os.kill(pid, 0)  # Check if running
        return pid
    except (ValueError, ProcessLookupError, PermissionError):
        # PID file is stale, clean up
        try:
            if config.pid_file.exists():
                config.pid_file.unlink()
            if config.socket_path.exists():
                config.socket_path.unlink()
        except OSError:
            pass  # Best effort cleanup
        return None


def is_daemon_running() -> bool:
    """Check if daemon is already running."""
    return get_daemon_pid() is not None


if __name__ == "__main__":
    run_daemon()
