"""Cron integration for automatic mode expiry."""

from __future__ import annotations

from homebot.cron.service import CronService
from homebot.cron.types import CronJob, CronPayload, CronSchedule
from homebot.modes.manager import ModeManager

_EVENT = "runtime_mode_expire"
_JOB_ID = "system:runtime-mode-expire"


def register_mode_expiry(cron: CronService, manager: ModeManager) -> None:
    """Register the protected 00:10 mode expiry job."""

    async def expire(_job: CronJob) -> None:
        await manager.expire_due()

    cron.register_system_handler(_EVENT, expire)
    cron.register_system_job(
        CronJob(
            id=_JOB_ID,
            name="Runtime mode daily expiry",
            schedule=CronSchedule(
                kind="cron",
                expr="10 0 * * *",
                tz=manager.timezone_name,
            ),
            payload=CronPayload(kind="system_event", message=_EVENT),
        )
    )
