# 01 音视频编解码

## 模块概览

音视频编解码是 Android 音视频开发的基石。本章聚焦 **H.264/H.265 编码标准**、**MediaCodec 硬编解码 API**、**AAC 音频编码**三大核心领域，涵盖面试高频考点、底层原理、源码分析和工程实践。

---

## 一、面试高频问题（6+）

### 1. H.264 与 H.265（HEVC）编码效率对比

> 问题：H.265 相比 H.264 在编码效率上有哪些提升？原理是什么？

**回答要点**：

| 对比维度 | H.264（AVC） | H.265（HEVC） | 差异说明 |
|----------|-------------|---------------|---------|
| **压缩率** | 基准 | 高 50% | 同等画质下码率减半 |
| **宏块大小** | 16×16 固定 | 8×8 ~ 64×64（CTU） | H.265 支持更大编码单元，高分辨率更优 |
| **帧内预测** | 9 种方向 | 35 种方向 | H.265 预测更精准，残差更小 |
| **帧间预测** | 单向/双向 ME | 高级 MVP + Merge 模式 | 运动矢量编码效率更高 |
| **变换** | DCT 4×4 / 8×8 | DCT/DST 4×4 ~ 32×32 | 更大的变换块提升压缩 |
| **去块滤波** | 环路滤波 | SAO + 环路滤波 | H.265 增加采样自适应偏移，改善主观质量 |
| **并行处理** | 切片级 | Tiles + WPP | H.265 更友好的多核并行设计 |
| **典型码率（1080p@30fps）** | 4~8 Mbps | 2~4 Mbps | 码率降低约 50% |
| **兼容性** | 所有设备 | Android 5.0+ | H.264 仍是最通用的选择 |

**核心原因**：H.265 通过更大的 CTU 结构、更丰富的预测模式、SAO 滤波和更先进的熵编码（CABAC 改进），在相同画质下实现约 50% 的码率节省，但编码复杂度提升 2~10 倍。

---

### 2. I/P/B 帧的区别与 GOP 概念

> 问题：解释 I 帧、P 帧、B 帧的区别，以及 GOP 如何影响编解码？

**回答要点**：

| 帧类型 | 全称 | 编码方式 | 压缩率 | 作用 |
|--------|------|---------|:------:|------|
| **I 帧** | Intra-coded Frame | 帧内编码，仅用本帧数据 | 最低 | 关键帧，随机访问起点，GOP 边界 |
| **P 帧** | Predictive Frame | 前向预测，参考前面的 I/P 帧 | 中等 | 帧间压缩，依赖前序帧 |
| **B 帧** | Bi-predictive Frame | 双向预测，参考前后帧 | 最高 | 压缩率最高，增加编码延迟 |

**GOP（Group of Pictures）**：

```
GOP 结构示例（GOP=12, 有B帧）:
I₀ B₁ B₂ P₃ B₄ B₅ P₆ B₇ B₈ P₉ B₁₀ B₁₁ | I₁₂ ...

关键参数：
- GOP Size：两个 I 帧之间的帧数间隔
- 解码顺序 ≠ 显示顺序（PTS vs DTS）
- H.264 Baseline Profile 不支持 B 帧（仅 I+P）
- 直播场景常用 GOP=1~3s（减少首屏延迟）
- 点播场景常用 GOP=2~5s（追求压缩率）
```

**面试延伸**：
- 为什么直播推流很少用 B 帧？→ B 帧需要等待"后面的帧"才能开始编码，引入延迟，不适合低延迟场景。
- IDR 帧与普通 I 帧的区别？→ IDR（Instantaneous Decoder Refresh）强制刷新参考帧缓冲区，解码器可以从 IDR 帧开始独立解码；普通 I 帧后面的帧可能还参考了 GOP 前的帧。

---

### 3. MediaCodec 硬编解码的异步模式与 BufferQueue

> 问题：MediaCodec 的同步模式和异步模式有什么区别？BufferQueue 的工作机制是什么？

**回答要点**：

**同步模式 vs 异步模式**：

| 对比维度 | 同步模式 | 异步模式（Callback） |
|----------|---------|---------------------|
| API 方式 | `dequeueInputBuffer()` / `dequeueOutputBuffer()` 手动轮询 | `setCallback(MediaCodec.Callback)` 回调通知 |
| 线程模型 | 调用线程阻塞等待 | 内部线程回调，不阻塞调用线程 |
| 时序控制 | 应用完全可控 | 回调驱动，按事件处理 |
| CPU 占用 | 轮询空转可能消耗 CPU | 事件驱动，更高效 |
| 代码复杂度 | 简单直接 | 需要处理回调中的状态同步 |
| 适用场景 | 简单录制、同步编码 | 播放器解码、复杂管线 |
| API 版本 | API 16+ | API 21+ |

**BufferQueue 机制**：

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────┐
│   Producer   │ ──▶ │   BufferQueue     │ ──▶ │  Consumer   │
│  (Surface)   │     │  ┌──┬──┬──┬──┐   │     │(MediaCodec) │
└─────────────┘     │  │B0│B1│B2│B3│   │     └─────────────┘
                    │  └──┴──┴──┴──┘   │
                    │  dequeue/queue/  │
                    │  acquire/release │
                    └──────────────────┘

