"""Device paths that can hang a read or stream output forever.

POSIX exposes them through ``/dev`` and ``/proc``; Windows exposes them
through the ``\\\\.\\`` namespace and the reserved DOS device names.  The two
rule sets are deliberately separate: a Windows path cannot match a POSIX rule
and vice versa, so neither platform can weaken the other's protection (and
adding a Windows rule can never change POSIX behaviour).
"""

from __future__ import annotations

import re
from pathlib import Path

from homebot.system.capabilities import IS_POSIX, IS_WINDOWS

_POSIX_DEVICES = frozenset(
    {
        "/dev/zero",
        "/dev/random",
        "/dev/urandom",
        "/dev/full",
        "/dev/stdin",
        "/dev/stdout",
        "/dev/stderr",
        "/dev/tty",
        "/dev/console",
        "/dev/fd/0",
        "/dev/fd/1",
        "/dev/fd/2",
    }
)
_POSIX_FD = re.compile(r"/proc/(?:\d+|self)/fd/[012]$")

# \\.\PhysicalDrive0, \\.\C:, \\?\Volume{...}
_WINDOWS_NAMESPACE_PREFIXES = ("\\\\.\\", "\\\\?\\")
# Reserved DOS device names: still special with an extension (NUL.txt works).
_WINDOWS_RESERVED_NAMES = frozenset(
    {"con", "nul", "prn", "aux", "clock$"}
    | {f"com{n}" for n in range(1, 10)}
    | {f"lpt{n}" for n in range(1, 10)}
)


def _blocked_posix(raw: str) -> bool:
    try:
        resolved = str(Path(raw).resolve())
    except (OSError, ValueError):
        resolved = raw
    if raw in _POSIX_DEVICES or resolved in _POSIX_DEVICES:
        return True
    if _POSIX_FD.search(raw) or _POSIX_FD.search(resolved):
        return True
    # Covers symlinks to any other device node.
    return resolved.startswith("/dev/")


def _blocked_windows(raw: str) -> bool:
    if raw.startswith(_WINDOWS_NAMESPACE_PREFIXES):
        return True
    name = Path(raw).name
    if not name:
        return False
    return name.split(".")[0].strip().lower() in _WINDOWS_RESERVED_NAMES


def is_blocked_device(path: str | Path) -> bool:
    """True for OS device paths that could hang or produce endless output."""
    raw = str(path)
    if IS_POSIX and _blocked_posix(raw):
        return True
    if IS_WINDOWS and _blocked_windows(raw):
        return True
    return False
