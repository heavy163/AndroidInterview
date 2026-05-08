# 04 FFmpeg 应用

## 模块概览

FFmpeg 是音视频开发领域的"瑞士军刀"——涵盖解封装、解码、滤镜、编码、封装全链路。本章聚焦 **FFmpeg 核心模块架构**、**解封装与解码流程**、**Android 交叉编译**、**与 MediaCodec 的对比选型**，以及 **视频转码实战**。掌握 FFmpeg 是高级音视频工程师的必备能力。

---

## 一、面试高频问题（6+）

### 1. FFmpeg 的模块组成与核心架构

> 问题：FFmpeg 由哪些核心模块组成？各自负责什么功能？

**回答要点**：

FFmpeg 采用**模块化分层架构**，核心模块及其职责如下：

| 模块 | 全称 | 核心职责 | 关键数据结构 / API |
|------|------|---------|-------------------|
| **libavformat** | AVFormat Library | 解封装/封装：读取/写入各种容器格式（MP4/MKV/FLV/TS 等） | `AVFormatContext`、`AVStream`、`avformat_open_input()`、`av_read_frame()` |
| **libavcodec** | AVCodec Library | 编解码：提供 H.264/H.265/VP9/AAC/MP3 等编解码器实现 | `AVCodecContext`、`AVCodec`、`avcodec_send_packet()`、`avcodec_receive_frame()` |
| **libavutil** | AVUtil Library | 工具库：内存管理、数学运算、错误码、日志、图像处理等通用工具 | `AVFrame`、`AVPacket`、`av_malloc()`、`av_dict_*()` |
| **libswscale** | Software Scale Library | 图像缩放与像素格式转换（YUV ↔ RGB、分辨率缩放） | `SwsContext`、`sws_scale()` |
| **libswresample** | Software Resample Library | 音频重采样：采样率转换、声道布局转换、音频格式转换 | `SwrContext`、`swr_convert()` |
| **libavfilter** | AVFilter Library | 滤镜处理：视频滤镜（裁剪、水印、调色）、音频滤镜（混音、音量、EQ） | `AVFilterGraph`、`AVFilterContext`、`avfilter_graph_create_filter()` |
| **libpostproc** | Postproc Library | 后处理：去块滤波、降噪等（已较少使用，功能被 libavfilter 取代） | `pp_context`、`pp_postprocess()` |
| **libavdevice** | AVDevice Library | 设备捕获：摄像头、麦克风、屏幕录制等输入/输出设备 | `avdevice_register_all()`、`avdevice_list_devices()` |

**FFmpeg 模块架构图**：

```
┌─────────────────────────────────────────────────────────────────┐
│                        FFmpeg 模块架构                           │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                   应用层 (ffmpeg / ffplay / ffprobe)       │  │
│  │                  CLI 工具、Android JNI 调用层               │  │
│  └────────────────────┬─────────────────────────────────────┘  │
│                       │                                         │
│  ┌────────────────────┼─────────────────────────────────────┐  │
│  │              API 层 (libavformat / libavcodec)             │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │  │
│  │  │  libavformat │  │  libavcodec  │  │  libavfilter  │    │  │
│  │  │  ┌────────┐  │  │  ┌────────┐  │  │  ┌────────┐  │    │  │
│  │  │  │ 解封装  │  │  │  │ 解码器  │  │  │  │ 滤镜图  │  │    │  │
│  │  │  │ 封装   │  │  │  │ 编码器  │  │  │  │ 水印   │  │    │  │
│  │  │  │ 协议   │  │  │  │ 解析器  │  │  │  │ 裁剪   │  │    │  │
│  │  │  └────────┘  │  │  └────────┘  │  │  └────────┘  │    │  │
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘    │  │
│  └─────────┼──────────────────┼──────────────────┼──────────┘  │
│            │                  │                  │              │
│  ┌─────────┼──────────────────┼──────────────────┼──────────┐  │
│  │   工具层        │                  │                  │      │  │
│  │  ┌──────────────┴──┐  ┌──────────┴──┐  ┌──────────┴──┐  │  │
│  │  │   libavutil     │  │  libswscale │  │libswresample│  │  │
│  │  │  ┌───────────┐  │  │  ┌────────┐ │  │  ┌────────┐ │  │  │
│  │  │  │ AVFrame   │  │  │  │YUV↔RGB │ │  │  │重采样   │ │  │  │
│  │  │  │ AVPacket  │  │  │  │缩放     │ │  │  │声道转换 │ │  │  │
│  │  │  │ 字典/日志 │  │  │  │格式转换 │ │  │  │采样率   │ │  │  │
│  │  │  └───────────┘  │  │  └────────┘ │  │  └────────┘ │  │  │
│  │  └─────────────────┘  └─────────────┘  └─────────────┘  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  数据流向:                                                       │
│  文件/网络 → libavformat(解封装) → libavcodec(解码)              │
│       → libavfilter(滤镜) → libswscale/libswresample(转换)       │
│       → libavcodec(编码) → libavformat(封装) → 输出              │
└─────────────────────────────────────────────────────────────────┘
```

**模块依赖关系**：

```
libavutil          ← 所有模块的基础依赖（无外部依赖）
     │
     ├── libavcodec    ← 依赖 libavutil（+ libswresample 可选）
     ├── libavformat   ← 依赖 libavutil + libavcodec
     ├── libavfilter   ← 依赖 libavutil + libavcodec + libswscale + libswresample
     ├── libswscale    ← 依赖 libavutil
     ├── libswresample ← 依赖 libavutil
     └── libavdevice   ← 依赖 libavutil + libavformat + libavcodec
```

---

### 2. FFmpeg 解封装 —— AVFormatContext 完整流程

> 问题：FFmpeg 解封装一个 MP4 文件的完整流程是什么？AVFormatContext 如何解析文件头？

**回答要点**：

解封装流程包含 4 个关键步骤：**打开文件** → **查找流信息** → **循环读取 Packet** → **关闭释放**。

```
解封装完整时序:

1. avformat_alloc_context()          创建 AVFormatContext
         │
2. avformat_open_input(&ctx, url, ...) 打开文件/网络流
         │
         ├─ 探测输入格式 (probe): 读取前 N KB 数据
         │    └─ 匹配 mp4/mkv/flv/ts 等格式特征码
         │
         ├─ 创建 AVInputFormat (如 ff_mov_demuxer)
         │    └─ 调用 read_header() 读取文件头
         │         ├─ 解析 ftyp/moov box (MP4)
         │         ├─ 创建 AVStream 对象 (每个音视频轨一个)
         │         ├─ 读取 duration / bit_rate 等元数据
         │         └─ 填充 codecpar (codec_id, width, height, extradata)
         │
3. avformat_find_stream_info(&ctx, ...)  探查流详细信息
         │
         ├─ 解码部分帧以获取精确信息
         │    ├─ 对于视频流: 填充 width/height/framerate/pix_fmt
         │    └─ 对于音频流: 填充 sample_rate/channels/channel_layout
         │
4. av_read_frame(&ctx, &pkt)            循环读取数据包
         │
         ├─ 每次调用返回一个 AVPacket
         ├─ pkt.stream_index 标识属于哪个流
         ├─ pkt.pts / pkt.dts 时间戳
         └─ pkt.data 指向压缩数据 (H.264 NAL / AAC ADTS 等)
         │
5. avformat_close_input(&ctx)           释放资源
```

**AVFormatContext 核心字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `iformat` | `AVInputFormat*` | 指向解封装器（如 ff_mov_demuxer） |
| `pb` | `AVIOContext*` | I/O 上下文，管理底层读写（文件/网络） |
| `nb_streams` | `unsigned int` | 流的数量（视频+音频+字幕等） |
| `streams[]` | `AVStream**` | 流数组，streams[i] 指向第 i 个 AVStream |
| `duration` | `int64_t` | 媒体总时长（单位：AV_TIME_BASE = 1/1000000 秒） |
| `bit_rate` | `int64_t` | 总码率 |
| `metadata` | `AVDictionary*` | 元数据字典（标题、作者等） |