关键概念：
- Producer（Surface/Camera）：往 BufferQueue 填充数据
- Consumer（MediaCodec 输入端）：从 BufferQueue 取出数据编码
- BufferQueue 最多缓存 N 个 buffer（由 dequeue 时的 timeout 决定）
- 当 BufferQueue 满时，Producer 阻塞等待 Consumer 消费
```

**面试延伸**：`MediaCodec.createInputSurface()` 创建 Surface 作为输入，内部使用 BufferQueue 传递数据。Camera 预览帧通过 OpenGL 渲染到该 Surface，零拷贝传递到编码器。

---

### 4. MediaCodec 的 ColorFormat（YUV → NV12/YV12）

> 问题：MediaCodec 编码时支持的 ColorFormat 有哪些？如何处理不同厂商的兼容性？

**回答要点**：

**Android YUV 颜色格式**：

| ColorFormat | 常量值 | 排列方式 | 说明 |
|-------------|:------:|---------|------|
| COLOR_FormatYUV420Planar | 19 | YYY...UUU...VVV | 标准 YUV420P，三个平面独立存储 |
| COLOR_FormatYUV420SemiPlanar | 21 | YYY...UVUVUV... | NV12，Y平面 + UV交错平面，**编码器最常用** |
| COLOR_FormatYUV420PackedSemiPlanar | — | YYY...UVUV... | 与 SemiPlanar 类似，对齐可能不同 |
| COLOR_FormatSurface | — | Surface 输入 | **推荐方式**，由系统处理格式转换 |
| COLOR_FormatYUV420Flexible | 0x7F420888 | 厂商定义 | 高通等厂商的私有格式 |

**关键注意事项**：

```kotlin
// 1. 查询编码器支持的 ColorFormat
val codecInfo = mediaCodec.codecInfo
val caps = codecInfo.getCapabilitiesForType("video/avc")
val colorFormats = caps.colorFormats  // 厂商不同，支持列表不同

// 2. 推荐做法：使用 Surface 输入，避免手动处理 YUV 格式
val surface = mediaCodec.createInputSurface()  // Surface 自动处理格式匹配

// 3. 如果必须使用 ByteBuffer 输入：
// - 优先选择 COLOR_FormatYUV420SemiPlanar（NV12），兼容性最好
// - 避免使用 COLOR_FormatYUV420Flexible（不同厂商实现不一致）
```

**NV12 vs YV12**：
- NV12（SemiPlanar）：Y 平面 + UV 交错平面。Android Camera、MediaCodec 默认输出格式。
- YV12（Planar）：Y + V + U 三个独立平面。FFmpeg/libyuv 常用。
- 转换公式：NV12 → YV12 分离 UV 通道即可；YV12 → NV12 交错 U 和 V。

---

### 5. 音频 AAC 编码和采样率/码率选择

> 问题：Android 上如何选择音频编码参数（采样率、码率、声道数）？AAC 有哪些 Profile？

**回答要点**：

**AAC Profile 对比**：

| Profile | 全称 | 复杂度 | 典型码率（立体声） | 适用场景 |
|---------|------|:------:|-------------------|---------|
| AAC-LC | Low Complexity | 低 | 64~256 kbps | 最通用，Android 默认支持 |
| HE-AAC | High Efficiency | 中 | 32~80 kbps | 低码率场景（≤64kbps） |
| HE-AACv2 | HE-AAC + PS | 中 | 16~48 kbps | 极低码率（≤48kbps），参数立体声 |
| AAC-ELD | Enhanced Low Delay | 中 | 48~128 kbps | 实时通话、低延迟通信 |

**采样率选择**：

| 采样率 | 应用场景 | 说明 |
|:------:|---------|------|
| **8000 Hz** | 语音通话 | 电话音质，窄带 |
| **16000 Hz** | VoIP | 宽带语音 |
| **22050 Hz** | 网络电台 | 低质量音频 |
| **44100 Hz** | CD 音质 | 音频录制默认值 |
| **48000 Hz** | 视频配音 | **视频录制首选**，与视频帧率时间基准对齐 |

**码率与声道**：

```
单声道（Mono）：
  - 录音/语音：32~64 kbps
  - 音乐：64~128 kbps

立体声（Stereo）：
  - 录音/语音：64~128 kbps
  - 音乐：128~256 kbps
  - 高清音频：256~320 kbps

典型视频录制配置：
  - 采样率：44100 或 48000 Hz
  - 码率：128 kbps（立体声）
  - Profile：AAC-LC
  - 声道数：2（立体声）
```

**MediaCodec 音频编码关键代码**：

```kotlin
val format = MediaFormat.createAudioFormat(
    MediaFormat.MIMETYPE_AUDIO_AAC,
    44100,  // 采样率
    1       // 声道数
)
format.setInteger(MediaFormat.KEY_BIT_RATE, 96000)        // 码率
format.setInteger(MediaFormat.KEY_AAC_PROFILE, 
    MediaCodecInfo.CodecProfileLevel.AACObjectLC)          // AAC-LC
format.setInteger(MediaFormat.KEY_MAX_INPUT_SIZE, 16384)  // 输入缓冲大小
```

---

### 6. 硬编解码（MediaCodec） vs 软编解码（FFmpeg）的适用场景

> 问题：什么时候选择 Hardware Codec，什么时候选择 FFmpeg 软编解码？

**回答要点**：

| 对比维度 | 硬编解码（MediaCodec） | 软编解码（FFmpeg） |
|----------|----------------------|-------------------|
| **性能** | 专用硬件模块（DSP/GPU），低功耗 | CPU 密集运算，功耗高 |
| **延迟** | 极低（<50ms） | 较高（依赖 CPU 算力） |
| **兼容性** | 仅支持设备支持的格式 | 支持几乎所有格式 |
| **画质控制** | 参数有限，黑盒 | 精细控制每个编码参数 |
| **功能丰富度** | 基础编码功能 | 滤镜、字幕、多路复用等全功能 |
| **稳定性** | 依赖厂商实现，可能有 Bug | 纯软件，行为可预测 |
| **功耗** | 低 | 高（发热明显） |
| **移植性** | Android 平台绑定 | 跨平台 |
| **CPU 占用** | <10% | 80%+ |

**决策流程**：

```
                    ┌─ 需要实时录制？──────────────── YES ──▶ 硬编码（Camera → Surface → MediaCodec）
                    │
