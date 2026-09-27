"""Backwards-compatible import path for the platform capability layer.

The implementation moved to :mod:`homebot.system` so that every platform
difference lives in one package.  This module stays as a shim because the
config schema, the browser tool and the skills import
``homebot.utils.platform``; it deliberately keeps importing nothing else from
homebot (the schema and the loader depend on each other, so the helper has to
sit outside that cycle).
"""

from __future__ import annotations

from homebot.system.capabilities import default_chrome_path, platform_label, python_executable

__all__ = ["default_chrome_path", "platform_label", "python_executable"]
