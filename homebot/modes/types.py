"""Data types shared by the mode runtime and mode plugins."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ModeState:
    """Persistent lifecycle state stored in ``modes/action.json``."""

    active: bool = False
    mode_id: str | None = None
    display_name: str | None = None
    session_id: str | None = None
    skill_name: str | None = None
    started_at: str | None = None
    expires_at: str | None = None
    session_dir: str | None = None
    exit_reason: str | None = None
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "active": self.active,
            "mode_id": self.mode_id,
            "display_name": self.display_name,
            "session_id": self.session_id,
            "skill_name": self.skill_name,
            "started_at": self.started_at,
            "expires_at": self.expires_at,
            "session_dir": self.session_dir,
            "exit_reason": self.exit_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModeState:
        return cls(
            schema_version=int(data.get("schema_version", 1)),
            active=bool(data.get("active", False)),
            mode_id=data.get("mode_id"),
            display_name=data.get("display_name"),
            session_id=data.get("session_id"),
            skill_name=data.get("skill_name"),
            started_at=data.get("started_at"),
            expires_at=data.get("expires_at"),
            session_dir=data.get("session_dir"),
            exit_reason=data.get("exit_reason"),
        )

    @property
    def path(self) -> Path | None:
        return Path(self.session_dir) if self.session_dir else None


@dataclass
class ModeTurn:
    """One completed conversation turn inside a mode."""

    timestamp: str
    channel: str
    chat_id: str
    speaker_id: str
    user: str
    assistant: str
    media: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "channel": self.channel,
            "chat_id": self.chat_id,
            "speaker_id": self.speaker_id,
            "user": self.user,
            "assistant": self.assistant,
            "media": list(self.media),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModeTurn:
        return cls(
            timestamp=str(data.get("timestamp", "")),
            channel=str(data.get("channel", "")),
            chat_id=str(data.get("chat_id", "")),
            speaker_id=str(data.get("speaker_id", "unknown")),
            user=str(data.get("user", "")),
            assistant=str(data.get("assistant", "")),
            media=[str(item) for item in data.get("media", []) if item],
        )


@dataclass
class ModePromptContext:
    """Prompt data attached to one active-mode turn."""

    system_prompt: str
    history: list[dict[str, str]]
    runtime_context: str
    skill_name: str
