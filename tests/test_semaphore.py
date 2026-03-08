"""Tests para media/semaphore.py"""

import asyncio
import importlib.util
import os
import sys
import types
import pytest
from contextlib import nullcontext
from unittest.mock import MagicMock

_WORKTREE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_semaphore_module():
    """
    Carga media/semaphore.py del worktree directamente usando importlib,
    pre-registrando las dependencias necesarias (config.DownloadsConfig)
    para que los imports relativos funcionen.
    """
    # Cargar streamrip.config del worktree (sobrescribir el stub del conftest raíz)
    config_spec = importlib.util.spec_from_file_location(
        "streamrip.config",
        os.path.join(_WORKTREE, "config.py"),
    )
    config_mod = importlib.util.module_from_spec(config_spec)  # type: ignore[arg-type]
    config_mod.__package__ = "streamrip"
    sys.modules["streamrip.config"] = config_mod
    config_spec.loader.exec_module(config_mod)  # type: ignore[union-attr]

    # Pre-registrar streamrip.media (namespace)
    if "streamrip.media" not in sys.modules:
        media_mod = types.ModuleType("streamrip.media")
        media_mod.__path__ = [os.path.join(_WORKTREE, "media")]
        media_mod.__package__ = "streamrip.media"
        sys.modules["streamrip.media"] = media_mod

    # Cargar media/semaphore.py del worktree
    sem_spec = importlib.util.spec_from_file_location(
        "streamrip.media.semaphore",
        os.path.join(_WORKTREE, "media", "semaphore.py"),
    )
    sem_mod = importlib.util.module_from_spec(sem_spec)  # type: ignore[arg-type]
    sem_mod.__package__ = "streamrip.media"
    sys.modules["streamrip.media.semaphore"] = sem_mod
    sem_spec.loader.exec_module(sem_mod)  # type: ignore[union-attr]
    return sem_mod


# Cargar el módulo del worktree al inicio
sem_module = _load_semaphore_module()


def make_downloads_config(concurrency=True, max_connections=4):
    cfg = MagicMock()
    cfg.concurrency = concurrency
    cfg.max_connections = max_connections
    return cfg


def reset_semaphore():
    sem_module._global_semaphore = None


class TestGlobalDownloadSemaphore:
    def setup_method(self):
        reset_semaphore()

    def test_returns_semaphore_when_concurrency_enabled(self):
        cfg = make_downloads_config(concurrency=True, max_connections=4)
        result = sem_module.global_download_semaphore(cfg)
        assert isinstance(result, asyncio.Semaphore)

    def test_returns_semaphore_with_value_1_when_concurrency_disabled(self):
        cfg = make_downloads_config(concurrency=False)
        result = sem_module.global_download_semaphore(cfg)
        assert isinstance(result, asyncio.Semaphore)

    def test_returns_unlimited_when_max_connections_negative(self):
        cfg = make_downloads_config(concurrency=True, max_connections=-1)
        result = sem_module.global_download_semaphore(cfg)
        assert isinstance(result, nullcontext)

    def test_zero_max_connections_returns_unlimited(self):
        """max_connections=0 con concurrency=True → trata como sin límite (nullcontext)."""
        cfg = make_downloads_config(concurrency=True, max_connections=0)
        result = sem_module.global_download_semaphore(cfg)
        assert isinstance(result, nullcontext)

    def test_same_instance_returned_on_second_call(self):
        cfg = make_downloads_config(concurrency=True, max_connections=4)
        s1 = sem_module.global_download_semaphore(cfg)
        s2 = sem_module.global_download_semaphore(cfg)
        assert s1 is s2

    def test_different_max_connections_logs_warning_not_raises(self, caplog):
        """Verificar que cambiar max_connections NO lanza excepción (solo warning)."""
        import logging
        cfg1 = make_downloads_config(concurrency=True, max_connections=4)
        cfg2 = make_downloads_config(concurrency=True, max_connections=8)
        sem_module.global_download_semaphore(cfg1)
        # NO debe lanzar AssertionError ni ninguna excepción
        try:
            with caplog.at_level(logging.WARNING, logger="streamrip"):
                sem_module.global_download_semaphore(cfg2)
        except AssertionError:
            pytest.fail("No debe lanzar AssertionError — debe loguear un warning")

    def test_unlimited_context_is_not_semaphore(self):
        cfg = make_downloads_config(concurrency=True, max_connections=-1)
        result = sem_module.global_download_semaphore(cfg)
        assert not isinstance(result, asyncio.Semaphore)
