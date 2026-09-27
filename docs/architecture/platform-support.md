# 跨平台支持：macOS 与 Windows 如何区分

homebot 同时在 macOS 和 Windows 上原生部署。这份文档说明"两种平台各自不同的部分
放在哪里、为什么这样分"，以及新增平台相关功能时应该往哪写。

## 设计原则

只有两条，其余规则都是它们的推论：

1. **能共用的充分共用** —— 业务逻辑、通道、工具、技能流程全部平台无关，只有一份
   实现，不复制粘贴。
2. **不能共用的彻底分离** —— 每个平台差异都有各自的**独立文件**，通过一个统一接口
   对外暴露。改 Windows 的实现，物理上碰不到 macOS 的代码。

还有一条推论：**业务代码里不出现 `sys.platform` 判断**。平台差异只允许存在于
`homebot/system/` 这一个包内，以及提示词模板和部署脚本这两处"边界"。

## 分层总览

```text
业务代码（通道 / 工具 / 技能 / agent 循环）——平台无关，只有一份
        │   只 import homebot.system
        ▼
homebot/system/                     ← 唯一允许出现平台差异的代码位置
        ├── capabilities.py         平台判定、解释器路径、Chrome 默认位置
        ├── devices.py              设备路径防护（两套规则互不干扰）
        ├── process.py    ──►  process_posix.py   /  process_nt.py
        └── shell.py      ──►  shell_posix.py     /  shell_nt.py
        │
        ├── templates/agent/platform_policy.md   提示词层的平台策略（Jinja 分支）
        └── scripts/{macos,windows}/             部署层（契约相同，实现不同）
```

## 平台能力层：一个接口，两套实现

| 能力 | 统一接口（业务代码只认这个） | macOS / POSIX 实现 | Windows 实现 |
|---|---|---|---|
| 执行 shell 命令 | `spawn()` | `bash -l -c <命令>` | `cmd.exe`，命令串**原样**下发 |
| 子进程环境 | `build_subprocess_env()` | 最小环境（HOME/LANG/TERM）+ 白名单 | 系统变量清单 + 白名单 + `PYTHONIOENCODING=utf-8` |
| 追加 PATH | `apply_path_append()` | 命令里内联 `export PATH` | 直接改环境里的 PATH |
| 查找进程 | `find_pids()` | `pgrep -f`（模式按字面转义） | CIM 查询 `Win32_Process.CommandLine` |
| 终止进程 | `terminate_pids()` / `terminate_matching()` | SIGTERM → 超时 → SIGKILL | `taskkill /PID <pid> /T /F` |
| 重启网关 | `restart_in_place()` | `os.execv` 原地替换进程 | 退出进程，交给启动器重新拉起 |
| 设备路径防护 | `is_blocked_device()` | `/dev/*`、`/proc/*/fd/*` | `\\.\...`、`CON`/`NUL`/`COM1`… |
| 解释器路径 | `python_executable()` | `sys.executable` | 同左（Windows 上没有 `python3`） |
| Chrome 默认位置 | `default_chrome_path()` | `/Applications/Google Chrome.app/...` | `C:\Program Files\Google\Chrome\...` |

