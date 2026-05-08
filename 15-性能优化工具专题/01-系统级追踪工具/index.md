# 系统级追踪工具 — 面试深度解析

> 六层递进：从面试八股到手撕源码，从架构原理到实战案例，全方位吃透 Systrace / Perfetto

---

## 第一层：面试八股 —— 5+ 高频问题精析

### Q1：Systrace 的常用命令行参数有哪些？如何使用 `Trace.beginSection` 做自定义埋点？

**命令行使用**是面试中最基础但必须通关的环节。Systrace 基于 Python 脚本驱动，核心命令：

```bash
# 基础用法：抓取 10 秒，收集 sched/freq/gfx/view/wm/am
python systrace.py -t 10 -o trace.html sched freq gfx view wm am

# 常用参数速查
-t N        # 抓取时长（秒），默认 5s
-o FILE     # 输出文件（.html 或 .ctrace）
-b N        # buffer 大小（KB），默认取决于类别，大 trace 建议 32768+
-a PACKAGE  # 只追踪指定进程（可多次使用）
-l          # 列出所有可用 category
--no-fix-threads  # 保留原始线程名
```

**`Trace.beginSection` 自定义埋点**是 "手撕源码" 级考点。Android 提供了三层埋点 API：

| 层级 | API | 适用场景 |
|:---|:---|:---|
| Java/Kotlin | `android.os.Trace.beginSection("name")` | 业务层：Activity/Fragment/View |
| Native C/C++ | `ATrace_beginSection("name")` | JNI/NDK 层逻辑 |
| 系统服务 | `Trace.traceBegin(Trace.TRACE_TAG_ACTIVITY_MANAGER, "name")` | 系统服务内部 |

**关键面试追问**：
- *beginSection 和 endSection 不成对调用会怎样？* 答：trace 文件会损坏或丢失该 section 的闭合标记，Chrome 渲染时出现错位，Perfetto 则直接拒绝解析跨线程的不匹配调用。
- *beginSection 的字符串长度限制？* 答：内部通过 `PROPERTY_VALUE_MAX=92` 裁剪，过长会被截断。
- *生产环境能用吗？* 答：`Trace.isEnabled()` 做前置判断，避免在非 trace 场景下拼接无用的 section 字符串。

```kotlin
// Kotlin 最佳实践
if (Trace.isEnabled()) {
    Trace.beginSection("LaunchActivity#onCreate")
}
// ... 业务代码 ...
if (Trace.isEnabled()) {
    Trace.endSection()
}
```

---

### Q2：Perfetto vs Systrace，你选谁？从架构到场景全面对比

| 维度 | Perfetto | Systrace (atrace 引擎) |
|:---|:---|:---|
| **定位** | Android 10+ 新一代全系统追踪平台 | Android 4.1~9 传统工具（已 deprecated） |
| **数据源** | ftrace + heapprofd + traced_perf + 自定义 data source | ftrace (atrace 是 ftrace 的 Android 封装) |
| **内存追踪** | ✅ 原生 heapprofd，支持 native/java heap profiling | ❌ 需要配合 MAT/Android Profiler |
| **功耗分析** | ✅ 关联 batterystats | ❌ 不支持 |
| **录制方式** | adb shell perfetto 命令行 / `record_android_trace` 脚本 / 系统内置开发者选项 UI | adb shell atrace + systrace.py |
| **文件格式** | `.perfetto-trace`（ProtoBuf 二进制压缩） | `.ctrace` 或 HTML |
| **文件大小** | 秒级抓取 MB 级别（压缩比 ~10:1），支持长达小时级录制 | HTML 动辄 GB，实测 30s 抓取约 2GB |
| **跨平台** | Web UI + trace_processor (Python/C++) Linux/Mac/Windows | 仅 Chrome 浏览器渲染 |
| **SQL 查询** | ✅ trace_processor 支持标准 SQL 分析 | ❌ 仅可视浏览，无编程分析能力 |
| **Android 版本支持** | Android 4.2+ (部分功能需 10+) | Android 4.1+，Android 10 起被 Perfetto 接管 |
| **生产环境采集** | ✅ 极低开销，可在 release 版安全使用 | ⚠️ 开销较大，生产慎用 |
| **环形缓冲区** | ✅ 支持，可只保留崩溃前 N 秒 trace | ❌ 不支持 |

