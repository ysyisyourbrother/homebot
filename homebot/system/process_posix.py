"""POSIX process control: pgrep to find, SIGTERM then SIGKILL to stop."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import time


def find_pids(pattern: str) -> list[int]:
    """PIDs whose command line contains *pattern* (treated literally)."""
    try:
        # pgrep matches an extended regex; escape so callers can pass plain paths.
        result = subprocess.run(
            ["pgrep", "-f", re.escape(pattern)], capture_output=True, text=True
        )
    except FileNotFoundError:
        return []
    return [int(token) for token in result.stdout.split() if token.strip().isdigit()]


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def terminate_pids(pids: list[int], *, timeout: float = 2.0) -> list[int]:
    """SIGTERM, wait up to *timeout*, then SIGKILL.  Returns survivors."""
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + timeout
    alive = [pid for pid in pids if _is_alive(pid)]
    while alive and time.monotonic() < deadline:
        time.sleep(0.05)
        alive = [pid for pid in alive if _is_alive(pid)]
    for pid in alive:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    return [pid for pid in alive if _is_alive(pid)]


def terminate_matching(pattern: str, *, timeout: float = 2.0) -> int:
    """Terminate every process whose command line matches *pattern*."""
    return len(terminate_pids(find_pids(pattern), timeout=timeout))


def restart_in_place(argv: list[str]) -> None:
    """Replace this process with a fresh one (POSIX ``exec`` semantics)."""
    os.execv(argv[0], argv)