**AVStream 核心字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `index` | `int` | 流索引 |
| `codecpar` | `AVCodecParameters*` | 编解码器参数（codec_id, width, height, extradata） |
| `time_base` | `AVRational` | 时间基（PTS/DTS 的时间单位） |
| `duration` | `int64_t` | 该流的时长（以 time_base 为单位） |
| `avg_frame_rate` | `AVRational` | 平均帧率 |
| `r_frame_rate` | `AVRational` | 真实帧率 |
| `metadata` | `AVDictionary*` | 流级别元数据 |

**面试延伸**：
- `avformat_open_input()` 内部会根据文件扩展名和前几个字节（魔数）探测格式，如 MP4 文件头 `00 00 00 xx 66 74 79 70`（ftyp box）。
- 如果探测失败，可以通过 `AVFormatContext->probesize` 和 `max_analyze_duration` 调大探测范围。
- `avformat_find_stream_info()` 可能会解码若干帧来获取精确的宽高/帧率，开销较大，对于某些场景可跳过（设置 `AVFMT_FLAG_NOBUFFER` 等 flags）。

---

### 3. FFmpeg 解码 —— avcodec_send_packet / avcodec_receive_frame

> 问题：FFmpeg 新解码 API 的工作机制是什么？avcodec_send_packet 和 avcodec_receive_frame 如何配合使用？

**回答要点**：

FFmpeg 3.1+ 引入**生产者-消费者模型**的新解码 API，替代了旧的 `avcodec_decode_video2()`。核心是两个函数：

```
┌──────────────────────────────────────────────────────────────┐
│              FFmpeg 解码：生产者-消费者模型                     │
│                                                              │
│   输入队列 (AVPacket)          输出队列 (AVFrame)              │
│  ┌───┬───┬───┬───┐           ┌───┬───┬───┬───┐              │
│  │P0 │P1 │P2 │...│──────────▶│F0 │F1 │F2 │...│              │
│  └───┴───┴───┴───┘  解码器   └───┴───┴───┴───┘              │
│       │    ▲                      │     ▲                     │
│       │    │                      │     │                     │
│  avcodec_send_packet()     avcodec_receive_frame()            │
│  送入压缩数据包              取出解码后的帧                     │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │            典型解码循环 (伪代码)                       │   │
│  │                                                      │   │
│  │  while (av_read_frame(fmt_ctx, &pkt) >= 0) {         │   │
│  │      if (pkt.stream_index == video_stream_index) {    │   │
│  │          // ① 送入压缩包                              │   │
│  │          ret = avcodec_send_packet(codec_ctx, &pkt);  │   │
│  │          // ② 循环取出解码帧 (一个 packet 可能解码出   │   │
│  │          //    多个 frame，也可能 0 个)                │   │
│  │          while (avcodec_receive_frame(                │   │
│  │                      codec_ctx, frame) >= 0) {        │   │
│  │              // ③ 处理解码后的 frame                   │   │
│  │              process_frame(frame);                   │   │
│  │          }                                           │   │
│  │      }                                               │   │
│  │      av_packet_unref(&pkt);                          │   │
│  │  }                                                   │   │
│  │                                                      │   │
│  │  // ④ Flush: 送入 NULL packet 冲刷解码器缓冲区        │   │
│  │  avcodec_send_packet(codec_ctx, NULL);               │   │
│  │  while (avcodec_receive_frame(codec_ctx, frame)>=0)  │   │
│  │      process_frame(frame);                           │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

**两个 API 的返回值语义**：

| 函数 | 返回值 | 含义 |
|------|:------:|------|
| `avcodec_send_packet()` | 0 | 成功送入 |
| | `AVERROR(EAGAIN)` | 解码器内部缓冲区满，需先 `receive_frame` 取走输出 |
| | `AVERROR_EOF` | 解码器已被 flush（已送入过 NULL packet） |
| | `AVERROR(EINVAL)` | 解码器未打开或参数错误 |
| | `AVERROR(ENOMEM)` | 内存不足 |
| `avcodec_receive_frame()` | 0 | 成功取出一帧 |
| | `AVERROR(EAGAIN)` | 需要继续送入更多 packet |
| | `AVERROR_EOF` | 解码器已完全 flush，无更多输出 |
| | `AVERROR(EINVAL)` | 解码器未打开 |

**关键面试点**：

1. **一个 packet 可能解码出多个 frame**（如 B 帧重排序），也可能解码出 0 个 frame（解码器缓存中）。
2. **内存管理**：`av_packet_unref()` 必须在每次循环后调用，否则内存泄漏。送入的 packet 数据会被解码器拷贝（或引用计数），调用 `avcodec_send_packet()` 后可以立即 `unref`。
3. **Flush 机制**：发送 NULL packet 冲刷解码器内部缓冲区，获取所有缓存的帧（典型场景：seek 后、文件末尾）。
4. **为什么废弃旧 API**：旧 API `avcodec_decode_video2()` 将输入和输出耦合在同一个调用中，无法处理解码器内部缓冲、错误恢复等复杂场景。新 API 将输入/输出解耦，更灵活。

---

### 4. FFmpeg 在 Android 上的交叉编译

> 问题：如何在 Android 上交叉编译 FFmpeg？关键步骤和常见坑有哪些？

**回答要点**：

**交叉编译本质**：在 x86 主机上使用 Android NDK 工具链编译出 ARM/AArch64 架构的 FFmpeg 动态库（.so）。

**完整编译流程**：

```
┌────────────────────────────────────────────────────────────────┐
│                   FFmpeg Android 交叉编译流程                    │
│                                                                │
│  环境准备                                                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ • Linux/macOS (推荐) 或 WSL (Windows)                     │  │
│  │ • Android NDK (推荐 r21~r26 LTS)                         │  │
│  │ • FFmpeg 源码 (推荐 4.4+ 或 5.x/6.x 稳定版)              │  │
│  └──────────────────────────────────────────────────────────┘  │
│       │                                                        │
│       ▼                                                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Step 1: 指定目标 ABI                                      │  │
│  │   armeabi-v7a  (ARM 32位, 兼容性最好)                      │  │
│  │   arm64-v8a    (ARM 64位, 性能最优)                        │  │
│  │   x86 / x86_64 (模拟器用)                                  │  │
│  └──────────────────────────────────────────────────────────┘  │
│       │                                                        │
│       ▼                                                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Step 2: 配置 NDK 交叉编译工具链                            │  │
│  │                                                          │  │
│  │  TOOLCHAIN=$NDK/toolchains/llvm/prebuilt/linux-x86_64    │  │
│  │                                                          │  │
│  │  arm64-v8a:                                              │  │
│  │    CC=$TOOLCHAIN/bin/aarch64-linux-android21-clang       │  │
│  │    CXX=$TOOLCHAIN/bin/aarch64-linux-android21-clang++    │  │
│  │    AR=$TOOLCHAIN/bin/llvm-ar                             │  │
│  │    LD=$TOOLCHAIN/bin/ld                                   │  │
│  │    RANLIB=$TOOLCHAIN/bin/llvm-ranlib                     │  │
│  │    STRIP=$TOOLCHAIN/bin/llvm-strip                       │  │
│  └──────────────────────────────────────────────────────────┘  │
│       │                                                        │
│       ▼                                                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Step 3: 执行 ./configure                                  │  │
│  │                                                          │  │
│  │  关键配置项:                                              │  │
│  │  --prefix=android/$ABI     输出目录                       │  │
│  │  --enable-cross-compile    启用交叉编译                   │  │
│  │  --target-os=android       目标 OS                       │  │
│  │  --arch=aarch64            目标架构                       │  │
│  │  --cpu=armv8-a             CPU 型号                      │  │
│  │  --cross-prefix=...        工具链前缀                     │  │
│  │                                                          │  │
│  │  功能裁剪 (减小体积):                                      │  │
│  │  --disable-everything      禁用所有组件                    │  │
│  │  --enable-decoder=h264     仅启用需要的解码器              │  │
│  │  --enable-encoder=aac      仅启用需要的编码器              │  │
│  │  --enable-demuxer=mov      MP4 解封装器                   │  │
│  │  --enable-muxer=mp4        MP4 封装器                     │  │
│  │  --enable-protocol=file    文件协议                       │  │
│  │  --enable-parser=h264      需要解析器配合解码器            │  │
│  │  --enable-filter=scale     缩放滤镜                       │  │
│  │                                                          │  │
│  │  输出配置:                                                │  │
│  │  --enable-shared           编译 .so 动态库                │  │
│  │  --disable-static          不编译 .a 静态库               │  │
│  │  --enable-jni              JNI 支持 (可选)                │  │
│  │  --enable-mediacodec       MediaCodec 硬件加速 (可选)     │  │
│  └──────────────────────────────────────────────────────────┘  │
│       │                                                        │
│       ▼                                                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Step 4: make -j$(nproc) && make install                  │  │
│  │                                                          │  │
│  │  输出:  android/arm64-v8a/                               │  │
│  │           ├── lib/libavcodec.so                          │  │
│  │           ├── lib/libavformat.so                         │  │
│  │           ├── lib/libavutil.so                           │  │
│  │           ├── lib/libswscale.so                          │  │
│  │           ├── lib/libswresample.so                       │  │
│  │           ├── lib/libavfilter.so                         │  │
│  │           └── include/  (头文件，用于 JNI 开发)           │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

