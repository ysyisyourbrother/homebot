"""Subprocess execution, dispatched to the platform implementation."""

from __future__ import annotations

from homebot.system.capabilities import IS_WINDOWS

if IS_WINDOWS:
    from homebot.system.shell_nt import (  # noqa: F401
        apply_path_append,
        build_subprocess_env,
        kill_process,
        spawn,
    )
else:
    from homebot.system.shell_posix import (  # noqa: F401
        apply_path_append,
        build_subprocess_env,
        kill_process,
        spawn,
    )

__all__ = ["apply_path_append", "build_subprocess_env", "kill_process", "spawn"]
