"""Cron types."""

import re
from dataclasses import dataclass, field
from typing import Literal


def _camel_to_snake(name: str) -> str:
    """createdAtMs → created_at_ms"""
    return re.sub(r"(?<=[a-z])([A-Z])", r"_\1", name).lower()


def _normalize_keys(d: dict) -> dict:
    """Convert camelCase keys to snake_case so external JSON matches dataclass fields."""
    return {_camel_to_snake(k) if k != "id" and not k.startswith("_") else k: v for k, v in d.items()}


@dataclass
class CronSchedule:
    """Schedule definition for a cron job."""
    kind: Literal["at", "every", "cron"]
    # For "at": timestamp in ms
    at_ms: int | None = None
    # For "every": interval in ms
    every_ms: int | None = None
    # For "cron": cron expression (e.g. "0 9 * * *")
    expr: str | None = None
    # Timezone for cron expressions
    tz: str | None = None


@dataclass
class CronPayload:
    """What to do when the job runs."""
    kind: Literal["system_event", "agent_turn"] = "agent_turn"
    message: str = ""
    deliver: bool = False
    # When True, CronService delivers payload.message directly — no agent round-trip
    deliver_direct: bool = False
    channel: str | None = None  # e.g. "telegram", "feishu"
    to: str | None = None  # e.g. phone number


@dataclass
class CronRunRecord:
    """A single execution record for a cron job."""
    run_at_ms: int
    status: Literal["ok", "error", "skipped"]
    duration_ms: int = 0
    error: str | None = None


@dataclass
class CronJobState:
    """Runtime state of a job."""
    next_run_at_ms: int | None = None
    last_run_at_ms: int | None = None
    last_status: Literal["ok", "error", "skipped"] | None = None
    last_error: str | None = None
    run_history: list[CronRunRecord] = field(default_factory=list)


@dataclass
class CronJob:
    """A scheduled job."""
    id: str
    name: str
    enabled: bool = True
    schedule: CronSchedule = field(default_factory=lambda: CronSchedule(kind="every"))
    payload: CronPayload = field(default_factory=CronPayload)
    state: CronJobState = field(default_factory=CronJobState)
    created_at_ms: int = 0
    updated_at_ms: int = 0
    delete_after_run: bool = False

    @classmethod
    def from_dict(cls, kwargs: dict):
        kwargs = _normalize_keys(kwargs)
        state_kwargs = _normalize_keys(kwargs.get("state", {}))
        state_kwargs["run_history"] = [
            record if isinstance(record, CronRunRecord) else CronRunRecord(**_normalize_keys(record))
            for record in state_kwargs.get("run_history", [])
        ]
        schedule_kwargs = _normalize_keys(kwargs.get("schedule", {"kind": "every"}))
        kwargs["schedule"] = CronSchedule(**schedule_kwargs)
        kwargs["payload"] = CronPayload(**_normalize_keys(kwargs.get("payload", {})))
        kwargs["state"] = CronJobState(**state_kwargs)
        return cls(**kwargs)


@dataclass
class CronStore:
    """Persistent store for cron jobs."""
    version: int = 1
    jobs: list[CronJob] = field(default_factory=list)