**常见编译坑与解决方案**：

| 常见问题 | 原因 | 解决方案 |
|---------|------|---------|
| `C compiler test failed` | NDK 工具链路径不正确 | 检查 `--cc` / `--cross-prefix` 路径 |
| `error: undefined reference to 'log'` | 缺少 liblog 链接 | `--extra-libs="-llog"` |
| `arm-linux-androideabi-gcc is unable to create an executable` | 新版 NDK 移除了 gcc | 必须使用 clang（`--cc=clang`） |
| `.so 体积过大（~30MB）` | 启用了不必要模块 | 使用 `--disable-everything` + 按需启用 |
| `libavcodec.so 依赖 x264` | GPL 许可冲突 | 如果不使用 x264：`--disable-gpl`；如果用：App 必须开源 |
| **API Level 兼容性** | minSdk 与 NDK API Level 不匹配 | `--target-os=android` 时指定 `--extra-cflags="-D__ANDROID_API__=21"` |
| `pkg-config not found` | 缺少 pkg-config 工具 | `sudo apt install pkg-config` 或 `--pkg-config=false` |

**减小 FFmpeg .so 体积的最佳实践**：

```bash
# 最小化配置示例（仅 H.264+AAC 解封装+解码，约 3~5MB）
./configure \
    --disable-everything \
    --enable-decoder=h264,aac \
    --enable-demuxer=mov,flv,matroska \
    --enable-parser=h264,aac \
    --enable-protocol=file \
    --enable-filter=scale,format,null \
    --enable-cross-compile \
    --target-os=android \
    --arch=aarch64 \
    --cpu=armv8-a \
    ...
```

**面试延伸**：为什么要交叉编译 FFmpeg 而不是用预编译库？
- 预编译库可能包含不需要的模块，体积大；
- 自定义编译可以精确控制功能裁剪、版本、ABI；
- 可以集成特定外部库（如 x264、fdk-aac）；
- 安全审计要求可以从源码编译。

---

### 5. FFmpeg vs MediaCodec 的深度对比与选型

> 问题：Android 开发中，什么场景用 FFmpeg 软解/软编，什么场景用 MediaCodec 硬解/硬编？

**回答要点**：

| 对比维度 | MediaCodec（硬件） | FFmpeg（软件） |
|----------|-------------------|---------------|
| **实现机制** | 调用芯片厂商的 DSP/VPU 硬件模块 | CPU 软件执行编解码算法 |
| **功耗/发热** | 极低（<5% CPU，发热少） | 高（80~100% CPU，明显发热） |
| **延迟** | <30ms（硬件管线） | 50~200ms（依赖 CPU 算力） |
| **编码速度** | 实时 4K@60fps | 1080p@30fps 可能吃力 |
| **格式兼容** | 仅支持芯片内置的格式列表 | 支持几乎所有音视频格式 |
| **画质可控性** | 参数有限（码率/帧率/关键帧间隔），黑盒 | 精细控制（preset/tune/profile/level/x264 参数） |
| **稳定性** | 依赖厂商实现（华为/高通/MTK 表现可能不同） | 纯软件，行为一致可预测 |
| **功能丰富度** | 仅基础编解码 | 滤镜/字幕/多路复用/网络协议等全功能 |
| **首帧耗时** | <50ms | 需初始化软件解码器，100~300ms |
| **多实例** | 受硬件资源限制（通常 6~8 个编解码器） | 纯软件无限制（但 CPU 可能不够） |

**架构级对比图**：

```
┌─────────────────────────────────────────────────────────────────┐
│                    MediaCodec 硬解链路                           │
│                                                                 │
│  文件 ──▶ MediaExtractor ──▶ MediaCodec ──▶ Surface/ByteBuffer  │
│          (解析容器)         (硬件解码)      (渲染/处理)           │
│                                                                 │
│  特点: 端到端硬件管线，零拷贝，极低延迟                           │
│  局限: 仅支持 MP4/3GPP/WebM 等少量容器格式                       │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    FFmpeg 软解链路                               │
│                                                                 │
│  文件/网络 ──▶ libavformat ──▶ libavcodec ──▶ libswscale       │
│              (通用解封装)     (软件解码)      (格式转换)          │
│                     │              │               │             │
│                     │              │               ▼             │
│                     │              │         ┌──────────┐       │
│                     │              └────────▶│ OpenGL   │       │
│                     │                         │ Texture  │       │
│                     │                         └──────────┘       │
│  特点: 全格式兼容，精细控制，CPU 密集                             │
│  局限: 功耗高，延迟高，4K 以上实时解码有压力                       │
└─────────────────────────────────────────────────────────────────┘
```

**混合方案（最佳实践）**：

```
┌─────────────────────────────────────────────────────────────────┐
│               Android 播放器：MediaCodec + FFmpeg 混合架构        │
│                                                                 │
│  视频源 (MP4/MKV/FLV/RTMP/HLS)                                   │
│            │                                                     │
│            ▼                                                     │
│  ┌─────────────────────────────────────────────────────┐       │
│  │             FFmpeg (libavformat)                     │       │
│  │         全格式解封装成 AVPacket (统一接口)            │       │
│  └─────────────────┬───────────────────────────────────┘       │
│                    │                                             │
│                    ▼                                             │
│  ┌─────────────────────────────────────────────────────┐       │
│  │         格式白名单检查                                │       │
│  │    H.264/H.265/AAC ──────▶ MediaCodec 硬解           │       │
│  │    VP8/VP9/AV1/其他 ─────▶ FFmpeg 软解              │       │
│  └─────────────────┬───────────────────────────────────┘       │
│                    │                                             │
│            ┌───────┴───────┐                                     │
│            ▼               ▼                                     │
│  ┌──────────────┐  ┌─────────────────┐                          │
│  │  Surface 渲染 │  │  OpenGL Texture │                          │
│  │ (MediaCodec  │  │ (软解 YUV→RGB   │                          │
│  │  直接输出)   │  │  后渲染)        │                          │
│  └──────────────┘  └─────────────────┘                          │
└─────────────────────────────────────────────────────────────────┘
```

**面试速记决策口诀**：

> **直播录制 → MediaCodec**（低延迟、低功耗、实时性）  
> **视频编辑/转码 → FFmpeg**（精细画质控制、全格式）  
> **播放器 → 硬解优先 + FFmpeg 兜底**（兼容性与性能兼顾）  
> **多路并发 → FFmpeg**（硬件编解码器数量有限）

---

## 二、核心原理深度解析

### 2.1 FFmpeg 管道式处理模型

FFmpeg 的核心设计哲学是**管道式处理（Pipeline Processing）**：将音视频处理分解为多个独立阶段，通过数据流串联。

