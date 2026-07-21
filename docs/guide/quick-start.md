# 快速开始

本指南将帮助你完成 homebot 的安装、初始化与启动。homebot 是一个基于对话的家庭智能助手 Agent：完成初始化后，即可通过已配置的渠道与它交流、执行任务和协同管理家庭设备。

## 环境要求

- **Python**：3.11 或更高版本
- **包管理器**：pip

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

::: tip 提示
建议先创建并激活独立的 Python 虚拟环境，再执行安装命令，避免影响系统中的其他 Python 项目。
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

配置文件会保存到 `~/.homebot/config.json`。

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

## 下一步

- 配置消息通道，连接飞书、Telegram 或语音
- 浏览 [Skills](/skills/index.html) 和 [Tools](/tools/index.html)，了解 homebot 可用的能力
