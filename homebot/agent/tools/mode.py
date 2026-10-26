"""Tool exposed to the LLM for explicit runtime mode transitions."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from homebot.agent.tools.base import Tool, tool_parameters
from homebot.modes.manager import ModeError, ModeManager


@tool_parameters(
    {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["enter", "exit"],
                "description": "Enter or exit a persistent runtime mode.",
            },
            "mode_id": {
                "type": "string",
                "description": "Registered mode id, for example 'cooking'.",
            },
            "summary": {
                "type": "string",
                "description": (
                    "When exiting, a concise summary of what happened in the mode. "
                    "Include important dishes, quantities, adjustments, and outcomes."
                ),
            },
        },
        "required": ["action", "mode_id"],
    }
)
class SwitchModeTool(Tool):
    """Let the LLM request mode changes; the backend performs validation."""

    def __init__(self, manager: ModeManager) -> None:
        self._manager = manager
        self._raw_user_text: ContextVar[str] = ContextVar(
            "switch_mode_raw_user_text",
            default="",
        )
        self._channel: ContextVar[str] = ContextVar("switch_mode_channel", default="direct")
        self._chat_id: ContextVar[str] = ContextVar("switch_mode_chat_id", default="direct")

    @property
    def name(self) -> str:
        return "switch_mode"

    @property
    def description(self) -> str:
        available = ", ".join(
            f"{mode_id} ({display_name})"
            for mode_id, display_name in self._manager.available_modes()
        )
        return (
            "Switch homebot's persistent runtime mode. Call this only when the user "
            "explicitly asks to enter or exit a mode. The user's message must contain "
            "the exact mode display name, such as '做饭模式', plus an explicit action. "
            "Do not infer a mode switch from a cooking topic or other subject matter. "
            f"Available modes: {available or 'none'}. "
            "Never edit action.json directly; this tool is the only transition interface."
        )

    def set_context(
        self,
        channel: str,
        chat_id: str,
        raw_user_text: str | None = None,
    ) -> None:
        self._channel.set(channel)
        self._chat_id.set(chat_id)
        if raw_user_text is not None:
            self._raw_user_text.set(raw_user_text)

    async def execute(
        self,
        action: str,
        mode_id: str,
        summary: str | None = None,
        **_: Any,
    ) -> str:
        try:
            if action == "enter":
                state = await self._manager.enter(
                    mode_id,
                    self._raw_user_text.get(),
                    channel=self._channel.get(),
                    chat_id=self._chat_id.get(),
                )
                return (
                    f"Mode entered: {state.display_name} ({mode_id}). "
                    "Reply to the user that the mode is now active."
                )
            if action == "exit":
                state = await self._manager.request_exit(
                    mode_id,
                    self._raw_user_text.get(),
                    summary=summary,
                )
                return (
                    f"Mode exit accepted: {state.display_name} ({mode_id}). "
                    "Reply to the user; finalization happens after this turn."
                )
            return f"Error: unsupported mode action: {action}"
        except ModeError as exc:
            return f"Error: {exc}"