```
┌─────────────────────────────────────────────────────────────────┐
│                 FFmpeg 管道式处理全景架构                         │
│                                                                 │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │          │    │          │    │          │    │          │  │
│  │ 解封装   │───▶│  解码    │───▶│  滤镜    │───▶│  编码    │  │
│  │ Demuxer  │    │ Decoder  │    │ Filter   │    │ Encoder  │  │
│  │          │    │          │    │          │    │          │  │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘  │
│       │               │               │               │         │
│       ▼               ▼               ▼               ▼         │
│  AVFormat        AVCodec         AVFilter         AVCodec       │
│  Context         Context          Graph           Context       │
│       │               │               │               │         │
│       ▼               ▼               ▼               ▼         │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐     │
│  │AVPacket │───▶│AVFrame  │───▶│AVFrame  │───▶│AVPacket │     │
│  │(压缩)   │    │(原始)   │    │(处理后) │    │(压缩)   │     │
│  └─────────┘    └─────────┘    └─────────┘    └─────────┘     │
│                                                     │          │
│                                                     ▼          │
│                                            ┌──────────────┐    │
│                                            │   封装        │    │
│                                            │   Muxer      │    │
│                                            └──────────────┘    │
│                                                     │          │
│                                                     ▼          │
│                                               输出文件/流       │
│                                                                 │
│  关键数据结构转换:                                               │
│  ① 解封装:   文件字节流 → AVPacket (压缩数据包, 含 PTS/DTS)      │
│  ② 解码:     AVPacket → AVFrame (原始 YUV/PCM 数据)             │
│  ③ 滤镜:     AVFrame → AVFrame (处理后的原始数据)               │
│  ④ 编码:     AVFrame → AVPacket (压缩数据包)                    │
│  ⑤ 封装:     AVPacket → 容器文件 (MP4/MKV 等)                   │
└─────────────────────────────────────────────────────────────────┘
```

**直播推流场景下的管道变体**：

```
摄像头采集 ──▶ 编码(H.264) ──▶ 封装(FLV) ──▶ RTMP 推流
   (YUV)          (AVPacket)      (FLV Tag)      (网络)
```

**播放器场景下的管道变体**：

```
网络流 ──▶ 解封装 ──▶ 解码 ──▶ 音视频同步 ──▶ 渲染
(HTTP/RTMP)  (Demux)  (Decode)   (PTS 对齐)    (Surface/AudioTrack)
```

---

### 2.2 avformat_open_input 读取头部并解析 Codec 参数（深入原理）

> `avformat_open_input()` 是 FFmpeg 最核心的入口函数之一，它不仅打开文件，还完成格式探测、头部解析、codec 参数提取。

**内部调用链**：

```
avformat_open_input(&ctx, url, fmt, &options)
    │
    ├─ 1. avformat_alloc_context()           // 若 ctx=NULL，内部分配
    │
    ├─ 2. init_input(ctx, url, &tmp)         // 初始化 I/O
    │      ├─ io_open()                       // 打开文件/网络流
    │      └─ avio_open2() → ffio_open_whitelist()
    │           └─ 创建 AVIOContext，设置 read/write/seek 回调
    │
    ├─ 3. av_probe_input_buffer2()           // 格式探测
    │      ├─ 读取数据到 probe buffer
    │      ├─ 遍历所有注册的 AVInputFormat
    │      │    └─ 调用 fmt->read_probe(probe_data)
    │      │         ├─ mp4: 检查 ftyp box (文件头 "ftyp")
    │      │         ├─ flv: 检查 "FLV" 魔数 + 版本号
    │      │         ├─ mkv: 检查 EBML 头
    │      │         └─ ts:  检查同步字节 0x47
    │      └─ 选择 score 最高的格式
    │
    ├─ 4. 设置 ctx->iformat = 探测到的格式
    │
    └─ 5. ctx->iformat->read_header(ctx)     // ★ 解析文件头
           │
           ├─ [MP4] mov_read_header()
           │      ├─ mov_read_default() 遍历顶层 box
           │      ├─ 遇到 'ftyp' → 读取品牌信息
           │      ├─ 遇到 'moov' → 进入 moov 解析
           │      │    ├─ 'mvhd' → 读取 duration, timescale
           │      │    ├─ 'trak' (视频轨)
           │      │    │    ├─ 'tkhd' → track 基本属性
           │      │    │    ├─ 'mdia' → 媒体信息
           │      │    │    │    ├─ 'mdhd' → timescale, duration
           │      │    │    │    ├─ 'hdlr' → handler type (vide/soun)
           │      │    │    │    └─ 'minf' → 媒体信息容器
           │      │    │    │         ├─ 'vmhd'/'smhd' → 视频/音频头
           │      │    │    │         └─ 'stbl' → 样本表
           │      │    │    │              ├─ 'stsd' → ★ 编解码器参数
           │      │    │    │              │    └─ avcC box → H.264 SPS/PPS
           │      │    │    │              │        (提取 extradata)
           │      │    │    │              ├─ 'stts' → 时间-样本映射
           │      │    │    │              ├─ 'stss' → 同步样本表 (I帧位置)
           │      │    │    │              ├─ 'stsz' → 样本大小
           │      │    │    │              └─ 'stco' → chunk 偏移
           │      │    │    └─ ...
           │      │    └─ 'trak' (音频轨) ...类似...
           │      └─ ...
           │
           ├─ [FLV] flv_read_header()
           │      ├─ 读取 FLV 头 (签名 + 版本 + flags)
           │      └─ 读取 metadata tag (script data)
           │           ├─ duration, width, height, videocodecid
           │           └─ 创建 AVStream，填充 codecpar
           │
           └─ [MKV] matroska_read_header()
                  ├─ 解析 EBML 头
                  └─ 遍历 Segment → Tracks → TrackEntry
                       ├─ CodecID → 映射到 AVCodecID
                       ├─ Video: PixelWidth/PixelHeight
                       ├─ Audio: SamplingFrequency/Channels
                       └─ CodecPrivate → extradata
```

**MP4 容器中 codec 参数提取的关键路径**：

```
MP4 文件结构:
┌───────────────────────────────────────────────┐
│ ftyp box: 文件类型标识                          │
├───────────────────────────────────────────────┤
│ moov box: 元数据容器                            │
│  ├─ mvhd: 全局时长/时间基                       │
│  ├─ trak(视频):                                │
│  │   ├─ tkhd: 宽度/高度 (显示尺寸)              │
│  │   └─ mdia → minf → stbl → stsd             │
│  │        └─ avc1/mp4a 条目:                   │
│  │             ├─ width/height (编码尺寸)       │
│  │             ├─ avcC (H.264):                │
│  │             │   ├─ AVCProfileIndication      │
│  │             │   ├─ profile_compatibility     │
│  │             │   ├─ AVCLevelIndication        │
│  │             │   └─ SPS + PPS (NAL units)    │
│  │             │       → 存入 codecpar->extradata│
│  │             └─ esds (AAC):                   │
│  │                  └─ DecoderConfigDescriptor  │
│  │                       → AudioSpecificConfig  │
│  │                          → codecpar->extradata│
│  ├─ trak(音频): ...类似...                      │
│  └─ udta: 用户自定义元数据                       │
├───────────────────────────────────────────────┤
│ mdat box: 媒体数据 (具体的音视频帧数据)          │
└───────────────────────────────────────────────┘
```

**为什么需要 extradata？**

- **H.264**：解码器需要 SPS（序列参数集）和 PPS（图像参数集）才能正确初始化解码。这些数据不在每个帧中重复，而是存在 extradata 中。
- **AAC**：需要 AudioSpecificConfig（音频特定配置，2字节），包含采样率索引、声道配置、Profile 等。
- 解码器初始化时必须传入 `codecpar->extradata` 和 `codecpar->extradata_size`。

**面试延伸**：
- `avformat_open_input()` 的性能开销主要在 `read_header()` 阶段，大文件的 moov 在末尾时需要 seek（MP4 的 "faststart" 优化）。
- 网络流的探测超时由 `AVFormatContext->probesize`（探测数据大小）和 `max_analyze_duration`（探测时间）控制。
- 自定义 I/O：可以通过 `avio_alloc_context()` 创建自定义的 `AVIOContext`，替换默认的文件 I/O，实现内存读取、自定义协议等。

---

## 三、流程图

### 3.1 FFmpeg 解封装 + 解码 + 格式转换 + 渲染 完整流程

