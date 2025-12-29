"""Tests for context module."""

from datetime import datetime

from music_cli.context.mood import Mood, MoodContext
from music_cli.context.temporal import DayType, Season, TemporalContext, TimePeriod


class TestTemporalContext:
    """Tests for TemporalContext class."""

    def test_morning_detection(self) -> None:
        """Test morning time period detection."""
        morning = datetime(2024, 1, 15, 9, 0)  # 9 AM
        context = TemporalContext(now=morning)

        assert context.get_time_period() == TimePeriod.MORNING

    def test_afternoon_detection(self) -> None:
        """Test afternoon time period detection."""
        afternoon = datetime(2024, 1, 15, 14, 0)  # 2 PM
        context = TemporalContext(now=afternoon)

        assert context.get_time_period() == TimePeriod.AFTERNOON

    def test_evening_detection(self) -> None:
        """Test evening time period detection."""
        evening = datetime(2024, 1, 15, 19, 0)  # 7 PM
        context = TemporalContext(now=evening)

        assert context.get_time_period() == TimePeriod.EVENING

    def test_night_detection(self) -> None:
        """Test night time period detection."""
        night = datetime(2024, 1, 15, 23, 0)  # 11 PM
        context = TemporalContext(now=night)

        assert context.get_time_period() == TimePeriod.NIGHT

    def test_weekday_detection(self) -> None:
        """Test weekday detection."""
        monday = datetime(2024, 1, 15, 12, 0)  # Monday
        context = TemporalContext(now=monday)

        assert context.get_day_type() == DayType.WEEKDAY

    def test_weekend_detection(self) -> None:
        """Test weekend detection."""
        saturday = datetime(2024, 1, 13, 12, 0)  # Saturday
        context = TemporalContext(now=saturday)

        assert context.get_day_type() == DayType.WEEKEND

    def test_season_detection(self) -> None:
        """Test season detection."""
        # Winter
        winter = datetime(2024, 1, 15, 12, 0)
        assert TemporalContext(now=winter).get_season() == Season.WINTER

        # Spring
        spring = datetime(2024, 4, 15, 12, 0)
        assert TemporalContext(now=spring).get_season() == Season.SPRING

        # Summer
        summer = datetime(2024, 7, 15, 12, 0)
        assert TemporalContext(now=summer).get_season() == Season.SUMMER

        # Autumn
        autumn = datetime(2024, 10, 15, 12, 0)
        assert TemporalContext(now=autumn).get_season() == Season.AUTUMN

    def test_holiday_detection(self) -> None:
        """Test holiday detection."""
        christmas = datetime(2024, 12, 25, 12, 0)
        context = TemporalContext(now=christmas)

        assert context.is_holiday() is True
        assert context.get_holiday_name() == "Christmas"

    def test_non_holiday(self) -> None:
        """Test non-holiday detection."""
        regular_day = datetime(2024, 3, 15, 12, 0)
        context = TemporalContext(now=regular_day)

        assert context.is_holiday() is False
        assert context.get_holiday_name() is None

    def test_music_prompt_generation(self) -> None:
        """Test music prompt generation."""
        morning = datetime(2024, 7, 15, 9, 0)  # Summer morning
        context = TemporalContext(now=morning)

        prompt = context.get_music_prompt()

        assert "morning" in prompt.lower()
        assert "summer" in prompt.lower()
        assert "music" in prompt.lower()


class TestMoodContext:
    """Tests for MoodContext class."""

    def test_parse_mood_valid(self) -> None:
        """Test parsing valid mood strings."""
        assert MoodContext.parse_mood("happy") == Mood.HAPPY
        assert MoodContext.parse_mood("FOCUS") == Mood.FOCUS
        assert MoodContext.parse_mood("Sad") == Mood.SAD

    def test_parse_mood_partial(self) -> None:
        """Test parsing partial mood strings."""
        assert MoodContext.parse_mood("hap") == Mood.HAPPY
        assert MoodContext.parse_mood("foc") == Mood.FOCUS

    def test_parse_mood_invalid(self) -> None:
        """Test parsing invalid mood strings."""
        assert MoodContext.parse_mood("invalid") is None
        assert MoodContext.parse_mood("xyz123") is None

    def test_get_all_moods(self) -> None:
        """Test getting all available moods."""
        moods = MoodContext.get_all_moods()

        assert len(moods) > 0
        assert "happy" in moods
        assert "focus" in moods

    def test_mood_characteristics(self) -> None:
        """Test mood characteristics."""
        chars = MoodContext.get_characteristics(Mood.HAPPY)

        assert "tempo" in chars
        assert "energy" in chars
        assert "genres" in chars

    def test_mood_prompt(self) -> None:
        """Test mood prompt generation."""
        prompt = MoodContext.get_prompt(Mood.FOCUS)

        assert len(prompt) > 0
        assert "focus" in prompt.lower() or "concentration" in prompt.lower()
