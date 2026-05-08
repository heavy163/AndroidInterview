# ExoPlayer 面试学习完整指南

> **六层递进体系**：面试问题 → 标准答案 → 核心原理 → 流程图 → 源码分析 → 实战场景
> 适用岗位：高级/资深 Android 工程师、音视频开发工程师

---

## 目录

1. [面试高频问题（6题）](#1-面试高频问题)
2. [标准答案与架构图](#2-标准答案与架构图)
3. [核心原理深度剖析](#3-核心原理深度剖析)
4. [流程图：ExoPlayer 播放数据流](#4-流程图exoplayer-播放数据流)
5. [源码分析：核心组件实现](#5-源码分析核心组件实现)
6. [应用场景：自定义 ExoPlayer 实现缓存策略（边下边播）](#6-应用场景自定义-exoplayer-实现缓存策略边下边播)

---

## 1. 面试高频问题

### Q1: ExoPlayer 的整体架构是怎样的？请画出架构图并说明 Timeline / MediaSource / Renderer / TrackSelector 的职责

ExoPlayer 采用高度模块化的架构设计，核心组件包括 Timeline（播放列表模型）、MediaSource（媒体数据源）、Renderer（渲染器）和 TrackSelector（轨道选择器）。请详细说明各组件的职责及其协作关系，并画出架构图。

### Q2: ExoPlayer 与 Android 原生 MediaPlayer 的核心区别是什么？在什么场景下应该选择 ExoPlayer？

从架构设计、扩展性、格式支持、DRM 能力、自定义能力、网络自适应等多个维度对比分析。为什么 ExoPlayer 已经成为 Android 官方推荐的播放器？

### Q3: 如何自定义 ExoPlayer 的 DataSource 和 Renderer？请说明扩展机制

ExoPlayer 的扩展性是其核心竞争力之一。如何实现自定义的 DataSource（如加密流媒体数据源）？如何实现自定义 Renderer（如特效渲染器）？扩展点有哪些？

### Q4: ExoPlayer 如何支持 DRM 内容播放？Widevine 的集成流程是怎样的？

DRM（Digital Rights Management）是在线视频平台的核心需求。ExoPlayer 如何集成 Widevine Modular DRM？DrmSessionManager 的工作原理是什么？在线获取许可证（License）的流程是怎样的？

### Q5: ExoPlayer 的离线下载和缓存机制是如何实现的？DownloadManager 的工作原理是什么？

视频离线缓存是移动端播放器的重要功能。ExoPlayer 的 DownloadManager 如何管理下载任务？DownloadTracker 如何跟踪离线内容状态？下载的媒体文件如何存储和索引？

### Q6（进阶）: 如果让你基于 ExoPlayer 实现一个"边下边播"的自定义缓存策略，你会如何设计？

考虑场景：用户观看视频时，如何将已播放部分的媒体数据缓存到本地，以便下次播放时直接从缓存加载？如何设计缓存淘汰策略（如 LRU）？如何处理 DASH/HLS 自适应流的缓存？

---

## 2. 标准答案与架构图

### Q1: ExoPlayer 整体架构

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           ExoPlayer 核心架构                                  │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      ExoPlayer (Player Facade)                       │    │
│  │  getPlayWhenReady() / seekTo() / getCurrentPosition() / setMediaSource│   │
│  └────────────────────────────────┬────────────────────────────────────┘    │
│                                   │                                          │
│  ┌────────────────────────────────┼────────────────────────────────────┐    │
│  │                       MediaSourceFactory                             │    │
│  │  ProgressiveMediaSource / DashMediaSource / HlsMediaSource / SsMediaSource│
│  └────────────────────────────────┬────────────────────────────────────┘    │
│                                   │                                          │
│  ┌────────────────────────────────▼────────────────────────────────────┐    │
│  │                          Timeline                                     │    │
│  │  ┌─────────────────────────────────────────────────────────────────┐ │    │
│  │  │ Window[0]          Window[1]          Window[2]                 │ │    │
│  │  │ ┌─────────────┐   ┌─────────────┐   ┌─────────────┐            │ │    │
│  │  │ │ Period[0]   │   │ Period[0]   │   │ Period[0]   │            │ │    │
│  │  │ │  durationUs │   │  durationUs │   │  durationUs │            │ │    │
│  │  │ │  uid         │   │  uid         │   │  uid         │            │ │    │
│  │  │ └─────────────┘   └─────────────┘   └─────────────┘            │ │    │
│  │  └─────────────────────────────────────────────────────────────────┘ │    │
│  └────────────────────────────────┬────────────────────────────────────┘    │
│                                   │                                          │
│  ┌────────────────────────────────▼────────────────────────────────────┐    │
│  │                       TrackSelector                                  │    │
│  │  ┌──────────────────────────────────────────────────────────────┐   │    │
│  │  │  DefaultTrackSelector / MappingTrackSelector                  │   │    │
│  │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐    │   │    │
│  │  │  │ Video    │ │ Audio    │ │ Text     │ │ Metadata     │    │   │    │
│  │  │  │ TrackGrp │ │ TrackGrp │ │ TrackGrp │ │ TrackGrp     │    │   │    │
│  │  │  │ 1024×720 │ │ en-128k  │ │ en       │ │ ID3          │    │   │    │
│  │  │  │ 1920×1080│ │ en-256k  │ │ zh       │ │ EMSG         │    │   │    │
│  │  │  │ 3840×2160│ │ de-128k  │ │ ja       │ │              │    │   │    │
│  │  │  └──────────┘ └──────────┘ └──────────┘ └──────────────┘    │   │    │
│  │  └──────────────────────────────────────────────────────────────┘   │    │
│  └────────────────────────────────┬────────────────────────────────────┘    │
│                                   │                                          │
│  ┌────────────────────────────────▼────────────────────────────────────┐    │
│  │                        LoadControl                                    │    │
│  │  DefaultLoadControl: minBufferMs / maxBufferMs / bufferForPlaybackMs │    │
│  │  shouldContinueLoading() / shouldStartPlayback()                     │    │
│  └────────────────────────────────┬────────────────────────────────────┘    │
│                                   │                                          │
│  ┌────────────────────────────────▼────────────────────────────────────┐    │
│  │                          Renderers                                    │    │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌─────────────┐ │    │
│  │  │ MediaCodec   │ │ MediaCodec   │ │ TextRenderer │ │ Metadata    │ │    │
│  │  │ VideoRenderer│ │ AudioRenderer│ │ (Subtitle)   │ │ Renderer    │ │    │
│  │  │ → Surface    │ │ → AudioTrack │ │ → Canvas     │ │ → Callback  │ │    │
│  │  └──────────────┘ └──────────────┘ └──────────────┘ └─────────────┘ │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

**各组件职责说明：**

| 组件 | 职责 | 关键技术细节 |
|:-----|:-----|:-----------|
| **Timeline** | 描述媒体播放列表的结构模型，包含 Window 和 Period 两级抽象 | 单个媒体文件对应一个 Window 下的一个 Period；多广告插入对应一个 Window 下多个 Period；播放列表对应多个 Window |
| **MediaSource** | 负责根据 Timeline 结构提供实际的媒体数据（MediaPeriod） | `ProgressiveMediaSource`（MP4/FLV 等）、`DashMediaSource`、`HlsMediaSource`、`SsMediaSource`（SmoothStreaming） |
| **TrackSelector** | 从 MediaSource 暴露的 TrackGroup 中选择合适的音视频轨道 | `DefaultTrackSelector` 支持根据分辨率、码率、语言等参数自动选择；可自定义 `TrackSelector.Parameters` |
| **Renderer** | 消费 SampleStream 中的压缩数据，解码并渲染 | `MediaCodecVideoRenderer`（视频硬解码）、`MediaCodecAudioRenderer`（音频硬解码）、`TextRenderer`（字幕渲染） |
| **LoadControl** | 控制播放器缓冲策略，决定何时开始加载、何时开始播放 | 三个关键方法：`shouldContinueLoading()`、`shouldStartPlayback()`、`getBackBufferDurationUs()` |

### Q2: ExoPlayer vs MediaPlayer 对比

| 对比维度 | ExoPlayer | MediaPlayer |
|:---------|:----------|:------------|
| **架构设计** | 高度模块化，组件可替换 | 单体设计，黑盒封装 |
| **扩展性** | 支持自定义 DataSource、Extractor、Renderer、TrackSelector | 几乎无法扩展，仅暴露有限回调 |
| **流媒体支持** | 原生支持 DASH（MPEG-DASH）、HLS、SmoothStreaming | 仅基础 HTTP 渐进式下载 |
| **DRM 支持** | Framework 和自定义 DRM，支持 Widevine Modular/Classic | 仅 Framework 层 DRM |
| **自适应码率** | 内置 ABR（Adaptive Bitrate）算法 | 不支持 |
| **离线下载** | 内置 DownloadManager，支持下载 DRM 内容 | 不支持 |
| **字幕支持** | 内置 WebVTT、TTML、SSA/ASS 字幕渲染 | API 33+ 支持有限 |
| **广告插入** | 通过多 Period Timeline 天然支持 | 不支持 |
| **代码透明度** | 完全开源（Apache 2.0） | 部分开源，Framework 层封装 |
| **更新频率** | 独立发布，快速迭代 | 随 Android 系统版本更新 |
| **首帧时间** | 可精细化控制，自定义 LoadControl | 黑盒不可控 |
| **音频焦点** | 需自行管理 | 自动管理 |

**选择建议：**
- **必须选 ExoPlayer**：需要 DASH/HLS 自适应流、DRM 内容、离线缓存、自定义播放器 UI、广告插入
- **可用 MediaPlayer**：极简播放需求（仅播放本地 MP4 文件），不需要扩展

### Q3: 自定义 DataSource 与 Renderer 扩展机制

**自定义 DataSource：**

```java
// 自定义加密流媒体 DataSource
public class EncryptedDataSource extends BaseDataSource {
    private final DataSource upstream;
    private Cipher cipher;

    public EncryptedDataSource(DataSource upstream, byte[] key) {
        this.upstream = upstream;
        this.cipher = new CipherInputStream(upstream.open(), getCipher(key));
    }

    @Override
    public long open(DataSpec dataSpec) throws IOException {
        // 解密逻辑：对原始数据进行 AES 解密
        return cipher.open(dataSpec);
    }

    @Override
    public int read(byte[] buffer, int offset, int length) throws IOException {
        return cipher.read(buffer, offset, length);
    }

    @Override
    public void close() throws IOException {
        cipher.close();
    }
}

// 使用自定义 DataSource
DataSource.Factory factory = () -> new EncryptedDataSource(
    new DefaultHttpDataSource.Factory().createDataSource(),
    encryptionKey
);
ProgressiveMediaSource mediaSource = new ProgressiveMediaSource.Factory(factory)
    .createMediaSource(MediaItem.fromUri(videoUri));
```

**自定义 Renderer（视频特效渲染器）：**

```java
public class EffectVideoRenderer extends MediaCodecVideoRenderer {
    private final EffectShaderProgram shaderProgram;

    public EffectVideoRenderer(Context context, EffectShaderProgram shader) {
        super(context, MediaCodecSelector.DEFAULT);
        this.shaderProgram = shader;
    }

    @Override
    protected void renderOutputBufferV21(
            Codec.DecoderOutputBuffer buffer,
            long presentationTimeUs,
            long releaseTimeNs) {
        // 在渲染前应用 OpenGL 特效（如滤镜、美颜）
        shaderProgram.apply();
        super.renderOutputBufferV21(buffer, presentationTimeUs, releaseTimeNs);
        shaderProgram.release();
    }
}

// 注册到 ExoPlayer
ExoPlayer player = new ExoPlayer.Builder(context)
    .setRenderersFactory((eventHandler, videoRendererEventListener,
            audioRendererEventListener, textRendererOutput, metadataRendererOutput) ->
        new Renderer[] {
            new EffectVideoRenderer(context, new BeautyShader()),
            new MediaCodecAudioRenderer(context, MediaCodecSelector.DEFAULT),
            new TextRenderer(textRendererOutput, eventHandler.getLooper()),
            new MetadataRenderer(metadataRendererOutput, eventHandler.getLooper())
        })
    .build();
```

### Q4: DRM 支持与 Widevine 集成

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    ExoPlayer DRM (Widevine) 集成流程                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌───────────┐    ┌────────────────┐    ┌───────────────────────────┐   │
│  │ ExoPlayer │    │ DefaultDrm     │    │   Widevine License Server  │   │
│  │           │    │ SessionManager │    │   (如 Google/Verimatrix)   │   │
│  └─────┬─────┘    └───────┬────────┘    └─────────────┬─────────────┘   │
│        │                  │                            │                 │
│  ┌─────▼──────────┐ ┌─────▼──────────┐ ┌──────────────▼───────────────┐ │
│  │ 1. 播放请求    │ │ 2. 检测 DRM    │ │                              │ │
│  │ MediaItem      │ │   UUID (如     │ │                              │ │
│  │ .drmUuid       │ │   Widevine)   │ │                              │ │
│  └────────────────┘ └─────┬──────────┘ │                              │ │
│                           │            │                              │ │
│  ┌────────────────────────▼──────────┐ │                              │ │
│  │ 3. 获取许可证请求                 │ │                              │ │
│  │   HttpMediaDrmCallback            │ │                              │ │
│  │   .executeKeyRequest(uuid, req)   ├─▶ 4. 发送密钥请求               │ │
│  └────────────────┬─────────────────┘ │   POST /license               │ │
│                   │                   │   {spc: "base64..."}          │ │
│                   │                   │                              │ │
│  ┌────────────────▼─────────────────┐ │                              │ │
│  │ 5. 接收许可证响应                │◀─┤ 6. 返回许可证              │  │ │
│  │   .executeProvisionRequest(uuid) │ │   {license: "base64..."}      │ │
│  └────────────────┬─────────────────┘ └──────────────────────────────┘ │
│                   │                                                     │
│  ┌────────────────▼─────────────────┐                                  │
│  │ 6. MediaDrm.provideKeyResponse() │                                  │
│  │   → 解密视频帧并渲染             │                                  │
│  └──────────────────────────────────┘                                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**关键代码：**

```java
// 配置 DRM
MediaItem mediaItem = new MediaItem.Builder()
    .setUri("https://example.com/encrypted_video.mpd")
    .setDrmUuid(C.WIDEVINE_UUID)
    .setDrmLicenseUri("https://license.example.com/widevine")
    .setDrmMultiSession(true)  // 多会话支持
    .build();

// 自定义 License 请求头
HttpMediaDrmCallback drmCallback = new HttpMediaDrmCallback(
    "https://license.example.com/widevine",
    new DefaultHttpDataSource.Factory()
);
drmCallback.setKeyRequestProperty("Authorization", "Bearer YOUR_TOKEN");

// 创建 DrmSessionManager 并传给播放器
DrmSessionManager drmSessionManager = new DefaultDrmSessionManager.Builder()
    .setUuidAndExoMediaDrmProvider(C.WIDEVINE_UUID, 
        FrameworkMediaDrm.DEFAULT_PROVIDER)
    .build(drmCallback);

ExoPlayer player = new ExoPlayer.Builder(context)
    .setMediaSourceFactory(new DefaultMediaSourceFactory(context)
        .setDrmSessionManagerProvider(unusedMediaItem -> drmSessionManager))
    .build();
```

**Widevine 安全等级：**

| 等级 | 名称 | 说明 | 典型场景 |
|:-----|:-----|:-----|:---------|
| **L1** | Widevine L1 | 所有内容在 TEE 中处理，输出到受保护的视频管道 | Netflix/Amazon Prime 高清播放 |
| **L2** | Widevine L2 | 内容解密在 TEE 中，视频处理在软件中（已废弃） | 已不再使用 |
| **L3** | Widevine L3 | 完全软件实现，安全级别最低 | 普通应用，最高 SD 质量 |

### Q5: DownloadManager 离线下载机制

```
┌────────────────────────────────────────────────────────────────────────────┐
│                      ExoPlayer DownloadManager 架构                         │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌──────────────────┐       ┌──────────────────┐       ┌────────────────┐ │
│  │ DownloadService  │       │ DownloadManager  │       │ DownloadTracker│ │
│  │ (Foreground      │──────▶│ (核心管理类)      │──────▶│ (状态跟踪)     │ │
│  │  Service)        │       │                  │       │                │ │
│  └──────────────────┘       └────────┬─────────┘       └────────────────┘ │
│                                      │                                     │
│                     ┌────────────────┼────────────────┐                    │
│                     │                │                │                    │
│              ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐            │
│              │ Download    │  │ Download    │  │ Download    │            │
│              │ Task 1      │  │ Task 2      │  │ Task N      │            │
│              │ (video1.mp4)│  │ (video2.mp4)│  │ (videoN.mp4)│            │
│              │ State: DONE │  │ State: 35%  │  │ State: QUE  │            │
│              └─────────────┘  └─────────────┘  └─────────────┘            │
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │                        存储层 (DownloadIndex)                         │ │
│  │  ┌────────────────────────────────────────────────────────────────┐ │ │
│  │  │ actions / downloads /                     ← DownloadManager ID  │ │ │
│  │  │   ├── 1234567890.actions                                     │ │ │
│  │  │   ├── 1234567890.downloads                                   │ │ │
│  │  │   └── 9876543210.actions                                     │ │ │
│  │  │ files / demuxed /                           ← 解封装后的文件     │ │ │
│  │  │   ├── 1234567890/                                            │ │ │
│  │  │   │   ├── 0 (视频流)                                        │ │ │
│  │  │   │   └── 1 (音频流)                                        │ │ │
│  │  │   └── 9876543210/                                            │ │ │
│  │  └────────────────────────────────────────────────────────────────┘ │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

**核心代码示例：**

```java
// 1. 初始化 DownloadManager
DownloadManager downloadManager = new DownloadManager(
    context,
    databaseProvider,          // 使用 ExoPlayer 内置 Room 数据库
    new CacheDataSource.Factory()
        .setCache(cache)
        .setUpstreamDataSourceFactory(new DefaultHttpDataSource.Factory())
);

// 2. 创建下载请求
DownloadRequest request = new DownloadRequest.Builder("video_id_001",
        Uri.parse("https://example.com/video.mpd"))
    .setData(/* 自定义数据 */)
    .build();

// 3. 启动下载服务
DownloadService.sendAddDownload(context, DemoDownloadService.class,
    request, /* foreground= */ false);

// 4. 监听下载状态
downloadManager.addListener(new DownloadManager.Listener() {
    @Override
    public void onDownloadChanged(DownloadManager manager, Download download) {
        int state = download.state;
        float percent = download.getPercentDownloaded();
    }

    @Override
    public void onDownloadRemoved(DownloadManager manager, Download download) {
        // 下载被移除
    }
});

// 5. 播放离线内容
MediaItem offlineItem = new MediaItem.Builder()
    .setMediaId("video_id_001")
    .setUri(Uri.parse("https://example.com/video.mpd"))
    .build();

player.setMediaItem(offlineItem);  // 自动检测本地缓存并播放
```

---

## 3. 核心原理深度剖析

### 3.1 TrackSelector：音视频轨道选择机制

TrackSelector 是 ExoPlayer 自适应码率（ABR）和轨道选择的核心组件，负责从 MediaSource 暴露的多个 TrackGroup 中选择最合适的音视频轨道。

**核心数据结构：**

```
TrackGroupArray
  ├── TrackGroup[0] (Video)        ← 所有视频轨道
  │   ├── Format(format=0): 1920×1080, 5000kbps, H.264
  │   ├── Format(format=1): 1280×720,  2500kbps, H.264
  │   ├── Format(format=2): 854×480,   1200kbps, H.264
  │   └── Format(format=3): 640×360,    600kbps, H.264
  │
  ├── TrackGroup[1] (Audio)        ← 所有音频轨道
  │   ├── Format(format=0): en, AAC, 128kbps
  │   ├── Format(format=1): en, AAC, 256kbps
  │   └── Format(format=2): de, AAC, 128kbps
  │
  └── TrackGroup[2] (Text)         ← 所有字幕轨道
      ├── Format(format=0): en, WebVTT
      └── Format(format=1): zh, WebVTT
```

**DefaultTrackSelector 选择策略：**

```java
// TrackSelector.Parameters 核心配置
DefaultTrackSelector.Parameters parameters = new DefaultTrackSelector
    .Parameters.Builder(context)
    // 视频约束
    .setMaxVideoSize(Integer.MAX_VALUE, Integer.MAX_VALUE)  // 最大分辨率
    .setMaxVideoBitrate(Integer.MAX_VALUE)                   // 最大码率
    .setMaxVideoFrameRate(Integer.MAX_VALUE)                 // 最大帧率
    // 音频约束
    .setPreferredAudioLanguage("en")                         // 首选语言
    .setMaxAudioBitrate(256000)                              // 最大音频码率
    // 自适应选择
    .setForceHighestSupportedBitrate(false)                  // 是否强制最高码率
    .setAllowVideoNonSeamlessAdaptiveness(true)              // 允许非无缝自适应
    .build();

// 选择逻辑（简化版核心流程）
TrackSelection selectTracks(TrackGroupArray groups, int[][] formats) {
    // 1. 过滤不符合约束条件的 Format
    List<Format> filtered = filterByConstraints(formats, constraints);
    
    // 2. 按优先级排序：分辨率 > 码率 > 帧率
    Collections.sort(filtered, (a, b) -> {
        int res = b.width * b.height - a.width * a.height;
        if (res != 0) return res;
        return b.bitrate - a.bitrate;
    });
    
    // 3. 返回最佳匹配
    return new FixedTrackSelection(groups[0], filtered.get(0));
}
```

### 3.2 Renderer：渲染流水线

Renderer 是 ExoPlayer 中负责将压缩的媒体数据解码并渲染到输出设备（屏幕/扬声器）的核心组件。

**Render 流水线状态机：**

```
                    ┌─────────────┐
                    │ STATE_IDLE  │  ← 初始状态
                    └──────┬──────┘
                           │ enable()
                    ┌──────▼──────┐
                ┌──▶│STATE_ENABLED│
                │   └──────┬──────┘
                │          │ start()
                │   ┌──────▼──────┐
                │   │STATE_STARTED│  ← 开始接收 SampleStream
                │   └──────┬──────┘
                │          │
                │   ┌──────▼──────────────────────┐
                │   │  逐帧处理循环 (doSomeWork)    │
                │   │                              │
                │   │  ┌───────────────────────┐   │
                │   │  │ 1. readSource()       │   │
                │   │  │   从 SampleStream     │   │
                │   │  │   读取压缩帧          │   │
                │   │  └──────────┬────────────┘   │
                │   │             │                │
                │   │  ┌──────────▼────────────┐   │
                │   │  │ 2. onQueueInputBuffer│   │
                │   │  │   送入 MediaCodec     │   │
                │   │  │   解码队列            │   │
                │   │  └──────────┬────────────┘   │
                │   │             │                │
                │   │  ┌──────────▼────────────┐   │
                │   │  │ 3. processOutputBuffer│  │
                │   │  │   从 MediaCodec 取出   │   │
                │   │  │   解码后的帧          │   │
                │   │  └──────────┬────────────┘   │
                │   │             │                │
                │   │  ┌──────────▼────────────┐   │
                │   │  │ 4. renderOutputBuffer │   │
                │   │  │   渲染到 Surface/      │   │
                │   │  │   AudioTrack          │   │
                │   │  └───────────────────────┘   │
                │   └──────────────────────────────┘
                │          │ stop()
                │   ┌──────▼──────┐
                └───│STATE_STOPPED│
                    └─────────────┘
```

**MediaCodecVideoRenderer 核心流程：**

```java
// 简化版渲染循环
@Override
protected void render(long positionUs, long elapsedRealtimeUs) {
    // 1. 管理输入缓冲区：从 SampleStream 读取数据送入 MediaCodec
    while (shouldFeedInputBuffer()) {
        int inputBufferIndex = codec.dequeueInputBuffer(DEQUEUE_TIMEOUT_US);
        if (inputBufferIndex < 0) break;
        
        ByteBuffer inputBuffer = codec.getInputBuffer(inputBufferIndex);
        int result = sampleStream.readData(formatHolder, decoderInputBuffer);
        
        if (result == C.RESULT_BUFFER_READ) {
            codec.queueInputBuffer(inputBufferIndex, 
                0, decoderInputBuffer.size,
                decoderInputBuffer.timeUs, decoderInputBuffer.flags);
        }
    }
    
    // 2. 管理输出缓冲区：从 MediaCodec 取解码帧并渲染
    MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();
    int outputBufferIndex = codec.dequeueOutputBuffer(info, DEQUEUE_TIMEOUT_US);
    
    if (outputBufferIndex >= 0) {
        // 计算渲染时间
        long earlyUs = (info.presentationTimeUs - positionUs);
        long elapsedSinceStart = System.nanoTime() / 1000 - startTimeUs;
        long timeToRenderUs = info.presentationTimeUs - elapsedSinceStart;
        
        if (timeToRenderUs > DROP_THRESHOLD_US) {
            // 帧已过期：丢帧
            codec.releaseOutputBuffer(outputBufferIndex, false);
            droppedFrameCount++;
        } else {
            // 渲染帧到 Surface
            codec.releaseOutputBuffer(outputBufferIndex, true);
            renderedFrameCount++;
        }
    }
}
```

### 3.3 LoadControl：缓冲控制

LoadControl 是 ExoPlayer 播放流畅度的核心控制器，决定何时开始加载数据、何时开始播放、缓冲多少数据合适。

**DefaultLoadControl 核心参数：**

```java
DefaultLoadControl loadControl = new DefaultLoadControl.Builder()
    .setBufferDurationsMs(
        50_000,   // minBufferMs：最少缓冲 50 秒才停止加载（播放）
        100_000,  // maxBufferMs：最多缓冲 100 秒（防止内存溢出）
        2_500,    // bufferForPlaybackMs：初始缓冲至少 2.5 秒才开始播放
        5_000     // bufferForPlaybackAfterRebufferMs：卡顿后重新缓冲至少 5 秒
    )
    .setPrioritizeTimeOverSizeThresholds(true)  // 优先基于时长而非数据量
    .build();
```

**LoadControl 决策模型：**

```
    缓冲时长 (bufferedDuration)
    │
    │  maxBufferMs ───────────────────────────────────────┐
    │  (100s)                                             │ shouldContinueLoading = false
    │                                                     │ (暂停加载，防止 OOM)
    │  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│
    │                                                     │ shouldContinueLoading = true
    │                                                     │ (继续加载，维持缓冲)
    │  minBufferMs ───────────────────────────────────────┘
    │  (50s)                                              
    │                                                      
    │                                                      
    │  bufferForPlaybackAfterRebufferMs ─ ─ ─ ─ ─ ─ ─ ─ ┐
    │  (5s)                                               │ shouldStartPlayback = true
    │  bufferForPlaybackMs ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘ (可以开始/恢复播放)
    │  (2.5s)
    │
    │  0 ──────────────────────────────────────────────────► 时间
    │       ↑                    ↑
    │   prepare()           正在播放中
    │   (首次缓冲等待)
```

**核心方法实现逻辑：**

```java
public class DefaultLoadControl implements LoadControl {
    
    // 是否应该继续加载数据
    @Override
    public boolean shouldContinueLoading(
            long bufferedDurationUs, 
            float playbackSpeed) {
        // 实际缓冲时长 = 总缓冲时长 / 播放速度
        long targetBufferUs = (long)(bufferedDurationUs / playbackSpeed);
        
        // 如果超过 maxBufferMs（转换为微秒），停止加载
        boolean isBufferingEnough = targetBufferUs >= maxBufferUs;
        
        // 如果是快进播放，需要更多缓冲；暂停时减少缓冲
        return !isBufferingEnough;
    }
    
    // 是否应该开始播放（首次或卡顿恢复后）
    @Override
    public boolean shouldStartPlayback(
            long bufferedDurationUs,
            float playbackSpeed,
            boolean rebuffering) {
        long minBufferUs = rebuffering 
            ? bufferForPlaybackAfterRebufferMs * 1000 
            : bufferForPlaybackMs * 1000;
            
        // 播放速度加快时，需要更多缓冲时长
        long adjustedBufferUs = (long)(bufferedDurationUs / playbackSpeed);
        return adjustedBufferUs >= minBufferUs;
    }
}
```

---

## 4. 流程图：ExoPlayer 播放数据流

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         ExoPlayer 播放全链路数据流                                │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                        1. 数据获取层 (DataSource)                         │  │
│  │                                                                          │  │
│  │  ┌───────────────┐   ┌───────────────┐   ┌───────────────┐              │  │
│  │  │ HttpDataSource │   │ FileDataSource │   │ AssetDataSrc  │  加密/自定   │  │
│  │  │ (网络流)       │   │ (本地文件)     │   │ (Asset目录)   │ 义 DataSource │  │
│  │  └───────┬───────┘   └───────┬───────┘   └───────┬───────┘              │  │
│  │          │                  │                   │                         │  │
│  │          └──────────────────┼───────────────────┘                         │  │
│  │                             │                                             │  │
│  │                    ┌────────▼────────┐                                    │  │
│  │                    │  Cache (可选)   │ ← SimpleCache / LRU                │  │
│  │                    └────────┬────────┘                                    │  │
│  └─────────────────────────────┼─────────────────────────────────────────────┘  │
│                                │                                                │
│  ┌─────────────────────────────▼─────────────────────────────────────────────┐  │
│  │                    2. 解封装层 (Extractor / ChunkSource)                   │  │
│  │                                                                          │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐    │  │
│  │  │ ProgressiveMediaSource → BundledExtractorsAdapter               │    │  │
│  │  │   ├── Mp4Extractor     (MP4/M4A/M4V)                            │    │  │
│  │  │   ├── TsExtractor      (TS 传输流)                               │    │  │
│  │  │   ├── FlvExtractor     (FLV 流媒体)                              │    │  │
│  │  │   ├── MatroskaExtractor (MKV/WebM)                              │    │  │
│  │  │   └── FragmentedMp4Extractor (fMP4 分片 MP4)                    │    │  │
│  │  └─────────────────────────────────────────────────────────────────┘    │  │
│  │                                                                          │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐    │  │
│  │  │ DashMediaSource / HlsMediaSource                                │    │  │
│  │  │   → Manifest 解析 → ChunkIterator → 逐 Chunk 获取 + Extractor    │    │  │
│  │  └─────────────────────────────────────────────────────────────────┘    │  │
│  │                                                                          │  │
│  │  输出：独立的 SampleStream (Video / Audio / Text)                         │  │
│  └─────────────────────────────┬────────────────────────────────────────────┘  │
│                                │                                                │
│  ┌─────────────────────────────▼─────────────────────────────────────────────┐  │
│  │                       3. 轨道选择层 (TrackSelector)                        │  │
│  │                                                                          │  │
│  │  ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐      │  │
│  │  │ Video TrackGroup │   │ Audio TrackGroup │   │ Text  TrackGroup │      │  │
│  │  │ [1080p,720p,480p]│   │ [en,zh,ja]       │   │ [en,zh]          │      │  │
│  │  └────────┬─────────┘   └────────┬─────────┘   └────────┬─────────┘      │  │
│  │           │                      │                       │                │  │
│  │           └──────────────────────┼───────────────────────┘                │  │
│  │                                  │                                        │  │
│  │                    ┌─────────────▼──────────────┐                         │  │
│  │                    │  DefaultTrackSelector      │                         │  │
│  │                    │  选择合适的 TrackSelection │                         │  │
│  │                    └─────────────┬──────────────┘                         │  │
│  └──────────────────────────────────┼────────────────────────────────────────┘  │
│                                     │                                           │
│  ┌──────────────────────────────────▼────────────────────────────────────────┐  │
│  │                         4. 缓冲控制层 (LoadControl)                        │  │
│  │                                                                          │  │
│  │   缓冲状态       加载策略                      播放决策                    │  │
│  │  ┌──────────┐   ┌────────────────┐    ┌─────────────────────┐            │  │
│  │  │ BUFFERING│──▶│ shouldContinue │    │ shouldStartPlayback │            │  │
│  │  │ (卡顿中) │   │ Loading()      │    │ ()                  │            │  │
│  │  └──────────┘   └────────────────┘    └─────────────────────┘            │  │
│  │       │                                                                   │  │
│  │  ┌────▼─────┐                                                             │  │
│  │  │  PLAYING │   minBufferMs=50s  maxBufferMs=100s  initBufferMs=2.5s     │  │
│  │  └──────────┘                                                             │  │
│  └──────────────────────────────┬───────────────────────────────────────────┘  │
│                                 │                                               │
│  ┌──────────────────────────────▼───────────────────────────────────────────┐  │
│  │                       5. 解码渲染层 (Renderer)                            │  │
│  │                                                                          │  │
│  │  ┌───────────────────────┐   ┌───────────────────────┐                  │  │
│  │  │ MediaCodecVideoRender │   │ MediaCodecAudioRender │                  │  │
│  │  │                       │   │                       │                  │  │
│  │  │  ① readSource()       │   │  ① readSource()       │                  │  │
│  │  │  ② queueInputBuffer() │   │  ② queueInputBuffer() │                  │  │
│  │  │  ③ dequeueOutputBuf() │   │  ③ dequeueOutputBuf() │                  │  │
│  │  │  ④ releaseOutputBuf() │   │  ④ writePcmData()      │                  │  │
│  │  │                       │   │                       │                  │  │
│  │  │  ▼ 渲染到 Surface     │   │  ▼ 写入 AudioTrack    │                  │  │
│  │  │  (SurfaceView /       │   │  (系统音频输出)       │                  │  │
│  │  │   TextureView)        │   │                       │                  │  │
│  │  └───────────────────────┘   └───────────────────────┘                  │  │
│  │                                                                          │  │
│  │  ┌───────────────────────┐   ┌───────────────────────┐                  │  │
│  │  │ TextRenderer          │   │ MetadataRenderer      │                  │  │
│  │  │ → SubtitleView 显示   │   │ → ID3/EMSG 回调       │                  │  │
│  │  └───────────────────────┘   └───────────────────────┘                  │  │
│  │                                                                          │  │
│  │  ┌───────────────────────────────────────────────────────────────────┐  │  │
│  │  │              输出：用户可见/可听 的音视频内容                        │  │  │
│  │  └───────────────────────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**数据流关键路径总结：**

```
DataSource.read() → Extractor.read() → SampleQueue → 
TrackSelector.selectTracks() → LoadControl 缓冲检查 →
Renderer.render() → MediaCodec.decode() → Surface/AudioTrack
```

---

## 5. 源码分析：核心组件实现

### 5.1 Timeline 模型源码

```java
// Timeline.java - 两个核心抽象
public abstract class Timeline {
    
    // Window：顶层容器，对应一个"播放窗口"
    public static final class Window {
        public long positionInFirstPeriodUs;  // 当前播放位置
        public long durationUs;              // 窗口总时长
        public boolean isDynamic;            // 是否动态流（直播）
        public boolean isLive;               // 是否直播
        public MediaItem mediaItem;          // 关联的 MediaItem
    }
    
    // Period：时间片段，一个 Window 可以包含多个 Period
    public static final class Period {
        public Object uid;          // Period 唯一标识
        public long durationUs;     // Period 时长
        public long positionInWindowUs;  // 在 Window 中的偏移
    }
    
    // 核心查询方法
    public abstract int getWindowCount();
    public abstract int getPeriodCount();
    public abstract Window getWindow(int windowIndex, Window window, long defaultPositionProjectionUs);
    public abstract Period getPeriod(int periodIndex, Period period, boolean setIds);
}
```

### 5.2 TrackSelection 核心源码

```java
// TrackSelection.java - 轨道选择结果
public interface TrackSelection {
    TrackGroup getTrackGroup();
    int length();                     // Format 数量
    Format getFormat(int index);      // 获取指定 Format
    int getIndexInTrackGroup(int index);
    int getSelectedIndex();           // 当前选中的 Format
    
    // 自适应选择的关键方法
    void onPlaybackSpeed(float playbackSpeed);
    int getSelectedIndexInTrackGroup();
    
    // 更新选择参数（如网络带宽变化时自动切换码率）
    void updateSelectedTrack(long playbackPositionUs,
            long bufferedDurationUs, long availableDurationUs,
            List<? extends QueueMediaChunk> queue, MediaChunkIterator[] iterators);
}

// DefaultTrackSelector 的核心选择逻辑
public final class DefaultTrackSelector extends MappingTrackSelector {
    
    // 根据 Parameters 生成 TrackSelection
    @Override
    protected TrackSelection[] selectTracks(
            MappedTrackInfo trackInfo,
            int[][][] rendererTrackGroupFormats,
            int[] rendererTrackGroupCounts,
            Parameters params) {
        
        TrackSelection[] selections = new TrackSelection[trackInfo.getRendererCount()];
        
        // 对每个 Renderer 类型（Video/Audio/Text）分别选择
        for (int i = 0; i < selections.length; i++) {
            if (trackInfo.getRendererType(i) == C.TRACK_TYPE_VIDEO) {
                selections[i] = selectVideoTrack(trackInfo, i, params);
            } else if (trackInfo.getRendererType(i) == C.TRACK_TYPE_AUDIO) {
                selections[i] = selectAudioTrack(trackInfo, i, params);
            } else {
                selections[i] = selectOtherTrack(trackInfo, i, params);
            }
        }
        return selections;
    }
}
```

### 5.3 LoadControl 核心源码

```java
public class DefaultLoadControl implements LoadControl {
    
    // 四大核心缓冲参数
    private final long minBufferUs;           // 最少缓冲 = 50s → 50_000_000us
    private final long maxBufferUs;           // 最多缓冲 = 100s → 100_000_000us
    private final long bufferForPlaybackUs;   // 启播缓冲 = 2.5s → 2_500_000us
    private final long bufferForPlaybackAfterRebufferUs; // 重连缓冲 = 5s
    
    private final boolean prioritizeTimeOverSizeThresholds;
    
    // 计算目标缓冲大小
    private long getAllocatorBufferUs(long totalBufferedDurationUs, float speed) {
        // 如果不是优先时间，则考虑数据量限制
        if (!prioritizeTimeOverSizeThresholds) {
            // 基于已分配的字节数估算时长
            return min(totalBufferedDurationUs, 
                       allocator.getTotalBytesAllocated() * bytesToUsRatio);
        }
        return totalBufferedDurationUs;
    }
    
    @Override
    public boolean shouldContinueLoading(
            long bufferedDurationUs,
            float playbackSpeed) {
        long adjustedBufferUs = (long)(bufferedDurationUs / playbackSpeed);
        // 快速播放时需要更多缓冲
        boolean targetBufferReached = adjustedBufferUs >= maxBufferUs;
        // 同时检查是否超过最大缓冲区大小
        boolean bufferFull = allocator.getTotalBytesAllocated() >= maxAllocatedBytes;
        
        return !targetBufferReached && !bufferFull;
    }
    
    @Override
    public boolean shouldStartPlayback(
            long bufferedDurationUs,
            float playbackSpeed,
            boolean rebuffering,
            long targetLiveOffsetUs) {
        // 根据是否在卡顿恢复中选择不同阈值
        long minBufferDurationUs = rebuffering 
            ? bufferForPlaybackAfterRebufferUs 
            : bufferForPlaybackUs;
        
        long adjustedDurationUs = (long)(bufferedDurationUs / playbackSpeed);
        return adjustedDurationUs >= minBufferDurationUs;
    }
}
```

---

## 6. 应用场景：自定义 ExoPlayer 实现缓存策略（边下边播）

### 6.1 场景描述

设计一个"边下边播"视频播放器，满足以下需求：
- 视频播放过程中，自动将已播放部分的媒体数据缓存到本地磁盘
- 下次播放同一视频时，优先从本地缓存加载，减少网络请求
- 支持 LRU 缓存淘汰策略，磁盘缓存大小可配置
- 可动态调整缓存策略（仅 WiFi 下缓存、缓存最大文件大小等）

### 6.2 架构设计

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                       边下边播缓存播放器架构                                    │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                        CachingPlayer                                  │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐ │  │
│  │  │  CacheStrategy (缓存策略接口)                                     │ │  │
│  │  │  ┌───────────────────┐  ┌───────────────────┐                   │ │  │
│  │  │  │ WifiOnlyStrategy  │  │ AlwaysCacheStrat  │  LruEviction     │ │  │
│  │  │  │ (仅WiFi下缓存)    │  │ (始终缓存)        │  (LRU淘汰策略)   │ │  │
│  │  │  └───────────────────┘  └───────────────────┘                   │ │  │
│  │  └─────────────────────────────────────────────────────────────────┘ │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌──────────────────────────────────────┐    ┌─────────────────────────┐    │
│  │        CacheDataSourceFactory         │    │   NetworkMonitor         │    │
│  │  ┌────────────────────────────────┐   │    │  (网络状态检测)          │    │
│  │  │  CacheDataSink (写缓存)        │   │    │  ┌───────────────────┐  │    │
│  │  │  ① 网络数据到达                │   │    │  │ isWifiConnected() │  │    │
│  │  │  ② 写入磁盘缓存                │   │    │  │ isCellularData()  │  │    │
│  │  │  ③ 同时返回数据给下游          │   │    │  └───────────────────┘  │    │
│  │  └────────────────────────────────┘   │    └─────────────────────────┘    │
│  │  ┌────────────────────────────────┐   │                                   │
│  │  │  CacheDataSource (读缓存)      │   │    ┌─────────────────────────┐    │
│  │  │  ① 检查磁盘缓存命中            │   │    │   LRUCacheManager       │    │
│  │  │  ② 命中 → 直接返回缓存数据     │   │    │   ┌─────────────────┐   │    │
│  │  │  ③ 未命中 → 网络请求并缓存     │   │    │   │ CacheEvictor    │   │    │
│  │  └────────────────────────────────┘   │    │   │ .evictIfNeeded()│   │    │
│  └──────────────────────────────────────┘    │   │ (超出上限时淘汰)│   │    │
│                                               │   └─────────────────┘   │    │
│  ┌──────────────────────────────────────┐    └─────────────────────────┘    │
│  │           SimpleCache                 │                                   │
│  │  ┌────────────────────────────────┐   │                                   │
│  │  │ 缓存目录结构：                  │   │                                   │
│  │  │ /data/cache/exo/               │   │                                   │
│  │  │   ├── abc123.uid              │   │                                   │
│  │  │   ├── abc123.0                │   │  (视频数据块)                      │
│  │  │   ├── abc123.1                │   │  (音频数据块)                      │
│  │  │   ├── abc123.2                │   │  (索引文件)                        │
│  │  │   └── cached_content_index.exi│   │  (缓存内容索引)                    │
│  │  └────────────────────────────────┘   │                                   │
│  └──────────────────────────────────────┘                                   │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 6.3 完整实现代码

**步骤 1：创建自定义 CacheDataSourceFactory（边下边播核心）**

```java
/**
 * 支持边下边播的 CacheDataSource 工厂
 * 核心思路：拦截数据读取流程，将网络数据同时写入本地缓存
 */
public class PlayWhileCachingDataSourceFactory implements DataSource.Factory {
    
    private final Context context;
    private final Cache cache;                    // ExoPlayer SimpleCache
    private final CacheEvictor evictor;           // LRU 淘汰器
    private final long maxCacheSize;              // 最大缓存 500MB
    private final CacheStrategy cacheStrategy;    // 缓存策略
    
    public PlayWhileCachingDataSourceFactory(Context context) {
        this.context = context;
        this.maxCacheSize = 500 * 1024 * 1024;    // 500MB
        
        // 1. 配置磁盘缓存
        File cacheDir = new File(context.getCacheDir(), "exo_cache");
        this.cache = new SimpleCache(cacheDir, new LeastRecentlyUsedCacheEvictor(maxCacheSize));
        this.evictor = new LeastRecentlyUsedCacheEvictor(maxCacheSize);
        
        // 2. 默认策略：仅 WiFi 下缓存
        this.cacheStrategy = new WifiOnlyCacheStrategy(context);
    }
    
    public PlayWhileCachingDataSourceFactory setCacheStrategy(CacheStrategy strategy) {
        this.cacheStrategy = strategy;
        return this;
    }
    
    @Override
    public DataSource createDataSource() {
        // 3. 构建三级数据源：缓存 → 网络（边下边存）
        return new CacheDataSource(
            cache,                                          // 本地缓存层
            new DefaultHttpDataSource.Factory()             // 网络数据层（上游）
                .setUserAgent("CachingPlayer/1.0")
                .setConnectTimeoutMs(10_000)
                .setReadTimeoutMs(10_000)
                .createDataSource(),
            new FileDataSource.Factory().createDataSource(),  // 文件数据源
            new CacheDataSinkFactory(cache, 
                CacheDataSinkFactory.DEFAULT_FRAGMENT_SIZE)   // 缓存写入器
                .createDataSink(),
            // 缓存控制标志
            CacheDataSource.FLAG_BLOCK_ON_CACHE |          // 未命中时阻塞等待
            CacheDataSource.FLAG_IGNORE_CACHE_ON_ERROR,    // 错误时回退网络
            new CacheDataSource.EventListener() {
                @Override
                public void onCachedBytesRead(long cacheSizeBytes, 
                        long cachedBytesRead) {
                    // 缓存命中统计
                    Log.d("CacheStat", "Cache hit: " + cachedBytesRead + " bytes");
                }
                
                @Override
                public void onCacheIgnored(int reason) {
                    Log.d("CacheStat", "Cache ignored, reason: " + reason);
                }
            }
        );
    }
}
```

**步骤 2：自定义缓存策略（WifiOnly / Always / LRU 淘汰）**

```java
/**
 * 缓存策略接口
 */
public interface CacheStrategy {
    boolean shouldCache();           // 是否应该缓存
    boolean shouldEvict(long currentCacheSize);  // 是否应该淘汰
    long getMaxCacheSize();          // 获取最大缓存大小
}

/**
 * 仅 WiFi 下缓存策略
 */
public class WifiOnlyCacheStrategy implements CacheStrategy {
    private final ConnectivityManager connectivityManager;
    
    public WifiOnlyCacheStrategy(Context context) {
        this.connectivityManager = (ConnectivityManager) 
            context.getSystemService(Context.CONNECTIVITY_SERVICE);
    }
    
    @Override
    public boolean shouldCache() {
        NetworkInfo networkInfo = connectivityManager.getActiveNetworkInfo();
        return networkInfo != null 
            && networkInfo.getType() == ConnectivityManager.TYPE_WIFI;
    }
    
    @Override
    public boolean shouldEvict(long currentCacheSize) {
        return currentCacheSize > getMaxCacheSize();
    }
    
    @Override
    public long getMaxCacheSize() {
        return 300 * 1024 * 1024; // WiFi 下最大 300MB
    }
}

/**
 * LRU 淘汰策略
 */
public class LruCacheEvictor implements CacheEvictor {
    private final long maxBytes;
    
    public LruCacheEvictor(long maxBytes) {
        this.maxBytes = maxBytes;
    }
    
    @Override
    public void onSpanAdded(Cache cache, CacheSpan span) {
        // 当新数据被缓存时触发
    }
    
    @Override
    public void onSpanRemoved(Cache cache, CacheSpan span) {
        // 当缓存数据被移除时触发
    }
    
    @Override
    public void onStartFile(Cache cache, String key, long position, long length) {
        // 开始缓存新文件
        evictIfNeeded(cache);
    }
    
    private void evictIfNeeded(Cache cache) {
        long currentSize = cache.getCacheSpace();
        if (currentSize > maxBytes) {
            // 触发 LRU 淘汰：移除最久未使用的缓存
            NavigableSet<CacheSpan> spans = cache.getCachedSpans(key);
            // SimpleCache 使用 LeastRecentlyUsedCacheEvictor 自动处理
        }
    }
}
```

**步骤 3：构建 CachingPlayer 封装类**

```java
/**
 * 封装了边下边播能力的 ExoPlayer 包装器
 */
public class CachingPlayer {
    
    private final Context context;
    private final ExoPlayer player;
    private final PlayWhileCachingDataSourceFactory dataSourceFactory;
    
    public CachingPlayer(Context context) {
        this.context = context;
        this.dataSourceFactory = new PlayWhileCachingDataSourceFactory(context);
        
        // 创建 ExoPlayer 实例
        DefaultRenderersFactory renderersFactory = new DefaultRenderersFactory(context)
            .setExtensionRendererMode(
                DefaultRenderersFactory.EXTENSION_RENDERER_MODE_ON);
        
        // 自定义 LoadControl：播放时缓冲更多，边下边播更流畅
        DefaultLoadControl loadControl = new DefaultLoadControl.Builder()
            .setBufferDurationsMs(
                30_000,   // 最少缓冲 30s（边下边播需要更多缓冲）
                120_000,  // 最多缓冲 120s
                2_000,    // 初始 2s 即可起播
                5_000     // 卡顿后 5s 恢复
            )
            .build();
        
        this.player = new ExoPlayer.Builder(context, renderersFactory)
            .setLoadControl(loadControl)
            .setMediaSourceFactory(
                new ProgressiveMediaSource.Factory(dataSourceFactory)
            )
            .build();
    }
    
    /**
     * 播放视频（自动边下边播并缓存）
     */
    public void play(String videoUrl) {
        MediaItem mediaItem = MediaItem.fromUri(videoUrl);
        player.setMediaItem(mediaItem);
        player.prepare();
        player.play();
    }
    
    /**
     * 播放视频并显示预览图
     */
    public void playWithPreview(String videoUrl, String previewUrl, 
            PlayerView playerView) {
        playerView.setPlayer(player);
        
        // 设置预览图（在视频加载前显示）
        playerView.setDefaultArtwork(
            BitmapFactory.decodeResource(context.getResources(), R.drawable.preview)
        );
        
        play(videoUrl);
    }
    
    /**
     * 清理过期缓存
     */
    public void clearOldCache() {
        // 清理超过 7 天未访问的缓存
        long sevenDaysAgo = System.currentTimeMillis() - 7 * 24 * 60 * 60 * 1000;
        // SimpleCache 通过 CacheEvictor 自动管理淘汰
    }
    
    /**
     * 获取缓存统计
     */
    public CacheStats getCacheStats() {
        Cache cache = dataSourceFactory.getCache();
        return new CacheStats(
            cache.getCacheSpace(),          // 当前缓存占用
            dataSourceFactory.getCacheStrategy().getMaxCacheSize(),  // 最大容量
            cache.getCacheSpace() * 100f / dataSourceFactory.getCacheStrategy().getMaxCacheSize()
        );
    }
    
    public ExoPlayer getPlayer() {
        return player;
    }
    
    public void release() {
        player.release();
    }
    
    /**
     * 缓存统计信息
     */
    public static class CacheStats {
        public final long usedBytes;
        public final long maxBytes;
        public final float usagePercent;
        
        public CacheStats(long used, long max, float percent) {
            this.usedBytes = used;
            this.maxBytes = max;
            this.usagePercent = percent;
        }
    }
}
```

**步骤 4：使用示例**

```java
// Activity 中使用
public class VideoPlayerActivity extends AppCompatActivity {
    private CachingPlayer cachingPlayer;
    private PlayerView playerView;
    
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_video_player);
        
        playerView = findViewById(R.id.player_view);
        cachingPlayer = new CachingPlayer(this);
        
        String videoUrl = "https://example.com/sample_video.mp4";
        cachingPlayer.playWithPreview(videoUrl, null, playerView);
        
        // 监听播放状态
        cachingPlayer.getPlayer().addListener(new Player.Listener() {
            @Override
            public void onPlaybackStateChanged(int playbackState) {
                if (playbackState == Player.STATE_BUFFERING) {
                    // 显示加载指示器（边下边播缓冲中）
                    showLoadingIndicator();
                } else if (playbackState == Player.STATE_READY) {
                    // 首帧渲染完毕
                    hideLoadingIndicator();
                }
            }
            
            @Override
            public void onPlayerError(PlaybackException error) {
                // 错误处理：可能是网络问题导致缓存不完整
                handlePlaybackError(error);
            }
        });
    }
    
    @Override
    protected void onDestroy() {
        super.onDestroy();
        cachingPlayer.release();
    }
    
    private void showLoadingIndicator() { /* ... */ }
    private void hideLoadingIndicator() { /* ... */ }
    private void handlePlaybackError(PlaybackException error) { /* ... */ }
}
```

### 6.4 缓存数据流向（边下边播完整时序）

```
时间线 ─────────────────────────────────────────────────────────────────────▶

网络请求     [Chunk1 2MB][Chunk2 2MB][Chunk3 2MB][Chunk4 2MB]...  (持续下载)
              │           │           │           │
              ▼           ▼           ▼           ▼
磁盘缓存     ┌─────────┐┌─────────┐┌─────────┐┌─────────┐
             │Chunk1 写││Chunk2 写││Chunk3 写││Chunk4 写│  (边下边存)
             └─────────┘└─────────┘└─────────┘└─────────┘
              │           │           │           │
              ▼           ▼           ▼           ▼
播放器缓冲区 [====Chunk1====][====Chunk2====]...  (缓冲中)
              │
              ▼
视频渲染      ▶▶▶ 开始播放 (首帧渲染)
              │
              ▼
用户观看      ─────────────────────────▶观看中▶──────────────────▶

二次播放     ┌──────────────────────────────────────┐
(再次打开)   │  直接从磁盘缓存读取，无需网络请求    │
             │  Chunk1→Chunk2→Chunk3→Chunk4→...      │
             └──────────────────────────────────────┘
```

### 6.5 进阶优化建议

1. **预加载策略**：在用户滑动到视频前，预加载下一个视频的前 N 秒数据
2. **分片缓存**：大视频按固定大小（如 2MB）分片缓存，支持 Range 请求
3. **缓存索引**：维护缓存内容的元数据索引（视频 ID、时长、清晰度、缓存完成度）
4. **多级缓存**：内存缓存（最近 2 个视频）→ 磁盘 LRU 缓存 → 网络
5. **智能清理**：结合用户观看行为（完播率、收藏、重复观看）决定缓存优先级

---

## 面试评分要点总结

| 评估维度 | 初级 (L4-L5) | 中级 (L6-L7) | 高级 (L8+) |
|:---------|:-------------|:-------------|:-----------|
| **架构理解** | 知道 ExoPlayer 能播放视频 | 能说出 Timeline/MediaSource/Renderer 的职责 | 能画出完整架构图并解释组件间协作 |
| **对比分析** | 知道 ExoPlayer 比 MediaPlayer 好 | 能说出 3+ 个区别 | 能从架构/扩展性/DRM/流媒体等多维度深入对比 |
| **扩展能力** | 看过官方 Demo | 能自定义 DataSource | 能实现自定义 Renderer、TrackSelector 和完整的缓存策略 |
| **DRM 理解** | 知道 DRM 是版权保护 | 理解 Widevine 三级安全机制 | 能画出完整 DRM 许可证获取流程图 |
| **离线下载** | 用过 DownloadManager API | 理解下载任务调度机制 | 能设计自定义缓存策略和 LRU 淘汰算法 |
| **缓冲控制** | 知道卡顿需要缓冲 | 理解 LoadControl 参数含义 | 能根据场景优化缓冲策略（直播/点播/短视频） |

---

> **学习建议**：建议结合 ExoPlayer 官方源码（GitHub: google/ExoPlayer）阅读本文档，重点关注 `DefaultTrackSelector`、`DefaultLoadControl`、`MediaCodecVideoRenderer` 和 `CacheDataSource` 等核心类的实现细节。
