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
