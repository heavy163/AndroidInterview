# 锁与同步机制面试题集

> 面向Android中高级开发者的锁与同步机制知识体系，涵盖synchronized锁升级全过程、ReentrantLock与AQS实现、读写锁原理、死锁排查以及LockSupport底层机制等核心考点。

---

## 一、面试层：高频面试题精选（5+题）

### 1. synchronized锁升级全过程：偏向锁 → 轻量级锁 → 重量级锁

synchronized在JDK 1.6之后引入了"锁升级"机制，不是一开始就使用重量级锁（mutex），而是根据竞争程度逐步升级，以减少不必要的系统调用开销。整个升级路径是 **无锁 → 偏向锁 → 轻量级锁（自旋锁）→ 重量级锁**，且升级是**单向不可逆**的。

#### 1.1 对象头的Mark Word

Java对象在堆内存中由三部分组成：对象头、实例数据、对齐填充。对象头中的Mark Word（32位JVM占32bit，64位JVM占64bit）存储了锁状态标志位：

| 锁状态 | 标志位（最后2bit） | 是否偏向（1bit） | Mark Word存储内容 |
|--------|-------------------|------------------|-------------------|
| **无锁** | `01` | `0` | hashCode（25bit）+ age（4bit） |
| **偏向锁** | `01` | `1` | 线程ID（54bit）+ epoch（2bit）+ age（4bit） |
| **轻量级锁** | `00` | - | 指向栈中Lock Record的指针（62bit） |
| **重量级锁** | `10` | - | 指向互斥量Monitor的指针（62bit） |
| **GC标记** | `11` | - | 空，用于GC标记 |

#### 1.2 偏向锁（Biased Locking）

**获取流程：**

1. 线程访问同步块时，检查Mark Word中是否存储了指向当前线程的偏向锁ID
2. 如果是当前线程ID → 直接进入同步块（无需CAS操作）
3. 如果为空（匿名偏向）→ CAS将Mark Word设置为当前线程ID
4. 如果已经是其他线程ID → 触发**偏向锁撤销**（需在SafePoint执行），升级为轻量级锁

**偏向锁的批量重偏向与批量撤销：**

JVM维护了每个类的epoch值。当撤销次数达到阈值（默认20，`-XX:BiasedLockingBulkRebiasThreshold`）时，触发批量重偏向（Bulk Rebias）；达到40次时，触发批量撤销（Bulk Revocation），此后该类的所有对象都不再支持偏向锁。

```java
// 偏向锁延迟：JVM启动后4秒才启用偏向锁
// -XX:BiasedLockingStartupDelay=0 可关闭延迟
Object lock = new Object();
synchronized (lock) {
    // 首次进入：匿名偏向 → 偏向当前线程
}
// 退出同步块后，Mark Word仍保留线程ID（不会降级）
```

**Android特殊性：** Android ART在Android 7.0+默认关闭了偏向锁（因为移动端线程竞争通常更频繁，偏向锁的撤销开销大于收益）。

#### 1.3 轻量级锁（Lightweight Locking / 自旋锁）

**获取流程（以HotSpot为例）：**

1. 在当前线程栈帧中创建**Lock Record**（包含 displaced mark word 和指向锁对象的指针）
2. 通过CAS操作将锁对象的Mark Word替换为指向Lock Record的指针
3. CAS成功 → 获取轻量级锁成功，Mark Word最后2bit变为`00`
4. CAS失败 → 检查Mark Word是否已指向当前线程的Lock Record（重入情况）→ 如果是则在Lock Record中设置displaced mark word为NULL表示重入计数
5. 否则发生竞争 → 自旋等待（自适应自旋）

**自适应自旋（Adaptive Spinning）：** JVM根据上次在同一锁上的自旋时间动态调整自旋次数。如果之前自旋成功过，则允许更长的自旋；如果自旋很少成功，则可能直接放弃自旋升级为重量级锁。

```java
// 轻量级锁典型场景：两个线程交替执行同步块
Object lock = new Object();
// 线程A进入
synchronized (lock) { /* A持有轻量级锁 */ }
// 线程B紧接着进入（此时A已释放），仍为轻量级锁
synchronized (lock) { /* B获取轻量级锁 */ }
```

#### 1.4 重量级锁（Heavyweight Lock）

当自旋等待的线程数超过阈值（默认10），或自旋次数达到上限，或一个线程在持有锁的同时被阻塞，锁膨胀为重量级锁。重量级锁依赖操作系统的**互斥量（Mutex）**，会导致线程挂起/唤醒的用户态-内核态切换。

每个Java对象关联一个 **ObjectMonitor**（由C++实现），核心结构：

```cpp
class ObjectMonitor {
    void*   _header;        // displaced mark word
    int     _count;         // 重入计数
    void*   _owner;         // 持有锁的线程
    void*   _WaitSet;       // wait()的线程等待队列
    void*   _EntryList;     // 阻塞等待锁的线程队列
    void*   _cxq;           // 竞争队列（Contention Queue）
    // ...
};
```

线程获取锁失败后，被放入`_cxq`或`_EntryList`，通过`park()`挂起自身。当持有锁的线程释放锁时，从`_EntryList`中唤醒一个线程。

---

### 2. ReentrantLock的公平锁 vs 非公平锁 和 AQS实现

#### 2.1 公平锁 vs 非公平锁

ReentrantLock内部通过`Sync`（继承自`AbstractQueuedSynchronizer`，AQS）实现锁语义，有两个子类：`FairSync`（公平锁）和 `NonfairSync`（非公平锁）。

| 维度 | 公平锁 (FairSync) | 非公平锁 (NonfairSync) |
|------|-------------------|------------------------|
| **获取策略** | 先到先得，FIFO队列 | 新来的线程先尝试CAS抢占 |
| **lock()实现** | 直接调用acquire(1) | 先CAS尝试获取锁，失败后才排队 |
| **性能** | 较差（更多线程切换） | 更高吞吐量（减少上下文切换） |
| **公平性** | 严格FIFO，无饥饿 | 可能导致某些线程长期饥饿 |
| **默认** | 否 | **是（ReentrantLock默认非公平）** |

