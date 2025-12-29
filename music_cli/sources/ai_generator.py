"""AI music generation using MusicGen (optional feature)."""

import logging
import tempfile
from pathlib import Path

from ..player.base import TrackInfo

logger = logging.getLogger(__name__)

# Flag to track if AI dependencies are available
_AI_AVAILABLE: bool | None = None
_musicgen_model = None


def is_ai_available() -> bool:
    """Check if AI music generation dependencies are available."""
    global _AI_AVAILABLE

    if _AI_AVAILABLE is not None:
        return _AI_AVAILABLE

    try:
        import torch  # noqa: F401
        from audiocraft.models import MusicGen  # noqa: F401

        _AI_AVAILABLE = True
        logger.info("AI music generation is available")
    except ImportError as e:
        _AI_AVAILABLE = False
        logger.info(f"AI music generation not available: {e}")

    return _AI_AVAILABLE


def _get_model():
    """Lazy-load the MusicGen model."""
    global _musicgen_model

    if not is_ai_available():
        return None

    if _musicgen_model is None:
        try:
            from audiocraft.models import MusicGen

            logger.info("Loading MusicGen model (this may take a moment)...")
            # Use the small model for faster loading and lower memory usage
            _musicgen_model = MusicGen.get_pretrained("facebook/musicgen-small")
            _musicgen_model.set_generation_params(duration=30)  # 30 seconds default
            logger.info("MusicGen model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load MusicGen model: {e}")
            return None

    return _musicgen_model


class AIGenerator:
    """Generates music using Meta's MusicGen model."""

    def __init__(self, output_dir: Path | None = None):
        """Initialize AI generator.

        Args:
            output_dir: Directory to save generated audio files.
                       Defaults to a temp directory.
        """
        if output_dir is None:
            output_dir = Path(tempfile.gettempdir()) / "music-cli-ai"
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @property
    def available(self) -> bool:
        """Check if AI generation is available."""
        return is_ai_available()

    def generate(
        self,
        prompt: str,
        duration: int = 30,
        filename: str | None = None,
    ) -> TrackInfo | None:
        """Generate music from a text prompt.

        Args:
            prompt: Text description of the music to generate.
            duration: Duration in seconds (5-300).
            filename: Optional output filename.

        Returns:
            TrackInfo for the generated audio, or None if generation failed.
        """
        model = _get_model()
        if model is None:
            logger.warning("AI model not available")
            return None

        try:
            import scipy.io.wavfile

            # Clamp duration
            duration = max(5, min(300, duration))
            model.set_generation_params(duration=duration)

            logger.info(f"Generating {duration}s of music: {prompt[:50]}...")

            # Generate audio
            wav = model.generate([prompt])

            # Generate filename if not provided
            if filename is None:
                import hashlib
                import time

                hash_input = f"{prompt}{time.time()}"
                short_hash = hashlib.md5(  # noqa: S324
                    hash_input.encode(), usedforsecurity=False
                ).hexdigest()[:8]
                filename = f"ai_music_{short_hash}.wav"

            # Save to file
            output_path = self.output_dir / filename

            # Get the audio tensor and sample rate
            audio = wav[0].cpu().numpy()
            sample_rate = model.sample_rate

            # Save as WAV
            scipy.io.wavfile.write(str(output_path), sample_rate, audio.T)

            logger.info(f"Generated audio saved to: {output_path}")

            return TrackInfo(
                source=str(output_path),
                source_type="ai",
                title=f"AI: {prompt[:40]}...",
                metadata={
                    "prompt": prompt,
                    "duration": duration,
                    "model": "musicgen-small",
                },
            )

        except Exception as e:
            logger.error(f"Failed to generate music: {e}")
            return None

    def generate_for_context(
        self,
        mood_prompt: str | None = None,
        temporal_prompt: str | None = None,
        duration: int = 30,
    ) -> TrackInfo | None:
        """Generate context-appropriate music.

        Args:
            mood_prompt: Mood-based prompt component.
            temporal_prompt: Time-based prompt component.
            duration: Duration in seconds.

        Returns:
            TrackInfo for the generated audio.
        """
        prompts = []

        if mood_prompt:
            prompts.append(mood_prompt)
        if temporal_prompt:
            prompts.append(temporal_prompt)

        if not prompts:
            prompts.append("ambient background music")

        full_prompt = ", ".join(prompts)
        return self.generate(full_prompt, duration)

    def cleanup_old_files(self, max_age_hours: int = 24) -> int:
        """Clean up old generated files.

        Args:
            max_age_hours: Maximum age of files to keep.

        Returns:
            Number of files deleted.
        """
        import time

        deleted = 0
        cutoff = time.time() - (max_age_hours * 3600)

        for f in self.output_dir.glob("ai_music_*.wav"):
            if f.stat().st_mtime < cutoff:
                try:
                    f.unlink()
                    deleted += 1
                except OSError:
                    pass

        return deleted


# Provide helpful error message if AI is not available
def get_ai_install_instructions() -> str:
    """Get instructions for installing AI dependencies."""
    return """
AI music generation requires additional dependencies.
Install them with:

    pip install 'music-cli[ai]'

Or install manually:

    pip install torch transformers audiocraft

Note: This requires significant disk space (~5GB) and RAM (~8GB minimum).
The first generation will download the MusicGen model (~3GB).
"""
