# 推流拉流 - 面试核心内容

---

## 一、面试高频问题（5+）

### Q1: RTMP 协议原理是什么？请描述握手、信令、数据传输三阶段。

**RTMP（Real-Time Messaging Protocol）** 是 Adobe 公司提出的基于 TCP 的实时消息传输协议，默认端口 1935，是直播推流的事实标准。其核心流程分为三个阶段：

#### 第一阶段：握手（Handshake）

RTMP 握手用于确认协议版本和建立加密/校验机制，分为简单握手和复杂握手两种：

- **C0/C1（客户端→服务器）**：C0 是 1 字节的协议版本号（通常为 0x03），C1 是 1536 字节的随机数据块，包含时间戳、零填充和随机字节。
- **S0/S1（服务器→客户端）**：服务器同样返回版本号 S0 和 1536 字节的 S1 数据块。
- **C2/S2（双向确认）**：客户端收到 S1 后回传 C2（对 S1 的回显），服务器收到 C1 后回传 S2（对 C1 的回显）。
- **复杂握手（RTMPE）**：增加了 DH 密钥交换和 HMAC 校验，用于加密传输。

握手完成后，双方进入复用层，开始收发 RTMP Chunk 数据。

#### 第二阶段：信令（Signaling / 控制消息）

信令阶段通过 RTMP 消息（Message）建立网络连接和流连接，主要包含：

- **NetConnection 命令**：
  - `connect`：客户端发起连接请求，携带 app、tcUrl、flashVer 等参数。服务器返回 `_result` 或 `_error`。
  - `createStream`：创建逻辑通道，服务器返回流 ID（streamId）。
- **NetStream 命令**：
  - `publish`：推流端发布流，指定流名（Stream Key）。服务器返回 `onStatus` 确认。
  - `play`：拉流端请求播放，同样返回 `onStatus` 状态。
- **Set Chunk Size**：协商后续 Chunk 传输的分块大小（默认 128 字节，可协商增大以提高效率）。
- **Window Acknowledgement Size**：设置对端确认窗口大小，用于流量控制。

#### 第三阶段：数据传输（Data Transfer）

信令完成后进入稳定传输阶段：

- **音视频数据封装**：FLV Tag → RTMP Message → RTMP Chunk。音频为 Type 8，视频为 Type 9，脚本数据（MetaData）为 Type 18。
- **Chunk 分块传输**：大消息被拆分为多个 Chunk，同一 Chunk Stream ID 的 Chunk 按序传输，接收端重组。
- **绝对时间戳**：首个 Chunk 携带绝对时间戳，后续同一消息的 Chunk 携带与首个 Chunk 的时间戳差值（Type 2）或零（Type 3），减少冗余。
- **Acknowledgement（确认）**：接收端在收到 Window Ack Size 指定的字节数后，发送 Ack 告知发送端已接收，实现流量控制。

> **面试话术**：RTMP 是基于 TCP 的实时消息传输协议。握手阶段通过三次交互（C0→S0, C1→S1, C2→S2）确认协议版本并建立连接。信令阶段通过 connect/createStream/publish 命令建立逻辑通道。数据传输阶段将 FLV 封装的音视频数据拆分为 Chunk 进行复用传输，通过时间戳和流 ID 实现多路复用。

---

### Q2: RTSP vs HLS vs RTMP 协议对比？

| 维度 | RTMP | HLS | RTSP |
|------|------|-----|------|
| **全称** | Real-Time Messaging Protocol | HTTP Live Streaming | Real-Time Streaming Protocol |
| **提出者** | Adobe（2009 开源） | Apple（2009） | RealNetworks / IETF |
| **传输层** | TCP（1935 端口） | HTTP/HTTPS（80/443） | TCP + UDP（554 端口） |
| **封装格式** | FLV | MPEG-TS 切片（.ts） + m3u8 索引 | RTP/RTCP 封包 |
| **延迟** | 1-3 秒（低延迟） | 10-30 秒（高延迟） | 0.5-2 秒（极低延迟） |
| **CDN 友好度** | 一般（需专用 CDN） | 极好（标准 HTTP CDN） | 差（需专用服务器） |
| **防火墙穿透** | 需开放 1935 | 天然穿透（HTTP） | 需开放多端口 |
| **跨平台支持** | 需 Flash/三方库 | 原生支持（iOS/Android/H5） | 需播放器 SDK |
| **应用场景** | 直播推流（上行） | 直播/点播分发（下行） | 监控/视频通话 |
| **自适应码率** | 不支持 | 原生支持（多码率 m3u8） | 有限支持 |
| **DRM 支持** | 有限 | 原生 FairPlay/AES | 有限 |
| **主流度（2024+）** | 推流端主流 | 拉流端主流 | 安防/IoT 领域 |
| **发展状态** | 维护中/逐渐被替代 | 主流/持续演进（LL-HLS） | 稳定/利基市场 |

**关键结论**：
- **推流端**：RTMP 仍是主流（国内 CDN 普遍支持），但 WebRTC 正在崛起。
- **拉流端**：HLS 已成事实标准（跨平台、CDN 友好），FLV/HTTP-FLV 在国内仍有广泛使用。
- **低延迟场景**：RTSP + WebRTC 占据主导（视频通话、IoT、云台控制）。

**国内补充**：HTTP-FLV 协议在国内直播拉流中非常流行（B站、斗鱼等），兼具 RTMP 的低延迟和 HTTP 的防火墙穿透优势。

---

### Q3: 推流端的关键参数有哪些？如何设置？

#### 核心参数四要素：

| 参数 | 含义 | 典型值（直播） | 影响 |
|------|------|--------------|------|
| **分辨率** | 输出画面宽高像素 | 720p (1280×720) / 1080p (1920×1080) | 清晰度 + 带宽 |
| **帧率（FPS）** | 每秒传输帧数 | 15/24/30 fps | 流畅度 + 带宽 |
| **码率（Bitrate）** | 每秒数据量 | 720p: 1.5-3 Mbps，1080p: 3-6 Mbps | 画质 + 带宽 |
| **GOP（关键帧间隔）** | I 帧间隔帧数 | 1-2 秒（30fps 时为 30-60 帧） | 首屏延迟 + 压缩效率 |

