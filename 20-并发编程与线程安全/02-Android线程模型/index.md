# Android 线程模型 —— 面试深度解析

---

## 一、面试高频考点（5+ 经典问题）

### Q1：Android 主线程 Looper 的启动过程及"死循环"原理？

**启动过程：**
Android 应用进程启动时，`ActivityThread.main()` 作为 Java 入口被调用。在 `main()` 中：

```java
public static void main(String[] args) {
    Looper.prepareMainLooper();  // ① 初始化主线程 Looper
    ActivityThread thread = new ActivityThread();
    thread.attach(false);
    Looper.loop();               // ② 开启消息循环
}
```

`Looper.prepareMainLooper()` 内部调用 `prepare(false)` 创建主线程唯一的 Looper 实例并存入 `sThreadLocal`。`Looper.loop()` 则取出当前线程的 Looper，以 `for(;;)` 死循环方式从 `MessageQueue` 中不断取消息（`queue.next()`），分发给 `msg.target.dispatchMessage(msg)`。

**"死循环"为何不导致 ANR？**

ANR 的本质是主线程 **在 5 秒内没有响应输入事件** 或 **BroadcastReceiver 10 秒内未完成**。`Looper.loop()` 的 `queue.next()` 在没有消息时会调用 `nativePollOnce()` 进入 **Linux epoll 等待**，线程挂起不消耗 CPU。当新消息入队时通过 `nativeWake()` 写入 eventfd 唤醒。因此：

- 有消息 → 立即处理 → 保持响应
- 无消息 → epoll 挂起 → 不占 CPU → 不触发 ANR
- ANR 仅当某条消息处理耗时 > 5 秒时发生

**补充：** 为什么不用 `wait()/notify()`？因为 `epoll` 可以同时监听 Input 事件（来自 InputDispatcher 的 socket fd）和消息队列的 eventfd，实现 Native 层事件与 Java 层消息的统一唤醒。

---

### Q2：HandlerThread 的实现机制与源码解读？

`HandlerThread` 是 Android 对"自带 Looper 的后台线程"的轻量封装：

```java
public class HandlerThread extends Thread {
    int mPriority;           // 线程优先级
    Looper mLooper;
    Handler mHandler;

    @Override
    public void run() {
        mTid = Process.myTid();
        Looper.prepare();               // ① 创建 Looper + MessageQueue
        synchronized (this) {
            mLooper = Looper.myLooper();
            notifyAll();                // ② 通知等待者 Looper 就绪
        }
        Process.setThreadPriority(mPriority);
        onLooperPrepared();
        Looper.loop();                  // ③ 进入消息循环
    }

    public Looper getLooper() {
        if (!isAlive()) return null;
        synchronized (this) {
            while (isAlive() && mLooper == null) {
                wait();                 // 阻塞直到 run() 中 notifyAll()
            }
        }
        return mLooper;
    }

    public boolean quit() {
        Looper looper = getLooper();
        if (looper != null) {
            looper.quit();              // 退出循环
            return true;
        }
        return false;
    }
}
```

**面试要点：**

- `run()` 中的 `synchronized + notifyAll()` 与 `getLooper()` 中的 `wait()` 构成 **生产者-消费者同步**，保证外部线程获取 Looper 时它已初始化完毕。
- `quit()` 调用 `Looper.quit()` → `MessageQueue.quit()` → 移除所有待处理消息 → `next()` 返回 null → `loop()` 退出。
- 必须调用 `quit()` 或 `quitSafely()` 释放线程，否则 HandlerThread 会因 `Looper.loop()` 死循环永不终止。

---

### Q3：IntentService 的线程模型与废弃原因？

**线程模型：**

`IntentService` 继承自 `Service`，内部使用 `HandlerThread` 实现串行任务执行：

```java
// IntentService 核心逻辑（简化）
public abstract class IntentService extends Service {
    private volatile Looper mServiceLooper;
    private volatile ServiceHandler mServiceHandler;

    @Override
    public void onCreate() {
        HandlerThread thread = new HandlerThread("IntentService[" + mName + "]");
        thread.start();
        mServiceLooper = thread.getLooper();
        mServiceHandler = new ServiceHandler(mServiceLooper);
    }

    @Override
    public void onStart(Intent intent, int startId) {
        Message msg = mServiceHandler.obtainMessage();
        msg.arg1 = startId;
        msg.obj = intent;
        mServiceHandler.sendMessage(msg);
    }

    private final class ServiceHandler extends Handler {
        @Override
        public void handleMessage(Message msg) {
            onHandleIntent((Intent) msg.obj);  // 子类实现
            stopSelf(msg.arg1);                 // 自动停止
        }
    }
}
```

