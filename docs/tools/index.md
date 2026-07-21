# 工具概览

homebot 内置了以下 Agent Tools，它们是 LLM 与外部世界交互的「手和眼」：

| Tool | 用途 | 需要额外配置 |
|------|------|-------------|
| **Browser** | Chrome 浏览器自动化（打开页面、点击、等待、检查） | Playwright + Chrome |
| **Web Search** | 互联网搜索 | Tavily API Key |
| **Shell** | 执行 Shell 命令 | 无 |
| **Filesystem** | 文件读写、目录操作 | 无 (沙箱限制) |
| **Web Fetch** | 抓取网页内容并转 Markdown | 无 |

## 安全模型

所有 Tools 都在受限环境中运行：

- **Filesystem**：默认仅允许在 workspace 目录下操作
- **Shell**：支持命令白名单/黑名单模式，可限制工作目录
- **Browser**：使用独立 Chrome Profile，与日常浏览器隔离
- **Web Search/Web Fetch**：外部内容标记为「不受信」，单独注入到上下文中

## 扩展 Tools

你可以在 `homebot/agent/tools/` 目录下添加自定义 Tool。继承 `Tool` 基类并使用 `@tool_parameters` 装饰器即可。详见源码中的现有实现。