**面试标准答案**：
> Systrace 是 Android 一代 trace 工具，本质是 atrace + Chrome 渲染引擎，已经官方 deprecated。Perfetto 是二代全栈平台，除了覆盖 Systrace 的 CPU/GPU/IO 追踪外，还集成了内存、功耗分析，提供 SQL 化分析能力。在新项目（Android 10+）中应优先使用 Perfetto，老版本设备仍可 fallback 到 Systrace。面试的关键加分点是能说出 Perfetto 的"**录制→分析→SQL 查询**"三层解耦架构。

---

### Q3：如何解读 trace 文件中的关键指标？CPU/GPU/IO/线程状态怎么看？

**线程状态**是 trace 解读的核心。每个线程的 "Running/Runnable/Sleeping/Uninterruptible Sleep" 是面试考察重点：

| 线程状态 | 颜色 | 含义 | 性能排查方向 |
|:---|:---|:---|:---|
| **Running** | 绿色 | 线程正在 CPU 上执行 | 关注这段 CPU 时间片内具体执行了什么函数 |
| **Runnable** | 蓝色 | 线程就绪但未分配到 CPU | **CPU 争抢严重** — 需要降负载/开核/提频/绑核 |
| **Sleeping** | 白色/灰色 | 线程主动休眠（Binder 等待/mutex/sleep） | **依赖阻塞** — 等 Binder 回复、等锁、等 I/O |
| **Uninterruptible Sleep** | 橙色（D 状态） | 内核 I/O 等待（Disk/GPU） | **I/O 瓶颈** — 磁盘读写慢、GPU 渲染压力大 |
| **Sched-Freq** | 蓝→红渐变色 | CPU 频率曲线 | 频率被压低→温控限频/省电模式 |

**CPU 指标解读方法**：
1. **CPU Duration per Core**：每核任务分布，观察是否单核过载
2. **sched_switch**：上下文切换频率，高频切换说明线程过多
3. **freq**：各核运行频率曲线，结合温控判断是否被限频
4. **C-State**：核心的 idle/C1/C2 深度休眠状态

**GPU 指标解读**：
- `mdss_fb0`/`kgsl` 是高通平台 GPU 渲染 tracepoint
- 关注 SurfaceFlinger `postFramebuffer` 的间隔是否超 16.6ms
- GPU 队列积压 → `dequeueBuffer` 长时间返回 → BufferQueue 空

**I/O 指标解读**：
- `ext4_sync_file_enter`/`ext4_sync_file_exit`：同步写延迟
- `f2fs`（Android 主流文件系统）相关 tracepoint
- 应用启动时 I/O 密集 → `open`/`read`/`mmap`/`dex2oat` system calls

---

### Q4：自定义 Trace — Native 层 `ATrace` + Java 层 `Trace` 完整方案

**Java 层**：
```java
// 在 android.jar 中，源码位于 frameworks/base/core/java/android/os/Trace.java
public class MyActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        Trace.beginSection("MyActivity#onCreate");
        super.onCreate(savedInstanceState);
        // ... 布局初始化 ...
        Trace.endSection();
    }
}
```

**Native 层（NDK / C++）**：
```cpp
#include <android/trace.h>

void heavyComputation() {
    ATrace_beginSection("HeavyCompute");
    // ... 复杂计算、JNI 调用 ...
    ATrace_endSection();
}
```

**编译要求**：
- CMakeLists.txt：`target_link_libraries( yourlib android )`
- Android.mk：`LOCAL_LDLIBS += -landroid`

**面试进阶追问 — ATrace vs TraceTag 的区别**：

| 对比 | `Trace.beginSection` / `ATrace_beginSection` | `Trace.traceBegin(long tag, String)` |
|:---|:---|:---|
| 层级 | 应用层埋点 | 系统服务内部埋点 |
| tag | 无需 tag，统一走 `TRACE_TAG_APP` | 需指定 tag（如 `TRACE_TAG_ACTIVITY_MANAGER`） |
| 开关 | 受 `traceApps` 控制 | 受各自的 tag 控制 |
| 典型调用方 | App 业务代码 | AMS/WMS/SurfaceFlinger 等 |

