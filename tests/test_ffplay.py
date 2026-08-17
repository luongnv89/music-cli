"""Tests for the FFplayPlayer class, especially macOS audio init failure."""

import asyncio
import signal
from unittest.mock import AsyncMock, patch

import pytest

from music_cli.player.base import PlayerState, TrackInfo
from music_cli.player.ffplay import FFplayPlayer


class FakeProcess:
    """Small controllable subprocess double for lifecycle assertions."""

    def __init__(self, returncode: int | None, pid: int = 12345) -> None:
        self.returncode = returncode
        self.pid = pid
        self.wait_calls = 0
        self._finished = asyncio.Event()
        if returncode is not None:
            self._finished.set()

    async def wait(self) -> int | None:
        self.wait_calls += 1
        await self._finished.wait()
        return self.returncode

    def terminate(self) -> None:
        self.returncode = 0
        self._finished.set()

    def kill(self) -> None:
        self.returncode = -9
        self._finished.set()


class TestFFplayPlayerImmediateExit:
    """Regression tests for issue #28: ffplay exits immediately on macOS.

    When ffplay exits immediately (e.g. macOS audio device unavailable),
    play() must report failure and leave no stale loading state or process.
    """

    @pytest.mark.asyncio
    async def test_play_returns_false_and_cleans_up_immediate_exit(self, tmp_path) -> None:
        """play() returns False and clears state when ffplay exits early."""
        player = FFplayPlayer()
        mock_process = FakeProcess(returncode=1)

        with patch.object(asyncio, "create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = mock_process

            track = TrackInfo(
                source=str(tmp_path / "test.mp3"),
                source_type="local",
                title="Test Track",
            )

            result = await player.play(track)

        assert result is False
        assert player.state == PlayerState.STOPPED
        assert player.current_track is None
        assert player._process is None
        assert player._monitor_task is None
        assert mock_process.wait_calls == 1

    @pytest.mark.asyncio
    async def test_play_succeeds_when_ffplay_stays_alive(self, tmp_path) -> None:
        """play() returns True when ffplay process stays running."""
        player = FFplayPlayer()
        mock_process = FakeProcess(returncode=None)

        with patch.object(asyncio, "create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = mock_process

            track = TrackInfo(
                source=str(tmp_path / "test.mp3"),
                source_type="local",
                title="Test Track",
            )

            result = await player.play(track)
            assert result is True
            assert player.state == PlayerState.PLAYING

            await player.stop()

        assert player.state == PlayerState.STOPPED
        assert player.current_track is None

    @pytest.mark.asyncio
    async def test_play_handles_process_exception(self, tmp_path) -> None:
        """play() returns False when create_subprocess_exec raises."""
        player = FFplayPlayer()

        with patch.object(asyncio, "create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.side_effect = FileNotFoundError("ffplay not found")

            track = TrackInfo(
                source=str(tmp_path / "test.mp3"),
                source_type="local",
                title="Test Track",
            )

            result = await player.play(track)

        assert result is False
        assert player.state == PlayerState.ERROR
        assert player._process is None

    @pytest.mark.asyncio
    async def test_status_reflects_play_failure(self, tmp_path) -> None:
        """get_status() does not report loading after startup failure."""
        player = FFplayPlayer()
        mock_process = FakeProcess(returncode=1)

        with patch.object(asyncio, "create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = mock_process

            track = TrackInfo(
                source=str(tmp_path / "test.mp3"),
                source_type="local",
                title="Test Track",
            )

            await player.play(track)

        status = player.get_status()
        assert status["state"] == "stopped"
        assert status["track"] is None

    @pytest.mark.asyncio
    async def test_play_can_retry_after_immediate_exit(self, tmp_path) -> None:
        """A later track can start after an immediate startup failure."""
        player = FFplayPlayer()
        failed_process = FakeProcess(returncode=1)
        running_process = FakeProcess(returncode=None)

        with patch.object(asyncio, "create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.side_effect = [failed_process, running_process]
            track = TrackInfo(
                source=str(tmp_path / "test.mp3"),
                source_type="local",
                title="Test Track",
            )

            assert await player.play(track) is False
            assert await player.play(track) is True
            assert player.state == PlayerState.PLAYING
            assert player.current_track is track

            await player.stop()

    @pytest.mark.asyncio
    async def test_youtube_pipe_failure_falls_back_to_direct_url(self) -> None:
        """A failed YouTube pipe is cleaned up before direct URL fallback."""
        player = FFplayPlayer()
        pipe_process = FakeProcess(returncode=1, pid=12345)
        direct_process = FakeProcess(returncode=None, pid=12346)
        track = TrackInfo(
            source="https://youtube.com/watch?v=xxx",
            source_type="youtube",
            title="YouTube Track",
            metadata={"youtube_url": "https://youtube.com/watch?v=xxx"},
        )

        with patch.object(asyncio, "create_subprocess_shell", new_callable=AsyncMock) as mock_shell:
            mock_shell.return_value = pipe_process
            with patch.object(
                asyncio, "create_subprocess_exec", new_callable=AsyncMock
            ) as mock_exec:
                mock_exec.return_value = direct_process
                with patch("music_cli.player.ffplay.shutil.which", return_value="/usr/bin/yt-dlp"):
                    with patch("music_cli.player.ffplay.os.killpg") as mock_killpg:
                        result = await player.play(track)

                        assert result is True
                        assert player.state == PlayerState.PLAYING
                        assert player.current_track is track
                        assert player._process is direct_process
                        mock_killpg.assert_called_once_with(12345, signal.SIGTERM)

                        await player.stop()

        assert pipe_process.wait_calls == 1

    @pytest.mark.asyncio
    async def test_youtube_pipe_exits_immediately_and_fallback_fails(self) -> None:
        """A failed pipe and failed fallback leave no stale playback state."""
        player = FFplayPlayer()
        pipe_process = FakeProcess(returncode=1, pid=12345)
        direct_process = FakeProcess(returncode=1, pid=12346)

        with patch.object(asyncio, "create_subprocess_shell", new_callable=AsyncMock) as mock_shell:
            mock_shell.return_value = pipe_process
            with patch.object(
                asyncio, "create_subprocess_exec", new_callable=AsyncMock
            ) as mock_exec:
                mock_exec.return_value = direct_process
                with patch("music_cli.player.ffplay.shutil.which", return_value="/usr/bin/yt-dlp"):
                    with patch("music_cli.player.ffplay.os.killpg") as mock_killpg:
                        track = TrackInfo(
                            source="https://youtube.com/watch?v=xxx",
                            source_type="youtube",
                            title="YouTube Track",
                            metadata={"youtube_url": "https://youtube.com/watch?v=xxx"},
                        )

                        result = await player.play(track)

        assert result is False
        assert player.state == PlayerState.STOPPED
        assert player.current_track is None
        assert player._process is None
        assert pipe_process.wait_calls == 1
        assert direct_process.wait_calls == 1
        mock_killpg.assert_called_once_with(12345, signal.SIGTERM)

    @pytest.mark.asyncio
    async def test_youtube_pipe_stays_alive_returns_true(self) -> None:
        """YouTube pipe playback returns True when the pipe stays running."""
        player = FFplayPlayer()
        mock_process = FakeProcess(returncode=None, pid=12345)

        with patch.object(asyncio, "create_subprocess_shell", new_callable=AsyncMock) as mock_shell:
            mock_shell.return_value = mock_process
            with patch("music_cli.player.ffplay.shutil.which", return_value="/usr/bin/yt-dlp"):
                with patch(
                    "music_cli.player.ffplay.os.killpg",
                    side_effect=lambda *_args: mock_process.terminate(),
                ) as mock_killpg:
                    track = TrackInfo(
                        source="https://youtube.com/watch?v=xxx",
                        source_type="youtube",
                        title="YouTube Track",
                        metadata={"youtube_url": "https://youtube.com/watch?v=xxx"},
                    )

                    result = await player.play(track)
                    assert result is True
                    assert player.state == PlayerState.PLAYING

                    await player.stop()

        mock_killpg.assert_called_once_with(12345, 15)