```java
// 非公平锁（默认）
ReentrantLock nonfairLock = new ReentrantLock();
// 公平锁
ReentrantLock fairLock = new ReentrantLock(true);

// 非公平锁的lock()源码简析（NonfairSync）：
// final void lock() {
//     if (compareAndSetState(0, 1))   // ① 先插队CAS
//         setExclusiveOwnerThread(Thread.currentThread());
//     else
//         acquire(1);                 // ② 失败则排队
// }

// 公平锁的lock()源码简析（FairSync）：
// final void lock() {
//     acquire(1);                     // ③ 直接排队
// }
// tryAcquire() 中会额外检查 hasQueuedPredecessors()
```

**公平锁的 `hasQueuedPredecessors()` 检测：**

```java
public final boolean hasQueuedPredecessors() {
    Node h = head, s;
    return h != t &&                      // 队列非空
        ((s = h.next) == null ||          // 头节点后继为空
         s.thread != Thread.currentThread()); // 第一个等待者不是当前线程
}
```

只有当前线程是队列头部元素时，公平锁才允许获取，保证了严格的FIFO。

#### 2.2 AQS（AbstractQueuedSynchronizer）核心实现

AQS是JUC包的基石，基于**CLH变体队列**实现。核心就是一个volatile的int `state` + 一个FIFO双向链表（CLH队列的变体）。

```
   AQS核心结构：

   state (volatile int)
   ├── 0 → 锁未被持有
   ├── 1 → 锁被独占
   └── n → 重入n次 (ReentrantLock)

   CLH变体队列（双向链表）：
   head (虚拟节点) → Node₁ → Node₂ → Node₃ (tail)
                    线程A    线程B    线程C
                    (排队)   (排队)   (排队)
```

**Node节点结构：**

```java
static final class Node {
    volatile int waitStatus;     // SIGNAL(-1)/CANCELLED(1)/CONDITION(-2)/PROPAGATE(-3)
    volatile Node prev;          // 前驱节点
    volatile Node next;          // 后继节点
    volatile Thread thread;      // 等待的线程
    Node nextWaiter;             // Condition队列的下一个节点
}
```

**AQS的acquire()流程（独占模式）：**

```java
public final void acquire(int arg) {
    if (!tryAcquire(arg) &&                    // ① 尝试快速获取
        acquireQueued(addWaiter(Node.EXCLUSIVE), arg)) // ② 入队+自旋
        selfInterrupt();                       // ③ 自我中断补偿
}
```

**addWaiter()：** 将当前线程包装成Node节点，CAS插入队尾。

**acquireQueued()：** 节点入队后进入死循环：
- 如果前驱是head → 再次tryAcquire()
- tryAcquire失败 → `shouldParkAfterFailedAcquire()` 将前驱waitStatus设为SIGNAL，然后`parkAndCheckInterrupt()`调用`LockSupport.park(this)`挂起

**release()流程：**

```java
public final boolean release(int arg) {
    if (tryRelease(arg)) {                     // ① 尝试释放
        Node h = head;
        if (h != null && h.waitStatus != 0)
            unparkSuccessor(h);                // ② 唤醒后继节点
        return true;
    }
    return false;
}
```

`unparkSuccessor()`找到head的后继有效节点，调用`LockSupport.unpark(s.thread)`唤醒。

---

### 3. ReentrantReadWriteLock读写锁原理和锁降级

#### 3.1 读写锁设计原理

ReentrantReadWriteLock内部同样基于AQS，将32位的`state`高低16位拆分使用：

```
state (int 32位)：
┌──────────────────────┬──────────────────────┐
│   高16位：读锁计数    │   低16位：写锁计数    │
│   (sharedCount)      │   (exclusiveCount)   │
└──────────────────────┴──────────────────────┘
```

通过 `Sync`（继承AQS）的两个子类 `FairSync` / `NonfairSync` 分别实现公平和非公平策略。

**锁模式：**

| 模式 | AQS方法 | 说明 |
|------|---------|------|
| **写锁（WriteLock）** | `tryAcquire(int)` / `tryRelease(int)` | 独占模式，与其他读写互斥 |
| **读锁（ReadLock）** | `tryAcquireShared(int)` / `tryReleaseShared(int)` | 共享模式，读-读可并发 |

**写锁获取（tryAcquire）：**

```java
protected final boolean tryAcquire(int acquires) {
    Thread current = Thread.currentThread();
    int c = getState();
    int w = exclusiveCount(c); // 低16位
    if (c != 0) {
        // state != 0，说明有线程持锁
        // 情况1：w==0 → 有读锁持锁 → 写锁获取失败
        // 情况2：w!=0，但持锁者不是自己 → 写锁获取失败
        if (w == 0 || current != getExclusiveOwnerThread())
            return false;
        // 情况3：写锁重入
        if (w + exclusiveCount(acquires) > MAX_COUNT)
            throw new Error("Maximum lock count exceeded");
        setState(c + acquires);
        return true;
    }
    // state==0，无锁状态
    // 非公平锁：直接CAS(state, 0, 1)
    // 公平锁：需检查hasQueuedPredecessors()
    if (writerShouldBlock() || !compareAndSetState(c, c + acquires))
        return false;
    setExclusiveOwnerThread(current);
    return true;
}
```

**读锁获取（tryAcquireShared）：**

```java
protected final int tryAcquireShared(int unused) {
    Thread current = Thread.currentThread();
    int c = getState();
    // 如果有写锁且不是当前线程持写锁 → 失败
    if (exclusiveCount(c) != 0 &&
        getExclusiveOwnerThread() != current)
        return -1;
    // 读锁获取：CAS增加高16位
    int r = sharedCount(c);
    if (!readerShouldBlock() && r < MAX_COUNT &&
        compareAndSetState(c, c + SHARED_UNIT)) { // SHARED_UNIT = 1<<16
        // ... 更新ThreadLocal的HoldCounter
        return 1;
    }
    return fullTryAcquireShared(current); // 自旋CAS
}
```

