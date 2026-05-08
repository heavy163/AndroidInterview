# 03 Kotlin协程并发

> **面试权重**: ★★★★★ | **字数**: ~4500 | **阅读时长**: 20min
>
> Kotlin协程不是线程，是挂起计算框架。30k+面试必问：你用的是真正结构化并发，还是披着协程皮的多线程？本文从面试题出发，深入源码，手写Channel+Actor。

---

## 目录

- [一、面试核心五问（1800字）](#一面试核心五问)
  - [Q1: 什么是结构化并发？CoroutineScope的生命周期如何管理？](#q1-什么是结构化并发coroutinescope的生命周期如何管理)
  - [Q2:协程的Mutex vs Java的synchronized——本质区别是什么？](#q2-协程的mutex-vs-java的synchronized本质区别是什么)
  - [Q3: Semaphore在协程中如何做并发限流？](#q3-semaphore在协程中如何做并发限流)
  - [Q4: Channel的三种模式——RENDEZVOUS / BUFFERED / CONFLATED各适用什么场景？](#q4-channel的三种模式rendezvous--buffered--conflated各适用什么场景)
  - [Q5: Actor模式如何实现协程内的并发安全？](#q5-actor模式如何实现协程内的并发安全)
- [二、协程取消的协作机制（900字）](#二协程取消的协作机制)
- [三、Mutex挂起非阻塞 & Channel的select多路复用（700字）](#三mutex挂起非阻塞--channel的select多路复用)
- [四、协程并发通信模式图（500字）](#四协程并发通信模式图)
- [五、Mutex.lock()源码分析（800字）](#五mutexlock源码分析)
- [六、实战：Channel + Actor 实现线程安全的消息处理（600字）](#六实战channel--actor-实现线程安全的消息处理)

---

## 一、面试核心五问

### Q1: 什么是结构化并发？CoroutineScope的生命周期如何管理？

**面试官意图**：你在协程中能否避免任务泄漏？知不知道父子协程的取消传播？

**核心答案**：

结构化并发是Kotlin协程的基石。它的核心原则是：**协程必须在某个CoroutineScope中启动，Scope控制着内部所有协程的生命周期**。当Scope被取消时，其内部所有协程都会被自动取消——不会遗留"悬空"协程。

```
结构化的三层关系：

    CoroutineScope (顶层作用域)
        ├── coroutineContext[Job]    ← 控制取消的根Job
        ├── launch { }              ← 子协程1 (父Job的子Job)
        ├── async { }               ← 子协程2
        └── launch {
                launch { }          ← 孙子协程
            }
    
    取消传播方向：父 → 子 (自上而下)
    异常传播方向：子 → 父 (自下而上，launch默认)
```

**面试必背的三个Scope**：

| Scope | 生命周期 | Android场景 |
|-------|---------|------------|
| `viewModelScope` | 绑定ViewModel的onCleared() | 屏幕旋转不重建时自动取消 |
| `lifecycleScope` | 绑定Lifecycle的onDestroy() | Activity/Fragment销毁时取消 |
| `GlobalScope` | 进程级别，永不自动取消 | ⚠️ 几乎永远不要用 |
| `CoroutineScope(Dispatchers.IO)` | 手动管理，需显式cancel() | 全局后台任务（需手动维护） |

**反模式——结构化并发的反面**：

```kotlin
// ❌ 反模式：GlobalScope + 忘记cancel = 协程泄漏
class MyActivity : Activity() {
    override fun onResume() {
        super.onResume()
        GlobalScope.launch {  // 永不取消！
            while (true) {
                fetchData()   // Activity销毁后仍在请求
            }
        }
    }
}
```

**正确做法**：

```kotlin
// ✅ 使用lifecycleScope自动取消
class MyActivity : Activity() {
    override fun onResume() {
        super.onResume()
        lifecycleScope.launch {
            while (isActive) {      // 尊重取消信号
                fetchData()
            }
        }
    }
}
```

**面试深挖——Job树如何传播取消**：

取消是协作式的，通过Job的父子关系传播：
1. `parentJob.cancel()` → 所有子Job收到CancellationException
2. 子协程在挂起点（如`delay()`, `yield()`）检查`isActive`
3. 如果子协程不检查`isActive`，取消不会生效——这就是"非抢占式取消"

**考官追问**："如果子协程捕获了CancellationException会怎样？"
- 答：如果只是捕获但不重新抛出，父协程会认为子协程"正常完成"，不会取消兄弟协程。这破坏了结构化并发的取消一致性。正确做法是使用`withContext(NonCancellable)`处理不可取消的清理代码。

---

### Q2: 协程的Mutex vs Java的synchronized——本质区别是什么？

**面试官意图**：知不知道协程的挂起特性和线程阻塞的根本差异？

**核心对比**：

| 维度 | synchronized（Java） | Mutex（Kotlin协程） |
|------|---------------------|---------------------|
| **阻塞类型** | 线程级阻塞（BLOCKED状态） | 协程挂起（SUSPENDED），线程释放 |
| **线程资源** | 等待时占用线程 | 等待时不占用线程 |
| **死锁风险** | 高（线程互等） | 低（协程可超时取消） |
| **可取消** | ❌ 不可取消 | ✅ `withTimeout`可取消等待 |
| **可重入** | ✅ 是可重入锁 | ❌ 不可重入（设计意图） |
| **适用场景** | 短临界区，线程池有限 | 长IO操作内的互斥，协程密集 |

**为什么Mutex在线程上不阻塞——核心机制**：

```kotlin
// synchronized：线程卡住
synchronized(lock) {
    Thread.sleep(1000)  // 线程实实在在睡了1秒，不干别的
}

// Mutex：协程挂起，线程去执行其他协程
mutex.withLock {
    delay(1000)  // 线程去执行其他协程，1秒后回来
}
```

**面试关键点——Mutex不能替代synchronized的场景**：

1. **与Java代码交互**：调用Java的synchronized方法时，Mutex无能为力——你仍然会阻塞线程。
2. **极短临界区**：对HashMap的put操作，synchronized开销远小于协程的挂起-恢复开销。
3. **框架硬需求**：某些第三方库要求必须在特定线程执行，禁用协程调度。

**Mutex不可重入的设计哲学**：

```kotlin
mutex.withLock {
    mutex.withLock { }  // ❌ 死锁！协程永远挂起等待自己释放锁
}
```

这并非缺陷，而是设计意图：鼓励更简洁的锁结构，避免"跨函数隐式持有锁"这种synchronized常见的死锁源头。

---

### Q3: Semaphore在协程中如何做并发限流？

**面试官意图**：考察对"非阻塞限流"的理解，区别于线程池的maxPoolSize。

**核心答案**：

Semaphore（信号量）是一种轻量级并发控制工具。与线程池的maxPoolSize不同，Semaphore限制的是**协程的并发数量**，而不是线程数量。

**典型场景**：你有1000个并发网络请求，但API服务器只允许同时5个连接。用线程池需要5个线程，使用Semaphore可以只用1个线程+5个并发协程。

```kotlin
class ApiRateLimiter {
    private val semaphore = Semaphore(permits = 5) // 最多5个并发协程

    suspend fun fetchUser(id: Int): User {
        semaphore.acquire()       // 挂起等待，直到有许可
        try {
            return api.getUser(id) // 挂起IO操作
        } finally {
            semaphore.release()    // 释放许可，让下一个协程进入
        }
    }
}

// 实际使用：1000个请求，但最多5个同时进行
lifecycleScope.launch {
    val users = coroutineScope {
        (1..1000).map { id ->
            async { rateLimiter.fetchUser(id) }
        }.awaitAll()
    }
}
```

**Semaphore vs Channel的限流对比**：

| 工具 | 原理 | 优势 | 劣势 |
|------|------|------|------|
| Semaphore | 许可计数，acquire时挂起 | 灵活，适合异构任务 | 需手动release |
| Channel(BUFFERED) | 缓冲区满时send挂起 | 天然工作队列 | 适合同构任务 |
| 线程池 | 线程数限制 | Java生态成熟 | 线程资源重，切换开销大 |

**面试追问**："如果协程在acquire之后、release之前被取消怎么办？"
- 答：必须在`finally`中release，且使用`withContext(NonCancellable)`保证release不被跳过：

```kotlin
suspend fun safeAcquire(semaphore: Semaphore, block: suspend () -> T): T {
    semaphore.acquire()
    return try {
        block()
    } finally {
        withContext(NonCancellable) {
            semaphore.release()  // 即使协程被取消，也一定释放
        }
    }
}
```

---

### Q4: Channel的三种模式——RENDEZVOUS / BUFFERED / CONFLATED各适用什么场景？

**面试官意图**：考察对生产者-消费者模型的深刻理解。

Channel本质上是一个**挂起队列**（SuspendingQueue），它同时拥有`send`和`receive`两个挂起函数，可以在生产者与消费者之间安全传递数据。

**三种模式深度解析**：

```
┌──────────────┬────────────────────────────────┬──────────────────────────────┐
│   模式       │          行为                  │         典型场景              │
├──────────────┼────────────────────────────────┼──────────────────────────────┤
│ RENDEZVOUS   │ 无缓冲区：send必须在receive    │ 精确同步：状态机联动、       │
│  (默认)      │ 就绪时才能完成（会面点）       │ 生产者需等待消费者确认        │
├──────────────┼────────────────────────────────┼──────────────────────────────┤
│ BUFFERED     │ 固定容量缓冲区（默认64）：     │ 生产者快于消费者、           │
│              │ send在缓冲区满之前不挂起       │ 允许一定的速率差              │
├──────────────┼────────────────────────────────┼──────────────────────────────┤
│ CONFLATED    │ 容量=1且新值覆盖旧值：         │ 只关心最新状态：             │
│              │ send永不挂起，receive取最新值  │ UI状态更新、传感器数据流      │
├──────────────┼────────────────────────────────┼──────────────────────────────┤
│ UNLIMITED    │ 无限缓冲区：send永不挂起       │ 生产者完全异步（⚠内存风险） │
└──────────────┴────────────────────────────────┴──────────────────────────────┘
```

**代码示例——三种模式的差异**：

```kotlin
// RENDEZVOUS：会面点模式
val rendezvous = Channel<Int>(Channel.RENDEZVOUS)
// send(1) 会挂起，直到有协程调用 receive()

// BUFFERED：缓冲模式
val buffered = Channel<Int>(Channel.BUFFERED)  // 默认64
buffered.send(1) // 不挂起（缓冲区有空间）
buffered.send(2) // 不挂起

// CONFLATED：合并模式——永远只保留最新值
val conflated = Channel<Int>(Channel.CONFLATED)
conflated.send(1) // 不挂起
conflated.send(2) // 1被丢弃，2生效
conflated.send(3) // 2被丢弃
println(conflated.receive()) // 输出 3
```

**面试场景题**："实现一个高并发计数器，显示实时点击数，但UI每秒只刷新一次。用什么Channel？"
- 答案：`CONFLATED`。生产者每秒可能send 1000次点击，消费者每秒只取一次最新值用于UI，中间的999次自动丢弃——完美。

**源码关键**：Channel内部基于`AbstractChannel`，使用CAS+链表管理`SendElement`和`ReceiveElement`的等待队列。BUFFERED模式额外维护一个固定大小的数组缓冲区。

---

### Q5: Actor模式如何实现协程内的并发安全？

**面试官意图**：考察对"消息驱动的无锁并发"的核心理解。

**核心答案**：

Actor模式的核心思想：**每个Actor拥有私有的可变状态，外界只能通过发送消息来修改状态**。消息在Actor内部被逐个顺序处理，天然避免了多线程竞态。

```
Actor并发模型：

    ┌──────────────┐      消息      ┌──────────────────┐
    │  协程1       │ ──send──→      │                  │
    │  (生产者)    │                │   Actor协程      │
    └──────────────┘               │                  │
                                   │  ┌────────────┐  │
    ┌──────────────┐     消息      │  │  私有状态   │  │
    │  协程2       │ ──send──→      │  │  (Mutable)  │  │
    │  (生产者)    │                │  └────────────┘  │
    └──────────────┘               │        │         │
                                   │   顺序处理消息    │
    ┌──────────────┐     消息      │        │         │
    │  协程3       │ ──send──→      │   产生新状态     │
    │  (生产者)    │                └──────────────────┘
    └──────────────┘
```

**关键特征**：
1. **状态隔离**：状态只存在于Actor协程内部，外部不可直接访问
2. **消息驱动**：所有状态修改通过消息队列（Channel）串行化
3. **无锁并发**：既然是顺序处理，就不需要synchronized、ReentrantLock或Mutex
4. **天然线程安全**：Actor协程在某一时刻只处理一条消息

**与Mutex的关键对比**：

| 维度 | Actor | Mutex |
|------|-------|-------|
| 加锁方式 | 消息队列天然串行 | 显式withLock |
| 状态修改 | 间接（发消息） | 直接（锁内修改） |
| 耦合度 | 低（解耦状态与操作） | 高（调用方必须知道锁） |
| 可组合性 | 强（可嵌套Actor） | 弱（锁嵌套=死锁风险） |
| 性能 | 略高（无锁） | 略低（需要CAS/自旋） |

---

## 二、协程取消的协作机制

### Job.join() 与 Job.cancel() 的协作语义

协程取消是**非抢占式**的，这意味着被取消的协程必须主动配合检查取消状态才会终止。

**核心流程**：

```
cancel()调用 → Job状态变为Cancelling
              → 向所有子Job传播CancellationException
              → 子协程在挂起点检测到取消
              → 子协程抛出CancellationException
              → Job状态变为Cancelled
              → join()返回（被取消的协程已终结）
```

**面试关键代码——join的语义陷阱**：

```kotlin
val job = launch {
    try {
        repeat(1000) { i ->
            println("计算中 $i")
        }
    } finally {
        println("清理资源")
    }
}

delay(100)
job.cancel()     // 发出取消信号
job.join()       // 挂起，直到job完全终止（执行完finally）
println("协程已完全终止")
// 输出：计算中 0 → ... → 计算中 N → 清理资源 → 协程已完全终止
```

**为什么是协作式取消——设计哲学**：

1. **资源安全**：如果强制终止，正在持有锁的协程被中断会导致死锁
2. **数据一致性**：给协程机会在finally中回滚事务、关闭连接
3. **无内存泄漏**：finally确保资源释放

**面试追问**："如果协程正在执行CPU密集计算（计算段没有挂起点），cancel会被忽略吗？"
- 答：会！必须显式检查`isActive`或调用`yield()`：

```kotlin
val job = launch {
    repeat(1_000_000) {
        if (!isActive) return@launch  // 必须主动检查！
        heavyComputation()
    }
}
```

---

## 三、Mutex挂起非阻塞 & Channel的select多路复用

### Mutex的挂起特性——为什么线程不阻塞

Mutex的核心秘密在于：当协程调用`mutex.lock()`但锁已被持有时，协程被**挂起**（SUSPENDED），而不是线程被阻塞。执行该协程的线程可以去执行其他就绪协程。

```kotlin
// 演示：Mutex不阻塞线程
suspend fun mutexDemo() = coroutineScope {
    val mutex = Mutex()
    val startTime = System.currentTimeMillis()

    // 协程A：先获取锁，占用2秒
    launch {
        mutex.withLock {
            delay(2000)  // 线程被释放！其他协程可以使用该线程
        }
    }

    // 协程B：稍后请求同一把锁
    delay(100)
    launch {
        mutex.withLock {
            // 这里被挂起了约1.9秒，但线程没有阻塞
            println("耗时: ${System.currentTimeMillis() - startTime}ms") // ~2100ms
        }
    }
}
```

**Mutex底层实现**：
- 基于原子操作（`AtomicReference`）的无锁状态机
- 锁状态：`UNLOCKED` → `LOCKED` → 等待队列（链表）
- 等待者被包装为`LockedQueue`节点，协程挂起时通过`Continuation`的`suspendCoroutineUninterceptedOrReturn`实现

### Channel的select多路复用

`select`表达式允许一个协程**同时等待多个挂起操作**，哪个先完成就执行哪个。这是对Go语言select语法的借鉴。

```kotlin
suspend fun selectDemo(): String = coroutineScope {
    val channel1 = produce { delay(100); send("结果A") }
    val channel2 = produce { delay(200); send("结果B") }

    // 同时等待两个Channel，谁先返回就用谁
    select<String> {
        channel1.onReceive { value ->
            "先收到: $value"  // 100ms后返回："先收到: 结果A"
        }
        channel2.onReceive { value ->
            "先收到: $value"
        }
    }
}
```

**实战场景——超时保护的select**：

```kotlin
suspend fun fetchWithTimeout(): Data = coroutineScope {
    val dataChannel = async { api.fetchData() }
    val timeoutChannel = produce<Unit> { delay(5000); send(Unit) }

    select<Data> {
        dataChannel.onAwait { it }       // 如果数据先到
        timeoutChannel.onReceive {       // 如果超时先到
            throw TimeoutException()
        }
    }
}
```

---

## 四、协程并发通信模式图

### 4.1 生产者-消费者模式（Channel）

```
                    ┌──────────────────────┐
                    │      Channel          │
                    │  ┌──────────────────┐ │
    生产者1 ─send───→│  │  缓冲区 (FIFO)   │ │───receive→ 消费者1
    生产者2 ─send───→│  │  [ ][ ][ ][ ]    │ │───receive→ 消费者2
    生产者3 ─send───→│  └──────────────────┘ │
                    │  挂起队列:              │
                    │  - senders等待缓冲区空  │
                    │  - receivers等待数据    │
                    └──────────────────────┘
```

### 4.2 Actor模式（消息驱动无锁）

```
    ┌─────────────────────────────────────┐
    │           Actor 协程                │
    │                                     │
    │   消息Channel ─→ 排队 ─→ 逐条处理   │
    │   ┌─────┐      ┌──┐   ┌──────────┐ │
    │   │ msg1│─────→│  │──→│ 更新状态  │ │
    │   │ msg2│─────→│  │──→│ 更新状态  │ │
    │   │ msg3│─────→│  │──→│ 更新状态  │ │
    │   └─────┘      └──┘   └──────────┘ │
    │                                     │
    │   私有状态（Mutable）:               │
    │   - 只有Actor自己可修改              │
    │   - 外部只能通过发消息间接修改        │
    └─────────────────────────────────────┘
```

### 4.3 结构化并发模型（父子协程树）

```
                    ┌──────────────────────────┐
                    │   CoroutineScope         │
                    │   (ScopeJob)             │
                    └────────┬─────────────────┘
                             │
            ┌────────────────┼────────────────┐
            ▼                ▼                ▼
    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
    │   launch 1   │ │   async 2    │ │   launch 3   │
    │  (Job-1)     │ │  (Deferred)  │ │  (Job-3)     │
    └──────┬───────┘ └──────────────┘ └──────┬───────┘
           │                                 │
    ┌──────┴──────┐                   ┌──────┴──────┐
    ▼             ▼                   ▼             ▼
  launch1.1    launch1.2          launch3.1     Async3.2
  (Job-1-1)    (Job-1-2)          (Job-3-1)     (Deferred)

    取消传播：Scope.cancel() → 依次取消所有后代Job
    异常传播：子Job异常 → 向上传播到ScopeJob → 取消兄弟Job
```

### 4.4 Mutex与Semaphore的调度模型

```
    协程A ──→ [Mutex等待队列] ──→ 获取锁 ──→ 执行临界区 ──→ 释放锁
    协程B ──→ [Mutex等待队列] ──→ 挂起等待...
    协程C ──→ [Mutex等待队列] ──→ 挂起等待...
    
    Semaphore(permits=3):
    协程A ──→ acquire(许可1) → 执行
    协程B ──→ acquire(许可2) → 执行
    协程C ──→ acquire(许可3) → 执行
    协程D ──→ acquire → 挂起等待（无可用许可）
    协程E ──→ acquire → 挂起等待
```

---

## 五、Mutex.lock()源码分析

### 5.1 类结构与状态机

Kotlin协程的Mutex实现在`kotlinx.coroutines.sync.Mutex.kt`中。`Mutex.lock()`返回的不是普通的锁对象，而是一个**挂起函数**——这是它与Java锁最根本的差异。

**核心状态机**（简化）：

```
UNLOCKED ──lock()──→ LOCKED ──释放──→ UNLOCKED
                         │
                    (另一个协程尝试lock())
                         │
                         ▼
                    LOCKED + 等待队列中有节点
                         │
                    释放时唤醒队列头部节点
```

源码结构（简化版）：

```kotlin
// 核心内部类 MutexImpl
internal class MutexImpl(locked: Boolean) : Mutex, SelectClause2<Any?, Mutex> {
    // 原子状态：_state 
    // - null: UNLOCKED
    // - Empty(unlocked): LOCKED，无等待者
    // - LockedQueue(owner): LOCKED，有等待队列
    // - LockedQueue中保存了挂起的Continuation链表
    private val _state = atomic<Any?>(if (locked) EMPTY_LOCKED else null)
    
    override suspend fun lock(owner: Any?) {
        // 快速路径：CAS尝试获取锁
        if (tryLock(owner)) return  // 成功，不挂起
        
        // 慢路径：加入等待队列并挂起
        return lockSuspend(owner)
    }
}
```

### 5.2 快速路径——tryLock的CAS操作

```kotlin
// 源码简化
override fun tryLock(owner: Any?): Boolean {
    _state.loop { state ->
        when {
            state == null -> {  // UNLOCKED
                // CAS：将null替换为EMPTY_LOCKED（表示已锁定且无等待者）
                if (_state.compareAndSet(null, EMPTY_LOCKED)) return true
            }
            else -> return false // 已锁定，快速失败
        }
    }
}
```

**关键设计**：
- `atomic`来自`kotlinx.atomicfu`，在编译时会被替换为平台相关的原子操作（JVM上用`AtomicReferenceFieldUpdater`）
- `loop`是一个无限循环包裹的CAS重试——这是lock-free编程的标准范式
- 如果`tryLock`成功，整个`lock()`调用**不会挂起协程**，零开销

### 5.3 慢路径——lockSuspend的挂起机制

当快速路径失败（锁已被占用），进入慢路径：

```kotlin
// 源码简化
private suspend fun lockSuspend(owner: Any?) = suspendCancellableCoroutine<Unit> sc@ { cont ->
    val waiter = LockedQueue()  // 创建等待节点
    waiter.owner = owner
    waiter.cont = cont          // 保存当前协程的Continuation
    
    _state.loop { state ->
        when (state) {
            is Empty -> {
                // 当前锁状态是EMPTY_LOCKED，需要替换为LockedQueue
                val newState = LockedQueue().apply { addLast(waiter) }
                if (_state.compareAndSet(state, newState)) {
                    // CAS成功，协程已加入到等待队列
                    cont.invokeOnCancellation {
                        // 如果协程被取消，从等待队列中移除自己
                        removeWaiter(waiter)
                    }
                    return@sc  // 协程挂起，等待被唤醒
                }
            }
            is LockedQueue -> {
                // 锁已有等待队列，追加到队尾
                state.addLast(waiter)
                cont.invokeOnCancellation { removeWaiter(waiter) }
                return@sc  // 挂起
            }
        }
    }
}
```

**核心挂起点**：`suspendCancellableCoroutine`——这是Kotlin协程挂起的"真正入口"。当`return@sc`被执行时，协程不会立即返回，而是被挂起。后续当锁的持有者调用`unlock()`时，会从等待队列头部取出等待者，通过`waiter.cont.resume(Unit)`恢复协程。

### 5.4 unlock的释放逻辑

```kotlin
// 源码简化
override fun unlock(owner: Any?) {
    _state.loop { state ->
        when (state) {
            is Empty -> {
                // 无等待者，直接置为null（UNLOCKED）
                if (_state.compareAndSet(state, null)) return
            }
            is LockedQueue -> {
                // 有等待者，取出队头节点
                val waiter = state.removeFirstOrNull()
                if (waiter == null) {
                    // 队列为空，CAS为null
                    if (_state.compareAndSet(state, null)) return
                } else {
                    // 唤醒队头等待者
                    if (_state.compareAndSet(state, newState)) {
                        waiter.complete()  // → cont.resume(Unit) → 协程恢复
                        return
                    }
                }
            }
        }
    }
}
```

### 5.5 设计精要总结

| 设计点 | 实现 | 意义 |
|--------|------|------|
| 无锁状态机 | AtomicReference + CAS循环 | 避免系统调用开销 |
| 协程挂起 | suspendCancellableCoroutine | 不阻塞线程 |
| 公平性 | FIFO链表队列 | 先来先服务，避免饥饿 |
| 可取消 | invokeOnCancellation | 协程取消时自动退队 |
| 不可重入 | 无owner检查 | 简化设计，避免死锁 |

---

## 六、实战：Channel + Actor 实现线程安全的消息处理

### 6.1 场景：并发支付状态管理器

需求：多个协程同时上报支付状态（支付中→支付成功/支付失败），要求：
1. 最终状态不可逆（成功→失败非法）
2. 线程安全（多个协程并发上报）
3. 通知外部观察者

### 6.2 传统方案的问题

传统方案需要使用`synchronized`或`Mutex`保护可变状态，但存在：
- 状态与业务逻辑耦合
- 锁的粒度难以把控
- 需要手动处理并发边界

### 6.3 Actor实现方案

```kotlin
// 消息类型
sealed class PaymentCommand {
    data class Pay(val orderId: String, val amount: Long) : PaymentCommand()
    data class ReportSuccess(val orderId: String) : PaymentCommand()
    data class ReportFailure(val orderId: String, val reason: String) : PaymentCommand()
}

// Actor返回结果
data class PaymentResult(val orderId: String, val status: String)

// Actor实现
fun CoroutineScope.paymentActor(): SendChannel<PaymentCommand> = actor {
    // ⭐ 私有可变状态——只存在于Actor协程内部
    val orders = mutableMapOf<String, PaymentResult>()
    val callbacks = mutableListOf<(PaymentResult) -> Unit>()

    for (msg in channel) {  // 逐条接收消息，串行处理
        when (msg) {
            is PaymentCommand.Pay -> {
                orders[msg.orderId] = PaymentResult(msg.orderId, "支付中")
            }
            is PaymentCommand.ReportSuccess -> {
                val result = PaymentResult(msg.orderId, "支付成功")
                orders[msg.orderId] = result
                callbacks.forEach { it(result) }  // 通知观察者
            }
            is PaymentCommand.ReportFailure -> {
                val order = orders[msg.orderId]
                // ⭐ 状态机保护：成功→失败是非法转换
                if (order?.status != "支付成功") {
                    val result = PaymentResult(msg.orderId, "支付失败: ${msg.reason}")
                    orders[msg.orderId] = result
                }
            }
        }
    }
}

// 使用示例
fun main() = runBlocking {
    val actor = paymentActor()

    // 多个协程并发发送消息，但Actor内部串行处理
    launch { actor.send(PaymentCommand.Pay("ORD-001", 10000)) }
    launch { actor.send(PaymentCommand.Pay("ORD-002", 5000)) }
    launch { delay(100); actor.send(PaymentCommand.ReportSuccess("ORD-001")) }
    launch { delay(50); actor.send(PaymentCommand.ReportFailure("ORD-001", "余额不足")) }

    delay(200)
    actor.close() // 关闭Actor，结束消息处理
}
```

### 6.4 为什么Actor能保证线程安全

```
时间线（Actor内部只有一个协程执行消息处理）：

t1: Pay("ORD-001")       → orders["ORD-001"] = 支付中
t2: Pay("ORD-002")       → orders["ORD-002"] = 支付中
t3: ReportSuccess("001") → orders["ORD-001"] = 支付成功 (通知)
t4: ReportFailure("001") → 检测到"支付成功"，拒绝非法转换

    所有操作在同一个协程内顺序执行 → 无需任何锁！
```

**关键分析**：
- `orders`这个`MutableMap`被多个协程通过消息间接修改，但从Actor协程的视角看，它是**单线程访问**
- Actor内部的`for(msg in channel)`循环保证了消息的**FIFO顺序处理**
- 无需`synchronized`、无需`Mutex`、无需`AtomicReference`
- 这就是"用通信来共享内存，而不是用共享内存来通信"的Go/Erlang哲学在Kotlin协程中的体现

### 6.5 Actor模式的适用边界

| ✅ 适合 | ❌ 不适合 |
|---------|----------|
| 有状态的服务（缓存、会话管理） | 无状态的纯计算 |
| 需要串行化的操作（支付、退款） | 需要高并行读的场景 |
| 多个生产者竞争写入 | 需要读多写少的缓存（用ReadWriteLock更好） |
| 需要解耦状态与操作的架构 | 极低延迟要求（消息转发有开销） |

---

## 附录：面试自检清单

在面试前，确保你能回答以下问题：

- [ ] 结构化并发的三个核心要素是什么？（Scope、Job树、取消传播）
- [ ] `viewModelScope`和`lifecycleScope`分别绑定什么生命周期？
- [ ] 为什么Mutex不可重入？设计意图是什么？
- [ ] Semaphore与Channel限流的核心区别？
- [ ] RENDEZVOUS vs CONFLATED Channel的应用场景区分？
- [ ] Actor模式为什么是无锁并发？
- [ ] 协程取消是抢占式还是协作式？为什么？
- [ ] `suspendCancellableCoroutine`在Mutex中扮演什么角色？
- [ ] `select`表达式可以同时等待哪些类型的挂起操作？
- [ ] 取消协程时，`finally`块中应该注意什么？（`NonCancellable`）

---

> **推荐阅读**：
> - [Kotlin Coroutines 官方文档 - Shared Mutable State](https://kotlinlang.org/docs/shared-mutable-state-and-concurrency.html)
> - [Roman Elizarov: Structured Concurrency](https://elizarov.medium.com/structured-concurrency-722d765aa952)
> - [kotlinx.coroutines 源码 - Mutex.kt](https://github.com/Kotlin/kotlinx.coroutines)
