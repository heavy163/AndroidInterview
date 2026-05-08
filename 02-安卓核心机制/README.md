# 02 安卓核心机制

## 概览
安卓应用运行的基础设施，涵盖四大组件、生命周期管理、IPC 通信及异步消息机制。

## 子模块

| 序号 | 技术点 | 核心内容 | 考察权重 |
|:---:|-------|---------|:-------:|
| 2.1 | [四大组件](./01-四大组件/) | Activity/Service/BroadcastReceiver/ContentProvider 启动模式与使用场景 | ★★★★★ |
| 2.2 | [生命周期管理](./02-生命周期管理/) | Activity/Fragment/Service 生命周期流转与异常恢复 | ★★★★★ |
| 2.3 | [组件间通信](./03-组件间通信/) | Intent、Bundle、接口回调、EventBus、SharedPreferences | ★★★★☆ |
| 2.4 | [Binder 机制](./04-Binder机制/) | Binder 驱动层、AIDL、匿名共享内存、一次拷贝原理 | ★★★★★ |
| 2.5 | [Handler 消息机制](./05-Handler消息机制/) | MessageQueue、Looper、epoll、同步屏障、IdleHandler | ★★★★★ |

## 面试高频考点
- Activity 启动模式（standard/singleTop/singleTask/singleInstance）与 TaskAffinity
- Binder 为什么只需要一次拷贝？与传统 IPC 对比
- Handler 内存泄漏的原因与解决方案
