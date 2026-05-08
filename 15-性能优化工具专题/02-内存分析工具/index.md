# Android 内存分析工具 - 面试深度解析

> 本文档按照六层递进结构组织，覆盖从面试高频考点到底层原理、再到实战案例的完整知识体系。

---

## 目录

1. [面试高频考点（5+ 问）](#1-面试高频考点5-问)
2. [HPROF 格式与 MAT OQL](#2-hprof-格式与-mat-oql)
3. [LeakCanary Shark 解析引擎](#3-leakcanary-shark-解析引擎)
4. [LeakCanary 检测时序图](#4-leakcanary-检测时序图)
5. [实战：Memory Profiler + MAT 定位 Fragment 泄漏](#5-实战memory-profiler--mat-定位-fragment-泄漏)
6. [扩展阅读与参考资料](#6-扩展阅读与参考资料)

---

## 1. 面试高频考点（5+ 问）

### 1.1 Memory Profiler 的 Shallow Heap vs Retained Heap

**面试问题：** "在 Android Studio 的 Memory Profiler 中，Shallow Heap 和 Retained Heap 分别代表什么含义？如何利用它们定位内存泄漏？"

#### Shallow Heap（浅堆）

- **定义：** 对象自身占用的内存大小，不包括它引用的其他对象。
- **计算方式：** 对象头（Object Header）+ 实例字段（Instance Fields）的总和。
  - 32位JVM：对象头8字节 + 压缩引用4字节 = 12字节头
  - 64位JVM（无压缩）：对象头16字节
  - Android ART：类似64位无压缩，对象头通常16字节
- **典型值举例：**
  - `Object`：仅对象头，shallow size ≈ 16 bytes
  - `byte[1024]`：对象头 + 数组长度字段(4) + 1024字节 = ~1044 bytes
  - `String`：对象头 + `char[]`引用(8) + `hash`(4) + 对齐 ≈ 32 bytes（不含char[]本身）

#### Retained Heap（保留堆）

- **定义：** 该对象被GC回收后，能够被同时释放的所有对象占用的**总内存**。
- **核心含义：** Retained Heap = Shallow Heap + 仅通过该对象可到达的所有子对象的 Shallow Heap 之和。换句话说，这张"独有引用图"中所有对象的 Shallow 总和。
- **计算依赖：** 基于 Dominator Tree（支配树）计算。如果一个对象A被释放后，对象B就变成不可达（即B只被A引用），那么B的Shallow Heap也计入A的Retained Heap。
- **面试关键理解：** 如果多个对象共同引用B，那么B的Retained Heap不计入任何一个父对象——只有"独占引用"才参与计算。

#### 面试真题延伸

**Q：一个 Activity 的 Retained Heap 很大，但 Shallow Heap 很小，说明什么？**

> **A：** 说明该 Activity 本身不占多少内存（可能只有几十字节），但它持有了大量独占引用的子对象（如大Bitmap、大型集合、子View树等）。一旦Activity泄漏，这些子对象都无法释放，造成严重的内存浪费。这正是 Memory Profiler 中我们需要关注 Retained Size 的原因——它反映了"修复这个泄漏能回收多少内存"。

**Q：以下代码，每个对象的 Shallow 和 Retained Heap 各是多少？**

```java
class Node {
    byte[] data = new byte[1024 * 1024]; // 1MB
    Node child;
}

Node a = new Node();  // a.child = null
Node b = new Node();  // b.child = null
```

> **A：** 
> - `a`：Shallow ≈ 24B（对象头+引用字段），Retained ≈ 1MB + 24B（独占data数组）
> - `b`：同理 ≈ 1MB + 24B
> - `a.data` 和 `b.data`：Shallow ≈ 1MB，Retained ≈ 1MB（各自独享）

---

### 1.2 LeakCanary 的检测算法（WeakReference + GC + HeapDump）

**面试问题：** "LeakCanary 是如何检测内存泄漏的？请描述其核心算法流程。"

#### 核心原理：基于弱引用的"存活检测"

LeakCanary 1.x 和 2.x 的核心检测算法本质相同，概括为三个阶段：

```
阶段1：创建弱引用 → 阶段2：主动触发GC → 阶段3：检查引用是否被清除
```

#### 详细步骤

**Step 1 — 注册观察对象：**

当 Activity / Fragment / View 等被销毁（`onDestroy`）时，LeakCanary 创建一个 `KeyedWeakReference` 包装该对象：

```kotlin
// LeakCanary 内部逻辑（简化）
val reference = KeyedWeakReference(
    watchedObject,  // 被观察对象，如 Activity
    key,            // 唯一标识
    description,    // "MainActivity 已销毁"
    watchUptimeMillis
)
```

关键点：使用 `WeakReference` 意味着被观察对象一旦失去强引用，GC就能回收它，同时 `WeakReference` 的 referent 会被置为 `null`。

**Step 2 — 主动触发 GC：**

调用 `Runtime.getRuntime().gc()` 无法保证一定触发GC。LeakCanary 采用更激进的方式：

```kotlin
// 在 LeakCanary 中触发 GC
private fun runGc() {
    Runtime.getRuntime().gc()
    enqueueReferences()
    System.runFinalization()
}
```

Android 5.0+ 还支持通过 `VMRuntime.getRuntime().requestConcurrentGC()` 请求并发GC。如果弱引用的 referent 在GC后仍不为 null，说明对象还有强引用路径（即"泄漏"了）。

**Step 3 — 如果泄漏：拉取 Heap Dump：**

确认泄漏后，LeakCanary 调用 `Debug.dumpHprofData(path)` 拉取当前堆的快照并启动 **Shark** 解析引擎进行分析。

#### LeakCanary 2.x 的改进

- **2.x 使用 Shark 替换了原来的 HAHA 解析库**，解析速度提升数倍
- 在单独进程中进行 heap dump 分析，避免主进程 OOM
- 支持动态开启/关闭、可配置保留 heap dump 数量

#### 面试中的常见追问

**Q：WeakReference 和 ReferenceQueue 是如何配合的？**

> **A：** `WeakReference` 构造时可以传入一个 `ReferenceQueue`。当GC回收弱引用指向的对象时，JVM会将该 `WeakReference` 对象本身放入 `ReferenceQueue`。LeakCanary 通过检查 referent 是否为 null 或是否已入队来判断对象是否存活。如果GC后 referent 仍不为 null 且未入队 → 泄漏。

**Q：为什么需要主动触发 GC？多次 GC 可以吗？**

> **A：** 因为 `System.gc()` 只是"建议"JVM执行GC，不保证立即执行。对于热点对象（刚被销毁的Activity可能还在新生代），可能需要多次GC才能晋升到老年代并被回收。LeakCanary 会重试最多5次GC，每次间隔100ms，确保垃圾真正被回收后再判断。

---

### 1.3 MAT 的 Dominator Tree 和 Path to GC Roots

**面试问题：** "在 Eclipse MAT 中，Dominator Tree 和 Path to GC Roots 分别解决什么问题？"

#### Dominator Tree（支配树）

- **支配关系定义：** 在有向图中，节点A支配节点B当且仅当：从根（GC Roots）出发到B的**每一条路径**都必须经过A。
- **直观理解：** A是B的唯一"大老板"，B的生死完全由A决定。如果你干掉A，B就彻底无人引用了。
- **MAT 中的应用：**
  - 在 Dominator Tree 视图中，每个节点的子节点都是"以它为最近支配者"的对象
  - **Retained Heap 的计算依据**：某个节点的 Retained Heap = 其自身 Shallow Heap + 其所有子节点在 Dominator Tree 中的 Shallow Heap 总和
  - 面试中可强调：Dominator Tree 的根是虚拟的"Super Root"，指向所有 GC Roots

- **典型分析场景：** 在 Histogram 中找到某个类的实例数量异常多 → 右键 "List objects → with outgoing references" → 在 Dominator Tree 中定位最大的 Retained Heap 持有者

#### Path to GC Roots（到GC根的路径）

- **功能：** 展示某个对象**为什么没有被回收**——显示从 GC Roots 到该对象的最短强引用链。
- **排除选项：**
  - `exclude weak references`：排除弱引用路径（默认开启），因为弱引用不会阻止GC
  - `exclude soft references`：排除软引用路径
  - `exclude phantom references`：排除虚引用路径
- **MAT 中的关键路径类型：**
  - **System Class**：由类加载器持有，通常是静态字段导致的泄漏
  - **Thread**：由活跃线程持有，常见于匿名内部类/Runnable
  - **JNI Local / JNI Global**：native层持有，常见于跨语言调用未释放
  - **Finalizer**：对象重写了 `finalize()` 且正在等待执行

- **面试真题：**

**Q：你在 MAT 中看到一条链 "this$0 → Activity"，说明什么？**

> **A：** `this$0` 是 Java 编译器为非静态内部类自动生成的字段，指向外部类实例。说明存在一个非静态内部类（如匿名Runnable、Handler、Listener）持有外部Activity的引用。如果这个内部类的实例生命周期长于Activity（如被静态变量持有、被后台线程持有），就会导致Activity泄漏。解决方式：将内部类改为静态内部类 + WeakReference。

---

### 1.4 HPROF 文件的分析方法（转 MAT 格式）

**面试问题：** "Android 导出的 hprof 文件能否直接在 MAT 中打开？如果不能，如何处理？"

#### Android HPROF vs Java HPROF

Android 的 heap dump 格式基于 Apache Harmony 的 HPROF 实现，与标准 Java SE HPROF（基于 J2SE）**格式不同**：

| 特性 | Android HPROF | Java SE HPROF |
|------|--------------|---------------|
| 标识符大小 | 4字节 | 4或8字节（取决于平台） |
| Record Tag | 部分自定义 | 标准JDK定义 |
| 类型表示 | ART/Dalvik特有 | JVM标准 |
| 压缩 | 通常未压缩 | 可选gzip |

#### 转换方法

**方法一：使用 hprof-conv 工具（Android SDK 自带）**

```bash
# hprof-conv 位于 Android SDK 的 platform-tools 目录
hprof-conv input.hprof output.hprof

# 示例：转换应用导出的 heap dump
hprof-conv memory_dump.hprof mat_compatible.hprof
```

- `hprof-conv` 将 Android 格式的 HPROF 转换为标准 Java SE HPROF 格式
- 转换后文件可以直接在 Eclipse MAT、jhat、VisualVM 等工具中打开
- 文件大小可能会略有变化（标识符对齐等原因）

**方法二：使用 Android Studio 直接导出**

Android Studio 3.0+ 的 Memory Profiler 在导出时会自动调用转换：

```
Memory Profiler → 点击"导出 Heap Dump" → 自动生成 MAT 兼容的 .hprof 文件
```

**方法三：使用 LeakCanary 自动分析**

LeakCanary 2.x 内建 Shark 引擎，可以直接解析 Android HPROF 格式，无需转换。

#### 面试深度追问

**Q：如果不转换直接在 MAT 中打开会发生什么？**

> **A：** MAT 会报错或解析出错误的数据。因为 Android HPROF 中的 Record Tag 值（如 `HPROF_GC_ROOT_THREAD_OBJECT` = 0x08）与标准 HPROF 定义不同，MAT 会将其识别为未知记录类型并跳过，导致分析结果缺失关键引用链。

**Q：hprof-conv 的内部原理是什么？**

> **A：** hprof-conv 本质上做以下工作：
> 1. 重新计算并更新 Record Header 的长度和 Tag 值，映射 Android Record Tag → Java SE Record Tag
> 2. 将 4 字节标识符扩展或重新编码为与目标格式兼容
> 3. 补充缺失的标准 HPROF 头信息（如 ID size、timestamp）
> 4. 处理 ART 特有的数据类型（如 ART internal types）的映射

---

### 1.5 线上内存监控（KOOM 的实现原理）

**面试问题：** "如果不用 LeakCanary，如何在线上监控 Android App 的内存泄漏？请描述 KOOM 的实现原理。"

#### KOOM（Kwai OOM）简介

KOOM 是快手开源的高性能线上内存监控方案，核心设计目标：**对性能影响极小（<1% CPU）、可线上部署、支持 OOM 前自动 dump**。

#### 核心实现原理

**1. 内存阈值检测机制**

KOOM 通过周期性轮询（默认每5秒）检测内存状态：

```kotlin
// KOOM 检测逻辑（简化）
class MonitorRunnable : Runnable {
    override fun run() {
        val heapInfo = getHeapInfo()         // 获取当前堆内存信息
        if (heapInfo.used > THRESHOLD) {     // 超过阈值（默认80%）
            dumpAndReport()                   // 触发dump
        }
        handler.postDelayed(this, 5000)      // 继续下一轮
    }
}
```

使用 `Debug.MemoryInfo` 和 `Runtime.getRuntime()` 获取：
- **PSS**（Proportional Set Size）：进程实际使用的物理内存
- **Java Heap**：Dalvik/ART堆的 used/max
- **Native Heap**：native层分配的内存

**2. 高性能 Fork Dump**

这是 KOOM 最核心的设计——**在子进程中 dump，不阻塞主进程**：

```
主进程 (App)                       子进程 (fork出来的)
    │                                  │
    │  fork() (copy-on-write)          │
    ├──────────────────────────────────>│
    │  (继续正常运行)                   │ Debug.dumpHprofData()
    │                                  │  ├─ 解析HPROF
    │                                  │  ├─ 分析泄漏链
    │                                  │  └─ 上报结果
    │  waitpid()回收子进程              │  进程退出
    │<──────────────────────────────────│
```

关键优势：
- **fork() 利用 Copy-On-Write**：fork瞬间内存几乎无额外开销，子进程与父进程共享内存页
- **子进程 dump 期间主进程不受影响**：用户无感知
- **子进程 dump 完成后立即退出**：不占用额外资源

**3. 内存泄漏判定策略**

KOOM 不依赖弱引用 + GC 方式（开销大），而是采用**镜像对比**策略：

```
当前镜像 vs 基线镜像（如App启动后5分钟的heap dump）
    → 比较各Activity/Fragment的实例数量
    → 实例数持续增长 → 判定泄漏
```

**4. 测试支持（test模块）**

```kotlin
// KOOM 提供各种模拟泄漏场景
class LeakMaker {
    // 静态持有Activity
    fun makeActivityLeak(activity: Activity) {
        Holder.sLeakedActivity = activity
    }
    // Handler内部类泄漏
    fun makeHandlerLeak(activity: Activity) { ... }
    // 单例持有Context
    fun makeSingletonLeak(context: Context) { ... }
}
```

#### 面试真题

**Q：KOOM 和 LeakCanary 的设计差异有哪些？**

| 维度 | LeakCanary | KOOM |
|------|-----------|------|
| 检测时机 | 对象销毁时（onDestroy） | 周期性内存阈值检测 |
| 检测方式 | WeakReference + GC | 内存阈值 + 镜像对比 |
| Dump方式 | 主进程 dump（阻塞） | fork子进程 dump |
| 适用场景 | 开发/测试阶段 | 线上环境 |
| 性能影响 | 较大（GC + dump阻塞UI） | 极小（<1% CPU） |
| 泄漏判定 | 精确（单对象可达性） | 启发式（实例数增长趋势） |

**Q：fork 子进程 dump 有什么风险？**

> **A：** 
> 1. **虚拟内存翻倍风险**：虽然 COW 下物理内存几乎不增加，但 fork 后虚拟内存地址空间翻倍，可能触发 OOM Killer。KOOM 通过 `pthread_atfork` 优化。
> 2. **文件描述符继承**：子进程会继承父进程的 fd，KOOM 需要在 fork 后关闭不需要的 fd。
> 3. **多线程问题**：fork 后子进程只有当前线程（fork的调用线程），其他线程的锁状态不可预知。KOOM 通过独立进程 + IPC 解决。

---

## 2. HPROF 格式与 MAT OQL

### 2.1 HPROF 二进制格式详解

HPROF（Heap/CPU Profiling Tool）是 JVM 标准化的 heap dump 格式。Android 基于 Apache Harmony 实现了一套兼容格式。

#### 文件结构

```
┌─────────────────────────────────────┐
│  HPROF Header                       │
│  ├─ Format String: "JAVA PROFILE 1.0.1/2"│
│  ├─ ID Size: 4 (Android) 或 8       │
│  └─ Timestamp                       │
├─────────────────────────────────────┤
│  Record #1                          │
│  ├─ Tag (1 byte)                    │
│  ├─ Time (4 bytes)                  │
│  ├─ Length (4 bytes)                │
│  └─ Data (Length bytes)             │
├─────────────────────────────────────┤
│  Record #2 ...                      │
│  ...                                │
├─────────────────────────────────────┤
│  Record #N                          │
└─────────────────────────────────────┘
```

#### 关键 Record 类型

| Tag | 名称 | 描述 |
|-----|------|------|
| 0x01 | STRING | UTF-8字符串常量池 |
| 0x02 | LOAD CLASS | 已加载类的信息 |
| 0x04 | STACK FRAME | 栈帧信息 |
| 0x05 | STACK TRACE | 完整堆栈跟踪 |
| 0x07 | HEAP DUMP SEGMENT | 包含大量子标签，核心数据 |
| 0x0A | UNLOAD CLASS | 已卸载的类 |
| 0x0C | CPU SAMPLES | CPU采样数据 |
| 0x1C | HEAP DUMP | 堆转储（主数据块） |
| 0x2C | HEAP SUMMARY | 堆摘要信息 |

#### HEAP DUMP SEGMENT 内部结构

HEAP DUMP 是一个复合记录，内部包含多个子记录：

```
HEAP DUMP (Tag 0x1C) {
    ROOT_UNKNOWN            (0xFF)     // GC Root: 未知根
    ROOT_JNI_GLOBAL         (0x01)     // GC Root: JNI全局引用
    ROOT_JNI_LOCAL          (0x02)     // GC Root: JNI局部引用
    ROOT_JAVA_FRAME         (0x03)     // GC Root: Java栈帧
    ROOT_NATIVE_STACK       (0x04)     // GC Root: Native栈
    ROOT_STICKY_CLASS       (0x05)     // GC Root: 系统类
    ROOT_THREAD_BLOCK       (0x06)     // GC Root: 线程阻塞引用
    ROOT_MONITOR_USED       (0x07)     // GC Root: 监视器
    ROOT_THREAD_OBJECT      (0x08)     // GC Root: 线程对象
    ROOT_INTERNED_STRING    (0x89)     // GC Root: 内部化字符串
    ROOT_FINALIZING         (0x8A)     // GC Root: 等待finalize的对象
    ROOT_VM_INTERNAL        (0xFE)     // GC Root: VM内部
    
    CLASS_DUMP              (0x20)     // 类定义(静态字段值等)
    INSTANCE_DUMP           (0x21)     // 实例对象
    OBJECT_ARRAY_DUMP       (0x22)     // 对象数组
    PRIMITIVE_ARRAY_DUMP    (0x23)     // 基本类型数组
}
```

#### 解析流程示意

```
HPROF文件 → 按Record顺序读取
  → STRING: 建立 StringID → 字符串值 的映射表
  → LOAD CLASS: 建立 ClassID → Class对象ID 的映射
  → HEAP DUMP:
      → CLASS_DUMP: 解析静态字段引用关系
      → INSTANCE_DUMP: 解析实例字段引用关系
      → OBJECT_ARRAY_DUMP: 解析数组元素引用关系
      → GC ROOT: 建立引用分析的起点
  → 构建完整的对象图 → 可达性分析
```

### 2.2 MAT 的 OQL 查询语言

OQL（Object Query Language）是 MAT 提供的类SQL查询语言，用于在 heap dump 中精确查找对象。

#### 基本语法

```sql
-- 查询某个类的所有实例
SELECT * FROM com.example.MyActivity

-- 带条件查询
SELECT * FROM android.graphics.Bitmap 
WHERE width > 1024 AND height > 1024

-- 查询对象字段值
SELECT s.mText, s.mWidth, s.mHeight 
FROM android.widget.TextView s
WHERE s.mText != null

-- 聚合查询
SELECT COUNT(*) FROM java.lang.String

-- 多表关联
SELECT a, b FROM com.example.MainActivity a, 
              android.graphics.Bitmap b
WHERE a.mBitmapField = b
```

#### 实用 OQL 查询示例

**1. 查找所有已泄漏的 Activity：**

```sql
SELECT * FROM INSTANCEOF android.app.Activity
```

**2. 查找引用了 Activity 的非静态内部类：**

```sql
SELECT * FROM java.lang.Object 
WHERE (object.toString().contains("$"))
```

**3. 查找大对象（Retained Heap 排序）：**

```sql
SELECT * FROM java.lang.Object 
WHERE @retainedHeapSize > 1048576  -- 1MB
```

**4. 查找特定类的静态字段持有者：**

```sql
SELECT * FROM com.example.MySingleton 
WHERE @GCRoot = object
```

**5. 查找 String 重复值：**

```sql
SELECT toString(s), COUNT(*) 
FROM java.lang.String s 
GROUP BY toString(s) 
HAVING COUNT(*) > 100
```

#### OQL 实用函数

| 函数 | 说明 |
|------|------|
| `@retainedHeapSize` | 对象的 Retained Heap 大小 |
| `@shallowHeapSize` | 对象的 Shallow Heap 大小 |
| `@GCRoot` | GC Root 路径 |
| `@objectId` | 对象唯一ID |
| `toString(obj)` | 转字符串 |
| `INSTANCEOF` | 类型判断（含子类） |

---

## 3. LeakCanary Shark 解析引擎

### 3.1 Shark 概述

Shark 是 LeakCanary 2.x 的 Kotlin 编写的 HPROF 解析引擎，取代了旧版基于 HAHA（perflib）的解析方案。

**核心设计优势：**

1. **内存映射（Memory-Mapped）解析**：使用 `RandomAccessFile` + `MappedByteBuffer`，不将整个 HPROF 加载到内存
2. **索引优先（Index-First）**：先扫描 HPROF 建立索引（对象ID→位置映射），再按需读取
3. **增量解析**：只解析泄漏分析需要的部分，而非整个堆
4. **Kotlin 协程**：解析过程可取消、可超时

### 3.2 Shark 核心组件

```
┌──────────────────────────────────────────────────┐
│                   Shark 架构                       │
├──────────────────────────────────────────────────┤
│  HprofReader       → 底层HPROF二进制读取           │
│  HprofHeader        → HPROF文件头解析              │
│  HprofIndex         → 对象ID→文件偏移量索引         │
│  HprofGraph         → 内存中的对象引用图            │
│  ReferenceMatcher   → 已知泄漏模式匹配器            │
│  LeakTrace          → 最短泄漏路径计算              │
│  HeapAnalyzer       → 堆分析器（核心入口）          │
└──────────────────────────────────────────────────┘
```

### 3.3 Shark 解析流程

```kotlin
// Shark 核心分析流程（简化）
fun analyze(heapDumpFile: File): HeapAnalysis {
    // 1. 解析HPROF头
    val header = HprofHeader.parse(heapDumpFile)
    
    // 2. 建立索引（ID → 文件偏移量）
    val index = HprofIndex.indexRecordsOf(heapDumpFile)
    
    // 3. 构建引用图（按需构建）
    val graph = HprofGraph.open(heapDumpFile, index)
    
    // 4. 查找泄漏对象
    val leakingObjects = graph.findLeakingObjects()
    
    // 5. 计算最短泄漏路径（BFS）
    val leakTraces = leakingObjects.map { obj ->
        graph.shortestPathToGcRoots(obj)
    }
    
    // 6. 返回分析结果
    return HeapAnalysis(leakTraces)
}
```

### 3.4 泄漏路径计算算法

Shark 使用 **BFS（广度优先搜索）** 计算从 GC Roots 到泄漏对象的最短引用路径：

```
目标：找到从 GC Root → ... → 泄漏对象的最短路径
数据结构：Queue + Visited Set
限制：最大遍历深度可配置（默认 ShortestPathFinder）
剪枝：已知的已知泄漏模式（如 InputMethodManager）通过 ReferenceMatcher 排除
```

### 3.5 ReferenceMatcher — 系统级"伪泄漏"过滤

Android Framework 本身存在一些"有意为之"的单例持有模式，LeakCanary 通过 ReferenceMatcher 标记为"已知无害"：

```kotlin
// 内置的 IgnoredReferenceMatcher 示例
AndroidReferenceMatchers.appDefaults = listOf(
    // InputMethodManager 持有上个 Activity 的 DecorView
    // 这是系统行为，下次使用时会被替换
    IgnoredReferenceMatcher(
        pattern = "android.view.inputmethod.InputMethodManager",
        description = "InputMethodManager 持有已销毁Activity的引用是正常行为"
    ),
    // AccessibilityManager 的 sInstance
    IgnoredReferenceMatcher(
        pattern = "android.view.accessibility.AccessibilityManager",
        ...
    )
)
```

---

## 4. LeakCanary 检测时序图

### 4.1 完整检测流程

```
┌──────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────┐
│  App     │     │  LeakCanary  │     │   Shark      │     │  Filter  │
│  Process │     │  Watcher     │     │   Engine     │     │  Engine  │
└────┬─────┘     └──────┬───────┘     └──────┬───────┘     └────┬─────┘
     │                  │                    │                  │
     │ 1. onDestroy()   │                    │                  │
     │─────────────────>│                    │                  │
     │                  │                    │                  │
     │                  │ 2. 创建 KeyedWeakReference           │
     │                  │    (referenceQueue)                  │
     │                  │                    │                  │
     │                  │ 3. 延迟 5 秒        │                  │
     │                  │    (等待GC)         │                  │
     │                  │                    │                  │
     │                  │ 4. 主动触发 GC       │                  │
     │                  │    Runtime.gc()    │                  │
     │                  │    System.runFinalization()           │
     │                  │    (最多重试 5 次)  │                  │
     │                  │                    │                  │
     │                  │ 5. 检查 WeakReference│                │
     │                  │    .get() == null? │                  │
     │                  │                    │                  │
     │                  │  [如果 null]       │                  │
     │                  │   ✅ 未泄漏，结束   │                  │
     │                  │                    │                  │
     │                  │  [如果非 null]     │                  │
     │                  │   ❌ 疑似泄漏       │                  │
     │                  │                    │                  │
     │                  │ 6. Debug.dumpHprofData()             │
     │                  │─────────────────>│                  │
     │                  │   .hprof 文件     │                  │
     │                  │                    │                  │
     │                  │                    │ 7. 解析 HPROF    │
     │                  │                    │    建立索引       │
     │                  │                    │                  │
     │                  │                    │ 8. 查找泄漏对象   │
     │                  │                    │    BFS 最短路径   │
     │                  │                    │                  │
     │                  │                    │ 9. 泄漏路径列表   │
     │                  │                    │──────────────────>│
     │                  │                    │                  │
     │                  │                    │     10. 应用 ReferenceMatcher
     │                  │                    │         过滤已知无害泄漏
     │                  │                    │                  │
     │                  │                    │     11. 分类      │
     │                  │                    │     Library Leak │
     │                  │                    │     App Leak     │
     │                  │                    │<─────────────────│
     │                  │                    │                  │
     │                  │ 12. 生成分析报告    │                  │
     │                  │<─────────────────│                  │
     │                  │                    │                  │
     │ 13. 显示通知      │                    │                  │
     │<─────────────────│                    │                  │
     │                  │                    │                  │
```

### 4.2 关键时间节点

| 阶段 | 耗时范围 | 备注 |
|------|---------|------|
| onDestroy → 创建 WeakReference | < 1ms | 几乎无开销 |
| 等待 + GC 重试 | 5s ~ 8s | LeakCanary 2.x 默认等待5秒后触发GC |
| Heap Dump | 2s ~ 15s | 取决于堆大小，期间App可能卡顿 |
| Shark 解析（子进程） | 1s ~ 5s | 2.x 在单独进程解析，不阻塞主进程 |
| 报告生成 | < 500ms | 文本/HTML 报告 |

### 4.3 LeakCanary 2.x 进程模型

```
┌──────────────────────┐      ┌──────────────────────┐
│   主进程 (App)        │      │   :leakcanary 子进程  │
│                      │      │                      │
│  ObjectWatcher       │      │  Shark 解析引擎       │
│  HeapDumper          │      │  HeapAnalyzerService  │
│  (Debug.dumpHprof)   │      │  (解析 .hprof)       │
│        │             │      │        │             │
│        │  写入文件     │      │        │             │
│        ├─────────────┼──────┼────────>              │
│        │ .hprof       │      │  读取分析  │             │
│        │             │      │        │             │
│        │             │      │        │ 分析结果     │
│        │<────────────┼──────┼─────────              │
│        │ 结果通知      │      │                      │
└──────────────────────┘      └──────────────────────┘
```

---

## 5. 实战：Memory Profiler + MAT 定位 Fragment 泄漏

### 5.1 场景设定

假设我们有一个新闻阅读 App，用户在 ViewPager 中浏览新闻详情。QA 反馈：来回切换 Fragment 页面约20次后，App 出现明显卡顿，内存使用持续上升。

### 5.2 使用 Memory Profiler 发现泄漏

**Step 1 — 录制内存分配**

1. 打开 Android Studio → View → Tool Windows → Profiler
2. 选择目标设备和进程 → 点击 Memory Profiler
3. 在 App 中操作：反复进入/退出新闻详情 Fragment（约10次）
4. 观察 Memory 时间线：如果每次进出后内存没有回落到基线，而是阶梯式上升，则大概率泄漏

**Step 2 — 手动 GC 并观察**

在 Memory Profiler 中点击 **Garbage Collection** 按钮（垃圾桶图标）。如果 GC 后内存曲线仍有显著"台阶"（比基线高出数十MB），说明有对象没有被回收。

**Step 3 — 捕捉 Heap Dump**

点击 **Dump Java Heap** 按钮，获取当前堆快照。

**Step 4 — 在 Memory Profiler 中初步分析**

- 切换到 **Arrange by package** 视图
- 找到 `com.example.news` 包
- 观察 `NewsDetailFragment` 的 **Allocations** 列和 **Shallow Size**

**关键发现指标：**

```
NewsDetailFragment 实例数 = 12（但我们只打开了1个！）
→ 说明前11个 Fragment 实例没有被回收
→ 每个实例 Retained Size ≈ 15MB（包含WebView/RecyclerView/图片等）
→ 总泄漏内存 ≈ 165MB
```

在每个泄漏的 `NewsDetailFragment` 实例上点击，查看 **Instance View** → **References**：

```
NewsDetailFragment[11]
  ├── mListener (匿名接口)
  │     └── NewsDetailPresenter (持有 Activity)
  ├── mRecyclerView
  │     └── mAdapter
  │           └── mDataList (持有大量数据)
  └── (注意是否有 this$0 引用指向外部类)
```

### 5.3 导出并使用 MAT 深度分析

**Step 5 — 导出 HPROF**

在 Memory Profiler 中点击"导出"按钮，保存为 `news_leak.hprof`。

**Step 6 — 转换格式（如需要）**

```bash
# Android SDK platform-tools 中
hprof-conv news_leak.hprof news_leak_mat.hprof
```

**Step 7 — 在 MAT 中打开**

启动 Eclipse MAT（或独立版 Memory Analyzer）：

```bash
# 增加 MAT 可用内存（大堆分析必须）
./MemoryAnalyzer -vmargs -Xmx4096m
```

File → Open Heap Dump → 选择 `news_leak_mat.hprof`

**Step 8 — 生成泄漏嫌疑报告**

MAT 打开后自动弹出向导 → 选择 **"Leak Suspects Report"** → Finish。

报告会给出：
- **Problem Suspect 1**：`com.example.news.NewsDetailFragment` 的 12 个实例占据 180MB
- **Biggest Objects**：Retained Heap 最大的对象列表
- **初步引用链**：显示对象是如何被持有的

**Step 9 — Dominator Tree 分析**

工具栏 → 点击 **Dominator Tree** 图标：

```
Class Name                          | Retained Heap  | %
------------------------------------+----------------+----
com.example.news.NewsDetailFragment | 180,456,728    | 35.2%
android.webkit.WebView              | 95,234,560     | 18.6%
androidx.recyclerview.widget.RecyclerView | 42,123,456 | 8.2%
...
```

展开 `NewsDetailFragment`，找到那些"不应该存在"的实例，右键 → **Path To GC Roots** → **exclude weak/soft references**。

**Step 10 — 追踪泄漏链**

MAT 展示的关键引用链（示例）：

```
NewsDetailFragment [11]
  ├─ mOnPageChangeListener → 类型: ViewPager.SimpleOnPageChangeListener
  │    ├─ this$0 → 类型: NewsDetailFragment  ← 非静态内部类自动引用！
  │    └─ held by → ViewPager.mListeners (ArrayList)
  └─ ViewPager.mListeners → 类型: ArrayList
       └─ GC Root: MainActivity.mViewPager → 类型: ViewPager
            └─ GC Root: Thread (main) → StackFrame → Local Variable
```

**根因分析：**

```
根本原因：NewsDetailFragment 内部注册了一个非静态的 OnPageChangeListener
到 ViewPager，而 ViewPager 是整个应用生命周期的（在 MainActivity 中）。
当 Fragment 被销毁时，该 Listener 没有从 ViewPager 中移除。

引用链：
  GC Root (Thread)
    → MainActivity.mViewPager
      → ViewPager.mListeners (ArrayList)
        → SimpleOnPageChangeListener (匿名内部类)
          → this$0 → NewsDetailFragment ❌ 泄漏！
```

### 5.4 修复方案

**方案一：Fragment.onDestroyView() 中移除 Listener**

```kotlin
class NewsDetailFragment : Fragment() {
    private val pageChangeListener = object : ViewPager.OnPageChangeListener {
        override fun onPageSelected(position: Int) { ... }
        // ...
    }
    
    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        viewPager.addOnPageChangeListener(pageChangeListener)
    }
    
    override fun onDestroyView() {
        super.onDestroyView()
        viewPager.removeOnPageChangeListener(pageChangeListener) // ✅ 修复
    }
}
```

**方案二：使用静态内部类 + WeakReference（更安全）**

```kotlin
class SafePageChangeListener(viewPager: ViewPager) : ViewPager.OnPageChangeListener {
    private val weakViewPager = WeakReference(viewPager)
    
    override fun onPageSelected(position: Int) {
        weakViewPager.get()?.let { /* 安全操作 */ }
    }
    // ...
}
```

### 5.5 MAT OQL 辅助排查

```sql
-- 查找所有 Fragment 实例及其持有者
SELECT * FROM INSTANCEOF androidx.fragment.app.Fragment

-- 查找所有非静态内部类引用 (this$0)
SELECT * FROM java.lang.Object 
WHERE object != null 
AND (object.toString() LIKE "%.%$%")

-- 查看 ViewPager 注册了多少 Listener
SELECT pager.mItems.size, pager.mCurItem 
FROM androidx.viewpager.widget.ViewPager pager
```

### 5.6 验证修复

1. 重新运行 App，重复之前的操作步骤（进出20次）
2. 在 Memory Profiler 中观察：GC后内存应回落到基线
3. 导出 heap dump → MAT 中搜索 `NewsDetailFragment` 实例数应为 1（当前显示的那个）
4. LeakCanary 不应再报告此泄漏

---

## 6. 扩展阅读与参考资料

### 关键工具链接

| 工具 | 用途 | 地址 |
|------|------|------|
| LeakCanary | Android 内存泄漏检测 | https://square.github.io/leakcanary/ |
| KOOM | 线上 OOM 监控 | https://github.com/KwaiAppTeam/KOOM |
| Eclipse MAT | Heap Dump 分析 | https://eclipse.dev/mat/ |
| Shark | HPROF 解析引擎 | https://square.github.io/leakcanary/shark/ |
| Android Profiler | 官方性能分析 | https://developer.android.com/studio/profile |

### 面试速查 Checklist

- [ ] Shallow Heap vs Retained Heap 定义与计算方式
- [ ] LeakCanary 三步检测法：WeakReference → GC → 检查
- [ ] Dominator Tree 与支配关系的直观理解
- [ ] Path to GC Roots 的四种排除选项
- [ ] Android HPROF 与 Java HPROF 的区别及转换
- [ ] KOOM fork dump 的原理与优势
- [ ] Shark 的 Memory-Mapped 解析与索引优先策略
- [ ] OQL 基本查询语法
- [ ] `this$0` 字段的来源与泄漏风险
- [ ] Fragment 生命周期相关泄漏的排查方法
- [ ] ReferenceMatcher 过滤系统级"伪泄漏"
- [ ] LeakCanary 进程隔离设计（2.x）

---

> **编写日期：** 2026-05-08
> **适用场景：** Android 高级/资深工程师面试准备
> **建议学习路径：** 先通读六层内容 → 重点记忆面试回答要点 → 动手复现实战案例 → 阅读 KOOM/LeakCanary 源码