**废弃原因（API 30 标记为 deprecated）：**

1. **无法取消任务：** 一旦 `onHandleIntent` 开始执行，无法从外部中止。
2. **无返回值：** 无法获取任务执行结果，必须借助 Broadcast 等间接方式。
3. **强制串行执行：** 所有 Intent 排队处理，高并发场景效率低。
4. **生命周期约束：** 必须绑定 Service，Android 8.0+ 后台服务限制使其在 App 后台时不稳定。
5. **无错误处理机制：** `onHandleIntent` 中异常未被捕获，进程可能崩溃。

**替代方案：** Google 推荐使用 `WorkManager` + `CoroutineWorker` 或直接使用 `JobIntentService`。

---

### Q4：AsyncTask 的缺点（生命周期 / 内存泄漏 / 串行执行）？

AsyncTask 在 API 30 正式废弃，核心问题如下：

**1. 内存泄漏：**
AsyncTask 通常作为 Activity 的内部类，持有外部 Activity 引用。异步任务执行期间若 Activity 被销毁（例如旋转屏幕），GC 无法回收 Activity，造成泄漏。即使使用 `WeakReference`，任务继续执行仍浪费资源。

**2. 生命周期不可感知：**
AsyncTask 不遵循 Activity/Fragment 生命周期。`onPostExecute()` 执行时 Activity 可能已 `onDestroy()`，UI 操作直接崩溃（如 `IllegalStateException: Can not perform this action after onSaveInstanceState`）。

**3. 串行执行（API 11+）：**
默认 `execute()` 使用 `SerialExecutor`，所有 AsyncTask 共用一个线程池的单一工作线程，前一个任务完成才执行下一个。大量任务会严重阻塞。必须使用 `executeOnExecutor(THREAD_POOL_EXECUTOR)` 才能并行。

**4. 取消机制的脆弱性：**
`cancel(true)` 仅设置标志位，通过 `Thread.interrupt()` 尝试中断。但如果 `doInBackground` 中没有检查 `isCancelled()` 或 `Thread.interrupted()`，取消无效。

**5. 配置变更问题：**
屏幕旋转时 Activity 重建，AsyncTask 持有的旧 Activity 引用失效，但任务继续执行并回调解散上下文。

**6. 无类型安全：**
泛型参数 `Params, Progress, Result` 在运行时擦除，无编译期保障。

---

### Q5：线程优先级 THREAD_PRIORITY 对调度的影响？

Android 使用 Linux CFS 调度器，线程优先级通过 `Process.setThreadPriority()` 设置，最终映射到 `nice` 值：

| 常量 | nice 值 | 典型用途 |
|------|---------|---------|
| `THREAD_PRIORITY_LOWEST` | 19 | 最低优先级 |
| `THREAD_PRIORITY_BACKGROUND` | 10 | 后台不可见任务 |
| `THREAD_PRIORITY_DEFAULT` | 0 | 默认应用线程 |
| `THREAD_PRIORITY_DISPLAY` | -4 | 显示相关（UI 渲染） |
| `THREAD_PRIORITY_URGENT_DISPLAY` | -8 | 音频线程 |
| `THREAD_PRIORITY_URGENT_AUDIO` | -19 | 实时音频 |

**影响机制：**

- **CPU 时间片分配：** nice 值越低（优先级越高），CFS 分配的 **虚拟运行时间（vruntime）** 增长越慢，实体调度实体被更频繁调度。
- **UI 线程优先级：** 主线程默认 `THREAD_PRIORITY_FOREGROUND`（约 -2），配合 cgroup 的 `top-app` group 获得最高调度份额。
- **后台线程限制：** Android 8.0+ 后台应用线程被移到 `background` cgroup，CPU 配额被严格限制（约 5%），即使设置高优先级也无效。
- **HandlerThread 默认：** 构造时可传入优先级，`run()` 中调用 `Process.setThreadPriority(mPriority)`。

