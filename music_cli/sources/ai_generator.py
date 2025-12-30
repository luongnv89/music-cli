"""AI music generation using MusicGen via HuggingFace Transformers (optional feature)."""

import logging
import tempfile
from pathlib import Path

from ..player.base import TrackInfo

logger = logging.getLogger(__name__)

# Looping instruction appended to all AI prompts for seamless playback
LOOP_INSTRUCTION = (
    "seamlessly looping, smooth transitions, perfect for continuous playback, no abrupt endings"
)

# Flag to track if AI dependencies are available
_AI_AVAILABLE: bool | None = None
_musicgen_model = None
_musicgen_processor = None


def is_ai_available() -> bool:
    """Check if AI music generation dependencies are available."""
    global _AI_AVAILABLE

    if _AI_AVAILABLE is not None:
        return _AI_AVAILABLE

    try:
        import torch  # noqa: F401
        from transformers import AutoProcessor, MusicgenForConditionalGeneration  # noqa: F401

        _AI_AVAILABLE = True
        logger.info("AI music generation is available (using HuggingFace Transformers)")
    except ImportError as e:
        _AI_AVAILABLE = False
        logger.info(f"AI music generation not available: {e}")

    return _AI_AVAILABLE


def _get_model():
    """Lazy-load the MusicGen model via HuggingFace Transformers."""
    global _musicgen_model, _musicgen_processor

    if not is_ai_available():
        return None, None

    if _musicgen_model is None:
        try:
            from transformers import AutoProcessor, MusicgenForConditionalGeneration

            model_name = "facebook/musicgen-small"
            logger.info(f"Loading MusicGen model ({model_name}) - this may take a moment...")

            _musicgen_processor = AutoProcessor.from_pretrained(model_name)  # nosec B615
            _musicgen_model = MusicgenForConditionalGeneration.from_pretrained(model_name)  # nosec B615

            logger.info("MusicGen model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load MusicGen model: {e}")
            return None, None

    return _musicgen_model, _musicgen_processor


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
        add_looping: bool = True,
    ) -> TrackInfo | None:
        """Generate music from a text prompt.

        Args:
            prompt: Text description of the music to generate.
            duration: Duration in seconds (5-60 for reasonable generation time).
            filename: Optional output filename.
            add_looping: If True, append looping instructions to prompt.

        Returns:
            TrackInfo for the generated audio, or None if generation failed.
        """
        model, processor = _get_model()
        if model is None or processor is None:
            logger.warning("AI model not available")
            return None

        try:
            import scipy.io.wavfile
            import torch

            # Clamp duration (keep reasonable for generation time)
            duration = max(5, min(60, duration))

            # Calculate max_new_tokens based on duration
            # MusicGen generates at ~50 tokens per second of audio
            tokens_per_second = 50
            max_new_tokens = duration * tokens_per_second

            # Enhance prompt with looping instructions for seamless playback
            enhanced_prompt = prompt
            if add_looping:
                enhanced_prompt = f"{prompt}, {LOOP_INSTRUCTION}"

            logger.info(f"Generating {duration}s of music: {enhanced_prompt[:50]}...")

            # Process the prompt
            inputs = processor(
                text=[enhanced_prompt],
                padding=True,
                return_tensors="pt",
            )

            # Generate audio
            with torch.no_grad():
                audio_values = model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    do_sample=True,
                )

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
            # MusicGen uses 32kHz sample rate
            sample_rate = model.config.audio_encoder.sampling_rate
            audio = audio_values[0, 0].cpu().numpy()

            # Normalize audio to int16 range for WAV
            audio = (audio * 32767).astype("int16")

            # Save as WAV
            scipy.io.wavfile.write(str(output_path), sample_rate, audio)

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
            import traceback

            traceback.print_exc()
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

    pip install 'coder-music-cli[ai]'

Or install manually:

    pip install torch transformers scipy

Note: This requires significant disk space (~5GB) and RAM (~8GB minimum).
The first generation will download the MusicGen model (~1.5GB).
"""
