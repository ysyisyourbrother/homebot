# 快速开始

本指南帮助你完成 homebot 的安装、初始化与启动。homebot 是一个基于对话的家庭智能助手 Agent：完成初始化后，即可通过已配置的渠道与它交流、执行任务和协同管理家庭设备。

::: tip 想要一份逐步可验证的部署清单？
- **Windows**：[Windows 部署指南](/guide/deployment-windows.html)（含虚拟环境、音频设备、开机自启）
- **macOS / Linux**：本页的命令已适用于这两个平台；开机自启可用 `systemd` 或 `launchd` 托管 `python -m homebot gateway`
:::

## 环境要求

| 项目 | 要求 |
|---|---|
| 操作系统 | Windows 10/11、macOS、Linux 均可 |
| Python | **3.11 或更高** |
| 包管理器 | pip |
| 可选依赖 | Google Chrome（浏览器类技能）、麦克风与扬声器（语音通道） |

## 1. 安装项目

你可以通过 PyPI 安装，也可以从源码安装。若希望查看、修改或参与开发，推荐使用源码安装。

### 通过 PyPI 安装

```bash
pip install homebot-ai
```

### 从源码安装

```bash
git clone https://github.com/ysyisyourbrother/homebot
cd homebot
pip install -e .
```

`pip install -e .` 会根据项目根目录中的 `pyproject.toml` 安装 homebot 及其依赖，并以可编辑模式关联当前源码；之后修改源码无需重复安装。

::: tip 建议使用虚拟环境
先创建并激活独立的 Python 虚拟环境再安装，避免影响系统中其他 Python 项目：

```bash
python -m venv .venv
# Windows
.venv\Scripts\python -m pip install -e .
# macOS / Linux
.venv/bin/python -m pip install -e .
```
:::

## 2. 初始化配置

安装完成后，运行初始化向导：

```bash
python -m homebot init
```

初始化向导会依次引导你填写默认大模型的连接信息、API Key 和语音服务的 DashScope API Key，并创建 homebot 的工作区与默认配置。

::: warning 语音服务
目前语音功能强制使用阿里云百炼（DashScope）平台的模型。启用语音前，请先注册百炼平台并创建 API Key，再在初始化向导中填写。未来会支持更多语音服务平台。
:::

::: tip 大模型 Provider
Homebot 的 LLM Provider 兼容 OpenAI 格式的接口。当前仅完成了 DeepSeek V4 模型的实际验证，因此强烈推荐使用 DeepSeek V4。
:::

如果通过 PyPI 安装，系统会同时提供 `homebot` 命令，也可以执行：

```bash
homebot init
```

本指南后续均以源码安装为例，因此继续使用 `python -m homebot`。如果你通过 PyPI 安装，只需将命令开头替换为 `homebot` 即可。

配置文件会保存到 `~/.homebot/config.json`（Windows 上为 `%USERPROFILE%\.homebot\config.json`）。

## 3. 启动 homebot

完成初始化后，启动网关：

```bash
python -m homebot gateway
```

网关默认监听 `127.0.0.1:18790`。启动后，你可以通过已配置的 Channel 与 homebot 交互。

验证网关是否正常运行：

```bash
curl http://127.0.0.1:18790/health
# 返回: {"status": "ok"}
```

## 4. 修改配置

任何时候都可以运行交互式配置菜单，修改模型、语音、工具与通道设置：

```bash
python -m homebot config
```

改动写入配置文件后，需要**重启网关**才会生效。各配置项的详细说明见：

- [语音设置](/voice/wake-word.html)：唤醒词、声纹、麦克风选择
- [消息通道](/channels/feishu.html)：飞书、Telegram
- [Agent Tools](/tools/index.html)：联网、搜索、命令执行、浏览器
- [内置 Skills](/skills/index.html)：音乐、小红书、米家、闹钟、天气

## 下一步

- **Windows 用户**：按 [Windows 部署指南](/guide/deployment-windows.html) 配置音频设备与开机自启
- 配置消息通道，连接飞书、Telegram 或语音
- 浏览 [Skills](/skills/index.html) 和 [Tools](/tools/index.html)，了解 homebot 可用的能力