**实战经验：**
后台下载任务应设置为 `THREAD_PRIORITY_BACKGROUND` 避免与 UI 争抢 CPU；音频播放用 `URGENT_AUDIO` 保证低延迟；切忌在主线程设置低优先级。

---

## 二、源码机制深度解析

### ActivityThread.main() 如何启动 Looper？

```
Android 进程启动链：
Zygote fork → RuntimeInit → ActivityThread.main()
     ↓
Looper.prepareMainLooper()
     ↓
new Looper(quitAllowed=false)  // 主线程 Looper 不可退出
     ↓
new MessageQueue(quitAllowed=false)
     ↓
nativeInit() → NativeMessageQueue → eventfd + epoll_create
     ↓
sThreadLocal.set(new Looper(...))
     ↓
thread.attach(false) → IActivityManager.attachApplication()
     ↓
Looper.loop() → for(;;) { queue.next() → dispatchMessage() }
```

**关键源码片段：**

```java
// Looper.java
public static void prepareMainLooper() {
    prepare(false);  // quitAllowed = false
    synchronized (Looper.class) {
        if (sMainLooper != null) {
            throw new IllegalStateException("The main Looper has already been prepared.");
        }
        sMainLooper = myLooper();
    }
}

public static void loop() {
    final Looper me = myLooper();
    final MessageQueue queue = me.mQueue;
    for (;;) {
        Message msg = queue.next(); // might block
        if (msg == null) return;    // Looper quit → exit
        msg.target.dispatchMessage(msg);
        msg.recycleUnchecked();
    }
}
```

### 主线程消息队列如何保持响应性？

**MessageQueue.next() 的阻塞与唤醒：**

```java
// MessageQueue.java（简化）
Message next() {
    for (;;) {
        nativePollOnce(ptr, nextPollTimeoutMillis);  // ① epoll_wait
        synchronized (this) {
            final long now = SystemClock.uptimeMillis();
            Message prevMsg = null;
            Message msg = mMessages;
            // ② 同步屏障检查
            if (msg != null && msg.target == null) {
                do {
                    prevMsg = msg;
                    msg = msg.next;
                } while (msg != null && !msg.isAsynchronous());
            }
            if (msg != null) {
                if (now < msg.when) {
                    nextPollTimeoutMillis = (int) Math.min(msg.when - now, Integer.MAX_VALUE);
                } else {
                    // ③ 取出消息
                    mBlocked = false;
                    if (prevMsg != null) prevMsg.next = msg.next;
                    else mMessages = msg.next;
                    msg.next = null;
                    return msg;
                }
            } else {
                nextPollTimeoutMillis = -1;
            }
        }
    }
}

boolean enqueueMessage(Message msg, long when) {
    // ... 排序插入消息链表
    if (needWake) {
        nativeWake(mPtr);  // ④ 向 eventfd 写入以唤醒 epoll_wait
    }
}
```

**同步屏障机制：** 当消息 `target == null` 时，它是一条"同步屏障"，随后的同步消息被跳过，只有 `isAsynchronous()` 为 true 的消息才能通过。View 的绘制请求（`ViewRootImpl.scheduleTraversals()`）即通过此机制获得优先执行权，保证 UI 流畅。

---

## 三、线程优先级与调度细节

### Linux CFS 与 Android 线程优先级映射

```cpp
// libcore/luni/src/main/native/java_lang_Process.c
static const int priorityMap[] = {
    [THREAD_PRIORITY_LOWEST]         = 19,
    [THREAD_PRIORITY_BACKGROUND]     = 10,
    [THREAD_PRIORITY_NORMAL]         = 0,
    [THREAD_PRIORITY_DEFAULT]        = 0,
    [THREAD_PRIORITY_MORE_FAVORABLE] = -1,
    [THREAD_PRIORITY_FOREGROUND]     = -2,
    [THREAD_PRIORITY_DISPLAY]        = -4,
    [THREAD_PRIORITY_URGENT_DISPLAY] = -8,
    [THREAD_PRIORITY_AUDIO]          = -16,
    [THREAD_PRIORITY_URGENT_AUDIO]   = -19,
};
```

底层调用 `setpriority(PRIO_PROCESS, tid, newPriority)` 修改 nice 值，CFS 调度器按 `vruntime` 排序选择下一个执行线程。nice 值每降低 1，CPU 权重约提升 10%。

