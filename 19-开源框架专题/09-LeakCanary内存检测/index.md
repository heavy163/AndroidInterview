# LeakCanary 内存检测框架 — 面试深度解析

> **目标**：掌握 LeakCanary 核心检测原理，从面试高频问题出发，逐层深入源码级实现，最终覆盖自定义泄漏规则与线上裁剪实战。

---

## 第一层：高频面试问题（6 道核心题）

### Q1：LeakCanary 检测内存泄漏的核心算法是什么？

**答案概要**：LeakCanary 基于 **WeakReference + ReferenceQueue + 主动触发 GC + HeapDump 分析** 四步组合算法。

| 步骤 | 机制 | 说明 |
|------|------|------|
| **① 弱引用绑定** | `KeyedWeakReference(obj, key, name, queue)` | 为每个监控对象创建带唯一 Key 的弱引用，注册到 ReferenceQueue |
| **② 主动 GC** | `Runtime.getRuntime().gc()` + 5 次循环检测 | 通过循环 `System.runFinalization()` + `Runtime.gc()` 确保对象被回收 |
| **③ ReferenceQueue 检测** | `queue.poll()` 判断是否入队 | 若弱引用出现在 ReferenceQueue 中 → 对象已被正常回收；若不在 → 疑似泄漏 |
| **④ HeapDump + Shark 解析** | `Debug.dumpHprofData()` → Shark 分析 | 对疑似泄漏对象 dump 堆快照，用 Shark 引擎 BFS 查找 GC Root 最短引用路径 |

**核心判断逻辑（伪代码）**：

```kotlin
// ObjectWatcher 核心检测流程
fun expectWeaklyReachable(watchedObject: Any, description: String) {
    // 1. 移除已回收的弱引用（在 ReferenceQueue 中 = 已 GC）
    removeWeaklyReachableObjects()
    
    // 2. 创建新的 KeyedWeakReference 并注册
    val key = UUID.randomUUID().toString()
    val ref = KeyedWeakReference(watchedObject, key, description, queue)
    watchedObjects[key] = ref
    
    // 3. 主动触发 GC（5 次循环确保回收）
    runGc()
    
    // 4. 再次检查 ReferenceQueue
    removeWeaklyReachableObjects()
    
    // 5. 若 ref 仍未被移除 → 疑似泄漏
    if (watchedObjects.containsKey(key)) {
        // 触发 HeapDump
        onObjectRetained()
    }
}
```

**面试亮点**：WeakReference 解决的是「监控」问题，ReferenceQueue 解决的是「反馈」问题，两者配合才能做到无侵入的自动化泄漏检测。

---

### Q2：Shark 解析引擎如何找到最短泄漏路径？

**答案概要**：Shark 使用 **BFS（广度优先搜索）** 从泄漏对象出发，沿引用链反向追溯至 GC Root，保证找到的路径是**最短引用链**。

**BFS 最短路径原理**：

```
泄漏对象(Leaking Instance)
    ↑
  引用1 ← 当前层
    ↑
  引用2 ← BFS 逐层展开
    ↑
  引用3 ← ...
    ↑
 GC Root ← 最终到达
```

| 概念 | 解释 |
|------|------|
| **搜索起点** | 所有被判定为泄漏的实例 |
| **搜索终点** | 任意 GC Root（静态字段、活跃线程、JNI 全局引用等） |
| **BFS 优势** | 层序遍历天然保证首次遇到 GC Root 时的路径就是最短路径 |
| **剪枝策略** | Shark 内置 `ReferenceMatcher` 系统，跳过系统级已知泄漏引用，聚焦应用层泄漏 |

**关键类**：

| 类 | 职责 |
|----|------|
| `HeapAnalyzer` | 分析入口，协调整个分析流程 |
| `ShortestPathFinder` | BFS 最短路径查找器 |
| `LeakingObjectFinder` | 从 HPROF 中识别泄漏对象 |
| `ReferenceMatcher` | 过滤系统库已知泄漏的引用节点 |
| `LeakTrace` | 最终产物：从 GC Root 到泄漏对象的完整引用链 |

