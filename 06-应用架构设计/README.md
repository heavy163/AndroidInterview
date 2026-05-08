# 06 应用架构设计

## 概览
中大型安卓应用的架构设计范式，从经典的 MVVM 到现代的 MVI 和 Clean Architecture。

## 子模块

| 序号 | 技术点 | 核心内容 | 考察权重 |
|:---:|-------|---------|:-------:|
| 6.1 | [MVVM 架构](./01-MVVM架构/) | 数据驱动 UI、双向绑定、Repository 模式 | ★★★★★ |
| 6.2 | [MVI 架构](./02-MVI架构/) | 单向数据流、State/Intent 模型、时间旅行调试 | ★★★★☆ |
| 6.3 | [Clean Architecture](./03-Clean-Architecture/) | 分层依赖、UseCase 层、领域驱动设计 | ★★★★☆ |
| 6.4 | [组件化与模块化](./04-组件化与模块化/) | ARouter、模块间通信、依赖管理、壳工程 | ★★★★★ |
| 6.5 | [插件化技术](./05-插件化技术/) | Tinker 热修复、Shadow 插件框架、ClassLoader Hook | ★★★☆☆ |

## 面试高频考点
- MVVM 中 View 如何感知 ViewModel 的数据变化？
- 组件化工程中模块间如何解耦通信？
- Clean Architecture 的依赖规则与数据流方向