解码/编码需求 ─────┼─ 格式在硬编码白名单？────────── YES ──▶ 硬编码（MediaCodec）
                    │
                    ├─ 需要精细控制码率/画质参数？─── YES ──▶ 软编码（FFmpeg/x264）
                    │
                    ├─ 需要特殊编码格式（VP9/AV1）？─ YES ──▶ Android 10+ 硬编码可用，否则软解
                    │
                    ├─ 稳定性优先（长期运行）？────── YES ──▶ 软编码（避免厂商 Bug）
                    │
                    └─ 杂格式/旧视频兼容播放？────── YES ──▶ 软解码（FFmpeg 兜底）
```

**最佳实践**：
- **录制/直播**：硬编码（MediaCodec + Surface），低延迟、低功耗
- **视频编辑/转码**：软编码（FFmpeg），可精细控制并能使用 x264/x265 高级参数
- **播放器**：优先硬解（MediaCodec），FFmpeg 兜底不支持的格式
- **混合方案**：MediaCodec 解码 → OpenGL 处理 → MediaCodec 编码（效率最高）

---

## 二、核心原理深度解析

### 2.1 H.264 编码完整流程

H.264 编码器的核心流程图（自顶向下）：

```
输入帧（YUV）
     │
     ▼
┌──────────────────────────────────────────────────────┐
│              1. 帧内/帧间预测决策                       │
│  ┌─────────────────┐    ┌─────────────────┐           │
│  │  帧内预测 (Intra) │    │  帧间预测 (Inter) │           │
│  │  • 4×4: 9种模式   │    │  • 运动估计 (ME)   │           │
│  │  • 16×16: 4种模式 │    │  • 运动补偿 (MC)   │           │
│  │  • 亮度+色度预测  │    │  • 多参考帧        │           │
│  └────────┬────────┘    └────────┬────────┘           │
│           │                      │ (运动矢量 MV)       │
│           └──────────┬───────────┘                    │
│                      ▼                                │
│              ┌───────────────┐                        │
│              │ 预测帧 (P-Frame)│                        │
│              └───────┬───────┘                        │
└──────────────────────┼────────────────────────────────┘
                       │
                       ▼
              ┌─────────────────┐
              │  原始帧 - 预测帧  │
              │  = 残差 (Residual)│
              └────────┬────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│              2. 变换 (Transform)                      │
│  ┌──────────────────────────────────────┐            │
│  │  DCT (离散余弦变换)                    │            │
│  │  • 4×4 整数 DCT（主变换）              │            │
│  │  • 8×8 整数 DCT（High Profile）        │            │
│  │  • Hadamard 变换（DC系数）             │            │
│  └──────────────────┬───────────────────┘            │
└──────────────────────┼────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│              3. 量化 (Quantization)                   │
│  ┌──────────────────────────────────────┐            │
│  │  除以量化步长 Qstep = 2^(QP/6) × Qoffset │         │
│  │  • QP 越大 → 量化越粗 → 码率低 / 画质差  │         │
│  │  • QP 越小 → 量化越细 → 码率高 / 画质好  │         │
│  │  • QP 范围：0~51（H.264）               │         │
│  └──────────────────┬───────────────────┘            │
└──────────────────────┼────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│              4. 熵编码 (Entropy Coding)               │
│  ┌──────────────────────┐  ┌──────────────────────┐  │
│  │   CAVLC               │  │   CABAC               │  │
│  │  (Baseline/Extended)  │  │  (Main/High Profile)  │  │
│  │  • 可变长编码          │  │  • 算术编码            │  │
│  │  • 计算简单            │  │  • 压缩率高 10%~20%    │  │
│  │  • 抗误码              │  │  • 计算复杂            │  │
│  └──────────────────────┘  └──────────────────────┘  │
└──────────────────────┼────────────────────────────────┘
                       │
                       ▼
              输出码流 (NAL Units)
```

**帧内预测（Intra Prediction）核心思想**：

```
当前 4×4 块     已编码的左/上像素
┌─┬─┬─┬─┐       ┌─┬─┬─┬─┬─┬─┬─┬─┬──┐
│?│?│?│?│       │X│X│X│X│X│X│X│X│X │  ← 上边参考像素
├─┼─┼─┼─┤       ├─┼─┼─┼─┼─┼─┼─┼─┼──┤
│?│?│?│?│       │X│?│?│?│?│?│?│?│? │
├─┼─┼─┼─┤       ├─┼─┼─┼─┼─┼─┼─┼─┼──┤  沿预测方向复制参考像素
│?│?│?│?│       │X│?│?│?│?│?│?│?│? │
├─┼─┼─┼─┤       ├─┼─┼─┼─┼─┼─┼─┼─┼──┤  → 选出残差最小的预测方向
│?│?│?│?│       │X│?│?│?│?│?│?│?│? │
└─┴─┴─┴─┘       ├─┼─┼─┼─┼─┼─┼─┼─┼──┤
                 │X│?│?│?│?│?│?│?│? │
                 └─┴─┴─┴─┴─┴─┴─┴─┴──┘
                   ↑ 左边参考像素

