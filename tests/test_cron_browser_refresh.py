import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from homebot.agent.tools.browser import BrowserTool
from homebot.cron.browser_refresh import register_browser_refresh
from homebot.cron.service import CronService
from homebot.cron.types import CronJob, CronJobState, CronPayload, CronSchedule


class CronSystemJobTest(unittest.IsolatedAsyncioTestCase):
    def make_service(self, path: Path, on_job=None) -> CronService:
        return CronService(path, on_job=on_job, max_sleep_ms=1000)

    async def test_system_handler_does_not_call_agent_handler(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            on_job = AsyncMock()
            handler = AsyncMock()
            service = self.make_service(Path(directory) / "jobs.json", on_job=on_job)
            service.register_system_handler("refresh", handler)
            job = CronJob(
                id="system:test",
                name="Test system job",
                schedule=CronSchedule(kind="every", every_ms=1000),
                payload=CronPayload(kind="system_event", message="refresh"),
            )
            service.register_system_job(job)

            await service.run_job(job.id, force=True)

            handler.assert_awaited_once()
            on_job.assert_not_awaited()
            self.assertEqual(service.get_job(job.id).state.last_status, "ok")

    async def test_system_job_registration_preserves_schedule_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "jobs.json"
            service = self.make_service(path)
            job = CronJob(
                id="system:test",
                name="Test system job",
                schedule=CronSchedule(kind="every", every_ms=259200000),
                payload=CronPayload(kind="system_event", message="refresh"),
            )
            with patch("homebot.cron.service._now_ms", return_value=1000):
                service.register_system_job(job)
            first = service.get_job(job.id)
            first.state.last_status = "ok"
            service._save_store()

            restarted = self.make_service(path)
            replacement = CronJob(
                id=job.id,
                name=job.name,
                schedule=job.schedule,
                payload=job.payload,
            )
            with patch("homebot.cron.service._now_ms", return_value=5000):
                restarted.register_system_job(replacement)

            restored = restarted.get_job(job.id)
            self.assertEqual(restored.state.next_run_at_ms, 259201000)
            self.assertEqual(restored.state.last_status, "ok")
            self.assertEqual(restored.created_at_ms, 1000)

    async def test_changed_system_schedule_uses_new_interval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "jobs.json"
            service = self.make_service(path)
            original = CronJob(
                id="system:test",
                name="Test system job",
                schedule=CronSchedule(kind="every", every_ms=259200000),
                payload=CronPayload(kind="system_event", message="refresh"),
            )
            with patch("homebot.cron.service._now_ms", return_value=1000):
                service.register_system_job(original)

            restarted = self.make_service(path)
            changed = CronJob(
                id=original.id,
                name=original.name,
                schedule=CronSchedule(kind="every", every_ms=3600000),
                payload=original.payload,
            )
            with patch("homebot.cron.service._now_ms", return_value=5000):
                restarted.register_system_job(changed)

            self.assertEqual(restarted.get_job(original.id).state.next_run_at_ms, 3605000)

    async def test_start_preserves_overdue_job_for_single_catch_up(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "jobs.json"
            service = self.make_service(path)
            job = CronJob(
                id="system:test",
                name="Test system job",
                schedule=CronSchedule(kind="every", every_ms=1000),
                payload=CronPayload(kind="system_event", message="refresh"),
                state=CronJobState(next_run_at_ms=100),
            )
            service._store = service._load_store()
            service._store.jobs.append(job)
            service._save_store()

            restarted = self.make_service(path)
            with patch("homebot.cron.service._now_ms", return_value=5000):
                await restarted.start()
            self.assertEqual(restarted.get_job(job.id).state.next_run_at_ms, 100)
            restarted.stop()

    async def test_browser_refresh_registers_three_day_native_job(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = self.make_service(Path(directory) / "jobs.json")
            browser = BrowserTool(user_data_dir="/tmp/homebot-browser-test")
            browser.refresh_sessions = AsyncMock()

            with patch("homebot.cron.service._now_ms", return_value=1000):
                register_browser_refresh(service, browser, ["https://y.qq.com/"], 72)

            jobs = service.list_jobs()
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0].schedule.every_ms, 259200000)
            self.assertEqual(jobs[0].state.next_run_at_ms, 259201000)

            await service.run_job(jobs[0].id, force=True)
            browser.refresh_sessions.assert_awaited_once_with(["https://y.qq.com/"])

    async def test_empty_browser_refresh_config_still_claims_existing_event(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "jobs.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "jobs": [
                            {
                                "id": "system:browser-session-refresh",
                                "name": "Browser session refresh",
                                "enabled": True,
                                "schedule": {"kind": "every", "everyMs": 1000},
                                "payload": {
                                    "kind": "system_event",
                                    "message": "browser_session_refresh",
                                },
                                "state": {"nextRunAtMs": 100},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            on_job = AsyncMock()
            service = self.make_service(path, on_job=on_job)
            browser = BrowserTool(user_data_dir="/tmp/homebot-browser-test")
            browser.refresh_sessions = AsyncMock()
            register_browser_refresh(service, browser, [], 72)

            await service.run_job("system:browser-session-refresh", force=True)

            on_job.assert_not_awaited()
            browser.refresh_sessions.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
