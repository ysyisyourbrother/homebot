"""Runtime path helpers derived from the active config context."""

from __future__ import annotations

from pathlib import Path

from homebot.config.loader import get_config_path
from homebot.utils.helpers import ensure_dir


def get_data_dir() -> Path:
    """Return the instance-level runtime data directory."""
    return ensure_dir(get_config_path().parent)


def get_runtime_subdir(name: str) -> Path:
    """Return a named runtime subdirectory under the instance data dir."""
    return ensure_dir(get_data_dir() / name)


def get_browser_data_dir(user_data_dir: str | None = None) -> Path:
    """Return the persistent browser profile directory owned by Homebot."""
    return ensure_dir(Path(user_data_dir).expanduser()) if user_data_dir else ensure_dir(get_workspace_path() / "browser")


def get_media_dir(channel: str | None = None) -> Path:
    """Return the media directory, optionally namespaced per channel."""
    base = get_runtime_subdir("media")
    return ensure_dir(base / channel) if channel else base


def get_logs_dir() -> Path:
    """Return the logs directory."""
    return get_runtime_subdir("logs")


def get_workspace_path(workspace: str | None = None) -> Path:
    """Resolve and ensure the agent workspace path."""
    path = Path(workspace).expanduser() if workspace else Path.home() / ".homebot" / "workspace"
    return ensure_dir(path)


def is_default_workspace(workspace: str | Path | None) -> bool:
    """Return whether a workspace resolves to homebot's default workspace path."""
    current = Path(workspace).expanduser() if workspace is not None else Path.home() / ".homebot" / "workspace"
    default = Path.home() / ".homebot" / "workspace"
    return current.resolve(strict=False) == default.resolve(strict=False)


def get_cli_history_path() -> Path:
    """Return the shared CLI history file path."""
    return Path.home() / ".homebot" / "history" / "cli_history"


def get_legacy_sessions_dir() -> Path:
    """Return the legacy global session directory used for migration fallback."""
    return Path.home() / ".homebot" / "sessions"