```
┌─────────────────────────────────────────────────────────────────┐
│          FFmpeg 解封装 + 解码 + YUV→RGB + OpenGL 渲染流程         │
│          (以 Android 视频播放器解码一帧为例)                      │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Phase 1: 初始化                                         │   │
│  │                                                         │   │
│  │  avformat_alloc_context()                               │   │
│  │      │                                                  │   │
│  │      ▼                                                  │   │
│  │  avformat_open_input(&ctx, "file.mp4", NULL, NULL)      │   │
│  │      │  └─ 探测格式 → MP4 → 调用 mov_read_header()     │   │
│  │      │     └─ 解析 moov box → 创建 AVStream[0](视频)    │   │
│  │      │                     → 创建 AVStream[1](音频)    │   │
│  │      ▼                                                  │   │
│  │  avformat_find_stream_info(ctx, NULL)                   │   │
│  │      │  └─ 解码部分帧 → 获取准确的 width/height/fps     │   │
│  │      ▼                                                  │   │
│  │  avcodec_find_decoder(stream->codecpar->codec_id)       │   │
│  │      │  └─ codec_id = AV_CODEC_ID_H264                 │   │
│  │      ▼                                                  │   │
│  │  avcodec_alloc_context3(codec)                          │   │
│  │  avcodec_parameters_to_context(ctx, stream->codecpar)   │   │
│  │      │  └─ 将 codecpar 参数拷入 codec_ctx               │   │
│  │      │     └─ extradata (SPS/PPS) 传入解码器            │   │
│  │      ▼                                                  │   │
│  │  avcodec_open2(codec_ctx, codec, NULL)                  │   │
│  │                                                         │   │
│  │  sws_getContext(width, height, AV_PIX_FMT_YUV420P,     │   │
│  │                 width, height, AV_PIX_FMT_RGBA,         │   │
│  │                 SWS_BILINEAR, NULL, NULL, NULL)          │   │
│  └─────────────────────────────────────────────────────────┘   │
│       │                                                        │
│       ▼                                                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Phase 2: 解码循环 (每帧)                                │   │
│  │                                                         │   │
│  │  ┌──────────────────────────────────────┐               │   │
│  │  │  ① av_read_frame(ctx, &packet)       │               │   │
│  │  │     从文件中读取一个压缩数据包         │               │   │
│  │  │     packet.stream_index = 0 (视频)    │               │   │
│  │  │     packet.pts = 512                  │               │   │
│  │  │     packet.data → H.264 NAL 数据      │               │   │
│  │  └──────────────┬───────────────────────┘               │   │
│  │                 │                                        │   │
│  │                 ▼                                        │   │
│  │  ┌──────────────────────────────────────┐               │   │
│  │  │  ② avcodec_send_packet(ctx, &packet) │               │   │
│  │  │     送入压缩数据到解码器               │               │   │
│  │  │     返回 0 (成功)                     │               │   │
│  │  └──────────────┬───────────────────────┘               │   │
│  │                 │                                        │   │
│  │                 ▼                                        │   │
│  │  ┌──────────────────────────────────────┐               │   │
│  │  │  ③ avcodec_receive_frame(ctx, frame) │               │   │
│  │  │     从解码器取出解码后的帧             │               │   │
│  │  │     frame->width = 1920              │               │   │
│  │  │     frame->height = 1080             │               │   │
│  │  │     frame->format = AV_PIX_FMT_YUV420P│              │   │
│  │  │     frame->data[0] → Y 平面          │               │   │
│  │  │     frame->data[1] → U 平面          │               │   │
│  │  │     frame->data[2] → V 平面          │               │   │
│  │  └──────────────┬───────────────────────┘               │   │
│  │                 │                                        │   │
│  │                 ▼                                        │   │
│  │  ┌──────────────────────────────────────┐               │   │
│  │  │  ④ sws_scale(ctx,                    │               │   │
│  │  │       frame->data, frame->linesize,  │               │   │
│  │  │       0, height,                     │               │   │
│  │  │       rgb_frame->data,               │               │   │
│  │  │       rgb_frame->linesize)           │               │   │
│  │  │     YUV420P → RGBA 转换              │               │   │
│  │  └──────────────┬───────────────────────┘               │   │
│  │                 │                                        │   │
│  │                 ▼                                        │   │
│  │  ┌──────────────────────────────────────┐               │   │
│  │  │  ⑤ glTexSubImage2D(GL_TEXTURE_2D,   │               │   │
│  │  │       0, 0, 0, width, height,        │               │   │
│  │  │       GL_RGBA, GL_UNSIGNED_BYTE,     │               │   │
│  │  │       rgb_frame->data[0])            │               │   │
│  │  │     上传纹理到 GPU 并渲染             │               │   │
│  │  └──────────────────────────────────────┘               │   │
│  │                                                         │   │
│  │  av_packet_unref(&packet)  ← 释放 packet                │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  性能关键点:                                                     │
│  • av_read_frame: I/O 密集，通常在这里阻塞等待                    │
│  • avcodec_receive_frame: CPU 密集，H.264 解码占用最大           │
│  • sws_scale: CPU 密集，可用 NEON 指令集加速                     │
│  • glTexSubImage2D: GPU 上传，受带宽限制                         │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 FFmpeg 解码线程模型

```
┌─────────────────────────────────────────────────────────────────┐
│                 FFmpeg 多线程解码架构                             │
│                                                                 │
│  ┌─────────────┐                                                │
│  │  Demux 线程  │  读取 AVPacket                                 │
│  │ (单线程)     │                                                │
│  └──────┬──────┘                                                │
│         │ av_read_frame()                                       │
│         ▼                                                       │
│  ┌──────────────────────────────────────────────────┐          │
│  │              Packet Queue (线程安全)              │          │
│  │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐        │          │
│  │  │ P0  │→│ P1  │→│ P2  │→│ P3  │→│ ... │        │          │
│  │  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘        │          │
│  └──────────────┬───────────────────────────────────┘          │
│                 │                                               │
│     ┌───────────┼───────────┬───────────┐                      │
│     ▼           ▼           ▼           ▼                      │
│  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐                       │
│  │Decode│  │Decode│  │Decode│  │Decode│   解码线程池            │
│  │Thd #0│  │Thd #1│  │Thd #2│  │Thd #3│   数量 = thread_count │
│  └──┬───┘  └──┬───┘  └──┬───┘  └──┬───┘                       │
│     │         │         │         │                             │
│     └─────────┼─────────┼─────────┘                             │
│               │         │                                       │
│               ▼         ▼                                       │
│  ┌──────────────────────────────────────────────────┐          │
│  │            Frame Queue (线程安全)                 │          │
│  │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐                │          │
│  │  │ F1  │→│ F2  │→│ F3  │→│ F4  │    PTS 有序     │          │
│  │  └─────┘ └─────┘ └─────┘ └─────┘                │          │
│  └──────────────┬───────────────────────────────────┘          │
│                 │                                               │
│                 ▼                                               │
│  ┌──────────────────────────────────────────┐                  │
│  │          Render 线程                      │                  │
│  │  取出帧 → 音视频同步 → Surface 渲染       │                  │
│  └──────────────────────────────────────────┘                  │
│                                                                 │
│  多线程解码配置:                                                 │
│  codec_ctx->thread_count = 4;    // 设置解码线程数              │
│  codec_ctx->thread_type = FF_THREAD_FRAME | FF_THREAD_SLICE;   │
│                                                                 │
│  帧级并行 (FF_THREAD_FRAME):                                    │
│  - 每个线程解码完整的一帧                                        │
│  - 延迟 = (thread_count - 1) 帧                                 │
│  - 适合大部分视频编码格式                                        │
│                                                                 │
│  片级并行 (FF_THREAD_SLICE):                                    │
│  - 多个线程协作解码同一帧的不同 slice                            │
│  - 延迟低，但某些编码格式不支持                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 四、源码分析：FFmpeg JNI 封装层

### 4.1 Android 项目中 FFmpeg 的 JNI 桥接层

