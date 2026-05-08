# 05 Jetpack 组件体系

## 概览
Google 官方推荐的安卓架构组件，覆盖生命周期感知、数据持久化、导航、依赖注入和声明式 UI。

## 子模块

| 序号 | 技术点 | 核心内容 | 考察权重 |
|:---:|-------|---------|:-------:|
| 5.1 | [ViewModel 与 LiveData](./01-ViewModel与LiveData/) | ViewModel 生命周期、LiveData 粘性事件、StateFlow 对比 | ★★★★★ |
| 5.2 | [Room 数据库](./02-Room数据库/) | DAO、Entity、Migration、FTS 全文搜索、类型转换器 | ★★★★☆ |
| 5.3 | [Navigation](./03-Navigation/) | NavGraph、SafeArgs、DeepLink、多返回栈 | ★★★★☆ |
| 5.4 | [Hilt 依赖注入](./04-Hilt依赖注入/) | DI 原理、Scope 管理、与 Dagger 对比 | ★★★★★ |
| 5.5 | [Compose 声明式 UI](./05-Compose声明式UI/) | 重组机制、状态管理、Modifier、副作用 API | ★★★★★ |
| 5.6 | [其他组件](./06-其他组件/) | WorkManager、DataStore、Paging、Startup | ★★★☆☆ |

## 面试高频考点
- ViewModel 如何在配置变更时保持数据？SavedStateHandle 机制
- Compose 重组（Recomposition）的触发条件与优化
- Hilt 的 Scope 层级与生命周期绑定关系