### cgroup 层面的限制

Android 使用 cgroup v2 的 `cpu` 和 `cpuset` 控制器：

- `top-app`：前台应用，无 CPU 限制
- `foreground`：可见但非焦点应用
- `background`：后台应用，CPU 限制到约 5%

即使线程设置了高优先级，若进程在 `background` cgroup 中，整体 CPU 时间仍受限。这就是为什么后台 Service 可能执行缓慢的原因。

---

## 四、Android 线程模型全景图

```
┌──────────────────────────────────────────────────────────────────┐
│                     Android 线程模型全景                          │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌───────────┐     ┌───────────────┐     ┌────────────────────┐ │
│  │ Zygote   │────▶│ SystemServer  │     │   App Process 1    │ │
│  │ 进程      │     │  (系统服务)    │     │                    │ │
│  └───────────┘     └───────────────┘     │  ┌──────────────┐  │ │
│         │                                │  │  Main Thread │  │ │
│         ▼                                │  │  (UI 线程)   │  │ │
│  ┌───────────┐                           │  │              │  │ │
│  │ fork()+  │                           │  │ Looper       │  │ │
│  │ exec     │                           │  │ MessageQueue │  │ │
│  └───────────┘                           │  │ Handler      │  │ │
│         │                                │  └──────┬───────┘  │ │
│         ▼                                │         │          │ │
│  ┌───────────────────┐                   │  ┌──────▼───────┐  │ │
│  │ ActivityThread    │                   │  │ Binder 线程池 │  │ │
│  │ .main()           │                   │  │ (IPC 线程)   │  │ │
│  │   │               │                   │  │ 默认16条     │  │ │
│  │   ├── prepareMainLooper()            │  └──────────────┘  │ │
│  │   ├── thread.attach()                │                    │ │
│  │   └── Looper.loop()                  │  ┌──────────────┐  │ │
│  └───────────────────┘                   │  │ HandlerThread│  │ │
│                                          │  │ (后台串行)   │  │ │
│  ┌───────────────────┐                   │  │              │  │ │
│  │ System Server     │                   │  │ IntentService│  │ │
│  │ 主线程 Looper     │                   │  │ 基于此实现   │  │ │
│  │ ActivityManager   │                   │  └──────────────┘  │ │
│  │ WindowManager     │                   │                    │ │
│  │ PackageManager    │                   │  ┌──────────────┐  │ │
│  │ ...               │                   │  │ ThreadPool  │  │ │
│  └───────────────────┘                   │  │ Executor    │  │ │
│                                          │  │ (并行任务)   │  │ │
│  ┌───────────────────┐                   │  └──────────────┘  │ │
│  │ Runtime Threads  │                   │                    │ │
│  │ ─────────────── │                   │  ┌──────────────┐  │ │
│  │ GC 线程          │                   │  │ Kotlin 协程  │  │ │
│  │ Finalizer 线程   │                   │  │ (结构化并发) │  │ │
│  │ ReferenceQueue   │                   │  │ Dispatchers  │  │ │
│  │ 守护线程         │                   │  │ .Main/IO/    │  │ │
│  │ JIT 编译线程     │                   │  │  Default     │  │ │
│  │ Signal Catcher   │                   │  └──────────────┘  │ │
│  └───────────────────┘                   └────────────────────┘ │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ 消息驱动机制：                                              │  │
│  │ ┌────────┐   ┌───────────┐   ┌──────────────┐   ┌──────┐ │  │
│  │ │Handler │──▶│MessageQueue│──▶│ nativePollOnce│──▶│epoll │ │  │
│  │ │.send() │   │.enqueue() │   │ (阻塞等待)     │   │_wait │ │  │
│  │ └────────┘   └───────────┘   └──────┬───────┘   └──┬───┘ │  │
│  │                                     │              │      │  │
│  │                                     ▼              │      │  │
│  │                              ┌────────────┐       │      │  │
│  │                              │ 消息就绪    │◀──────┘      │  │
│  │                              │ dispatch   │              │  │
│  │                              └────────────┘              │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**核心设计哲学：**

1. **单线程事件驱动：** Android UI 是单线程模型，通过消息队列 + epoll 实现高效的异步事件处理。
2. **Looper-Handler-MessageQueue 三位一体：** 每个线程可选配 Looper，线程间通过 Handler 通信，底层的 MessageQueue 管理消息的入队、排序、阻塞等待和唤醒。
3. **Binder 线程池：** 每个进程启动时创建 Binder 线程池（默认 16 条），处理来自其他进程的 IPC 调用，避免主线程被 IPC 阻塞。
4. **结构化并发趋势：** 从 AsyncTask → HandlerThread → RxJava → Kotlin Coroutines，Android 线程模型向结构化并发演进，追求生命周期感知和自动取消。

---

## 五、HandlerThread 源码逐行分析

```java
/*
 * frameworks/base/core/java/android/os/HandlerThread.java
 */
