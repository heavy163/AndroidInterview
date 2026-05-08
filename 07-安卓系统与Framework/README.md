# 07 安卓系统与 Framework

## 概览
安卓系统架构全景，深入 Framework 层核心服务：AMS、PMS、WMS 及系统级监控机制。

## 子模块

| 序号 | 技术点 | 核心内容 | 考察权重 |
|:---:|-------|---------|:-------:|
| 7.1 | [系统架构全景](./01-系统架构全景/) | 应用层→框架层→运行库层→Linux内核层 | ★★★★☆ |
| 7.2 | [AMS 详解](./02-AMS详解/) | Activity 启动流程、进程调度、ActivityRecord 管理 | ★★★★★ |
| 7.3 | [PMS 详解](./03-PMS详解/) | APK 安装流程、权限管理、包信息解析 | ★★★★☆ |
| 7.4 | [WMS 详解](./04-WMS详解/) | 窗口管理、SurfaceFlinger 合成、Display 管理 | ★★★★☆ |
| 7.5 | [WatchDog 机制](./05-WatchDog机制/) | 系统死锁监控、ANR 上报、FdMonitor | ★★★☆☆ |

## 面试高频考点
- 从点击桌面图标到 Activity 展示的完整流程
- APP 进程启动：Zygote → fork → ActivityThread.main()
- ANR 的底层触发机制（Input/Service/Broadcast 超时）
