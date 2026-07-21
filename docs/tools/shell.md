# Shell 命令执行

Shell Tool 让 Agent 能够执行 Shell 命令，适用于运行脚本、安装程序、执行系统操作等。

## 功能

- 执行任意 Shell 命令
- 可限制工作目录
- 支持命令白名单/黑名单
- 自动捕获 stdout/stderr
- 超时保护（默认 60 秒，最大 600 秒）

## 配置

```json
{
  "tools": {
    "shell": {
      "timeout": 60,
      "working_dir": null,
      "restrict_to_workspace": false,
      "allowed_env_keys": ["PATH", "HOME", "USER"]
    }
  }
}
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `timeout` | int | `60` | 命令超时秒数（最大 600） |
| `working_dir` | string | - | 命令执行的工作目录 |
| `deny_patterns` | list | - | 禁止执行的命令正则表达式 |
| `allow_patterns` | list | - | 仅允许执行的命令正则表达式 |
| `restrict_to_workspace` | bool | `false` | 限制在 workspace 目录下执行 |

## 安全策略

建议配置 `deny_patterns` 阻止危险命令：

```json
{
  "tools": {
    "shell": {
      "deny_patterns": [
        "rm\\s+-rf\\s+/",
        "sudo\\s+",
        "chmod\\s+777"
      ]
    }
  }
}
```

## 使用示例

> "帮我跑一下 tests/test_browser.py"
> "用 pip 安装 requests 库"
> "检查系统 Python 版本"
