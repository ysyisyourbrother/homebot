# Skills 总览

Skills 是 homebot 的领域能力模块，用于为 Agent 提供特定任务的操作说明与工具支持。

## 系统内置 Skills

| Skill | 用途 |
|-------|------|
| **QQ Music 音乐** | 搜索和播放 QQ 音乐 |
| **小红书搜索** | 搜索小红书笔记并向「点点」提问 |
| **米家智能家居** | 控制小米智能家居设备 |
| **闹钟提醒** | 设置一次性或周期性提醒 |
| **天气查询** | 查询当前天气和预报 |

## 扩展 Skills

homebot 启动时会同时扫描项目内的 `homebot/skills/` 目录，以及工作区下的 `skills/` 目录。

如需添加自己的 Skill，请在工作区的 `skills/` 目录中创建。例如，默认工作区为 `~/.homebot/workspace` 时，可将自定义 Skill 放在：

```text
~/.homebot/workspace/skills/
```

重启 homebot 后，系统会自动发现该目录下的自定义 Skills。
