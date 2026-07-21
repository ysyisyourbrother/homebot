# QQ Music 音乐助手

QQ Music Skill 让 homebot 能够搜索和播放 QQ 音乐歌曲。

## 功能

- **搜索歌曲**：按关键词搜索 QQ 音乐曲库
- **浏览器播放**：在 Chrome 中打开歌曲详情页并自动点击播放
- **智能查找**：支持按歌名、歌手、专辑搜索

## 前置依赖

- [Browser Tool](/tools/browser.html) — 已安装 Playwright 和 Chrome
- `curl` — 命令行 HTTP 工具

## 配置

### 1. 获取 API Key

QQ Music Skill 需要 `QQMUSIC_API_KEY` 来调用 QQ 音乐 API。

```bash
# 设置环境变量
export QQMUSIC_API_KEY="your-api-key"
```

### 2. 浏览器登录

首次使用需要手动在 Browser Tool 的 Chrome 窗口中登录 QQ 音乐账号：

1. 告诉 homebot：「帮我在 QQ 音乐搜一首歌」
2. homebot 会打开 Chrome 并导航到 QQ 音乐
3. 如果未登录，在弹出的 Chrome 窗口中手动完成 QQ 音乐登录
4. 登录状态会保存在 `~/.homebot/workspace/browser` 中

### 3. Session 保活 (可选)

为避免登录状态因闲置过期，可以配置定期刷新：

```json
{
  "tools": {
    "browser": {
      "sessionRefresh": {
        "urls": ["https://y.qq.com/"]
      }
    }
  }
}
```

## 使用示例

> "搜一下周杰伦的歌"
> "播放稻香"
> "QQ音乐放一首晴天"
> "搜陈奕迅的富士山下"

## 工作流程

Agent 执行 QQ 音乐播放的完整流程：

1. 调用 QQ 音乐搜索 API 获取歌曲列表
2. 展示搜索结果给用户确认
3. 通过 Browser Tool 打开歌曲详情页
4. 等待播放按钮变为可用状态
5. 点击播放按钮
6. 切换到播放器页面确认播放状态

## 接口 Base URL

```
https://a.y.qq.com
```

请求鉴权：`Authorization: Bearer $QQMUSIC_API_KEY`
