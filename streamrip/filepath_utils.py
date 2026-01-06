from string import printable
import os
import re
import unicodedata
from pathvalidate import sanitize_filename, sanitize_filepath


def truncate_str(text: str) -> str:
    # Truncado seguro por bytes
    str_bytes = text.encode()
    str_bytes = str_bytes[:255]
    return str_bytes.decode(errors="ignore")


def clean_filename(fn: str, restrict: bool = False) -> str:
    """
    Limpia un NOMBRE DE ARCHIVO individual (track).
    Reemplaza TODOS los caracteres prohibidos (incluyendo / y \) por equivalentes visuales.
    """
    # 1. Normalización NFC
    fn = unicodedata.normalize("NFC", str(fn))

    # 2. Mapa completo de reemplazos (Windows Forbidden -> Full-width Unicode)
    replacements = {
        ':': '：',
        '/': '／',  # En un nombre de archivo, la barra también se reemplaza
        '\\': '＼',  # La barra invertida también
        '<': '＜',
        '>': '＞',
        '"': '＂',
        '|': '｜',
        '?': '？',
        '*': '＊',
    }

    for char, replacement in replacements.items():
        fn = fn.replace(char, replacement)

    # 3. Sanitize básico (quita nulos)
    path = truncate_str(str(sanitize_filename(fn)))

    # 4. Limpieza estética
    path = re.sub(r"\s+", " ", path).strip()

    return path


def clean_filepath(fn: str, restrict: bool = False) -> str:
    """
    Limpia una RUTA COMPLETA (carpetas).
    Aplica los reemplazos visuales PERO respeta las barras / y \ para las carpetas.
    """
    fn = unicodedata.normalize("NFC", str(fn))

    # Mapa SIN las barras (porque las necesitamos para separar carpetas)
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

    # sanitize_filepath respeta los separadores de directorios
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