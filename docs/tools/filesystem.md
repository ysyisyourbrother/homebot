# Filesystem 文件系统

Filesystem Tool 提供受限的文件系统访问能力，包括文件读写、目录列表和文件编辑操作。

## 功能

| 操作 | 说明 |
|------|------|
| **Read** | 读取文件内容（文本 + 图像） |
| **Write** | 创建或覆盖文件 |
| **Edit** | 精确字符串替换编辑 |
| **List** | 列出目录内容 |

## 安全模型

所有文件操作被限制在 **允许的目录** 范围内：

- `workspace` 目录（默认为项目根目录）
- `media` 目录（`~/.homebot/media/`）
- 可通过 `extra_allowed_dirs` 扩展

越权访问会抛出 `PermissionError`。

## 配置

```json
{
  "tools": {
    "filesystem": {
      "workspace": "/path/to/workspace",
      "extra_allowed_dirs": ["/path/to/extra"]
    }
  }
}
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `workspace` | string | 工作目录（相对路径的基准） |
| `allowed_dir` | string | 文件操作的根目录 |
| `extra_allowed_dirs` | list | 额外允许的目录列表 |

## 支持的图片格式

Read 操作支持读取并返回以下格式的图片：

- PNG / JPG / JPEG / GIF
- WebP / SVG

## 使用示例

> "读一下 homebot/config/schema.py 这个文件"
> "在 workspace 目录下创建一个 README.md"
> "列出 tests/ 目录下的所有文件"