**HoldCounter机制：** 读写锁为每个线程维护了一个`HoldCounter`（通过ThreadLocal），用于记录该线程持有的读锁重入次数。数据结构为`ThreadLocalHoldCounter`继承自`ThreadLocal<HoldCounter>`，确保每个线程在读锁重入释放时正确递减计数。

#### 3.2 锁降级（Lock Downgrading）

锁降级指的是 **持有写锁的线程 → 先获取读锁 → 再释放写锁**，从而将写锁降级为读锁，保证数据可见性的连续性。

```java
ReentrantReadWriteLock rwLock = new ReentrantReadWriteLock();
ReadWriteLock.ReadLock readLock = rwLock.readLock();
ReadWriteLock.WriteLock writeLock = rwLock.writeLock();
Map<String, Object> cache = new HashMap<>();

// 锁降级的标准写法：
writeLock.lock();
try {
    cache.put("key", computeValue());  // 更新数据
    readLock.lock();                   // ① 在释放写锁前获取读锁
} finally {
    writeLock.unlock();                // ② 释放写锁，降级为读锁
}
// 此时仍持有读锁，可以安全读取刚写入的数据
try {
    return cache.get("key");
} finally {
    readLock.unlock();                 // ③ 最终释放读锁
}
```

**为什么需要锁降级？** 如果在释放写锁后、获取读锁前，有其他线程获取了写锁并修改了数据，当前线程再读到的就不是自己刚写的值了（失去可见性保证）。

**锁升级（读→写）不存在：** ReentrantReadWriteLock **不支持锁升级**。如果持有读锁时尝试获取写锁，会导致死锁——因为读锁未被完全释放时写锁无法获取，而读锁又等待写锁成功。

---

### 4. 死锁的4个必要条件和排查方法

#### 4.1 死锁的定义与4个必要条件

死锁（Deadlock）是指两个或多个线程互相持有对方所需要的资源，导致所有线程都无法继续执行。

死锁发生的4个**必要条件**（缺一不可，破坏任一即可预防）：

| 条件 | 说明 | 破坏方式 |
|------|------|----------|
| **1. 互斥条件** | 资源一次只能被一个线程持有 | 使用无锁数据结构（AtomicReference、ConcurrentHashMap）。但很多资源天然互斥，难以完全消除 |
| **2. 持有并等待** | 线程持有资源的同时等待其他资源 | 一次性申请所有需要的资源（`synchronized`嵌套改为统一锁），或设置超时（`tryLock(timeout)`） |
| **3. 不可剥夺** | 线程持有的资源不能被强制剥夺 | `Lock.lockInterruptibly()` 允许响应中断释放锁；`tryLock()` 获取失败直接放弃 |
| **4. 循环等待** | 线程间形成资源等待环路 | **按固定顺序获取锁**（Lock Ordering）——这是最实用的预防策略 |

```java
// 死锁典型代码：
// 线程A：先锁lock1，再锁lock2
// 线程B：先锁lock2，再锁lock1
Object lock1 = new Object();
Object lock2 = new Object();

// 线程A
synchronized (lock1) {
    Thread.sleep(100);
    synchronized (lock2) { /* 永远等不到 */ }
}

// 线程B
synchronized (lock2) {
    Thread.sleep(100);
    synchronized (lock1) { /* 永远等不到 */ }
}
```

#### 4.2 死锁排查方法

**方法一：jstack（最常用）**

```bash
# 1. 找到Java进程PID
jps -l
# 2. 打印线程堆栈（自动检测死锁）
jstack <PID>
# 3. 或导出完整dump
jstack -l <PID> > thread_dump.txt
```

jstack会**自动检测死锁**并在输出末尾明确标记：

```
Found one Java-level deadlock:
=============================
"Thread-1":
  waiting to lock monitor 0x00007f8e3c004e28 (object 0x000000076b5c8c88, a java.lang.Object),
  which is held by "Thread-0"
"Thread-0":
  waiting to lock monitor 0x00007f8e3c0062c8 (object 0x000000076b5c8c98, a java.lang.Object),
  which is held by "Thread-1"
```

**方法二：Android Studio Profiler /  stuck thread检测**

Android中，ANR（Application Not Responding）通常与主线程阻塞有关。排查时关注：

```bash
# adb 导出线程信息
adb shell kill -3 <PID>          # 输出到logcat
adb shell am trace-ipc stop       # 分析IPC阻塞
adb shell dumpsys activity services  # 查看Service超时
```

Android Profiler中查看CPU → Threads视图，可直观看到线程状态（Running / Sleeping / Waiting / Blocked）。

**方法三：代码层面预防**

```java
// 1. tryLock超时机制
if (lock1.tryLock(500, TimeUnit.MILLISECONDS)) {
    try {
        if (lock2.tryLock(500, TimeUnit.MILLISECONDS)) {
            try { /* 业务逻辑 */ }
            finally { lock2.unlock(); }
        }
    } finally { lock1.unlock(); }
}

// 2. Lock Ordering：统一按照hashCode排序获取锁
int hash1 = System.identityHashCode(lock1);
int hash2 = System.identityHashCode(lock2);
Object firstLock  = hash1 < hash2 ? lock1 : lock2;
Object secondLock = hash1 < hash2 ? lock2 : lock1;

// 3. 使用StampedLock（JDK8+）替代ReadWriteLock
//    StampedLock提供乐观读，不阻塞写锁，减少死锁可能性
```

---

### 5. LockSupport.park/unpark 与 wait/notify 的差异

`LockSupport` 是JUC锁框架的底层基础设施，AQS中线程的挂起和唤醒全部通过 `LockSupport.park()/unpark()` 实现。

