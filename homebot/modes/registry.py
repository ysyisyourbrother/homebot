"""Discover mode plugins from bundled and workspace Skills."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

from loguru import logger

from homebot.modes.plugin import ModePlugin


class ModeRegistry:
    """Load Skill-owned mode plugins from ``mode.json`` manifests."""

    def __init__(self, workspace: Path, builtin_skills_dir: Path | None = None) -> None:
        self.workspace = workspace
        self.builtin_skills_dir = (
            builtin_skills_dir
            if builtin_skills_dir is not None
            else Path(__file__).resolve().parent.parent / "skills"
        )
        self._plugins: dict[str, ModePlugin] = {}
        self._discovered = False

    def register(self, plugin: ModePlugin) -> None:
        """Register a plugin directly before or after manifest discovery."""
        if not plugin.mode_id or not plugin.display_name:
            raise ValueError("Mode plugins require mode_id and display_name")
        self._plugins[plugin.mode_id] = plugin

    def get(self, mode_id: str) -> ModePlugin | None:
        self.discover()
        return self._plugins.get(mode_id)

    def list(self) -> list[ModePlugin]:
        self.discover()
        return sorted(self._plugins.values(), key=lambda item: item.mode_id)

    def discover(self) -> None:
        """Scan workspace Skills first, then bundled Skills."""
        if self._discovered:
            return
        self._discovered = True

        seen: set[str] = set()
        roots = (self.workspace / "skills", self.builtin_skills_dir)
        for root in roots:
            if not root.is_dir():
                continue
            for manifest_path in sorted(root.glob("*/mode.json")):
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    mode_id = str(manifest["id"]).strip()
                    if not mode_id or mode_id in seen:
                        continue
                    plugin = self._load_plugin(manifest_path.parent, manifest)
                    if plugin.mode_id != mode_id:
                        raise ValueError(
                            f"mode.json id '{mode_id}' does not match plugin mode_id '{plugin.mode_id}'"
                        )
                    self._plugins[mode_id] = plugin
                    seen.add(mode_id)
                except Exception as exc:
                    logger.warning("Failed to load mode manifest {}: {}", manifest_path, exc)

    def _load_plugin(self, skill_dir: Path, manifest: dict[str, Any]) -> ModePlugin:
        entrypoint = str(manifest.get("entrypoint", "")).strip()
        if not entrypoint or ":" not in entrypoint:
            raise ValueError("entrypoint must use the form 'mode.py:ClassName'")
        relative_file, class_name = entrypoint.rsplit(":", 1)
        module_path = (skill_dir / relative_file).resolve()
        if module_path.parent != skill_dir.resolve():
            raise ValueError("mode entrypoint must stay inside its Skill directory")
        if not module_path.is_file():
            raise FileNotFoundError(module_path)

        module_name = "_homebot_mode_" + hashlib.sha256(
            str(module_path).encode("utf-8")
        ).hexdigest()[:16]
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load mode module: {module_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        plugin_class = getattr(module, class_name)
        plugin = plugin_class(skill_dir=skill_dir, workspace=self.workspace)
        if not isinstance(plugin, ModePlugin):
            raise TypeError(f"{entrypoint} must inherit from ModePlugin")
        return plugin
