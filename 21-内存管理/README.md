# 21 内存管理

## 概览
安卓内存管理的完整知识体系——从 JVM 堆栈模型到 ART 的现代化 GC 算法，从 Java 堆到 Native 堆的内存分配策略。这是理解 OOM、内存泄漏、内存抖动的理论基础。

## 子模块

| 序号 | 技术点 | 核心内容 | 权重 |
|:---:|-------|---------|:---:|
| 21.1 | [JVM内存模型](./01-JVM内存模型/) | 堆/栈/方法区/程序计数器、新生代(Eden/s0/s1)/老年代、TLAB、逃逸分析与栈上分配 | ★★★★★ |
| 21.2 | [ART内存与GC](./02-ART内存与GC/) | Dalvik→ART GC演进、Concurrent Copying GC、Baker Read Barrier、Region-based内存管理、GC暂停时间 | ★★★★★ |
| 21.3 | [内存分配策略](./03-内存分配策略/) | Bump Pointer分配、TLAB线程本地缓冲、对象的对齐与填充、大对象直接进老年代、方法内联与去虚拟化 | ★★★★☆ |
| 21.4 | [内存监控与压力](./04-内存监控与压力/) | onTrimMemory/ComponentCallbacks2、memoryClass/largeHeap、内存压力分级(TRIM_MEMORY_RUNNING_CRITICAL)、低内存杀进程(LMK) | ★★★★★ |
| 21.5 | [Native内存管理](./05-Native内存管理/) | malloc/free与jemalloc、mmap匿名映射、ashmem共享内存、Native内存泄漏检测(malloc_debug/nativeheapdump)、Bitmap内存演进(Java堆→Native堆→ashmem) | ★★★★☆ |

## 面试高频考点
- ART 的 Concurrent Copying GC 与 Dalvik 的 Mark-Sweep 差异
- onTrimMemory 各等级的含义与应对策略
- Bitmap 内存在不同 Android 版本中的存储位置变迁
- 为什么 Android 不用 JVM 的 G1/ZGC 而自研 ART GC
