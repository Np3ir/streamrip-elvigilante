import os
import re
import unicodedata
from pathvalidate import sanitize_filename, sanitize_filepath


def truncate_str(text: str) -> str:
    """
    Safely truncate a string to 240 bytes to stay within Windows path limits.
    """
    str_bytes = text.encode("utf-8")
    if len(str_bytes) > 240:
        str_bytes = str_bytes[:240]
    return str_bytes.decode("utf-8", errors="ignore")


def remove_zalgo(text: str) -> str:
    """
    Remove *excessive* combining marks (Zalgo) WITHOUT stripping normal accents.

    Key idea:
    - First NFC normalize to compose standard characters (so 'n' + '~' becomes 'ñ').
    - Then remove only *extra* combining marks that create the "glitch" effect.
      We keep at most 1 combining mark after a base character (and only if it's a letter),
      and we drop the rest.

    This preserves ñ, á, é, ü, etc.
    """
    s = unicodedata.normalize("NFC", str(text))

    out = []
    combining_run = 0
    last_base_is_letter = False

    for ch in s:
        cat = unicodedata.category(ch)

        if cat == "Mn":
            combining_run += 1
            # Keep at most 1 combining mark, and only after letters
            if last_base_is_letter and combining_run == 1:
                out.append(ch)
            continue

        combining_run = 0
        last_base_is_letter = cat.startswith("L")  # Letter
        out.append(ch)

    return unicodedata.normalize("NFC", "".join(out))


def get_alpha_bucket(name: str) -> str:
    """
    Bucket for "A-Z" folders.
    - Accented Latin -> base A-Z (Á->A, Ñ->N, Ç->C, Ü->U)
    - Everything else -> '#'
    """
    if not name:
        return "#"

    s = str(name).strip()
    if not s:
        return "#"

    ch = s[0].upper()

    # Decompose accents and remove combining marks
    decomposed = unicodedata.normalize("NFD", ch)
    base = "".join(c for c in decomposed if unicodedata.category(c) != "Mn").upper()

    return base if ("A" <= base <= "Z") else "#"


def _normalize_initial_folder_component(component: str) -> str:
    """
    If the FIRST folder in the relative path is a single character folder (like 'Á', 'Ñ', 'Ø', '3'),
    normalize it:
      - Á/À/Ä -> A
      - Ñ -> N
      - Ç -> C
      - symbols/non-latin/digits -> '#'
    If it's already longer than 1 char (e.g. 'AB', 'VirtualDJ'), leave it as-is.
    """
    if not component:
        return component

    comp = str(component).strip()
    if not comp:
        return component

    if comp == "#":
        return "#"

    # only transform 1-character "initial" folders
    if len(comp) == 1:
        return get_alpha_bucket(comp)

    return component


def clean_filename(fn: str, restrict: bool = False) -> str:
    """
    Clean a track filename for safe filesystem usage.

    Keeps Unicode letters (ñ, á, ü, etc). Only replaces Windows-forbidden characters.
    """
    fn = remove_zalgo(fn)
    fn = unicodedata.normalize("NFC", fn)

    replacements = {
        ":": "：",
        "/": "／",
        "\\": "＼",
        "<": "＜",
        ">": "＞",
        '"': "＂",
        "|": "｜",
        "?": "？",
        "*": "＊",
    }
    for char, replacement in replacements.items():
        fn = fn.replace(char, replacement)

    path = str(sanitize_filename(fn))
    path = truncate_str(path)
    path = re.sub(r"\s+", " ", path).strip()
    path = path.rstrip(". ")

    return path or "Unknown_Name"


def clean_filepath(fn: str, restrict: bool = False) -> str:
    """
    Clean a full directory path for safe filesystem usage.

    IMPORTANT ADDITION:
    - Normalizes the FIRST folder component to A-Z/# rules:
      * accented latin initials -> base A-Z
      * everything else -> '#'
    This prevents folders like 'Á', 'Ñ', 'Ç' and routes them into 'A', 'N', 'C'.
    """
    fn = remove_zalgo(fn)
    fn = unicodedata.normalize("NFC", fn)

    replacements = {
        ":": "：",
        "<": "＜",
        ">": "＞",
        '"': "＂",
        "|": "｜",
        "?": "？",
        "*": "＊",
    }
    for char, replacement in replacements.items():
        fn = fn.replace(char, replacement)

    # sanitize path (keeps separators)
    path = str(sanitize_filepath(fn))
    path = re.sub(r"\s+", " ", path).strip()
    path = path.rstrip(". ")

    # Normalize the FIRST folder component (relative path expected)
    # Support both "/" and "\" separators that may appear from formatters.
    parts = re.split(r"[\\/]+", path)
    if parts:
        parts[0] = _normalize_initial_folder_component(parts[0])

    # Rebuild using OS separator
    path = os.sep.join(parts)

    return path


def truncate_filepath_to_max(path: str, max_length: int = 255) -> str:
    """
    Truncate a complete filepath to fit within a maximum length.
    """
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
