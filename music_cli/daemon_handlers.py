"""Command handlers for the music-cli daemon.

Handlers live apart from the transport/lifecycle core in ``daemon.py`` so
``MusicDaemon`` composes them as ordinary methods: the dispatcher resolves
handlers through normal attribute lookup, which keeps per-instance
monkeypatching working. Each handler registers its command name once via
the :func:`handles` decorator; the registry is built at import time.
"""

import logging
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from .context.mood import MoodContext
from .player.base import TrackInfo

logger = logging.getLogger(__name__)


def _youtube_available() -> bool:
    """Resolve YouTube availability through ``music_cli.daemon``.

    The daemon module owns the availability flag, so resolving it late keeps
    patches against ``music_cli.daemon.is_youtube_available`` effective for
    handlers living in this module.
    """
    from .daemon import is_youtube_available

    return is_youtube_available()


_REGISTRY: dict[str, str] = {}

#: Command name -> handler method name. Built once at import time by the
#: :func:`handles` decorator; exposed read-only and re-exported as
#: ``MusicDaemon.COMMAND_HANDLERS``.
COMMAND_HANDLERS: Mapping[str, str] = MappingProxyType(_REGISTRY)


def handles(command: str) -> Any:
    """Register the decorated method as the handler for ``command``."""

    def register(method: Any) -> Any:
        _REGISTRY[command] = method.__name__
        return method

    return register


class SystemHandlers:
    """Health and lifecycle commands."""

    @handles("ping")
    async def _cmd_ping(self, args: dict) -> dict:
        """Health check. Echoes the run identity for liveness checks (#68)."""
        return {"status": "ok", "message": "pong", "identity": self._identity}

    @handles("shutdown")
    async def _cmd_shutdown(self, args: dict) -> dict:
        """Shutdown the daemon gracefully.

        Used on Windows where signal handlers aren't supported.
        """
        logger.info("Shutdown command received")
        # Schedule stop in a separate task so we can respond first
        self._spawn_task(self.stop())
        return {"status": "shutting_down"}


class PlaybackHandlers:
    """Playback control and play-mode track resolution."""

    @handles("play")
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

    @handles("stop")
    async def _cmd_stop(self, args: dict) -> dict:
        """Stop playback."""
        self._auto_play = False
        await self.player.stop()
        return {"status": "stopped"}

    @handles("pause")
    async def _cmd_pause(self, args: dict) -> dict:
        """Pause playback."""
        await self.player.pause()
        return {"status": "paused"}

    @handles("resume")
    async def _cmd_resume(self, args: dict) -> dict:
        """Resume playback."""
        await self.player.resume()
        return {"status": "playing"}

    @handles("status")
    async def _cmd_status(self, args: dict) -> dict:
        """Get current status."""
        status = self.player.get_status()
        status["auto_play"] = self._auto_play
        status["mood"] = self._current_mood.value if self._current_mood else None
        status["context"] = self.temporal.get_info().to_dict()
        return status

    @handles("next")
    async def _cmd_next(self, args: dict) -> dict:
        """Skip to next track (for auto-play mode)."""
        if self._auto_play:
            await self._play_next()
            return {"status": "playing_next"}
        else:
            return {"error": "Auto-play not enabled"}

    @handles("volume")
    async def _cmd_volume(self, args: dict) -> dict:
        """Set volume."""
        volume = args.get("level")
        if volume is None:
            return {"volume": self.player.volume}
        await self.player.set_volume(int(volume))
        return {"volume": self.player.volume}

    @handles("list_radios")
    async def _cmd_list_radios(self, args: dict) -> dict:
        """List available radio stations."""
        return {"stations": self.radio_source.list_stations()}

    @handles("list_history")
    async def _cmd_list_history(self, args: dict) -> dict:
        """List playback history."""
        limit = args.get("limit", 20)
        entries = self.history.get_all(limit=limit)
        return {"history": [{"index": i + 1, **e.to_dict()} for i, e in enumerate(entries)]}

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
            if not _youtube_available():
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

        if not _youtube_available():
            return {
                "error": "YouTube playback not available. Install with: pip install 'coder-music-cli[youtube]'"
            }

        return self.youtube_source.get_track(source)