---

### Q3：LeakCanary 的 GC 触发策略是什么？为什么需要循环触发？

**答案概要**：LeakCanary 并非简单调用一次 `System.gc()`，而是采用 **5 次循环 + Thread.sleep 等待** 的激进策略。

```kotlin
// LeakCanary 2.x GC 触发实现
fun runGc() {
    // 强制同步已失去引用的 finalize 队列
    Runtime.getRuntime().runFinalization()
    
    // 标记：记录当前已处理的引用数量
    val startCount = removeWeaklyReachableObjects()
    
    // 5 次循环尝试
    repeat(5) {
        System.runFinalization()   // 触发 finalize
        Runtime.getRuntime().gc()  // 请求 GC
        Thread.sleep(100)          // 等待 GC 线程执行
        System.runFinalization()   // 再次触发 finalize
        
        // 检查是否有新的弱引用入队
        if (removeWeaklyReachableObjects() == startCount) {
            // 没有新对象被回收 → GC 已足够彻底
            break
        }
    }
}
```

**为什么需要多次循环？**

| 原因 | 说明 |
|------|------|
| `System.gc()` 是**建议**非强制 | Dalvik/ART 可能延迟执行，多次调用提高概率 |
| finalize() 异步执行 | 对象回收分两步：先入 finalize 队列，finalize 后才真正释放；`runFinalization` 同步等待 |
| 引用链级联释放 | A → B → C：A 回收后 B 才能回收，一次 GC 可能不够 |
| 不同 GC 策略 | CMS/G1/ConcurrentCopying 等回收时机不同，反复触发保证一致性 |

---

### Q4：LeakCanary 2.0 相比 1.0 的架构变化是什么？

**答案概要**：从「一个库」拆分为 **ObjectWatcher（监控） + Shark（分析）** 两个独立模块，实现关注点分离。

| 维度 | 1.x | 2.x |
|------|-----|-----|
| **架构** | `leakcanary-android` 单体 | 拆分为 `leakcanary-android`（监控）+ `shark-android`（分析） |
| **入口** | `RefWatcher.watch()`（手动） | `AppWatcher.objectWatcher.watch()` 自动 + 手动 |
| **HeapDump** | `ServiceHeapDumper`（独立进程 Service） | `AndroidHeapDumper`（同进程主线程，更可靠） |
| **分析引擎** | `HAHA` 库（Hprof 解析，已停维） | `Shark`（自研 Kotlin 引擎，速度快 6×，内存低 10×） |
| **泄漏查找** | 遍历所有引用链（慢） | BFS 最短路径 + ReferenceMatcher 过滤（快） |
| **协程支持** | 无（RxJava/Thread） | 全面使用 Kotlin Coroutines |
| **报告 UI** | `DisplayLeakActivity` | 独立 `leakcanary-android-core` Activity，Material Design |
| **依赖** | 需要手动初始化 `LeakCanary.install()` | ContentProvider 自动初始化 (`AppWatcherInstaller`) |

**面试亮点**：2.0 最大的设计哲学变化是「监控与分析分离」——ObjectWatcher 只管「有没有泄露」，Shark 只管「泄露根源是什么」，两者可独立迭代、独立测试、独立裁剪。

---

### Q5：如何解读 LeakCanary 的泄漏报告？

**答案概要**：一份完整报告包含签名、引用链、元数据三个核心区域。

```
┌─────────────────────────────────────────────────────┐
│ ❶ Leak Signature                                    │
│   ├─ Class: com.example.MainActivity                │
│   ├─ Leaking Instances: 1/10                        │
│   └─ Retention Size: ~12.4 MB                       │
├─────────────────────────────────────────────────────┤
│ ❷ Leak Trace (最短路径 GC Root → 泄漏对象)          │
│   ├─ GC Root: Local variable in thread main         │
│   ├─ ─┬─ static MyApplication.INSTANCE              │
│   │   ├─ MyApplication.mLeakyList                   │
│   │   ├─ ArrayList[0]                               │
│   │   └─ MainActivity instance ← LEAKING            │
│   └─ Leaking: YES (this is the leaking instance)    │
├─────────────────────────────────────────────────────┤
│ ❸ Metadata                                          │
│   ├─ Build: Android 13, LeakCanary 2.12             │
│   ├─ Duration: analysis took 823ms                  │
│   └─ Heap dump size: 23.4 MB                        │
└─────────────────────────────────────────────────────┘
```

