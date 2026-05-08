# AMS 详解 — 面试深度剖析

---

## 目录

1. [高频面试问题](#1-高频面试问题)
2. [标准答案与OOM Adj对照表](#2-标准答案与oom-adj对照表)
3. [核心原理深度剖析](#3-核心原理深度剖析)
4. [startActivity 完整 Binder 调用序列图](#4-startactivity-完整-binder-调用序列图)
5. [源码分析：ATMS.startActivity() → ActivityStarter.execute()](#5-源码分析atmsstartactivity--activitystarterexecute)
6. [应用场景：Activity 启动慢原因分析](#6-应用场景activity-启动慢原因分析)

---

## 1. 高频面试问题

### Q1：从桌面点击图标到 Activity 显示，经历了哪些完整流程？

这道题几乎是所有 Android 系统岗的"开胃菜"。面试官想考察你对 Android 启动流程的全链路理解，涉及 Launcher、AMS/ATMS、Zygote、ApplicationThread、ActivityThread 等多个核心组件。

### Q2：AMS 如何管理进程优先级？请解释 LRU 列表和 OOM Adj 机制。

这道题考察你对 Android 内存管理的理解深度，面试官想知道你是否理解系统如何在内存不足时选择"杀掉"哪个进程。

### Q3：ActivityRecord、TaskRecord、ActivityStack 三个数据结构分别是什么？它们之间是什么关系？

这道题考察你对 AMS 核心数据模型的理解，是衡量候选人是否真正读过源码的重要标尺。

### Q4：startActivity 的 Binder 调用链路是怎样的？从 Client 端到 ATMS 再到 ApplicationThread 的全过程。

这道题考察你对 Android IPC 机制的理解，以及是否清楚 Activity 跨进程启动的完整调用链。

### Q5：进程启动流程是怎样的？Zygote fork 到 ActivityThread.main 的过程发生了什么？

这道题考察你对 Android 进程模型的深度理解，面试官想知道你是否清楚新进程是如何"诞生"的。

### Q6：前台进程、可见进程、服务进程、缓存进程的 OOM Adj 值分别是多少？系统如何进行 LRU 回收？

这道题是 Q2 的延伸，面试官要的是精确的数值和你对 LRU 回收策略的理解。

---

## 2. 标准答案与OOM Adj对照表

### 2.1 桌面点击图标到 Activity 显示的完整流程（时序回答）

**阶段一：Launcher 发起启动请求（Client 端）**

当用户在桌面点击图标时，Launcher 进程（作为普通 App 进程）调用 `startActivity(intent)`。经过层层调用，最终到达 `Instrumentation.execStartActivity()`，在这里通过 Binder 向系统服务 ATMS（ActivityTaskManagerService）发起跨进程调用。

关键代码路径：
```
Launcher.startActivitySafely()
  → Activity.startActivity()
    → Activity.startActivityForResult()
      → Instrumentation.execStartActivity()
        → ActivityTaskManager.getService().startActivity()  // Binder IPC!
```

**阶段二：ATMS 处理启动请求（System Server 端）**

ATMS 收到请求后，将启动任务委托给 `ActivityStarter`：

```
ATMS.startActivity()
  → ActivityStarter.execute()
    → ActivityStarter.startActivityUnchecked()
      → ActivityStarter.startActivityInner()
        → ActivityStack.startActivityLocked()
```

在这个阶段，ATMS 完成以下关键工作：
- 解析 Intent，确定目标 Activity 信息
- 创建或复用 ActivityRecord 和 TaskRecord
- 检查权限和 IntentFilter
- 管理 Task 栈（是否需要新建 Task、是否要 bringToFront）
- 决定是否需要创建新进程

**阶段三：进程创建（如需要）**

如果目标 Activity 所属的进程尚未启动，ATMS 通过 socket 通知 Zygote fork 新进程：

```
ATMS → ZygoteProcess.start()
  → ZygoteServer (socket通信)
    → ZygoteInit.main()
      → Zygote.forkAndSpecialize()
        → ActivityThread.main()  // 新进程入口
```

ActivityThread.main() 在新进程中执行：
1. 准备主线程 Looper（`Looper.prepareMainLooper()`）
2. 创建 ActivityThread 实例
3. 调用 `thread.attach(false)` 向 AMS 注册自己
4. 进入消息循环 `Looper.loop()`

**阶段四：ApplicationThread 回调（跨进程回调）**

新进程注册成功后，ATMS 通过 ApplicationThread（一个 Binder 对象）回调新进程：

```
ATMS → ApplicationThread.bindApplication()  // Binder IPC
  → ActivityThread.handleBindApplication()
    → 创建 Application 实例
    → 调用 Application.onCreate()
```

接着 ATMS 通知启动 Activity：
```
ATMS → ApplicationThread.scheduleTransaction()
  → LaunchActivityItem.execute()
    → ActivityThread.handleLaunchActivity()
      → performLaunchActivity()
        → Instrumentation.newActivity()       // 反射创建 Activity
        → Activity.attach()                    // 关联 Context
        → Instrumentation.callActivityOnCreate()  // Activity.onCreate()
      → handleResumeActivity()
        → Activity.onResume()
```

**阶段五：View 绘制与显示**

Activity 创建完毕后，WindowManager 开始处理视图：
```
PhoneWindow.setContentView()
  → DecorView 创建
    → ViewRootImpl.setView()
      → requestLayout()
        → performTraversals()
          → measure → layout → draw
```

最终，Activity 的界面渲染完成并显示在屏幕上。整个流程涉及多次 Binder 通信（至少 5-6 次跨进程调用），从点击到首帧绘制通常耗时在 100ms~500ms（冷启动）。

---

### 2.2 OOM Adj 对照表（核心记忆表）

| 进程类型 | OOM Adj 值 | 级别常量 | 典型场景 | 被杀优先级 |
|---------|-----------|----------|---------|-----------|
| **前台进程** | **0** | `FOREGROUND_APP_ADJ` | 正在与用户交互的 Activity；与前台 Activity 绑定的 Service；正在执行 onReceive 的 BroadcastReceiver | 最低（几乎不杀） |
| **可见进程** | **100** | `VISIBLE_APP_ADJ` | Activity 可见但不在前台（如被弹窗遮挡）；与可见 Activity 绑定的 Service | 很低 |
| **服务进程** | **200** | `SERVICE_ADJ` | 通过 startService 启动的后台服务（无 UI） | 中等 |
| **服务B** | **250** | `SERVICE_B_ADJ` | 服务进程中的"高内存"服务 | 中偏高 |
| **Home进程** | **600** | `HOME_APP_ADJ` | Launcher 进程（即使不可见，也有特殊待遇） | 中等 |
| **前一进程** | **700** | `PREVIOUS_APP_ADJ` | 用户上一个使用的应用（LRU 链表的头部缓存） | 中偏高 |
| **缓存进程** | **900** | `CACHED_APP_MIN_ADJ` | 不包含任何活跃组件的进程（只在后台的 Activity） | 很容易被杀 |
| **空进程** | **906** | `CACHED_APP_MAX_ADJ` | 没有任何 Activity/Service 的纯缓存进程 | 最高（最先被杀） |

**关键补充说明：**

1. **OOM Adj 值的动态调整**：AMS 中的 `OomAdjuster` 模块会根据进程内组件的状态变化，实时更新每个进程的 oom_adj 值。例如，当 Activity 从可见变为不可见，其 adj 值会从 100 升到 900。

2. **LRU 列表结构**：AMS 维护一个按 `lastActivityTime` 排序的进程 LRU 链表。每个缓存进程都有一个 index，index 越大（越久未使用），adj 惩罚越大：
   - 第一个缓存进程：adj = 900（index=0）
   - 第二个缓存进程：adj = 903（index=1）
   - 第 N 个缓存进程：adj = 900 + 3×N

3. **ADJ 映射到内核 oom_score_adj**：Android 将逻辑上的 ADJ 值通过 `/proc/<pid>/oom_score_adj` 写入内核。内核的 LMK（Low Memory Killer）根据这个值决定在内存压力下先杀哪个进程。ADJ 越大，oom_score_adj 越大，被内核回收的可能性越高。

4. **Android 10+ 的变化**：Google 在 Android 10 引入了 LMKD（用户空间的 lmkd 守护进程），替代了内核的 LMK 驱动程序。LMKD 通过查询 AMS 获取进程的 oom_score，然后根据内存压力级别（`/sys/module/lowmemorykiller/parameters/minfree`）选择性杀进程。这使得杀进程策略更加可控。

---

## 3. 核心原理深度剖析

### 3.1 ATMS（ActivityTaskManagerService）— Task 与 Activity 栈的管理者

ATMS 是 Android 10 从 AMS 中拆分出来的服务，专门负责 Activity 和 Task 的管理。AMS 本身则专注于进程管理、Service 管理、ContentProvider 管理和 Broadcast 管理。

**ATMS 的核心职责：**
- **Task 管理**：创建、销毁、移动 Task，维护最近任务列表
- **Activity 栈管理**：压栈、出栈、栈间移动 ActivityRecord
- **分屏/多窗口**：管理多窗口下的 Task 布局和焦点
- **启动模式解析**：处理 standard、singleTop、singleTask、singleInstance 四种启动模式

**核心数据结构：**

```
ActivityTaskManagerService
  └── RootWindowContainer          // 整个窗口树的根容器
       ├── DisplayContent (displayId=0, 主屏幕)
       │    └── TaskStack (HOME_STACK)   // Launcher 专属栈
       │    └── TaskStack (FULLSCREEN_WORKSPACE)  // 普通应用栈
       │         ├── TaskRecord 1 (Task A)
       │         │    ├── ActivityRecord (A1)
       │         │    └── ActivityRecord (A2)  // 栈顶
       │         └── TaskRecord 2 (Task B)
       │              └── ActivityRecord (B1)
       └── DisplayContent (displayId=1, 副屏幕)
            └── ...
```

**ActivityRecord**：代表一个 Activity 实例的元数据，包含 Intent、进程信息、状态（INITIALIZING/RESUMED/PAUSED/STOPPED/DESTROYED）、配置信息等。

**TaskRecord**：代表一个任务栈（回退栈），包含一组有序的 ActivityRecord。用户按返回键时，从栈顶逐个弹出 Activity。

**ActivityStack**：Android 10 后重构为 TaskStack，管理一组 TaskRecord。每个 Display 可以有多个 Stack，不同 Stack 对应不同的窗口模式（全屏、分屏、画中画等）。

### 3.2 OOM Adj 机制 — 动态优先级与进程回收

Android 的进程管理机制基于"优先级 + LRU"混合策略，具体由 `OomAdjuster` 实现。

**Adj 计算的核心逻辑（`OomAdjuster.computeOomAdjLocked()`）：**

```
1. 检查是否有前台 Activity          → ADJ = 0
2. 检查是否有可见 Activity          → ADJ = 100
3. 检查是否有运行的 Service         → ADJ = 200
4. 检查是否是 Service B（高内存）   → ADJ = 250
5. 检查是否是 Home 进程             → ADJ = 600
6. 检查是否是上一个前台进程         → ADJ = 700
7. 其他缓存进程                     → ADJ = 900 + (index in LRU) × 3
```

**trimApplications() — LRU 回收策略：**

`AMS.trimApplications()` 是进程回收的入口方法，由 LMKD 或定时任务触发。其核心逻辑：

```java
// 伪代码，展示核心逻辑
void trimApplications() {
    // 1. 遍历所有进程，计算 oom_adj
    for (ProcessRecord app : mProcessList) {
        computeOomAdjLocked(app);
    }

    // 2. 按照 oom_adj 从高到低排序
    // 3. 标记可回收进程（adj >= CACHED_APP_MIN_ADJ）
    // 4. 根据内存压力级别，从 adj 最高的开始杀
    
    // 5. 如果没有足够可杀进程，进入紧急回收模式
    //    释放非必要的 Activity 资源（destroyed Activity 的保存状态）
}
```

**LRU 列表维护：**

AMS 维护两个 LRU 列表：
- `mLruProcesses`：所有非 Service 进程，按最近使用时间排序
- `mProcessList`：所有进程的完整列表

每次 Activity 切换时，对应进程被移到 LRU 列表头部；当进程长时间不被使用时，其 adj 值随着 index 增长而递增，最终被 LMKD 回收。

### 3.3 ApplicationThread — AMS 与 App 通信的 Binder 桥梁

ApplicationThread 是一个内部类，位于 `ActivityThread` 中，继承自 `IApplicationThread.Stub`，是一个 Binder 服务端。

**通信模型：**

```
SystemServer 进程                            App 进程
┌─────────────────┐                    ┌──────────────────────┐
│  ATMS/AMS        │                    │  ActivityThread      │
│  (Binder Client) │                    │  (Binder Server)     │
│       │          │                    │       │              │
│       ▼          │    Binder IPC      │       ▼              │
│  ─────────────── │◄──────────────────►│  ApplicationThread   │
│       ▲          │                    │       │              │
│       │          │                    │       ▼              │
│  ApplicationThread│                   │  H (Handler)         │
│  .Proxy          │                    │  processMessage()    │
└─────────────────┘                    └──────────────────────┘
```

**关键回调方法：**

| 方法 | 触发场景 | App 端处理 |
|------|---------|-----------|
| `scheduleTransaction()` | 启动/恢复/暂停/停止 Activity | 通过 ClientTransaction 事务链处理 |
| `bindApplication()` | 进程启动后绑定 Application | 创建 Application 实例，调用 onCreate |
| `scheduleRegisteredReceiver()` | Broadcast 分发 | 在主线程回调 onReceive |
| `dumpActivity()` | 调试/ANR 时 dump Activity 状态 | 收集并返回当前 Activity 栈信息 |

ApplicationThread 的所有方法都是在系统服务进程的 Binder 线程池中被调用的，然后它通过 Handler（`H`）将执行切换到 App 的主线程。这就是为什么 AMS 可以"远程操控" App 中的 Activity 生命周期。

---

## 4. startActivity 完整 Binder 调用序列图

```
  Launcher进程              SystemServer进程              目标App进程             Zygote进程
  (Client)                 (ATMS/AMS/PMS)                (Application)           (Fork)
     │                           │                            │                     │
     │  1.startActivity(intent)  │                            │                     │
     │──────────────────────────►│                            │                     │
     │                           │                            │                     │
     │  2. ATMS.startActivity()  │                            │                     │
     │     → ActivityStarter     │                            │                     │
     │       .execute()          │                            │                     │
     │                           │                            │                     │
     │  3. PMS 解析 Intent       │                            │                     │
     │     resolveActivity()     │                            │                     │
     │     (查找匹配 Activity)    │                            │                     │
     │                           │                            │                     │
     │  4. 检查权限              │                            │                     │
     │     checkPermission()     │                            │                     │
     │                           │                            │                     │
     │  5. 检查目标进程是否存活    │                            │                     │
     │     ProcessRecord存在?    │                            │                     │
     │                           │                            │                     │
     │              [进程不存在 ──────────────────────────────────────────────►│
     │                           │                            │              6.Zygote fork │
     │                           │                            │              新进程        │
     │                           │                            │◄───────────────│
     │                           │                            │                     │
     │                           │                            │  7.ActivityThread │
     │                           │                            │    .main()        │
     │                           │                            │    Looper.prepare │
     │                           │                            │    thread.attach()│
     │                           │◄───────────────────────────│                   │
     │                           │  Binder: attachApplication │                   │
     │                           │                            │                   │
     │                           │  8. ATMS 确认新进程已注册   │                   │
     │                           │                            │                   │
     │                           │───────────────────────────►│                   │
     │                           │  9.ApplicationThread       │                   │
     │                           │    bindApplication()       │                   │
     │                           │    (创建Application)        │                   │
     │                           │                            │                   │
     │                           │───────────────────────────►│                   │
     │                           │ 10.ApplicationThread       │                   │
     │                           │   scheduleTransaction()    │                   │
     │                           │   (LaunchActivityItem)     │                   │
     │                           │                            │                   │
     │                           │                            │ 11.handleLaunch   │
     │                           │                            │   Activity()      │
     │                           │                            │   onCreate()      │
     │                           │                            │   onStart()       │
     │                           │                            │   onResume()      │
     │                           │                            │                   │
     │                           │  12.ApplicationThread      │                   │
     │                           │◄───────────────────────────│                   │
     │                           │  reportResumed()           │                   │
     │                           │                            │                   │
     │                           │  13.通知Launcher暂停        │                   │
     │◄──────────────────────────│  (当前台Activity不再可见)    │                   │
     │                           │                            │                   │
     ▼                           ▼                            ▼                   ▼
  桌面隐藏                  ATMS更新栈状态                  Activity显示           空闲
```

**关键 Binder 调用节点统计：**

| 步骤 | 调用方向 | 说明 |
|------|---------|------|
| 1→2 | Launcher → ATMS | `IActivityTaskManager.startActivity()` |
| 6 | ATMS → Zygote | socket 通信（非 Binder） |
| 7 | App → ATMS | `IActivityManager.attachApplication()` |
| 9 | ATMS → App | `IApplicationThread.bindApplication()` |
| 10 | ATMS → App | `IApplicationThread.scheduleTransaction()` |
| 12 | App → ATMS | `IActivityTaskManager.reportResumed()` |

整个流程至少发生 **5 次跨进程调用**（4 次 Binder + 1 次 socket），这是造成 Activity 冷启动延迟的重要原因之一。

---

## 5. 源码分析：ATMS.startActivity() → ActivityStarter.execute()

### 5.1 入口：ATMS.startActivity()

Android 12/13 源码路径：`frameworks/base/services/core/java/com/android/server/wm/ActivityTaskManagerService.java`

```java
// ATMS.java (简化版本，反映核心逻辑)
@Override
public final int startActivity(IApplicationThread caller, String callingPackage,
        Intent intent, String resolvedType, IBinder resultTo, String resultWho,
        int requestCode, int startFlags, ProfilerInfo profilerInfo,
        Bundle bOptions) {
    
    // 1. 调用方身份检查 —— 拒绝非系统进程的某些特殊权限
    assertPackageMatchesCallingUid(callingPackage);
    
    // 2. 如果不是从 Activity 上下文启动的（如 Service 中 startActivity），
    //    需要强制添加 FLAG_ACTIVITY_NEW_TASK
    enforceNotIsolatedCaller("startActivity");
    
    // 3. 获取调用者的进程 PID/UID
    final int realCallingPid = Binder.getCallingPid();
    final int realCallingUid = Binder.getCallingUid();
    
    // 4. 委托给 ActivityStarter 执行启动流程
    //    ActivityStarter 是真正"干活"的类
    return getActivityStartController().obtainStarter(intent, "startActivityAsUser")
            .setCaller(caller)           // 设置调用方的 ApplicationThread
            .setCallingPackage(callingPackage)
            .setResolvedType(resolvedType)
            .setResultTo(resultTo)       // 启动后结果返回给哪个 Activity
            .setRequestCode(requestCode)
            .setStartFlags(startFlags)
            .setProfilerInfo(profilerInfo)
            .setActivityOptions(bOptions)
            .execute();                  // 关键：执行启动
}
```

### 5.2 核心：ActivityStarter.execute()

源码路径：`frameworks/base/services/core/java/com/android/server/wm/ActivityStarter.java`

```java
// ActivityStarter.java (简化版本)
int execute() {
    try {
        // 1. 解析 Intent —— 通过 PMS 找到目标 ActivityInfo
        if (mRequest.activityInfo == null) {
            mRequest.resolveActivity(mSupervisor);
        }
    } catch (RemoteException e) {
        // Intent 解析失败，如目标 Activity 未在 AndroidManifest 注册
        return START_CLASS_NOT_FOUND;
    }

    // 2. 再次检查权限 —— 确保调用者有权限启动目标 Activity
    boolean abort = !mSupervisor.checkStartAnyActivityPermission(
            mRequest.intent, mRequest.activityInfo, ...);
    if (abort) {
        return START_PERMISSION_DENIED;
    }

    // 3. 执行启动流程 —— 这是核心中的核心
    int res;
    synchronized (mService.mGlobalLock) {
        // 检查是否有运行中的进程需要与启动同步
        final boolean globalConfigWillChange = mRequest.activityInfo != null
                && mService.getGlobalConfiguration().isConfigActive();
        
        // 获取目标 Task（如果指定了 taskAffinity）
        final Task task = mRequest.activityInfo != null
                ? mTargetStack.getReusableTask(mRequest.activityInfo) : null;
        
        // 进入主流程
        res = executeRequest(mRequest);
        
        // 如果配置需要变化，等待变化完成后再恢复栈顶
        if (globalConfigWillChange) {
            mService.mAmInternal.enforceCallingPermission(
                    android.Manifest.permission.CHANGE_CONFIGURATION,
                    "updateConfiguration()");
            mTargetStack.ensureActivityConfig(...);
        }
    }
    
    return res;
}

private int executeRequest(Request request) {
    // ... 省略大量前置检查 ...
    
    // 4. 核心：startActivityUnchecked —— 处理启动模式和 Task 逻辑
    //    这是 ActivityStarter 最复杂的方法（2000+ 行）
    mLastStartActivityResult = startActivityUnchecked(
            mRequest, mStartActivity, mSourceRecord, ...);
    
    // 5. 如果 Activity 成功加入栈，执行 resume
    if (mLastStartActivityResult == START_SUCCESS) {
        // 获取当前需要恢复的栈顶
        mTargetStack.startActivityLocked(mStartActivity, 
                mDoResume, ...);
    }
    
    return mLastStartActivityResult;
}
```

### 5.3 启动模式处理：startActivityUnchecked()

```java
// startActivityUnchecked 的核心决策逻辑（伪代码）
private int startActivityUnchecked(...) {
    // 1. 获取启动标志
    int launchMode = mRequest.activityInfo.launchMode;
    int launchFlags = mRequest.intent.getFlags();
    
    // 2. singleInstance 处理
    if (launchMode == LAUNCH_SINGLE_INSTANCE) {
        // 创建新的 Task，该 Task 只能容纳这一个 Activity
        mTargetStack = new TaskStack(..., WINDOWING_MODE_FULLSCREEN);
    }
    
    // 3. singleTask / FLAG_ACTIVITY_NEW_TASK 处理
    if (launchMode == LAUNCH_SINGLE_TASK || (launchFlags & FLAG_ACTIVITY_NEW_TASK) != 0) {
        // 查找是否存在相同 taskAffinity 的 Task
        Task existingTask = findTaskByAffinity(mRequest.activityInfo.taskAffinity);
        if (existingTask != null) {
            // 复用已有 Task，如果栈中已有同类型 Activity 则 clearTop
            existingTask.performClearTop(mRequest.activityInfo);
            // 将已有 Activity 移到栈顶
            existingTask.moveToFront();
            return START_DELIVERED_TO_TOP;
        }
    }
    
    // 4. singleTop 处理
    if (launchMode == LAUNCH_SINGLE_TOP || (launchFlags & FLAG_ACTIVITY_SINGLE_TOP) != 0) {
        // 如果目标 Activity 已在栈顶，复用，调用 onNewIntent
        ActivityRecord top = mTargetStack.getTopActivity();
        if (top != null && top.realActivity.equals(mRequest.activityInfo.name)) {
            top.deliverNewIntent(mRequest.intent);
            return START_DELIVERED_TO_TOP;
        }
    }
    
    // 5. 默认 standard 模式：直接创建新的 ActivityRecord 压入目标栈
    mTargetStack.addActivity(mStartActivity, ...);
    return START_SUCCESS;
}
```

### 5.4 进程存在性检查与创建决策

在 `ActivityStack.startActivityLocked()` 中，AMS 检查目标 Activity 所属进程是否存活：

```java
void startActivityLocked(ActivityRecord r, boolean doResume, ...) {
    // 查找目标进程
    ProcessRecord app = mService.getProcessRecordLocked(
            r.processName, r.info.applicationInfo.uid);
    
    if (app != null && app.thread != null) {
        // 进程已存在，直接通过 ApplicationThread 启动 Activity
        realStartActivityLocked(r, app, ...);
    } else {
        // 进程不存在，委托 AMS 启动新进程
        mService.startProcessAsync(r.processName, ...);
    }
    
    if (doResume) {
        mStackSupervisor.resumeFocusedStackTopActivityLocked();
    }
}
```

---

## 6. 应用场景：Activity 启动慢原因分析

当用户反馈"打开 App 很慢"时，我们需要从以下几方面系统排查：

### 6.1 冷启动 vs 热启动的时差分析

**冷启动（Cold Start）**：进程不存在，需要 Zygote fork 新进程。

主要耗时来源：
- **Zygote fork 开销**：fork 操作本身约 5~20ms，但 fork 后需要初始化 Runtime（加载 DEX、初始化 ClassLoader、加载 so 库），这一过程可能耗时 100~500ms
- **Application.onCreate()**：如果 Application 中做了大量初始化（如初始化第三方 SDK、加载本地数据、创建线程池），动辄增加 200~1000ms
- **首个 Activity.onCreate() + 首帧渲染**：setContentView 的 XML 解析和 View 构建、首帧 measure/layout/draw

**温启动（Warm Start）**：进程存在但 Activity 被销毁。

主要耗时：仅 Activity 生命周期回调 + 视图构建，通常在 50~200ms。

**热启动（Hot Start）**：Activity 在缓存栈中（仅 onStop 状态）。

主要耗时：onRestart → onStart → onResume，通常在 20~50ms，几乎可忽略。

### 6.2 排查维度与工具

| 维度 | 检查项 | 工具/命令 | 典型问题值 |
|------|-------|----------|-----------|
| System Server 侧 | ATMS 处理耗时 | `dumpsys activity activities` | > 50ms 需关注 |
| 进程创建 | Zygote fork + Runtime 初始化 | Systrace "fork" 事件；logcat 搜索"Start proc" | > 200ms 有问题 |
| Application 初始化 | onCreate() 中的耗时操作 | Trace.beginSection() 打点 + Systrace | > 500ms 严重影响 |
| DEX 加载 | 首次启动的 DEX 编译 | `adb shell cmd package compile` | 主 DEX 过大导致 |
| 主线程阻塞 | onCreate/onStart/onResume 中的 IO/网络 | Systrace 火焰图；BlockCanary | 任何 > 16ms 的操作 |
| 跨进程调用 | Binder 调用的序列化/反序列化 | Binder 跟踪（Systrace 的 binder_driver 标签） | 单次 Binder > 5ms |
| Layout 复杂度 | XML inflate 耗时、过度嵌套 | LayoutInspector；Systrace "inflate" | 层级 > 15 层需优化 |
| View 绘制 | measure/layout/draw 耗时 | GPU 呈现模式分析（开发者选项）；Systrace "draw" | 首帧 > 50ms 需优化 |

### 6.3 经典案例：Application.onCreate() 过度初始化

**现象**：冷启动黑屏约 2 秒后才出现第一个 Activity。

**排查命令**：
```bash
# 1. 抓取 Systrace
python systrace.py -o trace.html -t 5 sched freq idle am wm gfx view binder_driver

# 2. 查看进程启动时间
adb logcat | grep "Start proc"

# 3. dumpsys 查看 Activity 启动记录
adb shell dumpsys activity activities | grep -A 10 "Displayed"
```

**Systrace 分析发现**：
```
[主线程]
0ms  ── Application.onCreate() ──────────────── 2100ms ──
     ├── 初始化地图 SDK: 400ms
     ├── 初始化推送 SDK: 300ms
     ├── 加载本地数据库: 500ms
     └── 初始化各类管理器: 900ms
```

**优化方案**：
1. **延迟初始化**：将非关键 SDK 初始化延迟到 IdleHandler 或首帧显示之后
2. **异步初始化**：使用线程池并行初始化，但注意线程安全的 SDK（如微信 SDK 需在主线程）
3. **懒加载**：只在真正使用时才初始化（如地图 SDK 在进入地图页时才初始化）
4. **预加载优化**：使用启动器（如 Alpha）并行执行任务，利用拓扑排序管理依赖

```java
// 优化后的 Application.onCreate()
@Override
public void onCreate() {
    super.onCreate();
    // 1. 主线程必要初始化 —— 尽量轻量
    initCrashHandler(); // 崩溃捕获（必须最优先）
    
    // 2. 异步化非关键初始化
    ExecutorService executor = Executors.newFixedThreadPool(3);
    executor.execute(() -> initPushSDK());
    executor.execute(() -> preloadDatabase());
    
    // 3. 延迟到 IdleHandler（主线程空闲时执行）
    Looper.myQueue().addIdleHandler(() -> {
        initMapSDK(); // 地图只在需要时初始化
        return false; // 只执行一次
    });
}
```

### 6.4 另一个高频案例：主线程 Binder 调用阻塞

**现象**：startActivity 调用后，在执行 `realStartActivityLocked()` 中，ATMS 需要通过 ApplicationThread 回调 App 进程的 `scheduleTransaction()`。如果此时 App 进程的主线程正在执行耗时操作（如文件 IO），Binder 线程虽然能收到回调并发送消息到主线程 Handler，但主线程无法及时处理 → 表现为"卡住"。

**排查**：Systrace 中 Alooper 的"binder transaction"段过长（> 10ms），对应的 App 主线程处于"running"状态但未处理消息。

**解决**：确保主线程只做 UI 相关工作，任何耗时操作移到后台线程。

---

## 总结

AMS/ATMS 是 Android Framework 中最复杂的子系统之一。面试中要想脱颖而出，需要掌握以下几个核心要点：

1. **全链路思维**：从 Launcher 点击到 Activity 显示，能清晰讲述每一步发生了什么，跨越了哪些进程边界
2. **数据结构理解**：ActivityRecord → TaskRecord → TaskStack → RootWindowContainer 的层级关系
3. **OOM Adj 机制**：精确记忆各进程类型的 ADJ 值和 LRU 回收策略
4. **Binder 通信链路**：理解 ApplicationThread 作为 AMS 与 App 之间桥梁的作用
5. **源码阅读能力**：能说出 ATMS.startActivity() → ActivityStarter.execute() → startActivityUnchecked() 的核心逻辑
6. **实战排查能力**：面对 Activity 启动慢问题，有系统性的排查和分析方法

掌握以上六点，足以应对绝大多数 Android 系统岗位的 AMS 相关面试。

---

> **参考源码路径（Android 12/13 AOSP）：**
> - `frameworks/base/services/core/java/com/android/server/wm/ActivityTaskManagerService.java`
> - `frameworks/base/services/core/java/com/android/server/wm/ActivityStarter.java`
> - `frameworks/base/services/core/java/com/android/server/wm/RootWindowContainer.java`
> - `frameworks/base/services/core/java/com/android/server/am/OomAdjuster.java`
> - `frameworks/base/core/java/android/app/ActivityThread.java`
