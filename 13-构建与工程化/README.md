# 13 构建与工程化

## 概览
现代安卓工程的构建体系与工程化实践，从 Gradle 基础到 CI/CD 全流程。

## 子模块

| 序号 | 技术点 | 核心内容 | 考察权重 |
|:---:|-------|---------|:-------:|
| 13.1 | [Gradle 构建系统](./01-Gradle构建系统/) | Groovy/Kotlin DSL、Task 机制、Transform、插件开发 | ★★★★★ |
| 13.2 | [CI/CD 流程](./02-CICD流程/) | Jenkins/GitLab CI、自动化打包、AAB 发布 | ★★★★☆ |
| 13.3 | [单元测试与自动化测试](./03-单元测试与自动化测试/) | JUnit、Mockito、Espresso、UI 自动化 | ★★★★☆ |
| 13.4 | [代码规范与审查](./04-代码规范与审查/) | ktlint/detekt、Code Review 流程、Git 工作流 | ★★★★☆ |

## 面试高频考点
- Gradle 构建流程的三阶段（Init → Config → Exec）及 Task 执行顺序
- 如何编写自定义 Gradle 插件（Transform + AGP API）
- 组件化工程的 CI 策略（增量构建、变更检测）
