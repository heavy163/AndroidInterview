# 15 性能优化工具专题

## 概览
性能优化面试的必考重点——各类工具的 **原理、使用方式** 和 **实践技巧**。
按照工具性质分类，每类按先进程度排序。

## 工具分类

| 类别 | 工具 | 核心用途 | 先进度 |
|-----|------|---------|:-----:|
| **系统级追踪** | [Systrace / Perfetto](./01-系统级追踪工具/) | 全链路性能分析、CPU/GPU/IO 追踪 | ★★★★★ |
| **内存分析** | [Memory Profiler / LeakCanary / MAT](./02-内存分析工具/) | 内存分配追踪、泄漏检测、堆转储分析 | ★★★★★ |
| **CPU/线程分析** | [CPU Profiler / Traceview](./03-CPU与线程分析工具/) | 方法耗时、线程状态、热点代码定位 | ★★★★☆ |
| **网络/IO分析** | [Network Profiler / Stetho](./04-网络与IO分析工具/) | 网络请求监控、IO 性能分析 | ★★★★☆ |
| **APM监控** | [BlockCanary / Matrix / Sentry](./05-APM监控工具/) | 线上性能监控、卡顿/泄漏/崩溃上报 | ★★★★★ |

## 面试高频考点
- Systrace 中如何判断掉帧原因？Frame 分类（draw/misc/scheduling/delay）
- Memory Profiler 的 shallow heap vs retained heap 区别
- Matrix 的卡顿监控原理（Choreographer 回调 + Looper 埋点）
