#!/usr/bin/env python3
"""Search the QQ Music skill API.

Usage:
    python search.py "周杰伦 晴天" [type]

The documented ``curl`` one-liner is not safe on Windows: cmd.exe keeps the
bash-style backslash escapes literally and converts non-ASCII arguments with
the ANSI code page, so the JSON body reaches the server as mojibake and every
attempt fails.  Python receives the command line as Unicode and encodes the
body itself, so this works on every platform.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

API_URL = "https://a.y.qq.com/discover/search"
SKILL_VERSION = "0.0.6"


def _force_utf8_output() -> None:
    """Song names are Chinese; make sure they survive a pipe on Windows."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def main() -> int:
    _force_utf8_output()

    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print('usage: python search.py "<keyword>" [type]', file=sys.stderr)
        return 2

    keyword = sys.argv[1].strip()
    search_type = sys.argv[2] if len(sys.argv) > 2 else "0"

    api_key = os.environ.get("QQMUSIC_API_KEY", "").strip()
    if not api_key:
        print(
            "QQMUSIC_API_KEY is not set. Get a key from "
            "https://y.qq.com/n/ryqq_v2/qqmusic_skills and add it to the exec "
            "tool's allowedEnvKeys.",
            file=sys.stderr,
        )
        return 3

    body = json.dumps(
        {
            "params": {"keyword": keyword, "type": search_type},
            "comm": {"skill_version": SKILL_VERSION},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # network, TLS, timeout, bad JSON
        print(f"search failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    songs = payload.get("songs")
    if songs is None:
        print(
            f"search rejected: ret={payload.get('ret')} msg={payload.get('msg')}",
            file=sys.stderr,
        )
        return 1
    if not songs:
        print("no results")
        return 0

    for index, song in enumerate(songs, 1):
        print(
            f"{index}. {song.get('songName')} - {song.get('singerName')}"
            f"  songMid={song.get('songMid')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