---

### Q5：从 Systrace 中定位"启动慢"和"卡顿"问题的实战方法论

**启动慢三大嫌疑**：

> ⚠️ 面试中的启动分析必须区分两种"慢"：**CPU 慢**（主线程在做大量计算） vs **等待慢**（主线程等 Binder/锁/I/O）。

```
冷启动时间线（从 trace 中识别）：
  Zygote fork ──→ bindApplication ──→ Activity onCreate ──→ createWindow
  ──→ Resume（首帧）──→ Vsync-SF ──→ Vsync-app ──→ 完全显示
```

**关键 trace 阶段**：
1. `bindApplication` → `Activity onCreate` 间隔：**Application 初始化耗时**（ContentProvider、第三方 SDK Init）
2. `onCreate` → `onResume`：**UI 创建 + 布局 inflate**
3. `onResume` → `drawFrame` → `reportFullyDrawn`：**首帧渲染**
4. 主线程 Binder 等待（等 AMS/WMS 回复）→ 本质是系统服务的串行化

**卡顿定位五步法**：

| 步骤 | 操作 | Trace 信号 |
|:---|:---|:---|
| ① 找帧间隔 | 切到 Frames slice（绿色长条即 janky frame） | Frame duration > 16.6ms |
| ② 看主线程 | 点进 janky frame，观察 main thread 状态 | Runnable（等 CPU）vs Sleeping（等 Binder）vs Running（CPU 慢） |
| ③ 查 Binder | 主线程 Sleeping 时切到 Binder 代理线程 | 看是等哪个服务的哪个方法返回 |
| ④ 查 CPU | 如果是 Runnable，看此时各核 Running 的线程 | 其他线程是否正在大量占用 CPU |
| ⑤ 查 I/O | 橙色 D 状态 + ext4 tracepoint | 定位同步写/读导致的阻塞 |

---

## 第二层：Perfetto 三层架构 & ftrace 机制

### Perfetto 的三层解耦设计：tracing → recording → analysis

```
┌─────────────────────────────────────────────────┐
│                  analysis 层                     │
│   trace_processor (C++/Python)                  │
│   → SQL query engine                            │
│   → lib/ for stats/analysis                     │
│   → Perfetto UI (Web-based viewer)              │
├─────────────────────────────────────────────────┤
│                  recording 层                    │
│   traced (system daemon)                        │
│   → 管理所有 data source 生命周期               │
│   → 内存环形缓冲区管理                          │
│   → 触发录制 (CLI / 开发者选项 / config)        │
├─────────────────────────────────────────────────┤
│                  tracing 层                      │
│   Data Sources:                                 │
│   ftrace · /proc/sysrq-trigger                  │
│   heapprofd · heap profiling                    │
│   traced_perf · perf events                     │
│   atrace · Android trace events                 │
│   statsd · Android metrics                      │
│   Custom data sources (C++/Java)                │
└─────────────────────────────────────────────────┘
```

- **tracing 层**：真正的数据生产者。所有 data source 把事件写入 shared memory buffer
- **recording 层**：`traced` 守护进程负责管理 buffer、触发录制、序列化到文件
- **analysis 层**：`trace_processor` 把 proto 解析为 SQLite 数据库，支持 SQL 查询

**面试加分点**：Perfetto 的 shared memory buffer 是无锁的设计，通过 `SharedMemoryArbiter` 实现跨进程写入，开销极低（典型 < 0.1% CPU）。

### ftrace / tracepoint 机制

**ftrace** 是 Linux 内核的追踪基础设施，所有用户态 trace 工具在 Android 上都依赖它：

```
用户态                                   内核态
 ┌────────────┐         ┌──────────────────────────────┐
 │  Systrace   │──┐      │  tracefs (/sys/kernel/tracing)│
 │  (atrace)   │ ─┤ echo  │  ┌─────────────────────────┐ │
 └────────────┘  │──────→│  │ tracepoint:              │ │
 ┌────────────┐  │       │  │  sched/sched_switch       │ │
 │  Perfetto   │──┘       │  │  sched/sched_wakeup      │ │
 │  (traced)   │          │  │  binder/binder_transaction│ │
 └────────────┘          │  │  power/cpu_frequency      │ │
                         │  └─────────────────────────┘ │
                         └──────────────────────────────┘
```

