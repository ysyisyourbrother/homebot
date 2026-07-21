"""List alarms (one-shot and recurring) from the cron store.

Reads BOTH action.jsonl (pending add/del not yet consumed by CronService)
and jobs.json (consumed jobs), so the output is always accurate regardless
of whether CronService has processed the latest actions.
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path


def _resolve_cron_dir() -> Path:
    return Path.home() / ".homebot" / "workspace" / "cron"


def _format_alarm(j: dict, *, pending: bool) -> dict:
    """Convert a raw job dict into a display row."""
    cst = timezone(timedelta(hours=8))
    schedule = j.get("schedule", {})
    sk = schedule.get("kind", "")

    if sk == "cron":
        tz_str = schedule.get("tz", "")
        timing = f"cron: {schedule.get('expr', '?')}"
        if tz_str:
            timing += f" ({tz_str})"
    elif sk == "every":
        ms = schedule.get("everyMs", 0)
        if ms % 3_600_000 == 0:
            timing = f"每{ms // 3_600_000}小时"
        elif ms % 60_000 == 0:
            timing = f"每{ms // 60_000}分钟"
        else:
            timing = f"每{ms // 1000}秒"
    else:
        at_ms = schedule.get("atMs", 0)
        at_str = datetime.fromtimestamp(at_ms / 1000, tz=cst).strftime("%m月%d日 %H:%M")
        timing = at_str

    return {
        "id": j["id"],
        "name": j["name"],
        "timing": timing,
        "enabled": j.get("enabled", True),
        "kind": sk,
        "pending": pending,
    }


def main():
    cron_dir = _resolve_cron_dir()
    jobs_path = cron_dir / "jobs.json"
    action_path = cron_dir / "action.jsonl"

    # ── parse action.jsonl ──
    pending_deletes: set[str] = set()
    pending_adds: list[dict] = []
    if action_path.exists():
        try:
            for line in action_path.read_text(encoding="utf-8").strip().splitlines():
                if not line.strip():
                    continue
                action = json.loads(line)
                act = action.get("action")
                params = action.get("params", {})
                if act == "del":
                    pending_deletes.add(params.get("job_id", ""))
                elif act == "add":
                    pending_adds.append(params)
        except (json.JSONDecodeError, OSError):
            pass

    alarms: list[dict] = []
    seen: set[str] = set()

    # ── pending adds first (not yet consumed by CronService) ──
    for params in pending_adds:
        jid = params.get("id", "")
        if jid in pending_deletes or jid in seen:
            continue
        if params.get("payload", {}).get("kind") != "alarm":
            continue
        seen.add(jid)
        alarms.append(_format_alarm(params, pending=True))

    # ── jobs from jobs.json (authoritative state) ──
    if jobs_path.exists():
        try:
            data = json.loads(jobs_path.read_text(encoding="utf-8"))
            for j in data.get("jobs", []):
                if j.get("payload", {}).get("kind") != "alarm":
                    continue
                if j.get("schedule", {}).get("kind", "") not in ("at", "cron", "every"):
                    continue
                if j["id"] in pending_deletes or j["id"] in seen:
                    continue
                seen.add(j["id"])
                alarms.append(_format_alarm(j, pending=False))
        except (json.JSONDecodeError, OSError):
            pass

    if not alarms:
        print("暂无闹钟")
        return

    for a in alarms:
        pending = " [pending]" if a["pending"] else ""
        recurring = " [周期]" if a["kind"] in ("cron", "every") else ""
        status = "" if a["enabled"] else " [已禁用]"
        print(f"{a['id']}  {a['timing']}{recurring}{pending}  {a['name']}{status}")


if __name__ == "__main__":
    main()
