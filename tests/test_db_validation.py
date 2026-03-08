"""Tests for proper exception types in db.py (replaces assert statements)."""

import gc
import os
import tempfile

import pytest

from streamrip.db import Database, Downloads, Dummy, Failed


def _make_db_path():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    os.unlink(tmp.name)
    return tmp.name


def _cleanup(path: str):
    gc.collect()
    try:
        os.unlink(path)
    except (FileNotFoundError, PermissionError):
        pass


class TestDownloadsValidation:
    def setup_method(self):
        self.db_path = _make_db_path()
        self.db = Downloads(self.db_path)

    def teardown_method(self):
        self.db = None
        _cleanup(self.db_path)

    def test_empty_path_raises_valueerror(self):
        with pytest.raises(ValueError):
            Downloads("")

    def test_invalid_key_raises_keyerror(self):
        with pytest.raises(KeyError):
            self.db.contains(nonexistent_column="value")

    def test_wrong_column_count_raises_valueerror(self):
        with pytest.raises(ValueError):
            self.db.add(("id_1", "extra_col"))

    def test_add_and_contains(self):
        self.db.add(("track_abc",))
        assert self.db.contains(id="track_abc")

    def test_not_contains(self):
        assert not self.db.contains(id="does_not_exist")

    def test_duplicate_add_does_not_raise(self):
        self.db.add(("dup_id",))
        self.db.add(("dup_id",))
        assert self.db.contains(id="dup_id")

    def test_all_returns_list(self):
        self.db.add(("id_1",))
        self.db.add(("id_2",))
        result = self.db.all()
        assert isinstance(result, list)
        assert len(result) == 2


class TestFailedValidation:
    def setup_method(self):
        self.db_path = _make_db_path()
        self.db = Failed(self.db_path)

    def teardown_method(self):
        self.db = None
        _cleanup(self.db_path)

    def test_wrong_column_count_raises_valueerror(self):
        with pytest.raises(ValueError):
            self.db.add(("tidal",))  # missing columns

    def test_add_and_contains(self):
        self.db.add(("tidal", "track", "abc123"))
        assert self.db.contains(source="tidal", media_type="track", id="abc123")


class TestDatabaseFacade:
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
        self.database.set_downloaded("dup_id")
        assert self.database.downloaded("dup_id")


class TestDummy:
    def test_contains_always_false(self):
        d = Dummy()
        d.add(("anything",))
        assert not d.contains(id="anything")

    def test_all_empty(self):
        d = Dummy()
        assert d.all() == []

    def test_create_is_noop(self):
        Dummy().create()

    def test_remove_is_noop(self):
        Dummy().remove()
