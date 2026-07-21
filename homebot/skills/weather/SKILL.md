---
name: weather
description: 获取当前天气和预报（无需 API key）。
homepage: https://wttr.in/:help
metadata: {"homebot":{"emoji":"🌤️","requires":{"bins":["curl"]}}}
---

# 天气

wttr.in — 选择一个命令，然后用 2-3 句简洁的话回复（不用 markdown/emoji）：

`curl -s "wttr.in/<城市>?format=%l:+%c+%t+%h+%w&m"` — 当前天气
`curl -s "wttr.in/<城市>?T&m&2" | head -40` — 预报

URL 中的空格需要编码（New+York → New+York）。
中文城市名直接使用中文即可。
如果用户没有指定城市，默认查询广州。