public class HandlerThread extends Thread {
    // ── 成员变量 ──
    int mPriority;            // 线程优先级
    int mTid = -1;            // 线程 ID (JNI 层 tid)
    Looper mLooper;           // 线程关联的 Looper
    private @Nullable Handler mHandler;  // 便利 Handler

    // ── 构造方法 ──
    public HandlerThread(String name) {
        super(name);
        mPriority = Process.THREAD_PRIORITY_DEFAULT;
    }

    public HandlerThread(String name, int priority) {
        super(name);
        mPriority = priority;
    }

    // ── 线程入口 ──
    @Override
    public void run() {
        mTid = Process.myTid();                 // ① 记录 Linux tid
        Looper.prepare();                       // ② 创建 Looper + MessageQueue
        synchronized (this) {
            mLooper = Looper.myLooper();        // ③ 获取当前线程 Looper
            notifyAll();                         // ④ 唤醒 getLooper() 中的等待者
        }
        Process.setThreadPriority(mPriority);   // ⑤ 设置 CFS nice 值
        onLooperPrepared();                     // ⑥ 回调：可在子类覆写
        Looper.loop();                          // ⑦ 进入无限循环
    }

    // ── 获取 Looper (阻塞等待) ──
    public Looper getLooper() {
        if (!isAlive()) {
            return null;
        }
        // 竞态条件：线程可能已 start 但 run() 未执行到 synchronized 块
        synchronized (this) {
            while (isAlive() && mLooper == null) {
                try {
                    wait();                     // 等待 run() 中的 notifyAll()
                } catch (InterruptedException e) {
                    // 忽略
                }
            }
        }
        return mLooper;
    }

    // ── 获取 Handler (懒加载) ──
    @NonNull
    public Handler getThreadHandler() {
        if (mHandler == null) {
            mHandler = new Handler(getLooper());
        }
        return mHandler;
    }

    // ── 退出 ──
    public boolean quit() {
        Looper looper = getLooper();
        if (looper != null) {
            looper.quit();          // 立即退出，不处理未决延时消息
            return true;
        }
        return false;
    }

    public boolean quitSafely() {
        Looper looper = getLooper();
        if (looper != null) {
            looper.quitSafely();    // 安全退出，处理完已到时的消息
            return true;
        }
        return false;
    }

    // ── 钩子方法 ──
    protected void onLooperPrepared() {
        // 子类可覆写，在 Looper.loop() 前执行初始化
    }
}
```

**设计精要分析：**

| 设计点 | 机制 | 目的 |
|--------|------|------|
| `synchronized` + `wait/notifyAll` | 竞态保护 | 确保外部线程获取 Looper 时它已完全初始化 |
| `while(isAlive() && mLooper==null)` | 自旋检查 | 防虚假唤醒，确保 Looper 不为空才返回 |
| `onLooperPrepared()` | 模板方法 | 子类可在进入循环前初始化 Handler |
| `quit()` vs `quitSafely()` | 双退出策略 | 前者立即停止，后者处理完当前队列中已到时的消息 |
| 未实现 `finalize()` 自动 quit | 设计缺陷 | 若忘记调用 `quit()`，HandlerThread 将永不终止，JVM 线程泄漏 |

---

## 六、替代 AsyncTask 的现代方案

### 方案对比总览

| 特性 | AsyncTask | Kotlin Coroutines | WorkManager | RxJava |
|------|-----------|-------------------|-------------|--------|
| 生命周期感知 | ❌ | ✅ (lifecycleScope) | ✅ (自动管理) | ⚠️ (需手动 dispose) |
| 取消支持 | 弱 (需检查标志位) | ✅ (协作取消) | ✅ (系统级管理) | ✅ (dispose) |
| 错误处理 | try-catch | CoroutineExceptionHandler | Result.retry() | onError 回调 |
| 后台任务持久化 | ❌ | ❌ | ✅ (任务持久化) | ❌ |
| 约束条件执行 | ❌ | ❌ | ✅ (网络/充电) | ❌ |
| 链式调用 | ❌ | ✅ (Flow/Channel) | ✅ (链式 WorkRequest) | ✅ (操作符) |

### 方案一：Kotlin 协程（推荐首选）

```kotlin
// ── 基础用法：在 ViewModel 中使用 ──
class MyViewModel : ViewModel() {
    fun loadData() {
        viewModelScope.launch {
            // 自动绑定 ViewModel 生命周期，onCleared() 时自动取消
            val result = withContext(Dispatchers.IO) {
                // 后台线程执行网络/数据库操作
                apiService.fetchData()
            }
            // 自动切回 Dispatchers.Main
            _uiState.value = UiState.Success(result)
        }
    }
}

