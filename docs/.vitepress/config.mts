import { defineConfig } from "vitepress";

// https://vitepress.dev/reference/site-config
export default defineConfig({
  title: "homebot",
  description: "轻量级个人 AI 助手框架",

  base: "/homebot/",

  head: [["link", { rel: "icon", type: "image/png", href: "/homebot/logo_1.png" }]],

  themeConfig: {
    // https://vitepress.dev/reference/default-theme-config
    logo: "/logo_1.png",

    nav: [
      {
        text: "文档",
        items: [
          { text: "快速开始", link: "/guide/quick-start.html" },
          { text: "Agent Tools", link: "/tools/index.html" },
          { text: "内置 Skills", link: "/skills/index.html" },
          { text: "语音设置", link: "/voice/wake-word.html" },
          { text: "消息通道", link: "/channels/feishu.html" },
        ],
      },
    ],

    sidebar: {
      "/": [
        {
          text: "快速开始",
          collapsible: true,
          collapsed: true,
          items: [
            { text: "安装与启动", link: "/guide/quick-start.html" },
            { text: "语音唤醒与对话", link: "/guide/voice-interaction.html" },
          ],
        },
        {
          text: "Agent Tools",
          collapsible: true,
          collapsed: true,
          items: [
            { text: "工具概览", link: "/tools/index.html" },
            { text: "Browser 浏览器", link: "/tools/browser.html" },
          ],
        },
        {
          text: "内置 Skills",
          collapsible: true,
          collapsed: true,
          items: [
            { text: "Skills 总览", link: "/skills/index.html" },
            { text: "QQ Music 音乐", link: "/skills/qqmusic.html" },
            { text: "小红书搜索", link: "/skills/xiaohongshu.html" },
            { text: "米家智能家居", link: "/skills/mijia.html" },
            { text: "闹钟提醒", link: "/skills/alarm.html" },
            { text: "天气查询", link: "/skills/weather.html" },
          ],
        },
        {
          text: "语音设置",
          collapsible: true,
          collapsed: true,
          items: [
            { text: "关键词唤醒", link: "/voice/wake-word.html" },
            { text: "声纹检测", link: "/voice/speaker-verification.html" },
            { text: "麦克风选择", link: "/voice/audio-devices.html" },
          ],
        },
        {
          text: "消息通道",
          collapsible: true,
          collapsed: true,
          items: [
            { text: "飞书 Feishu", link: "/channels/feishu.html" },
            { text: "Telegram", link: "/channels/telegram.html" },
          ],
        },
      ],
    },

    socialLinks: [
      { icon: "github", link: "https://github.com/ysyisyourbrother/homebot" },
    ],

    search: {
      provider: "local",
    },

    // 中文 UI
    docFooter: {
      prev: "上一页",
      next: "下一页",
    },
    outline: {
      label: "目录",
    },
    lastUpdated: {
      text: "最后更新",
    },
    darkModeSwitchLabel: "主题",
    sidebarMenuLabel: "菜单",
    returnToTopLabel: "回到顶部",
  },

  ignoreDeadLinks: true,

  markdown: {
    theme: {
      light: "github-light",
      dark: "github-dark",
    },
  },
});
