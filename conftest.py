"""
conftest.py raíz: configura el entorno de pruebas para el worktree.

Problema: pytest 9.x crea un Package collector para angry-solomon/ (que tiene __init__.py).
Package.setup() llama a importtestmodule(__init__.py) sin contexto de paquete,
fallando los imports relativos.

Solución en dos pasos:
  1. Pre-registrar 'streamrip' en sys.modules apuntando al worktree.
  2. Parchear Package.setup() para saltear la carga de nuestro __init__.py
     (ya está registrado en sys.modules como 'streamrip').
"""

import importlib.util
import os
import sys
import types
from pathlib import Path

# Archivos que pytest NO debe recolectar como tests
collect_ignore = ["__init__.py", "setup.py"]

WORKTREE = os.path.dirname(os.path.abspath(__file__))
_WORKTREE_INIT = Path(WORKTREE) / "__init__.py"

# ─── Paso 1: Agregar el worktree a sys.path ──────────────────────────────────
if WORKTREE not in sys.path:
    sys.path.insert(0, WORKTREE)


# ─── Paso 2: Pre-registrar paquete 'streamrip' ───────────────────────────────
def _pre_register():
    if "streamrip" not in sys.modules:
        sr = types.ModuleType("streamrip")
        sr.__file__ = str(_WORKTREE_INIT)
        sr.__path__ = [WORKTREE]
        sr.__package__ = "streamrip"
        sys.modules["streamrip"] = sr

    # Stub de submodulos para satisfacer `from . import X` en __init__.py
    for name in ["converter", "db", "exceptions", "media", "metadata",
                 "config", "console", "filepath_utils", "progress", "util"]:
        fullname = f"streamrip.{name}"
        if fullname not in sys.modules:
            stub = types.ModuleType(fullname)
            pkg_dir = os.path.join(WORKTREE, name)
            if os.path.isdir(pkg_dir):
                stub.__path__ = [pkg_dir]
                stub.__package__ = fullname
            else:
                stub.__package__ = "streamrip"
            sys.modules[fullname] = stub


_pre_register()


# ─── Paso 3: Parchear Package.setup() de pytest ──────────────────────────────
try:
    from _pytest.python import Package as _PytestPackage

    _orig_pkg_setup = _PytestPackage.setup

    def _patched_pkg_setup(self):
        init_path = (self.path / "__init__.py").resolve()
        if init_path == _WORKTREE_INIT.resolve():
            # 'streamrip' ya está en sys.modules; no cargar __init__.py standalone.
            return
        _orig_pkg_setup(self)

    _PytestPackage.setup = _patched_pkg_setup  # type: ignore[method-assign]
except (ImportError, AttributeError):
    pass
