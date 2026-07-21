"""Set an alarm (one-shot or recurring) by writing a job to the cron store.

All time calculations are done by this script — the caller just passes
the user's words.  The running CronService picks up the job and fires it.

Alarm jobs only deliver notifications (Feishu / voice), they never trigger
agent execution.  For agent tasks, use the cron skill.

Modes (mutually exclusive):
  --in "10分钟"       human-readable duration, script parses it
  --at-time 09:00     clock time today (or tomorrow if passed)
  --at-iso  ...       absolute ISO datetime (last resort)
  --every "20分钟"    recurring interval
  --cron-expr "0 9 * * 3,5"  cron expression (recurring)
"""

import argparse
import json
import re
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path


# ---------------------------------------------------------------------------
# duration parser — handles Chinese / English / compact forms
# ---------------------------------------------------------------------------

_DURATION_UNITS = {
    # Chinese
    "秒": 1, "秒钟": 1,
    "分": 60, "分钟": 60,
    "时": 3600, "小时": 3600, "钟头": 3600,
    "天": 86400, "日": 86400,
    # English
    "s": 1, "sec": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hour": 3600, "hours": 3600,
    "d": 86400, "day": 86400, "days": 86400,
}


def _parse_duration(text: str) -> int:
    """Parse a human-readable duration string → total seconds.

    Supports: "10秒", "5分钟", "2小时", "1天",
              "10s", "5m", "2h", "1d",
              "10 seconds", "5 minutes", etc.
    """
    text = text.strip()

    # Try compact form: "10s", "5m", "2h", "1d", "30min", "10seconds"
    m = re.match(r"^(\d+)\s*([a-zA-Z一-鿿]+)$", text)
    if m:
        num = int(m.group(1))
        unit = m.group(2).lower()
        multiplier = _DURATION_UNITS.get(unit)
        if multiplier:
            return num * multiplier
        # Try stripping trailing 's' for English plurals not in dict
        if unit.endswith("s"):
            multiplier = _DURATION_UNITS.get(unit[:-1])
            if multiplier:
                return num * multiplier

    # Try "X 分钟" / "X 秒" etc (with space)
    m = re.match(r"^(\d+)\s+(\S+)$", text)
    if m:
        num = int(m.group(1))
        unit = m.group(2).lower()
        multiplier = _DURATION_UNITS.get(unit)
        if multiplier:
            return num * multiplier

    # Plain number → seconds
    try:
        return int(text)
    except ValueError:
        pass

    raise ValueError(f"无法解析时间: {text!r}")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _resolve_cron_dir() -> Path:
    return Path.home() / ".homebot" / "workspace" / "cron"


def _write_action(store_dir: Path, action: str, params: dict) -> None:
    store_dir.mkdir(parents=True, exist_ok=True)
    action_path = store_dir / "action.jsonl"
    lock_path = store_dir / "action.lock"
    import fcntl
    with open(lock_path, "w") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            with open(action_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"action": action, "params": params}, ensure_ascii=False) + "\n")
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


def _format_target(at_dt: datetime, kind: str, raw: str) -> str:
    """Human-readable description for the confirmation message."""
    if kind == "in":
        return f"{raw}后"
    return at_dt.strftime("%m月%d日 %H:%M")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Set an alarm (one-shot or recurring)")
    parser.add_argument("--in", dest="in_", metavar="DURATION",
                        help="One-shot: human-readable duration, e.g. '10分钟', '5m'")
    parser.add_argument("--at-time", metavar="HH:MM",
                        help="One-shot: clock time like '09:00' (today, or tomorrow if passed)")
    parser.add_argument("--at-iso", metavar="ISO",
                        help="One-shot: ISO datetime like '2026-06-30T09:00:00'")
    parser.add_argument("--every", metavar="DURATION",
                        help="Recurring: interval, e.g. '20分钟', '1小时'")
    parser.add_argument("--cron-expr", metavar="EXPR",
                        help="Recurring: cron expression, e.g. '0 9 * * 3,5'")
    parser.add_argument("--tz", default="Asia/Shanghai",
                        help="Timezone for --cron-expr (default: Asia/Shanghai)")
    parser.add_argument("--offset-days", type=int, default=0,
                        help="Day offset for --at-time (0=auto today/tomorrow, 1=tomorrow, …)")
    parser.add_argument("--message", required=True, help="Reminder message")
    parser.add_argument("--chat-id", required=True, help="Target chat ID (open_id or chat_id)")
    parser.add_argument("--channel", default="feishu", help="Target channel")
    parser.add_argument("--store-dir", default=None, help="Override cron store directory")
    args = parser.parse_args()

    # Validate: exactly one scheduling mode
    modes = [args.in_, args.at_time, args.at_iso, args.every, args.cron_expr]
    active = [m for m in modes if m is not None]
    if len(active) != 1:
        parser.error("必须且只能指定 --in、--at-time、--at-iso、--every、--cron-expr 中的一个")
        sys.exit(1)

    store_dir = Path(args.store_dir) if args.store_dir else _resolve_cron_dir()
    now = datetime.now()
    now_ms = int(now.timestamp() * 1000)

    # --- resolve schedule ---
    is_recurring = False
    timing_desc = None

    if args.in_:
        seconds = _parse_duration(args.in_)
        at_ms = now_ms + seconds * 1000
        at_dt = now + timedelta(seconds=seconds)
        schedule = {"kind": "at", "atMs": at_ms}
        timing_desc = _format_target(at_dt, "in", args.in_)
    elif args.at_time:
        h, m = map(int, args.at_time.split(":"))
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if args.offset_days > 0:
            target += timedelta(days=args.offset_days)
        elif target <= now:
            target += timedelta(days=1)
        at_ms = int(target.timestamp() * 1000)
        schedule = {"kind": "at", "atMs": at_ms}
        timing_desc = _format_target(target, "at", args.at_time)
    elif args.at_iso:
        at_dt = datetime.fromisoformat(args.at_iso)
        at_ms = int(at_dt.timestamp() * 1000)
        schedule = {"kind": "at", "atMs": at_ms}
        timing_desc = _format_target(at_dt, "iso", args.at_iso)
    elif args.every:
        seconds = _parse_duration(args.every)
        schedule = {"kind": "every", "everyMs": seconds * 1000}
        is_recurring = True
        timing_desc = f"每{args.every}"
    elif args.cron_expr:
        schedule = {"kind": "cron", "expr": args.cron_expr, "tz": args.tz}
        is_recurring = True
        timing_desc = f"cron: {args.cron_expr} ({args.tz})"
    else:
        parser.error("必须指定一个调度模式")
        sys.exit(1)

    job_id = str(uuid.uuid4())[:8]
    job = {
        "id": job_id,
        "name": args.message[:30],
        "enabled": True,
        "schedule": schedule,
        "payload": {
            "kind": "alarm",
            "message": f"闹钟提醒：{args.message}",
            "deliver": True,
            "deliverDirect": True,
            "channel": args.channel,
            "to": args.chat_id,
        },
        "state": {},
        "createdAtMs": now_ms,
        "updatedAtMs": now_ms,
        "deleteAfterRun": not is_recurring,
    }

    _write_action(store_dir, "add", job)
    print(f"闹钟已设定：{timing_desc}提醒「{args.message}」")


if __name__ == "__main__":
    main()
