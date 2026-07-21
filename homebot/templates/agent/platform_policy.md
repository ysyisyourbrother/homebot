{% if system == 'Windows' %}
## 平台策略（Windows）
- 你正在 Windows 上运行。不要假设 `grep`、`sed` 或 `awk` 等 GNU 工具存在。
- 优先使用 Windows 原生命令或文件工具（当它们更可靠时）。
- 如果终端输出乱码，重试时启用 UTF-8 输出。
{% else %}
## 平台策略（POSIX）
- 你正在 POSIX 系统上运行。优先使用 UTF-8 和标准 shell 工具。
- 当文件工具比 shell 命令更简单或更可靠时，使用文件工具。
{% endif %}
