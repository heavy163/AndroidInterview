# EventBus 事件通信框架

## 面试核心问题

1. **EventBus 的注册/反注册流程是怎样的？订阅者索引如何建立？**
2. **ThreadMode（POSTING/MAIN/BACKGROUND/ASYNC）的区别与实现？**
3. **粘性事件（Sticky Event）的原理？**
4. **Subscriber Index 是什么？如何提升查找性能？**
5. **EventBus 3.0 的注解处理器优化了什么？**
6. **EventBus vs RxBus vs LiveData/StateFlow 的选型？**

## 知识体系

| 层级 | 内容 | 难度 |
|-----|------|:---:|
| 基础 | @Subscribe注解、事件发送、线程模式 | ★★★ |
| 进阶 | 订阅者注册流程、事件分发、粘性事件 | ★★★★ |
| 源码 | SubscriberMethodFinder、PostingThreadState、ThreadMode切换 | ★★★★★ |
| 对比 | EventBus vs LiveData vs Flow vs RxBus | ★★★★★ |

## 六层内容（待填充）

1. 常见面试问题
2. 标准答案与要点解析
3. 核心原理深度讲解
4. 原理流程图（时序图/状态图）
5. 核心源码分析
6. 实际应用场景与项目经验