共有 9 种预测方向（模式0~8）：
模式0: 垂直（↓）   模式1: 水平（→）   模式2: DC（平均值）
模式3: 左下对角线  模式4: 右下对角线  模式5: 右垂直
模式6: 下水平      模式7: 左垂直      模式8: 上水平
```

**帧间预测（Inter Prediction）核心思想**：

```
参考帧（已编码）                   当前帧（待编码）
┌──────────────────┐             ┌──────────────────┐
│                  │             │        ┌─┐       │
│   ┌─┐            │   运动矢量   │        │?│       │
│   │A│──── MV ────┼─────────────┼────────▶│B│       │
│   └─┘            │  (dx, dy)   │        └─┘       │
│                  │             │                  │
└──────────────────┘             └──────────────────┘

步骤：
1. 运动估计 (ME)：在参考帧中搜索最佳匹配块 → 得到 MV
2. 运动补偿 (MC)：用 MV 从参考帧取出预测块
3. 计算残差 = 当前块 - 预测块 → 变换+量化+熵编码
4. 只需传输 MV + 残差，大幅减少数据量
```

---

### 2.2 MediaCodec 生命周期

MediaCodec 的完整生命周期状态机：

```
                    ┌──────────────────┐
                    │  Uninitialized   │  ← createByCodecName() / createEncoderByType()
                    └────────┬─────────┘
                             │ configure(format, surface, crypto, flags)
                             ▼
                    ┌──────────────────┐
          ┌────────│   Configured     │────────┐
          │        └────────┬─────────┘        │
          │                 │ start()           │ reset()
          │                 ▼                   │
          │        ┌──────────────────┐        │
          │        │    Running       │        │
          │        │                  │        │
          │        │  ┌────────────┐  │        │
          │        │  │  Flushing  │  │        │
          │        │  └────────────┘  │        │
          │        └──┬───────────┬───┘        │
          │           │ stop()    │ release()   │
          │           ▼           ▼             │
          │  ┌────────────┐  ┌────────────┐    │
          │  │  Stopped   │  │  Released   │    │
          │  └─────┬──────┘  └────────────┘    │
          │        │ reset()                    │
          │        └────────────────────────────┘
          │
          │  ┌──────────────────────────┐
          └─▶│  End-of-Stream (EOS)     │
             │  (OutputFormat Changed)  │
             └──────────────────────────┘