#### 详细说明：

**1. 分辨率（Resolution）**
- 主流直播为 720p（1280×720），兼顾画质与带宽成本。
- 移动端常见 540p（960×540），适配小屏和弱网条件。
- 竖屏直播（9:16）特殊处理：通常采集 1080×1920，编码输出 720×1280。

**2. 帧率（Frame Rate）**
- 游戏直播需要 30fps 甚至 60fps 保证流畅。
- 秀场/聊天直播 15-20fps 即可，节省带宽。
- 帧率过低（<15fps）画面卡顿；过高（>60fps）带宽倍增但观感提升有限。

**3. 码率（Bitrate）**
- **CBR（恒定码率）**：码率恒定，带宽可控，但复杂画面质量下降。直播最常用。
- **VBR（可变码率）**：大动态场景分配更多码率，质量更好但带宽波动。
- **ABR（平均码率）**：折中方案，允许一定波动但控制均值。
- 经验公式：`码率(kbps) = 分辨率宽 × 分辨率高 × 帧率 × 运动量因子 × 0.08 / 1000`。

**4. GOP（Group of Pictures）**
- GOP = I 帧间隔，决定关键帧（IDR）的间隔。
- **短 GOP（1s）**：首屏快、seek 快，但压缩率低，带宽高。
- **长 GOP（3-5s）**：压缩率高，带宽低，但首屏慢。
- 直播推荐 1-2 秒 GOP，兼顾首屏和压缩效率。
- I 帧必须是 IDR 帧（Instantaneous Decoding Refresh），确保拉流端从任何 I 帧开始都能正确解码。

**5. 其他关键参数**：
- **编码格式**：H.264（Baseline/Main/High Profile）；H.265 可节省 30-50% 码率，但兼容性和编码开销更高。
- **音频参数**：AAC-LC，采样率 44100Hz，码率 64-128kbps，单声道或立体声。
- **Profile/Level**：Baseline Profile 兼容性最好，适用于低端设备；High Profile 压缩率更高。

---

### Q4: 拉流端的缓冲策略和"秒开"优化怎么做？

#### 拉流缓冲的核心矛盾：卡顿 vs 延迟

| 缓冲策略 | 缓冲量 | 延迟 | 卡顿率 | 适用场景 |
|----------|--------|------|--------|----------|
| 极低缓冲 | 200-500ms | <1s | 高 | WebRTC 通话 |
| 低缓冲 | 1-2s | 2-3s | 中 | 直播互动 |
| 中等缓冲 | 3-5s | 5-8s | 低 | 标准直播 |
| 大缓冲 | 5-10s | 10-15s | 极低 | 弱网/点播 |

#### 秒开优化的关键技术：

**1. GOP 缓存策略（CDN 侧）**
- CDN 边缘节点缓存最近 N 个 GOP（通常缓存最近 2-3 个）。
- 拉流端请求时，CDN 从最近的 I 帧开始发送，避免等待下一个 I 帧。

**2. 首帧优先策略**
- 拉流端首先只缓存视频关键帧（I 帧），丢弃部分非关键帧加速解码。
- 可以请求 CDN 从最近的 IDR 帧开始传输。

**3. 播放器缓冲优化**
```java
// IJKPlayer / ExoPlayer 首帧优化示例
// 1. 设置极小的缓冲起始值
player.setOption(IjkMediaPlayer.OPT_CATEGORY_PLAYER, "framedrop", 1);  // 开启丢帧
player.setOption(IjkMediaPlayer.OPT_CATEGORY_PLAYER, "start-on-prepared", 0);
player.setOption(IjkMediaPlayer.OPT_CATEGORY_FORMAT, "probesize", 1024);  // 减小探测大小
player.setOption(IjkMediaPlayer.OPT_CATEGORY_FORMAT, "analyzeduration", 100);  // 微秒

// 2. 首帧渲染后逐步增大缓冲
player.setOption(IjkMediaPlayer.OPT_CATEGORY_PLAYER, "max-buffer-size", 2*1024*1024);  // 初始2MB
// 首帧显示后动态调整为5MB
```

**4. DNS 和连接预热**
- 预解析推流/拉流域名，减少 DNS 耗时。
- HTTP-DNS 替代 Local DNS，避免运营商劫持和调度不准。
- TCP 连接池复用，减少握手开销。

**5. 多码率自适应（ABR）**
- 首次拉流时选择最低码率（加载最快），播放稳定后无缝切换到高码率。
- HLS 原生支持多码率 m3u8；HTTP-FLV 需播放器自行实现切换逻辑。

**6. QUIC/HTTP3 加速**
- QUIC 基于 UDP，0-RTT 握手显著降低连接建立时间。
- 多路复用避免 TCP 队头阻塞，弱网环境下大幅提升缓冲效率。

**7. 预加载策略**
- 在用户进入直播间前（如列表页），预加载 2-3 个候选流的 GOP 首片。
- 预加载仅缓存 I 帧 + 少量 P 帧，总数据量 < 200KB。

---

### Q5: WebRTC 在直播中的应用场景和优势？

#### WebRTC 直播架构

```
[推流端] --SDP/ICE--> [信令服务器] --SDP/ICE--> [拉流端]
    |                                                    |
    +---------------- SRTP/SCTP 媒体流 ------------------+
                         (P2P 直连)
                         或经 TURN/STUN 中继
```

#### WebRTC 直播 vs 传统直播

| 维度 | WebRTC 直播 | RTMP + CDN 直播 |
|------|------------|-----------------|
| 延迟 | 200-500ms（亚秒级） | 3-10s |
| 传输 | P2P / SFU 转发 | CDN 分发 |
| 编码 | 强制 Opus 音频 + H.264/VP8/VP9/H.265 | H.264/H.265 + AAC |
| 信令 | 需自建信令服务器（WebSocket） | RTMP 内置 |
| 并发能力 | 依赖 SFU / MCU 水平扩展 | CDN 天然支持大规模 |
| 跨平台 | 浏览器原生 + Native SDK | 需播放器 SDK |
| 录制/回放 | 需旁路转推到 CDN | CDN 原生支持 |

