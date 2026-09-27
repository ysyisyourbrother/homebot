---
name: qqmusic
description: QQ Music — search and play songs in a browser. QQ音乐助手：搜歌、放歌。
version: 0.0.6
metadata: {"homebot":{"requires":{"bins":["curl"]}}}
---

# QQ音乐助手

搜歌 + 浏览器播放。API 接口详情见 [discover.md](discover.md)。

## 工作流

### 搜索

用脚本搜索（**不要手写 curl 一行命令**：Windows 的 cmd.exe 会把转义引号原样传下去，中文也会被转成 GBK，命令必然失败并让你陷入反复重试）：

```bash
python <脚本路径> "周杰伦 晴天"
```

脚本路径 = 把当前文件的 `SKILL.md` 替换为 `scripts/search.py`。脚本自己从环境变量读
`QQMUSIC_API_KEY`，输出编号列表（歌名 - 歌手 songMid=...）。把列表转述给用户，
`songMid` 留给播放步骤使用。

### 播放

用户说“播放”、“放”或“来一首”时：

1. 调 `/discover/search` 搜歌，取第一条结果的 `songMid`、歌名与歌手。
2. 用 `browser` 工具 `open` `https://y.qq.com/n/ryqq_v2/songDetail/<songMid>`，传 `timeout_seconds=5`，记录返回的 `page_id`。
3. 用 `browser` 工具 `wait` 等待 `.data__actions a.mod_btn_green` 达到 `enabled`。这是歌曲信息区域唯一的播放按钮，不要猜测或尝试其它选择器。
4. 用 `browser` 工具 `click` 点击 `.data__actions a.mod_btn_green`。
5. 用 `browser` 工具 `open` `https://y.qq.com/n/ryqq_v2/player`，传 `timeout_seconds=5`，接管点击后弹出的播放器页面并记录它的 `page_id`。
6. 在播放器页面用 `browser` 工具 `wait` 等待 `.btn_big_play--pause` 达到 `visible`。该状态表示播放器已进入播放状态。
7. 仅在 `.btn_big_play--pause` 可见后回复“正在播放：歌名 - 歌手”。如果点击成功但未出现该状态，回复“歌曲页面已打开并尝试播放，但未确认播放”，并说明工具返回的登录、版权、网络或页面状态原因。不要将 `click` 的 `ok` 当作播放成功，也不要用详情页中的 `audio` 或 `video` 判断 QQ 音乐播放状态。

浏览器使用 Homebot 专用的持久 Google Chrome profile。第一次使用或登录失效时，请让用户在该窗口中完成 QQ 音乐登录；不得尝试绕过登录、版权、地区、会员或付费限制。可以通过全局 `tools.browser.sessionRefresh` 配置定期访问 QQ 音乐以降低闲置过期概率，但服务端仍可能撤销 Session。

## 接口规范

- Base URL: `https://a.y.qq.com`
- 鉴权: `Authorization: Bearer $QQMUSIC_API_KEY`（由脚本自动附带，**不要把 Key 写进命令行或回复里**）
- 所有请求必须带 `"comm": {"skill_version": "0.0.6"}`
- 业务参数用 `params` 包裹
- 请求体必须是 UTF-8 编码的 JSON：在 Windows 上用 curl 的 `-d` 传中文会被转成 GBK，
  服务端会返回"请求参数类型不对"。所以搜索统一走 `scripts/search.py`。

## 失败处理

- `scripts/search.py` 退出码非 0 时，把它 stderr 里的原文作为失败原因告诉用户，**最多再试一次**。
- 连续失败就直接如实回复失败，不要再换写法反复执行同一条命令——那会陷入死循环并大量消耗调用。
- 任何情况下都不要把 API Key 写进命令行（环境变量由 exec 白名单透传）。
