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

获取地址（需要先登录 QQ 音乐账号）：

```text
https://y.qq.com/n/ryqq_v2/qqmusic_skills
```

在该页面领取的 Key 形如 `qmk-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`，需要用户身份的接口会根据这个 Key 自动识别调用者。

```bash
# macOS / Linux：设置环境变量
export QQMUSIC_API_KEY="your-api-key"
```

```powershell
# Windows PowerShell
$env:QQMUSIC_API_KEY = "your-api-key"
# 需要永久生效时：
setx QQMUSIC_API_KEY "your-api-key"
```

### 1.1 把变量加进 exec 白名单（必需）

exec 工具**只把白名单内的环境变量传给子进程**（默认是空列表，见
`homebot/config/schema.py` 的 `ExecToolConfig.allowed_env_keys`）。只设置环境变量
而不加白名单的话，Agent 执行 skill 命令时读不到它，接口会返回 `unauthorized`。

```json
{
  "tools": {
    "exec": {
      "allowedEnvKeys": ["QQMUSIC_API_KEY"]
    }
  }
}
```

改完配置后需要重启网关。Windows 上用 `setx` 设置的用户级变量，也要重启网关（或重新登录）
才会被进程读到。

### 1.2 搜索要走自带脚本（Windows 尤其重要）

搜索请使用 skill 自带的脚本，不要手写 `curl` 一行命令：

```bash
python <SKILL.md 同目录>/scripts/search.py "周杰伦 晴天"
```

原因有两个，都在 Windows 上会直接导致命令失败：

1. **引号**：exec 工具在 Windows 下如果以参数形式传命令，Python 会把命令里的双引号转义成
   `\"`，而 cmd.exe 不认识这种转义，于是报 `'\"C:\...\"' is not recognized`。
2. **编码**：`curl -d '{"keyword":"周杰伦"}'` 这种写法会把中文按 GBK 编码发出去，
   服务端按 UTF-8 解析，于是返回 `请求参数类型不对`。

脚本用 Python 直接发请求，参数用 Unicode 接收、请求体显式按 UTF-8 编码，两个问题都不存在。

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
