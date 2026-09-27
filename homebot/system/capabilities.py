"""Which platform this is, and the names that follow from it.

Answers questions only -- anything that *does* something belongs in the
``process_*`` / ``shell_*`` modules.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_POSIX = os.name == "posix"


def platform_label() -> str:
    """Human-facing platform name, used in prompts and log lines."""
    if IS_WINDOWS:
        return "Windows"
    if IS_MACOS:
        return "macOS"
    return "Linux"


def python_executable() -> str:
    """The interpreter that has homebot's dependencies installed.

    Skills are told to run scripts with this path rather than a bare
    ``python``/``python3``: on Windows there is no ``python3`` at all (the
    Store stub shadows it), and on macOS a bare ``python3`` may not be the
    interpreter homebot installed into.
    """
    return sys.executable


def default_chrome_path() -> str:
    """Conventional Chrome location for the browser tool and the skills."""
    if IS_WINDOWS:
        candidates = (
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
            Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "Application" / "chrome.exe",
        )
        return str(next((c for c in candidates if c.is_file()), candidates[0]))

    if IS_MACOS:
        return "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

    candidates = ("/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium")
    return next((c for c in candidates if Path(c).is_file()), candidates[0])
