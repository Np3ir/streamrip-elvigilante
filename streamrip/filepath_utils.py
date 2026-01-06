from string import printable
import os
import re
import unicodedata
from pathvalidate import sanitize_filename, sanitize_filepath


def truncate_str(text: str) -> str:
    # Safe byte truncation
    str_bytes = text.encode()
    str_bytes = str_bytes[:255]
    return str_bytes.decode(errors="ignore")


def clean_filename(fn: str, restrict: bool = False) -> str:
    """
    Cleans a TRACK FILENAME.
    Replaces ALL forbidden characters (including / and \) with visual equivalents.
    """
    # 1. NFC Normalization
    fn = unicodedata.normalize("NFC", str(fn))

    # 2. Full replacement map (Windows Forbidden -> Full-width Unicode)
    replacements = {
        ':': '：',
        '/': '／',
        '\\': '＼',
        '<': '＜',
        '>': '＞',
        '"': '＂',
        '|': '｜',
        '?': '？',
        '*': '＊',
    }

    for char, replacement in replacements.items():
        fn = fn.replace(char, replacement)

    # 3. Basic sanitize (remove nulls)
    path = truncate_str(str(sanitize_filename(fn)))

    # 4. Aesthetic cleaning
    path = re.sub(r"\s+", " ", path).strip()

    return path


def clean_filepath(fn: str, restrict: bool = False) -> str:
    """
    Cleans a FULL PATH (folders).
    Applies visual replacements BUT respects slashes / and \ for folder structure.
    """
    fn = unicodedata.normalize("NFC", str(fn))

    # Map WITHOUT slashes (needed for folder separation)
    replacements = {
        ':': '：',
        '<': '＜',
        '>': '＞',
        '"': '＂',
        '|': '｜',
        '?': '？',
        '*': '＊',
    }

    for char, replacement in replacements.items():
        fn = fn.replace(char, replacement)

    # sanitize_filepath respects directory separators
    path = str(sanitize_filepath(fn))

    path = re.sub(r"\s+", " ", path).strip()

    return path


def truncate_filepath_to_max(path: str, max_length: int = 260) -> str:
    if len(path) <= max_length:
        return path

    dir_path, filename = os.path.split(path)
    base, ext = os.path.splitext(filename)
    dir_path = dir_path.rstrip(os.sep)
    allowed_base_len = max_length - len(dir_path) - len(ext) - 1

    if allowed_base_len <= 0:
        return path[:max_length]

    base = base[:allowed_base_len]
    return os.path.join(dir_path, base + ext)