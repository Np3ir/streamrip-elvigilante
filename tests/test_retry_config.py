"""Tests for retry configuration fields in DownloadsConfig."""

import pytest

from streamrip.config import ConfigData, DownloadsConfig


class TestDownloadsConfigRetryDefaults:
    def _make_dl_config(self, **kwargs):
        defaults = dict(
            folder="",
            source_subdirectories=False,
            disc_subdirectories=True,
            concurrency=True,
            max_connections=6,
            requests_per_minute=60,
            verify_ssl=True,
        )
        defaults.update(kwargs)
        return DownloadsConfig(**defaults)

    def test_default_max_retries(self):
        dl = self._make_dl_config()
        assert dl.max_retries == 3

    def test_default_retry_delay(self):
        dl = self._make_dl_config()
        assert dl.retry_delay == 2.0

    def test_custom_max_retries(self):
        dl = self._make_dl_config(max_retries=5)
        assert dl.max_retries == 5

    def test_custom_retry_delay(self):
        dl = self._make_dl_config(retry_delay=1.5)
        assert dl.retry_delay == 1.5

    def test_zero_retries_allowed(self):
        dl = self._make_dl_config(max_retries=0)
        assert dl.max_retries == 0


class TestConfigDataRetryFieldsPresent:
    def test_defaults_have_max_retries(self):
        config = ConfigData.defaults()
        assert hasattr(config.downloads, "max_retries")
        assert config.downloads.max_retries >= 0

    def test_defaults_have_retry_delay(self):
        config = ConfigData.defaults()
        assert hasattr(config.downloads, "retry_delay")
        assert config.downloads.retry_delay > 0

    def test_from_toml_injects_missing_retry_fields(self):
        """Older config.toml without retry fields should get defaults injected."""
        config = ConfigData.defaults()
        assert config.downloads.max_retries == 3
        assert config.downloads.retry_delay == 2.0
