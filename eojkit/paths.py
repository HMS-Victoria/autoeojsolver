"""Portable resources and writable user data, kept separate."""
import os
import sys
from pathlib import Path

APP_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("EOJ_DATA_DIR") or (
    str(Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "EOJSolver")
    if getattr(sys, "frozen", False) else str(APP_DIR)
))
