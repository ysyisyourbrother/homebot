# 小红书助手

小红书 Skill 通过 OpenCLI Browser Bridge 与小红书网页版交互，支持搜索笔记和向智能助手「点点」提问。

## 功能

- **搜索笔记**：搜索小红书笔记内容并归纳回答
- **问问点点**：向小红书 AI 助手「点点」提问，获取带来源的回答

## 前置依赖

- **OpenCLI Browser Bridge**：需要在 Homebot 专用 Chrome 中安装该扩展
- Chrome 中已登录 `xiaohongshu.com`

## 安装 OpenCLI Browser Bridge

### 1. 安装 OpenCLI

```bash
# 按 OpenCLI 官方文档安装
# 详见 https://github.com/opencli/opencli
```

### 2. 安装 Browser Bridge 扩展

在 Homebot 专用 Chrome 中安装 OpenCLI Browser Bridge 扩展。

### 3. 登录小红书

在 Homebot Chrome 窗口中打开 [xiaohongshu.com](https://www.xiaohongshu.com/) 并完成登录。

## 配置

### Session 保活 (推荐)

```json
{
  "tools": {
    "browser": {
      "sessionRefresh": {
        "urls": ["https://www.xiaohongshu.com/"]
      }
    }
  }
}
```

## 使用示例

### 搜索笔记

> "小红书搜一下北京周末去哪玩"
> "查一下小红书上的减脂食谱"
> "小红书上有什么好的 Mac 软件推荐"

Agent 会搜索相关笔记，读取正文内容，然后归纳回答。

### 向点点提问

> "问问点点最近有什么好看的电影"
> "让点点推荐一些护肤建议"

Agent 会将问题交给小红书的「点点」AI 助手并返回带来源的回答。

## 工作原理

1. homebot 通过 `exec` 调用 `scripts/xiaohongshu.py` 脚本
2. 脚本通过 OpenCLI 与 Browser Bridge 通信，控制已登录的 Chrome
3. 脚本自动完成搜索 → 逐篇读取 → 输出结构化 JSON
4. Agent 根据 JSON 内容归纳并回复用户

::: warning 注意
- 不要手动调用 Browser Tool，让脚本自己处理
- 脚本失败时不要重试（除非明确是 Browser Bridge 断连）
- 不要使用其他 profile
:::