| 维度 | LockSupport.park/unpark | Object.wait/notify |
|------|------------------------|---------------------|
| **使用前提** | 无需持有任何锁 | 必须在 synchronized 块内调用 |
| **许可机制** | 基于**二元许可（permit）**，最多1个 | 基于**等待集（WaitSet）** |
| **唤醒顺序** | unpark可以先于park调用（预发许可） | notify必须先于wait调用才会被唤醒 |
| **精准唤醒** | unpark(Thread) 精准唤醒指定线程 | notify() 随机唤醒一个，notifyAll() 唤醒全部 |
| **中断响应** | park()可响应中断但不抛异常 | wait()响应中断并抛出InterruptedException |
| **虚假唤醒** | 不会（底层基于POSIX信号量） | 可能发生，需while循环检查条件 |
| **底层实现** | Unsafe.park() → pthread_cond_wait | JVM内部的ObjectMonitor |

**核心特性：permit许可机制**

```java
// LockSupport.permit 是一个二元信号量（0/1）
// park()：消耗一个permit，如果permit==0则阻塞
// unpark()：发放一个permit，如果permit已经是1则不做任何事（不能累积）

// 示例1：unpark先于park调用 —— 完全合法
LockSupport.unpark(thread);  // 发放permit，此时permit=1
LockSupport.park();           // 消费permit，立即返回，不会阻塞！

// 示例2：多次unpark不会累加
LockSupport.unpark(thread);  // permit=1
LockSupport.unpark(thread);  // permit 仍然是 1（饱和上限）
LockSupport.park();           // 消费permit，permit=0
LockSupport.park();           // 阻塞！permit已耗尽
```

**park的三种变体：**

```java
LockSupport.park();                    // 无限等待
LockSupport.parkNanos(long nanos);     // 等待指定纳秒数
LockSupport.parkUntil(long deadline);  // 等待至指定绝对时间
```

**wait/notify的坑：**

```java
// 错误示例：wait/notify必须在同步块内
Object lock = new Object();
lock.wait();  // ❌ IllegalMonitorStateException！

// 正确：（但notify先于wait执行时，wait会永久阻塞）
synchronized (lock) {
    lock.wait();  // 如果notify已执行过，此线程永久挂起
}

// LockSupport无此问题：
LockSupport.unpark(Thread.currentThread()); // 预发许可
LockSupport.park();                          // 立即返回 ✅
```

---

## 二、底层原理层：Mark Word与AQS数据结构

### 2.1 Mark Word的锁状态标志位详解

Java对象头（以64位JVM为例，忽略压缩指针的情况）共128位：

```
┌──────────────────────────────────┬──────────┐
│         Mark Word (64 bits)      │ Klass Pointer
├──────────────────────────────────┤ (64 bits) │
│ 锁标记位在Mark Word的最后3位：    │
│  biased_lock(1bit) + lock(2bit)  │
└──────────────────────────────────┴──────────┘
```

**各锁状态下的Mark Word布局（64位JVM）：**

| 锁状态 | biased_lock | lock | 前61位内容 |
|--------|------------|------|-----------|
| **无锁（normal）** | 0 | 01 | unused:25 \| identity_hashcode:31 \| age:4 \| 0 \| 01 |
| **偏向锁（biased）** | 1 | 01 | thread:54 \| epoch:2 \| age:4 \| 1 \| 01 |
| **轻量级锁** | - | 00 | ptr_to_lock_record:62 \| 00 |
| **重量级锁** | - | 10 | ptr_to_heavyweight_monitor:62 \| 10 |
| **GC标记** | - | 11 | forward_ptr:62 \| 11 |

**关键细节：**

- **hashCode与偏向锁的互斥**：如果一个对象计算过 `identityHashCode()`，就无法进入偏向锁状态（因为hashCode需要存储在Mark Word中，而偏向锁状态下Mark Word存的是线程ID）。调用hashCode时如果对象正处于偏向锁，会触发偏向锁撤销升级为轻量级锁。
- **age（分代年龄）**：4位，最大值15，恰好对应CMS/G1中对象晋升老年代的阈值（`-XX:MaxTenuringThreshold`默认15）。
- **轻量级锁重入**：每次重入，栈中新增一个Lock Record，displaced mark word设为NULL（第一个Lock Record存放真实displaced mark word）。

### 2.2 AQS的CLH变体队列和state状态

AQS使用的队列是 **CLH（Craig, Landin, and Hagersten）锁队列的变体**。原始CLH是单向链表+自旋等待，AQS改为了双向链表+阻塞等待。

```
   AQS CLH变体队列结构：

   head                        tail
    ↓                           ↓
   [Node₀]  ←→  [Node₁]  ←→  [Node₂]
   (空节点)      threadA       threadB
   ws=0          ws=SIGNAL     ws=0
                 (等待被唤醒)

   队列操作：
   - 入队（enq）：CAS设置tail指针
   - 出队：head后移（head = head.next）
   - 唤醒：从tail向前搜索有效的后继节点（因可能发生取消）
```

**Node.waitStatus的5种取值：**

| waitStatus | 值 | 含义 |
|-----------|-----|------|
| **0** | 0 | 初始状态 |
| **SIGNAL** | -1 | 后继节点需要被唤醒，当前节点释放锁时必须unpark后继 |
| **CONDITION** | -2 | 节点在Condition等待队列中 |
| **PROPAGATE** | -3 | 共享模式下，releaseShared需要传播到后续节点 |
| **CANCELLED** | 1 | 节点因超时或中断被取消 |

**为什么唤醒时从tail向前遍历？** `unparkSuccessor()`中从tail向前搜索第一个有效的后继节点，而不是直接用head.next。原因是并发入队时`prev`指针的赋值（`node.prev = t`）发生在CAS成功之前，而`next`的赋值（`t.next = node`）发生在CAS成功之后，存在一个极短的时间窗口`next`为null。向前遍历能保证不遗漏。

