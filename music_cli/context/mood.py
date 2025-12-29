"""Mood-based music selection."""

from dataclasses import dataclass
from enum import Enum


class Mood(Enum):
    """Supported mood types."""

    HAPPY = "happy"
    SAD = "sad"
    EXCITED = "excited"
    FOCUS = "focus"
    RELAXED = "relaxed"
    ENERGETIC = "energetic"
    MELANCHOLIC = "melancholic"
    PEACEFUL = "peaceful"


@dataclass
class MoodInfo:
    """Mood context information."""

    mood: Mood
    intensity: float  # 0.0 to 1.0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "mood": self.mood.value,
            "intensity": self.intensity,
        }


class MoodContext:
    """Manages mood-based music selection."""

    # Music characteristics for each mood
    MOOD_CHARACTERISTICS = {
        Mood.HAPPY: {
            "tempo": "upbeat",
            "key": "major",
            "energy": "high",
            "genres": ["pop", "indie", "funk"],
        },
        Mood.SAD: {
            "tempo": "slow",
            "key": "minor",
            "energy": "low",
            "genres": ["acoustic", "ambient", "classical"],
        },
        Mood.EXCITED: {
            "tempo": "fast",
            "key": "major",
            "energy": "very high",
            "genres": ["electronic", "rock", "dance"],
        },
        Mood.FOCUS: {
            "tempo": "medium",
            "key": "any",
            "energy": "medium",
            "genres": ["lo-fi", "ambient", "classical", "instrumental"],
        },
        Mood.RELAXED: {
            "tempo": "slow",
            "key": "any",
            "energy": "low",
            "genres": ["chill", "ambient", "jazz"],
        },
        Mood.ENERGETIC: {
            "tempo": "fast",
            "key": "major",
            "energy": "high",
            "genres": ["electronic", "rock", "hip-hop"],
        },
        Mood.MELANCHOLIC: {
            "tempo": "slow",
            "key": "minor",
            "energy": "low",
            "genres": ["indie", "classical", "folk"],
        },
        Mood.PEACEFUL: {
            "tempo": "very slow",
            "key": "any",
            "energy": "very low",
            "genres": ["ambient", "nature", "meditation"],
        },
    }

    # AI prompts for each mood
    MOOD_PROMPTS = {
        Mood.HAPPY: "cheerful, uplifting, feel-good music with major chords and upbeat rhythm",
        Mood.SAD: "melancholic, emotional, slow tempo music with minor chords",
        Mood.EXCITED: "high energy, fast tempo, exciting electronic or rock music",
        Mood.FOCUS: "lo-fi hip hop, ambient, instrumental music for concentration",
        Mood.RELAXED: "chill, relaxing, smooth jazz or ambient soundscapes",
        Mood.ENERGETIC: "powerful, driving beats, high BPM electronic or rock",
        Mood.MELANCHOLIC: "bittersweet, nostalgic, acoustic or indie music",
        Mood.PEACEFUL: "serene, calm, nature sounds mixed with soft ambient music",
    }

    @classmethod
    def parse_mood(cls, mood_str: str) -> Mood | None:
        """Parse a mood string to Mood enum."""
        mood_str = mood_str.lower().strip()
        try:
            return Mood(mood_str)
        except ValueError:
            # Try matching partial
            for mood in Mood:
                if mood.value.startswith(mood_str):
                    return mood
            return None

    @classmethod
    def get_all_moods(cls) -> list[str]:
        """Get list of all supported moods."""
        return [m.value for m in Mood]

    @classmethod
    def get_characteristics(cls, mood: Mood) -> dict:
        """Get music characteristics for a mood."""
        return cls.MOOD_CHARACTERISTICS.get(mood, {})

    @classmethod
    def get_prompt(cls, mood: Mood) -> str:
        """Get AI music generation prompt for a mood."""
        return cls.MOOD_PROMPTS.get(mood, "background music")

    @classmethod
    def get_combined_prompt(cls, mood: Mood, temporal_prompt: str) -> str:
        """Combine mood and temporal prompts for AI generation."""
        mood_prompt = cls.get_prompt(mood)
        return f"{mood_prompt}, {temporal_prompt}"