```

**关键阶段详解**：

| 阶段 | API 调用 | 说明 |
|------|---------|------|
| **创建** | `MediaCodec.createByCodecName()` / `createEncoderByType()` | 创建编解码器实例 |
| **配置** | `codec.configure(format, surface, crypto, flags)` | 设置输入格式、输出 Surface、加密等。`CONFIGURE_FLAG_ENCODE` 表示编码器 |
| **启动** | `codec.start()` | 进入 Running 状态，开始接收输入 |
| **输入** | `codec.queueInputBuffer(index, 0, size, pts, flags)` | 提交未压缩数据帧（编码）或压缩码流（解码） |
| **输出** | `codec.dequeueOutputBuffer(info, timeout)` | 获取编码后的数据或解码后的帧 |
| **EOS** | `codec.queueInputBuffer(..., BUFFER_FLAG_END_OF_STREAM)` | 发送结束信号，编解码器处理完剩余数据后输出 EOS |
| **停止** | `codec.stop()` | 回到 Uninitialized，可重新 configure |
| **释放** | `codec.release()` | 释放底层资源，不可再使用 |

**Buffer 管理关键点**：

```kotlin
// 同步模式核心循环
mediaCodec.start()
while (isEncoding) {
    // 1. 获取可用输入 buffer
    val inputIndex = mediaCodec.dequeueInputBuffer(10_000)  // timeout 10ms
    if (inputIndex >= 0) {
        val inputBuffer = mediaCodec.getInputBuffer(inputIndex)!!
        // 填充 YUV 数据到 inputBuffer
        inputBuffer.put(yuvData)
        mediaCodec.queueInputBuffer(inputIndex, 0, yuvData.size, timestamp, 0)
    }

    // 2. 获取编码输出
    val outputIndex = mediaCodec.dequeueOutputBuffer(bufferInfo, 10_000)
    if (outputIndex >= 0) {
        val outputBuffer = mediaCodec.getOutputBuffer(outputIndex)!!
        // 读取 H.264 码流数据
        muxer.writeSampleData(trackIndex, outputBuffer, bufferInfo)
        mediaCodec.releaseOutputBuffer(outputIndex, false)
    }
}
```

---

## 三、流程图

### 3.1 MediaCodec 硬编码完整流程

```
┌────────────────────────────────────────────────────────────────────┐
│                     MediaCodec 硬编码录制流程                        │
│                                                                    │
│  ┌─────────┐    ┌──────────┐    ┌─────────────┐    ┌────────────┐ │
│  │ Camera  │    │  OpenGL  │    │ MediaCodec  │    │ MediaMuxer │ │
│  │Preview  │───▶│  Surface │───▶│  (Encoder)  │───▶│  (MP4封装) │ │
│  │Texture  │    │  Texture │    │             │    │            │ │
│  └─────────┘    └──────────┘    └─────────────┘    └────────────┘ │
│       │               │               │                   │        │
│       │  onFrameAvail │               │                   │        │
│       │  (OES Texture)│  updateTexImg│                   │        │
│       ▼               ▼               ▼                   ▼        │
│  ┌─────────┐    ┌──────────┐    ┌─────────────┐    ┌────────────┐ │
│  │Surface  │    │EGL Surface│   │ 输入Surface  │    │ 输出.mp4    │ │
│  │Texture  │    │(编码目标) │   │ (零拷贝传递) │    │            │ │
│  └─────────┘    └──────────┘    └─────────────┘    └────────────┘ │
│                                                                    │
│  关键对象创建顺序：                                                  │
│  1. MediaCodec.createEncoderByType("video/avc")                     │
│  2. inputSurface = mediaCodec.createInputSurface()                  │
│  3. EGL: eglCreateWindowSurface(display, config, inputSurface, ...) │
│  4. Camera: camera.setPreviewTexture(surfaceTexture)                │
│  5. MediaMuxer("output.mp4", MUXER_OUTPUT_MPEG_4)                   │
│                                                                    │
│  线程模型：                                                         │
│  ┌──────────────┐    ┌──────────────────┐    ┌─────────────────┐   │
│  │ Camera Thread │    │   GL Render      │    │  Encoder Callback│  │
│  │ (HAL回调)     │───▶│   Thread (EGL)   │───▶│  (内部线程)      │  │
│  └──────────────┘    └──────────────────┘    └─────────────────┘   │
└────────────────────────────────────────────────────────────────────┘
```

### 3.2 软硬编解码选择决策树

```
                        ┌─────────────────────┐
                        │ 编解码需求分析        │
                        └──────────┬──────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
              ┌──────────┐  ┌──────────┐  ┌──────────┐
              │ 实时性要求 │  │ 格式兼容性│  │ 功能需求  │
              └────┬─────┘  └────┬─────┘  └────┬─────┘
                   │             │             │
        ┌──────────┼───┐         │             │
        ▼          ▼   ▼         ▼             ▼
    ┌───────┐  ┌────────┐   ┌────────┐   ┌──────────┐
    │低延迟  │  │实时录制 │   │目标格式 │   │滤镜/字幕  │
    │(<100ms)│  │(Camera) │   │在白名单 │   │高级处理   │
    └───┬───┘  └───┬────┘   └───┬────┘   └────┬─────┘
        │          │            │             │
        ▼          ▼            ▼             ▼
    ┌─────────────────────┐  ┌──────────────────────┐
    │   使用硬编码          │  │   使用软编码           │
    │  (MediaCodec +       │  │  (FFmpeg / x264)      │
    │   Surface 输入)       │  │                       │
    │                      │  │  • 精细码率控制        │
    │  • 功耗低 (<10%CPU)  │  │  • 全格式兼容          │
    │  • 延迟低 (<50ms)    │  │  • 可定制编码参数      │
    │  • 仅支持标准格式    │  │  • 跨平台              │
    │  • 依赖厂商实现      │  │  • CPU/功耗高          │
    └──────────────────────┘  └──────────────────────┘
              │                        │
              └──────────┬─────────────┘
                         ▼
              ┌──────────────────────────┐
              │  混合方案（最优实践）       │
              │                          │
              │  解码: MediaCodec (硬解)  │
              │  处理: OpenGL / GLSL     │
              │  编码: MediaCodec (硬编)  │
              │  封装: MediaMuxer        │
              │                          │
              │  兜底: FFmpeg 处理       │
              │  不支持的格式/功能        │
              └──────────────────────────┘
```

---

## 四、源码分析：MediaCodec.Callback 异步处理

### 4.1 异步回调接口

```kotlin
/**
 * MediaCodec 异步回调处理 —— 推荐用于 Android 5.0+ (API 21+)
 *
 * 优势：不用手动 dequeue，由编解码器内部线程驱动，避免主线程阻塞
 * 注意：回调在 MediaCodec 内部线程执行，不是主线程
 */

class VideoEncoderAsync(private val codecName: String) {

    private var mediaCodec: MediaCodec? = null
    private var muxer: MediaMuxer? = null
    private var trackIndex = -1
    private var muxerStarted = false
    private val encoderLock = Object()

    fun startEncoding(outputPath: String, width: Int, height: Int) {
        // 1. 创建编码器
        mediaCodec = MediaCodec.createByCodecName(codecName)

        // 2. 配置
        val format = MediaFormat.createVideoFormat(
            MediaFormat.MIMETYPE_VIDEO_AVC,
            width, height
        ).apply {
            setInteger(MediaFormat.KEY_COLOR_FORMAT,
                MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface)
            setInteger(MediaFormat.KEY_BIT_RATE, 8_000_000)
            setInteger(MediaFormat.KEY_FRAME_RATE, 30)
            setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1)  // GOP=1s
        }