**tracepoint** 是内核源代码中预埋的静态埋点（`TRACE_EVENT` 宏）：
- 编译时注册到 `tracefs`
- 运行时通过写入 `tracefs` 的 `enable` 文件来开关
- **零开销**：关闭时经过一个 `unlikely` 分支，对性能几乎无影响

**Android 关键 tracepoint 速查表**：

| tracepoint | 用途 | 分析场景 |
|:---|:---|:---|
| `sched/sched_switch` | 线程切换 | CPU 调度分析、线程状态图 |
| `sched/sched_wakeup` | 线程唤醒 | 分析唤醒延迟（wakeup → running 的间隔） |
| `binder/binder_transaction` | Binder 跨进程通信 | 识别 Binder 调用链、数据大小、回复延迟 |
| `binder/binder_transaction_received` | Binder 接收端 | 服务端处理耗时 |
| `power/cpu_frequency` | CPU 频率变化 | 限频分析 |
| `power/cpu_idle` | CPU C-State | 核心休眠深度 |
| `gfx/drm_vblank_event` | DRM VSYNC | 帧周期起点 |
| `mdss/mdp_video_underrun` | GPU 掉帧信号 | 渲染跟不上刷新率 |
| `irq/irq_handler_entry` | 硬中断 | 中断风暴排查 |
| `block/block_rq_issue` | 块设备 I/O 请求 | 磁盘 I/O 耗时 |

---

## 第三层：Choreographer 帧信息深度解读

### 帧的三种状态：跳过 / 卡顿 / 冻结

Choreographer 在 Systrace 中输出 Frames slice，Android S+ 的 Perfetto 有专门的 `android_surface` 表：

| 状态 | 判定标准 | 颜色 | 用户体感 |
|:---|:---|:---|:---|
| **绿色** | 实际帧耗时 ≤ 预期帧耗时 | 绿 | 流畅 |
| **黄色** | 实际帧耗时 > 预期帧耗时，但 < 预期帧耗时 × 2 | 黄 | 轻微卡顿 |
| **红色** | 实际帧耗时 ≥ 预期帧耗时 × 2 | 红 | 明显卡顿 |
| **冻结** | 连续 700ms 无新帧 | 无 slice | ANR 前兆 |

### 实际帧耗时 vs 预期帧耗时

```
预期帧耗时 = 1000ms / 刷新率(Hz)

  60Hz → 16.67ms
  90Hz → 11.11ms
 120Hz → 8.33ms
 144Hz → 6.94ms
```

**面试关键陷阱**：很多人以为"预期帧耗时 = 16.6ms"永远正确。**错！** 高刷屏（90Hz/120Hz/144Hz）的 deadline 更紧。必须通过 `adb shell dumpsys display | grep "mRefreshRate"` 动态获取。实际帧耗时 = `drawFrame` trace 的 wall duration，如果包含了 measure+layout+draw+sync+upload 全流程。

**帧的四个阶段**：

```
┌──────────┐  ┌───────────┐  ┌────────┐  ┌────────────┐
│  Input   │→│ Animation │→│  Draw  │→│  Composite  │
│  处理输入 │  │ Choreogr.  │  │ UI线程  │  │ SurfaceFlinger│
│          │  │  doFrame   │  │ +RenderThread│  │ 合成+送显  │
└──────────┘  └───────────┘  └────────┘  └────────────┘
    2ms           2ms           8ms           4ms
                              (易超标段)
```

### Choreographer 源码速通

```java
// frameworks/base/core/java/android/view/Choreographer.java
public void doFrame(long frameTimeNanos, int frame,
        DisplayEventReceiver.VsyncEventData vsyncEventData) {
    
    Trace.traceBegin(Trace.TRACE_TAG_VIEW, "Choreographer#doFrame");
    
    // 1. INPUT 回调
    doCallbacks(Choreographer.CALLBACK_INPUT, frameData, frameIntervalNanos);
    
    // 2. ANIMATION 回调  
    doCallbacks(Choreographer.CALLBACK_ANIMATION, frameData, frameIntervalNanos);
    
    // 3. INSETS_ANIMATION (Android 11+)
    doCallbacks(Choreographer.CALLBACK_INSETS_ANIMATION, frameData, frameIntervalNanos);
    
    // 4. TRAVERSAL（最重：measure/layout/draw）
    doCallbacks(Choreographer.CALLBACK_TRAVERSAL, frameData, frameIntervalNanos);
    
    // 5. COMMIT（提交事务到 RenderThread）
    doCallbacks(Choreographer.CALLBACK_COMMIT, frameData, frameIntervalNanos);
    
    Trace.traceEnd(Trace.TRACE_TAG_VIEW);
}
```

