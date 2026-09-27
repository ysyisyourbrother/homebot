"""Platform capability layer.

Everything that genuinely differs between operating systems lives in this
package, behind one interface.  Business code imports from here and never
branches on ``sys.platform`` itself, so:

* shared logic stays shared (one implementation to maintain), and
* each platform's implementation lives in its own module
  (``process_nt.py`` vs ``process_posix.py``, ``shell_nt.py`` vs
  ``shell_posix.py``), so changing one cannot break the other.

See ``docs/architecture/platform-support.md`` for the human-facing overview.
"""

from homebot.system.capabilities import (
    IS_MACOS,
    IS_POSIX,
    IS_WINDOWS,
    default_chrome_path,
    platform_label,
    python_executable,
)
from homebot.system.devices import is_blocked_device
from homebot.system.process import (
    find_pids,
    restart_in_place,
    terminate_matching,
    terminate_pids,
)
from homebot.system.shell import (
    apply_path_append,
    build_subprocess_env,
    kill_process,
    spawn,
)

__all__ = [
    "IS_MACOS",
    "IS_POSIX",
    "IS_WINDOWS",
    "apply_path_append",
    "build_subprocess_env",
    "default_chrome_path",
    "find_pids",
    "is_blocked_device",
    "kill_process",
    "platform_label",
    "python_executable",
    "restart_in_place",
    "spawn",
    "terminate_matching",
    "terminate_pids",
]
