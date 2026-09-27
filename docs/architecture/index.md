# 架构说明

这一部分写给**人类读者**（部署者、二次开发者、排障的人），不是写给 Agent 的提示词。

Agent 读的是 `homebot/skills/README.md`、`homebot/templates/agent/*.md` 和各个
`SKILL.md`；运维脚本在 `ops/`。而这里解释的是"这套代码为什么这么组织"。

## 目录

- [跨平台支持：macOS 与 Windows 如何区分](./platform-support) —— 平台能力层、
  共用与分离的边界、部署差异、新增平台相关功能的检查清单。