### 2.3 ReentrantReadWriteLock的Sync内部结构

```java
abstract static class Sync extends AbstractQueuedSynchronizer {
    // 共享移位数：16
    static final int SHARED_SHIFT   = 16;
    // 读锁计数单位：1 << 16 = 65536
    static final int SHARED_UNIT    = (1 << SHARED_SHIFT);
    // 读写最大计数：65535
    static final int MAX_COUNT      = (1 << SHARED_SHIFT) - 1;
    // 写锁掩码：低16位全1
    static final int EXCLUSIVE_MASK = (1 << SHARED_SHIFT) - 1;

    // 获取读锁计数（高16位）
    static int sharedCount(int c)    { return c >>> SHARED_SHIFT; }
    // 获取写锁计数（低16位）
    static int exclusiveCount(int c) { return c & EXCLUSIVE_MASK; }

    // 每个线程的读锁计数
    private transient ThreadLocalHoldCounter readHolds;
    // 最后一个获取读锁的线程的计数（缓存，减少ThreadLocal查找）
    private transient HoldCounter cachedHoldCounter;
    // 第一个获取读锁的线程
    private transient Thread firstReader;
    // 第一个获取读锁的线程的计数
    private transient int firstReaderHoldCount;
}
```

**读锁并发获取的关键优化：**

1. **firstReader/firstReaderHoldCount**：第一个读线程的重入计数直接存储在Sync中，避免ThreadLocal查找
2. **cachedHoldCounter**：缓存最后一个获取读锁的线程的HoldCounter，提高ThreadLocal命中率
3. **fullTryAcquireShared()**：当快速路径CAS失败时，进入完整版本的循环重试

---

## 三、突破层：synchronized锁升级状态机流程图

```
                        ┌─────────────────────────────────────────┐
                        │              对象创建                    │
                        │          Mark Word: 无锁状态            │
                        │        biased_lock=0, lock=01           │
                        └─────────────┬───────────────────────────┘
                                      │
                        ┌─────────────▼───────────────────────────┐
                        │         偏向锁延迟期（4秒）              │
                        │    JVM启动后默认4秒内，对象不启用偏向锁   │
                        └─────────────┬───────────────────────────┘
                                      │
                        ┌─────────────▼───────────────────────────┐
                        │         ❓ 是否启用偏向锁？              │
                        │   -XX:+UseBiasedLocking (默认true)      │
                        │   延迟期已过 + 类未达到批量撤销阈值       │
                        └──┬────────────────────────┬─────────────┘
                           │是                      │否
                ┌──────────▼──────────┐    ┌───────▼──────────────┐
                │   偏向锁（Biased）   │    │    轻量级锁入口       │
                │ biased_lock=1,lock=01│    │ （跳过偏向锁直接CAS） │
                │ [ThreadID|epoch|age] │    └───────┬──────────────┘
                └──────────┬──────────┘            │
                           │                       │
                ┌──────────▼──────────┐            │
                │  线程访问同步块      │            │
                │  Mark Word中ThreadID │            │
                │  == 当前线程？       │            │
                └──┬──────────────┬───┘            │
            是     │              │否               │
                   │              │                │
        ┌──────────▼──────┐  ┌───▼────────────┐   │
        │ 直接进入同步块   │  │ Mark Word      │   │
        │ （零开销 ✅）     │  │ ThreadID==NULL?│   │
        └─────────────────┘  └──┬─────────┬───┘   │
                             是 │         │否      │
                                │         │        │
                    ┌───────────▼──┐ ┌────▼───────▼────────┐
                    │ CAS替换      │ │ ⚡ 偏向锁撤销       │
                    │ ThreadID     │ │ 在SafePoint停止     │
                    └──┬───────┬───┘ │ 原持有线程          │
                 成功  │       │失败 │ 撤销偏向 → 轻量级   │
                       │       │     └────────┬───────────┘
              ┌────────▼──┐ ┌──▼──────────┐   │
              │ 偏向锁获取 │ │ 偏向锁竞争   │   │
              │ 成功 ✅    │ │ → 轻量级锁  │   │
              └───────────┘ └──────┬──────┘   │
                                   │          │
                    ┌──────────────┘          │
                    │                         │
                    ▼                         ▼
        ┌───────────────────────────────────────────────┐
        │          轻量级锁（Lightweight Lock）          │
        │              Mark Word: lock=00               │
        │   指向线程栈中Lock Record的指针                │
        │                                               │
        │  获取流程：                                    │
        │  ① 在线程栈中创建Lock Record（BASIC_LOCK）     │
        │  ② CAS将Mark Word替换为Lock Record指针        │
        │  ③ CAS成功 → 获取轻量级锁 ✅                  │
        │  ④ CAS失败 → 检查是否指向自己（重入）          │
        │       是 → Lock Record设NULL（重入计数）      │
        │       否 → 自旋等待（自适应自旋）              │
        └────────┬──────────────────────────────────────┘
                 │
                 │  自旋失败条件：
                 │  · 自旋次数达到阈值（-XX:PreBlockSpin）
                 │  · 等待的线程数 > CPU核数/2
                 │  · 自适应自旋预测失败率过高
                 │
        ┌────────▼──────────────────────────────────────┐
        │    ⚡ 锁膨胀（Inflate）                         │
        │    轻量级锁 → 重量级锁                         │
        │    创建ObjectMonitor对象                       │
        │    Mark Word指向ObjectMonitor                  │
        └────────┬──────────────────────────────────────┘
                 │
                 ▼
        ┌───────────────────────────────────────────────┐
        │          重量级锁（Heavyweight Lock）           │
        │              Mark Word: lock=10               │
        │    指向ObjectMonitor的指针                     │
        │                                               │
        │  ObjectMonitor结构：                           │
        │  ┌─────────────────────────────────┐          │
        │  │ _owner → 持有锁的线程           │          │
        │  │ _count → 重入计数               │          │
        │  │ _WaitSet → wait()等待队列       │          │
        │  │ _EntryList → 争锁阻塞队列       │          │
        │  │ _cxq → 竞争队列                 │          │
        │  └─────────────────────────────────┘          │
        │                                               │
        │  线程阻塞：pthread_mutex_lock(Mutex)           │
        │  线程唤醒：pthread_cond_signal(条件变量)        │
        │  涉及用户态↔内核态切换，开销大                 │
        └───────────────────────────────────────────────┘

    【关键原则】
    · 锁升级是单向的：偏向→轻量→重量，不可逆
    · 偏向锁撤销需要SafePoint（全局STW暂停）
    · 批量重偏向阈值：-XX:BiasedLockingBulkRebiasThreshold=20
    · 批量撤销阈值：-XX:BiasedLockingBulkRevocationThreshold=40
    · Android ART默认关闭偏向锁（Android 7.0+）
```

