---
name: xiaohongshu
description: 小红书助手：搜索小红书笔记、查询相关内容，或向小红书智能助手“点点”提问并获取带来源的回答。当用户提到“小红书搜一下”“查小红书”“找小红书攻略”“问问点点”“让点点回答”时使用。
metadata: {"homebot":{"requires":{"bins":["opencli"]}}}
---

# 小红书助手

通过 OpenCLI 使用 Homebot 专用 Google Chrome profile 中已登录的小红书，搜索笔记正文后归纳回答，或向小红书智能助手“点点”提问。

**脚本路径**：把当前文件的 `SKILL.md` 替换为 `scripts/xiaohongshu.py` 得到脚本绝对路径。

## 使用前提

- OpenCLI Browser Bridge 扩展已安装在 Homebot 专用 Google Chrome 中，该窗口已启动并登录 `xiaohongshu.com`。
- 脚本直接使用 OpenCLI default context（指向 Homebot 专用 Google Chrome），不指定额外 profile。
- `tools.browser.sessionRefresh.urls` 可加入 `https://www.xiaohongshu.com/`，定期访问同一 Google Chrome profile 以降低 Session 因闲置过期的概率。
- 不要在调用前后运行 `opencli doctor`、`opencli profile list` 或 `opencli profile use`。

## 调用流程

每次查询根据用户意图，直接且仅执行一次下方搜索或点点脚本。正常流程不要调用 Homebot `browser` 工具；Google Chrome、Browser Bridge 和登录状态以 OpenCLI 脚本的实际结果为准。脚本非零退出时按失败处理结束。

## 查询并归纳小红书内容

```bash
python3 <SCRIPT> search "<关键词>" --limit <数量>
```

- 默认只读取排名第一篇笔记；**除非用户明确说出数量，否则绝对不要传 `--limit`**，让脚本使用默认值。用户明确要求“综合多篇”时传 `--limit 3`；通常最多使用 5，10 篇仅限用户明确要求。
- 脚本先搜索，再逐篇读取笔记正文，输出 `query` 和 `notes` 的 JSON。每个 `notes` 元素包含 `search`（标题、作者、点赞、发布时间、URL 等搜索元数据）及 `content`（笔记正文和互动数据）。
- 为 `exec` 设置约 120 秒超时；用户指定超过 3 篇时，按每篇额外增加约 30 秒。
- 仅依据实际 JSON 中的笔记正文，用中文直接回答用户的问题：综合归纳共同结论、实用建议和存在分歧的信息。不要逐条罗列标题，也不要臆造正文未提及的内容。
- 需要举例或让用户继续查看时，附上实际存在的笔记标题或 URL；字段缺失直接省略。

## 向点点提问

```bash
python3 <SCRIPT> ask "<问题>" --timeout 90 --source-limit 10
```

- `--timeout` 是 OpenCLI 等待点点回答的秒数；`exec` 超时必须高于它，建议 120 秒。
- 优先把 `answer` 整理为直接的中文回答；若存在 `sources`，再附上实际存在的来源标题或 URL。
- `sources` 中的字段可能缺失，缺什么就省略什么，不显示空占位。

## 失败处理

脚本非零退出时，直接用一条简短回复说明错误并结束。仅当 Browser Bridge 明确断连时，脚本会在后台启动 Homebot Google Chrome 后重试一次，不额外打开首页；查询结束后会退出 Homebot 专用 Google Chrome。除此之外不得重试，不得读取脚本排查，不得运行任何 OpenCLI 诊断或 profile 命令，不得指定其他 profile，也不得改用 BrowserTool 或网页抓取兜底。