**性能瓶颈的分布规律**（来自 Google 内部统计）：
- **70%** 的 jank 发生在 `CALLBACK_TRAVERSAL`（measure/layout/draw）
- **15%** 发生在 Binder 等待（跨进程通信）
- **10%** 由 GC / I/O 导致
- **5%** 发生在 Input 处理和动画过度绘制

---

## 第四层：Systrace 火焰图分析示例

### 火焰图图谱（ASCII 示意）

```
                                调用栈深度
                                  ▲
                                  │
          ┌────────────────────────────────────────────────────┐
          │             onDraw()  [75ms 超标!]                  │  深度 8
          │   ┌──────────────────────────────────────────────┐ │
          │   │  drawText() [40ms]     drawBitmap() [30ms]   │ │  深度 7
          │   │  ┌──────────┐  ┌──────┴──────┐  ┌─────────┐│ │
          │   │  │measureText│  │decodeBitmap │  │  upload ││ │  深度 6
          │   │  │ [15ms]    │  │  [18ms]     │  │ [10ms]  ││ │
          │   │  └──────────┘  └─────────────┘  └─────────┘│ │
          │   └──────────────────────────────────────────────┘ │
          └────────────────────────────────────────────────────┘
          ┌────────────────────────────────────────────────────┐
          │               measure() [8ms]                       │  深度 5
          └────────────────────────────────────────────────────┘
          ┌────────────────────────────────────────────────────┐
          │        Binder: AMS.relaunchActivity [22ms]          │  深度 4
          │   ┌──────────────────────────────────────────────┐ │
          │   │  Waiting for lock (AMS lock contention)      │ │  深度 3
          │   └──────────────────────────────────────────────┘ │
          └────────────────────────────────────────────────────┘
```

### 火焰图分析三原则

| 原则 | 说明 |
|:---|:---|
| **宽度优先** | 水平宽度 = 耗时占比。哪个函数柱最宽，就是最大瓶颈 |
| **橙色警惕** | 橙色（Uninterruptible Sleep）= 正在等待 I/O。磁盘/GPU 是罪魁 |
| **蓝色警惕** | 蓝色（Runnable）= 线程准备好但没 CPU。需要提负载问题 |

---

## 第五层：冷启动问题完整案例分析

> **案例背景**：某电商 App，P50 冷启动耗时 2800ms，目标 ≤1500ms。设备：Snapdragon 8 Gen 2，Android 14。

### Step 1：抓取 Systrace

```bash
python systrace.py -t 15 -b 65536 \
  -a com.example.shop \
  -o cold_start_trace.html \
  sched freq gfx view wm am dalvik res binder_driver
```

> 关键 category 选择：`binder_driver` 捕获 Binder 驱动层信息，`dalvik` 捕获 GC 行为，`res` 捕获资源加载。

### Step 2：时间线分段分析

从 trace 中提取冷启动时间线（单位 ms，从 Zygote fork 起始为 0）：

