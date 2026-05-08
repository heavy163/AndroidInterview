# ANR 分析与解决

> **面试权重**: ★★★★★ | **字数**: ~4500 字 | **阅读时间**: 约 25 分钟

---

## 目录

1. [面试高频问题](#1-面试高频问题)
2. [标准答案与超时对照](#2-标准答案与超时对照)
3. [核心原理深度剖析](#3-核心原理深度剖析)
4. [流程图：ANR 触发与 trace 文件生成](#4-流程图anr-触发与-trace-文件生成)
5. [源码分析：从 InputDispatcher 到 AMS](#5-源码分析从-inputdispatcher-到-ams)
6. [应用场景：主线程 IO 导致 ANR 的排查与修复](#6-应用场景主线程-io-导致-anr-的排查与修复)

---

## 1. 面试高频问题

### Q1: Android 中三种常见 ANR 的超时时间分别是多少？

**标准答案：**

| ANR 类型 | 触发组件 | 前台超时 | 后台超时 | 触发机制 |
|:--------|:--------|:-------:|:-------:|:--------|
| Input ANR | InputDispatcher | **5 秒** | **5 秒** | 输入事件（触屏/按键）在 5s 内未被窗口消费 |
| Service ANR | AMS (ActiveServices) | **20 秒** | **200 秒** | Service 的 `onCreate()` / `onStartCommand()` 等生命周期超时 |
| Broadcast ANR | AMS (BroadcastQueue) | **10 秒** | **60 秒** | `onReceive()` 在主线程执行超时 |
| ContentProvider ANR | AMS | **10 秒** | — | Provider 发布超时（较少见） |

> **内存口诀**：「输入 5，服务 20/200，广播 10/60」。

### Q2: ANR 的触发机制是什么？由谁发出？

ANR 不是由一个统一模块发出的，而是由 **InputDispatcher** 和 **AMS** 分别在各自超时检测点触发：

- **Input ANR**: `InputDispatcher` 在分发输入事件时，检测目标窗口的 `finishedToken` 是否在 5s 内返回。若未返回，调用 `notifyANR()` → `InputManagerService` → `AMS.appNotResponding()`。
- **Service ANR**: `ActiveServices` 在 `scheduleServiceTimeoutLocked()` 中通过 `Handler.sendMessageDelayed(SERVICE_TIMEOUT_MSG)` 设置定时器。如果 Service 在规定时间内未调用 `serviceDoneExecuting()`，定时器触发 → `AMS.appNotResponding()`。
- **Broadcast ANR**: `BroadcastQueue` 在 `processNextBroadcast()` 中设置超时消息 `BROADCAST_TIMEOUT_MSG`。BroadcastReceiver 的 `onReceive()` 未在规定时间内返回 → `broadcastTimeoutLocked()` → `AMS.appNotResponding()`。

**最终汇聚点**：所有 ANR 最终都会调用 `ProcessRecord.appNotResponding()`，统一执行：dump 进程信息 → 弹 ANR 对话框 → 写入 event log → 生成 `/data/anr/traces.txt`。

### Q3: ANR 的 trace 文件如何解读？关键信息有哪些？

**拿到 trace.txt 后按以下顺序解读**（效率最高）：

**第一步：定位主线程状态**
搜索 `"main" prio=5 tid=1`，找到主线程当前的线程状态：

```
"main" prio=5 tid=1 Blocked / Waiting / Native / Runnable
  | group="main" sCount=1 ucsCount=0 flags=1 obj=0x...
  | sysTid=12345 nice=-10 cgrp=default sched=0/0 handle=0x...
  | state=S  schedstat=( ... ) utm=... stm=... core=...
  at com.example.MyClass.heavyMethod(MyClass.java:100)
  - waiting to lock <0x0a1b2c3d> (a java.lang.Object) held by thread #42
```

**关键判断逻辑**：

| 主线程 state | 含义 | 排查方向 |
|:-----------|:----|:-------|
| `Blocked` | 等待其他线程持有的锁 | 找到 `held by thread #N`，查看 #N 线程在做什么 |
| `Waiting` | Object.wait() / Thread.join() / 条件等待 | 检查谁在 notify / 等待条件何时满足 |
| `Native` | 正在执行 JNI / native 代码 | Binder 调用、IO 操作、OpenGL 渲染等 |
| `Runnable` | 在运行队列中但未分配到 CPU | 可能是 CPU 过载，或者是执行了耗时计算 |
| `Sleeping` | Thread.sleep() | 直接的代码问题，移除 sleep |

**第二步：定位持锁线程**
如果主线程是 `Blocked`，找到它等待的锁被哪个线程持有：

```
- waiting to lock <0x0a1b2c3d> → held by thread #42
```

然后搜索 `tid=42`，分析该线程的工作——通常是 DB 操作、文件 IO、网络请求等耗时任务持锁不放。

**第三步：检查 Binder 线程状态**
Binder 线程数量通常在 16~64 之间（取决于 `ro.binder.threads` 属性）。如果大量 Binder 线程处于 `Native` 状态（Binder 阻塞），说明系统服务压力大或存在死锁。

**第四步：看 ANR Reason 行**
文件最开头的 `----- pid 12345 at 2026-05-08 10:30:00 -----` 下方有 `Cmd line:` 和 `subject:`，后者就是 ANR 原因：

```
subject: Input dispatching timed out (Waiting because no window has focus...)
subject: executing service com.example/.MyService
subject: Broadcast of Intent { act=android.intent.action.SCREEN_ON }
```

### Q4: 主线程卡顿与 ANR 是什么关系？

- **主线程卡顿**（BlockCanary / Looper 监控）：主线程中某条 `Message` 执行耗时超过阈值（例如 100ms/500ms），导致掉帧 → 用户感知为「卡」。
- **ANR**：是系统级的超时判定（5s/10s/20s），会弹出系统对话框，提示用户「应用无响应」。

**时序关系**：
```
用户操作 → 掉帧(16ms+) → 卡顿感知(100ms+) → 输入 ANR(5s)
```

卡顿是 ANR 的前兆。如果每次主线程消息耗时都能控制在 200ms 以内，ANR 几乎不会发生。但反过来，单次消息 100ms 的卡顿累积 50 条也会触发 Input ANR——因为 InputDispatcher 只关心「我的那个事件等了多久」。

### Q5: Looper 监控方案（Printer 替换 + 消息耗时）如何实现？

**核心原理**：`Looper.loop()` 中每条消息处理前后都会调用 `Printer.println()`：

```java
// Looper.java (伪代码)
for (;;) {
    Message msg = queue.next(); // might block
    // ...
    if (logging != null) {
        logging.println(">>>>> Dispatching to " + msg.target + " " + msg.callback);
    }
    msg.target.dispatchMessage(msg);
    if (logging != null) {
        logging.println("<<<<< Finished to " + msg.target + " " + msg.callback);
    }
}
```

**监控实现**（BlockCanary 核心思路）：

```kotlin
object LooperMonitor {
    private var dispatchStartTime = 0L
    private var dispatchStartThread = ""

    fun install() {
        Looper.getMainLooper().setMessageLogging { x ->
            if (x.startsWith(">>>>> Dispatching")) {
                dispatchStartTime = SystemClock.uptimeMillis()
                dispatchStartThread = x
            } else if (x.startsWith("<<<<< Finished")) {
                val cost = SystemClock.uptimeMillis() - dispatchStartTime
                if (cost > THRESHOLD_MS) {
                    // dump 主线程 stack
                    val stackTrace = Looper.getMainLooper().thread.stackTrace
                    reportSlowMessage(cost, stackTrace, dispatchStartThread)
                }
            }
        }
    }
}
```

**进阶：ANR 预警**
- 阈值设置为 2s（Input ANR 为 5s，提前 3s 预警）
- 当检测到超过 2s 时，立即 dump 主线程堆栈和 CPU 使用情况
- 上报到 APM 平台，作为 ANR 的早期信号
- 可以在此时触发优雅降级（例如关闭非关键动画、释放缓存）

### Q6: 如何线上自动化收集 ANR？

**方案一：FileObserver 监听 `/data/anr/traces.txt`**（ROOT/系统应用）
```kotlin
val observer = FileObserver("/data/anr/", FileObserver.CLOSE_WRITE) {
    val tracesFile = File("/data/anr/traces.txt")
    if (tracesFile.exists()) {
        uploadTraces(tracesFile.readText())
    }
}
observer.startWatching()
```

**方案二：`getHistoricalProcessExitReasons()`**（Android 11+，推荐）
```kotlin
val am = context.getSystemService<ActivityManager>()
val reasons = am.getHistoricalProcessExitReasons("com.your.package", 0, 5)
for (reason in reasons) {
    if (reason.reason == ApplicationExitInfo.REASON_ANR) {
        val anrTrace = reason.traceInputStream?.bufferedReader()?.readText()
        uploadANR(anrTrace, reason.timestamp, reason.description)
    }
}
```
> 优点：无需 ROOT，可获取 ANR 的 trace 流 + 描述信息 + 时间戳。

**方案三：Signal Catcher 拦截**（Android 内部）
系统在 dump ANR trace 时会向目标进程发送 `SIGQUIT` 信号（signal 3）。进程中的 `Signal Catcher` 线程收到后执行 dump。可通过 `Runtime.getRuntime().postCollectStackTrace()` 主动收集。

---

## 2. 标准答案与超时对照

### 完整超时对照表

| ANR 类型 | 组件 | 前台超时 | 后台超时 | 源码位置 | 可配置 |
|:--------|:----|:-------:|:-------:|:--------|:-----:|
| Input ANR | InputDispatcher | **5s** | **5s** | `InputDispatcher.cpp::dispatchOnceInnerLocked()` | ❌ 硬编码 |
| Service (前台) | ActiveServices | **20s** | — | `ActiveServices.java::SERVICE_TIMEOUT` | ✅ `SERVICE_TIMEOUT` |
| Service (后台) | ActiveServices | — | **200s** | `ActiveServices.java::SERVICE_BACKGROUND_TIMEOUT` | ✅ |
| Broadcast (前台) | BroadcastQueue | **10s** | — | `BroadcastQueue.java::BROADCAST_FG_TIMEOUT` | ❌ |
| Broadcast (后台) | BroadcastQueue | — | **60s** | `BroadcastQueue.java::BROADCAST_BG_TIMEOUT` | ❌ |
| ContentProvider | AMS | **10s** | — | `ActivityManagerService.java::CONTENT_PROVIDER_PUBLISH_TIMEOUT` | ❌ |

### 超时值为什么这样设计？

- **Input 5s**：5 秒是用户耐心边界。心理学研究表明，用户对 2~5s 的等待尚可容忍，超过 5s 产生明显的负面情绪。
- **Service 20s/200s**：前台 Service 有通知可见，用户知道它在运行，给 20s 启动时间合理；后台 Service 宽松到 200s，避免系统负载高时频繁误报。
- **Broadcast 10s/60s**：BroadcastReceiver 设计原则是「轻量级」，10s 足够完成简单操作；后台广播给了 60s 的慷慨窗口，但实际开发中仍要求 `goAsync()` + 子线程处理耗时工作。

---

## 3. 核心原理深度剖析

### 3.1 Input ANR 触发机制

```
┌─────────────┐   触摸事件    ┌──────────────────┐
│  TouchPanel │─────────────▶│  InputReader      │
└─────────────┘               │  (EventHub读取)    │
                              └────────┬─────────┘
                                       │ 原始事件
                              ┌────────▼─────────┐
                              │  InputDispatcher  │
                              │  dispatchOnce      │
                              │  InnerLocked()     │
                              └────────┬─────────┘
                                       │ findFocusedWindowTargetsLocked()
                                       │ 找到目标窗口
                              ┌────────▼─────────┐
                              │  startDispatch    │
                              │  CycleLocked()    │
                              │  设置 mPendingEvent│
                              │  记录 dispatchTime │
                              └────────┬─────────┘
                                       │ dispatchKey / dispatchMotion
                                       │ @{eventEntry.dispatchTime > ANR_TIMEOUT}?
                              ┌────────▼─────────┐
                              │  超过 5s?          │
                              │  YES → notifyANR  │
                              │  NO  → 等待完成    │
                              └────────┬─────────┘
                                       │
                              ┌────────▼─────────┐
                              │  InputManagerSvc  │
                              │  notifyANR()      │
                              └────────┬─────────┘
                                       │
                              ┌────────▼─────────┐
                              │  AMS.             │
                              │  appNotResponding │
                              └──────────────────┘
```

**关键点**：InputDispatcher 不关心主线程是否繁忙——它只关心「我发出去的事件，你什么时候消费完」。即使主线程每 100ms 处理一条消息（远快于 5s），但如果没有消费 InputDispatcher 等待的那个特定事件，5s 后依然 ANR。

### 3.2 Service ANR 触发机制

```java
// ActiveServices.java（简化逻辑）
void realStartServiceLocked(ServiceRecord r, ...) {
    // 发送延时消息
    bumpServiceExecutingLocked(r, "create");
    mAm.mHandler.sendMessageAtTime(
        msg, r.executingStart + SERVICE_TIMEOUT); // 前台 20s / 后台 200s
}

void serviceDoneExecutingLocked(ServiceRecord r, ...) {
    // Service 完成后移除此消息
    mAm.mHandler.removeMessages(SERVICE_TIMEOUT_MSG, r);
}
```

如果 `onCreate()` / `onStartCommand()` 中执行了耗时操作（网络请求、数据库初始化），在主线程卡住 → `serviceDoneExecutingLocked()` 永远不被调用 → 超时消息触发 → ANR。

### 3.3 Broadcast ANR 触发机制

```java
// BroadcastQueue.java
final void processNextBroadcast(boolean fromMsg) {
    // 设置超时
    setBroadcastTimeoutLocked(timeoutTime);
    // 分发
    deliverToRegisteredReceiverLocked(r, filter, ...);
}

final void setBroadcastTimeoutLocked(long timeoutTime) {
    mHandler.sendMessageAtTime(
        mHandler.obtainMessage(BROADCAST_TIMEOUT_MSG, this), timeoutTime);
}
```

**与 Service ANR 的共同特征**：都通过 AMS 内部的 `mHandler` 发送延时消息 + 等待组件完成回调。如果回调未在规定时间返回 → `broadcastTimeoutLocked(false)` → `forceCloseBroadcastLocked()` → `appNotResponding()`。

### 3.4 ProcessRecord.appNotResponding()：ANR 的最终汇聚点

无论哪种 ANR，最终都会调用 `AMS` 中的：

```java
// ActivityManagerService.java（核心路径）
final void appNotResponding(ProcessRecord app, ActivityRecord activity,
        ActivityRecord parent, boolean aboveSystem, String annotation) {
    // 1. 记录 ANR 到 EventLog
    EventLog.writeEvent(EventLogTags.AM_ANR, app.userId, app.pid,
            app.processName, app.info.flags, annotation);

    // 2. 收集 FIRST CPU usage（前 5 分钟 CPU 使用率）
    updateCpuStatsNow();
    // 输出到 traces: "CPU usage from Xms to Yms later"

    // 3. 收集进程 traces
    // 向目标进程发送 SIGQUIT (signal 3)
    Process.sendSignal(app.pid, Process.SIGNAL_QUIT);
    // Signal Catcher 线程收到后 dump 所有线程堆栈

    // 4. 如果进程未响应 SIGQUIT，再次 dump
    // 超时后再次尝试

    // 5. 写入 /data/anr/traces.txt
    File tracesFile = new File("/data/anr/traces.txt");
    // ...

    // 6. 显示 ANR 对话框
    if (showDialog) {
        Message msg = mUiHandler.obtainMessage(SHOW_NOT_RESPONDING_UI_MSG, ...);
        mUiHandler.sendMessage(msg);
    }

    // 7. 如果是后台 ANR 且无可见 Activity，直接杀进程
    if (!isShowing) {
        Process.killProcess(app.pid);
    }
}
```

---

## 4. 流程图：ANR 触发与 trace 文件生成

### 4.1 三种 ANR 触发时序对比

```
时间线 (秒)    0        1        2        3        4        5        ...
─────────────────────────────────────────────────────────────────────▶

Input ANR:
  触摸下发 ────────┬──────────────────────────────────────[5s 超时]──▶ ANR!
                   │  (窗口应在 5s 内完成事件消费)
                   └─ finishInputEvent() 未调用

  正常路径: 触摸下发 ─► 窗口消费(200ms) ─► finishInputEvent() ─► 正常


Service ANR (前台):
  onCreate() ────────┬────────────────────────────[20s 超时]─────────▶ ANR!
                     │  (serviceDoneExecuting 未调用)
                     └─ serviceDoneExecuting() 未调用

  正常路径: onCreate() ─► 工作完成(1s) ─► serviceDoneExecuting() ─► 正常


Broadcast ANR (前台):
  onReceive() ───────┬──────────────────[10s 超时]──────────────────▶ ANR!
                     │  (onReceive 未返回)
                     └─ onReceive() 未 return

  正常路径: onReceive() ─► 轻量操作(100ms) ─► return ─► 正常
```

### 4.2 Trace 文件生成流程

```
触发 ANR
    │
    ▼
AMS.appNotResponding()
    │                                        应用进程
    │                                          ┌─────────────────────┐
    ├──► 1. EventLog: am_anr                  │                     │
    │                                          │  Signal Catcher ★   │
    ├──► 2. updateCpuStatsNow()               │  (tid=特殊线程)      │
    │    (写 CPU usage)                       │                     │
    │                                          │  while(true) {      │
    ├──► 3. Process.sendSignal(pid, SIGQUIT)──┼──► sigwait()阻塞    │
    │      │                                   │  ↓ 收到 SIGQUIT     │
    │      │                                   │  Thread.dumpStack() │
    │      │  ┌────────────────────────────┐   │  for each thread:   │
    │      └─►│ 等待 10s (ANR_TRACE_TIMEOUT)│   │    dump native     │
    │         │ 若超时,再次 SIGQUIT         │   │    dump java       │
    │         └────────────────────────────┘   │    dump locks       │
    │                                          └──────┬──────────────┘
    │                                                 │
    ├──► 4. 收集 traces.txt 内容 ◄────────────────────┘
    │
    ├──► 5. 写入 /data/anr/traces.txt
    │
    ├──► 6. dropBoxService 保存一份到 /data/system/dropbox/
    │
    └──► 7. 决定弹框 / 杀进程
```

> **面试加分点**：Signal Catcher 是 Android Runtime 中的一个独立线程，在 `runtime->StartSignalCatcher()` 中创建。它通过 `sigwait()` 系统调用等待 `SIGQUIT`，收到信号后执行 `DumpForSigQuit()`，遍历所有线程并输出堆栈。

---

## 5. 源码分析：从 InputDispatcher 到 AMS

### 5.1 InputDispatcher 的 ANR 检测（C++ 层）

```cpp
// frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp

// ANR 超时定义（硬编码）
constexpr nsecs_t DEFAULT_INPUT_DISPATCHING_TIMEOUT = 5 * 1000 * 1000 * 1000LL; // 5s

void InputDispatcher::dispatchOnceInnerLocked(nsecs_t* nextWakeupTime) {
    // ... 获取需要分发的事件

    // 关键 ANR 检测点
    nsecs_t currentTime = now();
    for (auto& connection : mAnrTracker) {  // ★ ANR 追踪表
        sp<Connection> connection = it.second.promote();
        if (connection == nullptr) continue;

        nsecs_t timeout = connection->inputState.getDispatchingTimeout();
        if (timeout < currentTime) {
            // ★ 超时！触发 ANR
            processAnrLocked(connection, timeoutReason);
        }
    }

    // 分发事件
    done = dispatchKeyLocked(currentTime, entry, ...);
}

void InputDispatcher::processAnrLocked(const sp<Connection>& connection,
        const std::string& reason) {
    // 1. 构造 ANR 描述
    std::string annotation = "Input dispatching timed out";
    annotation += " (" + reason + ")";

    // 2. 保存 ANR 状态（供 dump 使用）
    mLastAnrState.clear();
    dumpDispatchStateLocked(mLastAnrState);

    // 3. 通知 Java 层的 InputManagerService
    dispatchOnceInnerLocked(nullptr); // 先处理完剩余事件

    // 4. 通过 JNI 回调到 Java 层
    // InputManagerService.notifyANR()
}
```

**关键设计点**：
- `mAnrTracker` 是一个 `std::unordered_map`，key 是 inputChannel 的 connection token，value 是弱引用。
- 在 `startDispatchCycleLocked()` 中，事件被放入 tracker 并记录 `dispatchTime`。
- 在 `finishDispatchCycleLocked()` 中，事件完成后从 tracker 移除。
- 每次 `dispatchOnceInnerLocked()` 被调用时，遍历 tracker 检查是否有超时。

### 5.2 AMS 的 Service 超时处理（Java 层）

```java
// frameworks/base/services/core/java/com/android/server/am/ActiveServices.java

// 超时常量定义
static final int SERVICE_TIMEOUT = 20 * 1000;             // 前台 20s
static final int SERVICE_BACKGROUND_TIMEOUT = 200 * 1000; // 后台 200s

void realStartServiceLocked(ServiceRecord r, ProcessRecord app,
        boolean execInFg) throws RemoteException {
    // ...
    // ★ 关键：服务启动前，设置超时炸弹
    bumpServiceExecutingLocked(r, execInFg, "create");
    // ...
    try {
        app.thread.scheduleCreateService(r, ...);
    } finally {
        // 如果创建失败，取消超时
    }
}

private void bumpServiceExecutingLocked(ServiceRecord r, boolean fg, String why) {
    long now = SystemClock.uptimeMillis();
    if (r.executeNesting == 0) {
        r.executingStart = now;
        // ★ 根据前台/后台选择超时时长
        long timeout = fg ? SERVICE_TIMEOUT : SERVICE_BACKGROUND_TIMEOUT;
        // 发送延时消息
        mAm.mHandler.sendMessageAtTime(
            mAm.mHandler.obtainMessage(ActivityManagerService.SERVICE_TIMEOUT_MSG,
                r.app),
            r.executingStart + timeout);
    }
    r.executeNesting++;
}

void serviceDoneExecutingLocked(ServiceRecord r, int type, int startId, int res) {
    r.executeNesting--;
    if (r.executeNesting == 0) {
        // ★ 移除超时炸弹
        mAm.mHandler.removeMessages(
            ActivityManagerService.SERVICE_TIMEOUT_MSG, r.app);
        // ...
    }
}

// AMS 中处理 SERVICE_TIMEOUT_MSG
final class MainHandler extends Handler {
    @Override
    public void handleMessage(Message msg) {
        switch (msg.what) {
            case SERVICE_TIMEOUT_MSG: {
                // ★ Service 未在时限内完成！
                mServices.serviceTimeout((ProcessRecord) msg.obj);
            } break;
        }
    }
}

// ActiveServices.serviceTimeout()
void serviceTimeout(ProcessRecord proc) {
    // 1. 确认进程仍存在
    // 2. 构造 ANR annotation: "executing service <component>"
    // 3. 调用 ★ AMS.appNotResponding() ★
    mAm.mAnrHelper.appNotResponding(proc, annotation);
}
```

**面试深度追问**：
- ❓ **为什么 Service ANR 要用嵌套计数器 `executeNesting`？** → 因为 Service 的 `onCreate()` 和 `onStartCommand()` 可能依次调用，每次调用 `bumpServiceExecutingLocked()` 嵌套 +1，完成时 -1。只有所有嵌套都完成（`executeNesting == 0`），才取消超时定时器。
- ❓ **如果 Service 在主线程执行 `onStartCommand()` 时调用了 `startForeground()` 但 5s 内未调，会发生什么？** → 这是另一个 ANR 入口：前台 Service 必须在 `onStartCommand()` 返回后 5s 内调用 `startForeground()`，否则触发 `ANR: Context.startForegroundService() did not then call Service.startForeground()`。

---

## 6. 应用场景：主线程 IO 导致 ANR 的排查与修复

### 6.1 真实案例还原

**现象**：某社交 App 在弱网环境下频繁出现 Input ANR，ANR 率从 0.1% 飙升到 2.3%。

**Trace 文件关键片段**：
```
----- pid 12345 at 2026-05-08 10:30:00 -----
Cmd line: com.social.app
subject: Input dispatching timed out (Waiting to send non-key event because the
  touched window has not finished processing certain input events...)

"main" prio=5 tid=1 Blocked
  | group="main" sCount=1 ucsCount=0 flags=1 obj=0x...
  | sysTid=12345 nice=-10 cgrp=default sched=0/0 handle=0x...
  | state=S schedstat=( ... )
  at android.database.sqlite.SQLiteConnection.nativeExecute(Native method)
  at android.database.sqlite.SQLiteConnection.execute(SQLiteConnection.java:678)
  at android.database.sqlite.SQLiteSession.execute(SQLiteSession.java:621)
  at android.database.sqlite.SQLiteStatement.executeUpdateDelete(SQLiteStatement.java:70)
  at com.social.app.db.MessageDao.insertMessage(MessageDao.java:45)
  at com.social.app.receiver.MessageReceiver.onReceive(MessageReceiver.java:32)
  at android.app.ActivityThread.handleReceiver(ActivityThread.java:3456)
  ...
```

**根因分析**：
1. 主线程 `MessageReceiver.onReceive()` 收到推送消息。
2. 直接调用 `MessageDao.insertMessage()` → 主线程 SQLite 写入。
3. 弱网下消息密集到达，每次写入耗时 200~800ms。
4. 累计堵塞 InputDispatcher 的事件队列。
5. 最终触发 Input ANR（5s 超时）。

### 6.2 修复方案（从临时到根治）

**Step 1：紧急止血（热修复）**
```kotlin
// 将 SQLite 操作切到子线程
class MessageReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        // ★ 方案 A: goAsync() + 子线程
        val pendingResult = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val message = parseMessage(intent)
                MessageRepository.insert(message) // 子线程 DB 操作
            } finally {
                pendingResult.finish() // ★ 必须调用，否则 ANR
            }
        }
    }
}
```

**Step 2：性能优化（中期方案）**
```kotlin
// a. 批量写入代替逐条写入
class MessageRepository {
    private val buffer = mutableListOf<Message>()
    private val maxBufferSize = 50

    suspend fun insertBatch(message: Message) {
        buffer.add(message)
        if (buffer.size >= maxBufferSize) {
            flushBuffer()
        }
    }

    suspend fun flushBuffer() {
        if (buffer.isEmpty()) return
        database.withTransaction {
            buffer.forEach { dao.insert(it) }
        }
        buffer.clear()
    }
}

// b. 使用 WAL 模式提升并发性能
database.execSQL("PRAGMA journal_mode=WAL;")
database.execSQL("PRAGMA synchronous=NORMAL;")
```

**Step 3：架构重构（长期方案）**
```kotlin
// ★ 引入统一任务调度器，所有主线程重操作全部异步化
object MainThreadGuard {
    // 利用 StrictMode 在开发阶段检测
    fun enableStrictMode() {
        StrictMode.setThreadPolicy(
            StrictMode.ThreadPolicy.Builder()
                .detectDiskReads()
                .detectDiskWrites()
                .detectNetwork()
                .penaltyLog()
                .penaltyDeath() // 开发阶段直接 crash
                .build()
        )
    }

    // 线上使用 Looper 监控（见 Q5）实时上报耗时方法
}
```

### 6.3 排查清单（面试可套用）

遇到 ANR 问题，按以下顺序排查：

1. **[80%概率] 主线程耗时操作**
   - 检查 trace 中 main 线程堆栈顶部是否有：IO 操作、Binder 调用、数据库操作、网络请求、`Thread.sleep()`
2. **[10%概率] 锁竞争**
   - 主线程 `Blocked` 状态 → 查找持有锁的线程 → 分析持锁时间和原因
3. **[5%概率] Binder 耗尽**
   - 大量 Binder 线程处于 `Native` / `Blocked` 状态 → 系统服务压力大或死锁
4. **[3%概率] CPU 过载**
   - trace 开头 CPU usage 显示 iowait/irq 高 → 系统级问题
5. **[2%概率] 其他**
   - 系统服务死锁（system_server）、内存压力导致 GC 频繁（FinalizerWatchdogDaemon 超时）

### 6.4 线上 ANR 治理体系

```
               ┌────────────────────────────┐
               │  APM 平台 (Bugly/Sentry/Firebase) │
               └──────────────┬─────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
    ┌─────▼──────┐    ┌──────▼──────┐    ┌───────▼───────┐
    │ ANR 收集   │    │  ANR 聚合   │    │  ANR 归因     │
    │ (ExitInfo) │    │  (聚类算法)  │    │  (堆栈指纹)   │
    └─────┬──────┘    └──────┬──────┘    └───────┬───────┘
          │                   │                   │
          └───────────────────┼───────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │  智能告警          │
                    │  - ANR 率 > 阈值   │
                    │  - 新堆栈出现      │
                    │  - 单用户高频      │
                    └─────────┬─────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
        ┌─────▼──────┐ ┌─────▼──────┐ ┌──────▼──────┐
        │ 自动归因   │ │ 关联分析   │ │ 修复建议    │
        │ (AI)       │ │ (版本/机型)│ │ (自动提单)  │
        └────────────┘ └────────────┘ └─────────────┘
```

---

## 总结与面试技巧

**面试要点总结**：

1. **超时时间必须脱口而出**：Input 5s / Service 20s(前) 200s(后) / Broadcast 10s(前) 60s(后)
2. **trace 解读三步走**：定位 main 线程状态 → 追踪锁持有者 → 检查 Binder 线程状态
3. **原理问到什么深度**：至少到 `appNotResponding()` 这一层，能画出流程图更好
4. **线上方案**：Android 11+ 用 `getHistoricalProcessExitReasons()`，老版本用 FileObserver + SIGQUIT
5. **追问有亮点**：Looper Printer 替换监控、Signal Catcher 机制、WAL 模式优化、goAsync() 用法
6. **实战经验**：至少准备一个主线程 IO / 锁竞争导致 ANR 的真实排查案例

> **面试官最爱追问**：「ANR 弹窗是怎么弹出来的？」——这是在考察你对 WindowManager 和系统 UI 的了解。答案：`AMS.appNotResponding()` → `mUiHandler.sendMessage(SHOW_NOT_RESPONDING_UI_MSG)` → `AppNotRespondingDialog` ——这是一个运行在 `system_server` 进程 UI 线程上的系统级对话框，不属于应用进程。
