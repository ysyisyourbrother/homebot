# Browser 浏览器

Browser Tool 让 homebot 在专用的 Google Chrome 中访问网页、完成页面操作，并保留该专用浏览器的登录状态。它不会使用你的日常 Chrome 资料、Cookie 或登录账号。

## 专用浏览器环境

Browser Tool 仅支持安装了 Google Chrome 的 macOS。通过 `./install_env.sh` 安装 Playwright 等依赖后，首次调用 Browser Tool 会启动 Homebot 的专用 Chrome 窗口。

默认使用 `/Applications/Google Chrome.app`、`~/.homebot/workspace/browser` 数据目录，以及其中的 `Homebot` Profile。这个窗口与日常 Chrome 完全隔离：Homebot 不会读取、启动或关闭日常 Chrome，Cookie、登录状态、扩展和浏览器设置也不会相互影响。

在需要登录 QQ 音乐、小红书等网站时，请始终在该专用窗口中完成登录；后续启动会复用保存的 Session。

## 配置浏览器

执行以下命令进入配置向导：

```bash
python -m homebot config
```

配置向导会显示配置文件位置。选择 **[4] Tools Settings**，然后依次完成 Browser 的配置。

### 使用独立浏览器资料目录

当向导询问 Browser 设置时，按以下方式填写：

1. 将 `Browser` 设为 `yes`。
2. 确认 `Browser Executable Path` 指向本机 Chrome 的可执行文件；默认值适用于常见的 macOS 安装位置。
3. 在 `User Data Directory` 中使用 Homebot 工作区下的独立目录，例如：

   ```text
   ~/.homebot/workspace/browser
   ```

4. 在 Profile 选择中输入或保留 `Homebot`，创建 Homebot 专用的 Chrome Profile。

建议保留这个独立目录和 Profile。首次需要登录 QQ 音乐、小红书等网站时，Homebot 会打开专用浏览器窗口；请在该窗口中完成登录。之后，登录状态会保存在 Homebot 的资料目录中，与日常浏览器互不影响。

::: warning 注意
不要将日常 Chrome 的 User Data Directory 填入这里。日常 Chrome 运行时可能占用该目录，且混用资料会让个人浏览数据、登录状态与自动化任务相互干扰。
:::

## 定时刷新登录状态

部分网站的 Cookie 或 Session 会因长时间未访问而过期。Browser Tool 可以定期访问指定网站，降低登录状态因闲置失效的概率。

仍在 **[4] Tools Settings** 的 Browser 配置中，设置以下两项：

- `Session Refresh URLs`：以英文逗号分隔需要刷新的网址。例如：

  ```text
  https://www.xiaohongshu.com, https://www.qqmusic.com/
  ```

  输入 `none` 可清除已设置的网址。

- `Session Refresh Interval Hours`：刷新间隔，单位为小时。例如保留 `72`，表示每 72 小时刷新一次。

网关运行期间，homebot 会使用同一个专用 Profile 在后台临时打开这些网址；页面访问完成后会自动关闭，不会影响日常 Chrome 的窗口、资料或使用体验。

::: tip 提示
定时访问只能降低 Session 因闲置过期的概率。若网站主动让登录状态失效，仍需在 Homebot 专用浏览器窗口中重新登录。
:::

## 小红书与 OpenCLI Browser Bridge

小红书 Skill 不通过 Browser Tool 操作网页，而是由 OpenCLI Browser Bridge 连接 Homebot 专用 Chrome 中已经登录的小红书页面。首次使用前，请完成以下初始化：

1. 安装 OpenCLI，确认终端可执行 `opencli --version`。
2. 先通过 Browser Tool 打开任意网页，启动 Homebot 专用 Chrome。
3. 在该窗口中从 [Chrome Web Store](https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk) 安装 OpenCLI Browser Bridge 扩展。
4. 在同一窗口登录小红书，并保持该窗口运行。
5. 查看 Browser Bridge 已连接的 context：

   ```bash
   opencli profile list
   ```

6. 找到 Homebot 专用 Chrome 对应的 context，并设置稳定别名：

   ```bash
   opencli profile rename <contextId> homebot
   ```

7. 验证 OpenCLI 可复用该窗口的小红书登录状态：

   ```bash
   opencli xiaohongshu whoami -f json
   ```

小红书包装脚本使用 OpenCLI 的默认 context。因此应将 Homebot 专用 Chrome 对应的 Browser Bridge context 设为 default，不要改用日常 Chrome 或其他 Profile。更多小红书使用说明见[小红书助手](/skills/xiaohongshu.html)。

## 使用方式

配置完成后，直接在对话中告诉 homebot 你的需求即可。例如：

> 帮我在 QQ 音乐搜索周杰伦的晴天

homebot 会使用配置好的专用浏览器完成操作。

## 常见问题

### Chrome 无法启动

确认已安装 Google Chrome，并在配置向导中检查 `Browser Executable Path` 是否正确。

### 登录状态丢失

确认 `User Data Directory` 保持为 Homebot 的专用目录，并检查是否为相关网站设置了 Session Refresh URLs。需要重新登录时，请在 Homebot 打开的专用浏览器窗口中完成登录。