---

## 四、突破层：ReentrantLock.lock()和unlock()的AQS实现

以下以**非公平锁（NonfairSync）**为例，展示完整调用链：

### 4.1 lock() 完整调用链

```java
// ===== Step 1: ReentrantLock.lock() =====
public void lock() {
    sync.lock();  // → 调用 NonfairSync.lock()
}

// ===== Step 2: NonfairSync.lock() =====
static final class NonfairSync extends Sync {
    final void lock() {
        // ① 第一次CAS抢占，尝试直接获取锁（插队）
        if (compareAndSetState(0, 1))
            setExclusiveOwnerThread(Thread.currentThread());
        else
            // ② 抢占失败，走标准AQS获取流程
            acquire(1);
    }
}

// ===== Step 3: AQS.acquire() =====
public final void acquire(int arg) {
    // ③ tryAcquire → 再次尝试获取（处理重入等）
    // ④ addWaiter → 创建Node节点入队
    // ⑤ acquireQueued → 自旋等待或park
    if (!tryAcquire(arg) &&
        acquireQueued(addWaiter(Node.EXCLUSIVE), arg))
        selfInterrupt();
}

// ===== Step 4: Sync.tryAcquire()（非公平锁版） =====
protected final boolean tryAcquire(int acquires) {
    return nonfairTryAcquire(acquires);
}

final boolean nonfairTryAcquire(int acquires) {
    final Thread current = Thread.currentThread();
    int c = getState();         // 读取volatile state
    if (c == 0) {
        // state==0，锁未被持有 → CAS抢占
        if (compareAndSetState(0, acquires)) {
            setExclusiveOwnerThread(current);
            return true;
        }
    }
    else if (current == getExclusiveOwnerThread()) {
        // 当前线程已持有锁 → 重入
        int nextc = c + acquires;
        if (nextc < 0) // overflow
            throw new Error("Maximum lock count exceeded");
        setState(nextc);
        return true;
    }
    return false; // 获取失败，需排队
}

// ===== Step 5: AQS.addWaiter(Node.EXCLUSIVE) =====
private Node addWaiter(Node mode) {
    Node node = new Node(Thread.currentThread(), mode);
    Node pred = tail;
    if (pred != null) {
        node.prev = pred;
        if (compareAndSetTail(pred, node)) {
            pred.next = node;   // 注意：prev在CAS前赋值，next在CAS后赋值
            return node;
        }
    }
    enq(node);  // 队列为空或CAS失败 → 自旋入队
    return node;
}

private Node enq(final Node node) {
    for (;;) {
        Node t = tail;
        if (t == null) {
            // 队列为空 → 初始化虚拟head
            if (compareAndSetHead(new Node()))
                tail = head;
        } else {
            node.prev = t;
            if (compareAndSetTail(t, node)) {
                t.next = node;
                return t;
            }
        }
    }
}

// ===== Step 6: AQS.acquireQueued() =====
final boolean acquireQueued(final Node node, int arg) {
    boolean failed = true;
    try {
        boolean interrupted = false;
        for (;;) {
            final Node p = node.predecessor();
            // ⑦ 如果前驱是head → 尝试获取锁
            if (p == head && tryAcquire(arg)) {
                setHead(node);  // 将自己设为新head
                p.next = null;  // help GC
                failed = false;
                return interrupted;
            }
            // ⑧ 检查是否需要park
            if (shouldParkAfterFailedAcquire(p, node) &&
                parkAndCheckInterrupt())
                interrupted = true;   // 记录中断，但不退出循环
        }
    } finally {
        if (failed)
            cancelAcquire(node);
    }
}

// ===== Step 7: shouldParkAfterFailedAcquire() =====
private static boolean shouldParkAfterFailedAcquire(Node pred, Node node) {
    int ws = pred.waitStatus;
    if (ws == Node.SIGNAL)
        // 前驱已经设置了SIGNAL → 可以安全park
        return true;
    if (ws > 0) {
        // 前驱被取消 → 跳过所有被取消的节点
        do {
            node.prev = pred = pred.prev;
        } while (pred.waitStatus > 0);
        pred.next = node;
    } else {
        // 将前驱的waitStatus设置为SIGNAL
        compareAndSetWaitStatus(pred, ws, Node.SIGNAL);
    }
    return false; // 返回false，再次进入acquireQueued循环
}

// ===== Step 8: parkAndCheckInterrupt() =====
private final boolean parkAndCheckInterrupt() {
    LockSupport.park(this);  // ⑨ 底层调用 Unsafe.park() → pthread_cond_wait
    return Thread.interrupted(); // 返回中断状态并清除
}
```

**关键设计要点：**

1. **两次tryAcquire**：NonfairSync中CAS一次 + acquire()中tryAcquire一次，共两次抢占机会（非公平性体现）
2. **head节点永远是空节点**：`setHead(node)`将节点thread置null，保留waitStatus供后续唤醒使用
3. **prev/next赋值的非原子性**：prev在CAS tail之前赋值，next在CAS tail之后赋值。这导致从head向后遍历时可能丢失刚入队的节点，所以`unparkSuccessor()`选择从tail向前遍历

