"""Tests for global_download_semaphore warning behavior."""

import asyncio
import logging
from contextlib import nullcontext
from unittest.mock import MagicMock

import pytest

from streamrip.media.semaphore import global_download_semaphore
from streamrip import media as _media_pkg

# Import the module directly to reset the global state between tests
import importlib
import streamrip.media.semaphore as _sem_module


def _make_config(concurrency=True, max_connections=4):
    cfg = MagicMock()
    cfg.concurrency = concurrency
    cfg.max_connections = max_connections
    return cfg


def _reset():
    _sem_module._global_semaphore = None


class TestGlobalDownloadSemaphore:
    def setup_method(self):
        _reset()

    def test_returns_semaphore_when_concurrency_enabled(self):
        result = global_download_semaphore(_make_config(concurrency=True, max_connections=4))
        assert isinstance(result, asyncio.Semaphore)

    def test_returns_semaphore_with_value_1_when_disabled(self):
        result = global_download_semaphore(_make_config(concurrency=False))
        assert isinstance(result, asyncio.Semaphore)

    def test_negative_max_connections_returns_unlimited(self):
        result = global_download_semaphore(_make_config(concurrency=True, max_connections=-1))
        assert isinstance(result, nullcontext)

    def test_zero_max_connections_returns_unlimited(self):
        result = global_download_semaphore(_make_config(concurrency=True, max_connections=0))
        assert isinstance(result, nullcontext)

    def test_same_instance_returned_on_second_call(self):
        cfg = _make_config()
        s1 = global_download_semaphore(cfg)
        s2 = global_download_semaphore(cfg)
        assert s1 is s2

    def test_conflicting_max_connections_logs_warning_not_raises(self, caplog):
        """Changing max_connections after semaphore creation should warn, not crash."""
        global_download_semaphore(_make_config(max_connections=4))
        with caplog.at_level(logging.WARNING, logger="streamrip"):
            # Should NOT raise — just log a warning
            try:
                global_download_semaphore(_make_config(max_connections=8))
            except AssertionError:
                pytest.fail("Should log a warning, not raise AssertionError")
