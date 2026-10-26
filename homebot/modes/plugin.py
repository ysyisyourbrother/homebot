"""Base interface for a runtime mode implemented by a Skill."""

from __future__ import annotations

import re
from abc import ABC
from pathlib import Path
from homebot.modes.types import ModeState, ModeTurn

_FRONTMATTER = re.compile(r"^---\s*\r?\n.*?\r?\n---\s*\r?\n?", re.DOTALL)


class ModePlugin(ABC):
    """Optional backend behavior for one mode-backed Skill.

    A plugin only needs to declare ``mode_id`` and ``display_name``. The base
    implementation uses the Skill's own ``SKILL.md`` as the static system prompt.
    """

    mode_id: str
    display_name: str

    def __init__(self, skill_dir: Path, workspace: Path) -> None:
        self.skill_dir = skill_dir
        self.workspace = workspace

    @property
    def skill_name(self) -> str:
        return self.skill_dir.name

    def build_system_prompt(self, state: ModeState) -> str:
        """Build the static mode prompt snapshot created when entering a mode."""
        skill_file = self.skill_dir / "SKILL.md"
        skill_body = skill_file.read_text(encoding="utf-8") if skill_file.is_file() else ""
        skill_body = _FRONTMATTER.sub("", skill_body).strip()
        return (
            "# Active Runtime Mode\n\n"
            f"Mode: {self.display_name} (`{self.mode_id}`)\n"
            f"Session: {state.session_id}\n\n"
            "Follow this mode's Skill for the rest of the mode session. "
            "All conversations in this mode are part of the mode context. "
            "A mode persists across separate voice wakeups; it does not mean the "
            "voice channel must stay in a continuous listening turn.\n\n"
            "---\n\n"
            f"{skill_body}"
        ).strip()

    def prepare_session(self, state: ModeState) -> None:
        """Create mode-specific directories before the session becomes active."""

    def build_runtime_context(self, state: ModeState, turn: ModeTurn) -> str:
        """Return volatile information injected near the current user message."""
        session_dir = state.path
        lines = [
            "[Mode Context]",
            f"Mode: {self.display_name} ({self.mode_id})",
            f"Session ID: {state.session_id}",
            f"Speaker ID: {turn.speaker_id}",
            f"Channel: {turn.channel}",
        ]
        if session_dir:
            lines.append(f"Session directory: {session_dir}")
        return "\n".join(lines) + "\n[/Mode Context]"

    def finalize_session(
        self,
        state: ModeState,
        turns: list[ModeTurn],
        summary: str,
        reason: str,
    ) -> None:
        """Run optional domain-specific post-processing after the summary is written."""
