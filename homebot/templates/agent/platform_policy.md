{% if system == 'Windows' %}
## 平台策略（Windows）
- 你正在 Windows 上运行。不要假设 `grep`、`sed` 或 `awk` 等 GNU 工具存在。
- 没有 `python3` 命令；运行 Python 技能脚本时使用「运行环境」里给出的解释器路径（homebot 的依赖只装在那里）。路径含空格时记得加引号。
- shell 是 `cmd.exe`：用 `dir` 而不是 `ls`，`type` 而不是 `cat`，用 `;` 而不是 `&&` 连接命令（或分开执行）。
- 优先使用 Windows 原生命令或文件工具（当它们更可靠时）。
- 如果终端输出乱码，重试时启用 UTF-8 输出。
{% else %}
## 平台策略（POSIX）
- 你正在 POSIX 系统上运行。优先使用 UTF-8 和标准 shell 工具。
- 运行 Python 技能脚本时使用「运行环境」里给出的解释器路径——用 `python3` 会找不到 homebot 装好的依赖。
- 当文件工具比 shell 命令更简单或更可靠时，使用文件工具。
{% endif %}