#### WebRTC 直播适用场景：

1. **低延迟互动直播**（连麦、PK、竞拍）：亚秒级延迟让互动自然流畅。
2. **云游戏**：延迟要求 <100ms，WebRTC 是唯一现实选择。
3. **远程协作/教育**：白板同步 + 音视频互动，低延迟是刚需。
4. **IoT/安防**：对讲、云台控制需要低延迟信令 + 媒体通道。

#### 典型方案：WebRTC 推流 + RTMP 旁路分发

```
[推流端 WebRTC] → [SFU/WHP 服务器] → [RTMP 转推] → [CDN] → [HLS/FLV 拉流端（大量观众）]
                                      → [WebRTC 拉流端（少量互动观众）]
```

对于同时需要大规模分发和低延迟互动的场景，推流端使用 WebRTC 推流到 SFU，SFU 一路转推 RTMP 到 CDN 给海量观众，同时通过 WebRTC 直接分发给连麦/互动用户。

---

## 二、协议对比总结表

| 特性 | RTMP | RTSP/RTP | HLS | HTTP-FLV | WebRTC | SRT |
|------|------|----------|-----|----------|--------|-----|
| 定位 | 推流 | 监控/通话 | 分发 | 拉流分发 | 实时互动 | 低延迟传输 |
| 传输 | TCP | TCP+UDP | HTTP | HTTP | UDP(SRTP) | UDP |
| 延迟 | 1-3s | <1s | 10-30s | 1-3s | <500ms | <1s |
| 加密 | RTMPS | 无内置 | HTTPS | HTTPS | DTLS-SRTP | AES 内置 |
| 多轨 | 有限 | 支持 | 支持 | 单轨 | 原生支持 | 支持 |
| 拥塞控制 | TCP 自带 | 无 | TCP | TCP | GCC/BBR | 自定义 |
| FEC/重传 | TCP 重传 | 无 | 无 | 无 | NACK/RED | ARQ |
| 标准化 | Adobe | IETF RFC | IETF RFC | 非标 | W3C/IETF | IETF RFC |
| NAT 穿透 | 需端口 | 困难 | HTTP 友好 | HTTP 友好 | ICE 内置 | 需 STUN |
| CDN 支持 | 中等 | 差 | 极好 | 中等 | 差 | 差 |

---

## 三、核心原理深度剖析

### 3.1 RTMP Chunk 分块传输与消息类型

#### Chunk 结构

RTMP 在握手完成后，所有数据都通过 Chunk 传输。每个 Chunk 包含：

```
+--------+--------+--------+--------+--------+--------+
| Basic  | Chunk  |        |        |        |        |
| Header | Msg    | Extended Timestamp | Chunk  |
| (1-12B)| Header | (0/4B)  |  Data   |
+--------+--------+--------+--------+--------+--------+
```

**Basic Header（1-3 字节）**：
- 2 bit Chunk Type（fmt）+ 6 bit Chunk Stream ID（小 ID）
- 若 CS ID = 0，扩展 1 字节（64-319）
- 若 CS ID = 1，扩展 2 字节（64-65599）

**Message Header（0/3/7/11 字节）**，根据 fmt 不同：
- **Type 0**（11 字节）：完整头，包含 timestamp(3B)、msg length(3B)、msg type(1B)、msg stream ID(4B)。用于流的起始或绝对时间戳基准。
- **Type 1**（7 字节）：省略 msg stream ID（与上一条相同），timestamp 为与上一条的差值。
- **Type 2**（3 字节）：仅含 timestamp delta，其他同 Type 1 省略内容。同一消息分片。
- **Type 3**（0 字节）：无消息头，timestamp delta = 0。消息分片的延续。

**Extended Timestamp**：当 timestamp ≥ 0xFFFFFF（约 4.5 小时）时启用 4 字节扩展。

#### RTMP 消息类型（Message Type ID）

| Type ID | 名称 | 说明 |
|---------|------|------|
| 1 | Set Chunk Size | 设置 Chunk 分块大小 |
| 2 | Abort Message | 中止消息 |
| 3 | Acknowledgement | 流量确认（Sequence Number） |
| 4 | User Control | 用户控制事件（Stream EOF、Buffer Empty 等） |
| 5 | Window Ack Size | 设置确认窗口大小 |
| 6 | Set Peer Bandwidth | 对端带宽限制 |
| 8 | Audio Data | 音频数据（FLV Audio Tag 载荷） |
| 9 | Video Data | 视频数据（FLV Video Tag 载荷） |
| 15 | AMF3 Data | ActionScript 数据 |
| 16 | AMF3 Shared Object | 共享对象 |
| 17 | AMF3 Command | 命令（connect/createStream 等） |
| 18 | AMF0 Data | 脚本数据（MetaData） |
| 20 | AMF0 Command | 兼容性命令 |

#### Chunk 分块实现原理

```
大消息（例如300字节视频帧）：

Message: [Video Tag: 5B header + 295B data = 300B]

假设 Chunk Size = 128：

Chunk1: Type0 Header(11B) + Data[0:117]   = 128B (含header的数据)
Chunk2: Type2 Header(3B)  + Data[117:245] = 128B (最大分块)
Chunk3: Type3 Header(0B)  + Data[245:300] = 55B  (最后一块，不足128B)
```

多个 Chunk Stream 通过不同的 Chunk Stream ID 在同一 TCP 连接上交错传输，接收端根据 CS ID 分别重组。

---

### 3.2 HLS 的 m3u8 + ts 切片机制

#### HLS 架构核心

```
[源流] → [切片器(Media Segmenter)] → [.ts 文件 + .m3u8 索引] → [HTTP Server/CDN] → [播放器]
```