// ── Activity/Fragment 中的使用 ──
class MyActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        lifecycleScope.launch {
            // 绑定 Activity 生命周期，onDestroy 时自动取消
            delay(1000)
            updateUI()
        }
    }
}

// ── 并发控制 ──
suspend fun fetchMultipleSources() = coroutineScope {
    val deferred1 = async { apiService.fetchA() }
    val deferred2 = async { apiService.fetchB() }
    // 任一失败则取消另一个
    deferred1.await() to deferred2.await()
}

// ── Flow 替代 AsyncTask 的进度回调 ──
fun downloadFile(): Flow<DownloadProgress> = flow {
    emit(DownloadProgress.Starting)
    for (i in 0..100 step 10) {
        delay(100)
        emit(DownloadProgress.InProgress(i))
    }
    emit(DownloadProgress.Success)
}.flowOn(Dispatchers.IO)  // 上游在 IO 线程执行
```

**协程核心调度器：**

| Dispatcher | 用途 | 底层线程池 |
|------------|------|-----------|
| `Dispatchers.Main` | UI 更新 | 主线程 Looper |
| `Dispatchers.IO` | 网络/磁盘 I/O | 弹性线程池 (64 线程上限) |
| `Dispatchers.Default` | CPU 密集型计算 | CPU 核心数等量的线程池 |
| `Dispatchers.Unconfined` | 不切换线程 | 在调用者线程执行直到第一个挂起点 |

**AsyncTask 迁移对照：**

```kotlin
// AsyncTask 旧写法：
class MyTask : AsyncTask<String, Int, Result>() {
    override fun doInBackground(vararg params: String): Result { ... }
    override fun onProgressUpdate(vararg values: Int?) { ... }
    override fun onPostExecute(result: Result) { ... }
}

// Coroutines 新写法：
lifecycleScope.launch {
    val result = withContext(Dispatchers.IO) {
        // doInBackground
        asyncTaskLogic()
    }
    // onPostExecute → 已在 Main 线程
    updateUI(result)
}
```

### 方案二：WorkManager（持久化后台任务）

```kotlin
// ── 定义 Worker ──
class UploadWorker(context: Context, params: WorkerParameters) :
    CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        return try {
            // 在 Dispatchers.Default 上执行
            uploadData(inputData.getString("filePath")!!)
            Result.success()
        } catch (e: Exception) {
            Result.retry()  // 自动重试
        }
    }
}

// ── 调度任务 ──
val constraints = Constraints.Builder()
    .setRequiredNetworkType(NetworkType.CONNECTED)
    .setRequiresBatteryNotLow(true)
    .build()

val uploadRequest = OneTimeWorkRequestBuilder<UploadWorker>()
    .setConstraints(constraints)
    .setInputData(workDataOf("filePath" to "/sdcard/file.zip"))
    .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 10, TimeUnit.SECONDS)
    .build()

WorkManager.getInstance(context).enqueue(uploadRequest)

// ── 观察任务状态 ──
WorkManager.getInstance(context)
    .getWorkInfoByIdLiveData(uploadRequest.id)
    .observe(lifecycleOwner) { workInfo ->
        when (workInfo.state) {
            WorkInfo.State.SUCCEEDED -> showSuccess()
            WorkInfo.State.FAILED -> showError()
            WorkInfo.State.RUNNING -> showProgress(workInfo.progress)
            else -> {}
        }
    }
