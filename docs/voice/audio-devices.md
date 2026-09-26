# 麦克风选择

homebot 的语音通道可以单独选择输入与输出设备，不会修改系统默认的麦克风或扬声器。

执行 `python -m homebot config`，选择 **[3] Voice Channel**，再进入 **[3] Audio devices**。

配置向导会列出当前可用的设备：

- **Input device**：选择 Homebot 用于监听唤醒词和接收语音的麦克风。
- **Output device**：选择 Homebot 播放回应声和语音回复的扬声器。

选择 `System default` 可继续使用系统默认设备。使用 USB 麦克风、蓝牙耳机或外接音箱时，建议在这里显式选定对应设备，避免系统默认设备变化后影响语音交互。

## Windows：同一个设备会出现多次

Windows 会通过多个音频后端（host API）暴露同一块硬件，因此列表里会出现
`麦克风阵列 (USB Audio Device) [MME]`、`[Windows DirectSound]`、`[Windows WASAPI]`、
`[Windows WDM-KS]` 这样多条同名记录。

homebot 保存的是 `设备名, 后端名` 这种带后端的写法——只写设备名会有歧义，程序无法确定用哪一个。

**该选哪个后端？** 各后端支持的采样率不同，而 homebot 固定用 16 kHz 采集、24 kHz 合成语音：

| 方向 | WASAPI | DirectSound / MME |
|---|---|---|
| 麦克风（16 kHz） | 通常可用（设备原生多为 16 kHz） | 可用（会重采样） |
| 扬声器（24 kHz） | **多数设备只接受 48 kHz，会失败** | 可用（会重采样） |

建议**麦克风选 `[Windows WASAPI]`**（延迟最低），**扬声器选 `[Windows DirectSound]`**（兼容最好）。

选择时 homebot 会实际试开一次音频流，不兼容会当场提示（例如 `cannot open at 24000 Hz`），
换另一个后端重选即可。若不想操心，直接选 `System default` 跟随系统默认设备。

::: tip macOS / Linux
这两个平台通常每个设备只有一条记录，直接按名称选择即可，无需关心后端。
:::

## 麦克风建议

如果希望在家庭不同角落都能自然唤醒和交互，建议使用会议场景的 **360° 全向麦克风**。它能更均匀地接收房间内各方向的声音，适合将 homebot 放在客厅等公共区域使用。

笔记本电脑的内置麦克风通常更偏向近距离、定向拾音；距离较远或说话方向偏离时，唤醒与识别效果可能不如专用全向麦克风，也可能不如智能音箱灵敏。
