"""Tests para filepath_utils.py"""

import os
import sys
import pytest

# Importar directamente del worktree (filepath_utils.py no tiene imports relativos)
_WORKTREE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WORKTREE not in sys.path:
    sys.path.insert(0, _WORKTREE)

from filepath_utils import (
    clean_filename,
    clean_filepath,
    truncate_filepath_to_max,
    remove_zalgo,
    clean_track_title,
    get_alpha_bucket,
)


class TestRemoveZalgo:
    def test_normal_text_unchanged(self):
        assert remove_zalgo("Hello World") == "Hello World"

    def test_accented_chars_preserved(self):
        result = remove_zalgo("Ñoño café")
        assert "Ñ" in result or "ñ" in result

    def test_zalgo_text_cleaned(self):
        zalgo = "H\u0300\u0301\u0302\u0303\u0304\u0305\u0306ello"
        result = remove_zalgo(zalgo)
        assert len(result) < len(zalgo)

    def test_empty_string(self):
        assert remove_zalgo("") == ""


class TestCleanFilename:
    def test_colons_replaced(self):
        result = clean_filename("Song: Title")
        assert ":" not in result

    def test_slashes_replaced(self):
        result = clean_filename("Path/to/file")
        assert "/" not in result

    def test_backslash_replaced(self):
        result = clean_filename("Path\\to\\file")
        assert "\\" not in result

    def test_empty_string_fallback(self):
        result = clean_filename("***")
        assert result  # No debe ser cadena vacía

    def test_normal_name_intact(self):
        result = clean_filename("01. Artist - Song Name")
        assert "Artist" in result
        assert "Song Name" in result

    def test_long_filename_truncated(self):
        long_name = "A" * 300
        result = clean_filename(long_name)
        assert len(result.encode("utf-8")) <= 240

    def test_question_mark_replaced(self):
        result = clean_filename("Song? Title")
        assert "?" not in result

    def test_trailing_dots_removed(self):
        result = clean_filename("Song Name.")
        assert not result.endswith(".")


class TestCleanFilepath:
    def test_no_colons_in_path(self):
        # Usar rutas relativas (pathvalidate rechaza paths Unix absolutos en Windows)
        result = clean_filepath("some/path/with: colon")
        assert ":" not in result

    def test_path_structure_preserved(self):
        result = clean_filepath("Artist/Album/track")
        assert result  # No debe estar vacío

    def test_question_mark_replaced(self):
        result = clean_filepath("path/with? question")
        assert "?" not in result


class TestTruncateFilepath:
    def test_short_path_unchanged(self):
        path = "/short/path/file.flac"
        assert truncate_filepath_to_max(path, max_length=255) == path

    def test_long_path_truncated(self):
        long_path = "/dir/" + "A" * 300 + ".flac"
        result = truncate_filepath_to_max(long_path, max_length=255)
        assert len(result) <= 255
        assert result.endswith(".flac")

    def test_extension_preserved(self):
        long_path = "/dir/" + "B" * 300 + ".mp3"
        result = truncate_filepath_to_max(long_path, max_length=200)
        assert result.endswith(".mp3")


class TestCleanTrackTitle:
    def test_feat_removed_when_artist_matches(self):
        result = clean_track_title("Song (feat. John)", "John")
        assert "feat" not in result.lower()

    def test_feat_kept_when_artist_differs(self):
        result = clean_track_title("Song (feat. John)", "Jane")
        assert "John" in result

    def test_no_feat_tag(self):
        result = clean_track_title("Normal Song Title", "Artist")
        assert result == "Normal Song Title"

    def test_ft_variant(self):
        result = clean_track_title("Song (ft. Jane)", "Jane")
        assert "ft." not in result

    def test_empty_artist(self):
        result = clean_track_title("Song (feat. John)", "")
        # Con artista vacío, no debería eliminar el feat
        assert result  # No debe ser vacío


class TestGetAlphaBucket:
    def test_latin_letter(self):
        assert get_alpha_bucket("Artist") == "A"

    def test_number_returns_hash(self):
        assert get_alpha_bucket("2Pac") == "#"

    def test_empty_returns_hash(self):
        assert get_alpha_bucket("") == "#"

    def test_accented_letter(self):
        result = get_alpha_bucket("Óscar")
        assert result == "O"

    def test_lowercase(self):
        result = get_alpha_bucket("beatles")
        assert result == "B"

    def test_whitespace_returns_hash(self):
        result = get_alpha_bucket("   ")
        assert result == "#"