**关键字段解读**：

| 字段 | 含义 |
|------|------|
| `Leak Signature` | 泄漏签名（类名 + 引用链 Hash），用于分组 → 同一签名只显示一次 |
| `Retention Size` | 该泄漏对象持有的所有对象的堆内存总和（即回收此对象能释放的总内存） |
| `GC Root` | 根源：thread、jni global、system class、monitor 等 |
| `Leaking: YES/NO/UNKNOWN` | YES=是泄漏根因；NO=只是引用链上的中间节点 |

---

### Q6：LeakCanary 会不会产生误报？如何处理？

**答案概要**：会。主要来源有**系统库泄漏**和**异步时序问题**。

| 误报类型 | 典型例子 | 处理方式 |
|---------|---------|---------|
| **系统库泄漏** | `InputMethodManager.mCurRootView` 持有已销毁 Activity | Shark 内置 `AndroidReferenceMatchers` 忽略列表 |
| **异步时序** | 网络回调 200ms 后才释放，但 GC+检测已结束 | 增加 `watchDurationMillis` 等待时间（默认 5s） |
| **弱引用未入队** | 部分 Android 版本 GC 不及时 | 5 次循环 GC + 100ms sleep 降低误报率 |
| **对象在 finalize 中** | 对象 finalize 耗时较长，尚未真正释放 | `runFinalization()` 同步等待 |

---

## 第二层：核心原理深度解析 — ReferenceQueue 的 poll 机制

### 2.1 WeakReference 与 ReferenceQueue 协作原理

Java 的 `WeakReference` 构造函数支持传入一个 `ReferenceQueue`：

```java
ReferenceQueue<Object> queue = new ReferenceQueue<>();
WeakReference<Object> ref = new WeakReference<>(someObject, queue);
```

当 GC 确定 `someObject` **仅被弱引用可达** 时：

```
1. GC 清除 someObject 的强引用链
2. GC 将 someObject 标记为可回收
3. GC 将 ref 对象（不是 someObject！）enqueue 到 queue 中
4. 下次 queue.poll() 或 queue.remove() 将返回 ref
```

**关键认知**：进入 ReferenceQueue 的是 **WeakReference 对象本身**，而不是被弱引用包裹的对象。

### 2.2 ObjectWatcher 中的 poll 循环

```kotlin
// ObjectWatcher.kt — 核心 poll 逻辑（简化）
private fun removeWeaklyReachableObjects() {
    var ref: KeyedWeakReference?
    var removedCount = 0
    while (true) {
        // poll() 非阻塞：立即返回队首或 null
        ref = queue.poll() as KeyedWeakReference?
            ?: break
        removedCount++
        // 从监控 Map 中移除 → 该对象已安全回收
        watchedObjects.remove(ref.key)
    }
    return removedCount
}
```

**为什么用 poll() 而非 remove()？**

| 方法 | 行为 | 适用场景 |
|------|------|---------|
| `queue.poll()` | 立即返回队首元素，队列为空时返回 `null` | LeakCanary：主线程循环检查，不能阻塞 |
| `queue.remove()` | 阻塞等待直到有新元素入队 | 不适合 UI 线程，会导致 ANR |
| `queue.remove(timeout)` | 带超时的阻塞等待 | 可用于后台线程等待 |

### 2.3 为什么 poll 结果能可靠判断泄漏？

```
时间线：
T0: watch(activity) → 创建 KeyedWeakReference(activity, queue)
T1: activity.onDestroy() → 系统移除对 activity 的引用
T2: 主动触发 GC → GC 清除 activity
T3: 若 GC 成功：activity 的弱引用 ref 入队 → queue.poll() 不为 null ✓
    若 泄漏：activity 仍有强引用链 → ref 不入队 → queue.poll() 为 null ✗
```

