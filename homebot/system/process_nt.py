"""Windows process control.

Command-line matching goes through CIM (what Task Manager shows); stopping
uses ``taskkill /T`` so a child tree dies with its parent.  Liveness is probed
with ``OpenProcess`` + ``WaitForSingleObject`` because ``os.kill(pid, 0)`` on
Windows does not check anything -- it terminates the process.
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import time

_SYNCHRONIZE = 0x00100000
_WAIT_TIMEOUT = 0x00000102

# The filter travels through the environment: embedding it in the command line
# would hit cmd.exe quoting (see the 2026-09-27 exec bug) and it may contain
# spaces or wildcards.
_CIM_QUERY = (
    "$ErrorActionPreference='SilentlyContinue';"
    "Get-CimInstance Win32_Process | "
    "Where-Object { $_.CommandLine -like $env:HOMEBOT_PROC_FILTER } | "
    "Select-Object -ExpandProperty ProcessId | ConvertTo-Json -Compress"
)


def _cim_literal(value: str) -> str:
    """Escape a literal string for PowerShell's ``-like`` operator."""
    for char in ("[", "]", "*", "?"):
        value = value.replace(char, f"[{char}]")
    return value


def find_pids(pattern: str) -> list[int]:
    """PIDs whose command line contains *pattern* (treated literally)."""
    env = dict(os.environ)
    env["HOMEBOT_PROC_FILTER"] = f"*{_cim_literal(pattern)}*"
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _CIM_QUERY],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    except FileNotFoundError:
        return []
    output = (result.stdout or "").strip()
    if not output:
        return []
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return []
    if isinstance(data, int):
        return [data]
    if isinstance(data, list):
        return [int(item) for item in data]
    return []


def _is_alive(pid: int) -> bool:
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = kernel32.OpenProcess(_SYNCHRONIZE, False, pid)
    if not handle:
        return False
    try:
        return kernel32.WaitForSingleObject(handle, 0) == _WAIT_TIMEOUT
    finally:
        kernel32.CloseHandle(handle)


def terminate_pids(pids: list[int], *, timeout: float = 2.0) -> list[int]:
    """Force-stop the given processes (and their trees).  Returns survivors."""
    for pid in pids:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
        )
    deadline = time.monotonic() + timeout
    alive = [pid for pid in pids if _is_alive(pid)]
    while alive and time.monotonic() < deadline:
        time.sleep(0.05)
        alive = [pid for pid in alive if _is_alive(pid)]
    return alive


def terminate_matching(pattern: str, *, timeout: float = 2.0) -> int:
    """Terminate every process whose command line matches *pattern*."""
    return len(terminate_pids(find_pids(pattern), timeout=timeout))


def restart_in_place(argv: list[str]) -> None:  # noqa: ARG001 - interface parity
    """Windows has no ``exec``: exit so the supervisor starts a fresh process.

    ``os.execv`` on Windows spawns the new process while the old one still
    holds the HTTP port, so the new one dies on bind and the supervisor
    retries -- a restart storm.  The documented deployment runs the gateway
    under a supervisor (the Task Scheduler launcher), which restarts it.
    """
    os._exit(0)
