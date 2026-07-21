"""Delete a one-shot alarm by job ID."""

import json
import sys
from pathlib import Path


def _resolve_cron_dir() -> Path:
    return Path.home() / ".homebot" / "workspace" / "cron"


def main():
    if len(sys.argv) != 2:
        print("Usage: python delete.py <job_id>", file=sys.stderr)
        sys.exit(1)

    job_id = sys.argv[1]
    cron_dir = _resolve_cron_dir()
    action_path = cron_dir / "action.jsonl"

    cron_dir.mkdir(parents=True, exist_ok=True)
    lock_path = cron_dir / "action.lock"
    import fcntl
    with open(lock_path, "w") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            with open(action_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"action": "del", "params": {"job_id": job_id}}, ensure_ascii=False) + "\n")
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)

    print(f"已删除闹钟 {job_id}")


if __name__ == "__main__":
    main()