```
  0ms  Zygote fork 完成，进程创建
 12ms  bindApplication 开始
 45ms  bindApplication 完成 → 进入 Application.onCreate()
  ├─ 45ms~780ms  Application.onCreate()  【735ms 异常！】
  │  ├─ 50ms  ContentProvider 初始化完成
  │  ├─ 50ms~350ms  第三方 SDK A 初始化（MMKV 冷加载）【300ms】
  │  ├─ 350ms~680ms 第三方 SDK B 初始化（网络库预热+DNS）【330ms】
  │  └─ 680ms~780ms Merge 子进程数据（SP 迁移）【100ms】
 780ms  进入 Activity.onCreate()
  └─ 780ms~1350ms  Activity 创建+首帧 【570ms】
     ├─ 780ms~850ms  setContentView (XML inflate) 【70ms】
     │   └─ 包含 3 层嵌套 RecyclerView inflate
     ├─ 850ms~1120ms 网络请求等待主线程 Binder 【270ms！】
     │   └─ 主线程 Sleeping: 等 OkHttp → DNS → connect()
     ├─ 1120ms~1280ms RecyclerView 首屏 bind+draw 【160ms】
     └─ 1280ms~1350ms SurfaceFlinger 合成 【70ms】
1350ms  首帧显示
1350ms~2800ms  后续异步任务持续占用 CPU
  └─ 主线程持续 Running + Runnable 交替出现
```

### Step 3：三个核心问题定位

**问题①：Application.onCreate() 耗 735ms — SDK 初始化串行化**

Root Cause：三个第三方 SDK 都在主线程 Application.onCreate() 里同步初始化。trace 中三个 `beginSection` 各自占据 300ms、330ms、100ms。

优化方案：
```kotlin
// Before: 串行 735ms
override fun onCreate() {
    SDK_A.init()
    SDK_B.init()
    mergeSPData()
}

// After: 懒加载 + 子线程 + IdleHandler 三管齐下
override fun onCreate() {
    // 只做必须的
    initCoreSDK()
    // IdleHandler: 首帧之后再初始化非关键 SDK
    Looper.myQueue().addIdleHandler {
        thread { SDK_A.init() }  // 子线程
        thread { SDK_B.init() }
        false
    }
}
```
优化后：Application.onCreate() 从 735ms → 80ms。

**问题②：主线程做网络请求 — 等 OkHttp DNS resolve**

Root Cause：首页数据请求在 Activity.onCreate() 中同步发起，虽然用了回调，但 `connect()`（含 DNS 解析）在主线程执行。trace 显示主线程 Binder Sleep 270ms。

优化方案：
```kotlin
// 方案一：预建连接（启动前 DNS 预热）
OkHttpClient.Builder()
    .addInterceptor { chain ->
        val builder = chain.request().newBuilder()
            .header("Host", "api.shop.com") // 提前 DNS 解析
        chain.proceed(builder.build())
    }

// 方案二：启动阶段不在主线程做任何网络 I/O
// 数据改为 MMKV 缓存 + 后台刷新
```

**问题③：RecyclerView 三层嵌套导致首帧 draw 160ms**

Root Cause：首页 RecyclerView 内部嵌套两个横向 RecyclerView，首屏 inflate 时递归 createViewHolder，trace 中 `onCreateViewHolder` 被调用 80+ 次。

优化方案：
- 扁平化布局（用 Custom View 替代嵌套 RecyclerView）
- `ViewStub` 延迟非首屏 item
- `RecyclerView.setRecycledViewPool()` 共享 View 池

### Step 4：优化后的结果

| 指标 | 优化前 | 优化后 | 降幅 |
|:---|:---|:---|:---|
| P50 冷启动 | 2800ms | 1180ms | **-57.8%** |
| Application.onCreate | 735ms | 80ms | **-89%** |
| 首帧渲染 | 570ms | 420ms | **-26%** |
| Jank 率 | 42% | 8% | **下降 34pp** |

---

## 第六层：完整的"启动分析"SOP（标准操作流程）

### 定位冷启动问题的完整 Checklist

```
Phase 1: 数据采集
├── □ 确认 Android 版本（决定用 Perfetto 还是 Systrace）
├── □ 确认设备刷新率（adb shell dumpsys display）
├── □ 冷启动 5 次 + 抓取 trace（每次 kill 进程：adb shell am force-stop）
├── □ 同时采集 logcat（adb logcat -b all -v threadtime）
└── □ 记录每次的 Displayed 时间（adb shell am start -W）

Phase 2: 时间线重建
├── □ 识别 Zygote fork 的时间戳（sched/sched_process_free）
├── □ 标记 bindApplication → Activity.onCreate → onResume → reportFullyDrawn
├── □ 拆解每段耗时，归类为 CPU / Binder / I/O / GC / 其他
└── □ 对每段打标签（可并行化？可后置？可提前？可去掉？）

Phase 3: 根因分析
├── □ CPU 瓶颈 → sched_switch 看抢占，freq 看限频
├── □ Binder 瓶颈 → binder_transaction 看服务端耗时
├── □ I/O 瓶颈 → ext4/f2fs tracepoint + mmap 延迟
├── □ GC 瓶颈 → dalvik tracepoint + GC pause time
└── □ 内存瓶颈 → heapprofd 或 MAT 配合分析

Phase 4: 优化 & 验证
├── □ 逐项优化，每项优化后用同一设备重新抓 trace
├── □ 对比 p50/p90/p99 分布（不能只看平均值）
├── □ 回归测试（低端机 + 高端机 + 压测场景）
└── □ 添加启动耗时监控埋点（线上 APM 长期追踪）
```

