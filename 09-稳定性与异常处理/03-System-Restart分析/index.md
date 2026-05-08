# System Restart 分析 — 面试深度剖析

---

## 目录

1. [高频面试问题](#1-高频面试问题)
2. [标准答案与故障树](#2-标准答案与故障树)
3. [核心原理深度剖析](#3-核心原理深度剖析)
4. [流程图：system_server 重启完整事件链](#4-流程图system_server-重启完整事件链)
5. [源码分析：重启相关核心源码](#5-源码分析重启相关核心源码)
6. [应用场景：一次 System Restart 日志分析案例](#6-应用场景一次-system-restart-日志分析案例)

---

## 1. 高频面试问题

### Q1：System Server 重启（System Restart）有哪些触发原因？请列举并解释。

这道题考察你是否理解 system_server 重启的根因分类。面试官想了解你能否从 WatchDog、死锁、OOM、Native Crash 等多个维度系统地分析触发场景，而不是简单地说「系统卡了就重启」。对于高级/资深岗位，需要能够说出每种触发原因的底层机制和日志特征。

### Q2：System Server 重启后，对运行中的 APP 进程会产生哪些影响？

这是一道考察系统全局视角的经典问题。面试官想知道你能否清晰区分：Zygote 是否受影响？已存在的 App 进程是否存活？Binder 连接会发生什么？AMS 如何恢复进程状态？应用层会出现什么异常表现（DeadObjectException / 进程重建 / 状态丢失）？

### Q3：如何从日志中判断一次重启是 System Restart 而非普通重启？关键日志 TAG 有哪些？

这道题考察你的线上问题定位能力。你需要清楚 system_server 重启与 kernel panic、正常关机重启的日志区别——「热重启 vs 冷重启」的判断是稳定性工程师的核心技能。需要掌握的关键关键字包括：`WATCHDOG KILLING`、`system_server`、`BOOT_COMPLETED`、`sys.boot_completed` 等。

### Q4：system_server 的 OOM 和普通 APP 的 OOM 有什么区别？为什么 system_server 有 adj=-16 仍然可能 OOM？

这道题考察你对 Android LMK（Low Memory Killer）机制和 OOM Adj 体系的深度理解。面试官想知道你是否清楚 system_server 的特殊保护机制（`adj=-16` 永不被 LMK 杀），同时也了解它仍然可能因为 Java Heap 耗尽或 Native 内存泄漏而发生 OOM，但其后果远比普通 APP OOM 严重。

### Q5：Kernel Panic 和 System Restart 有什么区别？如何通过日志区分？

这道题是高阶问题，面试官想考察你从上层 Java 到底层 Linux Kernel 的全栈理解。你需要清楚：Kernel Panic 是内核级别的崩溃（系统彻底死机，通常伴随按键灯闪烁或自动重启），而 System Restart 是用户空间 system_server 进程的重启（系统短暂黑屏/开机动画后恢复）。两者的日志来源、表现形式和根因分析方法完全不同。

### Q6：如果线上大量用户上报「手机自动重启」，你的排查思路是什么？

开放性问题，考察你的系统性思维和线上问题定位方法论。你需要从「确认重启类型 → 分析发生条件 → 定位根本原因 → 制定修复方案」的完整链条来回答。

---

## 2. 标准答案与故障树

### 2.1 System Restart 触发原因完整故障树

```
System Restart（system_server 进程死亡）
│
├── 【第一类：WatchDog 触发（占比 ~70%）】
│   ├── 主线程死锁
│   │   ├── AMS 持锁执行耗时操作（如 PKMS 安装扫描）
│   │   ├── WMS 持锁 + Binder 调用阻塞（如 SurfaceFlinger 无响应）
│   │   └── 多服务循环锁依赖（AMS 等 WMS → WMS 等 IMS → IMS 等 AMS）
│   │
│   ├── Binder 线程池耗尽（16 个 Binder 线程全部阻塞）
│   │   ├── Binder 调用对端进程挂死（如 SurfaceFlinger、HAL 层服务）
│   │   └── Binder 事务超时累积 → 所有 Binder 线程卡在等待
│   │
│   ├── InputDispatcher 线程阻塞
│   │   ├── InputChannel 连接异常
│   │   └── 焦点窗口 ANR 状态未正确清理
│   │
│   └── FdMonitor 超时（Android 10+）
│       └── FD 泄漏耗尽 → 无法创建新 Binder 连接 → 系统性卡死
│
├── 【第二类：系统服务 Native Crash（占比 ~15%）】
│   ├── SurfaceFlinger 崩溃（HWC/HAL 层异常）
│   ├── audioserver / mediaserver 崩溃（HAL 层解码器异常）
│   ├── drmserver 崩溃（DRM 解密异常）
│   └── 关键 HAL 服务崩溃导致 system_server Binder 调用失败 → WatchDog 二次触发
│
├── 【第三类：system_server 自身 OOM（占比 ~10%）】
│   ├── Java Heap OOM
│   │   ├── 系统服务内存泄漏（如 AMS 中 ProcessRecord/ActivityRecord 未释放）
│   │   ├── PMS 扫描大量 APK 时瞬时内存峰值
│   │   └── Bitmap 缓存未释放（WallpaperManager 等）
│   │
│   └── Native OOM（更隐蔽）
│       ├── Binder 驱动内存分配失败（/dev/binder mmap 映射区耗尽）
│       ├── Ashmem 匿名共享内存分配失败
│       └── Native 层内存泄漏（GraphicBuffer、NativeWindow 等）
│
├── 【第四类：init 主动重启（占比 ~3%）】
│   ├── init.rc 中 `critical` 服务崩溃次数超限
│   │   └── 如 surfaceflinger 连续崩溃 4 次 → init 重启整个系统
│   └── servicemanager / hwservicemanager 崩溃
│
└── 【第五类：Kernel Panic → 全系统重启（占比 ~2%）】
    ├── 内核空指针解引用
    ├── 内核内存损坏（use-after-free / double-free）
    ├── 硬件看门狗超时（Qualcomm HW WDOG）
    └── 文件系统错误导致 Kernel Panic
```

### 2.2 System Server 重启后对 APP 的影响 — 分层分析

| 维度 | 具体影响 | 恢复机制 | APP 层表现 |
|------|---------|---------|-----------|
| **Zygote 进程** | 不受影响 | — | 无影响 |
| **已运行的 APP 进程** | 进程本身存活 | — | 内存状态保留（进程未杀） |
| **Binder 连接** | 全部断开 | AMS 重启后，APP 收到 Binder 死亡通知（`linkToDeath`），触发重新注册 | `DeadObjectException` / `RemoteException` |
| **四大组件状态** | Activity 栈、Service 记录、BroadcastReceiver 队列全部丢失 | AMS 从 `/data/system/` 恢复持久化数据（如 Task 栈快照） | Activity 可能被重建或回到桌面；Service 被重新绑定 |
| **系统服务代理** | WMS/PMS/PKMS/AlarmManager 等所有 proxy 失效 | APP 通过 `ServiceManager.getService()` 重新获取 Binder 句柄 | 调用系统服务时抛出 `RuntimeException` |
| **进程优先级记录** | OOM Adj 记录丢失 | AMS 重启后调用 `updateOomAdjLocked()` 重新计算 | 短时间内可能被杀（系统恢复期内存压力大） |
| **PendingIntent / Alarm** | AlarmManagerService 状态从磁盘恢复 | `/data/system/alarms/` 持久化文件 | 延迟触发的定时任务可能丢失 |
| **用户感知** | 屏幕短暂黑屏或卡在开机动画 5~15 秒 | — | 用户反馈「手机自动重启」 |

### 2.3 Kernel Panic vs System Restart — 关键区别

| 维度 | Kernel Panic（内核崩溃） | System Restart（system_server 重启） |
|------|--------------------------|--------------------------------------|
| **崩溃层级** | Linux Kernel 层 | Android Framework 层（用户空间） |
| **触发方** | 内核 BUG（空指针、内存损坏等） | WatchDog / Native Crash / OOM |
| **重启范围** | **全系统冷重启**：内核→init→所有进程 | **热重启**：仅 system_server 及相关服务 |
| **日志来源** | `dmesg` / `/sys/fs/pstore/console-ramoops` | `logcat`（system/bin） |
| **关键日志** | `Kernel panic - not syncing:` | `WATCHDOG KILLING SYSTEM PROCESS` |
| **重启后标志** | `ro.boot.bootreason` = `kernel_panic` | `sys.boot_completed` 从 1→0→1 |
| **Bootloader 日志** | 有异常重启记录（PON 寄存器） | 通常无 HW 级别记录 |
| **Zygote 进程** | 被杀死，重新 fork | 不受影响 |
| **APP 进程** | 全部被杀死 | 进程存活，但 Binder 连接断开 |
| **系统恢复时间** | 30~60 秒（完整开机流程） | 5~15 秒（仅 system_server 重启） |
| **典型原因** | 驱动问题、硬件故障、内存损坏 | 系统服务死锁、Binder 阻塞、OOM |

**面试关键话术**：

> Kernel Panic 是「心脏停跳」——内核崩溃，整个系统从零开始重新启动，bootloader→kernel→init→所有服务。System Restart 是「脑部休克」——只有 system_server（系统的大脑）重启，Zygote 和 APP 进程还在运行，相当于把中央指挥系统重启了一次。区分这两者，关键是看有没有经过 Bootloader 阶段：kernel panic 会有完整的开机日志链条，system restart 只有 system_server 的启动日志。

### 2.4 system_server OOM vs APP OOM — 深度对比

| 维度 | system_server OOM | APP OOM |
|------|-------------------|---------|
| **OOM Adj** | **-16 (SYSTEM_ADJ)** | 0 ~ 1001（前台→缓存） |
| **LMK 是否可杀** | **永不！** LMK 跳过 adj<0 的进程 | 可以被 LMK 杀（根据内存压力） |
| **OOM 类型** | 通常是 **Java Heap 满** 或 **Native 内存满** | Java Heap OOM 为主 |
| **触发机制** | `OutOfMemoryError` 被 Runtime 捕获 → 可能触发 system_server 崩溃 → init 重启 | `OutOfMemoryError` → APP 崩溃（仅影响自身） |
| **后果严重度** | 整个系统重启，所有用户受影响 | 仅该 APP 崩溃，不影响系统 |
| **典型场景** | PMS 扫描 APK 时 Bitmap 解析内存峰值；AMS 中 ActivityRecord 泄漏 | 图片加载/大对象分配/内存泄漏累积 |
| **堆大小** | 通常 192MB~512MB（取决于 ROM 配置） | 通常 128MB~512MB（取决于设备和 `dalvik.vm.heapgrowthlimit`） |
| **日志 TAG** | `system_server` + `OutOfMemoryError` + `WATCHDOG KILLING` | 应用包名 + `OutOfMemoryError` |

**为什么 adj=-16 仍然会 OOM？**

`adj=-16`（`SYSTEM_ADJ`）只能保证 system_server **不会被 LMK 选择杀掉**，但不能阻止它自身的堆内存分配失败：

1. **Java Heap OOM**：system_server 也有自己的 Dalvik/ART 堆，当持续分配对象导致堆满时，GC 无法回收足够空间，就会抛出 `OutOfMemoryError`。
2. **Native OOM**：Binder 驱动的 mmap 映射区（默认约 1MB）、Ashmem 分配、GraphicBuffer 分配等都不受 Java Heap 限制，如果这些区域耗尽同样会导致系统级 OOM。
3. **FD 耗尽**：Linux 的 `RLIMIT_NOFILE` 限制（通常 1024），system_server 打开大量 Binder 连接、文件、Socket 后可能耗尽 FD。

---

## 3. 核心原理深度剖析

### 3.1 system_server 进程的特殊性

system_server 是 Android 系统中**最重要的用户空间进程**，具有以下特殊性：

#### 3.1.1 进程属性

```java
// ProcessList.java 中定义
static final int SYSTEM_ADJ = -16;  // 永不被 LMK 杀死的 OOM Adj

// system_server 被 AMS 设置为：
ProcessRecord.setAdj(SYSTEM_ADJ);         // OOM Adj = -16
ProcessRecord.setProcState(PROCESS_STATE_PERSISTENT);  // 持久进程状态
```

```
OOM Adj 从低到高（越容易被杀）:
┌──────────────────────────────────────────────────────────────┐
│ -16 (SYSTEM)  │  -12 (PERSISTENT) │  ...  │  0 (FOREGROUND) │ ... │ 1001 (CACHED)
│  system_server │  Phone/SystemUI   │       │  前台 APP        │     │  缓存后台
│  永不杀        │  几乎不杀          │       │                  │     │  优先被杀
└──────────────────────────────────────────────────────────────┘
```

#### 3.1.2 system_server 承载的核心服务

system_server 启动时会创建 **超过 80 个系统服务**，包括：

| 类别 | 核心服务 |
|------|---------|
| **四大组件管理** | `ActivityManagerService`、`WindowManagerService`、`PackageManagerService` |
| **输入输出** | `InputManagerService`、`DisplayManagerService` |
| **通知** | `NotificationManagerService` |
| **电源** | `PowerManagerService`、`BatteryService` |
| **网络** | `ConnectivityService`、`NetworkManagementService` |
| **存储** | `MountService`、`StorageManagerService` |
| **传感器** | `SensorService`（部分 ROM 独立进程） |
| **音频** | `AudioService`（Android 5.0+ 部分独立为 audioserver） |
| **Alarm** | `AlarmManagerService` |
| **用户管理** | `UserManagerService` |

当 system_server 重启时，**所有这些服务都会重新初始化**，相当于系统功能核心的一次「硬复位」。

### 3.2 WatchDog 触发重启的完整流程

WatchDog 是 system_server 的「自我诊断+自我了断」机制。详细流程如下：

```
Phase 0: 常规监控（每 30 秒一轮）
  WatchDog.run() → scheduleCheckLocked() → 向所有注册线程发送心跳消息
                                              ↓
Phase 1: 超时判定（60 秒无响应）
  连续两轮心跳未收到 HandlerChecker 响应
  → waitedHalf 机制：第一次检测到后额外等待 30 秒（二次确认）
  → 确认超时不可恢复 → 进入自杀流程
                                              ↓
Phase 2: Dump 阶段（保留案发现场）
  ① dumpKernelStackTraces()         → 写入内核栈到 /data/anr/traces.txt
  ② AMS.dumpStackTraces(AMS_PID)    → 收集所有 Java 线程堆栈
  ③ native_debuggerd_dump()         → 收集 Native 线程堆栈
  ④ 输出 I/O 使用、Binder 调用统计、FD 状态
  ⑤ 所有信息写入 /data/anr/traces.txt
                                              ↓
Phase 3: Kill 阶段
  Slog.e(TAG, "*** WATCHDOG KILLING SYSTEM PROCESS: " + subject)
  → Process.killProcess(Process.myPid())   // SIGKILL = 信号 9
  → System.exit(10)
                                              ↓
Phase 4: init 检测与重启
  init 进程 (PID=1) waitpid() 检测到 system_server 死亡
  → 查找 init.rc 中 service system_server 的配置
  → 执行 onrestart 指令（重启依赖服务）
  → fork + execve → 启动新的 system_server 进程
                                              ↓
Phase 5: 系统服务重新初始化
  SystemServer.run()
  → startBootstrapServices()    // AMS、PMS、PKMS 等引导服务
  → startCoreServices()         // Battery、UsageStats 等核心服务
  → startOtherServices()        // WMS、IMS、Notification 等其他服务
  → Watchdog.getInstance().start()  // 重新启动 WatchDog
                                              ↓
Phase 6: 状态恢复
  AMS 从 /data/system/ 恢复持久化数据：
    - Activity 栈快照 (activity_task.dat / recent_tasks.xml)
    - 用户设置 (users/0.xml)
    - App 权限记录 (packages.xml / appops.xml)
  → 系统广播: ACTION_BOOT_COMPLETED（因为 sys.boot_completed 被重置）
  → APP 进程 Binder 重连
```

### 3.3 AMS 状态持久化机制

AMS 在关键操作时会**同步写入持久化数据**到 `/data/system/` 目录，以便 system_server 重启后恢复状态：

```
/data/system/
├── packages.xml              # 已安装应用信息（包名、签名、权限）
├── packages.list             # 包名→uid→数据目录映射
├── appops.xml                # AppOps 权限记录
├── users/                    # 多用户目录
│   └── 0.xml                # 用户 0 的设置
├── activity_task.dat         # Activity Task 栈的快照（二进制格式）
├── recent_tasks.xml          # 最近任务列表
├── procstats/                # 进程统计信息
├── netstats/                 # 网络统计信息
├── alarms/                   # Alarm 持久化数据
└── sync/                     # 同步管理器状态
```

**关键点**：这些持久化数据是**最终一致性**的，而非实时同步。系统重启时可能存在最近几秒的状态丢失（脏数据未刷盘）。

---

## 4. 流程图：system_server 重启完整事件链

```
═══════════════════════════════════════════════════════════════════════════════
                    SYSTEM_SERVER 重启完整事件链
═══════════════════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────────────────┐
│  触发源分类                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ WatchDog 超时 │  │ Native Crash │  │  Java OOM    │  │ Kernel Panic │     │
│  │ (70%)        │  │ (15%)        │  │ (10%)        │  │ (3%)         │     │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘     │
│         │                 │                 │                 │              │
│         │                 │                 │                 ▼              │
│         │                 │                 │         全系统冷重启            │
│         │                 │                 │         (本图不展开)            │
└─────────┼─────────────────┼─────────────────┼───────────────────────────────┘
          │                 │                 │
          ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  system_server 进程死亡 (SIGKILL / Native Crash / OOM Kill)                 │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  init 进程 (PID=1) 监控到子进程死亡                                          │
│                                                                             │
│  init.cpp:                                                                    │
│    waitpid(-1, &status, WNOHANG)  // 非阻塞等待任意子进程                     │
│    → 检测到 system_server PID 退出                                          │
│    → 读取 init.rc 中 service system_server 配置                              │
│                                                                             │
│  init.rc 关键配置:                                                           │
│    service system_server /system/bin/system_server                           │
│        class core                                                           │
│        user system                                                          │
│        group system ...                                                     │
│        capabilities ...                                                     │
│        onrestart restart servicemanager    ← 重启 servicemanager            │
│        onrestart restart surfaceflinger    ← 重启 surfaceflinger            │
│        onrestart restart zygote            ← 重启 zygote                    │
│        onrestart restart media             ← 重启 mediaserver               │
│        writepid /dev/cpuset/system-background/tasks                         │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
              重启 surfaceflinger   重启 zygote    重启其他依赖服务
                    │            │            │
                    └────────────┼────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  新的 system_server 进程启动 (fork + execve)                                 │
│                                                                             │
│  SystemServer.main()                                                        │
│    → Looper.prepareMainLooper()                                             │
│    → SystemServer.run()                                                     │
│      → startBootstrapServices()    ← AMS, PMS, PKMS, WatchDog 等          │
│      → startCoreServices()        ← Battery, UsageStats, WebView 等       │
│      → startOtherServices()       ← WMS, IMS, Notification, Power 等      │
│      → systemReady()               ← 通知 AMS 系统就绪                      │
│        → AMS.systemReady() → ... → ACTION_BOOT_COMPLETED 广播               │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  对 APP 进程的影响                                                           │
│                                                                             │
│  已存在的 APP 进程 (Zygote fork 出来的):                                     │
│    ✓ 进程本身存活（PID 不变）                                                 │
│    ✗ 与 system_server 的 Binder 连接断开                                     │
│    ✗ getSystemService() 返回的 Proxy 对象失效                                │
│    ✗ Scheduled jobs / alarms / broadcast 可能丢失                            │
│                                                                             │
│  APP 进程恢复机制:                                                           │
│    ① Binder.linkToDeath() 回调触发                                           │
│    ② 重新 ServiceManager.getService() 获取新 Binder 句柄                     │
│    ③ AMS 重建进程 Record → 重新绑定四大组件                                   │
│    ④ Activity 从 /data/system/activity_task.dat 恢复 Task 栈                │
│                                                                             │
│  用户感知:                                                                   │
│    - 屏幕短暂黑屏 2-5 秒，然后显示开机动画                                     │
│    - 整体恢复时间约 5-15 秒                                                   │
│    - 恢复后用户回到桌面（前台 Activity 可能丢失）                              │
└─────────────────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════
  时间轴示意 (以 WatchDog 触发为例):
═══════════════════════════════════════════════════════════════════════════════

T=0s     WatchDog 开始新一轮检测，发送心跳
T=30s    第一轮检测：某 HandlerChecker 未响应（标记 waitedHalf = true）
T=60s    第二轮检测：仍未响应，确认超时 → 触发 dump
T=60-62s Dump 阶段：堆栈写入 /data/anr/traces.txt
T=~62s   Process.killProcess(myPid) → system_server 收到 SIGKILL 死亡
T=~63s   init 检测到 system_server 退出 → 重启依赖服务
T=~64s   init fork 新的 system_server 进程
T=~65s   SystemServer.run() 开始执行
T=~68s   AMS 从 /data/system/ 恢复状态
T=~72s   AMS.systemReady() → ACTION_BOOT_COMPLETED 广播
T=~75s   用户看到桌面，系统基本恢复正常
```

---

## 5. 源码分析：重启相关核心源码

### 5.1 WatchDog.run() — 超时检测与自杀

```java
// frameworks/base/services/core/java/com/android/server/Watchdog.java

public class Watchdog extends Thread {
    static final long CHECK_INTERVAL = 30000;        // 30 秒检测间隔
    static final long DEFAULT_TIMEOUT = 60000;       // 60 秒超时阈值

    @Override
    public void run() {
        boolean waitedHalf = false;
        while (true) {
            final List<HandlerChecker> blockedCheckers;
            final String subject;
            final boolean allowRestart;

            synchronized (this) {
                long timeout = CHECK_INTERVAL;

                // ① 向所有注册的 HandlerChecker 发送心跳
                for (int i = 0; i < mHandlerCheckers.size(); i++) {
                    HandlerChecker hc = mHandlerCheckers.get(i);
                    hc.scheduleCheckLocked();
                }

                long start = SystemClock.uptimeMillis();
                while (timeout > 0) {
                    try {
                        wait(timeout);  // 等待 30 秒
                    } catch (InterruptedException e) { }
                    timeout = CHECK_INTERVAL
                        - (SystemClock.uptimeMillis() - start);
                }

                // ② 收集超时的 Checker
                blockedCheckers = getBlockedCheckersLocked();
                subject = describeCheckersLocked(blockedCheckers);
                allowRestart = mAllowRestart;
            }

            // ③ 如果有超时 Checker → 进入自杀流程
            if (blockedCheckers.size() > 0) {
                // 二次确认：给系统额外 30 秒恢复机会
                if (!waitedHalf) {
                    Slog.w(TAG, "*** WATCHDOG WAITED HALF: " + subject);
                    waitedHalf = true;
                    continue;  // 再等一轮
                }

                // ④ 确认超时 → 执行 dump + kill
                Slog.e(TAG, "*** WATCHDOG KILLING SYSTEM PROCESS: "
                    + subject);

                // Dump 所有线程堆栈
                ActivityManagerService.dumpStackTraces(
                    AMS_PID,           // system_server 的 PID
                    ProcessList.FIRST_APPLICATION_UID,
                    null
                );

                // 自杀：发送 SIGKILL
                Slog.e(TAG, "*** GOODBYE!");
                Process.killProcess(Process.myPid());
                System.exit(10);
            }

            waitedHalf = false;
        }
    }
}
```

**源码关键设计点解读：**

1. **`waitedHalf` 二次确认**：避免因瞬时高负载导致的误判。第一次检测到超时后，不立即自杀，而是给系统额外 30 秒恢复。这是一种「乐观」策略。

2. **`wait(timeout)` 而非 `sleep()`**：`Object.wait()` 可以被 `notify()` 提前唤醒，允许系统在正常运行时加速检测循环。

3. **`System.exit(10)`**：退出码 10 是 system_server 专用的「WatchDog 自杀」信号。init 进程可以根据退出码执行不同的重启策略。

### 5.2 init 进程检测与重启 system_server

```cpp
// system/core/init/init.cpp

static void restart_processes() {
    // 遍历所有需要重启的服务
    for (const auto& s : ServiceList::GetInstance()) {
        if (s->IsRunning()) {
            continue;
        }
        // onrestart 触发的服务才重启
        if (s->flags() & SVC_RESTARTING) {
            s->Start();  // fork + execve
        }
    }
}

// signal_handler.cpp — SIGCHLD 信号处理
static void HandleSignalFd() {
    // 接收 SIGCHLD 信号
    // → ReapAnyOutstandingChildren()
    //   → waitpid() 收集退出子进程
    //   → 标记对应 service 为 SVC_RESTARTING
    //   → 触发 restart_processes()
}
```

```ini
# system/core/rootdir/init.rc
service system_server /system/bin/system_server
    class core
    user system
    group system graphics input ...
    capabilities NET_ADMIN NET_RAW ...
    onrestart restart servicemanager
    onrestart restart surfaceflinger
    onrestart restart zygote
    onrestart restart audioserver
    onrestart restart media
    onrestart restart netd
    onrestart restart wificond
    writepid /dev/cpuset/system-background/tasks
```

**`onrestart` 的含义**：当 system_server 死亡并需要重启时，这些被 `onrestart` 标记的依赖服务也会被重启，确保 system_server 重新启动后有一个干净的系统环境。这就是为什么 system_server 重启会导致 Zygote 也重启的原因——尽管 Zygote 自身没有问题，但它与 system_server 的状态耦合太强。

### 5.3 AMS 状态持久化

```java
// frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java

// AMS 构造函数中注册 WatchDog Monitor
public ActivityManagerService(Context systemContext) {
    // ...
    Watchdog.getInstance().addMonitor(this);
    Watchdog.getInstance().addThread(mHandler);
    // ...
}

// AMS 的 Monitor 实现 —— 检测 AMS 关键锁是否可用
@Override
public void monitor() {
    synchronized (this) {
        // 如果 AMS 锁被长时间持有，这里就会阻塞
        // WatchDog 的 HandlerChecker 会检测到这个 Monitor 超时
    }
}

// systemReady() —— 系统就绪后的恢复入口
public void systemReady(final Runnable goingCallback, TimingsTraceLog traceLog) {
    // ...
    synchronized (this) {
        // 从 /data/system/ 恢复持久化数据
        mRecentTasks.loadUserRecentsLocked(currentUserId);
        // ...
        // 发送 ACTION_BOOT_COMPLETED 广播
        broadcastBootCompletedLocked();
    }
}
```

### 5.4 ProcessList — system_server 的 OOM Adj 设置

```java
// frameworks/base/services/core/java/com/android/server/am/ProcessList.java

public final class ProcessList {
    // system_server 的 ADJ 值 —— 永不被杀
    static final int SYSTEM_ADJ = -16;

    // 其他持久进程
    static final int PERSISTENT_PROC_ADJ = -12;
    static final int PERSISTENT_SERVICE_ADJ = -11;

    // 前台进程
    static final int FOREGROUND_APP_ADJ = 0;

    // 缓存进程 —— 最容易被杀
    static final int CACHED_APP_MIN_ADJ = 900;
    static final int CACHED_APP_MAX_ADJ = 1001;

    // system_server 创建时即设定为 SYSTEM_ADJ
    void setSystemProcessAdj(ProcessRecord app) {
        app.maxAdj = SYSTEM_ADJ;
        app.curAdj = SYSTEM_ADJ;
        app.curRawAdj = SYSTEM_ADJ;
        app.setCurrentSchedulingGroup(
            ProcessList.SCHED_GROUP_TOP_APP);
    }
}
```

**LMK 逻辑中的保护**：

```cpp
// system/memory/lmkd/lmkd.cpp (简化逻辑)
static int find_and_kill_process(int other_free, int other_file) {
    // 遍历进程列表，按 OOM Adj 从高到低排序
    for (auto& proc : proc_list_sorted_by_adj_desc) {
        // 跳过 OOM Adj < 0 的进程（system_server 等系统进程）
        if (proc.oomadj < 0) {
            continue;  // ← system_server 永不被 LMK 选中
        }
        // 杀掉该进程
        kill(proc.pid, SIGKILL);
        return 0;
    }
    return -1;  // 没有进程可杀
}
```

---

## 6. 应用场景：一次 System Restart 日志分析案例

### 6.1 案例背景

线上监控平台发现某设备在特定时段出现系统重启（用户反馈「手机突然进入开机动画」）。我们需要通过日志还原真相。

### 6.2 日志分析过程

#### Step 1：确认重启类型

首先搜索关键 TAG，确认是否为 system_server 重启：

```log
# 搜索 WatchDog 关键词
$ grep -n "WATCHDOG" main_log.txt

05-08 14:32:15.123  1234  1234 E Watchdog: *** WATCHDOG KILLING SYSTEM PROCESS: Blocked in monitor
    foreground thread on foreground thread (Blocked in monitor
    foreground thread) ...
```

**判断**：发现 `WATCHDOG KILLING SYSTEM PROCESS`，确认为 WatchDog 触发的 system_server 热重启，而非 Kernel Panic。

#### Step 2：定位阻塞点

从 WatchDog 日志中提取阻塞信息：

```log
05-08 14:32:15.123  1234  1234 E Watchdog: Blocked in monitor foreground thread
    on foreground thread
05-08 14:32:15.124  1234  1234 E Watchdog: foreground thread stack:
    at com.android.server.am.ActivityManagerService.monitor(AMS.java:2456)
    - waiting to lock <0x0a3b8c1d> (a com.android.server.am.ActivityManagerService)
    held by thread 47 (Binder:1234_7)
```

**判断**：`foreground thread` 在 `AMS.monitor()` 中阻塞，等待 AMS 锁。而该锁被 `Binder:1234_7` 线程持有。

#### Step 3：分析锁持有者

继续查看 Binder 线程 47 的堆栈：

```log
05-08 14:32:15.125  1234  1234 E Watchdog: Binder:1234_7 stack:
    at com.android.server.wm.WindowManagerService.relayoutWindow(WMS.java:3421)
    - waiting to lock <0x1f5a2b3e> (a com.android.server.wm.WindowManagerService)
    held by thread 52 (Binder:1234_C)
    ...
    at com.android.server.am.ActivityManagerService.bindService(AMS.java:18765)
    - locked <0x0a3b8c1d> (a com.android.server.am.ActivityManagerService)
```

**发现死锁链**：

```
Binder:1234_7  持有 AMS 锁 → 等待 WMS 锁
Binder:1234_C  持有 WMS 锁 → 等待 AMS 锁（通过调用 AMS.bindService()）
                 ↑___________________↓
                        死锁！
```

#### Step 4：分析根因

继续向上追溯触发调用：

```log
05-08 14:32:15.126  1234  1234 E Watchdog: 
    Binder:1234_7: AMS.bindService() 被应用进程调用
    → 该调用需要同时获取 AMS 锁和 WMS 锁
    
    Binder:1234_C: WMS.relayoutWindow() 被 SurfaceFlinger 回调触发
    → 窗口重布局需要 WMS 锁，重布局过程中又需要通知 AMS（需要 AMS 锁）
```

**根因结论**：`bindService()` 与 `relayoutWindow()` 形成了典型的 **AMS-WMS 交叉锁死锁**。

#### Step 5：查看重启恢复日志

```log
# system_server 死亡
05-08 14:32:15.500  1234  1234 I Watchdog: *** GOODBYE!

# init 检测到死亡
05-08 14:32:15.800     1     1 I init   : Service 'system_server' (pid 1234) killed by signal 9

# 重启依赖服务
05-08 14:32:15.810     1     1 I init   : Sending signal 9 to service 'zygote' (pid 890)
05-08 14:32:15.820     1     1 I init   : starting service 'zygote'...
05-08 14:32:15.850     1     1 I init   : starting service 'system_server'...

# system_server 重新启动
05-08 14:32:16.200  3456  3456 I SystemServer: Entered the Android system server!
05-08 14:32:16.500  3456  3456 I SystemServiceManager: Starting phase BOOTSTRAP
05-08 14:32:18.200  3456  3456 I SystemServiceManager: Starting phase CORE
05-08 14:32:20.000  3456  3456 I SystemServiceManager: Starting phase OTHER

# AMS 恢复状态
05-08 14:32:22.500  3456  3456 I ActivityManager: System now ready
05-08 14:32:22.510  3456  3456 I ActivityManager: Recovery: restoring recent tasks from disk

# 广播发送
05-08 14:32:23.000  3456  3456 I ActivityManager: Sending ACTION_BOOT_COMPLETED
```

### 6.3 案例总结

| 分析维度 | 结论 |
|---------|------|
| **重启类型** | WatchDog 触发的 system_server 热重启 |
| **直接原因** | AMS ↔ WMS 循环锁死锁 |
| **触发调用** | `bindService()` 与 `relayoutWindow()` 的并发交叉锁 |
| **恢复时间** | 从自杀到 AMS systemReady 约 7 秒 |
| **影响范围** | Zygote 重启、所有 APP Binder 连接断开、Activity 栈恢复 |
| **修复建议** | 减少 AMS 和 WMS 的锁竞争范围、使用细粒度锁、避免在持锁状态下跨服务调用 |

### 6.4 关键日志搜索命令速查

```bash
# 1. 确认 WatchDog 触发
grep -E "WATCHDOG KILLING|GOODBYE" logcat.txt

# 2. 确认 system_server 死亡与重启
grep -E "system_server.*killed|starting service.*system_server" logcat.txt

# 3. 确认 Kernel Panic（排除热重启）
grep -E "Kernel panic|ramoops|Panic" dmesg.txt

# 4. 确认 Bootloader 级别重启（全系统冷重启）
grep -E "sys.boot_completed.*0→1|BOOT_COMPLETED" logcat.txt

# 5. 查看重启时的堆栈快照
grep -A 50 "WATCHDOG KILLING" logcat.txt | grep -E "stack:|Blocked"

# 6. 查看 OOM 相关
grep -E "OutOfMemoryError|out of memory" logcat.txt | grep system_server

# 7. 确认 Binder 线程耗尽
grep -E "binder_thread_read.*blocked|binder_alloc_buf.*failed" logcat.txt
```

---

## 总结

System Restart 是 Android 系统稳定性的最后防线。理解它的核心在于把握三点：

1. **system_server 是 Android 的「大脑」**——它承载了 AMS、WMS、PMS 等所有核心服务，且通过 `adj=-16` 获得 LMK 永杀保护，但这种保护不意味着它不会崩溃。

2. **WatchDog 是「自我诊断+自我了断」机制**——当系统服务陷入死锁或 Binder 阻塞超过 60 秒，WatchDog 会主动 dump 堆栈后自杀，由 init 进程重新拉起 system_server，完成一次「热重启」。

3. **区分热重启和冷重启是排查的第一步**——从 WatchDog 日志判断是 system_server 级别重启，从 Kernel Panic 日志判断是全系统冷重启，两者的根因分析路径完全不同。

掌握 System Restart 分析能力，是高级 Android 稳定性工程师的核心竞争力之一。
