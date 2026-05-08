# 异常监控体系 — 面试深度剖析

> **面试权重**: ★★★★☆ | **字数**: ~7500 字 | **阅读时间**: 约 30 分钟

---

## 目录

1. [面试高频问题](#1-面试高频问题)
2. [标准答案与监控架构图](#2-标准答案与监控架构图)
3. [核心原理深度剖析](#3-核心原理深度剖析)
4. [流程图：异常从采集到告警的完整链路](#4-流程图异常从采集到告警的完整链路)
5. [源码分析：核心采集器的实现](#5-源码分析核心采集器的实现)
6. [监控体系建设实践案例](#6-监控体系建设实践案例)

---

## 1. 面试高频问题

### Q1：异常监控体系的建设思路是什么？从采集到止损的完整链路如何设计？

这道题考察你是否具备从零搭建一套监控体系的系统性思维。面试官想听到的不是某个工具的配置方法，而是 **采集 → 聚合 → 告警 → 止损** 四层递进架构，以及每层的技术选型和关键设计决策。对于高级/资深岗位，还需要能说出分级告警策略、SLA 定义、以及如何在「不漏报」和「不误报」之间取得平衡。

### Q2：Crash 率之外还有哪些关键质量指标？如何衡量一个 App 的线上健康度？

面试官想考察你是否跳出了「Crash 率 KPI」的单一维度认知。你需要说出 ANR 率、启动成功率、网络请求成功率、页面渲染帧率 (FPS)、内存 OOM 率、安装包增量监控等指标，并解释每个指标的业务含义和合理阈值。更深层次地，你需要理解「北极星指标」的概念——对不同类型的 App（社交、游戏、工具），核心质量指标是不同的。

### Q3：线上问题定位的闭环流程是什么？从收到告警到最终修复，中间经历了哪些环节？

这道题考察你完整的问题处理能力。完整闭环包括：告警触达 → 信息聚合（Crash 堆栈/用户路径/设备信息/自定义日志）→ 聚合分类（符号化+聚类算法）→ 原因定位 → 分配责任人 → 修复上线 → 回归验证 → 复盘沉淀。面试官尤其关注你如何做**问题聚合**——一个根因可能产生数百条不同堆栈的 Crash，如何将它们归类为同一条 Issue。

### Q4：APM 平台的核心指标和告警策略如何制定？

你需要说出 APM 的四大黄金信号：延迟 (Latency)、流量 (Traffic)、错误 (Errors)、饱和度 (Saturation)。告警策略需要分级：P0 致命告警（Crash 率环比 >200%、启动成功率跌破 95%）→ 即时电话+群通知；P1 严重告警（ANR 率破阈值、核心接口成功率 <99%）→ 5 分钟内告警群通知；P2 普通告警（卡顿率上升、内存峰值异常）→ 日报/周报汇总。

### Q5：如何设计 Crash 的符号化链路？Native Crash 和 Java Crash 在采集和解析上有什么区别？

Java Crash 的堆栈包含类名、方法名、行号，可直接阅读；而 Native Crash 的堆栈仅包含 .so 偏移地址（如 `libxxx.so + 0x1a2b3`），必须通过带符号表的 .so 或单独的 symbol 文件，使用 `addr2line` 或 `llvm-symbolizer` 还原为函数名+行号。符号化可以发生在客户端（增大包体）或服务端（推荐：上传时带 build_id → 服务端匹配符号表 → 还原后入库）。

### Q6：日志系统如何设计才能高效辅助线上问题定位？DropFrame 策略是什么？

关键设计原则：**分级输出 + 环形缓冲 + 抽样上报**。不应将所有 `Log.d()` 都上报，而是建立「Log → RingBuffer → 触发条件 → 快照上报」链路。DropFrame 是指当主线程单帧耗时超过阈值（如 100ms）时，记录当前主线程调用栈 + 帧耗时 + 发生时间，形成一组 DropFrame 日志，定期批量上报。这比全量堆栈采样的开销低 10 倍以上，同时能捕获瞬时性能尖峰。

---

## 2. 标准答案与监控架构图

### 2.1 异常监控体系总体架构（四层递进）

```
┌──────────────────────────────────────────────────────────────────────┐
│                        异常监控体系 — 四层递进                         │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐       │
│  │ 第四层   │    │          │    │          │    │ P0: 电话  │       │
│  │ 止损恢复 │◄───│  告警    │◄───│  聚合    │◄───│ P1: 群通知│       │
│  │ 自愈     │    │  策略    │    │  分析    │    │ P2: 日报  │       │
│  └────┬─────┘    └────┬─────┘    └────┬─────┘    └──────────┘       │
│       │               │               │                              │
│       ▼               ▼               ▼                              │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐       │
│  │·崩溃自愈 │    │·环比阈值 │    │·堆栈聚合 │    │  采集层   │       │
│  │ 热修复   │    │·同比阈值 │    │·聚类去重 │    │  六大模块  │       │
│  │·功能降级 │    │·多通道   │    │·用户聚合 │    │  实时上报  │       │
│  │·配置中心 │    │·静默期   │    │·智能指派 │    │  离线缓存  │       │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘       │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘

                            第一层：采集层（六大模块）

┌──────────────┬──────────────────────────────────────────────────────┐
│ 模块         │ 采集内容                      │ 采集方式              │
├──────────────┼──────────────────────────────────────────────────────┤
│ Java Crash   │ UncaughtException 栈、线程      │ Thread.setDefault     │
│              │ 状态、内存快照                   │ UncaughtExceptionHandler│
├──────────────┼──────────────────────────────────────────────────────┤
│ Native Crash │ 信号堆栈 (SIGSEGV/SIGABRT/     │ sigaction +           │
│              │ SIGFPE)、寄存器、maps           │ Google Breakpad/Bugly │
├──────────────┼──────────────────────────────────────────────────────┤
│ ANR 检测     │ 主线程堆栈、service/broadcast   │ getHistoricalProcess  │
│              │ 信息、CPU 使用率                │ ExitReasons (API 30+) │
├──────────────┼──────────────────────────────────────────────────────┤
│ 卡顿监控     │ Looper 消息耗时、DropFrame      │ Printer 替换 +        │
│              │ 帧信息、Choreographer 回调      │ FrameCallback 监控    │
├──────────────┼──────────────────────────────────────────────────────┤
│ 内存监控     │ Java Heap / Native Heap / PSS   │ Debug.MemoryInfo +    │
│              │ 周期性快照、OOM 预警             │ periodic 采样         │
├──────────────┼──────────────────────────────────────────────────────┤
│ 网络监控     │ HTTP/DNS/TCP 各阶段耗时、       │ OkHttp EventListener  │
│              │ 错误码分布、成功率               │ + 自建 httpdns 旁路   │
└──────────────┴──────────────────────────────────────────────────────┘
```

### 2.2 完整监控体系分层详解

| 层级 | 名称 | 核心职责 | 关键组件/技术 | 面试考察点 |
|:---:|:-----|:--------|:------------|:----------|
| L1 | **采集层** | 在客户端埋点，收集各类异常信号和性能数据 | Thread.UncaughtExceptionHandler、Breakpad、SignalCatcher、Printer 替换、OkHttp Interceptor | 如何保证采集不丢数据？如何控制采集开销？ |
| L2 | **传输层** | 数据压缩、加密、离线缓存、批量上报 | Protobuf 序列化、Gzip 压缩、MMKV 离线缓存、7z 符号表压缩 | 上报策略？弱网怎么办？数据怎么压缩？ |
| L3 | **聚合层** | 服务端接收 → 符号化 → 聚类去重 → 分配责任人 | 堆栈符号化服务、K-Means/DBSCAN 聚类、git blame 映射 | 如何高效聚类？符号化怎么做？ |
| L4 | **告警&止损层** | 实时监控指标、分级告警、自动化止损 | Prometheus + Grafana、P0-P4 分级、配置中心降级开关 | 如何避免告警风暴？如何自动止损？ |

---

## 3. 核心原理深度剖析

### 3.1 异常分层采集原理

异常采集并非「一把抓」，而是根据异常类型、紧急程度、采集成本进行**分层**——不同层级采用不同的采集策略和上报优先级。

```
                          ┌──────────────────┐
                          │   全量采集层       │
                          │  (Crash 必须全量)  │
                          │  · Java Crash      │
                          │  · Native Crash    │
                          │  · ANR             │
                          └────────┬─────────┘
                                   │ 100% 上报
                          ┌────────▼─────────┐
                          │   抽样采集层       │
                          │  (性能数据泛采)    │
                          │  · 卡顿堆栈 (10%)  │
                          │  · 启动耗时 (5%)   │
                          │  · 页面 FPS (3%)   │
                          └────────┬─────────┘
                                   │ 抽样+聚合 上报
                          ┌────────▼─────────┐
                          │   按需采集层       │
                          │  (用户触发/远程)   │
                          │  · 全量日志拉取    │
                          │  · 内存 dump       │
                          │  · 网络抓包        │
                          └──────────────────┘
```

**Java Crash 采集**（UncaughtExceptionHandler 链）：

```kotlin
// 核心采集器——必须在 Application.onCreate() 中第一个注册
object CrashCollector : Thread.UncaughtExceptionHandler {

    private var originalHandler: Thread.UncaughtExceptionHandler? = null
    private val pendingUploads = ConcurrentLinkedQueue<CrashData>()

    fun install() {
        originalHandler = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler(this)
    }

    override fun uncaughtException(thread: Thread, ex: Throwable) {
        // ★ 第一步：采集当前环境快照
        val crashData = CrashData(
            throwable = ex,
            threadName = thread.name,
            // 所有线程堆栈（类似 ANR trace）
            allThreadStacks = Thread.getAllStackTraces(),
            // 收集内存信息
            memInfo = collectMemInfo(),
            // 收集前序日志（环形缓冲区日志）
            recentLogs = LogBuffer.dump(),
            // 用户操作路径
            userTrail = UserTrailRecorder.getTrail(),
            timestamp = System.currentTimeMillis()
        )

        // ★ 第二步：持久化到磁盘（MMKV/文件），防止进程死亡丢失
        persistCrashData(crashData)

        // ★ 第三步：交给原始 Handler（Bugly/Firebase 等）
        originalHandler?.uncaughtException(thread, ex)
    }
}
```

**Native Crash 采集**（Signal 拦截机制）：

Native Crash 采集比 Java Crash 复杂得多。核心原理是通过 `sigaction()` 系统调用注册信号处理函数，当 Native 代码触发 `SIGSEGV`（段错误）、`SIGABRT`（断言失败）、`SIGFPE`（算术异常）等信号时，在信号处理函数中收集崩溃现场。

```
信号触发 (SIGSEGV/SIGABRT/SIGFPE/SIGBUS/SIGILL)
    │
    ▼
sigaction 注册的 signal_handler()
    │
    ├── 1. 保存寄存器现场 (ucontext_t)
    ├── 2. unwind 调用栈 (libunwind / libcorkscrew / fp unwinding)
    ├── 3. 收集内存映射 (/proc/self/maps)
    ├── 4. 生成 minidump 文件 (Breakpad 格式)
    ├── 5. 写入磁盘（安全操作：只能使用异步信号安全函数）
    │      write()、open()、mmap() — 不要用 malloc/printf
    └── 6. 恢复默认信号处理 → 再次 raise(signum) → 进程正常 crash
```

> **面试加分点**：Native Crash 采集的关键约束——信号处理函数中只能调用 **async-signal-safe** 函数。不能用 `printf`、`malloc`、`pthread_mutex_lock`，否则可能死锁或二次崩溃。Breakpad/Bugly 的实现使用 `write()` 系统调用直接写入文件描述符，并通过 pipe 与独立的 crash handler 进程通信。

### 3.2 日志系统设计：DropFrame → RingBuffer → 上报

日志系统的核心矛盾：**信息量 vs 开销**。全量采集所有日志会导致性能瓶颈和流量浪费，但太少又无法定位问题。

**三层日志架构**：

```
┌──────────────────────────────────────────────────────────────┐
│                      日志系统架构                              │
│                                                              │
│  业务代码                  采集引擎               上报引擎     │
│  ┌─────────┐            ┌─────────────┐        ┌──────────┐ │
│  │ Log.d()  │──Level过滤──► RingBuffer  │        │          │ │
│  │ Log.w()  │  (Release  │ (内存 512KB) │        │ 聚合上报  │ │
│  │ Log.e()  │   关Debug) │             │        │          │ │
│  └─────────┘            │ ┌─────────┐ │        │ 条件触发: │ │
│                          │ │ prev    │ │        │ ·Crash    │ │
│  ┌─────────┐            │ │ 500条   │ │─dump──►│ ·ANR      │ │
│  │ DropFrame│            │ │ 日志    │ │        │ ·手动上报 │ │
│  │ Detector│──帧耗时──►  │ └─────────┘ │        │ ·远程拉取 │ │
│  │ (>100ms)│            └──────┬──────┘        └──────────┘ │
│  └─────────┘                  │                              │
│        │                      ▼                              │
│        │              ┌──────────────┐                       │
│        └──堆栈采样────►│  采样策略     │                       │
│                       │ · Crash: 100%│                       │
│                       │ · 卡顿: 10% │                       │
│                       │ · 性能: 5%  │                       │
│                       └──────────────┘                       │
└──────────────────────────────────────────────────────────────┘
```

**RingBuffer 实现**（线程安全的环形日志缓冲区）：

```kotlin
object LogBuffer {
    private const val CAPACITY = 500 // 保留最近 500 条日志
    private val buffer = arrayOfNulls<LogEntry>(CAPACITY)
    private var writeIndex = 0L // AtomicLong

    @Synchronized
    fun append(level: Int, tag: String, msg: String) {
        buffer[(writeIndex++ % CAPACITY).toInt()] = LogEntry(
            time = SystemClock.uptimeMillis(),
            level = level,
            tag = tag,
            msg = msg,
            threadName = Thread.currentThread().name
        )
    }

    fun dump(): List<LogEntry> {
        // 返回按时间排序的最近日志快照
        return buffer.filterNotNull()
            .sortedBy { it.time }
    }
}
```

**DropFrame 检测器**（Choreographer 帧回调）：

```kotlin
class DropFrameDetector(private val thresholdMs: Long = 100) {

    private var lastFrameTimeNanos = 0L

    fun install() {
        Choreographer.getInstance().postFrameCallback(object : Choreographer.FrameCallback {
            override fun doFrame(frameTimeNanos: Long) {
                if (lastFrameTimeNanos > 0) {
                    val frameMs = (frameTimeNanos - lastFrameTimeNanos) / 1_000_000
                    if (frameMs > thresholdMs) {
                        // ★ 掉帧！记录主线程堆栈 + 帧耗时
                        recordDropFrame(frameMs)
                    }
                }
                lastFrameTimeNanos = frameTimeNanos
                Choreographer.getInstance().postFrameCallback(this)
            }
        })
    }

    private fun recordDropFrame(costMs: Long) {
        val stackTrace = Looper.getMainLooper().thread.stackTrace
        val dropEntry = DropFrameEntry(
            costMs = costMs,
            stackTrace = stackTrace,
            timestamp = System.currentTimeMillis()
        )
        DropFrameBuffer.append(dropEntry)
        // 累积 10 条后批量上报
        if (DropFrameBuffer.size() >= 10) {
            DropFrameReporter.upload(DropFrameBuffer.drain())
        }
    }
}
```

### 3.3 采样策略详解

| 异常类型 | 采集率 | 携带数据 | 上报优先级 | 设计理由 |
|:--------|:-----:|:--------|:---------:|:--------|
| **Java/Native Crash** | **100%** | 全量堆栈 + 全部线程 + logcat + 用户路径 | 实时（WiFi 立即 / 移动网络 5min 内） | 崩溃是最高优先级异常，一次也不能丢 |
| **ANR** | **100%** | trace 文件 + CPU usage + 前后台状态 | 实时（与 Crash 同优先级） | ANR 直接导致用户无法操作 |
| **主线程卡顿 (>2s)** | **100%** | 主线程堆栈 + 消息耗时 + 前后 20 条 LogBuffer | 准实时（10min 内） | 接近 ANR 的信号，需要完整现场 |
| **主线程卡顿 (200ms~2s)** | **10%** | 堆栈采样 + 帧耗时 | 批量（每小时） | 性能问题需要足够样本量而非单点 |
| **启动耗时** | **5%** | 启动各阶段耗时 + 设备信息 | 批量（每天） | 低开销、大样本足够反映趋势 |
| **页面 FPS** | **3%** | 页面名 + 平均 FPS + 最低 FPS | 批量（每天） | 仅用于大盘趋势，不需要个案 |
| **内存快照** | **1%** | MemoryInfo + 对象直方图 top 20 | 批量（每天上报 1 次） | 开销大，仅采样足够 |

> **关键设计原则**：采样率不是固定的，需要支持**动态下发**。当某个版本/某类设备的 Crash 率突然飙升，可以通过配置中心远程将相关采样率提升到 100%，在 10 分钟内完成问题定位。

---

## 4. 流程图：异常从采集到告警的完整链路

```
═══════════════════════════════════════════════════════════════════════
                    异常从采集到告警 — 完整链路 (端到端)
═══════════════════════════════════════════════════════════════════════

【客户端】                          【服务端】                   【运营/开发】

  用户操作
     │
     ▼
 ┌─────────┐
 │  异常发生 │ (Crash/ANR/卡顿/OOM/网络失败)
 └────┬────┘
      │
      ▼
 ┌──────────────────────────────────────┐
 │ ① 采集: 异常信号捕获                 │
 │  - UncaughtExceptionHandler (Java)    │
 │  - sigaction handler      (Native)    │
 │  - Printer 替换           (卡顿)      │
 │  - Debug.MemoryInfo       (内存)      │
 │  - EventListener          (网络)      │
 └────────────────┬─────────────────────┘
                  │
                  ▼
 ┌──────────────────────────────────────┐
 │ ② 快照: 收集异常现场                │
 │  - 堆栈 (主线程+所有子线程)           │
 │  - RingBuffer 前序日志 (500条)        │
 │  - 用户操作轨迹 (最近20步)            │
 │  - 设备状态 (内存/CPU/网络)           │
 │  - 自定义维度 (AB实验/灰度/渠道)      │
 └────────────────┬─────────────────────┘
                  │
                  ▼
 ┌──────────────────────────────────────┐
 │ ③ 本地处理: 序列化+压缩+缓存        │
 │  - 结构化: CrashData → Protobuf       │
 │  - 压缩: Gzip/7z (尤其trace文件)      │
 │  - 持久化: MMKV 离线缓存              │
 │  - 去重: 同堆栈5s内不重复上报         │
 └────────────────┬─────────────────────┘
                  │
                  ▼
 ┌──────────────────────────────────────┐
 │ ④ 上报策略: 根据网络和优先级        │
 │  - WiFi: 立即上报 (所有优先级)        │
 │  - 4G/5G: 实时(P0/P1) / 延迟(P2-P4) │
 │  - 无网络: 存入离线队列 → 恢复后补传  │
 │  - 限流: 单设备每小时 ≤ 50条上报     │
 └────────────────┬─────────────────────┘
                  │  HTTPS / Protobuf + Gzip
                  ▼
 ┌────────────────────────────────────────┐
 │ ⑤ 服务端接入层 (Gateway)              │
 │  - 鉴权 (app_id + secret)               │
 │  - 限流 (单app ≤ 10w qps)              │
 │  - 数据校验 (protobuf schema 验证)     │
 │  - 写入消息队列 (Kafka / RocketMQ)     │
 └────────────────┬───────────────────────┘
                  │
                  ▼
 ┌────────────────────────────────────────┐
 │ ⑥ 符号化服务 (Symbolization Service)   │
 │  - Java: 无需符号化 (堆栈已包含符号)    │
 │  - Native: build_id → 查符号表 →         │
 │    addr2line / llvm-symbolizer →        │
 │    还原函数名 + 行号                     │
 │  - 混淆: mapping.txt → retrace →        │
 │    还原原始类名/方法名                   │
 └────────────────┬───────────────────────┘
                  │
                  ▼
 ┌────────────────────────────────────────┐
 │ ⑦ 聚合分析 (Aggregation Cluster)       │
 │  - 堆栈特征提取 (归一化)                 │
 │  - K-Means / DBSCAN 聚类               │
 │  - 同 Issue 合并 (不同设备/OS版本)       │
 │  - git blame → 分配责任人               │
 └────────────────┬───────────────────────┘
                  │
                  ▼
 ┌────────────────────────────────────────┐
 │ ⑧ 指标计算 & 告警判定                 │
 │  - 实时指标:                            │
 │    · Crash rate (窗口: 5min/1h/24h)     │
 │    · ANR rate / 启动成功率 / 网络       │
 │  - 环比检测:                            │
 │    · Crash rate 环比 >200% ? → P0       │
 │    · ANR rate > 阈值 ?     → P1         │
 │  - 新增 Issue 检测:                     │
 │    · 出现新聚类 Issue → P1              │
 └────────────────┬───────────────────────┘
                  │
      ┌───────────┼───────────────┐
      ▼           ▼               ▼
 ┌─────────┐ ┌─────────┐   ┌─────────┐
 │ P0 电话  │ │P1 群通知│   │P2 日报  │
 │ + 短信   │ │+ 飞书群 │   │+ 周报   │
 └────┬────┘ └────┬────┘   └────┬────┘
      │           │               │
      └───────────┼───────────────┘
                  ▼
 ┌────────────────────────────────────────┐
 │ ⑨ 止损恢复 (自动化)                   │
 │  - 配置中心: 下发功能降级开关           │
 │  - 热修复: 下发 Tinker/Sophix 补丁     │
 │  - 版本回退: 触发灰度版本自动回滚       │
 │  - 通知: 「已启动止损预案，正在修复中」 │
 └────────────────────────────────────────┘
```

---

## 5. 源码分析：核心采集器的实现

### 5.1 Java Crash 采集器（完整实现）

```kotlin
// ========== 完整的企业级 Crash 采集器 ==========

class EnterpriseCrashHandler private constructor() : Thread.UncaughtExceptionHandler {

    private var originalHandler: Thread.UncaughtExceptionHandler? = null
    private var crashListener: CrashListener? = null

    companion object {
        @Volatile private var INSTANCE: EnterpriseCrashHandler? = null

        fun install(callback: CrashListener? = null): EnterpriseCrashHandler {
            return INSTANCE ?: synchronized(this) {
                INSTANCE ?: EnterpriseCrashHandler().also { handler ->
                    handler.crashListener = callback
                    handler.originalHandler = Thread.getDefaultUncaughtExceptionHandler()
                    Thread.setDefaultUncaughtExceptionHandler(handler)
                }
            }
        }
    }

    override fun uncaughtException(thread: Thread, ex: Throwable) {
        // ★ 第一步：静默收集，避免二次异常
        try {
            collectAndPersist(thread, ex)
        } catch (e: Exception) {
            // 采集过程自身出现异常，写入错误日志但不中断
            android.util.Log.e("CrashHandler", "Collection failed", e)
        }

        // ★ 第二步：回调业务层
        try {
            crashListener?.onCrash(ex)
        } catch (_: Exception) {}

        // ★ 第三步：交给原始 Handler（Bugly / Firebase）
        if (originalHandler != null && originalHandler != Thread.getDefaultUncaughtExceptionHandler()) {
            originalHandler!!.uncaughtException(thread, ex)
        } else {
            // 没有原始 Handler → 直接杀进程
            android.os.Process.killProcess(android.os.Process.myPid())
            System.exit(10)
        }
    }

    private fun collectAndPersist(thread: Thread, ex: Throwable) {
        // 1. 收集所有线程堆栈
        val allThreads = Thread.getAllStackTraces()

        // 2. 收集内存统计
        val memInfo = collectMemoryInfo()

        // 3. 收集用户操作轨迹
        val userTrail = UserTrailRecorder.getRecentTrail(20)

        // 4. 收集前序日志（RingBuffer）
        val recentLogs = LogBuffer.dump()

        // 5. 收集进程状态
        val procInfo = mapOf(
            "pid" to android.os.Process.myPid(),
            "uptime_ms" to SystemClock.uptimeMillis(),
            "process_name" to getProcessName(),
            "app_version" to BuildConfig.VERSION_NAME,
            "app_version_code" to BuildConfig.VERSION_CODE,
            "os_version" to Build.VERSION.SDK_INT,
            "device_model" to Build.MODEL,
            "device_brand" to Build.BRAND,
            "abi" to Build.SUPPORTED_ABIS?.joinToString(),
            "is_rooted" to isDeviceRooted(),
            "available_memory_mb" to getAvailableMemoryMB()
        )

        // 6. 结构化为 CrashData
        val crashData = CrashData(
            throwable = ex,
            threadInfo = ThreadInfo(thread.name, thread.state.name),
            allThreadStacks = allThreads.mapKeys { it.key.name },
            memoryInfo = memInfo,
            recentLogs = recentLogs,
            userTrail = userTrail,
            processInfo = procInfo,
            timestamp = System.currentTimeMillis()
        )

        // 7. 持久化到本地文件（Protobuf + MMKV 索引）
        persistCrashToFile(crashData)
    }

    private fun collectMemoryInfo(): Map<String, String> {
        val runtime = Runtime.getRuntime()
        val mi = Debug.MemoryInfo()
        Debug.getMemoryInfo(mi)
        return mapOf(
            "java_heap_allocated_kb" to ((runtime.totalMemory() - runtime.freeMemory()) / 1024).toString(),
            "java_heap_max_kb" to (runtime.maxMemory() / 1024).toString(),
            "native_heap_kb" to (Debug.getNativeHeapAllocatedSize() / 1024).toString(),
            "pss_total_kb" to mi.totalPss.toString(),
            "dalvik_pss_kb" to mi.dalvikPss.toString(),
            "native_pss_kb" to mi.nativePss.toString()
        )
    }
}
```

### 5.2 用户操作轨迹记录器（辅助定位必备）

```kotlin
// ========== 用户操作轨迹追踪 ==========

object UserTrailRecorder {
    private const val MAX_TRAIL = 100
    private val trail = ConcurrentLinkedDeque<TrailStep>()

    // ★ 通过 AspectJ/AOP 或者手动埋点在关键页面/操作处调用
    fun recordStep(screen: String, action: String, extra: Map<String, String> = emptyMap()) {
        val step = TrailStep(
            timestamp = System.currentTimeMillis(),
            screen = screen,
            action = action,
            extra = extra
        )
        trail.addLast(step)
        // 保持队列大小为 MAX_TRAIL
        while (trail.size > MAX_TRAIL) {
            trail.pollFirst()
        }
    }

    fun getRecentTrail(count: Int = 20): List<TrailStep> {
        return trail.takeLast(count)
    }
}

// 使用示例（可通过 AOP 自动注入到 Activity/Fragment 生命周期）
// class BaseActivity : AppCompatActivity() {
//     override fun onResume() {
//         super.onResume()
//         UserTrailRecorder.recordStep(javaClass.simpleName, "onResume")
//     }
// }
```

---

## 6. 监控体系建设实践案例

### 6.1 案例一：从 0 到 1 搭建「启动成功率」监控

**背景**：某电商 App 在上线初期只监控 Crash 率（0.8% 达标），但用户投诉「App 点不开」。后发现启动成功率仅 92%，意味着 8% 的用户每次打开 App 就白屏/闪退（但不触发 Java Crash）。

**建设步骤**：

```
步骤 1: 定义「启动」边界
  ├── 从 Application.onCreate() 开始
  ├── 到首页 Activity.onResume() + 2s (等待数据加载)
  └── 超时阈值: 15s (Android 启动超时阈值)

步骤 2: 采集维度
  ├── 启动总耗时（P0-P100）
  ├── 启动阶段拆解:
  │   ├── attachBaseContext → ContentProvider 初始化 → Application.onCreate
  │   ├── 首页 Activity.onCreate → onResume
  │   └── 首页数据加载完成
  ├── 启动失败原因分类:
  │   ├── 15s 超时（ANR 保护）
  │   ├── 首页 Activity 实例化失败
  │   ├── Application.onCreate 中 Crash
  │   └── 第三方 SDK 初始化超时
  └── 设备/系统兜底信息

步骤 3: 告警策略
  ├── 整体启动成功率 < 99% → P1 告警
  ├── 启动成功率环比下降 >0.3% → P1 告警
  ├── P99 启动耗时 > 5s → P2 告警
  └── 某类设备（如 Android 6.0/2GB RAM）成功率 < 90% → P1 告警

步骤 4: 优化闭环
  ├── 通过数据发现: 低端设备上某第三方 SDK 初始化耗时 8s+
  ├── 优化方案: SDK 延迟初始化 + 子线程异步
  ├── 效果: 启动成功率 92% → 99.3%，P99 耗时降 40%
  └── 固化: 新增「第三方 SDK 初始化耗时监控」子指标
```

**关键代码——启动耗时采集**：

```kotlin
object StartupMonitor {
    private const val STARTUP_TIMEOUT_MS = 15_000L
    private var startTime = 0L
    private val phaseTimes = mutableMapOf<String, Long>()

    fun onApplicationStart() {
        startTime = SystemClock.uptimeMillis()
        phaseTimes["app_start"] = startTime
        // 设置超时检测
        Handler(Looper.getMainLooper()).postDelayed({
            if (!isStartupCompleted()) {
                reportStartupTimeout() // ★ 启动失败——采集完整现场
            }
        }, STARTUP_TIMEOUT_MS)
    }

    fun recordPhase(phase: String) {
        if (startTime > 0) {
            phaseTimes[phase] = SystemClock.uptimeMillis()
        }
    }

    fun onStartupCompleted() {
        val totalMs = SystemClock.uptimeMillis() - startTime
        val phases = phaseTimes.entries.sortedBy { it.value }
            .zipWithNext { a, b -> "${a.key}->${b.key}: ${b.value - a.value}ms" }
        // 上报启动成功
        StartupReporter.upload(StartupData(totalMs, phases))
        startTime = 0
    }
}

// 使用时机:
// Application.onCreate: StartupMonitor.onApplicationStart()
// Application.onCreate 结束: StartupMonitor.recordPhase("app_oncreate_done")
// BaseActivity.onCreate: StartupMonitor.recordPhase("activity_create")
// BaseActivity.onResume: StartupMonitor.recordPhase("activity_resume")
// 首页数据加载完成: StartupMonitor.onStartupCompleted()
```

### 6.2 案例二：全链路网络监控方案

**背景**：用户投诉「App 加载慢」，但服务端数据显示接口 P99 仅 300ms。问题出在客户端 DNS 解析、TCP 建连、SSL 握手阶段。

**全链路拆解**：

```
┌─────────────────────────────────────────────────────────────────┐
│                    一次 HTTP 请求的全链路耗时                     │
│                                                                  │
│  DNS解析    TCP建连    SSL握手   发送请求   等待响应   接收响应   │
│  ├───────┼──────────┼──────────┼─────────┼─────────┼──────────┤ │
│  50ms     120ms       80ms       5ms      300ms      10ms        │
│                                                                  │
│  总耗时 = 50+120+80+5+300+10 = 565ms (用户感知时间)              │
│  服务端耗时 = 300ms (后端看到的时间)                              │
│  客户端额外开销 = 265ms (DNS+TCP+SSL = 250ms，占44%!)            │
└─────────────────────────────────────────────────────────────────┘
```

**实现方案（OkHttp EventListener + 自建 httpdns）**：

```kotlin
// ========== 全链路网络耗时采集 ==========

class NetworkMonitorEventListener(
    private val requestId: String,
    private val url: String
) : EventListener() {

    private var dnsStart = 0L    // DNS 解析开始时间
    private var tcpStart = 0L    // TCP 建连开始时间
    private var tlsStart = 0L    // SSL 握手开始时间
    private var sendStart = 0L   // 发送请求开始时间
    private var recvStart = 0L   // 接收响应开始时间

    private var dnsCost = 0L
    private var tcpCost = 0L
    private var tlsCost = 0L
    private var sendCost = 0L
    private var recvCost = 0L

    override fun dnsStart(call: Call, domainName: String) {
        dnsStart = SystemClock.uptimeMillis()
    }

    override fun dnsEnd(call: Call, domainName: String, inetAddressList: List<InetAddress>) {
        dnsCost = SystemClock.uptimeMillis() - dnsStart
    }

    override fun connectStart(call: Call, inetSocketAddress: InetSocketAddress, proxy: Proxy) {
        tcpStart = SystemClock.uptimeMillis()
    }

    override fun secureConnectStart(call: Call) {
        tlsStart = SystemClock.uptimeMillis()
    }

    override fun secureConnectEnd(call: Call, handshake: Handshake?) {
        tlsCost = SystemClock.uptimeMillis() - tlsStart
    }

    override fun connectEnd(call: Call, inetSocketAddress: InetSocketAddress, proxy: Proxy, protocol: Protocol?) {
        tcpCost = SystemClock.uptimeMillis() - tcpStart - tlsCost
    }

    override fun requestHeadersStart(call: Call) {
        sendStart = SystemClock.uptimeMillis()
    }

    override fun responseHeadersStart(call: Call) {
        recvStart = SystemClock.uptimeMillis()
    }

    override fun callEnd(call: Call) {
        val totalMs = SystemClock.uptimeMillis() - sendStart
        // 聚合上报
        NetworkMonitor.record(NetworkTrace(
            url = url,
            dnsMs = dnsCost,
            tcpMs = tcpCost,
            tlsMs = tlsCost,
            serverMs = recvStart - sendStart,
            recvMs = SystemClock.uptimeMillis() - recvStart,
            totalMs = totalMs
        ))
    }
}

// 注册到 OkHttp
val client = OkHttpClient.Builder()
    .eventListenerFactory { call ->
        val id = UUID.randomUUID().toString()
        NetworkMonitorEventListener(id, call.request().url.toString())
    }
    .build()
```

### 6.3 案例三：APM 平台核心告警策略制定

| 告警级别 | 指标 | 触发条件 | 通知方式 | 响应时长 | 止损措施 |
|:-------:|:----|:--------|:--------|:-------:|:--------|
| **P0** | Crash 率 | 5min 窗口环比增长 >200% 且影响 >1000 设备 | 电话 + 短信 + 飞书群 @all | 10min | 自动回滚灰度、下发功能降级 |
| **P0** | 启动成功率 | 5min 成功率 < 85%（正常 99.5%+） | 电话 + 短信 | 10min | 切换备用 CDN、切换默认配置 |
| **P1** | ANR 率 | 小时级 >0.5%（正常 <0.1%） | 飞书群 + 企业微信 | 30min | 定位 top ANR 问题，发布热修复 |
| **P1** | 网络失败率 | 5min 核心接口失败率 >5% | 飞书群 | 30min | 切换备用域名/IP |
| **P1** | 新增 Issue | 出现新 Crash Issue 影响 >100 用户 | 飞书群 | 60min | 紧急修复分支 |
| **P2** | 卡顿率 | 日用户卡顿率 >10% | 日报 / 周报汇总 | 下一工作日 | 性能优化排期 |
| **P3** | 内存峰值 | 日 P95 内存 > 设备可用 80% | 周报 | 下个迭代 | 优化内存泄漏 |
| **P4** | 包体积 | 版本增量 >5MB | 周报 | 下个迭代 | 资源优化、混淆检查 |

**告警静默与抖动抑制**：

```python
# 服务端告警引擎核心逻辑（伪代码）
def evaluate_alert(metric_name: str, current_value: float, window_minutes: int):
    # 1. 静默期检查：同一 Issue 30 分钟内不再告警
    if is_in_silence_window(metric_name):
        return None

    # 2. 环比计算
    baseline = get_baseline(metric_name, window_minutes * 2)  # 前一个窗口
    if baseline == 0:
        return None  # 无基线数据，不告警

    delta_ratio = (current_value - baseline) / baseline

    # 3. 兜底：绝对值不够不告警（避免样本量太小导致的误报）
    if current_value < ABSOLUTE_MIN_THRESHOLD:
        return None

    # 4. 判定告警级别
    if delta_ratio > 2.0 and current_value > 0.05:  # 环比 >200% 且绝对值 >5%
        return Alert(level='P0', ...)
    elif delta_ratio > 1.0:  # 环比 >100%
        return Alert(level='P1', ...)
    elif delta_ratio > 0.5:  # 环比 >50%
        return Alert(level='P2', ...)

    return None
```

---

## 总结

异常监控体系的面试核心考察点：**不是「你用过什么工具」，而是「你如何设计一套可靠的系统」**。

关键记忆框架：

```
采集层: UncaughtExceptionHandler / Breakpad / Printer / EventListener
    ↓
传输层: Protobuf + Gzip + MMKV 离线缓存 + 限流去重
    ↓
聚合层: 符号化(mapping.txt + addr2line) → 聚类(DBSCAN) → git blame
    ↓
告警层: 环比检测 + 分级告警(P0-P4) + 抖动抑制 + 静默窗口
    ↓
止损层: 配置中心降级 / 热修复 / 灰度回滚 / 备用链路切换
```

> **面试技巧**：回答时先画出四层架构图，然后按层展开，每层说 1-2 个核心技术点 + 1 个踩过的坑（如「Native Crash 采集不能使用 malloc」「RingBuffer 防止内存抖动」「采样率需要动态下发」），会极大增强面试官的信任感。
