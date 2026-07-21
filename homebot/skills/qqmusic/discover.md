# discover — 搜索

## 统一搜索

**PATH：** `/discover/search`

**请求参数 (`params`)：**

| 参数      | 类型   | 必填 | 说明                         |
| --------- | ------ | ---- | ---------------------------- |
| `keyword` | string | 是   | 搜索关键词                   |
| `type`    | string | 否   | 搜索类型，默认 `"0"`（歌曲） |
| `page`    | int32  | 否   | 页码，从 0 开始，默认 0      |

**type 取值：**

| type  | 含义 |
| ----- | ---- |
| `"0"` | 歌曲 |
| `"1"` | 专辑 |
| `"5"` | 歌手 |

**type="0"（歌曲）回包：**

| 字段                 | 类型   | 说明          |
| -------------------- | ------ | ------------- |
| `songs`              | array  | 歌曲列表      |
| `songs[].songMid`    | string | 歌曲 mid      |
| `songs[].songName`   | string | 歌曲名        |
| `songs[].singerName` | string | 歌手名        |
| `songs[].songH5Url`  | string | H5 详情页链接 |

**输出格式：**

- 编号列表，歌名 + 歌手
- 搜索场景可附带 H5 链接供点击
- **播放场景**不展示链接，用 exec 运行 `scripts/play.py`
