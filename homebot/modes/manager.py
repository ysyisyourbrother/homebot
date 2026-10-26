"""Mode lifecycle, isolated context, recording, and finalization."""

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from loguru import logger

from homebot.modes.plugin import ModePlugin
from homebot.modes.registry import ModeRegistry
from homebot.modes.types import ModePromptContext, ModeState, ModeTurn

_ENTER_CUES = ("打开", "进入", "开始", "切换", "启用")
_EXIT_CUES = ("关闭", "退出", "结束")


class ModeError(ValueError):
    """Raised when a requested mode transition is not valid."""


class ModeManager:
    """Manage one explicit, workspace-global runtime mode at a time."""

    def __init__(
        self,
        workspace: Path,
        *,
        registry: ModeRegistry | None = None,
        timezone: str | None = None,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self.workspace = workspace
        self.registry = registry or ModeRegistry(workspace)
        self.timezone_name = timezone
        self._timezone = ZoneInfo(timezone) if timezone else datetime.now().astimezone().tzinfo
        self._now = now_fn or (lambda: datetime.now(self._timezone))
        self.action_path = workspace / "modes" / "action.json"
        self._lock = asyncio.Lock()
        self._pending_exits: dict[str, str | None] = {}

    async def expire_due(self) -> bool:
        """Finalize an expired mode. Safe to call before every user turn."""
        async with self._lock:
            state = self._read_state()
            if not state.active or not state.expires_at:
                return False
            if self._now() < datetime.fromisoformat(state.expires_at):
                return False
            await self._finalize_locked(state, "auto_midnight", None)
            return True

    async def enter(
        self,
        mode_id: str,
        raw_user_text: str,
        *,
        channel: str,
        chat_id: str,
    ) -> ModeState:
        """Validate and activate a mode after an LLM tool request."""
        plugin = self.registry.get(mode_id)
        if plugin is None:
            raise ModeError(f"Unknown mode: {mode_id}")
        self._require_cue(raw_user_text, plugin.display_name, _ENTER_CUES, "进入")

        async with self._lock:
            current = self._read_state()
            if current.active:
                if current.mode_id == mode_id:
                    raise ModeError(f"{plugin.display_name}已经处于开启状态")
                raise ModeError(
                    f"已有活动模式 {current.display_name or current.mode_id}，请先退出"
                )

            now = self._now()
            session_id = (
                f"{mode_id}-{now:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
            )
            session_dir = (
                self.workspace / "modes" / "sessions" / mode_id / session_id
            )
            session_dir.mkdir(parents=True, exist_ok=True)

            expires_at = datetime.combine(
                now.date() + timedelta(days=1),
                time(hour=0, minute=10),
                tzinfo=self._timezone,
            )
            state = ModeState(
                active=True,
                mode_id=mode_id,
                display_name=plugin.display_name,
                session_id=session_id,
                skill_name=plugin.skill_name,
                started_at=now.isoformat(),
                expires_at=expires_at.isoformat(),
                session_dir=str(session_dir),
            )
            plugin.prepare_session(state)
            (session_dir / "conversation.jsonl").touch(exist_ok=True)
            (session_dir / "system_prompt.md").write_text(
                plugin.build_system_prompt(state),
                encoding="utf-8",
            )
            self._write_state(state)
            logger.info(
                "Mode activated: {} ({}) via {}:{}",
                state.display_name,
                session_id,
                channel,
                chat_id,
            )
            return state

    async def request_exit(
        self,
        mode_id: str,
        raw_user_text: str,
        *,
        summary: str | None = None,
    ) -> ModeState:
        """Mark an active mode for finalization after the current reply is recorded."""
        async with self._lock:
            state = self._read_state()
            if not state.active or state.mode_id != mode_id:
                raise ModeError("当前模式与要退出的模式不一致")
            self._require_cue(
                raw_user_text,
                state.display_name or mode_id,
                _EXIT_CUES,
                "退出",
            )
            assert state.session_id is not None
            self._pending_exits[state.session_id] = summary.strip() if summary else None
            return state

    async def prompt_context(
        self,
        *,
        channel: str,
        chat_id: str,
        speaker_id: str,
    ) -> ModePromptContext | None:
        """Build the isolated prompt context for an active mode."""
        state = self._read_state()
        if not state.active:
            return None
        plugin = self._plugin_for(state)
        session_dir = state.path
        if session_dir is None:
            raise ModeError("action.json is missing session_dir")
        system_prompt = (session_dir / "system_prompt.md").read_text(encoding="utf-8")
        turns = self._read_turns(state)
        history: list[dict[str, str]] = []
        for turn in turns:
            speaker = turn.speaker_id or "unknown"
            history.append({"role": "user", "content": f"[{speaker}] {turn.user}"})
            history.append({"role": "assistant", "content": turn.assistant})

        current_turn = ModeTurn(
            timestamp=self._now().isoformat(),
            channel=channel,
            chat_id=chat_id,
            speaker_id=speaker_id or "unknown",
            user="",
            assistant="",
        )
        return ModePromptContext(
            system_prompt=system_prompt,
            history=history,
            runtime_context=plugin.build_runtime_context(state, current_turn),
            skill_name=plugin.skill_name,
        )

    async def record_turn(
        self,
        *,
        channel: str,
        chat_id: str,
        speaker_id: str,
        user: str,
        assistant: str,
        media: list[str] | None = None,
    ) -> None:
        """Record a completed turn and finalize a pending manual exit."""
        async with self._lock:
            state = self._read_state()
            if not state.active:
                return
            turn = ModeTurn(
                timestamp=self._now().isoformat(),
                channel=channel,
                chat_id=chat_id,
                speaker_id=speaker_id or "unknown",
                user=user,
                assistant=assistant,
                media=list(media or []),
            )
            self._append_turn(state, turn)

            assert state.session_id is not None
            if state.session_id in self._pending_exits:
                summary = self._pending_exits.pop(state.session_id)
                await self._finalize_locked(state, "user", summary)

    def current_state(self) -> ModeState:
        return self._read_state()

    def available_modes(self) -> list[tuple[str, str]]:
        """Return registered mode IDs and display names for the switch tool."""
        return [
            (plugin.mode_id, plugin.display_name)
            for plugin in self.registry.list()
        ]

    def _plugin_for(self, state: ModeState) -> ModePlugin:
        if not state.mode_id:
            raise ModeError("Active mode has no mode_id")
        plugin = self.registry.get(state.mode_id)
        if plugin is None:
            raise ModeError(f"Mode plugin is unavailable: {state.mode_id}")
        return plugin

    async def _finalize_locked(
        self,
        state: ModeState,
        reason: str,
        provided_summary: str | None,
    ) -> None:
        plugin = self._plugin_for(state)
        turns = self._read_turns(state)
        summary = self._build_summary(state, turns, reason, provided_summary)
        session_dir = state.path
        if session_dir is None:
            raise ModeError("Active mode has no session directory")
        (session_dir / "summary.md").write_text(summary, encoding="utf-8")
        try:
            plugin.finalize_session(state, turns, summary, reason)
        except Exception:
            logger.exception("Mode post-processing failed for {}", state.session_id)
        inactive = ModeState(exit_reason=reason)
        self._write_state(inactive)
        self._pending_exits.pop(state.session_id or "", None)
        logger.info(
            "Mode finalized: {} ({}) reason={}",
            state.display_name,
            state.session_id,
            reason,
        )

    def _build_summary(
        self,
        state: ModeState,
        turns: list[ModeTurn],
        reason: str,
        provided_summary: str | None,
    ) -> str:
        lines = [
            f"# {state.display_name or state.mode_id}总结",
            "",
            f"- 会话 ID：`{state.session_id}`",
            f"- 开始时间：{state.started_at}",
            f"- 结束时间：{self._now().isoformat()}",
            f"- 退出方式：{reason}",
            f"- 对话轮数：{len(turns)}",
            "",
        ]
        if provided_summary:
            lines += ["## 总结", "", provided_summary.strip(), ""]
        else:
            lines += [
                "## 对话摘要",
                "",
                *[
                    f"- {turn.timestamp} [{turn.speaker_id}] 用户：{turn.user}"
                    for turn in turns
                ],
                "",
            ]
        return "\n".join(lines).rstrip() + "\n"

    def _read_state(self) -> ModeState:
        if not self.action_path.is_file():
            return ModeState()
        try:
            data = json.loads(self.action_path.read_text(encoding="utf-8"))
            return ModeState.from_dict(data)
        except Exception as exc:
            logger.warning("Failed to read {}: {}", self.action_path, exc)
            return ModeState()

    def _write_state(self, state: ModeState) -> None:
        self.action_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.action_path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(state.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp_path, self.action_path)

    def _read_turns(self, state: ModeState) -> list[ModeTurn]:
        session_dir = state.path
        if session_dir is None:
            return []
        path = session_dir / "conversation.jsonl"
        if not path.is_file():
            return []
        turns: list[ModeTurn] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                turns.append(ModeTurn.from_dict(json.loads(line)))
            except json.JSONDecodeError:
                logger.warning("Skipping malformed mode turn in {}", path)
        return turns

    def _append_turn(self, state: ModeState, turn: ModeTurn) -> None:
        session_dir = state.path
        if session_dir is None:
            raise ModeError("Active mode has no session directory")
        with (session_dir / "conversation.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(turn.to_dict(), ensure_ascii=False) + "\n")

    @staticmethod
    def _require_cue(
        raw_user_text: str,
        display_name: str,
        cues: tuple[str, ...],
        action_label: str,
    ) -> None:
        text = re.sub(r"\s+", "", raw_user_text)
        if display_name not in text:
            raise ModeError(f"{action_label}模式时必须明确说出“{display_name}”")
        if not any(cue in text for cue in cues):
            raise ModeError(f"缺少明确的{action_label}动作")
