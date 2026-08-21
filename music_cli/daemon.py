"""Background daemon for music-cli."""

import asyncio
import codecs
import hmac
import json
import logging
import os
import secrets
import signal
from collections.abc import Coroutine
from typing import Any

from .ai_tracks import get_ai_tracks
from .config import get_config
from .context.mood import Mood, MoodContext
from .context.temporal import TemporalContext
from .history import get_history
from .platform import get_ipc_server, supports_unix_signals
from .platform.ipc import IPCServer
from .player.base import TrackInfo
from .player.ffplay import FFplayPlayer
from .sources.local import LocalSource
from .sources.radio import RadioSource
from .sources.youtube import YouTubeSource, is_youtube_available
from .youtube_history import get_youtube_history

logger = logging.getLogger(__name__)

REQUEST_CHUNK_SIZE = 4096
MAX_REQUEST_SIZE = 1024 * 1024
REQUEST_READ_TIMEOUT = 5.0
# Liveness-probe budget (#68): long enough for a busy loop to answer a ping,
# short enough that a hung impostor does not stall every CLI command.
IDENTITY_PROBE_TIMEOUT = 2.0


class RequestError(ValueError):
    """An invalid, incomplete, or oversized daemon request."""


class _JSONRequestFramer:
    """Incrementally find the end of a top-level JSON object."""

    _ESCAPES = frozenset('"\\/bfnrt')
    _HEX_DIGITS = frozenset("0123456789abcdefABCDEF")

    def __init__(self) -> None:
        self._chunks: list[str] = []
        self._stack: list[str] = []
        self._started = False
        self._in_string = False
        self._escaped = False
        self._unicode_digits = 0
        self._complete = False

    def feed(self, text: str) -> bool:
        """Consume decoded text and return whether the object is complete."""
        self._chunks.append(text)

        for char in text:
            if self._complete:
                if not char.isspace():
                    raise RequestError("Invalid JSON")
                continue

            if self._in_string:
                if self._unicode_digits:
                    if char not in self._HEX_DIGITS:
                        raise RequestError("Invalid JSON")
                    self._unicode_digits -= 1
                elif self._escaped:
                    if char == "u":
                        self._unicode_digits = 4
                        self._escaped = False
                    elif char in self._ESCAPES:
                        self._escaped = False
                    else:
                        raise RequestError("Invalid JSON")
                elif char == "\\":
                    self._escaped = True
                elif char == '"':
                    self._in_string = False
                elif ord(char) < 0x20:
                    raise RequestError("Invalid JSON")
                continue

            if not self._started:
                if char.isspace():
                    continue
                if char != "{":
                    raise RequestError("Request must be a JSON object")
                self._started = True
                self._stack.append("}")
                continue

            if char == '"':
                self._in_string = True
            elif char in "{[":
                self._stack.append("}" if char == "{" else "]")
            elif char in "}]":
                if not self._stack or self._stack[-1] != char:
                    raise RequestError("Invalid JSON")
                self._stack.pop()
                if not self._stack:
                    self._complete = True

        return self._complete

    def finish(self) -> None:
        """Reject a stream that ended before a complete object was found."""
        if not self._complete:
            raise RequestError("Incomplete JSON request")

    def text(self) -> str:
        return "".join(self._chunks)


