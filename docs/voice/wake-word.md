# 关键词唤醒

关键词唤醒使用 KWS（关键词唤醒）模型持续监听你设置的唤醒词。识别到唤醒词后，homebot 才会开始接收后续语音。

## 进入语音设置

执行以下命令：

```bash
python -m homebot config
```

在主菜单中选择 **[3] Voice Channel**。

```text
--- Voice Channel ---
  [1] Enable / Disable Voice Channel
  [2] Basic settings
  [3] Audio devices
  [4] User Recognition Settings
  [5] KWS Detection Settings
```

## 启用或关闭语音通道

选择 **[1] Enable / Disable Voice Channel** 可打开或关闭语音通道。首次启用时，homebot 会下载并准备 KWS 模型；关闭后会保留已有模型与配置，之后可以随时重新开启。

## 基础设置

选择 **[2] Basic settings** 可重新配置日常会使用的语音参数：

- **STT API Key**：语音识别服务的 API Token。
- **TTS API Key**：语音合成服务的 API Token。
- **TTS model**：语音合成模型，默认 `cosyvoice-v3-flash`。
- **TTS voice**：合成音色，默认 `longxiaochun_v3`。
- **Wake words**：以英文逗号分隔的唤醒词；修改后会重新生成唤醒词识别所需的配置。
- **Silence timeout**：唤醒后未开始说话时，自动退出对话的等待时间。

直接按回车会保留当前值。

## KWS 检测参数

选择 **[5] KWS Detection Settings** 可调整唤醒词识别参数：

```text
--- KWS Detection Settings ---
  KWS score [2.5]
  KWS token threshold [0.002]
  KWS max active paths [12]
```

| 参数 | 作用 |
|---|---|
| **KWS score** | 唤醒词匹配的总体得分门槛。提高它会让唤醒更严格，减少误唤醒；降低它会让唤醒更灵敏，但可能更容易被相近声音触发。 |
| **KWS token threshold** | 唤醒词发音片段的匹配门槛。提高它会要求每个发音片段更接近目标唤醒词；降低它会放宽识别条件。 |
| **KWS max active paths** | 识别过程中同时保留的候选发音路径数量。数值更大通常能保留更多候选，但会增加少量计算量；数值更小则更轻量。 |

当前默认参数已完成调优，日常使用效果良好，建议先保持默认值。不同麦克风的拾音距离、环境噪声和音质可能不同；若遇到频繁误唤醒或难以唤醒，可根据实际情况小幅调整后测试。