**边界情况**：
- 若 5 次 GC 循环后 ref 仍未入队 → 高度疑似泄漏（概率 >99%）
- 若 5 秒等待后仍未入队 → **触发 HeapDump** 确认

---

## 第三层：Shark 的 ReferenceMatcher 系统 — 泄漏过滤体系

### 3.1 ReferenceMatcher 的分层设计

Shark 在分析 HPROF 时，并不是找到了 GC Root 路径就报泄漏，而是通过三层 `ReferenceMatcher` 系统过滤：

```
┌──────────────────────────────────────────────────────┐
│  HPROF 中所有对象（数十万个）                          │
│  └→ 疑似泄漏对象（数百个）                             │
│     └→ BFS 找到 GC Root 路径                          │
│        └→ ReferenceMatcher 过滤系统                    │
│           ├─ IgnoredReferenceMatcher（忽略节点）       │
│           │   └→ 该路径不被报告                       │
│           └─ LibraryLeakReferenceMatcher（库泄漏）     │
│              └→ 报告但标记为 Library Leak              │
└──────────────────────────────────────────────────────┘
```

### 3.2 AndroidReferenceMatchers — 内置系统泄漏忽略列表

Shark 内置了大量 Android 系统已知泄漏的匹配规则：

```kotlin
// shark-android/src/main/java/shark/AndroidReferenceMatchers.kt
enum class AndroidReferenceMatchers : ReferenceMatcher {
    // ── 输入法相关 ──
    INPUT_METHOD_MANAGER__M_CUR_ROOT_VIEW {
        // InputMethodManager.mCurRootView 持有已销毁 Activity 的 DecorView
        override fun match(node: LibraryLeakNode): Boolean =
            node.type == "android.view.inputmethod.InputMethodManager" &&
            node.field == "mCurRootView"
    },
    
    // ── Clipboard 相关 ──
    CLIPBOARD_UI_MANAGER__S_INSTANCE {
        // ClipboardManager 静态单例持有 Activity Context
        override fun match(node: LibraryLeakNode): Boolean =
            node.type == "android.sec.clipboard.ClipboardUIManager" &&
            node.field == "sInstance"
    },
    
    // ── Accessibility ──
    ACCESSIBILITY_NODE_INFO_MANAGER {
        // 无障碍服务持有 View 引用
        override fun match(node: LibraryLeakNode): Boolean =
            node.type == "android.view.accessibility.AccessibilityNodeInfoManager"
    },
    
    // ── AudioManager ──
    AUDIO_MANAGER__MCONTEXT_STATIC {
        override fun match(node: LibraryLeakNode): Boolean =
            node.type == "android.media.AudioManager" &&
            node.field == "mContext_static"
    },
    
    // ── 共 40+ 条匹配规则 ──
    // ...
}
```

### 3.3 匹配类型

| Matcher 类型 | 含义 | 报告行为 |
|-------------|------|---------|
| `IgnoredReferenceMatcher` | **完全忽略**该引用节点 → 整条路径不被报告 | 不显示 |
| `LibraryLeakReferenceMatcher` | 标记为**系统库泄漏** → 非应用代码导致 | 显示但归类为 Library Leak |
| 自定义 `ReferenceMatcher` | 业务层自定义过滤 | 由开发者决定 |

**面试亮点**：ReferenceMatcher 系统将「判定泄漏」和「过滤误报」解耦，允许开发者不断扩充忽略列表而不修改核心分析逻辑。这是**开闭原则**的经典实践。

### 3.4 构建自定义 ReferenceMatcher

