"""Tests para config.py"""

import os
import sys
import pytest

# Importar directamente del worktree (config.py no tiene imports relativos)
_WORKTREE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WORKTREE not in sys.path:
    sys.path.insert(0, _WORKTREE)

from config import (
    ConfigData,
    DownloadsConfig,
    BLANK_CONFIG_PATH,
    CURRENT_CONFIG_VERSION,
    OutdatedConfigError,
)


class TestConfigDefaults:
    def test_blank_config_file_exists(self):
        assert os.path.isfile(BLANK_CONFIG_PATH)

    def test_defaults_load_without_error(self):
        config = ConfigData.defaults()
        assert config is not None

    def test_defaults_have_correct_version(self):
        config = ConfigData.defaults()
        assert config.misc.version == CURRENT_CONFIG_VERSION

    def test_downloads_config_fields(self):
        config = ConfigData.defaults()
        dl = config.downloads
        assert isinstance(dl.max_connections, int)
        assert isinstance(dl.requests_per_minute, int)
        assert isinstance(dl.concurrency, bool)
        assert isinstance(dl.verify_ssl, bool)

    def test_retry_fields_exist(self):
        config = ConfigData.defaults()
        dl = config.downloads
        assert hasattr(dl, "max_retries"), "DownloadsConfig debe tener max_retries"
        assert hasattr(dl, "retry_delay"), "DownloadsConfig debe tener retry_delay"
        assert dl.max_retries >= 0
        assert dl.retry_delay > 0

    def test_tidal_config_fields(self):
        config = ConfigData.defaults()
        t = config.tidal
        assert isinstance(t.quality, int)
        assert isinstance(t.download_videos, bool)


class TestConfigFromToml:
    def test_outdated_config_raises(self):
        toml_str = '[misc]\nversion = "0.0.1"\ncheck_for_updates = false\n'
        with pytest.raises(OutdatedConfigError):
            ConfigData.from_toml(toml_str)

    def test_missing_playlist_folder_injected(self):
        config = ConfigData.defaults()
        assert hasattr(config.downloads, "playlist_folder")

    def test_missing_retry_fields_get_defaults(self):
        config = ConfigData.defaults()
        assert config.downloads.max_retries == 3
        assert config.downloads.retry_delay == 2.0


class TestDownloadsConfig:
    def test_max_retries_default(self):
        dl = DownloadsConfig(
            folder="",
            source_subdirectories=False,
            disc_subdirectories=True,
            concurrency=True,
            max_connections=6,
            requests_per_minute=60,
            verify_ssl=True,
        )
        assert dl.max_retries == 3
        assert dl.retry_delay == 2.0

    def test_custom_retry_values(self):
        dl = DownloadsConfig(
            folder="",
            source_subdirectories=False,
            disc_subdirectories=True,
            concurrency=True,
            max_connections=6,
            requests_per_minute=60,
            verify_ssl=True,
            max_retries=5,
            retry_delay=1.5,
        )
        assert dl.max_retries == 5
        assert dl.retry_delay == 1.5

    def test_zero_retries_allowed(self):
        dl = DownloadsConfig(
            folder="",
            source_subdirectories=False,
            disc_subdirectories=True,
            concurrency=True,
            max_connections=6,
            requests_per_minute=60,
            verify_ssl=True,
            max_retries=0,
        )
        assert dl.max_retries == 0