#### m3u8 播放列表

**Master Playlist（多码率入口）**：
```m3u8
#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=3000000,RESOLUTION=1280x720,CODECS="avc1.64001f,mp4a.40.2"
hi/prog_index.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=1500000,RESOLUTION=854x480,CODECS="avc1.64001f,mp4a.40.2"
low/prog_index.m3u8
```

**Media Playlist（单码率切片索引）**：
```m3u8
#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:5
#EXT-X-MEDIA-SEQUENCE:100
#EXTINF:4.000,
segment_100.ts
#EXTINF:4.000,
segment_101.ts
#EXTINF:3.800,
segment_102.ts
```

#### HLS 延迟来源分析

| 延迟来源 | 典型耗时 | 说明 |
|----------|---------|------|
| 切片生成 | 2-6s | 等待 ts 切片完成（通常 2-6 秒一个切片） |
| 索引刷新 | 1-2s | 播放器刷新 m3u8 的间隔 |
| 播放器缓冲 | 3-10s | 播放器至少缓冲 3 个切片才开始播放 |
| CDN 缓存 | 1-3s | 边缘节点缓存刷新延迟 |
| **总延迟** | **10-30s** | 传统 HLS 总延迟 |

**低延迟 HLS（LL-HLS）优化**：
- 将切片从 6s 缩短到 2s 甚至更小。
- 引入 `#EXT-X-PART` 部分片段，不等切片完成即可分发。
- 使用 HTTP/2 Push 主动推送新切片。
- 延迟可降至 2-5 秒。

---

### 3.3 直播推流全链路（采集→编码→封装→推流→CDN→拉流→解码→渲染）

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                                      直播推流全链路                                       │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│  [1.采集]          [2.预处理]         [3.编码]            [4.封装]                         │
│  ┌────────┐       ┌────────┐        ┌──────────┐        ┌────────┐                       │
│  │ Camera │──RGB──▶│ 美颜   │──NV21─▶│ H.264硬编│──ES──▶│ FLV    │                       │
│  │ YUV采集│       │ 滤镜   │        │ MediaCodec│       │ 封装   │                       │
│  │ Mic    │──PCM──▶│ 降噪   │──PCM──▶│ AAC 编码 │       │ muxer  │                       │
│  └────────┘       └────────┘        └──────────┘        └───┬────┘                       │
│                                                             │                            │
│  ┌──────────────────────────────────────────────────────────┘                            │
│  │                                                                                       │
│  │  [5.RTMP推流]                           [6.CDN分发]            [7.拉流]                │
│  │  ┌──────────────┐      ┌─────────────────────┐      ┌──────────────────┐              │
│  │  │ RTMP Handshake│─────▶│ 边缘节点(Edge)      │      │ 播放器请求拉流     │              │
│  │  │ connect/publish│     │    ↓                │──HTT▶│ HTTP-FLV/HLS/RTMP │              │
│  │  │ Chunk 分片发送 │     │ 区域节点(Region)    │  P/  │      ↓             │              │
│  │  │ TCP 长连接    │      │    ↓                │  FLV │  解封装(demux)    │              │
│  │  └──────────────┘      │ 源站(Origin)        │      │      ↓             │              │
│  │                        └─────────────────────┘      │  [8.解码]          │              │
│  │                                                     │  H.264→YUV         │              │
│  │                                                     │  AAC→PCM           │              │
│  │                                                     │      ↓             │              │
│  │                                                     │  [9.渲染]          │              │
│  │                                                     │  SurfaceView绘制   │              │
│  │                                                     │  AudioTrack播放    │              │
│  │                                                     └──────────────────┘              │
│  │                                                                                       │
│  └─[全链路延迟 = 采集延迟(50ms) + 编码延迟(100-300ms) + 网络RTT(10-100ms)                 │
│                 + CDN缓存(0-3s) + 播放器缓冲(1-5s) = 总计 2-8s]                           │
│                                                                                          │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 四、直播推流 → CDN 分发 → 拉流观看全链路流程图

```
                        ┌──────────────┐
                        │  主播端推流    │
                        │  (Android/iOS │
                        │   OBS/App)   │
                        └──────┬───────┘
                               │ RTMP Push (TCP 1935)
                               │ 1. Handshake (C0C1→S0S1→C2S2)
                               │ 2. connect(app)
                               │ 3. createStream → streamId
                               │ 4. publish(streamKey)
                               │ 5. 持续发送 FLV Chunks
                               ▼
                   ┌───────────────────────┐
                   │    CDN 边缘节点 (Edge)  │
                   │  ────────────────────  │
                   │  • 接收 RTMP 流        │
                   │  • 缓存 GOP            │
                   │  • 协议转换:           │
                   │    RTMP → HLS (.m3u8+.ts)
                   │    RTMP → HTTP-FLV     │
                   │    RTMP → RTMP (透传)  │
                   │  • 回源到区域节点       │
                   └───────────┬───────────┘
                               │ 内部专线 / 公网回源
                               ▼
                   ┌───────────────────────┐
                   │   区域节点 (Region)     │
                   │  ────────────────────  │
                   │  • 多边缘汇聚          │
                   │  • 缓存/中转            │
                   │  • 回源到源站           │
                   └───────────┬───────────┘
                               │ 回源
                               ▼
                   ┌───────────────────────┐
                   │   源站 (Origin)        │
                   │  ────────────────────  │
                   │  • 接收推流            │
                   │  • 持久化存储          │
                   │  • 切片生成(HLS)       │
                   │  • 鉴权/防盗链         │
                   └───────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                 ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │  观众端 (A)   │  │  观众端 (B)   │  │  观众端 (N)   │
    │  HTTP-FLV   │  │  HLS 拉流    │  │  RTMP 拉流   │
    │  (低延迟)    │  │  (跨平台)    │  │  (PC/专用)   │
    └──────────────┘  └──────────────┘  └──────────────┘


CDN 分发策略:
─────────────────────────────────────────────────
• GSLB (Global Server Load Balance)：DNS 智能调度，将用户请求分配到最近的边缘节点。
• 回源策略：边缘 MISS → 区域节点 → 源站（最少回源）。
• 缓存策略：热流长缓存，冷流短缓存，避免存储浪费。
• 协议转换：边缘节点实现 RTMP→HTTP-FLV/HLS 转换，减少源站压力。
• 多码率分发：源站生成多个码率的 HLS，CDN 全量缓存分发。

拉流端请求流程:
─────────────────────────────────────────────────
1. DNS 解析 → 获取最优 CDN 边缘节点 IP
2. HTTP 请求 → 边缘节点（如：GET /live/stream123.flv）
3. 边缘命中 → 返回缓存数据；边缘 MISS → 回源拉取
4. 播放器接收 → 解封装 → 解码 → 渲染
```

