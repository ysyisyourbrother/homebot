"""Slash command routing and built-in handlers."""

from homebot.command.builtin import register_builtin_commands
from homebot.command.router import CommandContext, CommandRouter

__all__ = ["CommandContext", "CommandRouter", "register_builtin_commands"]