### 面试总结：当面试官问"如何用 Systrace 定位性能问题"

> **标准回答模板**：
>
> 第一步，通过命令行抓取 trace，包含 sched/freq/gfx/view/binder_driver 等核心 category。
>
> 第二步，在 Chrome 打开 trace.html，先看总 timeline 确认启动阶段的范围，定位到 bindApplication → 首帧显示 的关键节点。
>
> 第三步，按"线程状态→Binder→CPU→I/O"的顺序排查：
> - 如果主线程大量蓝色（Runnable），说明 CPU 争抢严重，需要降负载或提频
> - 如果大量白色（Sleeping），说明在等锁或等 Binder 回复，顺着 Binder 链路找到服务端
> - 如果出现橙色（D 态），说明在等 I/O，需要检查是否在主线程做了文件读写或 SharedPreferences 提交
>
> 第四步，定位到具体函数后，通过 Trace.beginSection/ATrace 做精细埋点，精确定位到代码行。
>
> 第五步，优化后重新抓 trace 验证，对比 p50/p90 分布。同时建立线上 APM 的启动监控，防止劣化。

---

## 附录：速查表

### Systrace 常用 Category

| Category | 覆盖范围 | 场景 |
|:---|:---|:---|
| `sched` | CPU 调度、线程状态 | 必选，分析 CPU 瓶颈 |
| `freq` | CPU 频率变化 | 限频分析 |
| `gfx` | 图形渲染（egl/vulkan） | 帧率、掉帧 |
| `view` | Choreographer/View 系统 | 布局/测量/绘制 |
| `wm` | Window Manager | 窗口管理 |
| `am` | Activity Manager | Activity 生命周期 |
| `binder` | Java Binder 层 | Binder 调用 |
| `binder_driver` | Binder 驱动层 | Binder 耗时精确测量 |
| `dalvik` | ART 虚拟机 | GC、JIT |
| `res` | 资源加载 | 图片解码、字体加载 |
| `database` | SQLite | 数据库操作 |
| `network` | 网络 I/O | 网络请求耗时 |

### Perfetto SQL 速查（trace_processor）

```sql
-- 1. 冷启动各阶段耗时
SELECT slice.name, slice.dur/1000000 AS dur_ms
FROM slice JOIN process_track ON slice.track_id = process_track.id
  JOIN process USING(upid)
WHERE process.name = 'com.example.app'
  AND (slice.name LIKE '%bindApplication%'
    OR slice.name LIKE '%onCreate%'
    OR slice.name LIKE '%reportFullyDrawn%')
ORDER BY slice.ts;

-- 2. 主线程 Jank 帧统计
SELECT COUNT(*) AS janky_frames
FROM android_frame_stats
WHERE app_pid = (SELECT upid FROM process WHERE name = 'com.example.app')
  AND frame_dur > 16600000;  -- 16.6ms in ns

-- 3. 最耗 CPU 的前 5 个函数
SELECT name, SUM(dur) AS total_dur
FROM slice JOIN thread_track ON slice.track_id = thread_track.id
WHERE thread_track.utid = (SELECT utid FROM thread WHERE name = 'main')
GROUP BY name ORDER BY total_dur DESC LIMIT 5;
```

---

> **本文档定位**：面试导向的系统级追踪工具深度解析，覆盖 Systrace/Perfetto 从命令行使用到源码原理、从理论到实战的完整知识体系。建议配合实际的 trace 文件练习以达到最佳学习效果。
