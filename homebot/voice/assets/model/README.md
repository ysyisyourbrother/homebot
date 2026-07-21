# 唤醒词模型

语音通道需要 sherpa-onnx 的 Keyword Spotting 模型来检测唤醒词。

## 下载模型

从 sherpa-onnx 的发布页面下载模型文件：

```
https://github.com/k2-fsa/sherpa-onnx/releases
```

搜索 `sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20` 开头的 tar.bz2 压缩包。

下载后解压到此目录：

```bash
# 下载模型（以 v1.12.30 版本为例，请替换为最新版本）
wget https://github.com/k2-fsa/sherpa-onnx/releases/download/v1.12.30/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20.tar.bz2

# 解压到当前目录
tar -xjf sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20.tar.bz2 -C .

# 清理压缩包
rm sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20.tar.bz2
```

## 目录结构

解压后，此目录应包含：

```
model/
├── README.md
├── .gitkeep
└── sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20/
    ├── encoder-epoch-13-avg-2-chunk-8-left-64.onnx
    ├── decoder-epoch-13-avg-2-chunk-8-left-64.onnx
    ├── joiner-epoch-13-avg-2-chunk-8-left-64.onnx
    └── tokens.txt
```

## 配置

在 `config.json` 中设置模型路径（如果解压到此目录，可省略，通道会自动检测）：

```json
{
  "channels": {
    "voice": {
      "enabled": true,
      "modelDir": "path/to/model/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20"
    }
  }
}
```

如果不配置 `modelDir`，通道默认使用此目录下的模型。