---

## 五-六、完整直播推流方案：Android 摄像头采集 + 硬编码 + RTMP 推送

### 5.1 整体架构

```java
/**
 * Android 直播推流完整方案
 * 
 * 数据流: Camera → SurfaceTexture → GLSurfaceView (预览+美颜) 
 *         → MediaCodec (H.264硬编码) → FLV 封装 → RTMP 推流
 *         音频: AudioRecord → MediaCodec (AAC硬编码) → FLV 封装 → RTMP
 */
```

### 5.2 视频采集模块

```java
public class VideoCaptureManager {
    private Camera mCamera;
    private int mCameraId = Camera.CameraInfo.CAMERA_FACING_FRONT;
    
    // 推流参数配置
    private static final int VIDEO_WIDTH = 1280;
    private static final int VIDEO_HEIGHT = 720;
    private static final int VIDEO_FPS = 24;
    private static final int VIDEO_BITRATE = 2000 * 1000; // 2 Mbps
    private static final int VIDEO_GOP = 2; // 2秒一个I帧
    
    /**
     * 初始化摄像头采集
     * 使用 Camera API 或 Camera2 API
     */
    public void startCapture(SurfaceTexture surfaceTexture) {
        mCamera = Camera.open(mCameraId);
        Camera.Parameters params = mCamera.getParameters();
        
        // 设置预览尺寸
        params.setPreviewSize(VIDEO_WIDTH, VIDEO_HEIGHT);
        params.setPreviewFpsRange(VIDEO_FPS * 1000, VIDEO_FPS * 1000);
        
        // 自动对焦 + 自动白平衡
        params.setFocusMode(Camera.Parameters.FOCUS_MODE_CONTINUOUS_VIDEO);
        params.setWhiteBalance(Camera.Parameters.WHITE_BALANCE_AUTO);
        
        mCamera.setParameters(params);
        mCamera.setPreviewTexture(surfaceTexture);
        mCamera.startPreview();
    }
    
    /**
     * Camera2 API 方案（Android 5.0+ 推荐）
     */
    public void startCaptureV2(TextureView textureView) {
        CameraManager manager = (CameraManager) 
            context.getSystemService(Context.CAMERA_SERVICE);
        // Camera2 采集代码省略，核心：创建 CaptureSession，设置 Surface 目标
        // 优势：更好的控制、支持 RAW、更好的性能
    }
}
```

### 5.3 视频硬编码模块

```java
public class VideoEncoder {
    private MediaCodec mEncoder;
    private int mColorFormat;
    
    public void initEncoder(int width, int height, int fps, int bitrate, int gop) {
        // H.264 编码器 MIME
        String mime = MediaFormat.MIME_TYPE_VIDEO_AVC;
        
        try {
            mEncoder = MediaCodec.createEncoderByType(mime);
        } catch (IOException e) {
            throw new RuntimeException("创建编码器失败", e);
        }
        
        MediaFormat format = MediaFormat.createVideoFormat(mime, width, height);
        format.setInteger(MediaFormat.KEY_BIT_RATE, bitrate);
        format.setInteger(MediaFormat.KEY_FRAME_RATE, fps);
        format.setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, gop);
        format.setInteger(MediaFormat.KEY_COLOR_FORMAT,
            MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface);
        
        // 码率控制模式
        format.setInteger(MediaFormat.KEY_BITRATE_MODE,
            MediaCodecInfo.EncoderCapabilities.BITRATE_MODE_VBR);
        
        // H.264 Profile/Level
        format.setInteger(MediaFormat.KEY_PROFILE,
            MediaCodecInfo.CodecProfileLevel.AVCProfileHigh);
        format.setInteger(MediaFormat.KEY_LEVEL,
            MediaCodecInfo.CodecProfileLevel.AVCLevel31); // 720p
        
        mEncoder.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE);
        mEncoder.start();
    }
    
    /**
     * 通过 Surface 输入方式编码（高效零拷贝）
     * 配合 GLSurfaceView + OpenGL 美颜滤镜
     */
    public Surface getInputSurface() {
        return mEncoder.createInputSurface();
    }
    
    /**
     * 从 MediaCodec 输出缓冲区获取编码数据
     * 提供给 RTMP 推流模块
     */
    public void drainEncoder(RtmpPublisher publisher) {
        MediaCodec.BufferInfo bufferInfo = new MediaCodec.BufferInfo();
        
        while (true) {
            int outputIndex = mEncoder.dequeueOutputBuffer(bufferInfo, 10000);
            
            if (outputIndex == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                // 编码器输出格式变化，获取 SPS/PPS
                MediaFormat newFormat = mEncoder.getOutputFormat();
                ByteBuffer sps = newFormat.getByteBuffer("csd-0"); // SPS
                ByteBuffer pps = newFormat.getByteBuffer("csd-1"); // PPS
                
                // 发送 AVCDecoderConfigurationRecord 给 FLV 封装器
                publisher.sendSpsPps(sps, pps);
                
            } else if (outputIndex >= 0) {
                ByteBuffer encodedData = mEncoder.getOutputBuffer(outputIndex);
                
                if (bufferInfo.size > 0 && (bufferInfo.flags & MediaCodec.BUFFER_FLAG_CODEC_CONFIG) == 0) {
                    // 处理编码帧
                    boolean isKeyFrame = (bufferInfo.flags & MediaCodec.BUFFER_FLAG_KEY_FRAME) != 0;
                    publisher.sendVideoFrame(encodedData, bufferInfo, isKeyFrame);
                }
                
                mEncoder.releaseOutputBuffer(outputIndex, false);
            }
        }
    }
}
```

