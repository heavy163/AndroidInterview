# 播放器开发 —— 面试学习完整指南

> **六层递进体系**：面试问题 → 标准答案 → 核心原理 → 流程图 → 源码分析 → 实战场景
> 适用岗位：高级/资深 Android 工程师、音视频播放器开发工程师

---

## 目录

1. [面试高频问题（6+题）](#1-面试高频问题)
2. [标准答案与架构图](#2-标准答案与架构图)
3. [核心原理深度剖析](#3-核心原理深度剖析)
4. [流程图：播放器全链路](#4-流程图播放器全链路)
5. [源码分析：MediaPlayer 状态机 & ExoPlayer Timeline](#5-源码分析mediaplayer-状态机--exoplayer-timeline)
6. [应用场景：短视频无缝切换播放器设计](#6-应用场景短视频无缝切换播放器设计)

---

## 1. 面试高频问题

### Q1: 播放器的整体架构是怎样的？请画出架构图并说明各模块职责

播放器架构从数据输入到最终渲染呈现，通常分为 **解封装 → 解码 → 音视频同步 → 渲染** 四大核心环节。请描述每个环节的技术选型和关键考量。

### Q2: 音视频同步机制是怎么实现的？PTS 和 DTS 分别是什么？说出三种同步策略

播放器如何保证音频和视频在时间上对齐？PTS（显示时间戳）和 DTS（解码时间戳）的区别是什么？主流的三种同步策略（音频为基准、视频为基准、外部时钟）各有什么优劣？

### Q3: 播放器的缓冲策略是怎么设计的？双缓冲和三级缓冲分别适用什么场景？

网络播放中缓冲区的设计直接影响播放流畅度。请说明双缓冲（Decode Buffer + Render Buffer）和三级缓冲（网络缓冲区 → 解码缓冲区 → 渲染缓冲区）的原理和适用场景。

### Q4: Seek 操作的精准度问题是如何解决的？为什么 Seek 总是跳转到关键帧？

调用 `seekTo(position)` 后，播放器为什么总是从最近的 **关键帧（I 帧）** 开始解码，而不是从精确的目标位置开始？如何实现帧级精准 Seek？

### Q5: 播放器状态机包含哪些状态？状态的转换条件是什么？

请描述完整的播放器状态机：从 Idle → Initialized → Prepared → Started → Paused → Stopped → End，以及 PlaybackCompleted 和 Error 状态。每个状态允许哪些操作？非法状态转换会怎样？

### Q6（进阶）: 如果让你从零设计一个短视频播放器（类似抖音），你会如何设计播放器架构？

考虑场景：极速首帧渲染、无缝上下滑动切换、预加载策略、多实例复用、解码器资源管理。

---

## 2. 标准答案与架构图

### Q1: 播放器整体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                       播放器整体架构                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────────┐ │
│  │  Data     │   │  Demuxer │   │ Decoder  │   │   AV Sync &      │ │
│  │  Source   │──▶│ 解封装    │──▶│  解码    │──▶│   Render 渲染    │ │
│  └──────────┘   └──────────┘   └──────────┘   └──────────────────┘ │
│       │              │               │                  │           │
│       ▼              ▼               ▼                  ▼           │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────────┐ │
│  │ File/Net │   │ 分离     │   │ Video    │   │ AudioTrack 输出  │ │
│  │ Stream   │   │ Audio    │   │ Decoder  │   │ SurfaceView     │ │
│  │ Buffer   │   │ Video    │   │ Audio    │   │ TextureView     │ │
│  │          │   │ Subtitle │   │ Decoder  │   │ 或 ANativeWindow │ │
│  └──────────┘   └──────────┘   └──────────┘   └──────────────────┘ │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**各模块职责说明：**

| 模块 | 职责 | 关键技术点 |
|:-----|:-----|:-----------|
| **DataSource** | 数据源抽象层，支持文件/网络/Asset 等多种来源 | `MediaDataSource`、`OkHttpDataSource`、断点续传 |
| **Demuxer 解封装** | 将容器格式（MP4/FLV/TS/MKV）分离为独立的音视频流 | FFmpeg `avformat_open_input` / MediaExtractor |
| **Decoder 解码** | 将压缩的 H.264/H.265/AAC 数据解码为原始 PCM/YUV 帧 | MediaCodec 硬解 / FFmpeg 软解 |
| **AV Sync** | 音视频同步控制，决定每一帧何时渲染 | PTS/DTS 对齐，主时钟选择 |
| **Renderer** | 将原始数据渲染到屏幕/扬声器 | AudioTrack、Surface、OpenGL ES |

**面试加分点：**
- 解封装阶段已获取到每个 packet 的 PTS/DTS 信息，这是后续同步的基础
- 解码器通常采用生产者-消费者模型：解封装线程生产 packet → 解码线程消费并产出 frame
- 渲染层需要处理 **Surface 生命周期**：Surface 被销毁时（切后台）必须释放 `MediaCodec`，重建后重新配置

---

### Q2: 音视频同步的三种策略

#### PTS vs DTS 概念

| 概念 | 全称 | 含义 | 示例 |
|:-----|:-----|:-----|:-----|
| **PTS** | Presentation Time Stamp | **显示时间戳**：该帧应该在什么时间点被渲染到屏幕/扬声器 | 视频帧 PTS=100ms 表示在第 100ms 显示 |
| **DTS** | Decode Time Stamp | **解码时间戳**：该帧应该在什么时间点被送入解码器 | B 帧需要参考前后帧，DTS < PTS |

**为什么存在 PTS ≠ DTS？** 因为 B 帧（双向预测帧）的存在。B 帧解码需要依赖前后的 I/P 帧，所以解码顺序 ≠ 显示顺序：

```
显示顺序:  I(0)  B(1)  B(2)  P(3)  B(4)  B(5)  P(6)
解码顺序:  I(0)  P(3)  B(1)  B(2)  P(6)  B(4)  B(5)
              ↑ PTS(0)=DTS(0)    ↑ PTS(1)≠DTS(1)
```

#### 三种音视频同步策略

| 策略 | 原理 | 优点 | 缺点 | 适用场景 |
|:-----|:-----|:-----|:-----|:---------|
| **音频为主时钟** | 音频匀速播放，视频根据音频时钟调整 | 体验最好，音频卡顿比视频卡顿更敏感 | 音频流必须存在且连续 | **绝大多数播放器**（ExoPlayer、ijkplayer 默认） |
| **视频为主时钟** | 视频匀速渲染，音频根据视频时钟调整 | 无音频流时自然选择 | 音频可能出现杂音/断断续续 | 无音频的视频、监控播放 |
| **外部时钟** | 系统时间作为时钟基准，音视频都同步到系统时钟 | 独立于流本身 | 音视频都可能出现抖动 | 需要精确系统时间对齐的场景 |

**同步算法核心逻辑（伪代码）：**

```cpp
// 以音频为基准：视频同步到音频时钟
void sync_video_to_audio(VideoFrame *frame, int64_t audio_clock) {
    int64_t delay = frame->pts - audio_clock;  // 视频帧显示时间 vs 音频当前时间

    if (delay > AV_SYNC_THRESHOLD_MAX) {
        // 视频超前：延长当前帧显示时间（sleep）
        usleep((delay - AV_SYNC_THRESHOLD) * 1000);
    } else if (delay < AV_SYNC_THRESHOLD_MIN) {
        // 视频落后：丢弃当前帧，直接取下一帧
        drop_frame(frame);
    } else {
        // 在阈值内：正常渲染
        render_frame(frame);
    }
}
```

**同步阈值经验值：**
- 视频超前 > 100ms：等待 （sleep 差值）
- 视频落后 > 10ms：丢帧
- ±10ms 内：视为同步，正常渲染

---

### Q3: 缓冲策略

#### 双缓冲模型

```
┌─────────────────────────────────────────────────┐
│  网络线程              解码线程        渲染线程  │
│  ┌────────┐   packet   ┌────────┐  frame ┌────┐ │
│  │ Network │──────────▶│Decode  │──────▶│Rend│ │
│  │ Buffer  │           │ Buffer │       │Buf │ │
│  └────────┘           └────────┘       └────┘ │
│    (环形)              (队列)          (队列)   │
└─────────────────────────────────────────────────┘
```

- **Decode Buffer**：存放解码后的 frame（Video: YUV 帧，Audio: PCM 帧），大小通常 3~5 帧
- **Render Buffer**：已排序待渲染帧，通常只需 1~2 帧

#### 三级缓冲模型（网络播放专用）

```
┌───────────┐      ┌───────────┐      ┌───────────┐      ┌───────────┐
│ Network   │ ───▶ │ Jitter     │ ───▶ │ Decode    │ ───▶ │ Render    │
│ Download  │      │ Buffer     │      │ Buffer    │      │ Buffer    │
│           │      │ (去抖动)    │      │           │      │           │
└───────────┘      └───────────┘      └───────────┘      └───────────┘
    原始TS包       缓冲2~5秒数据       帧级缓冲            渲染输出
```

**缓冲水位控制（关键概念）：**

```
        高水位 ─────────────────────  暂停下载（避免OOM）
              │████████████████████│
              │    安全区间         │
        低水位 ─────────────────────  恢复下载（避免卡顿）
              │                    │
              └────────────────────┘
```

| 参数 | 典型值 | 说明 |
|:-----|:------|:-----|
| **低水位** | 1~2 秒 | 低于此值恢复下载/解码 |
| **高水位** | 5~10 秒 | 高于此值暂停下载/解码 |
| **初始缓冲** | 2~3 秒 | 起播前至少缓冲的量 |

---

### Q4: Seek 精准度与关键帧

**问题本质：** GOP（Group of Pictures）结构决定了只有 I 帧可以独立解码。当 Seek 到非关键帧位置时，解码器必须从最近的 I 帧开始解码，然后跳过中间的 P/B 帧直到目标位置。

```
GOP 结构： I₀  B₁  B₂  P₃  B₄  B₅  P₆  B₇  B₈  I₉
                             ↑ Seek to here (P₃)
实际解码： I₀ → P₃ (解码但不渲染 B₁B₂, 直到 P₃ 才渲染)
```

**解决方案：**

1. **缩短 GOP 长度**：GOP=1s（30 帧内必有一个 I 帧），最多偏差 1s
2. **插入额外 I 帧**：Seek 请求时，在目标位置附近编码一个 I 帧（需转码支持）
3. **帧级缓存**：服务器端存储所有帧的解码快照（存储成本高）
4. **容忍策略**：Seek 后从最近的 I 帧解码，播到目标位置前不渲染（静默解码），用户感知延迟极小

---

### Q5: 播放器状态机

```
                              ┌──────────┐
                              │  Error   │  (任何状态发生错误)
                              └──────────┘
                                    ▲
                                    │ error
        ┌───────────────────────────────────────────────────┐
        │               MediaPlayer 状态机                    │
        │                                                   │
        │   ┌──────┐  setDataSource  ┌─────────────┐       │
        │   │ Idle │───────────────▶│ Initialized │       │
        │   └──────┘                └──────┬──────┘       │
        │       ▲                          │ prepare()     │
        │       │ reset()                  │ prepareAsync()│
        │       │                          ▼               │
        │   ┌──────┐  stop()       ┌───────────┐          │
        │   │Stopped│◀────────────│ Prepared  │          │
        │   └──────┘              └─────┬─────┘          │
        │       ▲                       │ start()         │
        │       │ stop()          ┌─────▼─────┐          │
        │       │                 │  Started  │          │
        │       │                 └─────┬─────┘          │
        │       │        pause()  ┌─────▼─────┐          │
        │       │                 │  Paused   │          │
        │       │                 └─────┬─────┘          │
        │       │          start()      │                 │
        │       │                 ┌─────▼─────┐          │
        │       │                 │  Started  │          │
        │       │                 └─────┬─────┘          │
        │       │  播放完成              │                 │
        │       │                 ┌─────▼─────┐          │
        │       │                 │Playback   │          │
        │       │                 │Completed  │          │
        │       │                 └───────────┘          │
        └───────────────────────────────────────────────────┘
```

**状态转换规则表：**

| 当前状态 | 允许操作 | 目标状态 | 非法操作示例 |
|:---------|:---------|:---------|:------------|
| **Idle** | `setDataSource()` | Initialized | 直接 `start()` → 抛异常 |
| **Initialized** | `prepare()` / `prepareAsync()` | Prepared | 再次 `setDataSource()` → 非法状态 |
| **Prepared** | `start()`, `seekTo()` | Started | - |
| **Started** | `pause()`, `stop()`, `seekTo()` | Paused/Stopped | - |
| **Paused** | `start()` | Started | - |
| **Stopped** | `prepare()` / `reset()` | Prepared / Idle | 直接 `start()` 需要先 prepare |
| **PlaybackCompleted** | `start()` (重播), `stop()` | Started / Stopped | - |
| **Error** | `reset()` | Idle | 几乎一切操作都是非法的 |

**面试加分点：**
- `prepare()` 是同步阻塞操作，`prepareAsync()` 是异步操作，在主线程调用 `prepare()` 会导致 ANR
- `reset()` 使播放器回到 Idle 状态（复用播放器实例），`release()` 则彻底释放资源（播放器不再可用）
- Error 状态后必须调用 `reset()` 才能恢复，否则所有操作都会抛 `IllegalStateException`

---

## 3. 核心原理深度剖析

### 3.1 PTS/DTS 的生成与传递链路

```
编码端                         容器封装                   解码端
┌─────────────┐          ┌──────────────┐         ┌──────────────┐
│ 原始YUV帧    │          │ MP4/FLV/TS   │         │ demuxer 输出 │
│ timestamp=Ts│─────────▶│ 写入PTS/DTS  │────────▶│ PTS/DTS 透传 │
└─────────────┘          └──────────────┘         └──────┬───────┘
                                                         │
                                                    ┌────▼───────┐
                                                    │ Decoder    │
                                                    │ 输出frame  │
                                                    │ 附PTS值    │
                                                    └────┬───────┘
                                                         │
                                                    ┌────▼───────┐
                                                    │ AV Sync    │
                                                    │ 比较PTS &  │
                                                    │ 主时钟     │
                                                    └────────────┘
```

**时间基（Time Base）转换：**

```
PTS 实际值(秒) = PTS × time_base

例如：time_base = 1/90000，PTS = 360000
实际时间 = 360000 × (1/90000) = 4 秒
```

不同容器的 time_base 不同：MP4 通常 `1/90000`，TS 流通常 `1/90000`，FLV 通常 `1/1000`。播放器需要在解封装后统一转换到毫秒/微秒单位。

### 3.2 音频为主时钟的同步详解

```
音频时间线（匀速推进）：
├─────────┼─────────┼─────────┼─────────┤
0ms      40ms      80ms     120ms     160ms

视频帧 PTS 对比：
Frame0(PTS=0)     → 准时渲染      ✓
Frame1(PTS=38ms)  → delay=-2ms    → 等待2ms后渲染
Frame2(PTS=85ms)  → delay=+5ms    → 已落后，丢帧
Frame3(PTS=120ms) → delay=-5ms    → 在阈值内，渲染
```

**音频时钟的获取方式：**

```cpp
// 音频时钟 = 已写入 AudioTrack 的数据量 / 采样率
int64_t get_audio_clock() {
    // framesWritten: AudioTrack 已写入的总帧数
    // sampleRate: 如 44100
    // 返回值单位：微秒
    return (framesWritten * 1000000LL) / sampleRate;
}
```

### 3.3 缓冲水位控制原理

```
                      播放进度
                         ↓
┌────────────────────────────────────────────────────┐
│  已播放  │  缓冲中  │   未下载     │
│          │██████████│             │
└────────────────────────────────────────────────────┘
           ↑          ↑
      低水位(2s)   高水位(10s)

缓冲时长 = 最大PTS - 当前播放PTS

if (缓冲时长 < LOW_WATER_MARK) {
    恢复下载 / 恢复解码
} else if (缓冲时长 > HIGH_WATER_MARK) {
    暂停下载 / 暂停解码 （等待播放消耗）
}
```

---

## 4. 流程图：播放器全链路

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     播放器全链路数据流                                     │
└──────────────────────────────────────────────────────────────────────────┘

  ┌──────────┐
  │ 1. 打开   │  DataSource.open(url/file)
  │ 数据源    │  ── 建立网络连接或打开文件描述符
  └────┬─────┘
       │ 字节流 (byte stream)
       ▼
  ┌──────────┐
  │ 2. 解封装 │  MediaExtractor / avformat
  │ Demuxer  │  ── 解析容器头，获取 track 信息
  │          │  ── 循环读取 packet（含 PTS/DTS/Flags）
  └────┬─────┘
       │ packet 队列 (video_packet_queue / audio_packet_queue)
       ▼
  ┌──────────────────────────────────────────────┐
  │ 3. 解码 (并行)                               │
  │                                              │
  │  ┌─────────────┐    ┌─────────────┐         │
  │  │Video Decoder│    │Audio Decoder│         │
  │  │ MediaCodec  │    │ MediaCodec  │         │
  │  │ H.264→YUV   │    │ AAC→PCM     │         │
  │  └──────┬──────┘    └──────┬──────┘         │
  └─────────┼──────────────────┼────────────────┘
            │ frame 队列       │ frame 队列
            ▼                  ▼
  ┌──────────────────────────────────────────────┐
  │ 4. 音视频同步                                │
  │                                              │
  │   音频为主时钟 ─────────────────────┐         │
  │   audio_clock = writtenFrames / SR │         │
  │                                    │         │
  │   视频帧 PTS vs audio_clock:       │         │
  │   ├─ delay < -10ms → 丢帧         │         │
  │   ├─ delay > +100ms → sleep       │         │
  │   └─ |delay| ≤ 10ms → 渲染        │         │
  └─────────┬──────────────────┬────────────────┘
            │                  │
            ▼                  ▼
  ┌──────────────┐   ┌──────────────────┐
  │ 5a. 视频渲染  │   │ 5b. 音频渲染     │
  │ Surface/     │   │ AudioTrack       │
  │ OpenGL ES    │   │ write(PCM data)  │
  │ (ANative     │   │ 阻塞写入直到     │
  │  Window)     │   │ buffer 可用      │
  └──────────────┘   └──────────────────┘
```

**关键线程分工：**

| 线程 | 职责 | 常见数量 |
|:-----|:-----|:--------|
| **Demuxer Thread** | 读取数据源，解封装，分发 packet 到各解码队列 | 1 |
| **Video Decode Thread** | 从 video_packet_queue 取 packet，调用解码器，输出 frame | 1 |
| **Audio Decode Thread** | 从 audio_packet_queue 取 packet，调用解码器，输出 frame | 1 |
| **Video Render Thread** | 按同步策略渲染视频帧到 Surface | 1 |
| **Audio Render Thread** | AudioTrack 内部回调线程，自动从 audio_frame_queue 取数据 | AudioTrack 内部管理 |

---

## 5. 源码分析：MediaPlayer 状态机 & ExoPlayer Timeline

### 5.1 MediaPlayer 状态机源码（Android Framework）

`MediaPlayer.java` 的状态检查核心逻辑：

```java
// frameworks/base/media/java/android/media/MediaPlayer.java (简化)

public class MediaPlayer {
    // 状态常量
    private static final int IDLE = 0;
    private static final int INITIALIZED = 1;
    private static final int PREPARING = 2;
    private static final int PREPARED = 3;
    private static final int STARTED = 4;
    private static final int PAUSED = 5;
    private static final int STOPPED = 6;
    private static final int PLAYBACK_COMPLETE = 7;
    private static final int END = 8;
    private static final int ERROR = 9;

    private int mState = IDLE;

    // 状态合法性检查（每个方法入口都会调用）
    private void stayAwake(boolean awake) {
        // 该方法名有误导性，实际是状态检查
        if (mState == ERROR) {
            throw new IllegalStateException("MediaPlayer in error state");
        }
    }

    public void setDataSource(String path) {
        stayAwake(false); // IDLE / STOPPED 状态合法
        // ... JNI 调用 native_setDataSource
        mState = INITIALIZED;
    }

    public void prepare() throws IOException {
        stayAwake(false);
        if (mState != INITIALIZED && mState != STOPPED) {
            throw new IllegalStateException("Can't prepare in state: " + mState);
        }
        // ... 阻塞等待 prepare 完成
        mState = PREPARED;
    }

    public void start() {
        stayAwake(false);
        if (isPlaying()) return; // 幂等
        if (mState == PREPARED || mState == PAUSED || mState == PLAYBACK_COMPLETE) {
            // ... JNI 调用 native_start
            mState = STARTED;
        }
    }

    public void pause() {
        stayAwake(false);
        if (mState == STARTED || mState == PAUSED || mState == PLAYBACK_COMPLETE) {
            // ... JNI 调用 native_pause
            mState = PAUSED;
        }
    }

    public void stop() {
        stayAwake(false);
        if (mState == PREPARED || mState == STARTED || mState == STOPPED
                || mState == PAUSED || mState == PLAYBACK_COMPLETE) {
            // ... JNI 调用 native_stop
            mState = STOPPED;
        }
    }

    public void reset() {
        // reset 几乎可以从任何状态调用
        // ... 释放 native 资源
        mState = IDLE;
    }

    public void release() {
        // 彻底释放，此后对象不可用
        mState = END;
    }
}
```

**JNI 层的状态检查：**

```cpp
// frameworks/base/media/jni/android_media_MediaPlayer.cpp
static void
android_media_MediaPlayer_start(JNIEnv *env, jobject thiz)
{
    sp<MediaPlayer> mp = getMediaPlayer(env, thiz);
    if (mp == NULL) {
        jniThrowException(env, "java/lang/IllegalStateException", NULL);
        return;
    }
    process_media_player_call(env, thiz, mp->start(), NULL, NULL);
}
```

**面试解读要点：**
- Java 层状态检查是防御性的"第一道防线"，Native 层还有第二道检查
- 状态机保证了播放器 API 的线程安全性（虽不完美，但约定必须按顺序调用）
- `stayAwake` 方法名是历史遗留，实际语义是"断言当前状态不是 Error"

### 5.2 ExoPlayer Timeline 机制

ExoPlayer 抽象出 `Timeline` 概念来描述播放列表结构，这是它相比 MediaPlayer 的核心优势之一：

```
Timeline 结构：

Timeline
  └── Window (播放窗口)
        ├── Period (播放时段)
        │     ├── 一个 Period 可以包含多个 AdGroup (广告组)
        │     └── Period 内部有独立的 media source
        └── Window 可能包含多个 Period（多段视频拼接）
```

**核心类关系：**

```java
// Timeline 抽象类
public abstract class Timeline {
    public abstract int getWindowCount();
    public abstract Window getWindow(int windowIndex, Window window, long defaultPositionProjectionUs);
    public abstract int getPeriodCount();
    public abstract Period getPeriod(int periodIndex, Period period, boolean setIds);

    // Window 描述一个播放窗口的元数据
    public static final class Window {
        public long durationUs;              // 总时长
        public long positionInFirstPeriodUs; // 首 Period 起始偏移
        public boolean isDynamic;            // 是否是直播流
        public boolean isSeekable;           // 是否可 Seek
        public Object tag;                   // 自定义标签
    }

    // Period 描述一个播放时段
    public static final class Period {
        public Object uid;           // 唯一标识
        public long durationUs;      // 时长
        public long positionInWindowUs; // 在 Window 中的偏移
        public List<AdPlaybackState> adPlaybackStates; // 广告状态
    }
}
```

**Timeline 更新流程（直播场景）：**

```
直播流 Manifest 刷新
        │
        ▼
  MediaSource.refresh()
        │
        ▼
  Timeline 更新 (新 Window/Period 附加到末尾)
        │
        ▼
  Player.Listener.onTimelineChanged(Timeline timeline, int reason)
        │
        ▼
  UI 更新进度条范围、时长显示
```

**面试解读要点：**
- `Timeline` 将播放列表建模为 `Window → Period` 的层级结构，支持单视频、播放列表、直播、广告插入等多种场景
- `Period` 可以有不同的 `MediaSource`，意味着无缝拼接不同来源的视频
- 直播场景 Timeline 是 `isDynamic=true`，窗口会不断增长
- 广告插入通过 `AdPlaybackState` 管理，在 Period 内插入广告且不计入主内容时长

---

## 6. 应用场景：短视频无缝切换播放器设计

### 场景需求分析

类似抖音的短视频 Feed 流场景：
- 上下滑动切换视频，切换延迟 < 100ms
- 首帧渲染速度 < 200ms
- 无缝循环播放
- 预加载上一/下一个视频
- 多实例复用，控制解码器数量（Android 硬解码器有限，通常 6~8 个）

### 设计方案：播放器池 + 预加载队列

```
┌─────────────────────────────────────────────────────────────┐
│                  短视频播放器架构                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                 │
│  │ Player A │  │ Player B │  │ Player C │  播放器池(3实例) │
│  │ (上一视频) │  │ (当前视频) │  │ (下一视频) │                │
│  └──────────┘  └──────────┘  └──────────┘                 │
│       ↑              ↑              ↑                       │
│       │              │              │                       │
│  ┌────────────────────────────────────────┐                │
│  │         预加载队列 (PreloadQueue)       │                │
│  │  [pos-2] [pos-1] [pos] [pos+1] [pos+2]│                │
│  └────────────────────────────────────────┘                │
│                                                             │
│  RecyclerView / ViewPager2                                  │
│  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐                         │
│  │Item │ │Item │ │Item │ │Item │ ← 每个 item 绑定一个      │
│  │ -1  │ │  0  │ │ +1  │ │ +2  │   Surface/TextureView    │
│  └─────┘ └─────┘ └─────┘ └─────┘                         │
└─────────────────────────────────────────────────────────────┘
```

### 核心实现策略

**1. 播放器池管理：**

```kotlin
class VideoPlayerPool(private val maxSize: Int = 3) {
    private val availablePlayers = LinkedList<ExoPlayer>()
    private val inUsePlayers = mutableMapOf<String, ExoPlayer>()

    fun acquire(videoId: String): ExoPlayer {
        return if (availablePlayers.isNotEmpty()) {
            availablePlayers.poll()!!.also { inUsePlayers[videoId] = it }
        } else {
            createNewPlayer().also { inUsePlayers[videoId] = it }
        }
    }

    fun release(videoId: String) {
        inUsePlayers.remove(videoId)?.let { player ->
            player.stop()
            player.clearMediaItems()
            if (availablePlayers.size < maxSize) {
                availablePlayers.offer(player)  // 回收到池中
            } else {
                player.release()                // 超过池大小则彻底释放
            }
        }
    }
}
```

**2. 无缝切换流程：**

```
用户滑动 (视频 A → 视频 B)
        │
        ├─ 1. Player B 已预加载并 prepare 完成（处于 Prepared 状态）
        │
        ├─ 2. Surface 切换：将 Player B 的 surface 绑定到当前可见的 TextureView
        │     playerB.setSurface(surface)
        │
        ├─ 3. Player B.start() （首帧几乎立即渲染，因为已 Prepared）
        │
        ├─ 4. Player A.pause()  →  delay 200ms →  Player A.stop()
        │     延迟停止避免声音突然中断带来的不适感
        │
        └─ 5. 预加载 pos+1 的视频到 Player C
```

**3. 首帧优化策略：**

| 优化手段 | 说明 |
|:---------|:-----|
| **预播放** | 提前 prepare 上一个/下一个视频，切换时直接 start |
| **GOP 对齐** | 服务端转码时 GOP 设为 1s，且 I 帧放在视频开头 |
| **硬解优先** | 优先使用 MediaCodec 硬解，首帧出帧速度快于软解 |
| **Surface 预绑定** | 提前 `setSurface()` 避免等待 Surface 创建 |
| **CDN 预热** | 根据用户行为预测下一视频，提前建立连接和缓冲 |
| **Moov atom 前置** | MP4 的 moov 元数据在文件开头（faststart），避免等待尾部数据 |

**4. 内存与解码器管理：**

- Android 设备硬解码器数量有限（通常 6~8 个），播放器池上限 = min(3, 硬解码器数/2)
- 不可见视频保持在 Prepared 状态（解码器已配置但未解码），而非 Started 状态（持续解码消耗资源）
- 收到内存警告时，立即 release 预加载但不可见的播放器

---

## 总结

播放器开发是音视频领域最难也是最重要的模块。面试中需要重点掌握：

1. **架构设计**：解封装 → 解码 → 同步 → 渲染 的四层模型
2. **同步机制**：PTS/DTS 区别，三种同步策略，音频为主时钟的实现细节
3. **缓冲策略**：双缓冲/三级缓冲的区别，水位控制
4. **状态机**：MediaPlayer 7 个关键状态及其转换规则
5. **Seek 原理**：关键帧限制与解决方案
6. **实战能力**：短视频无缝切换的播放器池设计

> 💡 **面试技巧**：当被问到播放器相关问题时，先从架构层面回答（四层模型），再深入具体细节，展示系统性思维。如果能结合 ExoPlayer 源码或实际项目经验，加分更多。
