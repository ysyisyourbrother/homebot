"""Process control, dispatched to the platform implementation.

The branch happens once, at import time; every caller uses the same names.
"""

from __future__ import annotations

from homebot.system.capabilities import IS_WINDOWS

if IS_WINDOWS:
    from homebot.system.process_nt import (  # noqa: F401
        find_pids,
        restart_in_place,
        terminate_matching,
        terminate_pids,
    )
else:
    from homebot.system.process_posix import (  # noqa: F401
        find_pids,
        restart_in_place,
        terminate_matching,
        terminate_pids,
    )

__all__ = ["find_pids", "restart_in_place", "terminate_matching", "terminate_pids"]