        mediaCodec?.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)

        // 3. 设置异步回调
        mediaCodec?.setCallback(object : MediaCodec.Callback() {

            /**
             * 输入 Buffer 可用 —— 编码器准备好接收新数据
             * 使用 Surface 输入时不需要处理此回调
             */
            override fun onInputBufferAvailable(
                codec: MediaCodec,
                index: Int
            ) {
                // 当使用 createInputSurface() 时，输入由 Surface 驱动
                // 此回调通常不用于视频编码的 Surface 模式
                // 仅在 ByteBuffer 输入模式下使用：
                // val buffer = codec.getInputBuffer(index)
                // buffer?.put(rawYuvData)
                // codec.queueInputBuffer(index, 0, size, pts, 0)
            }

            /**
             * 输出 Buffer 可用 —— 编码完成了一帧数据
             * 核心回调：获取 H.264 码流并写入 Muxer
             */
            override fun onOutputBufferAvailable(
                codec: MediaCodec,
                index: Int,
                info: MediaCodec.BufferInfo
            ) {
                val outputBuffer = codec.getOutputBuffer(index) ?: return

                when {
                    // 正常编码数据
                    (info.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG) != 0 -> {
                        // SPS/PPS 配置数据
                        // MediaMuxer 不需要手动写入 CSD (Codec Specific Data)
                        // Android 会自动处理
                        codec.releaseOutputBuffer(index, false)
                    }

                    info.size > 0 -> {
                        // 有效编码帧数据
                        synchronized(encoderLock) {
                            if (muxerStarted && muxer != null) {
                                muxer?.writeSampleData(
                                    trackIndex,
                                    outputBuffer,
                                    info
                                )
                            }
                        }
                        codec.releaseOutputBuffer(index, false)
                    }

                    // EOS (End of Stream)
                    (info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0 -> {
                        // 编码结束，停止 Muxer
                        muxer?.stop()
                        muxer?.release()
                        muxer = null
                        codec.releaseOutputBuffer(index, false)
                    }

                    else -> {
                        codec.releaseOutputBuffer(index, false)
                    }
                }
            }

            /**
             * 输出格式变化 —— 编码器的输出格式已确定
             * 典型触发时机：收到第一个 CSD buffer 后
             * 在此处添加 MediaMuxer 的 track
             */
            override fun onOutputFormatChanged(
                codec: MediaCodec,
                format: MediaFormat
            ) {
                synchronized(encoderLock) {
                    // 获取编码器输出格式，添加 Muxer track
                    trackIndex = muxer?.addTrack(format) ?: -1
                    muxer?.start()
                    muxerStarted = true
                }
            }

            /**
             * 错误回调 —— 编码器异常
             */
            override fun onError(
                codec: MediaCodec,
                e: MediaCodec.CodecException
            ) {
                // 处理错误：
                // 1. 可恢复错误 → 重新 start
                // 2. 不可恢复 → release 并重新创建
                when {
                    e.isRecoverable -> codec.start()
                    e.isTransient -> {
                        // 瞬态错误，可能需要重试当前操作
                    }
                    else -> {
                        codec.stop()
                        codec.release()
                        // 触发重建逻辑
                    }
                }
            }
        })

        // 4. 创建 Muxer 并启动编码器
        muxer = MediaMuxer(outputPath, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4)
        mediaCodec?.start()
    }

    /**
     * 获取输入 Surface —— 用于 Camera / OpenGL 输入
     */
    fun getInputSurface(): Surface? {
        return mediaCodec?.createInputSurface()
    }

    /**
     * 发送 EOS 信号
     */
    fun signalEndOfInputStream() {
        mediaCodec?.signalEndOfInputStream()
    }

    fun release() {
        mediaCodec?.stop()
        mediaCodec?.release()
        mediaCodec = null
    }
}
```

### 4.2 同步模式 vs 异步模式代码对比

```kotlin
// ============ 同步模式（API 16+） ============
fun encodeSync() {
    val codec = MediaCodec.createByCodecName("OMX.qcom.video.encoder.avc")
    codec.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
    codec.start()

    val bufferInfo = MediaCodec.BufferInfo()

    while (isEncoding) {
        // 手动轮询输入
        val inIndex = codec.dequeueInputBuffer(TIMEOUT_US)
        if (inIndex >= 0) {
            val buf = codec.getInputBuffer(inIndex)
            buf?.put(rawData)
            codec.queueInputBuffer(inIndex, 0, size, pts, 0)
        }

        // 手动轮询输出
        val outIndex = codec.dequeueOutputBuffer(bufferInfo, TIMEOUT_US)
        when {
            outIndex == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED -> { /* ... */ }
            outIndex >= 0 -> {
                val buf = codec.getOutputBuffer(outIndex)
                // 处理编码数据...
                codec.releaseOutputBuffer(outIndex, false)
            }
        }
    }

    codec.stop()
    codec.release()
}

// ============ 异步模式（API 21+） ============
fun encodeAsync() {
    val codec = MediaCodec.createByCodecName("OMX.qcom.video.encoder.avc")
    codec.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)

    codec.setCallback(object : MediaCodec.Callback() {
        override fun onInputBufferAvailable(codec: MediaCodec, index: Int) {
            val buf = codec.getInputBuffer(index)
            buf?.put(rawData)
            codec.queueInputBuffer(index, 0, size, pts, 0)
        }

        override fun onOutputBufferAvailable(
            codec: MediaCodec,
            index: Int,
            info: MediaCodec.BufferInfo
        ) {
            val buf = codec.getOutputBuffer(index)
            // 处理编码数据...
            codec.releaseOutputBuffer(index, false)
        }

        override fun onOutputFormatChanged(codec: MediaCodec, format: MediaFormat) {
            trackIndex = muxer.addTrack(format)
            muxer.start()
        }

        override fun onError(codec: MediaCodec, e: MediaCodec.CodecException) {
            // 错误处理
        }
    }, Handler(Looper.getMainLooper()))  // 可选：指定回调线程

    codec.start()
}
```

---

## 五、应用场景：视频录制中硬编码 + MediaMuxer 封装 MP4

### 5.1 完整实现方案

```kotlin
/**
 * 视频录制器 —— 硬编码（MediaCodec）+ 封装（MediaMuxer）
 *
 * 场景：录制摄像头视频 + 麦克风音频，输出 MP4 文件
 *
 * 架构：
 *   Camera (SurfaceTexture) → GL Thread (渲染 + 滤镜)
 *       → MediaCodec (视频编码 H.264)
 *       → MediaMuxer (混合封装 MP4)
 *
 *   AudioRecord (PCM) → MediaCodec (音频编码 AAC) → MediaMuxer
 */
