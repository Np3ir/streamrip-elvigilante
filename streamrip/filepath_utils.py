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
    """
    s = unicodedata.normalize("NFC", str(text))

    out = []
    combining_run = 0
    last_base_is_letter = False

    for ch in s:
        cat = unicodedata.category(ch)

        if cat == "Mn":
            combining_run += 1
            if last_base_is_letter and combining_run == 1:
                out.append(ch)
            continue

        combining_run = 0
        last_base_is_letter = cat.startswith("L")
        out.append(ch)

    return unicodedata.normalize("NFC", "".join(out))


def get_alpha_bucket(name: str) -> str:
    if not name:
        return "#"
    s = str(name).strip()
    if not s:
        return "#"
    ch = s[0].upper()
    decomposed = unicodedata.normalize("NFD", ch)
    base = "".join(c for c in decomposed if unicodedata.category(c) != "Mn").upper()
    return base if ("A" <= base <= "Z") else "#"


def _normalize_initial_folder_component(component: str) -> str:
    if not component: return component
    comp = str(component).strip()
    if not comp or comp == "#": return "#"
    if len(comp) == 1: return get_alpha_bucket(comp)
    return component


def clean_filename(fn: str, restrict: bool = False) -> str:
    """
    Clean a track filename for safe filesystem usage.
    """
    fn = remove_zalgo(fn)
    fn = unicodedata.normalize("NFC", fn)

    replacements = {
        ":": "：", "/": "／", "\\": "＼", "<": "＜", ">": "＞",
        '"': "＂", "|": "｜", "?": "？", "*": "＊",
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
    """
    fn = remove_zalgo(fn)
    fn = unicodedata.normalize("NFC", fn)

    replacements = {
        ":": "：", "<": "＜", ">": "＞", '"': "＂",
        "|": "｜", "?": "？", "*": "＊",
    }
    for char, replacement in replacements.items():
        fn = fn.replace(char, replacement)

    path = str(sanitize_filepath(fn))
    path = re.sub(r"\s+", " ", path).strip()
    path = path.rstrip(". ")

    parts = re.split(r"[\\/]+", path)
    if parts:
        parts[0] = _normalize_initial_folder_component(parts[0])

    path = os.sep.join(parts)
    return path


def truncate_filepath_to_max(path: str, max_length: int = 255) -> str:
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


# --- NUEVA FUNCIÓN: Lógica unificada para limpiar títulos de canciones ---
_RE_ANTI_FEAT = re.compile(r"\s*\((?:f(?:ea)?t\.?|with|starring)\s+(.*?)\)", flags=re.IGNORECASE)
_RE_NORMALIZE = re.compile(r'[\W_]+')

def normalize_text(text: str) -> str:
    if not text: return ""
    return _RE_NORMALIZE.sub('', text).lower()

def clean_track_title(track_path: str, artist_name: str) -> str:
    """
    Elimina (feat. Artist) del título si el artista ya está en los metadatos principales.
    Usado tanto en track.py como en playlist.py para consistencia.
    """
    match = _RE_ANTI_FEAT.search(track_path)
    if match:
        feat_artist = match.group(1)
        simple_feat = normalize_text(feat_artist)
        simple_main_artist = normalize_text(artist_name)
        # Si el artista del feat ya está en el artista principal, borramos el tag del título
        if len(simple_feat) > 2 and simple_feat in simple_main_artist:
            return track_path.replace(match.group(0), "").strip()
    
    return track_path