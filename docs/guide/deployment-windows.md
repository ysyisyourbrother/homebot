# Windows 部署指南

本指南带你从零把 homebot 部署到一台 Windows 10/11 电脑上，并配置成开机自启的常驻服务。

每一步都给出**可复制的命令**和**验证方法**：前一步验证通过再进入下一步，出错时不会一路错到底。

::: tip 全程约 20 分钟
其中大约 10 分钟是在下载依赖。
:::

## 0. 部署前须知

| 事项 | 说明 |
|---|---|
| 运行方式 | homebot 是一个常驻后台进程，监听本机 `127.0.0.1:18790` |
| 数据位置 | 全部数据在 `%USERPROFILE%\.homebot`，卸载只需删除该目录 |
| 网络 | 需要联网：大模型 API + 阿里云百炼（语音识别/合成） |
| 不开放公网 | homebot 只监听本机，对外通信由飞书/Telegram 等通道主动发起，**不需要端口映射或公网 IP** |

## 1. 环境要求

| 项目 | 要求 | 检查方法 |
|---|---|---|
| 操作系统 | Windows 10 1809 或更高 / Windows 11 | `winver` |
| Python | **3.11 或更高**（推荐 3.12） | `python --version` |
| Git | 任意版本（也可以直接下载 zip 源码包） | `git --version` |
| Google Chrome | 可选，只在使用浏览器类技能时需要 | — |
| 麦克风与扬声器 | 使用语音通道时需要 | 系统「设置 → 系统 → 声音」 |

::: warning 关于音频
语音通道需要能访问音频设备。homebot 必须以**当前登录用户**的身份运行（见第 8 步），
不能安装成 Windows 服务——Session 0 里的服务访问不到麦克风。
:::

## 2. 安装 Python

任选一种方式。

**方式 A：winget（推荐，一条命令）**

```powershell
winget install -e --id Python.Python.3.12 --scope user
```

**方式 B：官网安装包**