```cpp
/**
 * FFmpeg JNI 桥接层 —— 封装 FFmpeg C API 供 Java/Kotlin 调用
 *
 * 架构层次:
 *   Java/Kotlin (Player.kt)
 *       ↕ JNI
 *   Native (ffmpeg_bridge.cpp)  ← 本文件
 *       ↕ C API
 *   FFmpeg (libavformat / libavcodec / libavutil)
 */

#include <jni.h>
#include <android/log.h>

extern "C" {
#include <libavformat/avformat.h>
#include <libavcodec/avcodec.h>
#include <libavutil/imgutils.h>
#include <libswscale/swscale.h>
}

#define TAG "FFmpegBridge"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, TAG, __VA_ARGS__)

// ─── 全局变量 ────────────────────────────────────────────
static AVFormatContext *g_fmt_ctx = nullptr;
static AVCodecContext *g_video_codec_ctx = nullptr;
static AVCodecContext *g_audio_codec_ctx = nullptr;
static int g_video_stream_idx = -1;
static int g_audio_stream_idx = -1;
static struct SwsContext *g_sws_ctx = nullptr;
static AVFrame *g_rgb_frame = nullptr;

// ─── JNI 初始化: 注册 FFmpeg 所有组件 ────────────────────
extern "C" JNIEXPORT void JNICALL
Java_com_example_player_FFmpegPlayer_nativeInit(
    JNIEnv *env, jobject thiz) {

    // FFmpeg 4.0+ 可省略 av_register_all()
    // 但为兼容性考虑，保留调用
#if LIBAVFORMAT_VERSION_INT < AV_VERSION_INT(58, 9, 100)
    av_register_all();
#endif
    LOGI("FFmpeg initialized, version: %s", av_version_info());
}

// ─── 打开媒体文件并提取流信息 ────────────────────────────
extern "C" JNIEXPORT jint JNICALL
Java_com_example_player_FFmpegPlayer_nativeOpen(
    JNIEnv *env, jobject thiz, jstring path) {

    const char *file_path = env->GetStringUTFChars(path, nullptr);

    // ① 分配 AVFormatContext
    g_fmt_ctx = avformat_alloc_context();
    if (!g_fmt_ctx) {
        LOGE("Failed to allocate AVFormatContext");
        return -1;
    }

    // ② 打开文件并解析头部
    int ret = avformat_open_input(&g_fmt_ctx, file_path, nullptr, nullptr);
    if (ret < 0) {
        LOGE("avformat_open_input failed: %s", av_err2str(ret));
        return -2;
    }

    // ③ 探查流详细信息（解码部分帧获取精确参数）
    ret = avformat_find_stream_info(g_fmt_ctx, nullptr);
    if (ret < 0) {
        LOGE("avformat_find_stream_info failed: %s", av_err2str(ret));
        return -3;
    }

    // ④ 查找视频流和音频流索引
    g_video_stream_idx = av_find_best_stream(g_fmt_ctx, AVMEDIA_TYPE_VIDEO,
                                              -1, -1, nullptr, 0);
    g_audio_stream_idx = av_find_best_stream(g_fmt_ctx, AVMEDIA_TYPE_AUDIO,
                                              -1, -1, nullptr, 0);

    LOGI("Opened: %s, video_stream=%d, audio_stream=%d, duration=%lld us",
         file_path, g_video_stream_idx, g_audio_stream_idx,
         g_fmt_ctx->duration);

    // ⑤ 初始化视频解码器
    if (g_video_stream_idx >= 0) {
        AVStream *video_stream = g_fmt_ctx->streams[g_video_stream_idx];
        AVCodecParameters *codecpar = video_stream->codecpar;

        // 查找 H.264 解码器
        const AVCodec *codec = avcodec_find_decoder(codecpar->codec_id);
        if (!codec) {
            LOGE("Decoder not found for codec_id=%d", codecpar->codec_id);
            return -4;
        }

        // 分配解码上下文
        g_video_codec_ctx = avcodec_alloc_context3(codec);
        avcodec_parameters_to_context(g_video_codec_ctx, codecpar);

        // ★ 关键: 设置多线程解码
        g_video_codec_ctx->thread_count = 4;
        g_video_codec_ctx->thread_type = FF_THREAD_FRAME;

        // 打开解码器
        ret = avcodec_open2(g_video_codec_ctx, codec, nullptr);
        if (ret < 0) {
            LOGE("avcodec_open2 failed: %s", av_err2str(ret));
            return -5;
        }

        LOGI("Video decoder opened: %dx%d, codec=%s, fps=%d/%d",
             codecpar->width, codecpar->height, codec->name,
             video_stream->avg_frame_rate.num,
             video_stream->avg_frame_rate.den);
    }

    // ⑥ 初始化音频解码器（类似视频，省略）
    // ...

    env->ReleaseStringUTFChars(path, file_path);
    return 0;
}

// ─── 解码一帧视频并转换为 RGBA ────────────────────────────
extern "C" JNIEXPORT jbyteArray JNICALL
Java_com_example_player_FFmpegPlayer_nativeDecodeFrame(
    JNIEnv *env, jobject thiz) {

    AVPacket *packet = av_packet_alloc();
    AVFrame *frame = av_frame_alloc();
    jbyteArray result = nullptr;

    // ⑦ 循环读取 AVPacket
    while (av_read_frame(g_fmt_ctx, packet) >= 0) {
        if (packet->stream_index == g_video_stream_idx) {

            // ⑧ 送入压缩数据
            int ret = avcodec_send_packet(g_video_codec_ctx, packet);
            av_packet_unref(packet);

            if (ret < 0 && ret != AVERROR(EAGAIN)) {
                LOGE("avcodec_send_packet error: %s", av_err2str(ret));
                break;
            }

            // ⑨ 循环取出解码帧（一个 packet 可能产生多个 frame）
            while (avcodec_receive_frame(g_video_codec_ctx, frame) >= 0) {

                // ⑩ 初始化/更新 SwsContext（懒初始化）
                if (!g_sws_ctx) {
                    g_sws_ctx = sws_getContext(
                        g_video_codec_ctx->width,
                        g_video_codec_ctx->height,
                        g_video_codec_ctx->pix_fmt,  // 通常是 YUV420P
                        g_video_codec_ctx->width,
                        g_video_codec_ctx->height,
                        AV_PIX_FMT_RGBA,
                        SWS_BILINEAR,
                        nullptr, nullptr, nullptr
                    );

                    // 分配 RGBA 输出帧
                    g_rgb_frame = av_frame_alloc();
                    int num_bytes = av_image_get_buffer_size(
                        AV_PIX_FMT_RGBA,
                        g_video_codec_ctx->width,
                        g_video_codec_ctx->height, 1);
                    uint8_t *buffer = (uint8_t *)av_malloc(num_bytes);
                    av_image_fill_arrays(
                        g_rgb_frame->data, g_rgb_frame->linesize,
                        buffer, AV_PIX_FMT_RGBA,
                        g_video_codec_ctx->width,
                        g_video_codec_ctx->height, 1);
                }

                // ⑪ YUV → RGBA 转换
                sws_scale(g_sws_ctx,
                          frame->data, frame->linesize,
                          0, g_video_codec_ctx->height,
                          g_rgb_frame->data, g_rgb_frame->linesize);

                // ⑫ 转换为 jbyteArray 返回给 Java 层
                int rgb_size = g_video_codec_ctx->width
                             * g_video_codec_ctx->height * 4;
                result = env->NewByteArray(rgb_size);
                env->SetByteArrayRegion(result, 0, rgb_size,
                                        (jbyte*)g_rgb_frame->data[0]);

                av_frame_unref(frame);
                av_frame_free(&frame);
                av_packet_free(&packet);
                return result;  // 返回解码后的 RGBA 数据
            }
        } else {
            av_packet_unref(packet);
        }
    }

    // 无更多帧
    av_frame_free(&frame);
    av_packet_free(&packet);
    return nullptr;
}

// ─── 释放资源 ────────────────────────────────────────────
extern "C" JNIEXPORT void JNICALL
Java_com_example_player_FFmpegPlayer_nativeRelease(
    JNIEnv *env, jobject thiz) {

    if (g_sws_ctx) { sws_freeContext(g_sws_ctx); g_sws_ctx = nullptr; }
    if (g_rgb_frame) {
        av_freep(&g_rgb_frame->data[0]);
        av_frame_free(&g_rgb_frame);
        g_rgb_frame = nullptr;
    }
    if (g_video_codec_ctx) {
        avcodec_free_context(&g_video_codec_ctx);
    }
    if (g_audio_codec_ctx) {
        avcodec_free_context(&g_audio_codec_ctx);
    }
    if (g_fmt_ctx) {
        avformat_close_input(&g_fmt_ctx);
    }

    LOGI("FFmpeg resources released");
}
```