### 4.2 unlock() 完整调用链

```java
// ===== Step 1: ReentrantLock.unlock() =====
public void unlock() {
    sync.release(1);  // → 调用 AQS.release()
}

// ===== Step 2: AQS.release() =====
public final boolean release(int arg) {
    if (tryRelease(arg)) {
        Node h = head;
        if (h != null && h.waitStatus != 0)
            // 唤醒head的后继节点
            unparkSuccessor(h);
        return true;
    }
    return false;
}

// ===== Step 3: Sync.tryRelease() =====
protected final boolean tryRelease(int releases) {
    int c = getState() - releases;
    // 只有锁持有者才能释放
    if (Thread.currentThread() != getExclusiveOwnerThread())
        throw new IllegalMonitorStateException();
    boolean free = false;
    if (c == 0) {
        // state归零 → 完全释放锁
        free = true;
        setExclusiveOwnerThread(null);
    }
    setState(c);  // 注意：先清owner再写state（volatile写保证可见性）
    return free;
}

// ===== Step 4: AQS.unparkSuccessor() =====
private void unparkSuccessor(Node node) {
    int ws = node.waitStatus;
    if (ws < 0)
        compareAndSetWaitStatus(node, ws, 0);

    Node s = node.next;
    // s为null或s.waitStatus > 0（CANCELLED）
    if (s == null || s.waitStatus > 0) {
        s = null;
        // 从tail向前遍历，找到最前面且未取消的节点
        for (Node t = tail; t != null && t != node; t = t.prev)
            if (t.waitStatus <= 0)
                s = t;
    }
    if (s != null)
        LockSupport.unpark(s.thread);  // ⑤ 唤醒等待线程
}
```

**unlock到线程重新运行的完整流程：**

```
Thread A (unlock)
    │
    ├→ tryRelease() state: 1→0, owner: ThreadA→null
    ├→ unparkSuccessor(head)
    │      └→ LockSupport.unpark(ThreadB)
    │
    ▼
Thread B (被唤醒)
    │  (从 acquireQueued 的 parkAndCheckInterrupt 处恢复)
    ├→ 返回 acquireQueued 循环
    ├→ p == head && tryAcquire(1) → 成功！
    ├→ setHead(node) → ThreadB成为新head
    └→ 返回 → 继续执行业务代码
```

### 4.3 公平锁 vs 非公平锁的核心差异代码

```java
// ============ 公平锁 FairSync ============
static final class FairSync extends Sync {
    final void lock() {
        acquire(1);  // 直接排队，不尝试CAS抢占
    }

    protected final boolean tryAcquire(int acquires) {
        final Thread current = Thread.currentThread();
        int c = getState();
        if (c == 0) {
            // ⚡ 关键差异：检查是否有前驱等待节点
            if (!hasQueuedPredecessors() &&
                compareAndSetState(0, acquires)) {
                setExclusiveOwnerThread(current);
                return true;
            }
        }
        else if (current == getExclusiveOwnerThread()) {
            int nextc = c + acquires;
            if (nextc < 0)
                throw new Error("Maximum lock count exceeded");
            setState(nextc);
            return true;
        }
        return false;
    }
}

// ============ 非公平锁 NonfairSync ============
static final class NonfairSync extends Sync {
    final void lock() {
        // ⚡ 关键差异：先CAS抢占
        if (compareAndSetState(0, 1))
            setExclusiveOwnerThread(Thread.currentThread());
        else
            acquire(1);
    }

    protected final boolean tryAcquire(int acquires) {
        return nonfairTryAcquire(acquires);  // 不检查 hasQueuedPredecessors()
    }
}
```

**非公平锁的"非公平"体现在两个时机：**

1. `lock()`中直接CAS抢锁——新来的线程可能比等待队列中线程更快获取锁
2. `tryAcquire()`中不检查`hasQueuedPredecessors()`——被唤醒的线程和刚到达的线程公平竞争，谁先CAS成功谁获得锁

---

## 五、实战层：用读写锁优化缓存访问的性能

### 5.1 问题场景

一个典型的缓存读写场景：90%的操作为读取，10%为写入。如果使用`synchronized`或`ReentrantLock`，读操作也会互斥——即使读操作之间不需要互斥。

```java
// ❌ 全部互斥——读-读也被阻塞
class SyncCache<K, V> {
    private final Map<K, V> map = new HashMap<>();
    public synchronized V get(K key) {
        return map.get(key);
    }
    public synchronized void put(K key, V value) {
        map.put(key, value);
    }
}
// 10个线程同时get → 串行执行，吞吐量极差
```

### 5.2 读写锁优化方案

```java
class ReadWriteCache<K, V> {
    private final Map<K, V> map = new HashMap<>();
    private final ReentrantReadWriteLock rwLock = new ReentrantReadWriteLock();
    private final Lock readLock  = rwLock.readLock();
    private final Lock writeLock = rwLock.writeLock();

    // ===== 读操作：使用读锁，多个线程可并发读取 =====
    public V get(K key) {
        readLock.lock();
        try {
            return map.get(key);
        } finally {
            readLock.unlock();
        }
    }

    // ===== 写操作：使用写锁，独占访问 =====
    public void put(K key, V value) {
        writeLock.lock();
        try {
            map.put(key, value);
        } finally {
            writeLock.unlock();
        }
    }

    // ===== 清除缓存：写操作 =====
    public void clear() {
        writeLock.lock();
        try {
            map.clear();
        } finally {
            writeLock.unlock();
        }
    }

    // ===== 带锁降级的复合操作：先读缓存，未命中则计算并写入 =====
    public V computeIfAbsent(K key, Function<K, V> computer) {
        // ① 先用读锁尝试获取
        readLock.lock();
        try {
            V value = map.get(key);
            if (value != null) return value;
        } finally {
            readLock.unlock();
        }

        // ② 读未命中，升级为写锁（经典Double-Check）
        writeLock.lock();
        try {
            V value = map.get(key);  // Double-Check：防止并发写入
            if (value == null) {
                value = computer.apply(key);
                map.put(key, value);
            }
            // ③ 锁降级：获取读锁后释放写锁
            readLock.lock();
        } finally {
            writeLock.unlock();
        }

        // ④ 降级为读锁返回结果
        try {
            return map.get(key);
        } finally {
            readLock.unlock();
        }
    }
}
```