```

**WorkManager 的独特优势：**

- **任务持久化：** 基于 Room 数据库存储任务，App 重启/设备重启后仍会执行。
- **约束感知：** 可按网络状态、电量、空闲状态等条件调度。
- **兼容 Doze 模式：** 在 Android 6.0+ 的 Doze 模式下也能通过 AlarmManager 唤醒执行。
- **链式任务：** `beginWith(A).then(B).then(C)` 构建 DAG。

---

## 七、面试进阶追问 & 深度回答

### 追问 1：Looper 死循环里为什么可以响应点击事件？

**回答：** 触摸事件通过 InputReader → InputDispatcher → socket 发送到应用进程。`MessageQueue` 的 `nativePollOnce()` 底层是 `epoll_wait`，同时监听了 **Input 事件 socket fd** 和 **消息队列 eventfd**。当 InputDispatcher 写入 socket 时，epoll_wait 被唤醒，Native 层读取事件并封装为 `Message` 投递到消息队列，`dispatchMessage` 再分发给 DecorView。整个链路上没有"繁忙等待"，全由 epoll 事件驱动。

### 追问 2：主线程 Looper 为什么 quitAllowed=false？

**回答：** `Looper.prepareMainLooper()` 调用 `prepare(false)`，`quitAllowed` 参数传入 `false`。主线程 Looper 是应用生命周期核心，一旦退出，整个应用的 UI 事件处理、Binder 调用回传、生命周期回调全部中断，进程实际上已不可用。Android 设计上禁止主线程 Looper 退出 —— 进程退出由 AMS 通过 `Process.killProcess()` 或系统信号完成，而非优雅退出。

### 追问 3：Handler 的消息延时精度如何？

**回答：** `sendMessageDelayed(msg, delayMillis)` 中 `delayMillis` 最终转化为 `SystemClock.uptimeMillis() + delayMillis` 存入 `msg.when`。在 `next()` 中计算 `nextPollTimeoutMillis = msg.when - now`，传给 `nativePollOnce(ptr, timeout)`。timeout 作为 `epoll_wait` 的超时参数，精确到 **毫秒级**。但因消息队列是 FIFO（按时序排列），前序消息处理耗时过长会推后后续消息的实际触发时间，所以延时精度受队列中前面消息的影响。

### 追问 4：同步屏障（SyncBarrier）的作用是什么？

**回答：** 同步屏障是一条 `target == null` 的特殊消息。插入后，后续同步消息被跳过，只有异步消息（`msg.setAsynchronous(true)`）能通过。View 的绘制（`ViewRootImpl.scheduleTraversals`）使用此机制：即使主线程消息队列中有大量同步消息，异步的绘制消息仍能优先执行，保证 60fps 流畅度。注意：同步屏障必须成对移除，否则主线程消息队列永久阻塞。

---

## 八、面试自测清单

- [ ] 能画出 Looper/Handler/MessageQueue 关系图
- [ ] 能解释 `Looper.prepare()` → `loop()` 的完整调用链
- [ ] 能分析 HandlerThread 为什么需要 `synchronized` + `wait/notify`
- [ ] 能说明 AsyncTask 串行执行的线程池实现
- [ ] 能写出协程替代 AsyncTask 的完整代码
- [ ] 能解释 `nativePollOnce` 与 epoll 的关系
- [ ] 能阐述 IdleHandler 的原理和用途
- [ ] 能说明同步屏障的使用场景
- [ ] 能对比 `quit()` 与 `quitSafely()` 的区别
- [ ] 能描述 Binder 线程池的工作方式
- [ ] 能解释 cgroup 如何限制后台线程 CPU 使用
- [ ] 能说明 Handler 内存泄漏的根本原因与修复方式

---

> **参考源码文件：**
> - `frameworks/base/core/java/android/os/Looper.java`
> - `frameworks/base/core/java/android/os/Handler.java`
> - `frameworks/base/core/java/android/os/MessageQueue.java`
> - `frameworks/base/core/java/android/os/HandlerThread.java`
> - `frameworks/base/core/java/android/app/IntentService.java`
> - `frameworks/base/core/java/android/os/AsyncTask.java`
> - `frameworks/base/core/java/android/app/ActivityThread.java`
