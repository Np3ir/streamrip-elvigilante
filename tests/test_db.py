"""Tests para el módulo db.py"""

import gc
import os
import sys
import tempfile
import pytest

# Importar directamente del worktree (db.py solo usa stdlib, sin imports relativos)
_WORKTREE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WORKTREE not in sys.path:
    sys.path.insert(0, _WORKTREE)

from db import Downloads, Failed, Database, Dummy


def _make_db_path():
    """Crea un archivo temporal vacío y devuelve su ruta para uso como BD."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    os.unlink(tmp.name)
    return tmp.name


def _cleanup(path: str):
    """Limpia el archivo de BD de forma segura (maneja locks de Windows)."""
    gc.collect()  # forzar cierre de conexiones sqlite pendientes
    try:
        os.unlink(path)
    except (FileNotFoundError, PermissionError):
        pass  # ignorar si ya no existe o sigue bloqueado


class TestDownloads:
    def setup_method(self):
        self.db_path = _make_db_path()
        self.db = Downloads(self.db_path)

    def teardown_method(self):
        self.db = None  # soltar referencia antes de limpiar
        _cleanup(self.db_path)

    def test_create_db_file(self):
        assert os.path.exists(self.db_path)

    def test_add_and_contains(self):
        self.db.add(("track_123",))
        assert self.db.contains(id="track_123")

    def test_not_contains(self):
        assert not self.db.contains(id="nonexistent_id")

    def test_duplicate_add_does_not_raise(self):
        self.db.add(("track_dup",))
        self.db.add(("track_dup",))  # debe ignorarse sin excepción
        assert self.db.contains(id="track_dup")

    def test_all_returns_list(self):
        self.db.add(("id_1",))
        self.db.add(("id_2",))
        result = self.db.all()
        assert isinstance(result, list)
        assert len(result) == 2

    def test_invalid_key_raises_keyerror(self):
        with pytest.raises(KeyError):
            self.db.contains(invalid_col="value")

    def test_wrong_column_count_raises_valueerror(self):
        with pytest.raises(ValueError):
            self.db.add(("id_1", "extra_col"))

    def test_empty_path_raises_valueerror(self):
        with pytest.raises(ValueError):
            Downloads("")

    def test_reset_removes_file(self):
        path = self.db_path
        self.db = None  # liberar referencia para que sqlite suelte el archivo
        gc.collect()
        fresh = Downloads(path)
        fresh.reset()
        fresh = None
        gc.collect()
        assert not os.path.exists(path)


class TestFailed:
    def setup_method(self):
        self.db_path = _make_db_path()
        self.db = Failed(self.db_path)

    def teardown_method(self):
        self.db = None
        _cleanup(self.db_path)

    def test_add_and_contains(self):
        self.db.add(("tidal", "track", "abc123"))
        assert self.db.contains(source="tidal", media_type="track", id="abc123")

    def test_not_contains(self):
        assert not self.db.contains(source="tidal", media_type="track", id="nope")

    def test_all_returns_entries(self):
        self.db.add(("deezer", "album", "xyz"))
        entries = self.db.all()
        assert len(entries) >= 1

    def test_wrong_column_count_raises(self):
        with pytest.raises(ValueError):
            self.db.add(("tidal",))  # faltan columnas


class TestDatabase:
    def setup_method(self):
        self.d_path = _make_db_path()
        self.f_path = _make_db_path()
        self.database = Database(Downloads(self.d_path), Failed(self.f_path))

    def teardown_method(self):
        self.database = None
        _cleanup(self.d_path)
        _cleanup(self.f_path)

    def test_set_and_check_downloaded(self):
        self.database.set_downloaded("track_xyz")
        assert self.database.downloaded("track_xyz")

    def test_not_downloaded(self):
        assert not self.database.downloaded("unknown_id")

    def test_set_failed(self):
        self.database.set_failed("tidal", "track", "fail_001")
        failed = self.database.get_failed_downloads()
        assert any(row[2] == "fail_001" for row in failed)

    def test_downloaded_idempotent(self):
        self.database.set_downloaded("dup_id")
        self.database.set_downloaded("dup_id")  # no debe lanzar excepción
        assert self.database.downloaded("dup_id")


class TestDummy:
    def test_dummy_contains_always_false(self):
        d = Dummy()
        d.add(("anything",))
        assert not d.contains(id="anything")

    def test_dummy_all_empty(self):
        d = Dummy()
        assert d.all() == []

    def test_dummy_create_is_noop(self):
        d = Dummy()
        d.create()  # no debe lanzar excepción

    def test_dummy_remove_is_noop(self):
        d = Dummy()
        d.remove()  # no debe lanzar excepción
