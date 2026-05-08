# OkHttp 网络请求框架

## 面试核心问题

1. **OkHttp 的拦截器链（Interceptor Chain）包含哪些拦截器？执行顺序？**
2. **连接池（ConnectionPool）的复用机制是怎样的？**
3. **OkHttp 如何支持 HTTP/2 多路复用？**
4. **DNS 解析优化怎么做？（自建 DNS、HTTP-DNS）**
5. **Call.enqueue() 和 Call.execute() 的区别？**
6. **Dispatcher 线程池的作用与配置？**
7. **OkHttp 的缓存策略（CacheStrategy）原理？**

## 知识体系

| 层级 | 内容 | 难度 |
|-----|------|:---:|
| 基础 | 同步/异步请求、基本配置 | ★★★ |
| 进阶 | 拦截器链、RealCall/RealInterceptorChain、连接池 | ★★★★ |
| 源码 | 五大拦截器、StreamAllocation、Http2Connection | ★★★★★ |
| 优化 | 连接复用、HTTP-DNS、QUIC支持、连接淘汰策略 | ★★★★★ |

## 六层内容（待填充）

1. 常见面试问题
2. 标准答案与要点解析
3. 核心原理深度讲解
4. 原理流程图（时序图/状态图）
5. 核心源码分析
6. 实际应用场景与项目经验
