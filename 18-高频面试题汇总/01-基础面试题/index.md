# 01 基础面试题

> 面向 30k+ 岗位的基础题深度解析，覆盖 Android 核心技术栈中最高频的面试问题。每道题按六层递进结构展开，从面试现场还原到加分扩展，帮你建立体系化答题框架。

---

## 目录

1. [Activity 启动模式](#1-activity-启动模式)
2. [Handler 消息机制原理](#2-handler-消息机制原理)
3. [HashMap 扩容机制](#3-hashmap-扩容机制)
4. [View 绘制流程](#4-view-绘制流程)
5. [Binder IPC 机制](#5-binder-ipc-机制)
6. [内存泄漏场景分析](#6-内存泄漏场景分析)
7. [Glide 三级缓存](#7-glide-三级缓存)
8. [OkHttp 拦截器链](#8-okhttp-拦截器链)
9. [Kotlin 协程原理](#9-kotlin-协程原理)
10. [Jetpack ViewModel 原理](#10-jetpack-viewmodel-原理)
11. [LiveData 数据倒灌问题](#11-livedata-数据倒灌问题)
12. [RecyclerView 四级缓存](#12-recyclerview-四级缓存)
13. [Activity 生命周期与任务栈](#13-activity-生命周期与任务栈)

---

## 1. Activity 启动模式

### 问题

> "说一下 Activity 的四种启动模式，它们分别在什么场景下使用？singleTask 和 singleInstance 的区别是什么？"

### 答题思路

这道题考察三层能力：**概念记忆**（四种模式的定义）→ **场景应用**（知道什么场景选什么模式）→ **底层理解**（Task 栈管理机制）。建议先用一句话概括四种模式的核心区别（是否复用、所在栈），然后逐一举例子说明，最后落脚到 Task 栈模型。

### 标准答案

四种启动模式由 `AndroidManifest.xml` 中的 `android:launchMode` 指定：

**1. standard（标准模式）**

- **行为**：每次启动 Activity 都创建新实例，放入启动它的 Task 栈顶。
- **典型场景**：绝大多数普通页面，如详情页、表单页。
- **示例**：从 A 启动 B（standard），Task 栈变为 A → B；再从 B 启动 B，栈变为 A → B → B（两个 B 实例）。

**2. singleTop（栈顶复用模式）**

- **行为**：如果目标 Activity 已在栈顶，不创建新实例，而是回调 `onNewIntent()`；不在栈顶则创建。
- **典型场景**：消息推送点击通知跳转到已有页面、搜索页面避免重复打开。
- **关键 API**：在 `onNewIntent()` 中获取最新 intent 数据并刷新 UI。

**3. singleTask（栈内复用模式）**

- **行为**：整个 Task 栈内只允许存在一个实例。如果已存在，将其之上的所有 Activity 出栈（clearTop 效果），并回调 `onNewIntent()`；不存在则创建并放到新的或指定的 Task 中。
- **典型场景**：应用主页面（MainActivity）、浏览器主页、WebView 容器页。
- **注意**：配合 `taskAffinity` 可以指定该 Activity 所属的 Task。

**4. singleInstance（单实例模式）**

- **行为**：与 singleTask 类似，但该 Activity 独占一个 Task，且该 Task 中只能有这一个 Activity。其他 Activity 启动时会放到不同的 Task 中。
- **典型场景**：系统级页面（如来电界面）、全局唯一的页面（如 Launcher）。
- **核心区别**：singleTask 可以和其他 Activity 共享 Task，singleInstance 必须独占。

**singleTask vs singleInstance 对比表：**

| 特性 | singleTask | singleInstance |
|-----|-----------|----------------|
| 所在 Task | 可以与其他 Activity 同栈 | 独占一个独立 Task |
| 启动其他 Activity | 其他 Activity 默认加入同一 Task | 其他 Activity 放到不同 Task |
| 典型场景 | 应用主页 | 来电界面、Launcher |

### 加分扩展

- **Intent Flag 补充**：除了清单文件配置，还可以用 `FLAG_ACTIVITY_NEW_TASK`（等效 singleTask）、`FLAG_ACTIVITY_SINGLE_TOP`（等效 singleTop）、`FLAG_ACTIVITY_CLEAR_TOP` 等动态控制。*Intent Flag 优先级高于清单配置*。
- **Task 栈模型**：Android 使用 `ActivityManagerService` 中的 `ActivityStack` 和 `TaskRecord` 管理所有栈。举例说明：微信分享到你的 App 时，AMS 会根据 `taskAffinity` 决定是否新建 Task。
- **onNewIntent 调用时机**：在 `onResume` 之前被调用。如果 Activity 之前被 `onStop` 了，会先走 `onRestart → onStart → onResume`，而 `onNewIntent` 在 `onRestart` 之后、`onResume` 之前。
- **源码关键词**：`ActivityStarter.computeLaunchingTaskFlags()`、`ActivityStack.startActivityLocked()`。

### 常见误区

- ❌ 以为 singleInstance 的 Activity 启动其他 Activity 也会在同一个 Task 中——实际上新 Activity 会进入另一个 Task。
- ❌ 混淆 `taskAffinity` 和 `launchMode`——taskAffinity 决定分配给哪个 Task，launchMode 决定如何分配。
- ❌ 忘记在 singleTop/singleTask 中处理 `onNewIntent`，导致页面数据不刷新。
- ❌ 不知道 `FLAG_ACTIVITY_CLEAR_TOP` 会销毁目标之上的所有 Activity（包括目标本身如果没设置 singleTop）。

---

## 2. Handler 消息机制原理

### 问题

> "Handler 的消息机制是怎么工作的？MessageQueue 是如何阻塞和唤醒的？为什么 Looper 不会导致 ANR？"

### 答题思路

这是 Android 面试题中的"必考题"。回答逻辑：**四件套关系**（Handler、Looper、MessageQueue、Message）→ **消息流转**（发送 → 入队 → 轮询 → 分发）→ **阻塞唤醒机制**（epoll）→ **与 ANR 的关系**。

### 标准答案

Handler 机制由四个核心类构成：

**1. Handler**：消息的发送者和处理者。通过 `sendMessage()` / `post()` 将 Message 插入 MessageQueue。

**2. MessageQueue**：以单链表结构组织的消息队列，按 `when`（执行时间）排序。核心方法：
- `enqueueMessage()`：按时间顺序插入消息，可能需要唤醒 Looper。
- `next()`：取下一个可执行消息，如果队列为空或头消息还没到执行时间，通过 `nativePollOnce()` 阻塞等待。

**3. Looper**：消息循环引擎。`loop()` 方法死循环调用 `queue.next()` 取消息，然后分发到 Handler 的 `dispatchMessage()`。

**4. Message**：消息载体，建议通过 `obtain()` 从对象池获取以复用。

**完整流程：**

```
Handler.sendMessage(msg)
  → MessageQueue.enqueueMessage(msg)  // 插入并按时间排序
    → 如果需要唤醒: nativeWake(mPtr)
Looper.loop()
  → MessageQueue.next()
    → nativePollOnce(mPtr, timeoutMillis)  // epoll_wait 阻塞
    → 被唤醒后返回队首 Message
  → msg.target.dispatchMessage(msg)  // msg.target 即发送它的 Handler
    → handleMessage(msg)  // 回调到我们覆写的方法
```

### 加分扩展

**阻塞唤醒机制（Native 层）**：
- MessageQueue 底层使用 Linux **epoll** 机制。初始化时创建 eventfd（或管道），`nativePollOnce` 调用 `epoll_wait` 阻塞。
- 有新消息入队时 `nativeWake` 向 eventfd 写入数据，唤醒 `epoll_wait`。
- *面试金句*：Handler 没有消息时线程挂起在 native 层，不消耗 CPU。当消息到达时 native 层唤醒线程，Java 层继续轮询。

**为什么 Looper.loop() 是死循环但不会 ANR？**
- ANR 是主线程在 5 秒内没有响应输入事件（触摸/按键）或 BroadcastReceiver 10 秒内未执行完毕。
- Looper 的 `loop()` 不是空转轮询——没有消息时线程在 native 层休眠。有消息时立即处理，处理完继续休眠。
- **真正导致 ANR 的是**：在 `handleMessage` 中执行耗时操作，阻塞了后续消息（包括系统输入事件）的处理。

**同步屏障（Sync Barrier）**：
- 通过 `MessageQueue.postSyncBarrier()` 插入一个 target 为 null 的消息。
- `next()` 遇到同步屏障时，只返回异步消息，普通同步消息被阻塞。
- View 的绘制流程利用此机制：`ViewRootImpl.scheduleTraversals()` 发送异步消息，确保绘制优先执行。
- 移除屏障：`MessageQueue.removeSyncBarrier(token)`。

**IdleHandler**：
- 当 MessageQueue 为空时，`next()` 返回前会调用注册的 `IdleHandler.queueIdle()`。
- 典型用途：Activity 启动优化中延迟执行非关键初始化（如 `Looper.myQueue().addIdleHandler{ ... }`）。

### 常见误区

- ❌ 误以为 Handler 只能用于子线程通信——主线程和子线程都可以有 Looper 和 Handler。
- ❌ 忘记在子线程先 `Looper.prepare()` 就创建 Handler——会抛 `"Can't create handler inside thread that has not called Looper.prepare()"`。
- ❌ Message 大量 new 创建导致内存抖动——应使用 `obtain()` 复用。
- ❌ handler.postDelayed 的时间不精确——受前面消息处理耗时的影响，实际延迟 ≥ 指定延迟。

---

## 3. HashMap 扩容机制

### 问题

> "HashMap 的扩容过程是怎样的？为什么扩容因子是 0.75？JDK 1.7 和 1.8 在扩容时有什么改进？"

### 答题思路

先讲清楚数据结构（数组+链表/红黑树）→ 扩容触发条件 → 扩容过程（resize） → 为什么 0.75 → 1.7 vs 1.8 的头插/尾插与死循环问题。Android 面试中特别喜欢问 1.7 的头插死循环。

### 标准答案

**数据结构**：JDK 1.8 中 HashMap = 数组（Node[] table）+ 链表 + 红黑树。
- 默认初始容量 16，最大容量 2^30。
- 当链表长度 ≥ 8 且数组长度 ≥ 64 时，链表转红黑树；当节点数 ≤ 6 时退化回链表。

**扩容触发条件**：
1. 存储元素数量 > `capacity * loadFactor`（默认阈值 = 16 × 0.75 = 12）
2. 链表转红黑树时如果数组长度 < 64，优先扩容而非树化。

**扩容过程（resize）**：

1. **新容量计算**：翻倍（newCap = oldCap << 1），新阈值也翻倍。
2. **数据迁移**：遍历旧桶的每个位置，将节点重新映射到新数组。
   - **单节点**：直接 `newTab[e.hash & (newCap - 1)]`。
   - **链表**：利用扩容后 hash 参与运算的位数多一位的特性，将链表拆分为 loHead（低位）和 hiHead（高位）两条链。
     - 低位留在原索引 j，高位放在 j + oldCap 位置。
   - **红黑树**：同样按高位/低位拆分为两棵树，如果拆分后节点数 ≤ 6 则退化为链表。

**为什么扩容因子是 0.75？**

- 在**时间**和**空间**之间取折中。
- 太小（如 0.5）：空间利用率低，频繁扩容。
- 太大（如 1.0）：冲突概率大增，链表变长，查询退化到 O(n)。
- 泊松分布推导：loadFactor=0.75 时，桶中节点数达到 8 的概率极低（约 0.00000006），这是链表转红黑树阈值设为 8 的数学依据。

### 加分扩展

**JDK 1.7 vs JDK 1.8（高频追问）**：

| 维度 | JDK 1.7 | JDK 1.8 |
|------|---------|---------|
| 插入方式 | 头插法 | 尾插法 |
| 链表结构 | 纯链表 | 链表 + 红黑树 |
| 扩容时的 rehash | 重新计算 hash | hash & oldCap 判断高位 |
| 并发问题 | **可能形成循环链表导致 CPU 100%** | 仍不安全，但不会死循环 |

**1.7 头插法死循环原理**（几乎每次面试都会被追问）：
- 扩容时头插法会反转链表顺序。
- 两个线程同时扩容时，一个线程挂起后另一个完成扩容，原线程恢复后引用关系错乱，形成 A→B→A 的循环链表。
- 后续 get() 或 put() 遍历该链表时进入死循环，CPU 飙升 100%。

**为什么需要 2 的幂次方容量？**
- `index = hash & (capacity - 1)` 等价于 `hash % capacity`，位运算更快。
- 如果不是 2 的幂，`capacity - 1` 的二进制低位不全为 1，某些桶永远不会被使用，分布不均。
- 构造时可传入非 2 的幂，内部 `tableSizeFor()` 会向上取到最近的 2 的幂。

**Android 中的替代方案**：
- `ArrayMap`：双数组实现（int[] mHashes + Object[] mArray），二分查找，适合少量数据（< 1000），内存更省。
- `SparseArray`：int 为 key 的 ArrayMap，避免装箱，专为 Android 优化。

### 常见误区

- ❌ 以为 HashMap 是线程安全的——完全不是。并发场景用 `ConcurrentHashMap` 或 `Collections.synchronizedMap()`。
- ❌ 以为扩容是整表一次性迁移——1.8 中链表/红黑树拆分是渐进式的（但并不等同于 ConcurrentHashMap 的渐进式扩容）。
- ❌ 不知道树化条件有两个——链表长度 ≥ 8 且数组长度 ≥ 64，缺一不可。

---

## 4. View 绘制流程

### 问题

> "说一下 View 的绘制流程，从 setContentView 到屏幕上显示经历了哪些步骤？measure 的 MeasureSpec 是怎么确定的？"

### 答题思路

这道题通常按时间线回答：**setContentView**（DecorView 创建）→ **ViewRootImpl**（连接 WindowManagerService）→ **三大流程**（measure → layout → draw）→ **最终通过 SurfaceFlinger 渲染到屏幕**。

### 标准答案

**1. 初始化阶段**：

```
Activity.setContentView()
  → PhoneWindow.setContentView()
    → installDecor()  // 创建 DecorView
    → mLayoutInflater.inflate(layoutResID, mContentParent)
```

DecorView 是一个 FrameLayout，包含标题栏 + `mContentParent`（即 `android.R.id.content`），我们的布局就被添加到 mContentParent 中。

**2. 挂载阶段（ViewRootImpl）**：

```
ActivityThread.handleResumeActivity()
  → WindowManagerImpl.addView(decorView)
    → WindowManagerGlobal.addView()
      → new ViewRootImpl(context, display)
      → root.setView(decorView, ...)
```

ViewRootImpl 是整个 View 树的"管理者"，负责：
- 与 WMS 通信（Binder IPC）
- 触发绘制流程
- 接收输入事件分发

**3. 三大流程（performTraversals）**：

ViewRootImpl 的 `performTraversals()` 依次调用：

**① Measure（测量）**：
```
performMeasure(childWidthMeasureSpec, childHeightMeasureSpec)
  → mView.measure()  // 从 DecorView 开始
    → onMeasure()
      → 递归 measureChildren()  // 遍历所有子 View
```

核心概念——**MeasureSpec**：
- 是一个 32 位 int，高 2 位是 SpecMode（UNSPECIFIED / EXACTLY / AT_MOST），低 30 位是 SpecSize。
- 子 View 的 MeasureSpec 由**父 View 的 MeasureSpec + 子 View 的 LayoutParams** 决定。

| 父 SpecMode \ 子 LP | EXACTLY（具体值/`match_parent`） | WRAP_CONTENT |
|--------------------|--------------------------------|--------------|
| EXACTLY | EXACTLY（父 size） | AT_MOST（≤ 父 size） |
| AT_MOST | AT_MOST（≤ 父 size） | AT_MOST（≤ 父 size） |
| UNSPECIFIED | UNSPECIFIED | UNSPECIFIED |

**② Layout（布局）**：
```
performLayout()
  → mView.layout(l, t, r, b)
    → onLayout(changed, l, t, r, b)
      → 递归 child.layout()
```

确定 View 的四个顶点位置。自定义 ViewGroup 需要覆写 `onLayout()` 来摆放子 View。

**③ Draw（绘制）**：
```
performDraw()
  → draw(fullRedrawNeeded)
    → drawSoftware()  // 软件绘制
      → mView.draw(canvas)
```

View 的 `draw()` 包含六个步骤：
1. 绘制背景（`drawBackground`）
2. 保存 Canvas 图层（必要时）
3. 绘制内容（`onDraw`）
4. 绘制子 View（`dispatchDraw`）
5. 绘制边缘效果（如 ScrollBar）
6. 绘制装饰（`onDrawForeground`）

**4. 渲染到屏幕**：

- 软件绘制：`drawSoftware()` 通过 Skia 引擎绘制到 Surface 的 Canvas。
- 硬件加速：DisplayList → RenderNode → RenderThread 执行 GPU 渲染。
- 最终通过 `SurfaceFlinger` 合成各 Surface 并送到 FrameBuffer 显示。

### 加分扩展

**requestLayout 与 invalidate 的区别**：

| 方法 | 作用 | 流程 |
|------|------|------|
| requestLayout | 标记需要重新测量和布局 | measure → layout → draw（全流程） |
| invalidate | 仅重绘，不重新测量 | 只走 draw，跳过 measure/layout |

**View.post() 的实现原理**：
- 如果 View 已 attach 到 Window，将 Runnable 放入主线程 MessageQueue（通过 Handler）。
- 如果尚未 attach，放入 `RunQueue` 中，等 `performTraversals` 时再统一 post 到 Handler。
- 这就是为什么在 `onCreate` 中 `view.post()` 也能拿到宽高。

**硬件加速原理**：
- Android 3.0+ 默认开启。将每个 View 的绘制命令存储为 `DisplayList`。
- 当 View 无效时只需更新 DisplayList，待 VSYNC 信号到达时 RenderThread 读取并交给 GPU 绘制。
- 优势：重绘无需重新执行 `onDraw`，直接复用 GPU 缓存。

### 常见误区

- ❌ 在 `onCreate` 中直接获取 View 宽高——此时尚未完成 measure，返回 0。正确方式是 `view.post {}` 或 `ViewTreeObserver`。
- ❌ 用 `invalidate` 期望触发重新测量——不会，只有 `requestLayout` 才会。
- ❌ 混淆 MeasureSpec 和 LayoutParams——MeasureSpec 由父 View 根据 LayoutParams 计算得出，是传递到子 View 的约束。

---

## 5. Binder IPC 机制

### 问题

> "Binder 通信的过程是怎样的？为什么 Binder 只需要一次拷贝？和传统 IPC（管道、共享内存、Socket）相比有什么优势？"

### 答题思路

按通信层次回答：**Java 层（AIDL/Stub/Proxy）** → **Native 层（BpBinder/BBinder）** → **Kernel 驱动层（binder driver）** → 重点解释"一次拷贝"的原因 → 与其他 IPC 对比。

### 标准答案

Binder 是 Android 中基于 C/S 架构的 IPC 机制，四层架构：

**1. Java 层**：开发者通过 AIDL 定义接口，编译生成 Stub（服务端）和 Proxy（客户端代理）。客户端调用 `proxy.method()`，实际通过 `transact()` 发送 Binder 事务。

**2. Native 层（libbinder）**：
- **BBinder**：服务端本地对象，负责接收事务并调用 `onTransact()`。
- **BpBinder**：客户端代理，持有目标 Binder 的 handle，负责收集参数并通过 `IPCThreadState` 发送。
- **IPCThreadState**：每个线程一个实例，通过 `ioctl` 与 Binder 驱动通信。

**3. Kernel 层（binder driver）**：Linux 内核模块，管理 Binder 节点（binder_node）、引用（binder_ref）、传输事务（binder_transaction）。

**通信流程（transaction）**：

```
Client Proxy
  → BpBinder.transact(code, data, reply)
    → IPCThreadState.transact()
      → writeTransactionData()  // 组装 binder_transaction_data
      → waitForResponse()
        → talkWithDriver()  // ioctl(BINDER_WRITE_READ)
          → copy_from_user()  // ① 拷贝到内核空间
Kernel Driver
  → 找到目标 Server（binder_ref → binder_node → binder_proc）
  → 唤醒目标进程/线程
Server
  → 被唤醒的线程在 ioctl 中等待
  → copy_to_user()  // ② 拷贝目标数据到用户空间
  → BBinder.onTransact()
    → Stub.onTransact()
      → 调用实际业务方法
```

### 加分扩展

**为什么 Binder 只需要"一次拷贝"？**

这是面试中最重要的加分点。一般 IPC 通信需要两次拷贝：
- 用户空间 → 内核空间 → 目标用户空间

而 Binder 利用内核驱动 + mmap：
- 接收方进程在内核中映射了一块缓冲区（通过 `mmap`，大小约 1M-8K = 1016KB）。
- 发送方 `copy_from_user` 将数据拷贝到**这块共享的 mmap 区域**。
- 接收方直接读取该区域，无需再拷贝。
- **实际是：发送方用户空间 → 内核空间（mmap 区域）→ 接收方直接读内核 mmap 区域**，所以是"一次拷贝"。

**Binder 对比其他 IPC**：

| IPC 方式 | 拷贝次数 | 特点 | 安全性 |
|---------|---------|------|--------|
| 管道/消息队列 | 2 次 | 简单，容量有限 | 无内置身份校验 |
| Socket | 2 次 | 通用，但性能低 | 无内置身份校验 |
| 共享内存 | 0 次 | 最快，但需信号量同步 | 无内置身份校验 |
| Binder | 1 次 | 性能与安全平衡 | UID/PID 校验 |

**Binder 的身份验证机制**：
- 调用 `Binder.getCallingUid()` / `getCallingPid()` 可以获取调用方进程的 UID/PID。
- 这个值由 Binder 驱动填写，无法伪造——这是 Binder 的核心安全优势。
- Android 权限系统（如 `checkCallingPermission`）依赖此机制。

**ServiceManager**：
- 作为 Binder 机制的"命名服务"，地址固定为 handle 0。
- Server 启动时通过 `addService(name, binder)` 注册，Client 通过 `getService(name)` 查询。

**Binder 线程池**：
- 每个进程最多 16 个 Binder 线程（`BR_SPAWN_LOOPER`）。
- `IPCThreadState.joinThreadPool()` 进入无限循环，等待驱动发来的事务。
- 系统服务的 Binder 调用同步返回，如果服务端耗时过久会阻塞客户端——系统服务中极少有耗时操作。

### 常见误区

- ❌ 以为 Binder 是"零拷贝"——实际是一次拷贝（发送方到内核 mmap 区），共享内存才是零拷贝。
- ❌ 不知道 Binder 有传输大小限制——一般 1M-8K（`BINDER_VM_SIZE`），大文件用共享内存（如 SurfaceFlinger 的 GraphicBuffer）或 Socket。
- ❌ 以为所有跨进程调用都用 Binder——ContentProvider、AMS 等系统服务是 Binder，但 Socket 也用于 Zygote 等场景。

---

## 6. 内存泄漏场景分析

### 问题

> "Android 中哪些常见场景会导致内存泄漏？讲讲你遇到过的内存泄漏以及排查和修复方式？"

### 答题思路

先建立内存泄漏的核心原因（长生命周期对象持有短生命周期对象的引用），再分场景讲述。每个场景：**原因 → 示例代码 → 修复方案**。最后串讲排查工具链。

### 标准答案

**核心公式**：`长生命周期对象持有短生命周期对象的引用 → GC 无法回收短生命周期对象 → 内存泄漏`。

**场景一：非静态内部类持有外部引用**

```java
// ❌ 泄漏：匿名 Handler 持有 Activity 引用
class MyActivity extends Activity {
    private Handler mHandler = new Handler() {
        @Override
        public void handleMessage(Message msg) {
            // 如果消息延迟发送，Activity 销毁后仍被持有
        }
    };
}

// ✅ 修复：静态内部类 + WeakReference
private static class MyHandler extends Handler {
    private WeakReference<MyActivity> mActivityRef;
    MyHandler(MyActivity activity) { mActivityRef = new WeakReference<>(activity); }
}
```

**场景二：单例持有 Activity Context**

```java
// ❌ 单例传入 Activity Context，Activity 销毁后无法回收
public class MyManager {
    private Context context;
    private static MyManager instance;
    public static MyManager getInstance(Context context) {
        if (instance == null) instance = new MyManager(context);
        return instance;
    }
}

// ✅ 传入 ApplicationContext
getInstance(context.getApplicationContext());
```

**场景三：静态 View**

```java
// ❌ 静态 View 隐式持有 Activity
static View sLeakyView;

// ✅ 在 onDestroy 中置 null
@Override protected void onDestroy() {
    sLeakyView = null;
    super.onDestroy();
}
```

**场景四：资源未关闭**

- 文件流、Cursor、Bitmap（Android 3.0 前）、广播接收器、ContentObserver 等。
- ✅ Try-with-resources（Kotlin `use {}`）、`onStop/onDestroy` 中反注册。

**场景五：系统服务监听器泄漏**

```java
// ❌ 注册了 SensorManager 监听但未反注册
sensorManager.registerListener(this, sensor, SENSOR_DELAY_NORMAL);
// ✅ onPause/onDestroy 中 unregisterListener
```

**场景六：WebView 泄漏**

WebView 持有 Activity 引用且其内部的线程和回调不易释放。
- ✅ 独立进程（`android:process=":webview"`）+ `onDestroy` 中先 removeAllViews 再 destroy。

### 加分扩展

**排查工具链**：

1. **LeakCanary**：开发阶段自动检测，给出引用链。
2. **Android Studio Profiler**：观察内存曲线，手动 GC 看内存是否回落。
3. **MAT（Memory Analyzer Tool）**：dump hprof 文件，分析 Dominator Tree、查找大对象。
4. **adb shell dumpsys meminfo**：查看进程内存组成。

**LeakCanary 原理简述**：
1. 通过 `ActivityLifecycleCallbacks` 注册监听，Activity 销毁时用 WeakReference 包装。
2. 5 秒后检查 ReferenceQueue，如果 WeakReference 未被回收，触发 GC 后再次检查。
3. 如果仍未回收，dump hprof 文件，分析引用链（GCRoot → leaked object 的最短路径）。
4. 通过 `HeapAnalyzer` 解析，归类泄漏类型并给出报告。

**引用类型补充**：
| 类型 | GC 时机 | 用途 |
|------|--------|------|
| Strong（强引用） | 永远不会被回收 | 普通引用 |
| Soft（软引用） | 内存不足时 | 缓存，如图片内存缓存 |
| Weak（弱引用） | 下一次 GC | Handler、Callback 防护 |
| Phantom（虚引用） | 被回收后进队列 | 跟踪对象回收 |

### 常见误区

- ❌ 以为内存泄漏只发生在 Java 堆——Native 内存泄漏（如 `Bitmap.nativeCreate` 分配的）同样严重。
- ❌ Handler 用了 WeakReference 就万事大吉——但 `removeCallbacksAndMessages(null)` 才是彻底释放。
- ❌ 在 MVP/MVVM 中 Presenter 持有 View 引用，但销毁时忘记解绑。

---

## 7. Glide 三级缓存

### 问题

> "Glide 有哪些缓存层级？各自的作用和淘汰机制是什么？和 Picasso 的缓存设计有什么不同？"

### 答题思路

按缓存层级从快到慢、从内存到磁盘：**活动缓存 → 内存缓存 → 磁盘缓存 → 网络/原始数据**。重点解释活动缓存为什么多此一举（防止内存回收时 LruCache 的图片被 GC）。

### 标准答案

Glide 的四级缓存结构：

**第一级：活动资源（ActiveResources）**

- 存储当前正在使用的图片，以 `WeakReference<EngineResource>` 形式。
- **目的**：防止正在显示的图片被 LruCache 的 LRU 算法意外回收。LruCache 的 `value` 可能在任何时候被 GC，但正在展示的图片如果被回收会导致显示空白。
- 获取流程：先从 ActiveResources 找 → 如果有，引用计数 +1，直接返回。

**第二级：内存缓存（LruResourceCache）**

- 基于 LRU 算法的内存缓存，默认大小为各进程可用内存的约 1/4 或一个屏幕的 buffer 大小。
- 使用 `LruCache<Key, EngineResource>` 存储最近使用过但当前未展示的图片。
- `EngineResource` 有引用计数，计数为 0 时从 ActiveResources 移入 LruCache。
- 淘汰策略：最近最少使用的被移除，回调 `onResourceReleased` → 可能加入 BitmapPool。

**第三级：磁盘缓存（DiskLruCacheWrapper）**

- 基于 DiskLruCache，默认大小 250MB，目录位于 `context.getCacheDir()` 下的 `image_manager_disk_cache`。
- 存储经过**编码压缩后的原始图片数据**（不是 Bitmap），即从网络/文件加载的原始字节流。
- 读取时从磁盘 decode 为 Bitmap（相对耗时，但远快于网络）。

**第四级：原始数据（Source）**

- 从网络、文件、ContentProvider 等加载原始数据。

**完整加载流程**：

```
Glide.with(context).load(url).into(imageView)
  → 1. 检查 ActiveResources（当前使用中）
  → 2. 检查 LruCache（内存最近使用）
  → 3. 检查 DiskLruCache（磁盘缓存原始数据）
  → 4. 从网络/文件加载原始数据
```

**缓存 Key 的生成**：Glide 的缓存 Key 由约 10 个参数决定，包括 URL/Model、宽高、变换（Transformations）、选项等。任何参数不同都视为不同缓存。

### 加分扩展

**BitmapPool（复用池）**：
- LruCache 中淘汰的 Bitmap 不会立即 `recycle()`，而是放入 BitmapPool。
- 下次需要分配 Bitmap 时优先从池中取，避免重复分配和 GC 压力。
- 适配条件：被回收的 Bitmap 必须与请求的 Bitmap 尺寸和配置一致。

**Glide vs Picasso**：

| 维度 | Glide | Picasso |
|-----|-------|---------|
| 默认图片格式 | RGB_565（省一半内存） | ARGB_8888 |
| GIF 支持 | ✅ 原生支持 | ❌ |
| 内存占用 | 按 ImageView 尺寸加载 | 全尺寸加载到内存 |
| 磁盘缓存 | 原始数据（解码前的字节流） | 解码后的 Bitmap（更快但占空间） |
| 生命周期集成 | 强（RequestManager 绑定 Fragment） | Activity 级别 |

**Glide 生命周期感知原理**：
- `Glide.with(Activity)` 向当前 Activity 添加一个透明的 `SupportRequestManagerFragment`。
- 该 Fragment 感知 Activity 的生命周期（`onStart`/`onStop`/`onDestroy`）。
- `onStop` 时暂停请求（`pauseRequests`），`onDestroy` 时清除请求（`clearRequests`）。
- 这就是 Glide 不会在 Activity 销毁后继续加载图片的原因。

### 常见误区

- ❌ 以为 Glide 只有三级缓存——实际是四级（ActiveResources + LruCache + DiskCache + Source）。
- ❌ 混淆 Glide 磁盘缓存存储的是原始数据而非 Bitmap——所以变换参数变化会导致磁盘缓存 miss。
- ❌ `diskCacheStrategy(DiskCacheStrategy.ALL)` 会缓存所有尺寸的图片，导致磁盘占用过大。建议按场景选择 `RESOURCE` 或 `DATA`。

---

## 8. OkHttp 拦截器链

### 问题

> "OkHttp 的拦截器链是怎么工作的？责任链模式如何实现？有哪些内置拦截器，各自做什么？怎么添加自定义拦截器？"

### 答题思路

OkHttp 的核心设计模式就是**责任链**。回答时先画责任链的链路结构，五个内置拦截器的职责和顺序，然后讲自定义拦截器的 `addInterceptor` vs `addNetworkInterceptor` 的区别。

### 标准答案

**责任链结构（RealInterceptorChain）**：

OkHttp 的每一次请求都由以下拦截器链依次处理（按顺序）：

```
用户自定义 Interceptor (addInterceptor)
  → RetryAndFollowUpInterceptor    // 重试与重定向
    → BridgeInterceptor             // 请求头补全
      → CacheInterceptor            // 缓存处理
        → ConnectInterceptor        // 建立连接
          → 用户自定义 NetworkInterceptor (addNetworkInterceptor)
            → CallServerInterceptor  // 发送请求、读取响应
```

**五大内置拦截器详解**：

**① RetryAndFollowUpInterceptor（重试与重定向）**
- 从 `OkHttpClient` 创建 `StreamAllocation`（管理连接、流、请求的生命周期）。
- 处理重定向（最多 20 次）和鉴权挑战。
- 发生 `RouteException` 或 `IOException` 时决定是否重试。

**② BridgeInterceptor（桥接拦截器）**
- 把用户请求转为网络请求，补全请求头：`Content-Type`、`Content-Length`、`Host`、`Connection: Keep-Alive`、`Accept-Encoding: gzip`、Cookie。
- 响应返回后，保存 Cookie、解压 Gzip 响应体。

**③ CacheInterceptor（缓存拦截器）**
- 根据请求和响应头（`Cache-Control`、`Expires`、`Last-Modified`、`ETag`）决定：
  - 直接返回缓存（有且未过期）→ request 不发出。
  - 发出带 `If-None-Match` / `If-Modified-Since` 的条件请求 → 304 则用缓存。
  - 无缓存或过期 → 正常发请求并缓存结果。

**④ ConnectInterceptor（连接拦截器）**
- 打开到目标服务器的连接。核心功能：
  - 从连接池（`ConnectionPool`）中复用已有连接。
  - 无可用连接时，通过 Route 链（DNS → Proxy → TLS）建立新连接（TCP + TLS 握手）。
  - 返回 `HttpCodec`（HTTP/1.1 或 HTTP/2 的编解码器）。

**⑤ CallServerInterceptor（调用服务拦截器）**
- 真正向服务器发送 HTTP 请求：写请求头 → 写请求体 → 读响应头 → 读响应体。

**责任链模式的实现**：

```java
// 简化源码逻辑
Response getResponse(Interceptor.Chain chain) {
    Request request = chain.request();
    // ... 处理前逻辑 ...
    Response response = chain.proceed(request);  // 传给下一个拦截器
    // ... 处理后逻辑 ...
    return response;
}
```

- 每个拦截器在 `intercept()` 中调用 `chain.proceed(request)` 将控制权交给下一个拦截器。
- 递归调用形成一个"洋葱模型"——请求从外向内传递，响应从内向外传递。

### 加分扩展

**addInterceptor vs addNetworkInterceptor**：

| 维度 | addInterceptor | addNetworkInterceptor |
|-----|---------------|----------------------|
| 调用位置 | RetryAndFollowUp 之前 | Connect 之后，CallServer 之前 |
| 调用次数 | 可能多次（重试/重定向会再次触发） | 仅一次（实际网络请求） |
| 可见请求 | 原始请求（可能在内部被修改） | 最终发出的网络请求 |
| 可见响应 | 可能包含缓存响应 | 仅网络返回的响应 |
| 典型用途 | 统一日志、加 Header、Mock | 网络监控、抓包、统计网络耗时 |

**连接池（ConnectionPool）**：
- 默认最多 5 个空闲连接，存活 5 分钟。
- 连接复用条件是：相同的 Address（host + port + proxy + SSL 配置），且 HTTP/1.1 需要 `Connection: Keep-Alive`。
- HTTP/2 天然支持多路复用（一个 TCP 连接承载多个并发请求流）。

**OkHttp 请求调度流程**：
```
Call.enqueue(callback)
  → Dispatcher.enqueue()  // 加入 runningCalls 或 readyAsyncCalls 队列
    → 控制并发：同 host 最多 5 个，总数最多 64 个
    → 有可用槽位 → runningCalls.add(call)
      → 线程池执行 AsyncCall.execute()
        → getResponseWithInterceptorChain()
```

### 常见误区

- ❌ 在自定义拦截器中忘记调用 `chain.proceed(request)`——请求会中断。
- ❌ 混淆 `addInterceptor` 和 `addNetworkInterceptor`——前者可能因缓存而不触发。
- ❌ 在拦截器中多次读取 Response Body——`Response.body()` 只能读一次（流式），需要先缓存到内存。

---

## 9. Kotlin 协程原理

### 问题

> "Kotlin 协程是什么？和线程有什么区别？挂起（suspend）函数是怎么实现的？协程的调度器有哪些？"

### 答题思路

从"协程是什么"（轻量级线程）→ "为什么轻量"（挂起不阻塞线程）→ "怎么实现"（状态机 + Continuation）→ "调度器" → "结构化并发"。这是 30k+ 岗位的高频题。

### 标准答案

**协程是什么？**

协程（Coroutine）是一种**运行在线程之上的、可挂起和恢复的轻量级并发框架**。
- 一个线程上可以运行数千个协程。
- 协程的"挂起"不会阻塞当前线程，而是让出线程资源执行其他任务。
- **核心优势**：用同步的写法写异步代码，消除回调地狱。

**协程 vs 线程**：

| 维度 | 线程 | 协程 |
|------|------|------|
| 调度者 | OS Kernel（内核） | 用户态调度（Dispatcher） |
| 切换成本 | 高（用户态↔内核态，上下文保存） | 极低（函数调用级别） |
| 内存占用 | 约 1MB 栈空间 | 约几十 KB |
| 创建数量 | 数百到数千 | 数十万 |
| 阻塞行为 | 阻塞线程 | 挂起不阻塞线程 |

**挂起（suspend）函数的实现原理**：

Kotlin 编译器将 `suspend` 函数编译成**状态机**：

```kotlin
suspend fun fetchData(): String {
    val result = api.fetch()  // 挂起点
    return result
}
```

编译后等价于（简化）：

```java
// 编译器生成 Continuation 状态机
class FetchDataContinuation(
    private val completion: Continuation<String>
) : Continuation<Any?> {
    var label = 0  // 状态机的当前状态
    var result: String? = null

    override fun resumeWith(value: Result<Any?>) {
        // 根据 label 跳转到对应代码段
        when (label) {
            0 -> {
                label = 1
                api.fetch(this)  // 传递自己作为回调
                return  // 挂起，线程被释放
            }
            1 -> {
                result = value.getOrNull() as String
                completion.resumeWith(Result.success(result!!))
            }
        }
    }
}
```

- 每个 `suspend` 函数会自动添加一个 `Continuation` 参数（CPS 变换——Continuation-Passing Style）。
- 遇到挂起点（网络请求等）时，保存当前状态 label，注册回调后 return（线程被释放）。
- 异步操作完成后通过 `resumeWith` 恢复，根据 label 跳转到挂起点之后继续执行。
- **关键是：整个过程没有创建新线程，只是在同一个线程上挂起/恢复。**

**协程调度器（Dispatcher）**：

| 调度器 | 用途 | 线程池 |
|--------|------|--------|
| Dispatchers.Main | UI 更新 | Android 主线程 |
| Dispatchers.IO | 网络、文件 I/O | 最多 64 个线程（和 Default 共享） |
| Dispatchers.Default | CPU 密集计算 | CPU 核心数个线程 |
| Dispatchers.Unconfined | 不切换线程（不推荐） | 在调用它的线程执行 |

### 加分扩展

**结构化并发（Structured Concurrency）**：

```kotlin
// ✅ 结构化：子协程在父协程的 scope 内
viewModelScope.launch {
    val result1 = async { fetchUser() }
    val result2 = async { fetchOrder() }
    updateUI(result1.await(), result2.await())
}
// viewModelScope 取消时，所有子协程自动取消
```

- `CoroutineScope` 管理协程的生命周期。
- 父协程会等待所有子协程执行完毕才退出。
- 任何一个子协程抛异常，父协程和其他子协程会被取消（`SupervisorJob` 除外）。

**CoroutineScope 的选择**：
- `viewModelScope`：绑定 ViewModel 生命周期，ViewModel.clear() 时自动取消。
- `lifecycleScope`：绑定 Lifecycle，onDestroy 时自动取消。
- `GlobalScope`：❌ 不推荐，生命周期为整个应用进程。

**协程上下文（CoroutineContext）**：
- `Job`：控制协程生命周期（cancel / join / children）。
- `CoroutineDispatcher`：指定协程运行线程。
- `CoroutineName`：调试用。
- `CoroutineExceptionHandler`：异常处理。

### 常见误区

- ❌ 以为 `launch` 中的异常会自动被 `try-catch` 捕获——`launch` 的异常会传播到 `CoroutineExceptionHandler`，需在 launch 内部 try-catch 或用 `async.await()`。
- ❌ 在主线程 `runBlocking`——会阻塞主线程导致 ANR。
- ❌ `GlobalScope.launch` 忘记手动取消——容易造成内存泄漏。
- ❌ 挂起函数中切换到 IO 线程后没有切回 Main 就更新 UI——需要 `withContext(Dispatchers.Main) { }`。

---

## 10. Jetpack ViewModel 原理

### 问题

> "ViewModel 是怎么存储和恢复的？屏幕旋转时 ViewModel 为什么不会销毁？ViewModel 可以用在 Fragment 之间共享数据吗？"

### 答题思路

核心是 ViewModelStore + ViewModelStoreOwner + 生命周期感知。按三个层次：**创建流程**（Factory + Provider）→ **存活机制**（屏幕旋转不销毁）→ **作用域**（Activity/Fragment/Shared）。

### 标准答案

**ViewModel 的创建流程**：

```kotlin
val viewModel = ViewModelProvider(this).get(MyViewModel::class.java)
```

1. `ViewModelProvider` 获取宿主（`ViewModelStoreOwner`，如 Activity/Fragment）的 `ViewModelStore`。
2. 以类的完全限定名为 Key，查看 `ViewModelStore` 中是否已有实例。
3. 没有则通过 `Factory` 创建，存入 `ViewModelStore` 的 `HashMap<String, ViewModel>`。

**屏幕旋转时 ViewModel 存活原理**：

这是 `ComponentActivity` 的关键设计：

```
屏幕旋转
  → Activity.onRetainNonConfigurationInstance()
    → 保存 NonConfigurationInstances（包含 ViewModelStore）
  → Activity 销毁重建
    → Activity.onCreate(savedInstanceState)
      → getLastNonConfigurationInstance()
        → 取回 ViewModelStore
  → 新 Activity 的 ViewModelProvider 拿到的是旋转前的同一个 ViewModelStore
    → get(ViewModel) 返回已存在的实例
```

- ViewModelStore 在 `onRetainNonConfigurationInstance` 中被保留，横跨 Activity 的重建周期。
- 只有当 Activity 真正 `finish()`（不是配置变更）时，`onDestroy` 中调用 `ViewModelStore.clear()`，ViewModel 的 `onCleared()` 才被调用。

**Fragment 间共享 ViewModel**：

```kotlin
// 使用 Activity 作为 ViewModelStoreOwner
val sharedVM = ViewModelProvider(requireActivity()).get(SharedViewModel::class.java)
```

- 两个 Fragment 共享同一个 Activity 的 ViewModelStore。
- Key 相同（SharedViewModel 类名），所以拿到的都是同一个实例。
- 推荐使用 Navigation 的 `navGraphViewModels` 按导航图作用域共享。

### 加分扩展

**ViewModel + SavedStateHandle**：

```kotlin
class MyViewModel(savedStateHandle: SavedStateHandle) : ViewModel() {
    val userName = savedStateHandle.getLiveData<String>("user_name")
}
```

- 进程被杀死后恢复时会走 `onSaveInstanceState` → `SavedStateHandle` 保存 → 恢复时还原。
- 结合了 ViewModel 的内存复活性 + Bundle 的持久性。

**ViewModel vs onSaveInstanceState**：

| 维度 | ViewModel | onSaveInstanceState |
|-----|-----------|-------------------|
| 场景 | 屏幕旋转/配置变更 | 进程被杀死 |
| 数据量 | 大（Bitmap 级别） | 小（几 KB，Bundle 限制） |
| 类型 | 任意对象 | 可序列化/可打包类型 |
| 配合 | + SavedStateHandle 覆盖进程死亡 | 单独使用 |

**ViewModelScope**：
- `viewModelScope` 绑定 ViewModel 的 `onCleared()`。
- 内部使用 `CloseableCoroutineScope + SupervisorJob`。
- 任何在 `onCleared` 前未完成的协程被自动取消。

### 常见误区

- ❌ 在 ViewModel 中持有 View/Activity/Context 的引用——会导致内存泄漏。应该用 `AndroidViewModel(application)` 持有 Application Context 或用 LiveData 回调。
- ❌ 混淆 `onRetainNonConfigurationInstance` 和 `onSaveInstanceState`——前者在配置变更时调用（ViewModel 存活），后者在可能被系统杀死时调用（Bundle 保存）。
- ❌ 在 ViewModel 中做网络请求但不处理生命周期取消——用 `viewModelScope` 会自动处理。

---

## 11. LiveData 数据倒灌问题

### 问题

> "LiveData 的数据倒灌是什么意思？为什么会出现？怎么解决？LiveData 和 Flow 对比如何？"

### 答题思路

解释"数据倒灌"（observe 之前 setValue 的数据在 observe 时被立即回调）→ 根本原因（mVersion 对齐机制）→ 解决方案 → 与 Flow 对比。

### 标准答案

**什么是数据倒灌？**

LiveData 数据倒灌是指：在 Activity/Fragment 重建（如屏幕旋转）或首次 attach 时，`observe()` 注册后立即收到之前 `setValue/postValue` 的最后一次数据——即使这个数据是用户在操作前就已经处理过的。

**原因：mVersion 对齐机制**

LiveData 内部有两个版本号：
- `mVersion`：LiveData 每次 setValue 时 +1。
- `mLastVersion`：每个 ObserverWrapper 的版本号（初始为 -1）。

```java
// 简化逻辑
private void considerNotify(ObserverWrapper observer) {
    if (observer.mLastVersion >= mVersion) return;
    observer.mLastVersion = mVersion;
    observer.mObserver.onChanged(mData);  // 回调！
}
```

当 observe 注册时，如果 Observer 的 `mLastVersion` (-1) < `mVersion` (≥0)，立即触发回调 → 数据倒灌。

**常见场景**：
- Fragment 重建时重复 observe，数据被重新消费一次（如弹出多次 Toast）。
- 先 setValue 再 observe（如 ViewModel 初始化默认值），Observer 立即收到数据。

**解决方案**：

1. **SingleLiveEvent**（简单场景）：
```kotlin
class SingleLiveEvent<T> : MutableLiveData<T>() {
    private val pending = AtomicBoolean(false)
    override fun observe(owner: LifecycleOwner, observer: Observer<in T>) {
        super.observe(owner) { t ->
            if (pending.compareAndSet(true, false)) {
                observer.onChanged(t)
            }
        }
    }
    override fun setValue(value: T) {
        pending.set(true)
        super.setValue(value)
    }
}
```

2. **Event Wrapper 模式**（推荐）：
```kotlin
open class Event<out T>(private val content: T) {
    var hasBeenHandled = false; private set
    fun getContentIfNotHandled(): T? {
        return if (hasBeenHandled) null else { hasBeenHandled = true; content }
    }
    fun peekContent(): T = content
}
```

3. **Kotlin SharedFlow / StateFlow**（Google 官方推荐方向）：
```kotlin
private val _events = MutableSharedFlow<Event>()  // 不重放
val events: SharedFlow<Event> = _events
```

### 加分扩展

**LiveData vs Flow 对比**：

| 维度 | LiveData | Flow / StateFlow |
|-----|---------|------------------|
| 生命周期感知 | ✅ 内置（LifecycleOwner） | ❌ 需要 `repeatOnLifecycle` / `flowWithLifecycle` |
| 背压处理 | 无（永远取最新值） | ✅ SharedFlow 支持 Buffer |
| 线程切换 | 默认主线程 | `flowOn(Dispatcher)` |
| 操作符 | 有限（Transformations） | 丰富（map/filter/combine 等 100+） |
| 初始值 | null 友好 | StateFlow 必须初始值 |
| 数据倒灌 | 有 | StateFlow 有，SharedFlow 可选（replay=0） |

**LiveData 粘性事件 vs 数据倒灌**：
- 粘性事件（Sticky Event）是 LiveData 的设计特性——新 Observer 可以获取最新数据（适合状态展示）。
- 数据倒灌是这个特性在错误场景下的副作用（事件消费场景）。

### 常见误区

- ❌ 用 MutableLiveData<Boolean> 做一次性事件（Toast、Navigation）——倒灌导致事件被重复消费。
- ❌ 混淆 LiveData 的 setValue 和 postValue——postValue 只在主线程 setValue，后台线程发 postValue 在线程竞争下可能丢失数据。
- ❌ 在 Fragment onCreate 中 observe，在 onCreateView 中 observe——两次 observe 都触发回调。

---

## 12. RecyclerView 四级缓存

### 问题

> "RecyclerView 有哪几级缓存？各级缓存的作用和区别是什么？和 ListView 的缓存机制有什么不同？"

### 答题思路

四级缓存由近到远：**Scrap → Cache → ViewCacheExtension → RecycledViewPool**。重点解释各级的位置、复用条件、以及"不需要重新 bind"这个面试高频点。

### 标准答案

RecyclerView 四级缓存结构：

| 级别 | 名称 | 存储对象 | 复用条件 | 是否需要重新 bind |
|-----|------|---------|---------|:---:|
| 1 | mAttachedScrap & mChangedScrap | ViewHolder | 与当前位置相同 + 数据未变 | ❌ |
| 2 | mCachedViews | ViewHolder | 位置无关 + 数据未变 | ❌ |
| 3 | ViewCacheExtension | 用户自定义 | 自定义规则 | 视情况 |
| 4 | RecycledViewPool | ViewHolder | 仅 type 相同 | ✅ |

**一级缓存：Scrap**

- `mAttachedScrap`：缓存当前屏幕内、未与 RecyclerView 分离的 ViewHolder。数据未变时直接复用，**无需 `onBindViewHolder`**。
- `mChangedScrap`：数据发生了变化（`notifyItemChanged` 后）的 ViewHolder，需要重新绑定。

**二级缓存：mCachedViews**

- 缓存滑出屏幕的 ViewHolder，默认容量 2。
- 按位置匹配（position），如果位置变了（如数据增删），缓存作废移入 RecyclePool。
- **复用条件苛刻但高效：无需重新 bind**。

**三级缓存：ViewCacheExtension**

- 留给开发者的自定义缓存接口，一般不用。如果实现，可以创建自定义 ViewHolder 返回。
- 需要覆写 `getViewForPositionAndType()`。

**四级缓存：RecycledViewPool**

- 所有 RV 的最终兜底缓存。默认每个 ViewType 最多存 5 个 ViewHolder。
- **全局共享**：同一 Activity 中多个 RecyclerView 可以共享一个 RecycledViewPool。
- 复用需要重新 `onBindViewHolder`（因为数据已清空）。

**复用流程**：

```
获取 ViewHolder (getViewForPosition)
  → 1. 有动画且 position 不变 → Scrap（最快）
  → 2. 查 mCachedViews（按 position 匹配）
  → 3. 查 ViewCacheExtension（自定义）
  → 4. 查 RecycledViewPool（按 ViewType 匹配）
  → 5. 缓存全 miss → createViewHolder（创建新 ViewHolder）
```

### 加分扩展

**RecyclerView vs ListView 缓存机制对比**：

| 维度 | ListView | RecyclerView |
|------|---------|-------------|
| 回收 | Active View → ScrapViews | Scrap → Cache → Pool（更精细） |
| 复用 | 按 ViewType，必须重新 bind | 部分缓存在 Cache 层无需 bind |
| ViewHolder | 需要自己封装 | 强制使用 ViewHolder 模式 |
| 局部刷新 | 不支持（只能 notifyDataSetChanged） | ✅ notifyItemChanged(position) |
| 动画 | 无内置 | ✅ ItemAnimator |

**优化技巧**：

1. **增大 mCachedViews**：内部列表频繁进出屏幕时，`recyclerView.setItemViewCacheSize(20)`。
2. **设置固定尺寸**：`recyclerView.setHasFixedSize(true)` 跳过 requestLayout。
3. **共享 RecycledViewPool**：
```kotlin
val sharedPool = RecyclerView.RecycledViewPool()
recyclerView1.setRecycledViewPool(sharedPool)
recyclerView2.setRecycledViewPool(sharedPool)
```
适用于 ViewPager 中的多个同类型列表。
4. **预取**：`LayoutManager.setItemPrefetchEnabled(true)`（默认 true），空闲时提前创建下一屏的 ViewHolder。

### 常见误区

- ❌ 以为 Scrap 和 Cache 都需要重新 bind——Scrap 和 Cache 中数据未变的 ViewHolder 直接复用，不需要 bind。
- ❌ RecycledViewPool 只和当前 RecyclerView 绑定——可以多个 RV 共享。
- ❌ 所有场景都用 `notifyDataSetChanged`——应使用更精细的 `notifyItemChanged/Inserted/Removed` 来触发动画和保留缓存。

---

## 13. Activity 生命周期与任务栈

### 问题

> "A 启动 B 后按 Home 键再回来，两个 Activity 分别走了哪些生命周期？如果 B 是透明主题呢？"

### 答题思路

这道题的考点在于对**生命周期时序**和**可见性变化**的理解。回答要点：分场景画生命周期流程图 → 解释透明主题的特殊性 → 补充 onSaveInstanceState 的调用时机。

### 标准答案

**场景一：A 启动 B（B 全屏），按 Home 再返回**

```
启动 B：
  A.onPause → B.onCreate → B.onStart → B.onResume → A.onStop

按 Home：
  B.onPause → B.onStop

返回应用：
  B.onRestart → B.onStart → B.onResume

按 Back 返回 A：
  B.onPause → A.onRestart → A.onStart → A.onResume → B.onStop → B.onDestroy
```

**场景二：B 是透明主题（Dialog 样式）**

因为 A 仍然可见，A 不会走 onStop：

```
A 启动透明 B：
  A.onPause → B.onCreate → B.onStart → B.onResume
  （A 可见但不交互，不走到 onStop）

按 Back 返回：
  B.onPause → A.onResume → B.onStop → B.onDestroy
```

**onSaveInstanceState 调用时机**：
- 在 `onStop` 之前，可能与 `onPause` 先后不定（API 28+ 在 onStop 之后）。
- 系统需要保存状态时会被调用，但用户主动按 Back 退出时**不调用**。

### 加分扩展

**生命周期核心配对规则**：

| 我的变化 | 我的回调 | 对方的回调 |
|---------|---------|-----------|
| 打开全屏覆盖我的 Activity | onPause → onStop | 对方 onCreate → onStart → onResume |
| 透明/浮窗覆盖我的 Activity | onPause（不到 onStop） | 对方 onCreate → onStart → onResume |
| 从覆盖返回 | onRestart → onStart → onResume | 对方 onPause → onStop → onDestroy |
| 我的 setResult 什么时候有用 | — | 对方 onActivityResult 在我 onStop 之前收到 |

**进程优先级与生命周期**：

| 状态 | 进程优先级 | 被杀死风险 |
|------|----------|:---:|
| onResume（前台可见可交互） | 前台进程 | 极低 |
| onPause / onStop（可见但不可交互/不可见） | 可见进程 | 低 |
| onDestroy（已销毁但 Service 存活） | 服务进程 | 中 |
| 无组件在运行 | 缓存进程 | 高 |

### 常见误区

- ❌ 以为 A 启动 B 时 A 直接 onStop——实际是先 onPause（B 的 onCreate 在 A.onPause 之后），等 B 完全可见了 A 再 onStop。
- ❌ 混淆 `onSaveInstanceState` 和 `onRetainNonConfigurationInstance`——前者是持久化到 Bundle（应对进程被杀），后者只应对配置变更。
- ❌ 在 `onPause` 中做耗时操作——`onPause` 必须在 B 启动前完成，耗时会导致 B 的显示延迟。

---

## 总结

本文涵盖了 Android 基础面试中最高频的 13 个考点。在回答这些问题时，记住一个原则：**面试官不只想听你背答案，更想看你是否真正理解了底层机制**。每道题都尽量往源码层、设计模式、或者实际工程经验方向延伸一两句，这样你的回答会在众多候选人中脱颖而出。

> **下一步**：掌握了基础题之后，建议继续阅读 [架构设计题](../02-架构设计题/index.md)，学习如何在设计类问题中展示架构思维。