```kotlin
// 注册自定义规则（在 Application.onCreate 中）
LeakCanary.config = LeakCanary.config.copy(
    referenceMatchers = AndroidReferenceMatchers.appDefaults + listOf(
        // 忽略第三方 SDK 的已知泄漏
        IgnoredReferenceMatcher(
            pattern = ReferencePattern.InstanceFieldPattern(
                className = "com.tencent.mm.sdk.openapi.WXApiImplV10",
                fieldName = "context"
            )
        ),
        // 标记为库泄漏（不忽略，但区分责任）
        LibraryLeakReferenceMatcher(
            pattern = ReferencePattern.StaticFieldPattern(
                className = "com.example.sdk.SdkManager",
                fieldName = "sInstance"
            ),
            description = "已知 SDK 单例未调用 release"
        )
    )
)
```

---

## 第四层：LeakCanary 检测全流程时序图

```
┌──────────┐  ┌──────────────────┐  ┌──────────────┐  ┌───────────────┐  ┌──────────────┐
│  App     │  │  ObjectWatcher   │  │  GC Trigger  │  │  HeapDumper   │  │ Shark Engine │
│  Code    │  │  (监控模块)      │  │  (主动GC)    │  │  (堆转储)     │  │  (分析引擎)  │
└────┬─────┘  └───────┬──────────┘  └──────┬───────┘  └───────┬───────┘  └──────┬───────┘
     │                │                    │                  │                  │
     │ watch(obj)     │                    │                  │                  │
     │───────────────>│                    │                  │                  │
     │                │                    │                  │                  │
     │                │ 1. 创建 KeyedWeakReference(obj, queue)                  │
     │                │─────────────────────────────────────────────────────────│
     │                │                    │                  │                  │
     │                │ 2. removeWeaklyReachableObjects()                        │
     │                │    while(queue.poll()!=null) { remove from map }         │
     │                │─────────────────────────────────────────────────────────│
     │                │                    │                  │                  │
     │  onDestroy()   │                    │                  │                  │
     │───────────────>│                    │                  │                  │
     │                │                    │                  │                  │
     │                │ 3. runGc()         │                  │                  │
     │                │───────────────────>│                  │                  │
     │                │                    │                  │                  │
     │                │                    │ repeat(5):       │                  │
     │                │                    │  Runtime.gc()    │                  │
     │                │                    │  runFinalization │                  │
     │                │                    │  Thread.sleep(100)                  │
     │                │                    │─────────────────>│                  │
     │                │                    │                  │                  │
     │                │ 4. removeWeaklyReachableObjects() 再检查                  │
     │                │    poll() → ref 是否入队？                                │
     │                │─────────────────────────────────────────────────────────│
     │                │                    │                  │                  │
     │                │ 5. ref 未入队 → 疑似泄漏                                 │
     │                │    延迟 5s 后再次检查（排除异步释放）                      │
     │                │                    │                  │                  │
     │                │ 6. 仍未被回收 → 确认泄漏                                 │
     │                │                    │                  │                  │
     │                │ 7. 触发 HeapDump   │                  │                  │
     │                │──────────────────────────────────────>│                  │
     │                │                    │                  │                  │
     │                │                    │     Debug.dumpHprofData(heapDumpFile)
     │                │                    │                  │──────────────────│
     │                │                    │                  │    .hprof 文件   │
     │                │                    │                  │                  │
     │                │ 8. 启动 Shark 分析                   │                  │
     │                │─────────────────────────────────────────────────────────│
     │                │                    │                  │                  │
     │                │                    │                  │  analyze(heapDump, leakingObjects)
     │                │                    │                  │                  │
     │                │                    │                  │  9. 解析 HPROF   │
     │                │                    │                  │     HprofParser   │
     │                │                    │                  │     └→ 构建对象图 │
     │                │                    │                  │                  │
     │                │                    │                  │  10. BFS 最短路径│
     │                │                    │                  │    ShortestPath   │
     │                │                    │                  │    Finder         │
     │                │                    │                  │    └→ LeakTrace[] │
     │                │                    │                  │                  │
     │                │                    │                  │  11. ReferenceMatcher 过滤
     │                │                    │                  │    忽略系统泄漏  │
     │                │                    │                  │                  │
     │                │ 12. 生成 HeapAnalysis 结果            │                  │
     │                │<─────────────────────────────────────────────────────────│
     │                │                    │                  │                  │
     │ 13. 发送通知 + 写入数据库          │                  │                  │
     │<───────────────│                    │                  │                  │
     │                │                    │                  │                  │
│    通知栏展示       │                    │                  │                  │
│    "MainActivity   │                    │                  │                  │
│     leaking 12MB"  │                    │                  │                  │
```