为什么统一接口这么重要：业务代码只依赖函数签名。只要签名不变，替换某一侧的实现
(或再加一个 Linux 实现）都不需要动业务代码。

### 两个实现必须留在各自文件里的理由

- **命令执行**：POSIX 需要 `bash -l` 去加载用户 profile 才能拿到 PATH；Windows 的
  `cmd.exe` 没有登录 profile 机制，必须显式传一组系统变量。两者的环境构造逻辑天然
  不同，混在一个函数里会让"给 Windows 加一个变量"变成"重新审视 POSIX 的行为"。
- **进程控制**：POSIX 有 `pgrep`/信号；Windows 走 CIM + `taskkill`。而且
  `os.kill(pid, 0)` 在 Windows 上不是"探测"而是**终止**进程，这种语义陷阱必须锁在
  Windows 实现内部。
- **设备防护**：`/dev/zero` 在 Windows 上只是普通相对路径，`NUL` 在 POSIX 上只是
  文件名。两套规则分开写，才不会出现"为 A 平台加的规则误伤 B 平台"。

## 提示词层：平台策略只写一处

Agent 的系统提示里确实需要平台相关的行为约定（用什么 shell、有没有 `python3`），
但这类内容集中在一个 Jinja 模板里：

`homebot/templates/agent/platform_policy.md`

```jinja
{% if system == 'Windows' %}
## 平台策略（Windows）
- shell 是 cmd.exe：用 dir 而不是 ls……
{% else %}
## 平台策略（POSIX）
- 优先使用 UTF-8 和标准 shell 工具……
{% endif %}
```

渲染时只输出匹配的分支，另一个平台的文字**不会进入上下文**，因此不存在"两个平台的
说明都塞在一个文件里导致提示词膨胀"的问题。

### 技能（Skills）层的三条规矩

技能的 `SKILL.md` 是被 Agent 原样读进上下文的，所以：

1. **命令差异下沉到脚本**：`SKILL.md` 只写"运行 `scripts/xxx.py`"，平台差异在脚本
   内部处理。这样正文里不会出现任何平台分支。（`skills/qqmusic/scripts/search.py`
   就是范例：中文参数与 UTF-8 请求体都在 Python 里解决，绕开 shell 的引号/编码坑。）
2. **整个技能只适用于一个平台**：在 frontmatter 里写 `platforms: [win32]` 或
   `platforms: [darwin, linux]`（也接受 `macos`、`posix`、`*`）。另一个平台上这个
   技能**不会出现在提示词里**，连名字都不出现。
3. **确实是文字差异时**：才考虑在 `SKILL.md` 内写平台条件块，并且尽量短。

### 已知的合理例外

技能脚本（`homebot/skills/*/scripts/*.py`）为了能独立运行，不依赖 `homebot.system`，
允许在自身内部按 `sys.platform` 处理命令行引号等差异。例如米家的
`driver.py::_json_arg()`：bash 用单引号包 JSON，Windows 则用双引号 + `\"` 转义
（cmd.exe 自身不转义，但 Python 的 C 运行时会还原）。这类分支局限在单个脚本内，
不会影响框架其它部分。

## 部署层：契约相同，实现不同

两个平台的自启脚本刻意不共享代码，但遵守同一套契约：

| 契约项 | 约定 |
|---|---|
| 启动方式 | 执行 `~/.homebot/run-gateway.{cmd,sh}` |
| 启动脚本职责 | 设置环境、写日志、进程退出后 10 秒重新拉起 |
| 日志位置 | `~/.homebot/logs/gateway.log`，超过 10 MB 轮转为 `gateway.log.1` |
| 健康检查 | `http://127.0.0.1:18790/health` |
| 卸载 | 各自脚本的 `-Uninstall` / `--uninstall` |

| | Windows | macOS |
|---|---|---|
| 自启机制 | 计划任务 `homebot-Gateway`（登录时启动、隐藏窗口） | LaunchAgent `com.homebot.gateway`（RunAtLoad + KeepAlive） |
| 脚本 | `scripts/windows/install-autostart.ps1` | `scripts/macos/install-autostart.sh` |
| 不使用 | Windows 服务（Session 0 拿不到音频设备） | 系统级 LaunchDaemon（同样因为音频要留在用户会话里） |

契约写在这份文档里，实现各自演化——这样"两边行为一致"，但改一边不会波及其它一边。

## 新增平台相关功能时的检查清单

1. **能共用吗？** 先把逻辑写成平台无关的接口；只有确实无法共用的部分才往下走。
2. **差异属于命令 / 路径 / API 吗？** 在 `homebot/system/` 里加接口，并在
   `*_posix.py` 与 `*_nt.py` 各实现一份。**函数名和签名必须一致**——这是"互不影响"
   的保证，也让以后新增第三个平台变成一件平凡的事。
3. **差异属于提示词文字吗？** 全局规则写进 `templates/agent/platform_policy.md` 的
   对应分支；技能内尽量下沉到脚本。
4. **整个技能只对某个平台有意义吗？** 用 frontmatter 的 `platforms:` 过滤。
5. **部署相关吗？** 只改那个平台的 `scripts/<platform>/`，契约变更时同步更新本文档
   的表格。
6. **两边都验证**：平台代码的正确性只能靠"在两端各跑一次"来保证；接口层可以写
   单元测试，平台实现要么在真机验证，要么写成可注入的纯函数。

## 一个真实案例（为什么值得这么做）

2026-09-27 那天连续踩了两个坑：

1. **exec 引号**：Windows 分支用 `create_subprocess_exec(cmd, "/c", command)`，
   CPython 会把命令里的引号转义成 `\"`，而 cmd.exe 不认这种转义——所有带引号的命令
   全部失败，Agent 反复重试直到死循环。修复就是把这个分支搬进 `shell_nt.py` 并改成
   原样下发命令。
2. **浏览器首次导航**：`y.qq.com` 播放器页第一次导航必报
   `net::ERR_HTTP2_PROTOCOL_ERROR`，重试即成功。这是 Chromium 的瞬时错误，和平台无关，
   所以修复放在共享的浏览器工具里（自动重试 + 上下文自愈），两个平台同时受益。

一个平台特有的坑（引号）和跨平台的坑（重试）被分别放在"平台实现文件"和"共享工具"
里——这就是这套结构的价值。
