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

用户说“播放”、“放”或“来一首”时，严格按这个顺序走。每一步失败都按后面「判定与回复」的表**直接给用户
明确结论**，不要继续摸索。

1. **搜索**：调 `/discover/search`，取第一条结果的 `songMid`、歌名与歌手。
2. **打开歌曲页**：`browser` `open` `https://y.qq.com/n/ryqq_v2/songDetail/<songMid>`，
   `timeout_seconds=10`，记录 `page_id`。
3. **先确认登录**（关键，别跳过）：`browser` `inspect` 该页面的 `body`。
   如果文本里出现「登录」字样（页面右上角会显示“登录”），说明 Homebot 专用 Chrome 的登录态已失效 →
   **立刻结束**并按下面的表回复，不要再往下走。
4. **等播放按钮**：`browser` `wait` `.data__actions a.mod_btn_green` 到 `enabled`，`timeout_seconds=15`。
5. **点击播放**：`browser` `click` `.data__actions a.mod_btn_green`。
6. **打开播放器页**：`browser` `open` `https://y.qq.com/n/ryqq_v2/player`，`timeout_seconds=10`，记录 `page_id`。
7. **确认播放**：`browser` `wait` `.btn_big_play--pause` 到 `visible`，`timeout_seconds=15`。

### 判定与回复（必须照做，不能沉默）

| 情况 | 你要回复的内容 |
|---|---|
| 第 7 步成功（按钮变成“暂停”） | 「正在播放：<歌名> - <歌手>」 |
| 第 3 步发现「登录」 | 「需要先登录 QQ 音乐：在 Homebot 的 Chrome 窗口里登录一次就行，登录状态会保存在里面，之后就能正常播放了。」然后**结束** |
| 第 4 步超时，且页面是空壳（标题形如 `- - QQ音乐…`、正文出现“加载中”） | 「歌曲页没有加载出来，像是网络问题，稍后再试一次。」然后**结束** |
| 第 5 步点了，但第 7 步没进入播放态 | 「页面打开了但没能开始播放，可能是版权或会员限制。」然后**结束** |
| 其它任何失败 | 「播放遇到问题，暂时放不了。」然后**结束** |

### 硬性限制（防止卡住）

- 整个播放阶段最多走 **两轮**（第 2~7 步），第二轮仍失败就按上表分类回复并结束。
- **只允许**使用这三个选择器：`.data__actions a.mod_btn_green`、`.btn_big_play--pause`、`body`。
- **禁止**用 `inspect` 去试探别的选择器“找按钮”：登录失效或页面没加载时它们根本不存在，
  只会让用户干等好几分钟。

### 声音从哪里出来（排障用）

浏览器播放走的是 **Windows 默认播放设备**，不是 homebot 配置里的 `outputDevice`（两者可以不同）。
如果用户说“显示在播放但没声音”，提示他检查 Windows 的默认输出设备是不是那台音箱。

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