**关键时间节点**：

| 阶段 | 耗时 | 说明 |
|------|------|------|
| watch → GC 检测 | ~5-10s | 5 次 GC 循环 + 5s 等待延迟 |
| GC 检测 → HeapDump | ~1-3s | dump 文件写入磁盘（取决于堆大小） |
| HeapDump → 分析完成 | ~0.5-2s | Shark 解析 + BFS 遍历 |
| **总计** | **~8-15s** | 从调用 watch 到通知栏弹出 |

---

## 第五层：自定义泄漏规则

### 5.1 自定义 ObjectWatcher 监控范围

默认情况下，LeakCanary 2.x 自动监控 Activity/Fragment/ViewModel 等。可以通过配置扩展：

```kotlin
// Application.onCreate()
LeakCanary.config = LeakCanary.config.copy(
    // 监控自定义对象
    watchingDelegates = listOf(
        WatchingDelegates.activity,
        WatchingDelegates.fragment,
        WatchingDelegates.viewModel,
        WatchingDelegates.service,
        object : WatchingDelegate {
            override fun expectDeletionOnDestroy(
                target: Any,
                config: Config
            ): Boolean {
                // 自定义 View 也纳入监控
                if (target is CustomWebView) {
                    AppWatcher.objectWatcher.watch(
                        target, "CustomWebView should be released"
                    )
                    return true
                }
                return false
            }
        }
    )
)
```

### 5.2 手动 watch 自定义对象

```kotlin
class MyPresenter(private val view: MyView) {
    fun onDestroy() {
        // 手动监控：确保 Presenter 被正常回收
        AppWatcher.objectWatcher.watch(
            watchedObject = this,
            description = "MyPresenter should be GC'd when View is destroyed"
        )
    }
}
```

### 5.3 自定义 Reachability Inspector（可达性检查器）

```kotlin
// 自定义可达性判定规则
class CustomReachabilityInspectors : Reachability.Inspector {
    override val reachabilityInspectors: List<Reachability.Inspector> =
        listOf(
            // 将自定义引用类型也标记为「泄漏路径」
            object : Reachability.Inspector {
                override fun inspect(
                    graph: HprofHeapGraph,
                    node: HeapObject
                ): Reachability? {
                    if (node.instanceClassName == "com.example.WeakRefHolder") {
                        // 即使是通过自定义弱引用持有，也标记为泄漏
                        return Reachability.reachable("held by WeakRefHolder")
                    }
                    return null
                }
            }
        )
}

// 注册
LeakCanary.config = LeakCanary.config.copy(
    reachabilityInspectors = listOf(CustomReachabilityInspectors())
)
```

### 5.4 自定义 LeakInspector（泄漏检查器）

```kotlin
// 在 Shark 分析阶段注入自定义检查逻辑
class DatabaseLeakInspector : OnAnalyzedListener {
    override fun onHeapAnalyzed(heapAnalysis: HeapAnalysis) {
        if (heapAnalysis is HeapAnalysisSuccess) {
            for (leak in heapAnalysis.applicationLeaks) {
                // 识别数据库相关的泄漏
                if (leak.leakTraces.any { trace ->
                    trace.leakingObject.className.contains("SQLiteDatabase")
                }) {
                    // 发送到自定义监控平台
                    reportToFirebase(leak, "DATABASE_LEAK")
                }
            }
        }
    }
}

// 注册
LeakCanary.config = LeakCanary.config.copy(
    onHeapAnalyzedListeners = listOf(DatabaseLeakInspector())
)
```

---

## 第六层：线上 LeakCanary 裁剪与生产环境部署

