# 工具概览

homebot 内置了以下 Agent Tools，它们是 LLM 与外部世界交互的「手和眼」：

| Tool | 用途 | 需要额外配置 |
|------|------|-------------|
| **Browser** | Chrome 浏览器自动化（打开页面、点击、等待、检查） | Playwright + Chrome |
| **Web Search** | 互联网搜索 | Tavily API Key |
| **Shell** | 执行 Shell 命令 | 无 |
| **Filesystem** | 文件读写、目录操作 | 无 (沙箱限制) |
| **Web Fetch** | 抓取网页内容并转 Markdown | 无 |

## 配置工具

执行以下命令进入配置向导：

```bash
python -m homebot config
```

在主菜单选择 **[4] Tools Settings** 后，会进入工具菜单。选择具体工具即可单独修改它的配置，完成后选择 **[0] Back** 返回；不需要每次重新填写其他工具的配置。

- **Web Fetch**：启用或停用网页抓取。
- **Web Search**：启用或停用，并配置 Tavily API Key。详见 [Web Search 网页搜索](./web-search)。
- **Shell Exec**：启用或停用 Shell 命令执行。
- **Browser**：配置启用状态、Chrome 路径、独立资料目录、Profile 和 Session 刷新。详见 [Browser 浏览器](./browser)。

配置工具后返回主菜单，选择其他菜单项或退出时会保存到默认配置文件 `~/.homebot/config.json`。


所有 Tools 都在受限环境中运行：

- **Filesystem**：默认仅允许在 workspace 目录下操作
- **Shell**：支持命令白名单/黑名单模式，可限制工作目录
- **Browser**：使用独立 Chrome Profile，与日常浏览器隔离
- **Web Search/Web Fetch**：外部内容标记为「不受信」，单独注入到上下文中

## 扩展 Tools

你可以在 `homebot/agent/tools/` 目录下添加自定义 Tool。继承 `Tool` 基类并使用 `@tool_parameters` 装饰器即可。详见源码中的现有实现。
