# 20 并发编程与线程安全

## 概览
30k+ 安卓工程师的核心区分维度——不仅要会用线程，更要理解并发模型、锁机制底层原理和 Android 特有的线程设计。涵盖 Java 并发基础、Android 线程模型、协程并发、线程安全最佳实践和锁优化。

## 子模块

| 序号 | 技术点 | 核心内容 | 权重 |
|:---:|-------|---------|:---:|
| 20.1 | [Java并发基础](./01-Java并发基础/) | Thread/Runnable/Callable/Future、ThreadPoolExecutor核心参数、CAS与Atomic类、AQS框架、volatile内存语义 | ★★★★★ |
| 20.2 | [Android线程模型](./02-Android线程模型/) | 主线程Looper、HandlerThread、IntentService、AsyncTask缺陷与替代、线程优先级(THREAD_PRIORITY) | ★★★★★ |
| 20.3 | [Kotlin协程并发](./03-Kotlin协程并发/) | 结构化并发、Mutex/Semaphore、Channel并发通信、Actor模式、协程上下文切换 | ★★★★★ |
| 20.4 | [线程安全最佳实践](./04-线程安全最佳实践/) | 不可变对象(Immutable)、线程封闭(ThreadLocal)、同步容器vs并发容器、CopyOnWriteArrayList、ConcurrentHashMap原理 | ★★★★★ |
| 20.5 | [锁与同步机制](./05-锁与同步机制/) | synchronized锁升级(偏向→轻量→重量)、ReentrantLock&AQS、读写锁、死锁排查(stuck thread)、LockSupport | ★★★★☆ |

## 面试高频考点
- synchronized 锁升级过程与 JVM 实现
- ThreadPoolExecutor 的 corePoolSize/maxPoolSize/keepAliveTime/BlockingQueue 调参
- 协程的 Mutex vs synchronized 的差异
- ConcurrentHashMap JDK7→8 的锁粒度演进