### 4.2 关键设计模式分析

| 设计模式 | 应用场景 | 说明 |
|---------|---------|------|
| **懒初始化** | SwsContext 延迟创建 | 避免在 open 阶段进行不必要的资源分配，等实际解码时才创建 |
| **生产者-消费者** | send_packet → receive_frame | 解耦输入和输出，支持 B 帧重排序、解码器内部缓冲 |
| **全局状态管理** | 使用静态全局变量 | 简化 JNI 调用（每次 JNI 调用是无状态的），适合单播放器实例 |
| **错误码传播** | 负数返回码 + av_err2str | 将 FFmpeg 错误码映射为可读字符串，传递给 Java 层 |

---

## 五、应用场景：FFmpeg 视频转码（任意格式 → H.264 + AAC）

### 5.1 完整转码流程与代码

> 场景：将任意输入格式的视频转码为 H.264 视频 + AAC 音频的 MP4 文件。

```
┌─────────────────────────────────────────────────────────────────┐
│              FFmpeg 转码管道: 任意格式 → MP4 (H.264+AAC)          │
│                                                                 │
│  输入文件 (mkv/avi/flv/wmv/...)                                 │
│       │                                                         │
│       ▼                                                         │
│  ┌──────────────────────────────────────────────────┐          │
│  │  ① 解封装 (avformat_open_input)                  │          │
│  │     读取输入容器格式，提取 AVStream               │          │
│  │     创建输入解码器 (avcodec_find_decoder)         │          │
│  └──────────────────────┬───────────────────────────┘          │
│                         │                                       │
│         ┌───────────────┼───────────────┐                      │
│         ▼                               ▼                      │
│  ┌─────────────────┐          ┌─────────────────┐              │
│  │  ② 视频处理      │          │  ③ 音频处理      │              │
│  │                 │          │                 │              │
│  │ 输入: 任意编码   │          │ 输入: 任意编码   │              │
│  │ 解码: FFmpeg    │          │ 解码: FFmpeg    │              │
│  │ 滤镜: (可选)     │          │ 重采样: 44100Hz │              │
│  │   scale/format  │          │ 声道: 立体声    │              │
│  │ 编码: libx264   │          │ 编码: AAC-LC    │              │
│  │ 输出: H.264     │          │ 输出: AAC       │              │
│  └────────┬────────┘          └────────┬────────┘              │
│           │                            │                        │
│           └──────────┬─────────────────┘                        │
│                      ▼                                          │
│  ┌──────────────────────────────────────────────────┐          │
│  │  ④ 封装 (avformat_write_header / av_write_frame) │          │
│  │     创建 MP4 输出容器                             │          │
│  │     交错写入视频/音频 AVPacket                    │          │
│  │     av_write_trailer 完成封装                     │          │
│  └──────────────────────┬───────────────────────────┘          │
│                         │                                       │
│                         ▼                                       │
│                  输出文件 (output.mp4)                           │
│                  H.264 + AAC / MP4                              │
└─────────────────────────────────────────────────────────────────┘
```

**转码核心代码（C 语言 / Android NDK）**：

```c
/**
 * FFmpeg 视频转码核心实现
 * 输入: 任意格式 → 输出: MP4 (H.264 + AAC)
 *
 * 关键步骤:
 *  1. 打开输入文件，创建输入解码器
 *  2. 创建输出文件，创建输出编码器
 *  3. 逐帧: 读取 → 解码 → (可选滤镜) → 编码 → 封装
 *  4. Flush + 释放资源
 */

#include <libavformat/avformat.h>
#include <libavcodec/avcodec.h>
#include <libavutil/opt.h>
#include <libavutil/timestamp.h>
#include <libswresample/swresample.h>
#include <libswscale/swscale.h>

typedef struct {
    AVFormatContext *fmt_ctx;
    AVCodecContext *codec_ctx;
    int stream_idx;
} InputStream;

typedef struct {
    AVFormatContext *fmt_ctx;
    AVCodecContext *codec_ctx;
    AVStream *stream;
    int stream_idx;
} OutputStream;

/**
 * 打开输入媒体文件，创建解码器
 */
int open_input(const char *filename, InputStream *input) {
    int ret;

    // ① 打开输入文件
    input->fmt_ctx = NULL;
    ret = avformat_open_input(&input->fmt_ctx, filename, NULL, NULL);
    if (ret < 0) {
        av_log(NULL, AV_LOG_ERROR, "Cannot open input: %s\n", filename);
        return ret;
    }

    // ② 查找流信息
    ret = avformat_find_stream_info(input->fmt_ctx, NULL);
    if (ret < 0) {
        av_log(NULL, AV_LOG_ERROR, "Cannot find stream info\n");
        return ret;
    }

    // ③ 查找视频流
    input->stream_idx = av_find_best_stream(input->fmt_ctx,
                                            AVMEDIA_TYPE_VIDEO,
                                            -1, -1, NULL, 0);
    if (input->stream_idx < 0) {
        av_log(NULL, AV_LOG_ERROR, "No video stream found\n");
        return input->stream_idx;
    }

    // ④ 创建解码器
    AVStream *stream = input->fmt_ctx->streams[input->stream_idx];
    const AVCodec *decoder = avcodec_find_decoder(stream->codecpar->codec_id);
    input->codec_ctx = avcodec_alloc_context3(decoder);
    avcodec_parameters_to_context(input->codec_ctx, stream->codecpar);

    // 设置多线程解码
    input->codec_ctx->thread_count = 4;

    ret = avcodec_open2(input->codec_ctx, decoder, NULL);
    if (ret < 0) {
        av_log(NULL, AV_LOG_ERROR, "Cannot open decoder\n");
        return ret;
    }

    return 0;
}

/**
 * 创建输出 MP4 文件，创建 H.264 编码器
 */
int open_output(const char *filename, OutputStream *output,
                InputStream *input) {
    int ret;

    // ① 分配输出 AVFormatContext
    avformat_alloc_output_context2(&output->fmt_ctx, NULL, "mp4", filename);
    if (!output->fmt_ctx) {
        av_log(NULL, AV_LOG_ERROR, "Cannot create output context\n");
        return AVERROR_UNKNOWN;
    }

    // ② 查找 H.264 编码器 (libx264)
    const AVCodec *encoder = avcodec_find_encoder(AV_CODEC_ID_H264);
    if (!encoder) {
        av_log(NULL, AV_LOG_ERROR, "H.264 encoder not found\n");
        return AVERROR_ENCODER_NOT_FOUND;
    }

    output->codec_ctx = avcodec_alloc_context3(encoder);

    // ③ 设置编码参数
    AVCodecContext *c = output->codec_ctx;
    c->width     = input->codec_ctx->width;      // 保持原始分辨率
    c->height    = input->codec_ctx->height;
    c->time_base = input->fmt_ctx->streams[input->stream_idx]->time_base;
    c->framerate = input->fmt_ctx->streams[input->stream_idx]->avg_frame_rate;
    c->pix_fmt   = AV_PIX_FMT_YUV420P;           // H.264 通用像素格式
    c->bit_rate  = 4 * 1000 * 1000;              // 4 Mbps
    c->gop_size  = 30;                            // GOP = 30 帧 (1 秒 @30fps)
    c->max_b_frames = 2;                          // 允许 B 帧

    // ★ x264 高级参数: preset + tune
    av_opt_set(c->priv_data, "preset", "medium", 0);   // 编码速度/质量平衡
    av_opt_set(c->priv_data, "tune", "film", 0);        // 优化电影内容
    av_opt_set(c->priv_data, "profile", "high", 0);     // High Profile

    // ④ 打开编码器
    ret = avcodec_open2(c, encoder, NULL);
    if (ret < 0) {
        av_log(NULL, AV_LOG_ERROR, "Cannot open encoder\n");
        return ret;
    }

    // ⑤ 创建输出流
    output->stream = avformat_new_stream(output->fmt_ctx, NULL);
    avcodec_parameters_from_context(output->stream->codecpar, c);
    output->stream->time_base = c->time_base;
    output->stream_idx = 0;

    // ⑥ 写文件头 (MP4 ftyp + moov 占位)
    ret = avformat_write_header(output->fmt_ctx, NULL);
    if (ret < 0) {
        av_log(NULL, AV_LOG_ERROR, "Cannot write header\n");
        return ret;
    }

    return 0;
}

/**
 * 执行转码
 */
int transcode(InputStream *input, OutputStream *output) {
    AVPacket *pkt = av_packet_alloc();
    AVFrame *frame = av_frame_alloc();
    AVPacket *enc_pkt = av_packet_alloc();

    while (1) {
        // ① 从输入文件读取压缩数据包
        int ret = av_read_frame(input->fmt_ctx, pkt);
        if (ret < 0) break;

        // 只处理视频流
        if (pkt->stream_index != input->stream_idx) {
            av_packet_unref(pkt);
            continue;
        }

        // ② 送入解码器
        ret = avcodec_send_packet(input->codec_ctx, pkt);
        av_packet_unref(pkt);
        if (ret < 0) break;

        // ③ 循环取出解码帧
        while (avcodec_receive_frame(input->codec_ctx, frame) >= 0) {

            // ★ 修正 PTS（从输入流时间基映射到输出流时间基）
            frame->pts = frame->pts;

            // ④ 送入编码器
            ret = avcodec_send_frame(output->codec_ctx, frame);
            av_frame_unref(frame);
            if (ret < 0) break;

            // ⑤ 循环取出编码后的包
            while (avcodec_receive_packet(output->codec_ctx, enc_pkt) >= 0) {

                // ★ 转换时间基 (编码器时间基 → 输出流时间基)
                av_packet_rescale_ts(enc_pkt,
                    output->codec_ctx->time_base,
                    output->stream->time_base);
                enc_pkt->stream_index = 0;

                // ⑥ 写入输出文件 (封装)
                ret = av_interleaved_write_frame(output->fmt_ctx, enc_pkt);
                av_packet_unref(enc_pkt);
                if (ret < 0) {
                    av_log(NULL, AV_LOG_ERROR, "Write frame error\n");
                    break;
                }
            }
        }
    }

    // ⑦ Flush 编码器: 发送 NULL frame 获取所有缓存帧
    avcodec_send_frame(output->codec_ctx, NULL);
    while (avcodec_receive_packet(output->codec_ctx, enc_pkt) >= 0) {
        av_packet_rescale_ts(enc_pkt,
            output->codec_ctx->time_base,
            output->stream->time_base);
        enc_pkt->stream_index = 0;
        av_interleaved_write_frame(output->fmt_ctx, enc_pkt);
        av_packet_unref(enc_pkt);
    }

    // ⑧ 写文件尾 (更新 moov box)
    av_write_trailer(output->fmt_ctx);

    av_packet_free(&pkt);
    av_frame_free(&frame);
    av_packet_free(&enc_pkt);
    return 0;
}

// ─── 主入口 ──────────────────────────────────────────────
int main(int argc, char **argv) {
    if (argc < 3) {
        fprintf(stderr, "Usage: %s <input> <output.mp4>\n", argv[0]);
        return 1;
    }

    InputStream input = {0};
    OutputStream output = {0};

    if (open_input(argv[1], &input) < 0) return 1;
    if (open_output(argv[2], &output, &input) < 0) return 1;

    transcode(&input, &output);

    // 释放资源
    avcodec_free_context(&input.codec_ctx);
    avformat_close_input(&input.fmt_ctx);
    avcodec_free_context(&output.codec_ctx);
    avformat_free_context(output.fmt_ctx);

    printf("Transcode complete: %s → %s\n", argv[1], argv[2]);
    return 0;
}
```