class AIHandlers:
    """AI generation commands sharing one setup/error-mapping path (#75)."""

    @staticmethod
    def _ai_unavailable_error() -> dict:
        return {
            "error": "AI generation not available. Install with: pip install 'coder-music-cli[ai]'"
        }

    @handles("ai_list")
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

    @handles("ai_play")
    async def _cmd_ai_play(self, args: dict) -> dict:
        """Generate and play AI music.

        Args (from args dict):
            prompt: Custom prompt (optional). If not provided, uses context.
            duration: Duration in seconds (default: 5).
            mood: Mood to use for context-based generation.
            model: Model ID to use (optional). If not provided, uses default.
            lyrics: Optional lyrics for lyrics-conditioned models.
        """
        try:
            from .sources.ai_generator import is_ai_available

            if not is_ai_available():
                return self._ai_unavailable_error()

            prepared = self._prepare_ai_generation(args)
            if isinstance(prepared, dict):
                return prepared
            prompt, duration, model_id, lyrics = prepared

            track = self._generate_ai_track(prompt, duration, model_id=model_id, lyrics=lyrics)
            if not track:
                return {"error": "Failed to generate AI music"}

            self._record_generated_track(track, prompt=prompt, duration=duration, lyrics=lyrics)
            return await self._play_generated_track(track, extra={"prompt": prompt})

        except ImportError:
            return self._ai_unavailable_error()

    @handles("ai_replay")
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
            return self._invalid_ai_index_error(index)

        if not track_entry.file_exists() or regenerate:
            if not regenerate:
                return {
                    "status": "file_missing",
                    "prompt": track_entry.prompt,
                    "message": "Audio file not found. Regenerate with the same prompt?",
                }
            return await self._regenerate_ai_track(index, track_entry)

        # File exists, play it directly
        track = TrackInfo(
            source=track_entry.file_path,
            source_type="ai",
            title=f"AI: {track_entry.display_prompt(40)}",
            metadata={"prompt": track_entry.prompt, "duration": track_entry.duration},
        )
        return await self._play_generated_track(track)

    @handles("ai_remove")
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

    def _prepare_ai_generation(self, args: dict) -> dict | tuple[str, int, str | None, str | None]:
        """Validate parameters and build the prompt for ``ai_play``.

        Returns either an error response dict or the generation inputs
        ``(prompt, duration, model_id, lyrics)``.
        """
        custom_prompt = args.get("prompt")
        duration = args.get("duration", 5)
        model_id = args.get("model")
        lyrics = args.get("lyrics")

        error = self._validate_model_selection(model_id, lyrics)
        if error:
            return error

        mood = args.get("mood")
        if mood:
            self._current_mood = MoodContext.parse_mood(mood)

        if custom_prompt:
            prompt = custom_prompt
        else:
            prompts = [self.temporal.get_music_prompt()]
            if self._current_mood:
                prompts.append(MoodContext.get_prompt(self._current_mood))
            prompt = ", ".join(prompts) if prompts else "ambient background music"

        return prompt, duration, model_id, lyrics

    def _validate_model_selection(self, model_id: str | None, lyrics: str | None) -> dict | None:
        """Return an error response when the requested model/lyrics are invalid."""
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
        return None

    def _invalid_ai_index_error(self, index: int) -> dict:
        """Map a missing library entry to the client-visible index errors."""
        count = self.ai_tracks.count()
        if count == 0:
            return {"error": "No AI tracks available. Generate one with 'music-cli ai play'"}
        return {"error": f"Invalid index. Choose between 1 and {count}"}

    def _generate_ai_track(
        self,
        prompt: str,
        duration: int,
        model_id: str | None,
        lyrics: str | None,
    ) -> TrackInfo | None:
        from .sources.ai_generator import AIGenerator

        generator = AIGenerator(output_dir=self.config.ai_music_dir, config=self.config)
        return generator.generate(prompt, duration, model_id=model_id, lyrics=lyrics)

    def _record_generated_track(
        self, track: TrackInfo, *, prompt: str, duration: int, lyrics: str | None
    ) -> None:
        """Persist the generated track and log it to playback history."""
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

        self.history.log(
            source=track.source,
            source_type=track.source_type,
            title=track.title,
            mood=self._current_mood.value if self._current_mood else None,
            context=self.temporal.get_time_period().value,
        )

    async def _regenerate_ai_track(self, index: int, track_entry: Any) -> dict:
        """Regenerate a stored AI track with its original model/prompt/lyrics."""
        try:
            from .sources.ai_generator import is_ai_available

            if not is_ai_available():
                return self._ai_unavailable_error()

            # Always use the stored model for regeneration to maintain consistency
            model_id = track_entry.model

            track = self._generate_ai_track(
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

            return await self._play_generated_track(track, extra={"regenerated": True})

        except ImportError:
            return self._ai_unavailable_error()

    async def _play_generated_track(self, track: TrackInfo, extra: dict | None = None) -> dict:
        success = await self.player.play(track)

        if success:
            response = {"status": "playing", "track": track.to_dict()}
            if extra:
                response.update(extra)
            return response
        else:
            return {"error": "Failed to start playback"}


class YouTubeHistoryHandlers:
    """Cached YouTube history commands."""

    @handles("youtube_history_list")
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

    @handles("youtube_history_play")
    async def _cmd_youtube_history_play(self, args: dict) -> dict:
        index = args.get("index", 1)
        entry = self.youtube_history.get_by_index(index)
        if not entry:
            return {"error": f"Invalid index: {index}"}

        if not _youtube_available():
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

    @handles("youtube_history_remove")
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

    @handles("youtube_history_clear")
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