class VideoRecorder(
    private val outputPath: String,
    private val width: Int = 1920,
    private val height: Int = 1080
) {
    // 编解码器
    private var videoEncoder: MediaCodec? = null
    private var audioEncoder: MediaCodec? = null
    private var muxer: MediaMuxer? = null

    // Track 索引
    private var videoTrackIndex = -1
    private var audioTrackIndex = -1

    // 音频
    private var audioRecord: AudioRecord? = null
    private val SAMPLE_RATE = 44100
    private val AUDIO_BITRATE = 128_000

    // 状态
    private var isRecording = false
    private var muxerStarted = false

    /**
     * 准备并启动录制
     */
    fun startRecording() {
        // ===== 1. 创建 MediaMuxer =====
        muxer = MediaMuxer(outputPath, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4)

        // ===== 2. 配置视频编码器 =====
        setupVideoEncoder()

        // ===== 3. 配置音频编码器 =====
        setupAudioEncoder()

        // ===== 4. 启动录制线程 =====
        isRecording = true
        startAudioRecording()
    }

    /**
     * 视频编码器配置 —— H.264 硬编码
     */
    private fun setupVideoEncoder() {
        val videoFormat = MediaFormat.createVideoFormat(
            MediaFormat.MIMETYPE_VIDEO_AVC,  // H.264
            width,
            height
        ).apply {
            // 码率策略：VBR（可变码率）通常优于 CBR
            setInteger(MediaFormat.KEY_BIT_RATE, 8_000_000)       // 8 Mbps
            setInteger(MediaFormat.KEY_BITRATE_MODE,
                MediaCodecInfo.EncoderCapabilities.BITRATE_MODE_VBR)
            setInteger(MediaFormat.KEY_FRAME_RATE, 30)             // 30 fps
            setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1)        // 每秒一个 I 帧

            // ColorFormat：使用 Surface 输入（推荐）
            setInteger(MediaFormat.KEY_COLOR_FORMAT,
                MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface)

            // 额外编码参数（部分厂商支持）
            setInteger(MediaFormat.KEY_PROFILE,
                MediaCodecInfo.CodecProfileLevel.AVCProfileHigh)    // High Profile
            setInteger(MediaFormat.KEY_LEVEL,
                MediaCodecInfo.CodecProfileLevel.AVCLevel4)         // Level 4.0
        }

        videoEncoder = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_VIDEO_AVC)
        videoEncoder?.configure(videoFormat, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)

        // 异步回调处理编码输出
        videoEncoder?.setCallback(object : MediaCodec.Callback() {
            override fun onInputBufferAvailable(codec: MediaCodec, index: Int) {
                // Surface 输入模式下不需要处理
            }

            override fun onOutputBufferAvailable(
                codec: MediaCodec,
                index: Int,
                info: MediaCodec.BufferInfo
            ) {
                val buffer = codec.getOutputBuffer(index) ?: return

                if (info.size > 0 && (info.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG) == 0) {
                    // 写入 Muxer（需要同步避免与音频写入冲突）
                    synchronized(muxer!!) {
                        if (muxerStarted && videoTrackIndex >= 0) {
                            buffer.position(info.offset)
                            buffer.limit(info.offset + info.size)
                            muxer?.writeSampleData(videoTrackIndex, buffer, info)
                        }
                    }
                }
                codec.releaseOutputBuffer(index, false)
            }

            override fun onOutputFormatChanged(codec: MediaCodec, format: MediaFormat) {
                synchronized(muxer!!) {
                    videoTrackIndex = muxer?.addTrack(format) ?: -1
                    tryStartMuxer()
                }
            }

            override fun onError(codec: MediaCodec, e: MediaCodec.CodecException) {
                e.printStackTrace()
            }
        })

        videoEncoder?.start()
    }

    /**
     * 获取视频输入 Surface（供 Camera/OpenGL 使用）
     */
    fun getInputSurface(): Surface {
        return videoEncoder!!.createInputSurface()
    }

    /**
     * 音频编码器配置 —— AAC-LC
     */
    private fun setupAudioEncoder() {
        val audioFormat = MediaFormat.createAudioFormat(
            MediaFormat.MIMETYPE_AUDIO_AAC,
            SAMPLE_RATE,
            1  // 单声道（录制场景通常单声道即可）
        ).apply {
            setInteger(MediaFormat.KEY_BIT_RATE, AUDIO_BITRATE)
            setInteger(MediaFormat.KEY_AAC_PROFILE,
                MediaCodecInfo.CodecProfileLevel.AACObjectLC)
            setInteger(MediaFormat.KEY_MAX_INPUT_SIZE, 16384)
        }

        audioEncoder = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_AUDIO_AAC)
        audioEncoder?.configure(audioFormat, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)

        audioEncoder?.setCallback(object : MediaCodec.Callback() {
            override fun onInputBufferAvailable(codec: MediaCodec, index: Int) {
                // 音频 PCM 数据由录制线程填充（在 startAudioRecording 中）
            }

            override fun onOutputBufferAvailable(
                codec: MediaCodec,
                index: Int,
                info: MediaCodec.BufferInfo
            ) {
                val buffer = codec.getOutputBuffer(index) ?: return

                if (info.size > 0 && (info.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG) == 0) {
                    synchronized(muxer!!) {
                        if (muxerStarted && audioTrackIndex >= 0) {
                            muxer?.writeSampleData(audioTrackIndex, buffer, info)
                        }
                    }
                }
                codec.releaseOutputBuffer(index, false)
            }

            override fun onOutputFormatChanged(codec: MediaCodec, format: MediaFormat) {
                synchronized(muxer!!) {
                    audioTrackIndex = muxer?.addTrack(format) ?: -1
                    tryStartMuxer()
                }
            }

            override fun onError(codec: MediaCodec, e: MediaCodec.CodecException) {
                e.printStackTrace()
            }
        })

        audioEncoder?.start()
    }

    /**
     * 启动音频录制线程
     */
    private fun startAudioRecording() {
        val minBufferSize = AudioRecord.getMinBufferSize(
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT
        )

        audioRecord = AudioRecord(
            MediaRecorder.AudioSource.MIC,
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            minBufferSize * 2
        )

        audioRecord?.startRecording()

        thread(name = "AudioEncoder") {
            val pcmBuffer = ByteArray(minBufferSize)
            var totalBytesRead = 0L

            while (isRecording) {
                val bytesRead = audioRecord?.read(pcmBuffer, 0, pcmBuffer.size) ?: 0
                if (bytesRead > 0) {
                    // 获取音频编码器输入 buffer
                    val inputIndex = audioEncoder?.dequeueInputBuffer(10_000) ?: -1
                    if (inputIndex >= 0) {
                        val inputBuffer = audioEncoder?.getInputBuffer(inputIndex)
                        inputBuffer?.clear()
                        inputBuffer?.put(pcmBuffer, 0, bytesRead)

                        val presentationTimeUs = (totalBytesRead * 1_000_000L) /
                                (SAMPLE_RATE * 2)  // 16-bit PCM = 2 bytes/sample

                        audioEncoder?.queueInputBuffer(
                            inputIndex, 0, bytesRead,
                            presentationTimeUs, 0
                        )
                        totalBytesRead += bytesRead
                    }
                }
            }
        }
    }

    /**
     * 尝试启动 Muxer（当视频和音频 track 都准备好时）
     */
    private fun tryStartMuxer() {
        if (!muxerStarted && videoTrackIndex >= 0 && audioTrackIndex >= 0) {
            muxer?.start()
            muxerStarted = true
        }
    }

    /**
     * 停止录制并释放资源
     */
    fun stopRecording() {
        isRecording = false

        // 1. 发送 EOS 并释放编码器
        videoEncoder?.signalEndOfInputStream()
        audioEncoder?.signalEndOfInputStream()

        // 2. 等待编码器处理完 EOS（简单实现：等待一段时间）
        Thread.sleep(500)

        // 3. 释放资源
        audioRecord?.stop()
        audioRecord?.release()
        audioRecord = null

        videoEncoder?.stop()
        videoEncoder?.release()
        videoEncoder = null

        audioEncoder?.stop()
        audioEncoder?.release()
        audioEncoder = null

        muxer?.stop()
        muxer?.release()
        muxer = null
    }
}
```

### 5.2 关键注意事项

| 注意事项 | 详细说明 |
|----------|---------|
| **Muxer 同步** | 音频和视频编码器在不同线程回调，写入 `MediaMuxer.writeSampleData()` 必须加锁同步 |
| **PTS 对齐** | 视频 PTS 以帧率计算（`frameIndex * 1_000_000 / 30`），音频 PTS 以采样数计算，起始时间应一致 |
| **Muxer 启动时机** | 必须在所有 track 添加完成后才能 `muxer.start()`，否则 crash |
| **EOS 处理** | `signalEndOfInputStream()` 后需等待编码器输出 EOS buffer，再释放 Muxer |
| **旋转/方向** | 摄像头预览方向可能旋转，需在 GL 渲染时处理旋转矩阵，或写入 MP4 的旋转 metadata |
| **BufferQueue 满** | 当 Muxer 写入磁盘慢于编码器输出时，BufferQueue 满会导致 `dequeueOutputBuffer` 超时 → 编码掉帧 |

---

## 六、面试速查卡

| 问题 | 一句话答案 |
|------|-----------|
| H.264 vs H.265 | H.265 压缩率高 50%，但复杂度高 2~10 倍，Android 5.0+ 支持 |
| I/P/B 帧 | I=帧内编码(关键帧)、P=前向预测、B=双向预测(压缩率最高) |
| GOP | 两个 I 帧之间的帧组；直播 GOP=1~3s，点播 GOP=2~5s |
| MediaCodec 同步/异步 | 同步手动 dequeue 轮询；异步 setCallback 事件驱动，API 21+ |
| ColorFormat | 推荐 `COLOR_FormatSurface`（零拷贝）；ByteBuffer 用 NV12 |
| AAC Profile | AAC-LC (通用)、HE-AAC (低码率)、AAC-ELD (低延迟通话) |
| 硬编 vs 软编 | 硬编=低功耗低延迟（录制/直播）；软编=高画质可控（转码/编辑） |
| MediaMuxer | 混合音视频 track 封装 MP4；需同步写入、等所有 track 就绪后启动 |

---

## 七、延伸学习

- [MediaCodec 官方文档](https://developer.android.com/reference/android/media/MediaCodec)
- [Android 图形架构 — BufferQueue](https://source.android.com/docs/core/graphics/arch-bq-gralloc)
- [H.264 白皮书 — ITU-T H.264](https://www.itu.int/rec/T-REC-H.264)
- [Grafika — Google 官方 MediaCodec 示例](https://github.com/google/grafika)
- [BigFlake — 视频录制/编辑示例](https://github.com/google/grafika/tree/master/app/src/main/java/com/android/grafika)

---

*最后更新：2026-05-08*
