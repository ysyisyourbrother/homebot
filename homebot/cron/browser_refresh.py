"""Periodic browser session refresh driven by CronService."""

from homebot.agent.tools.browser import BrowserTool
from homebot.cron.service import CronService
from homebot.cron.types import CronJob, CronPayload, CronSchedule

_EVENT = "browser_session_refresh"
_JOB_ID = "system:browser-session-refresh"


def register_browser_refresh(
    cron: CronService,
    browser: BrowserTool,
    urls: list[str],
    interval_hours: int,
) -> None:
    """Register the native handler and its protected periodic job."""

    async def refresh(_job: CronJob) -> None:
        if urls:
            await browser.refresh_sessions(urls)

    cron.register_system_handler(_EVENT, refresh)
    if not urls:
        return

    cron.register_system_job(
        CronJob(
            id=_JOB_ID,
            name="Browser session refresh",
            schedule=CronSchedule(kind="every", every_ms=interval_hours * 60 * 60 * 1000),
            payload=CronPayload(kind="system_event", message=_EVENT),
        )
    )
