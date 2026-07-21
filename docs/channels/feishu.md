# 飞书 Channel

飞书 (Feishu/Lark) Channel 通过飞书开放平台的 WebSocket 长连接接收和发送消息。

## 功能

- WebSocket 长连接实时收发消息
- 支持文本、图片、文件等多种消息类型
- 支持群聊 @提及 触发
- 支持按钮交互
- 多实例（多 Bot）并行运行

## 前置条件

1. 在 [飞书开放平台](https://open.feishu.cn/) 创建企业自建应用
2. 获取 `App ID` 和 `App Secret`
3. 开启应用的 **机器人** 能力
4. 配置事件订阅（无需配置 Request URL，WebSocket 模式不需要）

## 配置

```json
{
  "channels": {
    "feishu": {
      "appId": "cli_xxx",
      "appSecret": "your-app-secret",
      "groupPolicy": "whitelist",
      "groupWhitelist": ["oc_xxx"],
      "domain": "feishu"
    }
  }
}
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `appId` | string | (必需) | 飞书应用的 App ID |
| `appSecret` | string | (必需) | 飞书应用的 App Secret |
| `groupPolicy` | string | `"all"` | 群聊策略：`all` / `whitelist` / `mention` |
| `groupWhitelist` | list | `[]` | `whitelist` 模式下的群聊白名单 (chat_id) |
| `domain` | string | `"feishu"` | 飞书域：`feishu` / `lark` |

## 群聊策略

| 策略 | 行为 |
|------|------|
| `all` | 所有群聊消息都触发响应 |
| `whitelist` | 仅白名单群聊触发响应 |
| `mention` | 仅 @Bot 时触发响应 |

## 权限要求

应用需要以下权限：

- `im:message` — 获取消息
- `im:message:send_as_bot` — 发送消息
- `im:chat` — 获取群聊信息

## 使用步骤

### 1. 创建飞书应用

1. 进入 [飞书开放平台控制台](https://open.feishu.cn/app)
2. 创建「企业自建应用」
3. 在「应用功能」→「机器人」中启用

### 2. 配置权限

在「权限管理」中添加并申请上述权限。

### 3. 发布应用

首次使用需要创建版本并发布（可以仅对你自己可见）。

### 4. 填写配置

将 `appId` 和 `appSecret` 填入配置文件。

### 5. 启动

```bash
python -m homebot gateway
```

启动后飞书 Bot 会自动上线，在飞书中找到你的 Bot 即可对话。

## 调试

```bash
# 查看 Gateway 日志
# 飞书 WebSocket 连接状态会在日志中显示
```