class MusicDaemon:
    """Background daemon that handles music playback."""

    def __init__(self):
        self.config = get_config()
        self.player = FFplayPlayer()
        self.local_source = LocalSource()
        self.radio_source = RadioSource()
        self.youtube_source = YouTubeSource()
        self.history = get_history()
        self.youtube_history = get_youtube_history()
        self.temporal = TemporalContext()
        self.ai_tracks = get_ai_tracks()

        # Platform-specific IPC server (Unix sockets or TCP)
        self._ipc_server: IPCServer = get_ipc_server()
        self._running = False
        self._current_mood: Mood | None = None
        self._auto_play = False  # For infinite/context-aware mode
        self._auth_token: str | None = None  # Issued in start(); None rejects every request
        # Serializes state-mutating command handlers (#67): per-connection
        # tasks interleave at every await, so concurrent plays would race on
        # player state and orphan ffplay processes.
        self._command_lock = asyncio.Lock()
        # Strong references to fire-and-forget tasks (#69): the event loop
        # keeps only a weak reference, so unreferenced tasks can be collected
        # mid-execution.
        self._background_tasks: set[asyncio.Task] = set()
        # Per-run identity (#68): recorded in the PID file and echoed by
        # ``ping`` so liveness checks can tell this daemon apart from an
        # unrelated process that merely recycled its PID.
        self._identity = secrets.token_hex(16)

    def _spawn_task(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
        """Schedule a background task and hold a reference until it finishes."""
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    def _issue_auth_token(self) -> str:
        """Generate a fresh auth token and persist it owner-only.

        The token is stored in the config directory (0o700) with file mode
        0o600 so only the owning user's clients can authenticate.
        """
        self._auth_token = secrets.token_hex(32)
        self.config.write_auth_token(self._auth_token)
        return self._auth_token

    async def start(self) -> None:
        """Start the daemon server.

        Uses platform-appropriate IPC:
        - Linux/macOS: Unix domain sockets
        - Windows: TCP localhost
        """
        socket_path = self.config.socket_path

        self._running = True

        # Generate a fresh per-run auth token before accepting connections
        self._issue_auth_token()

        # Set up signal handlers (Unix only - not supported on Windows asyncio)
        if supports_unix_signals():
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, lambda: self._spawn_task(self.stop()))

        # Start IPC server (platform-specific)
        await self._ipc_server.start(self._handle_client, socket_path)

        # Write PID file with the run's identity so liveness checks can
        # verify the process behind the PID is this daemon (#68).
        self.config.pid_file.write_text(
            json.dumps({"pid": os.getpid(), "identity": self._identity})
        )

        address_display = self._ipc_server.get_address_display(socket_path)
        logger.info(f"Daemon started, listening on {address_display}")

        await self._ipc_server.serve_forever()

    async def stop(self) -> None:
        """Stop the daemon."""
        logger.info("Stopping daemon...")
        self._running = False

        await self.player.stop()

        # Stop IPC server (handles socket cleanup on Unix)
        await self._ipc_server.stop()

        # Clean up PID file
        if self.config.pid_file.exists():
            try:
                self.config.pid_file.unlink()
            except OSError:
                pass  # Best effort cleanup

        logger.info("Daemon stopped")

    async def _read_request(self, reader: asyncio.StreamReader) -> dict | None:
        """Read one complete JSON request without relying on socket boundaries."""
        decoder = codecs.getincrementaldecoder("utf-8")()
        framer = _JSONRequestFramer()
        size = 0
        deadline = asyncio.get_running_loop().time() + REQUEST_READ_TIMEOUT

        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise RequestError("Request timed out")
            try:
                chunk = await asyncio.wait_for(reader.read(REQUEST_CHUNK_SIZE), remaining)
            except TimeoutError as exc:
                raise RequestError("Request timed out") from exc

            if not chunk:
                try:
                    text = decoder.decode(b"", final=True)
                except UnicodeDecodeError as exc:
                    raise RequestError("Invalid UTF-8") from exc
                if text:
                    framer.feed(text)
                if size == 0:
                    return None
                framer.finish()
                break

            size += len(chunk)
            if size > MAX_REQUEST_SIZE:
                raise RequestError(f"Request too large (maximum {MAX_REQUEST_SIZE} bytes)")

            try:
                text = decoder.decode(chunk)
            except UnicodeDecodeError as exc:
                raise RequestError("Invalid UTF-8") from exc

            complete = framer.feed(text) if text else False
            # A split UTF-8 sequence may still be pending after the closing
            # brace. Read on so invalid trailing bytes are not mistaken for a
            # complete request.
            pending_utf8, _ = decoder.getstate()
            if complete and not pending_utf8:
                break

        try:
            request = json.loads(framer.text())
        except json.JSONDecodeError as exc:
            raise RequestError("Invalid JSON") from exc
        if not isinstance(request, dict):
            raise RequestError("Request must be a JSON object")
        return request

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle a client connection."""
        try:
            try:
                request = await self._read_request(reader)
            except RequestError as exc:
                response = {"error": str(exc)}
                writer.write(json.dumps(response).encode())
                await writer.drain()
                return

            if request is None:
                return

            # Authenticate before dispatching any command handler
            token = request.get("token")
            auth_token = self._auth_token
            if (
                not auth_token
                or not isinstance(token, str)
                or not hmac.compare_digest(token, auth_token)
            ):
                logger.warning("Rejected request with missing or invalid token")
                response = {"error": "Unauthorized"}
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
            "ai_list": self._cmd_ai_list,
            "ai_play": self._cmd_ai_play,
            "ai_replay": self._cmd_ai_replay,
            "ai_remove": self._cmd_ai_remove,
            "youtube_history_list": self._cmd_youtube_history_list,
            "youtube_history_play": self._cmd_youtube_history_play,
            "youtube_history_remove": self._cmd_youtube_history_remove,
            "youtube_history_clear": self._cmd_youtube_history_clear,
            "shutdown": self._cmd_shutdown,
        }

        handler = handlers.get(command)
        if handler:
            # Health checks answer outside the command lock (#68): a ping
            # must not queue behind a long state-mutating handler, or every
            # liveness probe would block for the duration of a play.
            if command == "ping":
                return await handler(args)
            try:
                # Hold the command lock for the whole handler so concurrent
                # connections cannot interleave state mutations (#67).
                async with self._command_lock:
                    return await handler(args)
            except Exception as e:
                # Log the detail server-side; never leak exception text
                # (which can contain filesystem paths) to the client.
                logger.error(f"Error processing {command}: {e}", exc_info=True)
                return {"error": "Internal error while processing command"}
        else:
            return {"error": f"Unknown command: {command}"}

    async def _cmd_ping(self, args: dict) -> dict:
        """Health check. Echoes the run identity for liveness checks (#68)."""
        return {"status": "ok", "message": "pong", "identity": self._identity}

    async def _cmd_play(self, args: dict) -> dict:
        """Play music based on arguments."""
        mode = args.get("mode", "radio")
        self._auto_play = args.get("auto", False)

        mood = args.get("mood")
        if mood:
            self._current_mood = MoodContext.parse_mood(mood)

        resolvers = {
            "local": self._resolve_local_track,
            "radio": self._resolve_radio_track,
            "ai": self._resolve_ai_track,
            "context": self._resolve_context_track,
            "history": self._resolve_history_track,
            "youtube": self._resolve_youtube_track,
            "yt": self._resolve_youtube_track,
        }

        track: TrackInfo | None = None
        resolver = resolvers.get(mode)
        if resolver:
            resolved = await resolver(args)
            if isinstance(resolved, dict):
                # The resolver answered with a client-visible error response.
                return resolved
            track = resolved

        if not track:
            return {"error": "Could not find track to play"}

        # Set up callback for auto-play
        if self._auto_play and track.source_type == "local":
            self.player.set_on_track_end(self._on_track_end)
        else:
            self.player.set_on_track_end(None)

        success = await self.player.play(track)

        if success:
            # For YouTube, log the original YouTube URL (not the stream URL) for replay
            log_source = track.source
            if track.source_type == "youtube" and track.metadata.get("youtube_url"):
                log_source = track.metadata["youtube_url"]
                self.youtube_history.add_entry(
                    video_id=track.metadata.get("video_id", ""),
                    url=log_source,
                    title=track.title or "Unknown",
                    artist=track.artist,
                    duration=track.duration,
                )

            self.history.log(
                source=log_source,
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

    async def _resolve_local_track(self, args: dict) -> TrackInfo | None:
        """Resolve a track from the local library for play mode ``local``."""
        source = args.get("source")
        if source:
            return self.local_source.get_track(source)
        return self.local_source.get_random_track()

    async def _resolve_radio_track(self, args: dict) -> TrackInfo | None:
        """Resolve a station for play mode ``radio``.

        Tries the source as a station name, then as a URL; without a source it
        falls back to the mood station (when one was requested with this
        command) and then to the time-of-day station.
        """
        source = args.get("source")
        mood = args.get("mood")

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

        # Handle YouTube URLs in radio stations
        if track and ("youtube.com" in track.source or "youtu.be" in track.source):
            station_name = track.title
            yt_track = self.youtube_source.get_track(track.source)
            if yt_track:
                yt_track.title = station_name
                track = yt_track

        return track

    async def _resolve_ai_track(self, args: dict) -> TrackInfo | dict | None:
        """Generate a track for play mode ``ai``.

        Returns an error response dict when AI generation is unavailable.
        """
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
            return generator.generate_for_context(mood_prompt, temporal_prompt, duration)

        except ImportError:
            return {
                "error": "AI generation not available. Install with: pip install 'music-cli[ai]'"
            }

    async def _resolve_context_track(self, args: dict) -> TrackInfo | None:
        """Resolve a station for play mode ``context``.

        Context-aware mode: use radio with mood/time awareness.
        """
        if self._current_mood:
            track = self.radio_source.get_mood_station(self._current_mood.value)
        else:
            time_period = self.temporal.get_time_period()
            track = self.radio_source.get_time_station(time_period.value)

        if not track:
            track = self.radio_source.get_random_station()

        return track

    async def _resolve_history_track(self, args: dict) -> TrackInfo | dict | None:
        """Replay a history entry for play mode ``history``.

        Returns an error response dict when YouTube playback is unavailable or
        the video can no longer be loaded.
        """
        index = args.get("index", 1)
        entry = self.history.get_by_index(index)
        if not entry:
            return None

        if entry.source_type == "local":
            return self.local_source.get_track(entry.source)

        if entry.source_type == "youtube":
            if not is_youtube_available():
                return {
                    "error": "YouTube playback not available. Install with: pip install 'coder-music-cli[youtube]'"
                }
            track = self.youtube_source.get_track(entry.source)
            if not track:
                return {
                    "error": f"Could not load YouTube video (may be deleted or private): {entry.source}"
                }
            return track

        return self.radio_source.get_track(entry.source, entry.title)

    async def _resolve_youtube_track(self, args: dict) -> TrackInfo | dict | None:
        """Resolve a stream for play modes ``youtube``/``yt``.

        Returns an error response dict when the URL is missing or YouTube
        playback is unavailable.
        """
        source = args.get("source")
        if not source:
            return {"error": "YouTube URL is required. Use: -s 'https://youtube.com/watch?v=...'"}

        if not is_youtube_available():
            return {
                "error": "YouTube playback not available. Install with: pip install 'coder-music-cli[youtube]'"
            }

        return self.youtube_source.get_track(source)

    def _on_track_end(self) -> None:
        """Called when a track ends in auto-play mode."""
        if self._auto_play:
            self._spawn_task(self._auto_advance())

    async def _auto_advance(self) -> None:
        """Advance to the next track under the command lock.

        The lock is not reentrant, so ``_cmd_next`` (which already holds it)
        calls ``_play_next`` directly; only the detached auto-play chain
        re-acquires the lock here.
        """
        async with self._command_lock:
            await self._play_next()

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

    async def _cmd_ai_list(self, args: dict) -> dict:
        """List all AI-generated tracks."""
        tracks = self.ai_tracks.get_all()
        return {
            "tracks": [
                {
                    "index": i + 1,
                    "prompt": t.prompt,
                    "duration": t.duration,
                    "timestamp": t.timestamp,
                    "model": t.model,
                    "file_exists": t.file_exists(),
                }
                for i, t in enumerate(tracks)
            ]
        }

    async def _cmd_ai_play(self, args: dict) -> dict:
        """Generate and play AI music.

        Args (from args dict):
            prompt: Custom prompt (optional). If not provided, uses context.
            duration: Duration in seconds (default: 30).
            mood: Mood to use for context-based generation.
            model: Model ID to use (optional). If not provided, uses default.
            lyrics: Optional lyrics for lyrics-conditioned models.
        """
        try:
            from .sources.ai_generator import AIGenerator, is_ai_available

            if not is_ai_available():
                return {
                    "error": "AI generation not available. Install with: pip install 'coder-music-cli[ai]'"
                }

            # Get parameters
            custom_prompt = args.get("prompt")
            duration = args.get("duration", 5)
            mood = args.get("mood")
            model_id = args.get("model")
            lyrics = args.get("lyrics")

            # Validate model if specified
            if model_id and not self.config.validate_ai_model(model_id):
                available = ", ".join(self.config.list_ai_models(enabled_only=True))
                return {"error": f"Unknown or disabled model: '{model_id}'. Available: {available}"}

            selected_model = self.config.get_ai_models_config().get_model(model_id)
            if selected_model is None:
                return {"error": "No enabled AI model is configured"}
            if lyrics is not None and not selected_model.supports_lyrics:
                return {"error": f"Model '{selected_model.id}' does not support lyrics"}
            if selected_model.requires_lyrics and (not lyrics or not lyrics.strip()):
                return {"error": f"Model '{selected_model.id}' requires non-empty lyrics"}

            # Update mood if provided
            if mood:
                self._current_mood = MoodContext.parse_mood(mood)

            # Build prompt
            if custom_prompt:
                # Use custom prompt directly
                prompt = custom_prompt
            else:
                # Build context-aware prompt
                prompts = []

                # Add temporal context (time of day, day of week)
                temporal_prompt = self.temporal.get_music_prompt()
                prompts.append(temporal_prompt)

                # Add mood if set in current session
                if self._current_mood:
                    mood_prompt = MoodContext.get_prompt(self._current_mood)
                    prompts.append(mood_prompt)

                prompt = ", ".join(prompts) if prompts else "ambient background music"

            # Generate the track with specified model
            generator = AIGenerator(output_dir=self.config.ai_music_dir, config=self.config)
            track = generator.generate(prompt, duration, model_id=model_id, lyrics=lyrics)

            if not track:
                return {"error": "Failed to generate AI music"}

            # Save the effective clamped duration and lyrics for replay.
            model_used = track.metadata.get("model", "musicgen-small")
            effective_duration = int(track.metadata.get("duration", duration))
            self.ai_tracks.add_track(
                prompt=prompt,
                file_path=track.source,
                duration=effective_duration,
                model=model_used,
                lyrics=lyrics,
            )

            # Log to history
            self.history.log(
                source=track.source,
                source_type=track.source_type,
                title=track.title,
                mood=self._current_mood.value if self._current_mood else None,
                context=self.temporal.get_time_period().value,
            )

            # Play the track
            success = await self.player.play(track)

            if success:
                return {
                    "status": "playing",
                    "track": track.to_dict(),
                    "prompt": prompt,
                }
            else:
                return {"error": "Failed to start playback"}

        except ImportError:
            return {
                "error": "AI generation not available. Install with: pip install 'coder-music-cli[ai]'"
            }

    async def _cmd_ai_replay(self, args: dict) -> dict:
        """Replay an AI track by index, or regenerate if file is missing.

        Args (from args dict):
            index: 1-based index of the track.
            regenerate: If True, regenerate the track even if file exists.
        """
        index = args.get("index", 1)
        regenerate = args.get("regenerate", False)

        track_entry = self.ai_tracks.get_by_index(index)
        if not track_entry:
            count = self.ai_tracks.count()
            if count == 0:
                return {"error": "No AI tracks available. Generate one with 'music-cli ai play'"}
            return {"error": f"Invalid index. Choose between 1 and {count}"}

        # Check if file exists
        if not track_entry.file_exists() or regenerate:
            # File is missing or regeneration requested
            if not regenerate:
                return {
                    "status": "file_missing",
                    "prompt": track_entry.prompt,
                    "message": "Audio file not found. Regenerate with the same prompt?",
                }

            # Regenerate the track
            try:
                from .sources.ai_generator import AIGenerator, is_ai_available

                if not is_ai_available():
                    return {
                        "error": "AI generation not available. Install with: pip install 'coder-music-cli[ai]'"
                    }

                # Always use the stored model for regeneration to maintain consistency
                model_id = track_entry.model

                generator = AIGenerator(output_dir=self.config.ai_music_dir, config=self.config)
                track = generator.generate(
                    track_entry.prompt,
                    track_entry.duration,
                    model_id=model_id,
                    lyrics=track_entry.lyrics,
                )

                if not track:
                    return {"error": "Failed to regenerate AI music"}

                # Update the path and effective metadata after regeneration.
                self.ai_tracks.update_file_path(
                    index,
                    track.source,
                    duration=int(track.metadata.get("duration", track_entry.duration)),
                    model=track.metadata.get("model", model_id),
                    lyrics=track.metadata.get("lyrics", track_entry.lyrics),
                )

                # Play the regenerated track
                success = await self.player.play(track)
                if success:
                    return {
                        "status": "playing",
                        "track": track.to_dict(),
                        "regenerated": True,
                    }
                else:
                    return {"error": "Failed to start playback"}

            except ImportError:
                return {
                    "error": "AI generation not available. Install with: pip install 'coder-music-cli[ai]'"
                }

        # File exists, play it directly
        track = TrackInfo(
            source=track_entry.file_path,
            source_type="ai",
            title=f"AI: {track_entry.display_prompt(40)}",
            metadata={"prompt": track_entry.prompt, "duration": track_entry.duration},
        )

        success = await self.player.play(track)
        if success:
            return {
                "status": "playing",
                "track": track.to_dict(),
            }
        else:
            return {"error": "Failed to start playback"}

    async def _cmd_ai_remove(self, args: dict) -> dict:
        index = args.get("index", 1)

        track_entry = self.ai_tracks.get_by_index(index)
        if not track_entry:
            count = self.ai_tracks.count()
            if count == 0:
                return {"error": "No AI tracks to remove"}
            return {"error": f"Invalid index. Choose between 1 and {count}"}

        removed = self.ai_tracks.remove_by_index(index)

        if removed:
            return {
                "status": "removed",
                "prompt": removed.prompt,
                "file_path": removed.file_path,
            }
        else:
            return {"error": "Failed to remove track"}

    async def _cmd_youtube_history_list(self, args: dict) -> dict:
        entries = self.youtube_history.get_all()

        total_size_bytes = 0
        cache_dir = self.config.youtube_cache_dir
        if cache_dir.exists():
            for f in cache_dir.glob("*.m4a"):
                total_size_bytes += f.stat().st_size

        max_size_gb = self.config.get_youtube_cache_config().get("max_size_gb", 2.0)
        max_size_bytes = max_size_gb * 1024 * 1024 * 1024
        usage_percent = (total_size_bytes / max_size_bytes * 100) if max_size_bytes > 0 else 0

        tracks = []
        for i, entry in enumerate(entries):
            file_path = cache_dir / f"{entry.video_id}.m4a"
            file_exists = file_path.exists()
            file_size_mb = file_path.stat().st_size / (1024 * 1024) if file_exists else 0

            tracks.append(
                {
                    "index": i + 1,
                    "video_id": entry.video_id,
                    "url": entry.url,
                    "title": entry.title,
                    "artist": entry.artist,
                    "duration": entry.duration,
                    "timestamp": entry.timestamp,
                    "file_exists": file_exists,
                    "file_size_mb": file_size_mb,
                }
            )

        return {
            "tracks": tracks,
            "stats": {
                "count": len(entries),
                "total_size_mb": total_size_bytes / (1024 * 1024),
                "max_size_gb": max_size_gb,
                "usage_percent": usage_percent,
            },
        }

    async def _cmd_youtube_history_play(self, args: dict) -> dict:
        index = args.get("index", 1)
        entry = self.youtube_history.get_by_index(index)
        if not entry:
            return {"error": f"Invalid index: {index}"}

        if not is_youtube_available():
            return {"error": "YouTube playback not available."}

        file_path = self.config.youtube_cache_dir / f"{entry.video_id}.m4a"
        if file_path.exists():
            track = TrackInfo(
                source=str(file_path),
                source_type="youtube",
                title=entry.title,
                artist=entry.artist,
                duration=entry.duration,
                metadata={"youtube_url": entry.url, "video_id": entry.video_id, "cached": True},
            )
        else:
            track = self.youtube_source.get_track(entry.url)

        if not track:
            return {"error": "Could not load track"}

        success = await self.player.play(track)
        if success:
            self.youtube_history.add_entry(
                video_id=entry.video_id,
                url=entry.url,
                title=entry.title,
                artist=entry.artist,
                duration=entry.duration,
            )
            return {"status": "playing", "track": track.to_dict()}
        else:
            return {"error": "Failed to start playback"}

    async def _cmd_youtube_history_remove(self, args: dict) -> dict:
        index = args.get("index", 1)
        removed = self.youtube_history.remove_by_index(index)
        if removed:
            file_path = self.config.youtube_cache_dir / f"{removed.video_id}.m4a"
            if file_path.exists():
                try:
                    file_path.unlink()
                except OSError:
                    pass
            return {"status": "removed", "title": removed.title}
        return {"error": f"Invalid index: {index}"}

    async def _cmd_youtube_history_clear(self, args: dict) -> dict:
        count = self.youtube_history.count()
        cache_dir = self.config.youtube_cache_dir
        if cache_dir.exists():
            for f in cache_dir.glob("*.m4a"):
                try:
                    f.unlink()
                except OSError:
                    pass
        self.youtube_history.clear()
        return {"status": "cleared", "removed_count": count}

    async def _cmd_shutdown(self, args: dict) -> dict:
        """Shutdown the daemon gracefully.

        Used on Windows where signal handlers aren't supported.
        """
        logger.info("Shutdown command received")
        # Schedule stop in a separate task so we can respond first
        self._spawn_task(self.stop())
        return {"status": "shutting_down"}


def run_daemon() -> None:
    """Run the daemon (entry point)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    daemon = MusicDaemon()
    asyncio.run(daemon.start())


def _pid_alive(pid: int) -> bool:
    """Check if a PID is alive, cross-platform safe (does not kill on Windows).

    On Unix, uses ``os.kill(pid, 0)`` which is a no-op liveness probe.
    On Windows, uses ``OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)``
    to query process existence without requiring ``TerminateProcess``
    access — this avoids the Windows ``os.kill()`` bug where signal ``0``
    calls ``TerminateProcess(handle, 0)`` and can kill the process.

    Args:
        pid: The process ID to check.

    Returns:
        ``True`` if a process with the given PID exists, ``False`` otherwise.
    """
    from .platform import is_unix

    if is_unix():
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            # Process exists but we lack permission to signal it.
            return True
    else:
        # Windows: use ctypes to call OpenProcess with limited rights.
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000  # noqa: N806
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)  # type: ignore[attr-defined]
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
            return True
        return False


def _probe_daemon_identity(socket_path: Any, token: str | None) -> str | None:
    """Ask the process listening on ``socket_path`` to identify itself (#68).

    Sends an authenticated ``ping`` and returns the daemon's run identity,
    or ``None`` when nothing answers, the answer is unauthenticated, or the
    response carries no identity. Never raises.
    """
    from .platform import get_ipc_client

    try:
        client = get_ipc_client()
        sock = client.connect(socket_path, IDENTITY_PROBE_TIMEOUT)
    except Exception:
        return None
    try:
        request = json.dumps({"command": "ping", "args": {}, "token": token})
        sock.sendall(request.encode())
        response_data = b""
        while len(response_data) < MAX_REQUEST_SIZE:
            chunk = sock.recv(REQUEST_CHUNK_SIZE)
            if not chunk:
                break
            response_data += chunk
        response = json.loads(response_data.decode())
    except Exception:
        return None
    finally:
        try:
            sock.close()
        except OSError:
            pass
    if not isinstance(response, dict):
        return None
    identity = response.get("identity")
    return identity if isinstance(identity, str) else None


def get_daemon_pid() -> int | None:
    """Get the PID of the running daemon.

    Returns the PID only when the PID file is current *and* the process it
    names proves its identity (#68): the daemon records a per-run nonce in
    the PID file and echoes it over ``ping``, so a recycled PID belonging to
    an unrelated process no longer reads as a live daemon.

    Also cleans up stale PID/socket files when the daemon is not running.
    """
    from .platform import is_unix

    config = get_config()

    if not config.pid_file.exists():
        return None

    try:
        raw = config.pid_file.read_text().strip()
    except OSError:
        raw = ""

    # Current format: JSON {"pid": ..., "identity": ...}. A legacy plain-int
    # file parses as a PID but carries no identity, so it can never be
    # verified and is treated as stale.
    identity: str | None = None
    pid: int | None = None
    try:
        parsed = json.loads(raw)
    except ValueError:
        parsed = None
    if isinstance(parsed, dict):
        file_pid = parsed.get("pid")
        file_identity = parsed.get("identity")
        # bool is an int subclass; a PID of ``true`` must not read as 1.
        if (
            isinstance(file_pid, int)
            and not isinstance(file_pid, bool)
            and isinstance(file_identity, str)
        ):
            pid = file_pid
            identity = file_identity
    if pid is None:
        try:
            pid = int(raw)
        except ValueError:
            pid = None

    if pid is None:
        try:
            if config.pid_file.exists():
                config.pid_file.unlink()
        except OSError:
            pass
        return None

    if not _pid_alive(pid):
        # PID file is stale, clean up
        try:
            if config.pid_file.exists():
                config.pid_file.unlink()
            # Only clean up socket file on Unix (Windows uses TCP)
            if is_unix() and config.socket_path.exists():
                config.socket_path.unlink()
        except OSError:
            pass  # Best effort cleanup
        return None

    # The PID is alive — now make sure it is *our* daemon and not whatever
    # process recycled the PID after an unclean exit (#68).
    answered = _probe_daemon_identity(config.socket_path, config.read_auth_token())
    if identity is None or answered != identity:
        logger.info(
            "PID file identity check failed (recorded=%s, answered=%s) — "
            "treating PID file as stale",
            "present" if identity else "missing",
            "matching" if answered == identity else "mismatched",
        )
        try:
            if config.pid_file.exists():
                config.pid_file.unlink()
            # Only clean up socket file on Unix (Windows uses TCP)
            if is_unix() and config.socket_path.exists():
                config.socket_path.unlink()
        except OSError:
            pass  # Best effort cleanup
        return None

    return pid


def is_daemon_running() -> bool:
    """Check if daemon is already running."""
    return get_daemon_pid() is not None


if __name__ == "__main__":
    run_daemon()
