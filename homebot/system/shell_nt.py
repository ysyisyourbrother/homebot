"""Windows subprocess execution: ``cmd.exe`` and the pitfalls that come with it.

Two rules, both learned the hard way on 2026-09-27:

* the command must reach cmd.exe **verbatim** -- handing it over as an argv
  element lets CPython escape the inner quotes as ``\\"``, cmd.exe cannot run
  that, and every quoted command fails;
* ``PYTHONIOENCODING=utf-8`` must be forwarded, because the exec tool decodes
  child stdout as UTF-8 while Python otherwise writes GBK on a Chinese
  Windows (skill output turned into mojibake before this was added).
"""

from __future__ import annotations

import asyncio
import os
from typing import Any


def build_subprocess_env(allowed_env_keys: list[str]) -> dict[str, str]:
    """Curated environment: cmd.exe has no login-profile mechanism.

    PATH and the system locations are forwarded so ordinary commands work;
    API keys and other secrets are still excluded unless explicitly allowed.
    """
    system_root = os.environ.get("SYSTEMROOT", r"C:\Windows")
    env = {
        "SYSTEMROOT": system_root,
        "COMSPEC": os.environ.get("COMSPEC", f"{system_root}\\system32\\cmd.exe"),
        "USERPROFILE": os.environ.get("USERPROFILE", ""),
        "HOMEDRIVE": os.environ.get("HOMEDRIVE", "C:"),
        "HOMEPATH": os.environ.get("HOMEPATH", "\\"),
        "TEMP": os.environ.get("TEMP", f"{system_root}\\Temp"),
        "TMP": os.environ.get("TMP", f"{system_root}\\Temp"),
        "PATHEXT": os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD"),
        "PATH": os.environ.get("PATH", f"{system_root}\\system32;{system_root}"),
        "APPDATA": os.environ.get("APPDATA", ""),
        "LOCALAPPDATA": os.environ.get("LOCALAPPDATA", ""),
        "ProgramData": os.environ.get("ProgramData", ""),
        "ProgramFiles": os.environ.get("ProgramFiles", ""),
        "ProgramFiles(x86)": os.environ.get("ProgramFiles(x86)", ""),
        "ProgramW6432": os.environ.get("ProgramW6432", ""),
        # Child stdout is decoded as UTF-8 by the exec tool.
        "PYTHONIOENCODING": "utf-8",
    }
    for key in allowed_env_keys:
        value = os.environ.get(key)
        if value is not None:
            env[key] = value
    return env


def apply_path_append(command: str, env: dict[str, str], path_append: str) -> str:
    """cmd.exe keeps the environment we hand it, so PATH is patched directly."""
    if not path_append:
        return command
    env["PATH"] = env.get("PATH", "") + ";" + path_append
    return command


async def spawn(command: str, *, cwd: str, env: dict[str, str]) -> Any:
    # shell=True keeps the command string verbatim for cmd.exe.
    return await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=env,
    )


async def kill_process(process: Any) -> None:
    process.kill()
    try:
        await asyncio.wait_for(process.wait(), timeout=5.0)
    except asyncio.TimeoutError:
        pass
