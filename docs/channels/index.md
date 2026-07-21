# Channels 总览

Channels 是 homebot 的「消息通道」层，负责接收用户消息和发送回复。

## 内置 Channels

| Channel | 类型 | 适用场景 |
|---------|------|----------|
| **飞书** | 企业 IM (WebSocket) | 个人/团队日常使用，企业内部协作 |
| **Telegram** | 即时通讯 (Long Polling) | 个人使用，跨平台消息 |
| **Voice** | 语音 (麦克风) | 本地语音助手，唤醒词交互 |

## Channel 架构

所有 Channel 继承 `BaseChannel`，实现统一的接口：

```python
class BaseChannel:
    async def start(self) -> None: ...   # 启动通道
    async def stop(self) -> None: ...    # 停止通道
    async def send(self, msg: OutboundMessage) -> None: ...  # 发送消息
```

Channel 通过 `ChannelManager` 统一管理，在 Gateway 启动时自动加载。消息流：

```
User → Channel → InboundMessage → MessageBus → Agent → OutboundMessage → Channel → User
```

## 多 Channel 并行

homebot 支持同时运行多个 Channel。例如：

- 飞书 Bot 处理工作消息
- Telegram Bot 处理个人消息
- Voice 在本地待命

所有 Channel 共享同一个 Agent 实例和配置。

## 扩展 Channels

要添加自定义 Channel：
1. 在 `homebot/channels/` 下创建新 Python 文件
2. 继承 `BaseChannel` 并实现必需方法
3. Channel 会被自动发现和注册

也可以通过 Python entry_points 外部安装 Channel 插件（`homebot.channels` 组）。
