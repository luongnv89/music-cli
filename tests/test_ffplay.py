"""Tests for the FFplayPlayer class, especially macOS audio init failure."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from music_cli.player.base import PlayerState, TrackInfo
from music_cli.player.ffplay import FFplayPlayer


class TestFFplayPlayerImmediateExit:
    """Regression tests for issue #28: ffplay exits immediately on macOS.

    When ffplay exits immediately (e.g. macOS audio device unavailable),
    the old code would set state to PLAYING and return True, while the
    monitor task would quickly set STOPPED — leaving the daemon in an
    inconsistent state where `mc status` reported "stopped" while the
    CLI thought it was "playing".

    The fix adds a 0.1s verification delay after spawning ffplay: if
    poll() returns a non-None exit code, play() returns False instead.
    """

    @pytest.mark.asyncio
    async def test_play_returns_false_when_ffplay_exits_immediately(self) -> None:
        """play() returns False when ffplay process exits before verification."""
        player = FFplayPlayer()

        mock_process = MagicMock()
        mock_process.poll.return_value = 1  # exited immediately
        mock_process.pid = 12345

        with patch.object(asyncio, "create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = mock_process

            track = TrackInfo(
                source="/tmp/test.mp3",
                source_type="local",
                title="Test Track",
            )

            result = await player.play(track)

            assert result is False
            # State should NOT be PLAYING
            assert player.state != PlayerState.PLAYING

    @pytest.mark.asyncio
    async def test_play_succeeds_when_ffplay_stays_alive(self) -> None:
        """play() returns True when ffplay process stays running."""
        player = FFplayPlayer()

        mock_process = MagicMock()
        mock_process.poll.return_value = None  # still running
        mock_process.pid = 12345

        with patch.object(asyncio, "create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = mock_process

            track = TrackInfo(
                source="/tmp/test.mp3",
                source_type="local",
                title="Test Track",
            )

            result = await player.play(track)

            assert result is True
            assert player.state == PlayerState.PLAYING

    @pytest.mark.asyncio
    async def test_play_handles_process_exception(self) -> None:
        """play() returns False when create_subprocess_exec raises."""
        player = FFplayPlayer()

        with patch.object(asyncio, "create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.side_effect = FileNotFoundError("ffplay not found")

            track = TrackInfo(
                source="/tmp/test.mp3",
                source_type="local",
                title="Test Track",
            )

            result = await player.play(track)

            assert result is False
            assert player.state == PlayerState.ERROR

    @pytest.mark.asyncio
    async def test_status_reflects_play_result(self) -> None:
        """get_status() returns correct state after play() failure."""
        player = FFplayPlayer()

        mock_process = MagicMock()
        mock_process.poll.return_value = 1  # exited immediately

        with patch.object(asyncio, "create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = mock_process

            track = TrackInfo(
                source="/tmp/test.mp3",
                source_type="local",
                title="Test Track",
            )

            await player.play(track)

            status = player.get_status()
            # The key assertion: state should NOT be "playing"
            assert status["state"] != "playing"

    @pytest.mark.asyncio
    async def test_youtube_pipe_exits_immediately_returns_false(self) -> None:
        """YouTube pipe playback returns False when the pipe process exits."""
        player = FFplayPlayer()

        mock_process = MagicMock()
        mock_process.poll.return_value = 1  # exited immediately
        mock_process.pid = 12345

        with patch.object(asyncio, "create_subprocess_shell", new_callable=AsyncMock) as mock_shell:
            mock_shell.return_value = mock_process

            track = TrackInfo(
                source="https://youtube.com/watch?v=xxx",
                source_type="youtube",
                title="YouTube Track",
                metadata={"youtube_url": "https://youtube.com/watch?v=xxx"},
            )

            result = await player.play(track)

            assert result is False

    @pytest.mark.asyncio
    async def test_youtube_pipe_stays_alive_returns_true(self) -> None:
        """YouTube pipe playback returns True when the pipe process stays running."""
        player = FFplayPlayer()

        mock_process = MagicMock()
        mock_process.poll.return_value = None  # still running
        mock_process.pid = 12345

        with patch.object(asyncio, "create_subprocess_shell", new_callable=AsyncMock) as mock_shell:
            mock_shell.return_value = mock_process

            track = TrackInfo(
                source="https://youtube.com/watch?v=xxx",
                source_type="youtube",
                title="YouTube Track",
                metadata={"youtube_url": "https://youtube.com/watch?v=xxx"},
            )

            result = await player.play(track)

            assert result is True
            assert player.state == PlayerState.PLAYING
