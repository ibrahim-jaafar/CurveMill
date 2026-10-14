"""CurveMill package."""

# SolidWorks poisons USERPROFILE to its own (unwritable) install dir for child processes,
# so ezdxf's default "~/.cache/ezdxf" resolves into Program Files and its font-cache build
# warns. Pin ezdxf's cache home to LOCALAPPDATA (SW leaves it alone) via ezdxf's own
# supported override, before anything imports ezdxf. Belt-and-suspenders to the add-in's
# USERPROFILE fix — covers Start-menu / packaged launches the add-in never touches.
import os as _os
from pathlib import Path as _Path

_os.environ.setdefault(
    "XDG_CACHE_HOME",
    _os.environ.get("LOCALAPPDATA") or str(_Path.home() / "AppData" / "Local"),
)

__all__ = ["__version__"]

__version__ = "0.1.0"