### 5.4 音频采集与 AAC 编码

```java
public class AudioCaptureEncoder {
    private AudioRecord mAudioRecord;
    private MediaCodec mAudioEncoder;
    
    private static final int SAMPLE_RATE = 44100;
    private static final int CHANNEL_CONFIG = AudioFormat.CHANNEL_IN_STEREO;
    private static final int AUDIO_FORMAT = AudioFormat.ENCODING_PCM_16BIT;
    private static final int AUDIO_BITRATE = 128000; // 128kbps
    
    public void startAudioCapture() {
        int bufferSize = AudioRecord.getMinBufferSize(SAMPLE_RATE, 
            CHANNEL_CONFIG, AUDIO_FORMAT);
        
        mAudioRecord = new AudioRecord(MediaRecorder.AudioSource.MIC,
            SAMPLE_RATE, CHANNEL_CONFIG, AUDIO_FORMAT, bufferSize);
        
        // 初始化 AAC 编码器
        initAudioEncoder();
        
        mAudioRecord.startRecording();
        
        new Thread(() -> {
            byte[] buffer = new byte[2048];
            while (isRecording) {
                int readBytes = mAudioRecord.read(buffer, 0, buffer.length);
                if (readBytes > 0) {
                    encodePcmToAac(buffer, readBytes);
                }
            }
        }, "audio-capture").start();
    }
    
    private void initAudioEncoder() {
        try {
            mAudioEncoder = MediaCodec.createEncoderByType(MediaFormat.MIME_TYPE_AUDIO_AAC);
            MediaFormat format = MediaFormat.createAudioFormat(
                MediaFormat.MIME_TYPE_AUDIO_AAC, SAMPLE_RATE, 2); // 立体声
            format.setInteger(MediaFormat.KEY_BIT_RATE, AUDIO_BITRATE);
            format.setInteger(MediaFormat.KEY_AAC_PROFILE,
                MediaCodecInfo.CodecProfileLevel.AACObjectLC);
            
            mAudioEncoder.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE);
            mAudioEncoder.start();
        } catch (IOException e) {
            e.printStackTrace();
        }
    }
}
```

### 5.5 FLV 封装模块

```java
public class FlvMuxer {
    private ByteArrayOutputStream mOutputBuffer;
    
    /**
     * FLV 文件结构:
     * FLV Header (9B) + PreviousTagSize0 (4B)
     * + Tag1 [TagHeader(11B) + TagData] + PreviousTagSize1(4B)
     * + Tag2 ...
     */
    
    public void writeFlvHeader(boolean hasVideo, boolean hasAudio) {
        byte[] header = new byte[9];
        header[0] = 'F';
        header[1] = 'L';
        header[2] = 'V';
        header[3] = 0x01; // Version 1
        header[4] = 0x00;
        if (hasVideo) header[4] |= 0x01;
        if (hasAudio) header[4] |= 0x04;
        header[5] = 0x00; header[6] = 0x00; header[7] = 0x00; header[8] = 0x09; // Header length
        // + 4 bytes PreviousTagSize0 = 0
        // 发送这 13 字节
    }
    
    /**
     * 封装视频 Tag:
     * Tag Type = 0x09 (Video)
     * Tag Data = FrameType(4bit) + CodecID(4bit) + AVCPacketType(1B) + CompositionTime(3B) + NALU Data
     */
    public byte[] createVideoTag(byte[] naluData, long timestamp, boolean isKeyFrame) {
        int dataSize = naluData.length + 5; // 1(帧类型) + 1(AVC包类型) + 3(CTS)
        byte[] tag = new byte[11 + dataSize + 4]; // header + data + PreviousTagSize
        
        // Tag Header
        tag[0] = 0x09; // Video Tag
        // DataSize (3 bytes, big-endian)
        tag[1] = (byte)((dataSize >> 16) & 0xFF);
        tag[2] = (byte)((dataSize >> 8) & 0xFF);
        tag[3] = (byte)(dataSize & 0xFF);
        // Timestamp (3 bytes + 1 byte extended)
        tag[4] = (byte)((timestamp >> 16) & 0xFF);
        tag[5] = (byte)((timestamp >> 8) & 0xFF);
        tag[6] = (byte)(timestamp & 0xFF);
        tag[7] = (byte)((timestamp >> 24) & 0xFF);
        // StreamID = 0
        tag[8] = 0; tag[9] = 0; tag[10] = 0;
        
        int offset = 11;
        // FrameType + CodecID
        tag[offset++] = (byte)(isKeyFrame ? 0x17 : 0x27); // 0x17=IDR帧(AVC), 0x27=非IDR帧(AVC)
        // AVCPacketType = 1 (NALU)
        tag[offset++] = 0x01;
        // CompositionTime = 0
        tag[offset++] = 0x00; tag[offset++] = 0x00; tag[offset++] = 0x00;
        
        // NALU Data
        System.arraycopy(naluData, 0, tag, offset, naluData.length);
        offset += naluData.length;
        
        // PreviousTagSize
        int previousTagSize = dataSize + 11;
        tag[offset++] = (byte)((previousTagSize >> 24) & 0xFF);
        tag[offset++] = (byte)((previousTagSize >> 16) & 0xFF);
        tag[offset++] = (byte)((previousTagSize >> 8) & 0xFF);
        tag[offset++] = (byte)(previousTagSize & 0xFF);
        
        return tag;
    }
    
    /**
     * 封装 Script Tag (MetaData - onMetaData)
     * 必须在首个音视频 Tag 之前发送
     */
    public byte[] createMetaDataTag(double duration, int width, int height,
                                     double videoDataRate, double frameRate,
                                     double audioDataRate, double sampleRate) {
        // 使用 AMF0 编码 onMetaData 对象
        // width, height, videodatarate, framerate, videocodecid=7 (AVC)
        // audiodatarate, audiosamplerate, audiocodecid=10 (AAC)
        // ... (AMF0 编码实现省略，实际项目推荐使用成熟的 FLV 封装库如 srs-librtmp)
        return new byte[0]; // placeholder
    }
}
```