### 6.1 为什么需要线上版本？

| 场景 | Debug 版本 | 线上版本 |
|------|-----------|---------|
| HeapDump 开销 | 可接受 | 不可接受（~1-3s 卡顿 + ~20-50MB 磁盘） |
| 分析线程 | 可阻塞 | 不可阻塞主流程 |
| 数据上报 | 本地通知栏 | 远程埋点 + 聚合分析 |
| 泄漏判定 | 5 次 GC + 5s 等待 | 轻量级：仅 watch + poll（不上报 HeapDump） |

### 6.2 条件编译：debugImplementation vs releaseImplementation

```kotlin
// build.gradle.kts
dependencies {
    // debug 版本：完整 LeakCanary
    debugImplementation("com.squareup.leakcanary:leakcanary-android:2.12")
    
    // release 版本：轻量级 no-op 或裁剪版
    releaseImplementation("com.squareup.leakcanary:leakcanary-android-no-op:2.12")
    
    // 或者：自定义线上裁剪版
    // releaseImplementation(project(":leakcanary-android-release"))
}
```

**`leakcanary-android-no-op` 原理**：所有方法为空实现，编译后无任何运行时开销，APK 增加 < 5KB。

### 6.3 自定义线上轻量版 LeakCanary

如果需要在线上**保留监控能力但不做 HeapDump**：

```kotlin
// ReleaseLeakCanary.kt
object ReleaseLeakCanary {
    private val queue = ReferenceQueue<Any>()
    private val watchedObjects = ConcurrentHashMap<String, KeyedWeakReference>()
    
    fun watch(obj: Any, description: String) {
        val key = UUID.randomUUID().toString()
        val ref = KeyedWeakReference(obj, key, description, queue)
        watchedObjects[key] = ref
        
        // 仅 poll 检测，不触发 GC（依赖系统自然 GC）
        CoroutineScope(Dispatchers.Default).launch {
            delay(30_000) // 30 秒后再检查
            
            // 移除已回收的对象
            while (true) {
                val ref = queue.poll() as? KeyedWeakReference ?: break
                watchedObjects.remove(ref.key)
            }
            
            // 仍存在的对象 → 上报元数据（不 dump）
            if (watchedObjects.containsKey(key)) {
                reportLeakMetadata(
                    className = obj.javaClass.name,
                    description = description,
                    deviceInfo = Build.MODEL
                )
            }
        }
    }
    
    private fun reportLeakMetadata(className: String, description: String, deviceInfo: String) {
        // 发送到 Firebase / 自建埋点平台
        // 只上报泄漏的类名 + 设备信息，不上传整个 HeapDump
        FirebaseAnalytics.getInstance().logEvent("leak_detected") {
            param("class", className)
            param("description", description)
            param("device", deviceInfo)
        }
    }
}
```

### 6.4 线上版本配置对比

| 方案 | HeapDump | GC 触发 | 性能开销 | 信息量 | 适用场景 |
|------|---------|---------|---------|--------|---------|
| **完整版** | ✅ | ✅ 5 次循环 | 高（~15s 卡顿） | 完整引用链 | Debug / 内测 |
| **No-Op** | ❌ | ❌ | 零 | 零 | 正式发布 |
| **轻量版（自建）** | ❌ | ❌ | 极低（<1ms） | 类名 + 次数 | 线上灰度 / 线上监控 |
| **HeapDump 采样** | ✅（1% 采样） | ✅ | 低（按采样率） | 完整引用链 | 线上全量（需后端存储） |

### 6.5 线上 HeapDump 采样方案

```kotlin
// 仅 1% 用户执行完整 HeapDump
object SamplingLeakCanary {
    private const val DUMP_SAMPLE_RATE = 0.01 // 1%
    
    fun shouldDumpHeap(): Boolean {
        // 使用用户 ID hash 保证同一用户行为一致
        val userId = getUserId()
        return (userId.hashCode() and 0x7FFFFFFF).toDouble() / Int.MAX_VALUE < DUMP_SAMPLE_RATE
    }
    
    fun onLeakDetected(leakInfo: LeakInfo) {
        if (shouldDumpHeap()) {
            // 1% 用户：执行完整 HeapDump 并上传
            val heapDumpFile = HeapDumper.dump()
            uploadHeapDump(heapDumpFile)
        } else {
            // 99% 用户：仅上报元数据
            reportLightweightData(leakInfo)
        }
    }
}
```

