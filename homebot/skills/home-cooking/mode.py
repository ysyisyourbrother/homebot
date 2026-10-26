"""Cooking-specific mode data and post-processing."""

from __future__ import annotations

import os
from pathlib import Path

from homebot.modes.plugin import ModePlugin
from homebot.modes.types import ModeState, ModeTurn


class CookingMode(ModePlugin):
    mode_id = "cooking"
    display_name = "做饭模式"

    @property
    def cooking_root(self) -> Path:
        return self.workspace / "cooking"

    @property
    def recipes_dir(self) -> Path:
        return self.cooking_root / "recipes"

    @property
    def history_path(self) -> Path:
        return self.cooking_root / "history.md"

    def prepare_session(self, state: ModeState) -> None:
        self.recipes_dir.mkdir(parents=True, exist_ok=True)
        index = self.recipes_dir / "index.md"
        if not index.exists():
            index.write_text("# 菜谱目录\n\n", encoding="utf-8")
        if not self.history_path.exists():
            self.history_path.write_text("# 做饭历史\n\n", encoding="utf-8")

    def build_runtime_context(self, state: ModeState, turn: ModeTurn) -> str:
        base = super().build_runtime_context(state, turn)
        return (
            f"{base}\n"
            "[Cooking Paths]\n"
            f"Recipes: {self.recipes_dir}\n"
            f"Recipe index: {self.recipes_dir / 'index.md'}\n"
            f"History index: {self.history_path}\n"
            "[/Cooking Paths]"
        )

    def finalize_session(
        self,
        state: ModeState,
        turns: list[ModeTurn],
        summary: str,
        reason: str,
    ) -> None:
        session_dir = state.path
        if session_dir is None:
            return
        summary_path = session_dir / "summary.md"
        existing = (
            self.history_path.read_text(encoding="utf-8")
            if self.history_path.exists()
            else ""
        )
        if state.session_id and state.session_id in existing:
            return
        link = Path(os.path.relpath(summary_path, self.history_path.parent)).as_posix()
        date = (state.started_at or "")[:10]
        row = (
            f"- {date} | `{state.session_id}` | {len(turns)} 轮 | "
            f"{reason} | [{Path(link).name}]({link})\n"
        )
        with self.history_path.open("a", encoding="utf-8") as handle:
            handle.write(row)
