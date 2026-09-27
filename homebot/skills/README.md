# homebot Skills

This directory contains built-in skills that extend homebot's capabilities.

## Skill Format

Each skill is a directory containing a `SKILL.md` file with:
- YAML frontmatter (name, description, metadata)
- Markdown instructions for the agent

When skills reference large local documentation or logs, prefer homebot's built-in
`grep` / `glob` tools to narrow the search space before loading full files.
Use `grep(output_mode="count")` / `files_with_matches` for broad searches first,
use `head_limit` / `offset` to page through large result sets,
and `glob(entry_type="dirs")` when discovering directory structure matters.

### Cross-platform commands in SKILL.md

SKILL.md is read verbatim by the agent on Windows, macOS and Linux, so any shell
command in it has to be platform-neutral:

- Write `python <SCRIPT>`, never `python3`. Windows has no `python3`, and on
  macOS/Linux a bare `python3` may not be the interpreter that has homebot's
  dependencies. The system prompt tells the agent the exact interpreter path
  (see `templates/agent/identity.md` and `platform_policy.md`).
- Avoid Unix-only utilities (`grep`, `sed`, `awk`, `chmod`). Prefer homebot's
  own tools, or say what you want rather than how to do it.
- Prefer forward slashes in relative paths; they work on all three platforms.
- Anything that truly differs per platform belongs in a script, not in the
  prose: SKILL.md says "run `scripts/xxx.py`" and the script handles quoting,
  encoding and path conventions itself. `skills/qqmusic/scripts/search.py` is
  the reference example.
- If a whole skill only makes sense on one platform, gate it with frontmatter
  instead of writing "on Windows … / on macOS …" into the body:

  ```yaml
  metadata: {"homebot":{"platforms":["win32"]}}   # or darwin / linux / posix / *
  ```

  A skill that does not match the current platform is not shown to the agent at
  all, so it costs nothing in the prompt.

The full rationale (capability layer, deployment contract, checklist for new
platform-dependent features) is in `docs/architecture/platform-support.md`.

## Attribution

These skills are adapted from [OpenClaw](https://github.com/openclaw/openclaw)'s skill system.
The skill format and metadata structure follow OpenClaw's conventions to maintain compatibility.

## Available Skills

| Skill | Description |
|-------|-------------|
| `weather` | Get weather info using wttr.in and Open-Meteo |
| `skill-creator` | Create new skills |
| `qqmusic` | QQ Music — search, recommendations, charts, AI playlists, listening reports |
| `xiaohongshu` | Search Xiaohongshu notes and ask 点点 through OpenCLI Browser Bridge |