### 5.2 转码关键注意事项

| 注意事项 | 详细说明 |
|----------|---------|
| **时间基转换** | 解码帧的 PTS 基于输入流 time_base，编码后需要 `av_packet_rescale_ts()` 转换到输出流 time_base，否则音视频不同步 |
| **x264 预编译** | FFmpeg 默认不包含 x264（GPL 协议问题），需要 `--enable-libx264 --enable-gpl` 编译。Android 上可用 `libx264` 软编或用 MediaCodec 替代 |
| **B 帧处理** | B 帧会导致解码/显示顺序不一致，`av_interleaved_write_frame()` 会自动按 DTS 排序写入 |
| **交错写入** | 使用 `av_interleaved_write_frame()` 而非 `av_write_frame()`，确保音视频包按时间交错写入 |
| **多路输出** | 同时有音视频流时，需要分别创建解码器和编码器，并将两个流都写入输出文件 |
| **内存峰值** | 转码过程中 max_b_frames=2 时，编码器可能缓存 2~3 帧后才输出第一个 I 帧，注意 AVFrame 生命周期 |
| **Faststart** | `av_dict_set(&opts, "movflags", "faststart", 0)` 将 moov box 移到文件开头，使 MP4 可边下边播 |

---

## 六、面试速查卡

| 问题 | 一句话答案 |
|------|-----------|
| FFmpeg 核心模块 | libavformat(解封装/封装) + libavcodec(编解码) + libavutil(工具) + libswscale(图像缩放) + libswresample(音频重采样) + libavfilter(滤镜) |
| avformat_open_input 做了什么 | 探测容器格式 → 调用 read_header 解析文件头 → 创建 AVStream → 填充 codecpar(codec_id/width/height/extradata) |
| avcodec_send_packet / receive_frame | 生产者-消费者模型：send 送入压缩数据，receive 取出解码帧，解耦输入输出，支持 B 帧重排和 decoder flush |
| Android 交叉编译关键步骤 | 指定 NDK clang 工具链 → configure 设置 target-os=android + arch + cross-prefix → enable 需要的模块 → make |
| 交叉编译减小体积 | `--disable-everything` + 按需启用 decoder/encoder/demuxer/muxer/protocol/parser/filter |
| FFmpeg vs MediaCodec | 硬编硬解=低功耗低延迟（录制/直播/播放优先）；软编软解=全格式高画质可控（转码/编辑/兜底） |
| yuv→rgb 用哪个模块 | libswscale 的 `sws_scale()`，支持多种像素格式转换和缩放 |
| 解码帧内存管理 | `av_frame_alloc()/av_frame_free()` 分配/释放；`av_frame_unref()` 释放引用但不释放结构体（可复用） |
| 如何让转码后的 MP4 支持流式播放 | 输出时设置 `movflags=+faststart`，将 moov box 移到 mdat 前面 |
| 为什么 send_packet 返回 EAGAIN | 解码器内部缓冲区已满，需要先调用 receive_frame 将解码帧取走 |

---

## 七、延伸学习

- [FFmpeg 官方文档](https://ffmpeg.org/documentation.html)
- [FFmpeg Wiki: H.264 Encoding Guide](https://trac.ffmpeg.org/wiki/Encode/H.264)
- [Android NDK + FFmpeg 交叉编译脚本示例](https://github.com/tanersener/mobile-ffmpeg) (Mobile-FFmpeg)
- [FFmpeg 源码结构分析](https://github.com/FFmpeg/FFmpeg)
- [浅析 FFmpeg 新解码 API (send/receive)](https://ffmpeg.org/doxygen/trunk/group__lavc__encdec.html)
- [MP4 文件格式详解 — ISO Base Media File Format](https://www.iso.org/standard/68960.html)
- [Android MediaCodec + FFmpeg 混合播放器架构参考](https://github.com/google/ExoPlayer) (ExoPlayer 内部同时支持 MediaCodec 和 FFmpeg 扩展)

---

*最后更新：2026-05-08*