从 [python.org](https://www.python.org/downloads/windows/) 下载 3.12 的 Windows 安装包，
安装时**务必勾选 `Add python.exe to PATH`**。

安装完成后，**新开一个 PowerShell 窗口**（环境变量需要新会话才生效）再验证：

```powershell
python --version      # 期望输出 Python 3.12.x
```

::: warning 版本检查很重要
如果输出是 3.8 或更低，说明 `PATH` 里还有旧版本 Python。可以用绝对路径代替，
或调整「环境变量 → 用户变量 → Path」把新版本提前。
:::

## 3. 获取代码

```powershell
cd $env:USERPROFILE
mkdir Codespace -Force
cd Codespace
git clone https://github.com/ysyisyourbrother/homebot.git
cd homebot
```

没有安装 Git 的话，在 GitHub 仓库页面点 `Code → Download ZIP`，解压到
`%USERPROFILE%\Codespace\homebot` 即可（效果相同，只是后续更新要用重新下载的方式）。

**验证**：当前目录下能看到 `pyproject.toml` 和 `homebot` 文件夹。

## 4. 创建虚拟环境并安装依赖

```powershell
cd $env:USERPROFILE\Codespace\homebot
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\pip.exe install -e .
```

国内网络可以把最后一条换成清华镜像，速度快很多：

```powershell
.\.venv\Scripts\pip.exe install -e . --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

::: tip 为什么用虚拟环境
homebot 的依赖装进 `.venv`，不会污染系统 Python。之后所有命令都用
`.\.venv\Scripts\python.exe`，不依赖 `PATH` 里是哪个 Python。
:::

**验证**：

```powershell
.\.venv\Scripts\python.exe -m homebot --help
```

应看到 `init` / `config` / `gateway` 三个子命令。

## 5. 初始化配置

```powershell
.\.venv\Scripts\python.exe -m homebot init
```

向导会依次询问：

1. **大模型**：模型名、API Base URL、API Key（推荐 DeepSeek V4）
2. **语音服务**：阿里云百炼（DashScope）的 API Key——语音识别与合成共用这一个 Key
3. **唤醒词**：例如「你好小助手」

向导还会自动下载唤醒词模型（约 30 MB）。如果下载失败，按提示手动下载解压到
`%USERPROFILE%\.homebot\workspace\voice\model\` 后重新运行 `init`。

配置保存在 `%USERPROFILE%\.homebot\config.json`。

::: warning 语音服务的 Key 是可选的
暂时不用语音、只想先通过飞书/Telegram 使用的话，语音部分可以跳过，
用 `python -m homebot config` 之后再补。
:::

## 6. 试运行

先在前台跑一次，确认能起来：

```powershell
.\.venv\Scripts\python.exe -m homebot gateway
```

**另开一个 PowerShell 窗口**验证：

```powershell
curl.exe http://127.0.0.1:18790/health
# 期望输出 {"status": "ok"}
```

启动日志里应能看到：

```
Gateway started on port 18790.
Channels enabled: voice, feishu
```

确认无误后，回到第一个窗口按 `Ctrl+C` 停掉，接着做第 7、8 步。

## 7. 配置语音设备（Windows 专属）

用配置菜单进入语音设置：

```powershell
.\.venv\Scripts\python.exe -m homebot config
# 选择 [3] Voice Channel → [3] Audio devices
```

::: warning 同一个设备会出现多次，这是正常的
Windows 会通过多个音频后端（host API）暴露同一块硬件，所以列表里会出现
`麦克风阵列 (USB Audio Device) [MME]`、`[Windows DirectSound]`、
`[Windows WASAPI]`、`[Windows WDM-KS]` 这样多条。

homebot 保存的是 `设备名, 后端名` 这种带后端的写法——只写设备名会有歧义，程序无法确定用哪个。
:::

**该选哪一个？** 关键区别是各后端支持的采样率不同（homebot 固定用 16 kHz 采集、24 kHz 合成语音）：

| 方向 | WASAPI | DirectSound / MME |
|---|---|---|
| 麦克风（16 kHz） | 通常可用（设备原生多为 16 kHz） | 可用（会重采样） |
| 扬声器（24 kHz） | **多数设备只接受 48 kHz，会失败** | 可用（会重采样） |

因此建议：

- **麦克风优先选 `[Windows WASAPI]`**：延迟最低
- **扬声器选 `[Windows DirectSound]`**：能重采样，兼容性最好

选择时 homebot 会**实际试开一次音频流**，不兼容会当场提示
（例如 `cannot open at 24000 Hz`），看到提示就换另一个后端再选一次。

::: tip 想用系统默认设备？
直接选 `[0] System default`，跟随 Windows 当前默认设备，不必关心后端。
:::

## 8. 设置开机自启

仓库自带一个安装脚本，它会完成：生成自看护启动脚本 → 注册登录自启任务 → 立即启动并检查健康状态。

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\install-autostart.ps1
```

脚本做的事：

1. 在 `%USERPROFILE%\.homebot\run-gateway.cmd` 生成启动脚本
2. 注册计划任务 `homebot-Gateway`，**用户登录时**自动启动，窗口隐藏
3. 网关进程若退出，10 秒后自动重新拉起

**验证**：

```powershell
Get-ScheduledTask -TaskName homebot-Gateway | Select-Object TaskName, State
curl.exe http://127.0.0.1:18790/health
```

常用管理命令：

```powershell
# 停止 / 启动 / 重启
Stop-ScheduledTask  -TaskName homebot-Gateway
Start-ScheduledTask -TaskName homebot-Gateway

# 等价的原生命令
schtasks /End /TN "homebot-Gateway"
schtasks /Run /TN "homebot-Gateway"

# 取消开机自启
powershell -ExecutionPolicy Bypass -File .\scripts\windows\install-autostart.ps1 -Uninstall
```

::: warning 重启电脑后需要登录
任务由「用户登录」触发，所以重启后要处于登录状态 homebot 才会运行。
这是音频设备访问权限决定的，无法绕过。
:::

## 9. 日常维护

| 事项 | 做法 |
|---|---|
| 查看日志 | `Get-Content $env:USERPROFILE\.homebot\logs\gateway.log -Wait -Encoding UTF8` |
| 改配置 | `.\.venv\Scripts\python.exe -m homebot config`，改完**重启**任务生效 |
| 更新版本 | 见下方 |
| 备份 | 复制整个 `%USERPROFILE%\.homebot` 目录即可（含配置、记忆、语音模型） |

**更新版本**（源码安装）：

```powershell
cd $env:USERPROFILE\Codespace\homebot
git pull
.\.venv\Scripts\pip.exe install -e .
Stop-ScheduledTask  -TaskName homebot-Gateway
Start-ScheduledTask -TaskName homebot-Gateway
```

## 10. 故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| 启动即报 `UnicodeEncodeError: 'gbk' codec can't encode` | 旧版本在中文 Windows 下输出日志的编码问题 | 升级到已修复的版本；临时可在启动前设置 `PYTHONUTF8=1` |
| `.venv\Scripts\python.exe -m homebot` 提示没有这个模块 | 依赖没装好 | 重新执行第 4 步的 `pip install -e .` |
| 命令 `python3` 找不到 | Windows 没有 `python3` | 一律用 `.\.venv\Scripts\python.exe` |
| 说唤醒词没有反应 | 麦克风未选中 / 灵敏度偏低 | 检查第 7 步；确认 Windows 里该麦克风未被静音；必要时降低 `kwsScore`（越小越灵敏） |
| 能识别但语音播报失败 `Invalid sample rate` | 扬声器选了 WASAPI 而设备只支持 48 kHz | 改选 `[Windows DirectSound]` 后端 |
| 日志里出现乱码 | 用记事本或错误的编码读取 | 用 `Get-Content ... -Encoding UTF8` |
| 飞书里发消息没反应 | 机器人未开启长连接 / 应用权限不足 | 见[飞书通道文档](/channels/feishu.html)；确认日志里有 `Feishu bot started with WebSocket long connection` |
| 端口 18790 被占用 | 已有实例在运行 | `Get-NetTCPConnection -LocalPort 18790 -State Listen` 找到进程后处理，避免同时跑两个实例 |

## 11. 附录：不用脚本手动注册计划任务

如果希望完全手动，命令等价于脚本里的操作：

```powershell
schtasks /Create /TN "homebot-Gateway" /SC ONLOGON /RL LIMITED `
  /TR "powershell -NoProfile -WindowStyle Hidden -Command \"& '%USERPROFILE%\.homebot\run-gateway.cmd'\"" /F
```

前提是先手工创建 `%USERPROFILE%\.homebot\run-gateway.cmd`（内容可参考脚本生成的版本）。
直接执行脚本更省事，也更不容易出错。
