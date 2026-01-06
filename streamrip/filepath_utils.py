from string import printable
import os
import re
import unicodedata
from pathvalidate import sanitize_filename, sanitize_filepath


def truncate_str(text: str) -> str:
    # Safe byte truncation to 240 bytes (leaving room for extension/path)
    # Windows limit is 260 total, so 240 for filename is safer.
    str_bytes = text.encode("utf-8")
    if len(str_bytes) > 240:
        str_bytes = str_bytes[:240]
    return str_bytes.decode("utf-8", errors="ignore")


def remove_zalgo(text: str) -> str:
    """Removes combining characters (Zalgo text) to fix Windows errors."""
    # Normalize to NFD to separate base characters from combining marks
    normalized = unicodedata.normalize("NFD", str(text))
    # Filter out combining marks (Category Mn = Mark, Nonspacing)
    # This keeps the cool symbols (Braille, etc.) but removes the 'glitch' effect causing errors
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def clean_filename(fn: str, restrict: bool = False) -> str:
    """
    Cleans a TRACK FILENAME.
    """
    # 1. Remove Zalgo / Combining marks FIRST to reduce length and fixing syntax errors
    fn = remove_zalgo(fn)

    # 2. NFC Normalization (compose back what's left)
    fn = unicodedata.normalize("NFC", fn)

    # 3. Full replacement map (Windows Forbidden -> Full-width Unicode)
    replacements = {
        ':': '：', '/': '／', '\\': '＼', '<': '＜', '>': '＞',
        '"': '＂', '|': '｜', '?': '？', '*': '＊',
    }

    for char, replacement in replacements.items():
        fn = fn.replace(char, replacement)

    # 4. Sanitize (removes control chars)
    path = str(sanitize_filename(fn))

    # 5. Truncate (Critical for Windows)
    path = truncate_str(path)

    # 6. Aesthetic cleaning
    path = re.sub(r"\s+", " ", path).strip()

    # 7. Remove trailing dots/spaces (Windows hates 'Folder. ')
    path = path.rstrip(". ")

    if not path:
        return "Unknown_Name"

    return path


def clean_filepath(fn: str, restrict: bool = False) -> str:
    """
    Cleans a FULL PATH (folders).
    """
    # 1. Remove Zalgo from path components too
    fn = remove_zalgo(fn)
    fn = unicodedata.normalize("NFC", fn)

    # Map WITHOUT slashes (needed for folder separation)
    replacements = {
        ':': '：', '<': '＜', '>': '＞', '"': '＂', '|': '｜', '?': '？', '*': '＊',
    }

    for char, replacement in replacements.items():
        fn = fn.replace(char, replacement)

    # sanitize_filepath respects directory separators
    path = str(sanitize_filepath(fn))

    path = re.sub(r"\s+", " ", path).strip()
    path = path.rstrip(". ")  # Safety check

    return path


def truncate_filepath_to_max(path: str, max_length: int = 255) -> str:
    if len(path) <= max_length:
        return path

    dir_path, filename = os.path.split(path)
    base, ext = os.path.splitext(filename)

    # Try to keep directory structure, truncate filename
    dir_path = dir_path.rstrip(os.sep)
    allowed_base_len = max_length - len(dir_path) - len(ext) - 1

    if allowed_base_len <= 0:
        # If directory itself is too long, we are in trouble, but let's try strict cut
        return path[:max_length]

    base = base[:allowed_base_len]
    return os.path.join(dir_path, base + ext)