### 5.6 RTMP 推流模块

```java
public class RtmpPublisher {
    private Socket mSocket;
    private OutputStream mOutputStream;
    private InputStream mInputStream;
    
    private String mRtmpUrl; // rtmp://live.example.com/live/streamKey
    private int mStreamId;
    private int mChunkSize = 128;   // 默认分块大小
    private int mWindowAckSize = 2500000;
    private int mMaxChunkSize = 4096; // 协商后增大分块
    
    // Chunk Stream ID 分配
    private static final int CSID_PROTOCOL_CONTROL = 2;  // 协议控制消息
    private static final int CSID_COMMAND = 3;            // AMF 命令
    private static final int CSID_AUDIO = 4;              // 音频流
    private static final int CSID_VIDEO = 5;              // 视频流
    
    /**
     * RTMP 连接建立完整流程
     */
    public void connect(String rtmpUrl) throws IOException {
        mRtmpUrl = rtmpUrl;
        
        // 1. 解析 URL：rtmp://host:port/app/streamName
        URI uri = new URI(rtmpUrl);
        String host = uri.getHost();
        int port = uri.getPort() > 0 ? uri.getPort() : 1935;
        
        // 2. TCP 连接
        mSocket = new Socket(host, port);
        mOutputStream = mSocket.getOutputStream();
        mInputStream = mSocket.getInputStream();
        
        // 3. RTMP 握手
        performHandshake();
        
        // 4. 发送 connect 命令
        sendConnect(uri);
        
        // 5. 等待 _result
        waitForConnectResult();
        
        // 6. 发送 createStream
        sendCreateStream();
        
        // 7. 发送 publish
        sendPublish(uri);
        
        // 8. 增大 Chunk Size（从128→4096）
        sendSetChunkSize(mMaxChunkSize);
    }
    
    /**
     * RTMP 简单握手实现
     */
    private void performHandshake() throws IOException {
        // C0: 发送协议版本号 0x03
        mOutputStream.write(0x03);
        
        // C1: 发送 1536 字节（时间戳 + 零填充 + 随机数据）
        byte[] c1 = new byte[1536];
        c1[0] = 0; c1[1] = 0; c1[2] = 0; c1[3] = 0; // timestamp = 0
        // c1[4-7] = 0 (zero)
        new Random().nextBytes(c1); // random bytes from offset 8
        mOutputStream.write(c1);
        mOutputStream.flush();
        
        // 读取 S0 (1 byte)
        byte[] s0 = new byte[1];
        mInputStream.read(s0);  // expect 0x03
        
        // 读取 S1 (1536 bytes)
        byte[] s1 = new byte[1536];
        mInputStream.read(s1);
        
        // 发送 C2（回显 S1 的时间戳和 S1 数据）
        byte[] c2 = new byte[1536];
        System.arraycopy(s1, 0, c2, 0, 4); // S1 timestamp
        c2[4] = 0; c2[5] = 0; c2[6] = 0; c2[7] = 0;
        System.arraycopy(s1, 8, c2, 8, 1528); // echo S1 random data
        mOutputStream.write(c2);
        mOutputStream.flush();
        
        // 读取 S2 (1536 bytes)
        byte[] s2 = new byte[1536];
        mInputStream.read(s2);
    }
    
    /**
     * Chunk 数据发送格式
     */
    private void writeChunk(int csid, int msgType, int msgStreamId, 
                            byte[] data, int timestamp) throws IOException {
        // Chunk Basic Header (1-3 bytes)
        // 简单实现：csid 2-63 用 1 字节
        byte fmt = 0x00; // Type 0
        byte basicHeader = (byte)((fmt << 6) | csid);
        
        // 写入 Basic Header
        mOutputStream.write(basicHeader);
        
        // Message Header (Type 0 = 11 bytes)
        // Timestamp (3 bytes)
        byte[] ts = intToBytes3(timestamp);
        mOutputStream.write(ts);
        
        // Message Length (3 bytes)
        byte[] length = intToBytes3(data.length);
        mOutputStream.write(length);
        
        // Message Type (1 byte)
        mOutputStream.write(msgType);
        
        // Message Stream ID (4 bytes, little-endian)
        byte[] sid = new byte[4];
        sid[0] = (byte)(msgStreamId & 0xFF);
        sid[1] = (byte)((msgStreamId >> 8) & 0xFF);
        sid[2] = (byte)((msgStreamId >> 16) & 0xFF);
        sid[3] = (byte)((msgStreamId >> 24) & 0xFF);
        mOutputStream.write(sid);
        
        // Chunk Data
        int offset = 0;
        while (offset < data.length) {
            int chunkLen = Math.min(mChunkSize, data.length - offset);
            if (offset == 0) {
                // First chunk already has the full header above
                mOutputStream.write(data, offset, chunkLen);
            } else {
                // Subsequent chunks use Type 3 (no message header)
                byte type3Header = (byte)((0x03 << 6) | csid); // fmt=3
                mOutputStream.write(type3Header);
                mOutputStream.write(data, offset, chunkLen);
            }
            offset += chunkLen;
        }
    }
    
    /**
     * 发送视频帧数据
     */
    public void sendVideoFrame(ByteBuffer encodedData, MediaCodec.BufferInfo bufferInfo,
                                boolean isKeyFrame) {
        // 将 H.264 NAL Unit 封装为 FLV Video Tag
        byte[] naluData = new byte[bufferInfo.size];
        encodedData.get(naluData);
        encodedData.position(bufferInfo.offset);
        
        // 创建 FLV Video Tag
        long timestamp = bufferInfo.presentationTimeUs / 1000; // 微秒转毫秒
        byte[] flvTag = mFlvMuxer.createVideoTag(naluData, timestamp, isKeyFrame);
        
        // 通过 RTMP Chunk 发送（CSID=5 for video, MessageType=9）
        try {
            writeChunk(CSID_VIDEO, 9, mStreamId, flvTag, (int)timestamp);
        } catch (IOException e) {
            handleDisconnect(e);
        }
    }
    
    /**
     * 发送音频帧
     */
    public void sendAudioFrame(byte[] aacData, long timestamp) {
        // AAC RAW → FLV Audio Tag
        byte[] flvAudioTag = mFlvMuxer.createAudioTag(aacData, timestamp);
        try {
            writeChunk(CSID_AUDIO, 8, mStreamId, flvAudioTag, (int)timestamp);
        } catch (IOException e) {
            handleDisconnect(e);
        }
    }
}
```

