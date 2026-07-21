---
name: alarm
description: 闹钟和定时提醒（一次性 + 周期性）。当用户说"设闹钟"、"提醒我"、"X分钟后叫我"、"几点叫我"、"倒计时"、"明早X点提醒我"、"每天X点"、"每周X提醒"、"每隔X分钟"、"查看闹钟"、"我的闹钟"、"删除闹钟"、"取消闹钟"时使用。
---

**脚本路径**：把当前文件的 `SKILL.md` 替换为 `scripts/<脚本名>` 得到脚本绝对路径。

---

## 设定闹钟 -> `set.py`

```bash
python3 <SCRIPT> --message "<内容>" --channel <channel> --chat-id <Chat ID> <调度参数>
```

### 调度参数（五选一）

| 用户说 | 参数 |
|--------|------|
| "10分钟后叫我" | `--in "10分钟"` |
| "下午3点提醒我开会" | `--at-time 15:00` |
| "明天早上9点叫我" | `--at-time 09:00 --offset-days 1` |
| 明确 ISO 时间 | `--at-iso "2026-07-08T09:00"` |
| "每20分钟提醒我喝水" | `--every "20分钟"` |
| "每天早上9点提醒我" | `--cron-expr "0 9 * * *"` |
| "每周三周五早上9点" | `--cron-expr "0 9 * * 3,5"` |
| "工作日早上9点" | `--cron-expr "0 9 * * 1-5"` |

- `--message`：提醒内容，去掉"提醒我""叫我"等口语词。
- `--channel`、`--chat-id`：从 Runtime Context 直接复制。
- `--tz`：配合 `--cron-expr`，默认 `Asia/Shanghai`。
- 时区始终用北京时间，不做换算。

执行完后跑一次 `list.py` 确认闹钟已在列表，再回复用户"已设定"。

## 查看闹钟 -> `list.py`

```bash
python3 <SCRIPT>
```

直接输出脚本结果，不用读文件。输出中 `[周期]` 表示重复闹钟，`[pending]` 表示等待 CronService 消费。

## 删除闹钟 -> `delete.py`

```bash
python3 <SCRIPT> <job_id>
```

- `job_id`：8 位短 ID，从 list 结果获取。
- 用户说"删除所有闹钟"时，先 list 再逐个 delete。

执行完后跑一次 `list.py` 确认已移除，再回复用户。
