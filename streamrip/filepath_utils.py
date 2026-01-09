from string import printable
import os
import re
import unicodedata
from pathvalidate import sanitize_filename, sanitize_filepath


def truncate_str(text: str) -> str:
    """
    Safely truncate a string to 240 bytes to stay within Windows path limits.
    
    Windows has a 260 character path limit, so 240 bytes for the filename
    leaves room for extensions and parent directories.
    
    Args:
        text: The string to truncate
        
    Returns:
        Truncated string that fits within byte limit
    """
    str_bytes = text.encode("utf-8")
    if len(str_bytes) > 240:
        str_bytes = str_bytes[:240]
    return str_bytes.decode("utf-8", errors="ignore")


def remove_zalgo(text: str) -> str:
    """
    Remove combining characters (Zalgo text) that cause Windows filesystem errors.
    
    Normalizes to NFD (separate base chars from combining marks), then filters out
    combining marks (Unicode category Mn). This preserves symbols like Braille while
    removing the 'glitch' effect that causes Windows errors.
    
    Args:
        text: String potentially containing zalgo/combining characters
        
    Returns:
        Cleaned string with combining marks removed
    """
    # Normalize to NFD to separate base characters from combining marks
    normalized = unicodedata.normalize("NFD", str(text))
    # Filter out combining marks (Category Mn = Mark, Nonspacing)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def clean_filename(fn: str, restrict: bool = False) -> str:
    """
    Clean a track filename for safe filesystem usage.
    
    Process:
    1. Remove zalgo/combining characters
    2. NFC normalize (recompose remaining characters)
    3. Replace Windows-forbidden characters with full-width Unicode equivalents
    4. Sanitize (remove control characters)
    5. Truncate to safe length
    6. Clean up whitespace
    7. Remove trailing dots/spaces (Windows compatibility)
    
    Args:
        fn: Filename to clean
        restrict: If True, apply additional character restrictions (unused but kept for compatibility)
        
    Returns:
        Cleaned filename safe for all filesystems
    """
    # Remove zalgo/combining marks first to reduce length and fix syntax errors
    fn = remove_zalgo(fn)

    # NFC normalization (compose back what's left)
    fn = unicodedata.normalize("NFC", fn)

    # Replace Windows-forbidden characters with full-width Unicode equivalents
    # This preserves the visual appearance while making them filesystem-safe
    replacements = {
        ':': '：', '/': '／', '\\': '＼', '<': '＜', '>': '＞',
        '"': '＂', '|': '｜', '?': '？', '*': '＊',
    }

    for char, replacement in replacements.items():
        fn = fn.replace(char, replacement)

    # Sanitize to remove control characters
    path = str(sanitize_filename(fn))

    # Truncate to safe length (critical for Windows)
    path = truncate_str(path)

    # Clean up whitespace (collapse multiple spaces to one)
    path = re.sub(r"\s+", " ", path).strip()

    # Remove trailing dots/spaces (Windows doesn't allow these)
    path = path.rstrip(". ")

    # Return fallback name if result is empty
    if not path:
        return "Unknown_Name"

    return path


def clean_filepath(fn: str, restrict: bool = False) -> str:
    """
    Clean a full directory path for safe filesystem usage.
    
    Similar to clean_filename but preserves directory separators (/ and \).
    Process is the same except slashes are not replaced.
    
    Args:
        fn: Full path to clean
        restrict: If True, apply additional character restrictions (unused but kept for compatibility)
        
    Returns:
        Cleaned path safe for all filesystems
    """
    # Remove zalgo from all path components
    fn = remove_zalgo(fn)
    fn = unicodedata.normalize("NFC", fn)

    # Replace forbidden characters but preserve slashes for directory separation
    replacements = {
        ':': '：', '<': '＜', '>': '＞', '"': '＂', '|': '｜', '?': '？', '*': '＊',
    }

    for char, replacement in replacements.items():
        fn = fn.replace(char, replacement)

    # sanitize_filepath respects directory separators
    path = str(sanitize_filepath(fn))

    # Clean up whitespace
    path = re.sub(r"\s+", " ", path).strip()
    
    # Remove trailing dots/spaces for safety
    path = path.rstrip(". ")

    return path


def truncate_filepath_to_max(path: str, max_length: int = 255) -> str:
    """
    Truncate a complete filepath to fit within a maximum length.
    
    Intelligently truncates the filename portion while preserving the directory
    structure and file extension as much as possible.
    
    Args:
        path: Complete filepath to truncate
        max_length: Maximum allowed path length (default 255 for most filesystems)
        
    Returns:
        Truncated path that fits within max_length
    """
    if len(path) <= max_length:
        return path

    dir_path, filename = os.path.split(path)
    base, ext = os.path.splitext(filename)

    # Try to preserve directory structure, truncate filename only
    dir_path = dir_path.rstrip(os.sep)
    allowed_base_len = max_length - len(dir_path) - len(ext) - 1

    if allowed_base_len <= 0:
        # Directory itself is too long, do strict truncation as last resort
        return path[:max_length]

    # Truncate the base filename to fit
    base = base[:allowed_base_len]
    return os.path.join(dir_path, base + ext)