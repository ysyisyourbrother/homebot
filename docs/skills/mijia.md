# 米家智能家居

homebot 通过 **Home Assistant** 控制米家设备。先让 Home Assistant 成功接入并控制你的米家设备，再将设备清单生成给 homebot，便可通过语音控制家中的设备。

## 1. 安装 Home Assistant

建议使用 Docker 部署 Home Assistant：

```bash
docker run -d \
  --name home-assistant \
  --restart=unless-stopped \
  -p 8123:8123 \
  -v ~/.homeassistant:/config \
  ghcr.io/home-assistant/home-assistant:stable
```

启动后，在浏览器打开 Home Assistant 的管理界面，完成首次初始化。

## 2. 在 Home Assistant 中接入米家

按照小米官方的 Home Assistant 集成文档完成米家配置：

<https://github.com/XiaoMi/ha_xiaomi_home/blob/main/doc/README_zh.md>

配置完成后，请先在 Home Assistant 中确认可以查看并操作米家设备。例如，能在 Home Assistant 中打开客厅灯或查看传感器状态，就说明基础连接已完成，离使用 homebot 控制设备只差最后一步。

## 3. 生成家庭设备 Skill

### 创建 Home Assistant 连接配置

在 Homebot 工作区中创建米家目录和私有配置文件。默认工作区路径为：

```text
~/.homebot/workspace
```

配置文件路径建议为：

```text
~/.homebot/workspace/skills/mijia/config.json
```

其中填写 Home Assistant 地址和在 Home Assistant 中创建的长期访问令牌：

```json
{
  "base_url": "http://<Home-Assistant 地址>:8123",
  "access_token": "<长期访问令牌>"
}
```

::: warning 注意
`config.json` 包含可控制家庭设备的访问令牌，请妥善保管，不要提交到 Git 仓库或分享给他人。
:::

### 根据设备清单生成 Skill

运行项目内置的米家驱动，读取 Home Assistant 中已接入的设备，并生成 homebot 使用的 Skill：

```bash
python3 homebot/skills/mijia/driver.py \
  --config ~/.homebot/workspace/skills/mijia/config.json \
  build-skill \
  --output ~/.homebot/workspace/skills/mijia/SKILL.md
```

生成后的文件位于：

```text
~/.homebot/workspace/skills/mijia/SKILL.md
```

它会包含当前可控制设备的名称、实体 ID 与支持的操作。新增或移除设备后，重新执行该命令即可更新设备清单。

## 4. 通过语音控制设备

重启 homebot 后，唤醒它并直接说出需求即可，例如：

> 打开客厅的灯

> 把卧室空调调到 24 度

> 关闭所有窗帘

生成的米家 Skill 会自动标记为 `always`，因此会持续保留在 homebot 的对话上下文中。这样处理家居控制请求时，无需先额外读取一次 `SKILL.md`，响应会更快。

::: tip 提示
只有生成 Skill 时已发现的设备会出现在 homebot 的设备清单中。接入新设备后，请重新生成 Skill，再重启 homebot。
:::
