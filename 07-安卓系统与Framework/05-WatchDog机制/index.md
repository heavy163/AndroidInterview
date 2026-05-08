# WatchDog 机制 — 面试深度剖析

---

## 目录

1. [高频面试问题](#1-高频面试问题)
2. [标准答案与机制对比](#2-标准答案与机制对比)
3. [核心原理深度剖析](#3-核心原理深度剖析)
4. [流程图：WatchDog 监控→超时→dump→重启](#4-流程图watchdog-监控超时dump重启)
5. [源码分析：WatchDog.run() 与 HandlerChecker](#5-源码分析watchdogrun-与-handlerchecker)
6. [应用场景：系统死锁导致 WatchDog 重启案例](#6-应用场景系统死锁导致-watchdog-重启案例)

---

## 1. 高频面试问题

### Q1：WatchDog 的监控原理是什么？HandlerChecker 和 Monitor 分别起什么作用？

这道题考察你是否理解 WatchDog 的「心跳检测」设计。面试官想知道你是否清楚 WatchDog 如何判断系统服务是否卡死、HandlerChecker 和 Monitor 的分工以及它们之间的协作关系。

### Q2：WatchDog 触发后系统会做什么？请描述从检测超时到 system_server 重启的完整流程。

这是一道高频追问。面试官想考察你对 WatchDog「自毁式」保护机制的完整理解：从 dump 堆栈、杀死进程到 init 进程重新拉起的全链路。

### Q3：如何分析 WatchDog 产生的日志？ANR 和 WatchDog 有什么区别？

这道题考察你的问题定位能力。WatchDog 重启属于系统级致命故障，能够快速从日志中定位根因是高级工程师的必备技能。同时你需要清楚地区分 ANR（应用层超时）和 WatchDog（系统层超时）。

### Q4：FdMonitor（文件描述符监控）是怎么回事？它和传统的 HandlerChecker 有什么不同？

Android 10 之后新增的机制。面试官想看你是否跟进最新的系统变化，了解 FdMonitor 如何通过 epoll 监控 `/proc/self/fd` 目录来检测 FD 泄漏导致的系统卡死。

### Q5：如果让你设计一个系统服务健康检查框架，你会参考 WatchDog 的哪些设计思想？

开放性问题，考察你对 WatchDog 设计精髓的抽象能力：超时分层、心跳机制、Monitor 解耦、自愈/自毁策略。

---

## 2. 标准答案与机制对比

### 2.1 WatchDog 监控原理 — 心跳检测模型

WatchDog 本质上是一个**单例守护线程**，运行在 system_server 进程中，通过**轮询心跳**的方式检测系统关键服务的健康状态。它的检测对象分为两大类：

#### 第一类：HandlerChecker — 检测目标线程的 Looper 是否响应

HandlerChecker 是最核心的检测单元。每个 HandlerChecker 绑定到一个特定的 Handler（即一个 MessageQueue/Looper），通过向目标线程发送一个空的 `Runnable`（称为「心跳消息」），然后等待该 Runnable 执行完毕来确认目标线程的 Looper 仍在正常运转。

关键服务及其被检测线程：

| 服务 | 检测的线程 | HandlerChecker 名称 | 超时时间 |
|------|-----------|-------------------|---------|
| AMS (ActivityManagerService) | **主线程** (ActivityManager) | `foreground thread` | 60s (DEFAULT_TIMEOUT) |
| WMS (WindowManagerService) | **主线程** | 同上检测 | — |
| PMS (PackageManagerService) | **主线程** | 同上检测 | — |
| IMS (InputManagerService) | **InputDispatcher 线程** | `input dispatcher thread` | 60s |
| Netd/ConnectivityService | **NetworkManagement 线程** | `network management thread` | 60s |
| ActivityManager | **UI 线程** | `ui thread` | 60s |
| FgThread | **Fg 线程** | `foreground thread` | 60s |
| IoThread | **I/O 线程** | `i/o thread` | 60s |
| DisplayThread | **Display 线程** | `android.display` | 60s |
| AnimationThread | **Animation 线程** | `android.anim` | 60s |

**工作流程：**

1. WatchDog 线程每隔 **30 秒**（`CHECK_INTERVAL = 30s`）唤醒一次
2. 遍历所有 HandlerChecker，调用 `scheduleCheckLocked()` 向目标线程发送心跳 Runnable
3. 轮询等待（每次等待 `CHECK_INTERVAL/2 = 15s`，并带有一个 `wait()` 超时）
4. 如果超过 **60 秒**（`DEFAULT_TIMEOUT`）仍未收到响应 → 判定该线程卡死
5. 收集所有已超时的 HandlerChecker，进入 **dump + 自杀** 流程

#### 第二类：Monitor — 检测锁竞争

Monitor 是 HandlerChecker 的一个子概念。每个 HandlerChecker 内部维护一个 `ArrayList<Monitor>` 列表。当 HandlerChecker 执行心跳消息时，除了执行 Runnable 本身，还会依次调用每个 Monitor 的 `monitor()` 方法。

```java
// Watchdog.Monitor 接口
public interface Monitor {
    void monitor();
}
```

每个系统服务（如 AMS、WMS、PMS）会向 WatchDog 注册自己的 Monitor 实现。Monitor 的 `monitor()` 方法中通常会去尝试获取该服务的关键锁：

```java
// AMS 的 Monitor 实现示例
public void monitor() {
    synchronized (this) {
        // 如果 AMS 的锁被长时间持有，这里就会阻塞
    }
}
```

**Monitor 的检测逻辑**：如果某个 Monitor 的 `monitor()` 调用超过 60 秒没有返回，说明该服务的关键锁被长时间持有，系统处于死锁或严重锁竞争状态。

#### HandlerChecker vs Monitor 的核心区别

| 维度 | HandlerChecker | Monitor |
|------|---------------|---------|
| 检测对象 | 线程 Looper 的响应性 | 服务关键锁的可用性 |
| 判定标准 | 心跳 Runnable 是否在超时前执行 | `monitor()` 是否在超时前返回 |
| 超时维度 | 线程消息队列堆积 | 锁竞争/死锁 |
| 典型场景 | 主线程耗时操作、大量消息堆积 | 持锁执行耗时操作、死锁 |

---

### 2.2 WatchDog 触发后的完整处理流程

当 WatchDog 检测到超时后，会触发一套**不可逆的自毁流程**。具体步骤：

**第一步：收集系统状态信息 (dump)**

WatchDog 调用 `ActivityManagerService.dumpStackTraces()`，触发以下 dump 操作：

- **Java 堆栈**：所有 Java 线程的堆栈 dump 到 `/data/anr/traces.txt`
- **Native 堆栈**：通过 `debuggerd` 收集 Native 层堆栈
- **内核栈**：dump 所有线程在内核态的调用栈
- **Ftrace**：可选的 kernel ftrace 信息

**第二步：杀死 system_server 进程**

WatchDog 调用 `Process.killProcess(Process.myPid())`，发送 SIGKILL 信号给 system_server 自身。

```java
// Watchdog.java 核心代码
Slog.e(TAG, "*** WATCHDOG KILLING SYSTEM PROCESS: " + name);
Process.killProcess(Process.myPid());
System.exit(10);
```

**第三步：init 进程检测到 system_server 死亡**

init 进程是 Android 用户空间的第一个进程（PID=1），它是所有系统服务的「祖先进程」。init 通过 `waitpid()` 监控 system_server 进程状态，一旦检测到其死亡：

1. 读取 `init.rc` 中 `service system_server` 的 `onrestart` 配置
2. 执行 `restart` 操作：重新 fork 并启动 system_server
3. system_server 重新加载所有系统服务（AMS、WMS、PMS、PKMS 等）

**第四步：系统重启**

当 system_server 重启后，意味着所有系统服务都会重新初始化：
- Zygote 进程不受影响（它独立于 system_server）
- 已启动的 App 进程不受影响（它们由 Zygote fork，不依赖 system_server 的存活）
- **但 App 进程与 system_server 的 Binder 连接会断开**，表现为应用发生 DeadObjectException
- AMS 重启后会重建所有 App 进程的信息（从 `/data/system/` 恢复持久化数据）

**完整时间线：**

```
T=0s      WatchDog 线程定期唤醒，开始新一轮检测
T=30s     第二轮心跳仍未收到某 HandlerChecker 响应
T=60s     超时确认！触发 WatchDog 流程
T=60s~    dumpStackTraces() → 写入 /data/anr/traces.txt
T=~61s    Process.killProcess(myPid) → system_server 收到 SIGKILL
T=~62s    init 检测到 system_server 死亡
T=~63s    init fork + exec system_server
T=~65s    system_server 启动完成，AMS 开始恢复状态
T=~70s    系统基本恢复正常
```

> **注意**：用户侧表现为设备自动重启到开机动画（bootanimation），但实际上只有 system_server 重启，内核和 init 并未重启，这不是一次完整的系统重启 — 业内称之为「**热重启 (Hot Reboot)**」或「**system_server 重启**」。

---

### 2.3 ANR vs WatchDog — 关键区别

| 维度 | ANR (Application Not Responding) | WatchDog |
|------|--------------------------------|----------|
| 检测主体 | **AMS / InputDispatcher** | **WatchDog 线程** |
| 检测对象 | **App 进程的主线程** | **system_server 的系统服务线程** |
| 触发原因 | App 主线程 5~10 秒内未响应输入事件/Broadcast/Service | 系统服务线程 60 秒内未响应心跳 |
| 后果 | 弹 ANR 对话框；用户可选择「等待」或「关闭」 | system_server 自杀重启（不可逆） |
| 日志位置 | `/data/anr/anr_*.txt` | 与 ANR dump 相同的 `/data/anr/traces.txt` |
| 系统影响 | 单个应用无响应，不影响系统 | 整个系统重启，所有应用受影响 |
| 超时时间 | 输入事件 5s / Broadcast 10s(前台)/60s(后台) / Service 20s(前台)/200s(后台) | 统一 60s（`DEFAULT_TIMEOUT`） |
| 可恢复性 | 可以恢复（用户等待或杀进程） | 不可恢复（必须重启 system_server） |

**关键面试话术**：

> ANR 是应用层的「假死」检测，系统还有主动权，可以选择等待或者杀应用进程。而 WatchDog 是系统层的「真死」检测 — 系统服务本身已经无法正常工作，唯一的选择就是自杀重启。WatchDog 是 Android 的最后一道防线。

---

### 2.4 FdMonitor — 文件描述符泄漏监控

Android 10 引入的 FdMonitor 是对传统 HandlerChecker 机制的重要补充。某些情况下系统卡死并非因为锁竞争或消息队列堆积，而是因为**文件描述符泄漏耗尽**，导致无法创建新的 Binder 连接或打开文件。

**FdMonitor 原理：**

1. **监控对象**：`/proc/self/fd` 目录（当前进程已打开的所有文件描述符）
2. **监控方式**：通过 Linux `inotify` 机制监控 `/proc/self/fd` 目录的 inode 变化
3. **阈值告警**：当 FD 数量超过阈值（默认 1024），FdMonitor 触发 dump
4. **周期性检测**：每 30 秒执行一次 `readdir` 扫描 FD 目录，统计 FD 数量

```java
// FdMonitor 工作原理简示
File fdDir = new File("/proc/self/fd");
int fdCount = fdDir.list().length;  // 统计已打开的 FD 数量
if (fdCount > threshold) {
    // 触发 dump + 告警
    dumpFdLeakInfo();
}
```

**FdMonitor 与 HandlerChecker 的协作关系：**

- HandlerChecker 检测的是「**功能性卡死**」（线程不响应）
- FdMonitor 检测的是「**资源性卡死**」（FD 耗尽导致无法工作）
- 两者互为补充，共同构成 WatchDog 的完整检测体系

---

## 3. 核心原理深度剖析

### 3.1 WatchDog 线程模型

WatchDog 是 system_server 进程中的一个**守护线程**，在 SystemServer 启动流程中创建并启动：

```
SystemServer.run()
  → startBootstrapServices()
    → startOtherServices()
      → Watchdog.getInstance().start()   // 启动 WatchDog 线程
```

WatchDog 采用**饿汉式单例**模式，整个 system_server 进程中只有一个 WatchDog 实例：

```java
public class Watchdog extends Thread {
    private static Watchdog sWatchdog;
    
    public static Watchdog getInstance() {
        if (sWatchdog == null) {
            sWatchdog = new Watchdog();
        }
        return sWatchdog;
    }
}
```

### 3.2 核心检测流程

```
┌──────────────────────────────────────────────────────┐
│                 Watchdog.run() 主循环                   │
│                                                      │
│  while (true) {                                      │
│    ① stepMonitors()      — 检查所有 Monitor          │
│    ② wait(30s)            — 睡眠等待                  │
│    ③ evaluteCheckerStates() — 评估各 Checker 状态     │
│    ④ if (有超时) → dumpAndKill()  — 自杀              │
│  }                                                    │
└──────────────────────────────────────────────────────┘
```

### 3.3 HandlerChecker 内部状态机

每个 HandlerChecker 有四种状态：

```
WAITING (等待中)        → 已发送心跳，等待目标线程执行
   ↓ (心跳执行完成)
COMPLETED (已完成)      → 目标线程正常响应
   ↓ (新一轮检测开始)
WAITING                 → 重新发送心跳...

WAITING (等待中)
   ↓ (超过 60 秒未响应)
OVERDUE (已超时)        → 标记为超时，触发 dumpAndKill
```

**scheduleCheckLocked() 核心逻辑：**

```java
public void scheduleCheckLocked() {
    if (mCompleted) {
        // 新轮次开始，重置状态
        mCompleted = false;
        mCurrentMonitor = null;
    }
    
    if (!mStarted) {
        // 发送心跳消息到目标线程的消息队列
        mHandler.postAtFrontOfQueue(this);  // this 即 Runnable
        mStarted = true;
    }
}
```

**getCompletionStateLocked() — 超时判断：**

```java
public int getCompletionStateLocked() {
    if (mCompleted) {
        return COMPLETED;
    } else {
        long latency = SystemClock.uptimeMillis() - mStartTime;
        if (latency > mTimeout) {  // 默认 60s
            return OVERDUE;
        } else {
            return WAITING;
        }
    }
}
```

### 3.4 「饿死」问题的解决

WatchDog 本身也是一个线程，如果 system_server 整体 CPU 饥饿（比如被 cgroup 限制或被其他高优先级任务抢占），WatchDog 线程也可能得不到执行。为了解决这个问题：

1. **WatchDog 线程优先级设为 `THREAD_PRIORITY_FOREGROUND`**（高优先级）
2. **使用 `SystemClock.uptimeMillis()`** 而不是 `System.currentTimeMillis()`，前者不受系统时间调整影响
3. **每个 Checker 独立计时**，即使 WatchDog 自己被阻塞，下次唤醒时仍能正确判断超时

---

## 4. 流程图：WatchDog 监控→超时→dump→重启

```
                                ┌──────────────────────┐
                                │  SystemServer 启动     │
                                │  Watchdog.start()     │
                                └──────────┬───────────┘
                                           │
                                           ▼
                                ┌──────────────────────┐
                                │  WatchDog 线程进入     │
                                │  run() 主循环          │
                                └──────────┬───────────┘
                                           │
                          ┌────────────────┼────────────────┐
                          │                │                │
                          ▼                ▼                ▼
                 ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
                 │Foreground    │  │Main Thread   │  │I/O Thread    │
                 │Checker       │  │Checker       │  │Checker       │
                 │(AMS Monitor) │  │(WMS Monitor) │  │(PKMS Monitor)│
                 └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
                        │                 │                 │
                        │  发送心跳到      │                 │
                        │  目标线程        │                 │
                        ▼                 ▼                 ▼
                 ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
                 │ 等待 30s      │  │ 等待 30s      │  │ 等待 30s      │
                 │ ... 60s       │  │ ... 响应OK    │  │ ... 响应OK    │
                 │ 超时!         │  │              │  │              │
                 └──────┬───────┘  └──────────────┘  └──────────────┘
                        │
                        ▼
                 ┌──────────────────────────────────────┐
                 │  Watchdog 判定: Foreground Checker   │
                 │  超时 60s → 触发自杀流程               │
                 └──────────────┬───────────────────────┘
                                │
                                ▼
                 ┌──────────────────────────────────────┐
                 │  Phase 1: Dump 阶段                    │
                 │                                      │
                 │ ① dumpKernelStackTraces()            │
                 │    写入内核栈到 traces.txt             │
                 │ ② AMS.dumpStackTraces()              │
                 │    收集所有 Java 线程栈                │
                 │ ③ native_debuggerd_dump()            │
                 │    收集 Native 线程栈                  │
                 │ ④ 输出到 /data/anr/traces.txt         │
                 └──────────────┬───────────────────────┘
                                │
                                ▼
                 ┌──────────────────────────────────────┐
                 │  Phase 2: Kill 阶段                    │
                 │                                      │
                 │ ① Slog.e("WATCHDOG KILLING...")       │
                 │ ② Process.killProcess(myPid)         │
                 │    → SIGKILL 发送给 system_server     │
                 │ ③ System.exit(10)                    │
                 └──────────────┬───────────────────────┘
                                │
                                ▼
                 ┌──────────────────────────────────────┐
                 │  Phase 3: Init 检测与重启              │
                 │                                      │
                 │ init 进程 (PID=1)                     │
                 │  → waitpid() 检测到 system_server 死亡 │
                 │  → 解析 init.rc 中的 onrestart 指令    │
                 │  → restart servicemanager             │
                 │  → restart surfaceflinger             │
                 │  → restart zygote                    │
                 │  → restart system_server              │
                 └──────────────┬───────────────────────┘
                                │
                                ▼
                 ┌──────────────────────────────────────┐
                 │  Phase 4: 系统恢复                     │
                 │                                      │
                 │ ① system_server 重新启动              │
                 │ ② SystemServer.run() 重新执行          │
                 │ ③ 所有系统服务重新初始化                │
                 │ ④ AMS 从 /data/system/ 恢复状态        │
                 │ ⑤ App 进程 Binder 连接重建             │
                 │ ⑥ 用户看到开机动画 (~5-10秒)            │
                 └──────────────────────────────────────┘
```

---

## 5. 源码分析：WatchDog.run() 与 HandlerChecker

### 5.1 WatchDog.run() — 主循环

以下代码来自 `frameworks/base/services/core/java/com/android/server/Watchdog.java`（Android 12，核心逻辑多版本通用）：

```java
@Override
public void run() {
    boolean waitedHalf = false;
    while (true) {
        final List<HandlerChecker> blockedCheckers;
        final String subject;
        final boolean allowRestart;
        int debuggerWasConnected = 0;
        
        synchronized (this) {
            long timeout = CHECK_INTERVAL;  // 默认 30 秒
            
            // ① 向所有 Checker 发送心跳消息
            for (int i = 0; i < mHandlerCheckers.size(); i++) {
                HandlerChecker hc = mHandlerCheckers.get(i);
                hc.scheduleCheckLocked();
            }
            
            // ② 记录开始时间
            long start = SystemClock.uptimeMillis();
            
            // ③ 等待 CHECK_INTERVAL（30秒）或被 notify 唤醒
            while (timeout > 0) {
                try {
                    wait(timeout);  // 释放锁，等待 30 秒
                } catch (InterruptedException e) {
                    // ignore
                }
                timeout = CHECK_INTERVAL - 
                    (SystemClock.uptimeMillis() - start);
            }
            
            // ④ 评估所有 Checker 的状态
            blockedCheckers = getBlockedCheckersLocked();
            subject = describeCheckersLocked(blockedCheckers);
            allowRestart = mAllowRestart;
        }
        
        // ⑤ 如果存在超时的 Checker → 触发自杀流程
        if (blockedCheckers.size() > 0) {
            // 再等一次（给系统一个最后的机会）
            if (!waitedHalf) {
                waitedHalf = true;
                continue;
            }
            
            // 最终确认超时 → DUMP AND KILL
            Slog.e(TAG, "*** WATCHDOG KILLING SYSTEM PROCESS: "
                + subject);
            
            // Dump 所有线程栈
            ActivityManagerService.dumpStackTraces(
                AMS_PID, 
                ProcessList.FIRST_APPLICATION_UID,
                null  // no additional pids
            );
            
            // 杀死自己
            Process.killProcess(Process.myPid());
            System.exit(10);
        }
        
        waitedHalf = false;
    }
}
```

**关键设计点分析：**

1. **`waitedHalf` 机制**：当第一次检测到超时时，并不立即自杀，而是给系统额外 30 秒的宽限期。这是一个「二次确认」机制，避免因为瞬时高负载导致的假阳性。

2. **`wait(timeout)` 而非 `sleep()`**：使用 `Object.wait()` 可以在等待期间被其他线程通过 `notify()` 提前唤醒，这在系统正常运行时可以加速检测循环。

3. **同步块设计**：`scheduleCheckLocked()` 和状态评估都在同一个 `synchronized(this)` 块中完成，保证 Checker 状态的一致性。

### 5.2 HandlerChecker.scheduleCheckLocked() — 发送心跳

```java
public final class HandlerChecker implements Runnable {
    private final Handler mHandler;
    private final String mName;
    private final long mTimeout;  // 默认 DEFAULT_TIMEOUT = 60s
    private final ArrayList<Monitor> mMonitors = new ArrayList<>();
    
    private boolean mCompleted;
    private Monitor mCurrentMonitor;
    private long mStartTime;
    
    HandlerChecker(Handler handler, String name, long timeout) {
        mHandler = handler;
        mName = name;
        mTimeout = timeout;
    }
    
    // 添加 Monitor
    public void addMonitor(Monitor monitor) {
        mMonitors.add(monitor);
    }
    
    // 发送心跳消息
    public void scheduleCheckLocked() {
        if (mCompleted) {
            // 上一轮已完成，开始新一轮
            mCompleted = false;
            mCurrentMonitor = null;
        }
        
        if (!mStarted) {
            // 将自身作为 Runnable 投递到目标线程的消息队列头部
            mHandler.postAtFrontOfQueue(this);
            mStarted = true;
            mStartTime = SystemClock.uptimeMillis();
        }
    }
    
    // 这是心跳消息的执行体
    @Override
    public void run() {
        final int size = mMonitors.size();
        for (int i = 0; i < size; i++) {
            synchronized (this) {
                mCurrentMonitor = mMonitors.get(i);
            }
            // 调用 Monitor.monitor() —— 这里可能阻塞！
            mCurrentMonitor.monitor();
        }
        
        synchronized (this) {
            mCompleted = true;
            mCurrentMonitor = null;
            mStarted = false;  // 准备下一轮
        }
    }
    
    // 判断是否超时
    public int getCompletionStateLocked() {
        if (mCompleted) {
            return COMPLETED;
        } else {
            long latency = SystemClock.uptimeMillis() - mStartTime;
            if (latency > mTimeout) {
                // 超过 60 秒未完成 → OVERDUE
                return OVERDUE;
            } else {
                return WAITING;
            }
        }
    }
}
```

**为什么用 `postAtFrontOfQueue`？**

`postAtFrontOfQueue` 将心跳消息插入到消息队列的**头部**，这意味着它几乎可以立即被处理（除非当前正在执行的消息耗时很长）。这确保了心跳检测的敏感度 — 如果即使插入头部的消息也无法在 60 秒内执行，说明目标线程确实处于严重的阻塞状态。

### 5.3 AMS 的 Monitor 注册

```java
// ActivityManagerService.java
public class ActivityManagerService extends IActivityManager.Stub
        implements Watchdog.Monitor, BatteryStatsImpl.BatteryCallback {
    
    // AMS 构造过程中向 Watchdog 注册 Monitor
    public ActivityManagerService(Context systemContext) {
        // ...
        Watchdog.getInstance().addMonitor(this);  // 注册自己为 Monitor
        Watchdog.getInstance().addThread(mHandler);  // 注册主线程 Handler
        
        // 注册其他关键线程
        Watchdog.getInstance().addThread(mUiHandler, "ui");
        Watchdog.getInstance().addThread(mIoHandler, "i/o");
        Watchdog.getInstance().addThread(mFgHandler, "foreground");
    }
    
    // Monitor 接口实现 —— 检测 AMS 锁
    @Override
    public void monitor() {
        synchronized (this) {
            // 空方法体！
            // 只要 synchronized (this) 能获取锁就立刻返回
            // 如果拿不到锁（被其他线程持有），则会阻塞 → 被 Watchdog 判定超时
        }
    }
}
```

**WMS 也类似注册：**

```java
// WindowManagerService.java
public class WindowManagerService extends IWindowManager.Stub
        implements Watchdog.Monitor {
    
    private WindowManagerService(Context context, ...) {
        // ...
        Watchdog.getInstance().addMonitor(this);  // WMS 也注册为 Monitor
    }
    
    @Override
    public void monitor() {
        synchronized (mGlobalLock) {  // WMS 的全局锁
            // ...
        }
    }
}
```

---

## 6. 应用场景：系统死锁导致 WatchDog 重启案例

### 6.1 场景描述

假设 AMS 正在持锁执行一个耗时的 `broadcastIntent()` 操作，而 WMS 正好需要调用 AMS 的某个方法（同样需要 AMS 锁）。同时 InputDispatcher 线程也需要 AMS 锁来通知焦点变化。

```
AMS 主线程：持有 AMS 锁 → 等待 WMS 的某些操作完成
   ↑                              ↓
   │                              │
   └── WMS 线程：需要 AMS 锁 ←────┘  （死锁！）
```

### 6.2 日志特征分析

当 WatchDog 触发时，你在 `logcat` 中会看到以下特征日志：

```
// 第一次检测到异常
W Watchdog: *** WATCHDOG WAITING FOR HALF OF A MINUTE: 
W Watchdog: foreground thread {not complete, blocked on monitor 
W Watchdog:   for ActivityManager}

// 60 秒后最终确认
E Watchdog: *** WATCHDOG KILLING SYSTEM PROCESS: 
E Watchdog: foreground thread stack trace:
E Watchdog:   at com.android.server.am.ActivityManagerService.monitor(AMS.java:12345)
E Watchdog:   at com.android.server.Watchdog$HandlerChecker.run(Watchdog.java:234)
E Watchdog:   at android.os.Handler.dispatchMessage(Handler.java:106)
E Watchdog:   ...

// Kill 确认
I Process: Sending signal. PID: 1234 SIG: 9  // system_server 进程
```

### 6.3 traces.txt 分析要点

打开 `/data/anr/traces.txt`（通常在 bugreport 中），搜索 `WATCHDOG KILLING`：

```
----- pid 1234 at 2024-01-15 10:23:45 -----
Cmd line: system_server

"main" prio=5 tid=1 Blocked
  | group="main" sCount=1 ucsCount=0 flags=1 obj=0x7240a7a8 self=0xb400007d0000
  | sysTid=1234 nice=-2 cgrp=default sched=0/0 handle=0x7d1234abcd
  | state=S schedstat=( 999999999 888888888 1234 ) utm=100 stm=50 core=4 HZ=100
  | stack=...
  at com.android.server.wm.WindowManagerService.relayoutWindow(WMS.java:5678)
  - waiting to lock <0x0a1b2c3d> (a com.android.server.am.ActivityManagerService)
  - held by thread "ActivityManager" (tid=56)

"ActivityManager" prio=5 tid=56 Blocked
  | group="main" sCount=1 ucsCount=0 flags=1 obj=0x7240b9c0 self=0xb400007d8000
  | sysTid=1267 nice=-2 cgrp=default sched=0/0 handle=0x7d5678ef00
  | state=S
  at com.android.server.am.ActivityManagerService.broadcastIntent(AMS.java:9012)
  - waiting to lock <0x0d4e5f6a> (a com.android.server.wm.WindowManagerService)
  - held by thread "main" (tid=1)
```

**分析结论：**

> main 线程持 WMS 锁等 AMS 锁，ActivityManager 线程持 AMS 锁等 WMS 锁 → **经典死锁**。WatchDog 的 Foreground Checker 在 60 秒内无法完成 AMS Monitor → 触发自杀重启。

### 6.4 常见 WatchDog 触发原因总结

| 原因类别 | 典型场景 | 日志特征 |
|---------|---------|---------|
| **死锁** | AMS ↔ WMS 循环等待锁 | tid 相互 blocked，waiting to lock 彼此持有的对象 |
| **主线程耗时操作** | 系统服务在主线程执行 I/O、大量计算 | `foreground thread` 超时，MONITOR 阶段卡在 `monitor()` |
| **Binder 线程池耗尽** | 大量并发 Binder 调用占满所有 Binder 线程 | `Binder Thread Pool full` 日志，多个 App 进程 blocked |
| **FD 泄漏** | 文件描述符耗尽，无法创建新连接 | FdMonitor 告警，`/proc/self/fd` 数量 > 1024 |
| **内存压力** | 系统内存极低，system_server 各线程被挂起等内存回收 | `kswapd` 高 CPU，`GFP_KERNEL` 分配失败 |
| **SurfaceFlinger 死锁** | SF 持锁阻塞 → WMS Binder 调用超时 → AMS 连锁阻塞 | SF 线程 blocked，WMS 线程 waiting for Binder reply |

### 6.5 调试技巧与排查方法

**1. 获取 WatchDog 触发时的完整现场：**

```bash
# 复现问题前开启更多日志
adb shell dumpsys activity watchdog

# 获取完整 bugreport（含 traces.txt）
adb bugreport watchdog_analysis.zip
```

**2. 分析死锁的工具：**

```bash
# 使用 jstack 分析 Java 线程栈
# 使用 debuggerd 获取 native 栈
adb shell debuggerd -b <pid>

# 使用 systrace/perfetto 获取调度信息（看是谁持锁不放）
```

**3. 代码层面预防 WatchDog：**

```java
// 系统服务编程黄金法则：
// ① 绝不在主线程做 I/O 操作
// ② 持锁时间尽可能短
// ③ 避免嵌套锁（按固定顺序获取多把锁）
// ④ 将所有耗时操作放到工作线程（HandlerThread / ThreadPool）
// ⑤ Binder 调用要设置超时（避免无限等待）
```

---

## 总结

WatchDog 是 Android 系统稳定性的「守夜人」。它本质上是一个**基于心跳的超时检测框架**，通过 HandlerChecker 检测线程 Looper 响应、通过 Monitor 检测关键锁的可用性。当检测到系统服务卡死超过 60 秒时，它会触发一场「可控的自毁」— dump 所有现场信息后杀死 system_server，由 init 进程重新拉起整个系统服务栈。

理解 WatchDog，不仅是理解一个机制，更是理解 Android 系统设计中「**面对不可恢复错误时的处理哲学**」：

> 与其让系统以一种不可预测的方式崩溃，不如在检测到异常时主动、干净地重启，并留下足够的诊断信息。这是一种「fail-fast and recover」的设计思想。
