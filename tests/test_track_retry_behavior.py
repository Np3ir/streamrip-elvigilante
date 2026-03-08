"""
Tests for retry and exponential backoff behavior in Track.download.

These tests use a fake Downloadable to control failure/success and mock
asyncio.sleep to assert the expected backoff pattern without slowing the suite.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from streamrip.media.track import Track
from streamrip.config import DownloadsConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_downloads_config(**overrides) -> DownloadsConfig:
    """Build a DownloadsConfig with sensible defaults plus any overrides."""
    defaults = dict(
        folder="",
        source_subdirectories=False,
        disc_subdirectories=True,
        concurrency=True,
        max_connections=6,
        requests_per_minute=60,
        verify_ssl=True,
        max_retries=3,
        retry_delay=1.0,
        max_wait=60.0,
    )
    defaults.update(overrides)
    return DownloadsConfig(**defaults)


def _make_track(downloads_config: DownloadsConfig) -> Track:
    """
    Return a Track instance with all heavy dependencies mocked out.
    Only the download loop is exercised — metadata, tagging, etc. are stubs.
    """
    meta = MagicMock()
    meta.title = "Test Track"
    meta.info.id = "test-id"
    meta.info.explicit = False
    meta.artist = "Test Artist"

    session_cfg = MagicMock()
    session_cfg.downloads = downloads_config
    session_cfg.cli.progress_bars = False
    session_cfg.filepaths.restrict_characters = False
    session_cfg.filepaths.track_format = "{artist} - {title}"
    session_cfg.filepaths.truncate_to = 0
    session_cfg.conversion.enabled = False

    config = MagicMock()
    config.session = session_cfg

    db = MagicMock()
    db.downloaded.return_value = False

    downloadable = MagicMock()
    downloadable.source = "qobuz"
    downloadable.extension = "flac"

    track = Track(
        meta=meta,
        downloadable=downloadable,
        config=config,
        folder="/tmp/test",
        cover_path=None,
        db=db,
        is_single=False,
        from_playlist=False,
    )
    track.download_path = "/tmp/test/test-track.flac"
    return track


class _FailingDownloadable:
    """Downloadable that raises `aiohttp.ClientError` a fixed number of times."""

    def __init__(self, failures: int):
        self.failures = failures
        self.attempts = 0

    async def size(self):
        return 1024

    async def download(self, path, callback):
        self.attempts += 1
        if self.attempts <= self.failures:
            import aiohttp
            raise aiohttp.ClientError(f"simulated failure #{self.attempts}")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_succeeds_on_first_attempt():
    """No failures → single attempt, no sleep."""
    dl_cfg = _make_downloads_config(max_retries=3, retry_delay=1.0)
    track = _make_track(dl_cfg)
    failing = _FailingDownloadable(failures=0)
    track.downloadable = failing

    sleep_calls = []
    with patch("streamrip.media.track.asyncio.sleep", new=AsyncMock(side_effect=sleep_calls.append)):
        with patch("streamrip.media.track.global_download_semaphore") as mock_sem:
            mock_sem.return_value.__aenter__ = AsyncMock(return_value=None)
            mock_sem.return_value.__aexit__ = AsyncMock(return_value=False)
            await track.download()

    assert failing.attempts == 1
    assert sleep_calls == []


@pytest.mark.asyncio
async def test_retries_on_transient_failure():
    """Fails twice then succeeds → 3 total attempts, 2 sleeps."""
    dl_cfg = _make_downloads_config(max_retries=3, retry_delay=1.0, max_wait=60.0)
    track = _make_track(dl_cfg)
    failing = _FailingDownloadable(failures=2)
    track.downloadable = failing

    sleep_calls = []
    with patch("streamrip.media.track.asyncio.sleep", new=AsyncMock(side_effect=sleep_calls.append)):
        with patch("streamrip.media.track.global_download_semaphore") as mock_sem:
            mock_sem.return_value.__aenter__ = AsyncMock(return_value=None)
            mock_sem.return_value.__aexit__ = AsyncMock(return_value=False)
            await track.download()

    assert failing.attempts == 3        # 2 failures + 1 success
    assert len(sleep_calls) == 2        # slept once per failure


@pytest.mark.asyncio
async def test_max_retries_zero_makes_single_attempt():
    """max_retries=0 → one attempt only, no sleep, failure recorded in db."""
    dl_cfg = _make_downloads_config(max_retries=0, retry_delay=1.0)
    track = _make_track(dl_cfg)
    failing = _FailingDownloadable(failures=5)
    track.downloadable = failing

    sleep_calls = []
    with patch("streamrip.media.track.asyncio.sleep", new=AsyncMock(side_effect=sleep_calls.append)):
        with patch("streamrip.media.track.global_download_semaphore") as mock_sem:
            mock_sem.return_value.__aenter__ = AsyncMock(return_value=None)
            mock_sem.return_value.__aexit__ = AsyncMock(return_value=False)
            await track.download()

    assert failing.attempts == 1
    assert sleep_calls == []
    track.db.set_failed.assert_called_once()


@pytest.mark.asyncio
async def test_exponential_backoff_pattern():
    """Delays follow retry_delay * 2**(attempt-1), capped at max_wait."""
    retry_delay = 1.5
    max_wait = 60.0
    dl_cfg = _make_downloads_config(max_retries=3, retry_delay=retry_delay, max_wait=max_wait)
    track = _make_track(dl_cfg)
    failing = _FailingDownloadable(failures=3)  # fails 3× then succeeds
    track.downloadable = failing

    sleep_calls = []
    with patch("streamrip.media.track.asyncio.sleep", new=AsyncMock(side_effect=sleep_calls.append)):
        with patch("streamrip.media.track.global_download_semaphore") as mock_sem:
            mock_sem.return_value.__aenter__ = AsyncMock(return_value=None)
            mock_sem.return_value.__aexit__ = AsyncMock(return_value=False)
            await track.download()

    expected = [min(max_wait, retry_delay * (2 ** i)) for i in range(3)]
    assert sleep_calls == expected


@pytest.mark.asyncio
async def test_backoff_capped_at_max_wait():
    """With high max_retries, wait never exceeds max_wait."""
    retry_delay = 2.0
    max_wait = 5.0  # low cap to test clamping
    dl_cfg = _make_downloads_config(max_retries=10, retry_delay=retry_delay, max_wait=max_wait)
    track = _make_track(dl_cfg)
    failing = _FailingDownloadable(failures=10)
    track.downloadable = failing

    sleep_calls = []
    with patch("streamrip.media.track.asyncio.sleep", new=AsyncMock(side_effect=sleep_calls.append)):
        with patch("streamrip.media.track.global_download_semaphore") as mock_sem:
            mock_sem.return_value.__aenter__ = AsyncMock(return_value=None)
            mock_sem.return_value.__aexit__ = AsyncMock(return_value=False)
            await track.download()

    assert all(w <= max_wait for w in sleep_calls), "No wait should exceed max_wait"


@pytest.mark.asyncio
async def test_cancelled_error_propagates():
    """asyncio.CancelledError must not be swallowed by the retry loop."""
    dl_cfg = _make_downloads_config(max_retries=3)
    track = _make_track(dl_cfg)

    async def _raise_cancelled(path, cb):
        raise asyncio.CancelledError()

    track.downloadable.size = AsyncMock(return_value=1024)
    track.downloadable.download = _raise_cancelled

    with patch("streamrip.media.track.global_download_semaphore") as mock_sem:
        mock_sem.return_value.__aenter__ = AsyncMock(return_value=None)
        mock_sem.return_value.__aexit__ = AsyncMock(return_value=False)
        with pytest.raises(asyncio.CancelledError):
            await track.download()
