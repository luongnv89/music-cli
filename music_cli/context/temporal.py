"""Temporal context detection for music selection."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class TimePeriod(Enum):
    """Time periods of the day."""

    MORNING = "morning"  # 6:00 - 12:00
    AFTERNOON = "afternoon"  # 12:00 - 17:00
    EVENING = "evening"  # 17:00 - 21:00
    NIGHT = "night"  # 21:00 - 6:00


class DayType(Enum):
    """Types of days."""

    WEEKDAY = "weekday"
    WEEKEND = "weekend"


class Season(Enum):
    """Seasons of the year."""

    SPRING = "spring"
    SUMMER = "summer"
    AUTUMN = "autumn"
    WINTER = "winter"


@dataclass
class TemporalInfo:
    """Complete temporal context information."""

    time_period: TimePeriod
    day_type: DayType
    season: Season
    is_holiday: bool
    hour: int
    day_of_week: int  # 0 = Monday, 6 = Sunday
    month: int
    day: int

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "time_period": self.time_period.value,
            "day_type": self.day_type.value,
            "season": self.season.value,
            "is_holiday": self.is_holiday,
            "hour": self.hour,
            "day_of_week": self.day_of_week,
            "month": self.month,
            "day": self.day,
        }


class TemporalContext:
    """Detects temporal context for music selection."""

    # Major US holidays (month, day)
    HOLIDAYS = {
        (1, 1): "New Year's Day",
        (2, 14): "Valentine's Day",
        (7, 4): "Independence Day",
        (10, 31): "Halloween",
        (12, 24): "Christmas Eve",
        (12, 25): "Christmas",
        (12, 31): "New Year's Eve",
    }

    def __init__(self, now: datetime | None = None):
        """Initialize with optional custom datetime for testing."""
        self._now = now

    @property
    def now(self) -> datetime:
        """Get current datetime."""
        return self._now or datetime.now()

    def get_time_period(self) -> TimePeriod:
        """Get current time period of the day."""
        hour = self.now.hour

        if 6 <= hour < 12:
            return TimePeriod.MORNING
        elif 12 <= hour < 17:
            return TimePeriod.AFTERNOON
        elif 17 <= hour < 21:
            return TimePeriod.EVENING
        else:
            return TimePeriod.NIGHT

    def get_day_type(self) -> DayType:
        """Get current day type (weekday/weekend)."""
        if self.now.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return DayType.WEEKEND
        return DayType.WEEKDAY

    def get_season(self) -> Season:
        """Get current season (Northern Hemisphere)."""
        month = self.now.month

        if month in (3, 4, 5):
            return Season.SPRING
        elif month in (6, 7, 8):
            return Season.SUMMER
        elif month in (9, 10, 11):
            return Season.AUTUMN
        else:
            return Season.WINTER

    def is_holiday(self) -> bool:
        """Check if today is a holiday."""
        return (self.now.month, self.now.day) in self.HOLIDAYS

    def get_holiday_name(self) -> str | None:
        """Get the name of today's holiday, if any."""
        return self.HOLIDAYS.get((self.now.month, self.now.day))

    def get_info(self) -> TemporalInfo:
        """Get complete temporal context information."""
        return TemporalInfo(
            time_period=self.get_time_period(),
            day_type=self.get_day_type(),
            season=self.get_season(),
            is_holiday=self.is_holiday(),
            hour=self.now.hour,
            day_of_week=self.now.weekday(),
            month=self.now.month,
            day=self.now.day,
        )

    def get_music_prompt(self) -> str:
        """Generate a music prompt based on temporal context.

        Used for AI music generation.
        """
        info = self.get_info()
        parts = []

        # Time of day
        time_moods = {
            TimePeriod.MORNING: "uplifting, energizing morning",
            TimePeriod.AFTERNOON: "focused, productive afternoon",
            TimePeriod.EVENING: "relaxing, unwinding evening",
            TimePeriod.NIGHT: "calm, peaceful night",
        }
        parts.append(time_moods[info.time_period])

        # Day type
        if info.day_type == DayType.WEEKEND:
            parts.append("weekend vibes")

        # Season
        season_moods = {
            Season.SPRING: "fresh spring",
            Season.SUMMER: "warm summer",
            Season.AUTUMN: "cozy autumn",
            Season.WINTER: "serene winter",
        }
        parts.append(season_moods[info.season])

        # Holiday
        holiday = self.get_holiday_name()
        if holiday:
            parts.append(f"{holiday} celebration")

        return ", ".join(parts) + " music"
