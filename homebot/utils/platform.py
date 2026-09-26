"""Small platform helpers shared by the config schema, tools and skills.

This module deliberately imports nothing from homebot: the config schema and
the config loader depend on each other, so a shared helper has to sit outside
that cycle.
"""

from __future__ import annotations

import sys
from pathlib import Path


def default_chrome_path() -> str:
    """Return the conventional Google Chrome location on this platform.

    Only used as the default for ``tools.browser.executablePath``; users can
    point it at any Chromium build.  Keeping it in one place stops the value
    from drifting between the config schema, the browser tool and the skills
    that launch Chrome themselves.
    """
    if sys.platform == "win32":
        candidates = (
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
            Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "Application" / "chrome.exe",
        )
        return str(next((c for c in candidates if c.is_file()), candidates[0]))

    if sys.platform == "darwin":
        return "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

    candidates = ("/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium")
    return next((c for c in candidates if Path(c).is_file()), candidates[0])
