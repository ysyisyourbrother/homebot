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

用户要搜歌时，参考 discover.md 调 `/discover/search`，结果用编号列表展示（歌名 + 歌手）。

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
- 鉴权: `Authorization: Bearer $QQMUSIC_API_KEY`
- 所有请求必须带 `"comm": {"skill_version": "0.0.6"}`
- 业务参数用 `params` 包裹

```bash
curl -X POST "${BaseUrl}/discover/search" \
  -H "Authorization: Bearer $QQMUSIC_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"params": {"keyword": "周杰伦", "type": "0"}, "comm": {"skill_version": "0.0.6"}}'
```
