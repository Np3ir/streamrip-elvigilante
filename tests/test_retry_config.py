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

    def test_defaults_have_max_wait(self):
        config = ConfigData.defaults()
        assert hasattr(config.downloads, "max_wait")
        assert config.downloads.max_wait > 0

    def test_from_toml_injects_missing_retry_fields(self):
        """from_toml must backfill max_retries/retry_delay when absent from TOML."""
        # Build a minimal config TOML that is missing the retry fields
        base_toml = ConfigData.defaults().toml
        # Remove the retry fields so from_toml must inject them
        for field in ("max_retries", "retry_delay", "max_wait"):
            if field in base_toml["downloads"]:
                del base_toml["downloads"][field]
        from tomlkit.api import dumps
        stripped_toml_str = dumps(base_toml)
        injected = ConfigData.from_toml(stripped_toml_str)
        assert injected.downloads.max_retries == 3
        assert injected.downloads.retry_delay == 2.0
        assert injected.downloads.max_wait == 60.0

    def test_negative_max_retries_is_clamped_to_zero(self):
        """from_toml must reset negative max_retries to 0 to prevent silent download skips."""
        base_toml = ConfigData.defaults().toml
        base_toml["downloads"]["max_retries"] = -1
        from tomlkit.api import dumps
        config = ConfigData.from_toml(dumps(base_toml))
        assert config.downloads.max_retries == 0