### 6.6 线上泄漏聚合分析

```
客户端上报（轻量元数据）               服务端聚合
┌─────────────────────┐         ┌─────────────────────────┐
│ Device: Pixel 7     │         │ Top Leaking Classes:    │
│ Class: MainActivity │   ───>  │ 1. MainActivity  (12,345)│
│ OOM: false          │         │ 2. WebView       (8,721) │
│ Timestamp: 1715...  │         │ 3. DialogFragment(3,201) │
└─────────────────────┘         │                         │
                                │ ── 触发告警 ──          │
                                │ MainActivity 泄漏率      │
                                │ 超过 0.5% 阈值           │
                                └─────────────────────────┘
```

---

## 附录：LeakCanary 关键类速查表

| 包/类 | 层级 | 职责 |
|-------|-----|------|
| `AppWatcher` | 入口 | 配置入口，持有 `ObjectWatcher` 实例 |
| `ObjectWatcher` | 监控核心 | 创建 `KeyedWeakReference`，poll `ReferenceQueue`，触发 GC，判定泄漏 |
| `KeyedWeakReference` | 监控辅助 | 携带 Key + Description 的 WeakReference 子类 |
| `GcTrigger` | GC 触发 | `Runtime.gc()` + `runFinalization()` + 5 次循环 |
| `HeapDumper` | 堆转储 | `Debug.dumpHprofData()` 写入磁盘 |
| `HeapAnalyzer` | 分析入口 | 协调 Shark 引擎分析 HPROF 文件 |
| `HprofParser` | HPROF 解析 | 将二进制 HPROF 解析为内存对象图 |
| `ShortestPathFinder` | 路径查找 | BFS 查找 GC Root → 泄漏对象的最短路径 |
| `ReferenceMatcher` | 过滤系统 | 过滤系统库已知泄漏（Ignored / LibraryLeak） |
| `AndroidReferenceMatchers` | 内置规则 | 40+ 条 Android 系统泄漏忽略规则 |
| `LeakTrace` | 结果数据 | 一条完整的 GC Root → 泄漏对象引用链 |
| `HeapAnalysisSuccess` | 分析结果 | 分析成功的结果，含 `applicationLeaks` 和 `libraryLeaks` |
| `LeakCanary.Config` | 全局配置 | dumpHeap, retainedVisibleThreshold, referenceMatchers 等 |

---

## 总结：面试回答模板

当被问到「说说你对 LeakCanary 的理解」，可按以下结构回答：

```
1. 【总述】LeakCanary 是 Square 开源的 Android 内存泄漏检测库，
   核心原理是 WeakReference + ReferenceQueue + 主动 GC + HeapDump 四步法。

2. 【检测算法】watch() → 创建 KeyedWeakReference → 5 次循环 GC →
   poll ReferenceQueue → 未入队即疑似泄漏 → 延迟 5s 后仍存在 → 触发 HeapDump。

3. 【Shark 引擎】自研 Kotlin HPROF 解析器，比老 HAHA 快 6× 省 10× 内存；
   BFS 查找最短泄漏路径；ReferenceMatcher 过滤系统库泄漏。

4. 【2.0 架构】拆分为 ObjectWatcher（监控）+ Shark（分析），
   关注点分离，可独立裁剪独立迭代。

5. 【线上实践】release 用 no-op 或轻量版仅上报类名，
   1% 采样 HeapDump，服务端聚合分析 + 阈值告警。
```

---

> **参考资料**：[LeakCanary 官方文档](https://square.github.io/leakcanary/) | [源码仓库](https://github.com/square/leakcanary) | [Shark 设计文档](https://square.github.io/leakcanary/shark/)