### 5.7 完整推流 SDK 装配流程

```java
/**
 * 完整推流 SDK 使用示例
 */
public class LivePusher {
    private VideoCaptureManager mVideoCapture;
    private VideoEncoder mVideoEncoder;
    private AudioCaptureEncoder mAudioEncoder;
    private RtmpPublisher mRtmpPublisher;
    private FlvMuxer mFlvMuxer;
    
    // 推流参数配置
    public static class PusherConfig {
        int videoWidth = 1280;
        int videoHeight = 720;
        int videoFps = 24;
        int videoBitrate = 2000000;   // 2 Mbps
        int videoGop = 48;            // 2秒 (24fps*2)
        int audioSampleRate = 44100;
        int audioBitrate = 128000;    // 128 kbps
        String rtmpUrl;
    }
    
    public void startPush(PusherConfig config) {
        // 1. 初始化 RTMP 连接（异步）
        mRtmpPublisher = new RtmpPublisher();
        new Thread(() -> {
            try {
                mRtmpPublisher.connect(config.rtmpUrl);
                // 发送 MetaData
                mRtmpPublisher.sendMetaData(config);
            } catch (IOException e) {
                onError(e);
                return;
            }
            
            // 2. 连接成功后启动采集和编码
            runOnUiThread(() -> startCaptureAndEncode(config));
        }, "rtmp-connect").start();
    }
    
    private void startCaptureAndEncode(PusherConfig config) {
        // 初始化编码器
        mVideoEncoder = new VideoEncoder();
        mVideoEncoder.initEncoder(config.videoWidth, config.videoHeight,
            config.videoFps, config.videoBitrate, config.videoGop);
        
        // 初始化 FLV 封装器
        mFlvMuxer = new FlvMuxer();
        
        // 初始化摄像头
        mVideoCapture = new VideoCaptureManager();
        
        // OpenGL 美颜滤镜 surface → 编码器 surface
        Surface encoderSurface = mVideoEncoder.getInputSurface();
        // GLSurfaceView 处理后输出到 encoderSurface
        
        mVideoCapture.startCapture(encoderSurface);
        
        // 启动音频采集
        mAudioEncoder = new AudioCaptureEncoder();
        mAudioEncoder.startAudioCapture();
        
        // 持续获取编码数据并推流
        drainAndPublish();
    }
    
    /**
     * 推流断开重连策略
     */
    private void onDisconnect() {
        int retryCount = 0;
        int maxRetry = 5;
        long retryDelay = 1000; // 1秒
        
        while (retryCount < maxRetry && !isStopped) {
            try {
                Thread.sleep(retryDelay * (retryCount + 1)); // 递增延迟
                mRtmpPublisher.connect(mRtmpUrl);
                return; // 重连成功
            } catch (Exception e) {
                retryCount++;
                Log.w("LivePusher", "重连失败，第 " + retryCount + " 次");
            }
        }
        // 重连失败，停止推流
        stopPush();
    }
    
    public void stopPush() {
        isStopped = true;
        mVideoCapture.release();
        mVideoEncoder.release();
        mAudioEncoder.release();
        mRtmpPublisher.disconnect();
    }
}
```

### 5.8 关键优化点总结

| 优化项 | 具体措施 | 效果 |
|--------|---------|------|
| **编码延迟** | MediaCodec 硬编码 + Surface 输入（零拷贝） | 编码延迟 <50ms |
| **网络适应** | 动态码率调整，根据网络 RTT/丢包率调整 | 避免卡顿和断流 |
| **弱网对抗** | FEC（前向纠错）+ NACK（丢包重传） | 弱网下流畅播放 |
| **内存优化** | 复用 ByteBuffer、对象池、减少 GC | 避免编码丢帧 |
| **帧率控制** | 根据编码耗时动态跳帧，保持实时性 | 编码堆积不扩散 |
| **GOP 优化** | 1-2s GOP 均衡首屏和压缩 | 秒开 + 低带宽 |
| **降噪/美颜** | OpenGL ES Shader 实时处理 | 画面质量提升 |
| **音频同步** | 音视频时间戳对齐，PTS 驱动 | 唇音同步 |

---

## 总结

| 技术栈 | 推荐方案 |
|--------|---------|
| **推流协议** | RTMP（当前主流）/ WebRTC（新型低延迟） |
| **拉流协议** | HTTP-FLV（低延迟国内）/ HLS（跨平台） |
| **编码格式** | H.264 + AAC（兼容性最佳）/ H.265（节省带宽） |
| **CDN** | 阿里云/腾讯云/七牛云直播 CDN |
| **开源方案** | SRS（Simple-Rtmp-Server）/ Nginx-RTMP-Module / Live555 |
| **播放器** | ExoPlayer / IJKPlayer（FFmpeg）/ AliPlayer |

面试中重点掌握 **RTMP 三阶段原理**、**协议对比表格**、**推流全链路**和**秒开优化**四大核心话题，即可应对 90% 以上的推流拉流面试问题。