### 5.3 性能对比基准测试思路

```java
// 模拟Benchmark测试（简化版）
public class CacheBenchmark {
    static final int THREAD_COUNT = 16;
    static final int OPERATIONS   = 100_000;
    static final int READ_RATIO   = 90; // 90%读，10%写

    @Test
    public void testThroughput() throws Exception {
        SyncCache<Integer, String> syncCache   = new SyncCache<>();
        ReadWriteCache<Integer, String> rwCache = new ReadWriteCache<>();

        long syncTime = benchmark(syncCache);
        long rwTime   = benchmark(rwCache);

        System.out.printf("synchronized: %d ms\n", syncTime);
        System.out.printf("ReadWriteLock: %d ms (%.1fx improvement)\n",
                rwTime, (double) syncTime / rwTime);
        // 典型结果（16线程，90%读）：
        // synchronized: 3200 ms
        // ReadWriteLock: 850 ms  (3.7x improvement)
    }

    private long benchmark(Object cache) {
        ExecutorService executor = Executors.newFixedThreadPool(THREAD_COUNT);
        long start = System.currentTimeMillis();

        for (int i = 0; i < THREAD_COUNT; i++) {
            executor.submit(() -> {
                Random rnd = new Random();
                for (int j = 0; j < OPERATIONS / THREAD_COUNT; j++) {
                    if (rnd.nextInt(100) < READ_RATIO) {
                        ((ReadWriteCache) cache).get(rnd.nextInt(1000));
                    } else {
                        ((ReadWriteCache) cache).put(rnd.nextInt(1000), "val");
                    }
                }
            });
        }
        executor.shutdown();
        executor.awaitTermination(1, TimeUnit.MINUTES);
        return System.currentTimeMillis() - start;
    }
}
```

### 5.4 StampedLock：读写锁的进一步优化

JDK 8引入的`StampedLock`提供了**乐观读**模式，读操作完全不阻塞写操作：

```java
class StampedCache<K, V> {
    private final Map<K, V> map = new HashMap<>();
    private final StampedLock lock = new StampedLock();

    public V get(K key) {
        // ① 尝试乐观读（获取戳记）
        long stamp = lock.tryOptimisticRead();
        V value = map.get(key);

        // ② 检查戳记是否有效（读期间是否有写操作）
        if (!lock.validate(stamp)) {
            // ③ 乐观读失败 → 升级为悲观读锁
            stamp = lock.readLock();
            try {
                value = map.get(key);
            } finally {
                lock.unlockRead(stamp);
            }
        }
        return value;
    }

    public void put(K key, V value) {
        long stamp = lock.writeLock();
        try {
            map.put(key, value);
        } finally {
            lock.unlockWrite(stamp);
        }
    }
}
```

**StampedLock vs ReentrantReadWriteLock：**

| 特性 | ReentrantReadWriteLock | StampedLock |
|------|----------------------|-------------|
| **重入性** | ✅ 支持重入 | ❌ 不支持重入 |
| **Condition** | ✅ 支持 | ❌ 不支持 |
| **乐观读** | ❌ 不支持 | ✅ 支持 |
| **锁升级** | ❌ 不支持 | ✅ tryConvertToWriteLock() |
| **性能** | 一般 | 高（乐观读零开销） |
| **适用场景** | 重入需求 + 读写均衡 | 读多写少极端的缓存 |

---

## 六、常见追问与陷阱

### Q1: synchronized锁升级过程中，如果hashCode已经生成会怎样？

偏向锁存储线程ID需要占用Mark Word中hashCode的位置。已生成hashCode的对象无法进入偏向锁状态，直接从轻量级锁开始。如果在偏向锁状态下调用`hashCode()`，会触发偏向锁撤销。

### Q2: ReentrantReadWriteLock中的"写锁饥饿"问题

在读多写少场景下，写线程可能永远获取不到锁——因为只要有读线程持有读锁，写锁就无法获取。JDK 8的`StampedLock`也不能完全解决这个问题，真正公平的策略只能通过`ReentrantReadWriteLock(true)`公平模式实现（但代价是性能大幅下降）。

### Q3: `synchronized` 和 `ReentrantLock` 如何选型？

| 场景 | 推荐 |
|------|------|
| 简单同步块、代码清晰度优先 | `synchronized` |
| 需要tryLock超时、可中断获取 | `ReentrantLock` |
| 需要Condition（多个条件队列） | `ReentrantLock` |
| 读多写少缓存 | `ReentrantReadWriteLock` / `StampedLock` |
| 极致性能 + 读多写少 + 无重入 | `StampedLock` |

### Q4: `LockSupport.park()` 被中断后会怎样？

`park()`被中断后**不会抛出InterruptedException**，而是静默返回。调用者需要**主动检查**中断状态（`Thread.interrupted()`）。AQS的`acquireQueued()`正是这样处理的——检测到中断后标记位`interrupted = true`，但继续循环等待锁，最后通过`selfInterrupt()`补偿。

---

## 参考资源

- [OpenJDK: Synchronization - Biased Locking](https://wiki.openjdk.org/display/HotSpot/Synchronization)
- [AQS Source Code - java.util.concurrent.locks.AbstractQueuedSynchronizer](https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/java/util/concurrent/locks/AbstractQueuedSynchronizer.java)
- [Java并发编程的艺术 - 方腾飞](https://book.douban.com/subject/26591326/)
- [Android Developer - Threading on Android](https://developer.android.com/topic/performance/threads)
