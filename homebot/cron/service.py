"""Cron service for scheduling agent tasks."""

import asyncio
import fcntl
import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Coroutine, Literal

from loguru import logger

from homebot.cron.types import CronJob, CronJobState, CronPayload, CronRunRecord, CronSchedule, CronStore


def _now_ms() -> int:
    return int(time.time() * 1000)


def _compute_next_run(schedule: CronSchedule, now_ms: int) -> int | None:
    """Compute next run time in ms."""
    if schedule.kind == "at":
        return schedule.at_ms if schedule.at_ms and schedule.at_ms > now_ms else None

    if schedule.kind == "every":
        if not schedule.every_ms or schedule.every_ms <= 0:
            return None
        # Next interval from now
        return now_ms + schedule.every_ms

    if schedule.kind == "cron" and schedule.expr:
        try:
            from zoneinfo import ZoneInfo

            from croniter import croniter
            # Use caller-provided reference time for deterministic scheduling
            base_time = now_ms / 1000
            tz = ZoneInfo(schedule.tz) if schedule.tz else datetime.now().astimezone().tzinfo
            base_dt = datetime.fromtimestamp(base_time, tz=tz)
            cron = croniter(schedule.expr, base_dt)
            next_dt = cron.get_next(datetime)
            return int(next_dt.timestamp() * 1000)
        except Exception:
            return None

    return None


def _validate_schedule_for_add(schedule: CronSchedule) -> None:
    """Validate schedule fields that would otherwise create non-runnable jobs."""
    if schedule.tz and schedule.kind != "cron":
        raise ValueError("tz can only be used with cron schedules")

    if schedule.kind == "cron" and schedule.tz:
        try:
            from zoneinfo import ZoneInfo

            ZoneInfo(schedule.tz)
        except Exception:
            raise ValueError(f"unknown timezone '{schedule.tz}'") from None


