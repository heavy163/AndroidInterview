# 22 高性能编程

## 概览
安卓高性能编程的系统化方法论——从对象池模式到零拷贝技术，从序列化性能到 IO 优化再到编译期优化。这是区分「能用」和「高性能」的关键知识体系。

## 子模块

| 序号 | 技术点 | 核心内容 | 权重 |
|:---:|-------|---------|:---:|
| 22.1 | [对象复用与池化](./01-对象复用与池化/) | Message池化(obtain/recycle)、RecyclerView的ViewHolder/缓存池、Glide的BitmapPool、对象池设计模式(GenericObjectPool)、避免自动装箱 | ★★★★★ |
| 22.2 | [零拷贝与共享内存](./02-零拷贝与共享内存/) | Binder mmap一次拷贝、FileChannel.transferTo、MemoryFile共享内存、管道/Socket的splice机制、DirectByteBuffer | ★★★★☆ |
| 22.3 | [序列化性能优化](./03-序列化性能优化/) | Parcelable vs Serializable性能对比、ProtoBuf FlatBuffer对比、Json解析(Moshi vs Gson vs kotlinx.serialization)、SharedPreferences的apply vs commit | ★★★★☆ |
| 22.4 | [IO与存储优化](./04-IO与存储优化/) | NIO vs BIO、mmap文件读写(如MMKV)、WAL日志(先写后改)、SQLite优化(WAL模式/批量事务/索引)、磁盘缓存策略 | ★★★★☆ |
| 22.5 | [编译优化与基线](./05-编译优化与基线/) | R8优化(内联/去虚拟化/分支删除)、ProGuard keep规则调优、DEX布局优化(启动类重排)、Baseline Profile、PGO(Profile Guided Optimization) | ★★★★☆ |

## 面试高频考点
- Message.obtain() 对象池的线程安全设计
- Binder 为什么只需要一次拷贝（mmap 原理）
- kotlinx.serialization vs Gson 的性能差异来源
- Baseline Profile 如何加速应用启动
