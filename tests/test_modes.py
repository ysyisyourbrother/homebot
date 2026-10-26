import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from homebot.agent.context import ContextBuilder
from homebot.agent.tools.mode import SwitchModeTool
from homebot.cron.service import CronService
from homebot.modes.cron import register_mode_expiry
from homebot.modes.manager import ModeError, ModeManager


class ModeManagerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        self.now = datetime.fromisoformat("2026-10-22T19:55:00+08:00")
        self.manager = ModeManager(
            self.workspace,
            timezone="Asia/Shanghai",
            now_fn=lambda: self.now,
        )

    async def asyncTearDown(self) -> None:
        self.temp.cleanup()

    async def test_enter_requires_explicit_mode_name_and_action(self) -> None:
        with self.assertRaises(ModeError):
            await self.manager.enter(
                "cooking",
                "我们开始做饭吧",
                channel="voice",
                chat_id="voice-1",
            )

        state = await self.manager.enter(
            "cooking",
            "我要开始做饭模式",
            channel="voice",
            chat_id="voice-1",
        )

        self.assertTrue(state.active)
        self.assertEqual(state.mode_id, "cooking")
        action = json.loads(
            (self.workspace / "modes" / "action.json").read_text(encoding="utf-8")
        )
        self.assertTrue(action["active"])
        self.assertEqual(action["expires_at"], "2026-10-23T00:10:00+08:00")

        session_dir = Path(state.session_dir)
        self.assertIn(
            "# 家庭做饭",
            (session_dir / "system_prompt.md").read_text(encoding="utf-8"),
        )
        self.assertTrue((self.workspace / "cooking" / "recipes" / "index.md").is_file())

    async def test_mode_history_is_the_prompt_history_across_sessions(self) -> None:
        await self.manager.enter(
            "cooking",
            "打开做饭模式",
            channel="voice",
            chat_id="voice-1",
        )
        await self.manager.record_turn(
            channel="voice",
            chat_id="voice-1",
            speaker_id="guest",
            user="番茄炒蛋两个人怎么放盐？",
            assistant="先放两克，尝味后再补。",
        )

        prompt = await self.manager.prompt_context(
            channel="voice",
            chat_id="voice-2",
            speaker_id="guest",
        )

        self.assertIsNotNone(prompt)
        assert prompt is not None
        self.assertEqual(len(prompt.history), 2)
        self.assertIn("番茄炒蛋", prompt.history[0]["content"])
        self.assertIn("Session directory:", prompt.runtime_context)
        self.assertIn("History index:", prompt.runtime_context)

    async def test_context_builder_keeps_mode_static_and_dynamic_parts_separate(self) -> None:
        profile_path = self.workspace / "members" / "guest" / "USER.md"
        profile_path.parent.mkdir(parents=True)
        profile_path.write_text("MODE_PROFILE_SENTINEL", encoding="utf-8")
        await self.manager.enter(
            "cooking",
            "进入做饭模式",
            channel="voice",
            chat_id="voice-1",
        )
        prompt = await self.manager.prompt_context(
            channel="voice",
            chat_id="voice-2",
            speaker_id="guest",
        )
        assert prompt is not None

        messages = ContextBuilder(self.workspace).build_messages(
            history=prompt.history,
            current_message="鸡蛋要几个？",
            channel="voice",
            chat_id="voice-2",
            mode_system_prompt=prompt.system_prompt,
            mode_context=prompt.runtime_context,
            exclude_skills={prompt.skill_name},
            include_profile=False,
        )

        self.assertIn("Active Runtime Mode", messages[0]["content"])
        self.assertIn("家庭做饭", messages[0]["content"])
        self.assertNotIn("MODE_PROFILE_SENTINEL", messages[0]["content"])
        self.assertNotIn("Session directory:", messages[0]["content"])
        self.assertIn("Session directory:", messages[-1]["content"])
        self.assertIn("鸡蛋要几个", messages[-1]["content"])

    async def test_user_exit_preserves_history_and_generates_summary(self) -> None:
        state = await self.manager.enter(
            "cooking",
            "打开做饭模式",
            channel="voice",
            chat_id="voice-1",
        )
        await self.manager.record_turn(
            channel="voice",
            chat_id="voice-1",
            speaker_id="guest",
            user="两个人吃番茄炒蛋。",
            assistant="用两个番茄和三个鸡蛋。",
        )
        await self.manager.request_exit(
            "cooking",
            "关闭做饭模式",
            summary="- 做番茄炒蛋\n- 两人份",
        )
        await self.manager.record_turn(
            channel="voice",
            chat_id="voice-1",
            speaker_id="guest",
            user="关闭做饭模式",
            assistant="做饭模式已关闭。",
        )

        self.assertFalse(self.manager.current_state().active)
        session_dir = Path(state.session_dir)
        self.assertTrue((session_dir / "conversation.jsonl").is_file())
        summary = (session_dir / "summary.md").read_text(encoding="utf-8")
        self.assertIn("做番茄炒蛋", summary)
        self.assertIn("退出方式：user", summary)
        history = (self.workspace / "cooking" / "history.md").read_text(encoding="utf-8")
        self.assertIn(state.session_id, history)

    async def test_mode_expires_after_next_midnight(self) -> None:
        state = await self.manager.enter(
            "cooking",
            "开始做饭模式",
            channel="voice",
            chat_id="voice-1",
        )
        await self.manager.record_turn(
            channel="voice",
            chat_id="voice-1",
            speaker_id="guest",
            user="今晚做青菜。",
            assistant="好的。",
        )

        self.now = datetime.fromisoformat("2026-10-23T00:09:59+08:00")
        self.assertFalse(await self.manager.expire_due())
        self.assertTrue(self.manager.current_state().active)

        self.now += timedelta(minutes=1)
        self.assertTrue(await self.manager.expire_due())
        self.assertFalse(self.manager.current_state().active)
        summary = (Path(state.session_dir) / "summary.md").read_text(encoding="utf-8")
        self.assertIn("退出方式：auto_midnight", summary)

    async def test_switch_mode_tool_uses_backend_validation(self) -> None:
        tool = SwitchModeTool(self.manager)
        tool.set_context("voice", "voice-1", "我们开始做饭吧")
        rejected = await tool.execute("enter", "cooking")
        self.assertTrue(rejected.startswith("Error:"))

        tool.set_context("voice", "voice-1", "请进入做饭模式")
        entered = await tool.execute("enter", "cooking", None)
        self.assertIn("Mode entered", entered)
        self.assertTrue(self.manager.current_state().active)

    async def test_mode_expiry_cron_job_is_registered_at_0010(self) -> None:
        cron = CronService(
            self.workspace / "cron" / "jobs.json",
            max_sleep_ms=1000,
        )
        with patch("homebot.cron.service._now_ms", return_value=1000):
            register_mode_expiry(cron, self.manager)

        job = cron.get_job("system:runtime-mode-expire")
        self.assertIsNotNone(job)
        assert job is not None
        self.assertEqual(job.schedule.expr, "10 0 * * *")
        self.assertEqual(job.schedule.tz, "Asia/Shanghai")


if __name__ == "__main__":
    unittest.main()