class CronService:
    """Service for managing and executing scheduled jobs."""

    _MAX_RUN_HISTORY = 20

    def __init__(
        self,
        store_path: Path,
        on_job: Callable[[CronJob], Coroutine[Any, Any, str | None]] | None = None,
        max_sleep_ms: int = 300_000,  # 5 minutes
        bus = None,  # MessageBus | None — for direct delivery jobs
    ):
        self.store_path = store_path
        self.on_job = on_job
        self._bus = bus
        self._store: CronStore | None = None
        self._timer_task: asyncio.Task | None = None
        self._running = False
        self._timer_active = False
        self._system_handlers: dict[
            str, Callable[[CronJob], Coroutine[Any, Any, None]]
        ] = {}
        self.max_sleep_ms = max_sleep_ms

    def _load_jobs(self) -> tuple[list[CronJob], int]:
        if not self.store_path.exists():
            return [], 1

        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
            version = data.get("version", 1)
            jobs = []
            for j in data.get("jobs", []):
                job = self._parse_job_dict(j)
                # Overlay persisted state (action.jsonl jobs come with fresh state)
                st = j.get("state", {})
                job.state = CronJobState(
                    next_run_at_ms=st.get("nextRunAtMs"),
                    last_run_at_ms=st.get("lastRunAtMs"),
                    last_status=st.get("lastStatus"),
                    last_error=st.get("lastError"),
                    run_history=[
                        CronRunRecord(
                            run_at_ms=r["runAtMs"],
                            status=r["status"],
                            duration_ms=r.get("durationMs", 0),
                            error=r.get("error"),
                        )
                        for r in st.get("runHistory", [])
                    ],
                )
                jobs.append(job)
            return jobs, version
        except Exception as e:
            logger.warning("Failed to load cron store: {}", e)
            return [], 1

    def _load_store(self) -> CronStore:
        """Load jobs from disk. Reloads automatically if file was modified externally.
        - Reload every time because it needs to merge operations on the jobs object from other instances.
        - During _on_timer execution, return the existing store to prevent concurrent
          _load_store calls (e.g. from list_jobs polling) from replacing it mid-execution.
        """
        if self._timer_active and self._store:
            return self._store
        jobs, version = self._load_jobs()
        self._store = CronStore(version=version, jobs=jobs)
        return self._store

    def _save_store(self) -> None:
        """Save jobs to disk."""
        if not self._store:
            return

        self.store_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": self._store.version,
            "jobs": [
                {
                    "id": j.id,
                    "name": j.name,
                    "enabled": j.enabled,
                    "schedule": {
                        "kind": j.schedule.kind,
                        "atMs": j.schedule.at_ms,
                        "everyMs": j.schedule.every_ms,
                        "expr": j.schedule.expr,
                        "tz": j.schedule.tz,
                    },
                    "payload": {
                        "kind": j.payload.kind,
                        "message": j.payload.message,
                        "deliver": j.payload.deliver,
                        "deliverDirect": j.payload.deliver_direct,
                        "channel": j.payload.channel,
                        "to": j.payload.to,
                    },
                    "state": {
                        "nextRunAtMs": j.state.next_run_at_ms,
                        "lastRunAtMs": j.state.last_run_at_ms,
                        "lastStatus": j.state.last_status,
                        "lastError": j.state.last_error,
                        "runHistory": [
                            {
                                "runAtMs": r.run_at_ms,
                                "status": r.status,
                                "durationMs": r.duration_ms,
                                "error": r.error,
                            }
                            for r in j.state.run_history
                        ],
                    },
                    "createdAtMs": j.created_at_ms,
                    "updatedAtMs": j.updated_at_ms,
                    "deleteAfterRun": j.delete_after_run,
                }
                for j in self._store.jobs
            ]
        }

        self.store_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    async def start(self) -> None:
        """Start the cron service."""
        self._running = True
        self._load_store()
        self._recompute_next_runs()
        self._save_store()
        self._arm_timer()
        logger.info("Cron service started with {} jobs", len(self._store.jobs if self._store else []))

    def stop(self) -> None:
        """Stop the cron service."""
        self._running = False
        if self._timer_task:
            self._timer_task.cancel()
            self._timer_task = None

    def _recompute_next_runs(self) -> None:
        """Recompute next run times for all enabled jobs.

        Expired one-shot ``at`` jobs are fired immediately (catch-up) rather
        than silently dropped.
        """
        if not self._store:
            return
        now = _now_ms()
        for job in self._store.jobs:
            if job.enabled and job.state.next_run_at_ms is None:
                job.state.next_run_at_ms = _compute_next_run(job.schedule, now)
                if job.schedule.kind == "at" and job.state.next_run_at_ms is None:
                    job.state.next_run_at_ms = now

    def _parse_job_dict(self, j: dict) -> CronJob:
        """Parse a raw job dict (from action.jsonl or jobs.json) into a CronJob."""
        return CronJob(
            id=j["id"],
            name=j["name"],
            enabled=j.get("enabled", True),
            schedule=CronSchedule(
                kind=j["schedule"]["kind"],
                at_ms=j["schedule"].get("atMs"),
                every_ms=j["schedule"].get("everyMs"),
                expr=j["schedule"].get("expr"),
                tz=j["schedule"].get("tz"),
            ),
            payload=CronPayload(
                kind=j["payload"].get("kind", "agent_turn"),
                message=j["payload"].get("message", ""),
                deliver=j["payload"].get("deliver", False),
                deliver_direct=j["payload"].get("deliverDirect", False),
                channel=j["payload"].get("channel"),
                to=j["payload"].get("to"),
            ),
            state=CronJobState(),
            created_at_ms=j.get("createdAtMs", _now_ms()),
            updated_at_ms=j.get("updatedAtMs", _now_ms()),
            delete_after_run=j.get("deleteAfterRun", False),
        )

    def _apply_pending_actions(self) -> int:
        """Consume pending add/del actions from action.jsonl and apply to the store.

        External scripts (alarm set.py, cron manage.py, etc.) write one-line
        JSON actions to action.jsonl.  This method reads them, applies them to
        the in-memory store, persists to jobs.json, and clears action.jsonl.
        """
        action_path = self.store_path.parent / "action.jsonl"
        if not action_path.exists():
            return 0

        lock_path = self.store_path.parent / "action.lock"
        actions: list[dict] = []
        with open(lock_path, "w") as lf:
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
            try:
                content = action_path.read_text(encoding="utf-8").strip()
                if not content:
                    return 0
                for line in content.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        actions.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning("Cron: malformed action line in action.jsonl")
                action_path.write_text("", encoding="utf-8")
            finally:
                fcntl.flock(lf.fileno(), fcntl.LOCK_UN)

        if not actions:
            return 0

        applied = 0
        for action in actions:
            act = action.get("action")
            params = action.get("params", {})
            if act == "add":
                try:
                    job = self._parse_job_dict(params)
                    self._store.jobs = [j for j in self._store.jobs if j.id != job.id]
                    self._store.jobs.append(job)
                    applied += 1
                    logger.info("Cron: applied add action for job '{}' ({})", job.name, job.id)
                except Exception as e:
                    logger.warning("Cron: failed to apply add action: {}", e)
            elif act == "del":
                job_id = params.get("job_id", "")
                before = len(self._store.jobs)
                self._store.jobs = [j for j in self._store.jobs if j.id != job_id]
                if len(self._store.jobs) < before:
                    applied += 1
                    logger.info("Cron: applied del action for job {}", job_id)

        if applied > 0:
            self._recompute_next_runs()
            self._save_store()

        return applied

    def _get_next_wake_ms(self) -> int | None:
        """Get the earliest next run time across all jobs."""
        if not self._store:
            return None
        times = [j.state.next_run_at_ms for j in self._store.jobs
                 if j.enabled and j.state.next_run_at_ms]
        return min(times) if times else None

    def _arm_timer(self) -> None:
        """Schedule the next timer tick.

        Sleeps in 2 s chunks so that external processes can write new actions
        to action.jsonl and the timer will wake within ~2 s to pick them up.
        """
        if self._timer_task:
            self._timer_task.cancel()

        if not self._running:
            return

        next_wake = self._get_next_wake_ms()
        if next_wake is None:
            delay_s = self.max_sleep_ms / 1000
        else:
            delay_s = min(self.max_sleep_ms / 1000, max(0, (next_wake - _now_ms()) / 1000))

        async def tick():
            deadline = time.monotonic() + delay_s
            while self._running and time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                chunk = min(2.0, remaining)
                if chunk > 0:
                    await asyncio.sleep(chunk)
                action_path = self.store_path.parent / "action.jsonl"
                if action_path.exists() and action_path.stat().st_size > 0:
                    break
            if self._running:
                await self._on_timer()

        self._timer_task = asyncio.create_task(tick())

    async def _on_timer(self) -> None:
        """Handle timer tick - consume pending actions, run due jobs."""
        self._load_store()
        if not self._store:
            self._arm_timer()
            return

        self._apply_pending_actions()

        self._timer_active = True
        try:
            now = _now_ms()
            due_jobs = [
                j for j in self._store.jobs
                if j.enabled and j.state.next_run_at_ms and now >= j.state.next_run_at_ms
            ]

            for job in due_jobs:
                await self._execute_job(job)

            self._save_store()
        finally:
            self._timer_active = False
        self._arm_timer()

    async def _execute_job(self, job: CronJob) -> None:
        """Execute a single job."""
        start_ms = _now_ms()
        logger.info("Cron: executing job '{}' ({})", job.name, job.id)

        if job.payload.kind == "system_event":
            try:
                handler = self._system_handlers.get(job.payload.message)
                if handler is None:
                    raise RuntimeError(f"No handler registered for system event '{job.payload.message}'")
                await handler(job)
                job.state.last_status = "ok"
                job.state.last_error = None
                logger.info("Cron: system job '{}' completed", job.name)
            except Exception as e:
                job.state.last_status = "error"
                job.state.last_error = str(e)
                logger.error("Cron: system job '{}' failed: {}", job.name, e)
        elif job.payload.deliver_direct and job.payload.message and self._bus:
            # Direct delivery — no agent round-trip
            from homebot.bus.events import OutboundMessage
            try:
                await self._bus.publish_outbound(OutboundMessage(
                    channel=job.payload.channel or "direct",
                    chat_id=job.payload.to or "direct",
                    content=job.payload.message,
                    metadata={"_reminder_repeat": 2},
                ))
                job.state.last_status = "ok"
                job.state.last_error = None
            except Exception as e:
                job.state.last_status = "error"
                job.state.last_error = str(e)
                logger.error("Cron: job '{}' direct delivery failed: {}", job.name, e)
        else:
            try:
                if self.on_job:
                    await self.on_job(job)
                job.state.last_status = "ok"
                job.state.last_error = None
                logger.info("Cron: job '{}' completed", job.name)
            except Exception as e:
                job.state.last_status = "error"
                job.state.last_error = str(e)
                logger.error("Cron: job '{}' failed: {}", job.name, e)

        end_ms = _now_ms()
        job.state.last_run_at_ms = start_ms
        job.updated_at_ms = end_ms

        job.state.run_history.append(CronRunRecord(
            run_at_ms=start_ms,
            status=job.state.last_status,
            duration_ms=end_ms - start_ms,
            error=job.state.last_error,
        ))
        job.state.run_history = job.state.run_history[-self._MAX_RUN_HISTORY:]

        # Handle one-shot jobs
        if job.schedule.kind == "at":
            if job.delete_after_run:
                self._store.jobs = [j for j in self._store.jobs if j.id != job.id]
            else:
                job.enabled = False
                job.state.next_run_at_ms = None
        else:
            # Compute next run
            job.state.next_run_at_ms = _compute_next_run(job.schedule, _now_ms())

    # ========== Public API ==========

    def list_jobs(self, include_disabled: bool = False) -> list[CronJob]:
        """List all jobs."""
        store = self._load_store()
        jobs = store.jobs if include_disabled else [j for j in store.jobs if j.enabled]
        return sorted(jobs, key=lambda j: j.state.next_run_at_ms or float('inf'))

    def add_job(
        self,
        name: str,
        schedule: CronSchedule,
        message: str,
        deliver: bool = False,
        channel: str | None = None,
        to: str | None = None,
        delete_after_run: bool = False,
    ) -> CronJob:
        """Add a new job."""
        _validate_schedule_for_add(schedule)
        now = _now_ms()

        job = CronJob(
            id=str(uuid.uuid4())[:8],
            name=name,
            enabled=True,
            schedule=schedule,
            payload=CronPayload(
                kind="agent_turn",
                message=message,
                deliver=deliver,
                channel=channel,
                to=to,
            ),
            state=CronJobState(next_run_at_ms=_compute_next_run(schedule, now)),
            created_at_ms=now,
            updated_at_ms=now,
            delete_after_run=delete_after_run,
        )
        store = self._load_store()
        store.jobs.append(job)
        self._save_store()
        self._arm_timer()

        logger.info("Cron: added job '{}' ({})", name, job.id)
        return job

    def register_system_handler(
        self,
        event: str,
        handler: Callable[[CronJob], Coroutine[Any, Any, None]],
    ) -> None:
        """Register an in-process handler for a protected system event."""
        self._system_handlers[event] = handler

    def register_system_job(self, job: CronJob) -> CronJob:
        """Register an internal system job (idempotent on restart)."""
        store = self._load_store()
        existing = next((item for item in store.jobs if item.id == job.id), None)
        now = _now_ms()
        if existing is not None:
            job.state = existing.state
            job.created_at_ms = existing.created_at_ms
            if existing.schedule != job.schedule:
                job.state.next_run_at_ms = _compute_next_run(job.schedule, now)
        elif job.state.next_run_at_ms is None:
            job.state.next_run_at_ms = _compute_next_run(job.schedule, now)
            job.created_at_ms = now
        job.updated_at_ms = now
        store.jobs = [item for item in store.jobs if item.id != job.id]
        store.jobs.append(job)
        self._save_store()
        self._arm_timer()
        logger.info("Cron: registered system job '{}' ({})", job.name, job.id)
        return job

    def remove_job(self, job_id: str) -> Literal["removed", "protected", "not_found"]:
        """Remove a job by ID, unless it is a protected system job."""
        store = self._load_store()
        job = next((j for j in store.jobs if j.id == job_id), None)
        if job is None:
            return "not_found"
        if job.payload.kind == "system_event":
            logger.info("Cron: refused to remove protected system job {}", job_id)
            return "protected"

        before = len(store.jobs)
        store.jobs = [j for j in store.jobs if j.id != job_id]
        removed = len(store.jobs) < before

        if removed:
            self._save_store()
            self._arm_timer()
            logger.info("Cron: removed job {}", job_id)
            return "removed"

        return "not_found"

    def enable_job(self, job_id: str, enabled: bool = True) -> CronJob | None:
        """Enable or disable a job."""
        store = self._load_store()
        for job in store.jobs:
            if job.id == job_id:
                job.enabled = enabled
                job.updated_at_ms = _now_ms()
                if enabled:
                    job.state.next_run_at_ms = _compute_next_run(job.schedule, _now_ms())
                else:
                    job.state.next_run_at_ms = None
                self._save_store()
                self._arm_timer()
                return job
        return None

    def update_job(
        self,
        job_id: str,
        *,
        name: str | None = None,
        schedule: CronSchedule | None = None,
        message: str | None = None,
        deliver: bool | None = None,
        channel: str | None = ...,
        to: str | None = ...,
        delete_after_run: bool | None = None,
    ) -> CronJob | Literal["not_found", "protected"]:
        """Update mutable fields of an existing job. System jobs cannot be updated.

        For ``channel`` and ``to``, pass an explicit value (including ``None``)
        to update; omit (sentinel ``...``) to leave unchanged.
        """
        store = self._load_store()
        job = next((j for j in store.jobs if j.id == job_id), None)
        if job is None:
            return "not_found"
        if job.payload.kind == "system_event":
            return "protected"

        if schedule is not None:
            _validate_schedule_for_add(schedule)
            job.schedule = schedule
        if name is not None:
            job.name = name
        if message is not None:
            job.payload.message = message
        if deliver is not None:
            job.payload.deliver = deliver
        if channel is not ...:
            job.payload.channel = channel
        if to is not ...:
            job.payload.to = to
        if delete_after_run is not None:
            job.delete_after_run = delete_after_run

        job.updated_at_ms = _now_ms()
        if job.enabled:
            job.state.next_run_at_ms = _compute_next_run(job.schedule, _now_ms())

        self._save_store()
        self._arm_timer()

        logger.info("Cron: updated job '{}' ({})", job.name, job.id)
        return job

    async def run_job(self, job_id: str, force: bool = False) -> bool:
        """Manually run a job without disturbing the service's running state."""
        was_running = self._running
        self._running = True
        try:
            store = self._load_store()
            for job in store.jobs:
                if job.id == job_id:
                    if not force and not job.enabled:
                        return False
                    await self._execute_job(job)
                    self._save_store()
                    return True
            return False
        finally:
            self._running = was_running
            if was_running:
                self._arm_timer()

    def get_job(self, job_id: str) -> CronJob | None:
        """Get a job by ID."""
        store = self._load_store()
        return next((j for j in store.jobs if j.id == job_id), None)

    def status(self) -> dict:
        """Get service status."""
        store = self._load_store()
        return {
            "enabled": self._running,
            "jobs": len(store.jobs),
            "next_wake_at_ms": self._get_next_wake_ms(),
        }
