# Voice Channel

Voice Channel 将 homebot 变成一个本地语音助手——支持唤醒词检测、实时语音识别和流式语音合成。

## 功能

- **唤醒词检测** (KWS)：说唤醒词激活对话
- **实时语音识别** (STT)：边说边转文字
- **流式语音合成** (TTS)：AI 回复实时合成语音播放
- **多轮对话**：支持连续对话，直到静默超时

## 架构

```
麦克风 → KWS (唤醒词) → STT (语音识别) → Agent → TTS (语音合成) → 扬声器
```

## 前置依赖

- **麦克风**：可用的音频输入设备
- **扬声器**：音频输出设备
- **模型文件** (~30MB)：KWS 唤醒词检测模型

### Python 依赖

安装 Homebot 时会自动安装语音依赖：

```bash
pip install -e .
```

其中 `sherpa-onnx` 和 `sounddevice` 不锁定版本，pip 会根据当前 Python 与操作系统环境解析可用版本。

### 模型下载

唤醒词检测模型需要下载到 `homebot/voice/assets/model/`：

```bash
# 下载 sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20 模型
# 放到 homebot/voice/assets/model/ 目录
```

## 配置

```json
{
  "channels": {
    "voice": {
      "enabled": true,
      "wake_word": "你好小助手",
      "stt_provider": "dashscope",
      "tts_provider": "cosyvoice",
      "voice_dir": "~/.homebot/voice",
      "silence_timeout_ms": 3000,
      "max_turns": 10,
      "language": "zh"
    }
  }
}
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | `false` | 是否启用语音通道 |
| `wake_word` | string | `"你好小助手"` | 唤醒词 |
| `stt_provider` | string | - | 语音识别后端 |
| `tts_provider` | string | - | 语音合成后端 |
| `voice_dir` | string | `"~/.homebot/voice"` | 语音资产目录 |
| `silence_timeout_ms` | int | `3000` | 静默超时 (ms) |
| `max_turns` | int | `10` | 单次对话最大轮数 |
| `language` | string | `"zh"` | 语音语言 |

## 语音服务配置

### STT (语音识别)

目前使用 **DashScope paraformer-realtime-v2**：

```json
{
  "providers": {
    "dashscope": {
      "api_key": "sk-xxx"
    }
  },
  "channels": {
    "voice": {
      "stt_provider": "dashscope"
    }
  }
}
```

### TTS (语音合成)

使用 **DashScope CosyVoice** 流式合成：

```json
{
  "channels": {
    "voice": {
      "tts_provider": "cosyvoice"
    }
  }
}
```

## 使用

启动 Gateway 后，Voice Channel 会在后台运行：

```bash
python -m homebot gateway
```

1. 说 **"你好小助手"** 唤醒
2. 听到提示音后说出你的问题
3. 等待 AI 语音回复
4. 可以继续对话（多轮），静默超时后自动结束

## 自定义唤醒词

修改配置中的 `wake_word` 即可。注意唤醒词需要在模型的词汇表中。

## 音频资产

Voice Channel 自带以下音频文件（位于 `homebot/voice/assets/audio/`）：

- `reminder_bg.wav` — 唤醒提示音
- `beep.wav` — 开始说话提示音

可以替换为你自己的音频文件。

## 性能

- 唤醒词检测：本地运行，低延迟
- STT：依赖网络（DashScope API）
- TTS：流式合成，首字延迟低
