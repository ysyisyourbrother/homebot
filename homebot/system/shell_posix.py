"""POSIX subprocess execution: ``bash -l -c`` with a deliberately small env.

Passing a minimal environment is intentional: ``bash -l`` sources the user's
profile, which restores PATH and the essentials, while API keys and other
secrets in the gateway's environment stay out of the child process.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from typing import Any


def build_subprocess_env(allowed_env_keys: list[str]) -> dict[str, str]:
    env = {
        "HOME": os.environ.get("HOME", "/tmp"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "TERM": os.environ.get("TERM", "dumb"),
    }
    for key in allowed_env_keys:
        value = os.environ.get(key)
        if value is not None:
            env[key] = value
    return env


def apply_path_append(command: str, env: dict[str, str], path_append: str) -> str:
    """A login shell rebuilds PATH, so the extra entry must be exported inline."""
    if not path_append:
        return command
    return f'export PATH="$PATH:{path_append}"; {command}'


async def spawn(command: str, *, cwd: str, env: dict[str, str]) -> Any:
    bash = shutil.which("bash") or "/bin/bash"
    return await asyncio.create_subprocess_exec(
        bash,
        "-l",
        "-c",
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=env,
    )


async def kill_process(process: Any) -> None:
    """Kill and reap, so no zombie is left behind."""
    process.kill()
    try:
        await asyncio.wait_for(process.wait(), timeout=5.0)
    except asyncio.TimeoutError:
        pass
    try:
        os.waitpid(process.pid, os.WNOHANG)
    except (ProcessLookupError, ChildProcessError):
        pass
