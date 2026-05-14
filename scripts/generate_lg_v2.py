#!/usr/bin/env python3
"""简化版学习指南生成器 — 使用统一模板，所有模块走 quick_guide 模式"""
import os, sys

PROJECT_ROOT = "/home/heavy/AndroidJob"
PRINCIPLES = {
    "骨架先行": "先搞懂整体结构、模块划分、核心链路，不一开始扎进零散语法/API；先有地图，再逛景点",
    "最小闭环": "先做一个能完整运行的最小可用版本，不求完美、不求精通；先建立体感和全局流程，再回头拆解底层原理",
    "问题驱动": "放弃「从头看到尾」的被动学习；用实战需求倒逼知识点，缺什么学什么，遇到坑再补理论",
    "单点击穿": "把复杂大系统拆成独立小知识点，一次只攻克一个，学完立刻落地使用；不并行啃多个难点",
    "学以致用": "学到的每一个知识点，必须立刻动手复用一次；不囤积知识，只留存能落地、能复现的内容",
    "先会后懂": "先用起来，再慢慢吃透底层；不要卡在一个细节死磕，耽误整体进度",
    "模板沉淀": "把常用写法、固定架构、避坑方案，沉淀成私有模板/笔记/代码片段；从「临时记忆」变成「长期能力」",
    "新旧嫁接": "用已会的技能类比映射新技能，找异同、记差异，不用从零陌生认知",
    "刻意屏蔽": "主动过滤冷门、边角、工作用不到的知识；只学核心主干、高频必备，边缘知识用到再查",
    "闭环复盘": "定期复盘：把零散知识点串联成逻辑链路，从「会零散 API」升级为「懂架构、懂设计、能独立搭建」",
}

TEMPLATE = """# {module_title} — 学习指南

> 遵循「先框架后细节、先闭环后原理、先实战后理论、学即用常沉淀、拆解难点不贪多」核心心法

---

## 🗺️ 知识骨架全景图

打开本目录下的 `知识骨架.xmind` 查看完整知识结构。

{tree_skeleton}

---

## 🎯 10 条学习原则落地指南

### 1. 骨架先行 — 建立整体认知地图

> {p1}

**本模块骨架**：{skeleton_desc}

**行动**：打开 `知识骨架.xmind`，花 5 分钟浏览全部节点，建立模块全局印象，再按阶段逐一攻克。

---

### 2. 最小闭环 — 先跑通再深挖

> {p2}

**本模块最小闭环项目**：
{minimal_project}

**检查点**：能否独立跑通这个闭环？如果能，说明框架理解正确；如果不能，回头补最基础的 API 调用。

---

### 3. 问题驱动 — 缺什么学什么

> {p3}

**核心面试问题驱动学习**：
{interview_questions}

**行动**：选一个问题 → 尝试自己回答 → 对比标准答案 → 补知识点 → 再回答一遍。

---

### 4. 单点击穿 — 一次只攻克一个

> {p4}

**建议学习顺序**（一次只学一个子模块）：
{learning_sequence}

**规则**：当前子模块没跑通最小闭环前，绝不开下一个。

---

### 5. 学以致用 — 学了立刻用

> {p5}

**每个子模块的实战任务**：
{practical_tasks}

---

### 6. 先会后懂 — 允许先会用

> {p6}

**先用起来的关键 API**（暂时不需要深究源码）：
{quick_start_apis}

---

### 7. 模板沉淀 — 把知识变成资产

> {p7}

**建议沉淀的模板**：
{templates_to_save}

---

### 8. 新旧嫁接 — 用已知类比未知

> {p8}

**本模块的类比映射**：
{analogy_mapping}

---

### 9. 刻意屏蔽 — 先学核心再补边缘

> {p9}

**本模块的核心主干**（必须掌握）：
{core_content}

**本模块的边缘知识**（先跳过，用到再学）：
{edge_content}

---

### 10. 闭环复盘 — 串联成体系

> {p10}

**复盘检查清单**：
{review_checklist}

**频率**：每完成一个阶段的 3 个子模块后，做一次串联复盘。

---

## 📊 学习进度追踪

| 子模块 | 状态 | 最小闭环 | 面试题 | 模板沉淀 | 日期 |
|--------|:----:|:--------:|:------:|:--------:|------|
{progress_table}

---

## 🔗 相关资源

- **本模块知识骨架**：`知识骨架.xmind`
- **知识点深入学习**：各子目录下的 `index.md`
- **性能优化工具**：`15-性能优化工具专题/`
- **高频面试题**：`18-高频面试题汇总/`

---

> 💡 **一句话终极心法**：先框架后细节、先闭环后原理、先实战后理论、学即用常沉淀、拆解难点不贪多。
"""

# ─── 统一数据结构：所有模块用同样的 dict 格式 ───
DATA = {}

def add(mid, title, skeleton_desc, minimal_project, learning_sequence,
        interview_questions, practical_tasks, quick_start_apis="",
        templates_to_save="", analogy_mapping="", core_content="",
        edge_content="", review_checklist="", progress_table=""):
    DATA[mid] = {
        "module_title": title,
        "skeleton_desc": skeleton_desc,
        "minimal_project": minimal_project,
        "learning_sequence": learning_sequence,
        "interview_questions": interview_questions,
        "practical_tasks": practical_tasks,
        "quick_start_apis": quick_start_apis,
        "templates_to_save": templates_to_save,
        "analogy_mapping": analogy_mapping,
        "core_content": core_content,
        "edge_content": edge_content,
        "review_checklist": review_checklist,
        "progress_table": progress_table,
    }

P = PRINCIPLES  # shortcut

# ========== 模块数据定义（精简但完整）==========

add("01-安卓语言基础", "01 · 安卓语言基础",
    "Kotlin 核心特性 → 协程并发 → Java 进阶 → KMM 跨平台，四层递进",
    "- **项目**：天气预报 App\n- **技术栈**：Kotlin + MVVM + 协程 + Flow + Retrofit\n- **闭环目标**：搜索城市 → 网络请求 → UI 更新",
    "1. Kotlin 核心特性（扩展函数/高阶函数/委托/密封类/数据类）\n2. Kotlin 协程（suspend→Flow→StateFlow→结构化并发）\n3. Java 进阶（JVM 内存模型/GC/APT）\n4. KMM 跨平台",
    "- suspend 函数底层实现？\n- Flow vs LiveData vs StateFlow 选用场景？\n- 协程取消的协作机制？\n- Kotlin inline 如何减少对象创建？",
    "- 用扩展函数封装 View 通用操作\n- 用 sealed class 定义网络请求状态机\n- 用 Flow 实现搜索防抖",
    "- `suspend fun` / `viewModelScope.launch { }` / `flow { emit(value) }` / `MutableStateFlow(initial)`",
    "- 协程网络请求模板 / sealed class 状态机模板 / Flow 搜索防抖模板",
    "- Java 匿名内部类→Kotlin lambda / Java Future→suspend / Java RxJava→Flow",
    "- Kotlin 扩展函数/高阶函数/委托/密封类/数据类 / 协程基础 / Flow/StateFlow / JVM 堆栈结构/GC Roots",
    "- KMM expect/actual 详细用法 / inline/noinline 编译细节 / Kotlin 编译器插件开发",
    "- [ ] 独立用 Kotlin+协程写网络请求页面\n- [ ] 解释 suspend 函数 CPS 转换\n- [ ] 说清 Flow vs LiveData vs StateFlow 选择标准\n- [ ] 画出 JVM 内存区域分布图",
    "| Kotlin 核心特性 | ⬜ | — | — | — | |\n| Kotlin 协程 | ⬜ | — | — | — | |\n| Java 进阶 | ⬜ | — | — | — | |\n| KMM 跨平台 | ⬜ | — | — | — | |")

add("02-安卓核心机制", "02 · 安卓核心机制",
    "四大组件生命周期 → 组件通信 → Binder IPC → Handler 消息循环，从表象到底层",
    "- **项目**：IPC 跨进程通信 Demo\n- **技术栈**：AIDL + Service\n- **闭环目标**：定义 AIDL 接口 → Service 实现 → 客户端调用",
    "1. 四大组件全景（生命周期/启动模式/注册方式）\n2. 生命周期管理（Activity/Fragment/异常恢复/ViewModel）\n3. 组件间通信（Intent→EventBus→LiveEventBus→ContentProvider）\n4. Binder 机制深度（mmap→AIDL 生成类→ashmem）\n5. Handler 消息机制源码级（MessageQueue→Looper→同步屏障→IdleHandler）",
    "- 点击图标到 Activity 展示的完整流程？\n- Binder 为什么只拷贝一次？\n- Handler 消息延迟原因？\n- Activity 四种启动模式？\n- Service 与 Thread 区别？",
    "- 实现跨进程 Service 调用\n- 写 Handler 消息机制 Demo（含同步屏障+IdleHandler）\n- 四种启动模式效果演示",
    "- `startActivity`/`bindService`/`registerReceiver`/`Handler.post`",
    "- Activity 生命周期模板 / AIDL 接口模板 / Handler 消息机制图解 / 四大组件对比速查表",
    "- Binder→Linux 管道/socket 对比 / Handler→EventLoop 类比 / ContentProvider→RESTful API",
    "- Activity 四种启动模式 / Service 三种形态 / Handler 源码 / Binder 一次拷贝原理",
    "- BroadcastReceiver 有序广播细节 / ContentProvider 批量操作 / Binder 线程池 16 上限",
    "- [ ] 画出 Activity 启动流程图\n- [ ] 解释 Binder mmap 一次拷贝\n- [ ] 手写简化版 Handler\n- [ ] 说出四大组件使用场景和限制",
    "| 四大组件全景 | ⬜ | — | — | — | |\n| 生命周期管理 | ⬜ | — | — | — | |\n| 组件间通信 | ⬜ | — | — | — | |\n| Binder 机制 | ⬜ | — | — | — | |\n| Handler 机制 | ⬜ | — | — | — | |")

add("03-数据结构与算法", "03 · 数据结构与算法",
    "常用数据结构 API → 排序/查找算法 → 动态规划 → 安卓中的算法落地",
    "- **刷题路径**：数组(5题)→链表(5题)→二叉树(5题)→DP(5题)\n- **闭环目标**：每个数据结构核心操作能手写，能口述复杂度",
    "1. 数据结构基础（ArrayList扩容/HashMap源码/SparseArray/ArrayMap）\n2. 排序算法手写（快排/归并/堆排）+复杂度推导\n3. 查找与遍历（二分/BFS/DFS/布隆过滤器）\n4. 动态规划（0-1背包/LCS）",
    "- HashMap put 完整流程？\n- SparseArray 和 HashMap 本质区别？\n- 手写快排+复杂度分析？\n- LRU Cache 实现？",
    "- 手写 HashMap 简化版\n- 手写 LRU Cache\n- 手写快排+三路分区优化",
    "- `HashMap.put/get` / `SparseArray.put/get` / `ArrayDeque` / `Collections.sort()`",
    "- 快排/归并/堆排手写模板 / BFS/DFS 框架模板 / LRU Cache 模板 / 数据复杂度速查表",
    "- HashMap→图书馆索引 / SparseArray→字典拼音 / BFS→水波 / DFS→走迷宫",
    "- HashMap 源码（put/get/resize/树化）/ ArrayList 扩容 / 快排+归并 / 二分查找 / SparseArray",
    "- 红黑树自平衡细节 / 布隆过滤器推导 / DP 状态压缩 / 图高级算法",
    "- [ ] 手写 HashMap 简化版\n- [ ] 手写快排和归并\n- [ ] 解释 SparseArray 省内存原因\n- [ ] LeetCode Hot100 完成30+题",
    "| 数据结构基础 | ⬜ | — | — | — | |\n| 排序算法 | ⬜ | — | — | — | |\n| 查找与遍历 | ⬜ | — | — | — | |\n| 动态规划 | ⬜ | — | — | — | |")

add("04-UI与View体系", "04 · UI与View体系",
    "View 树全景（Measure→Layout→Draw）→ 事件分发 → 自定义 View → 动画系统",
    "- **项目**：自定义圆形进度条\n- **技术栈**：自定义 View + 属性动画\n- **闭环目标**：onMeasure→onDraw 画圆弧→ValueAnimator(0→100)",
    "1. View 绘制流程（Measure→Layout→Draw→ViewRootImpl）\n2. 事件分发（三方法调用链+源码+滑动冲突）\n3. 自定义 View（onMeasure/onLayout/onDraw+Canvas）\n4. 动画系统（补间/帧/属性/过渡）",
    "- View 绘制三阶段各自做了什么？\n- MeasureSpec 如何确定？\n- 事件分发三方法调用链？\n- requestLayout 和 invalidate 区别？\n- 滑动冲突如何解决？",
    "- 实现流式布局 ViewGroup\n- 解决 ViewPager 嵌套 RecyclerView 滑动冲突\n- 贝塞尔曲线波浪动画\n- 自定义评分组件",
    "- `View.measure`/`View.layout`/`View.draw`/`ValueAnimator.ofInt(0,100).start()`",
    "- 自定义 View 模板 / 事件分发流程图 / 滑动冲突解决模板 / 属性动画模板",
    "- View 绘制→画家作画 / 事件分发→领导审批链 / 属性动画→遥控器调音量",
    "- MeasureSpec 三种模式 / 事件分发三方法+源码 / 自定义 View+属性 / 属性动画 vs 补间动画",
    "- Transition 过渡高级用法 / SurfaceView vs TextureView 底层 / RenderNode 硬件加速",
    "- [ ] 画出 View 绘制三阶段流程图\n- [ ] 画出事件分发调用链\n- [ ] 独立写自定义 View\n- [ ] 解决嵌套滑动冲突",
    "| View 绘制流程 | ⬜ | — | — | — | |\n| 事件分发 | ⬜ | — | — | — | |\n| 自定义 View | ⬜ | — | — | — | |\n| 动画系统 | ⬜ | — | — | — | |")

add("05-Jetpack组件体系", "05 · Jetpack组件体系",
    "ViewModel/LiveData→Room→Navigation→Hilt→Compose，6 组件递进",
    "- **项目**：记事本 App\n- **技术栈**：Compose + Room + Hilt + MVVM\n- **闭环目标**：笔记增删改查 + Flow 响应式列表",
    "1. ViewModel+LiveData（生命周期感知+SavedStateHandle）\n2. Room（三剑客注解+Migration+Flow查询）\n3. Navigation（NavGraph+SafeArgs+DeepLink）\n4. Hilt（Scope层级+@Binds/@Provides）\n5. Compose（重组机制+状态管理+副作用API）\n6. 其他组件（WorkManager+DataStore+Paging3）",
    "- ViewModel 横竖屏切换如何保持数据？\n- Compose 重组与 View invalidate 区别？\n- Room Flow 查询如何感知变更？\n- Hilt Scope 层级？\n- StateFlow vs LiveData？",
    "- ViewModel+StateFlow 改造 LiveData 项目\n- Room Migration 测试\n- DeepLink 从通知跳转详情页\n- Compose 搜索列表页",
    "- `ViewModelProvider.get`/`liveData.observe`/`@Entity/@Composable`",
    "- ViewModel+StateFlow 模板 / Room DAO CRUD 模板 / Hilt Module 模板 / Compose 状态管理模板",
    "- ViewModel→乐队指挥 / Room→Excel / Hilt→外卖平台 / Compose→公式推导",
    "- ViewModel 生命周期+SavedStateHandle / Room 三剑客+Migration / Hilt Scope层级 / Compose 重组+remember+mutableStateOf+副作用",
    "- Compose 与 View 互操作细节 / Room FTS4 / Paging3 RemoteMediator",
    "- [ ] Compose+Room+Hilt 写 CRUD 页面\n- [ ] 解释 Compose 重组和智能跳过\n- [ ] 画出 Hilt Scope 层级图\n- [ ] 说出 ViewModel 和 onSaveInstanceState 互补关系",
    "| ViewModel+LiveData | ⬜ | — | — | — | |\n| Room | ⬜ | — | — | — | |\n| Navigation | ⬜ | — | — | — | |\n| Hilt | ⬜ | — | — | — | |\n| Compose | ⬜ | — | — | — | |\n| 其他组件 | ⬜ | — | — | — | |")

add("06-应用架构设计", "06 · 应用架构设计",
    "MVVM→MVI→Clean Architecture→组件化→插件化，架构演进之路",
    "- **项目**：三模块组件化 Demo\n- **技术栈**：app(壳)+home+profile+ARouter\n- **闭环目标**：壳工程组装→ARouter 路由跳转→模块间服务调用",
    "1. MVVM（ViewModel+Repository+DataBinding）\n2. MVI（State/Intent/Action+单向数据流）\n3. Clean Architecture（Domain/Data/Presentation+UseCase+DIP）\n4. 组件化（ARouter+接口下沉+Gradle模块管理）\n5. 插件化（Tinker Dex差量+Shadow ClassLoader Hook）",
    "- MVVM 和 MVI 核心区别？\n- 组件化模块间通信方案？\n- ARouter 路由表如何生成？\n- Clean Architecture 三层职责？\n- Tinker Dex 差量替换原理？",
    "- 对比 MVVM 和 MVI 同功能实现\n- 单模块拆分为 3 模块+壳工程\n- ARouter 拦截器（登录校验）\n- Tinker 热修复 Demo",
    "- `@HiltViewModel`/`@Composable(state,onIntent)`/`@Route(path)`/`interface IAccountService`",
    "- MVVM 项目结构模板 / MVI State/Intent/Reducer 模板 / 组件化模块划分模板 / ARouter 路由配置模板",
    "- MVVM→观察者模式 / MVI→银行柜台 / Clean Architecture→三层办公楼 / 组件化→乐高积木",
    "- MVVM vs MVI 数据流 / Repository 模式 / 组件化通信 4 方案 / ARouter APT 路由表 / Clean Architecture 分层",
    "- 插件化 ClassLoader 双亲委派突破 / Tinker 资源补丁 / VirtualAPK 对比",
    "- [ ] 画出 MVVM 和 MVI 数据流向图\n- [ ] 画出 Clean Architecture 三层依赖图\n- [ ] 解释组件化 vs 插件化区别\n- [ ] 设计中大型 App 架构方案",
    "| MVVM | ⬜ | — | — | — | |\n| MVI | ⬜ | — | — | — | |\n| Clean Architecture | ⬜ | — | — | — | |\n| 组件化 | ⬜ | — | — | — | |\n| 插件化 | ⬜ | — | — | — | |")

add("07-安卓系统与Framework", "07 · 安卓系统与Framework",
    "5 层系统架构全景→AMS→PMS→WMS→WatchDog",
    "- **项目**：源码追踪\n- **闭环目标**：画出 AMS.startActivity→ActivityThread.main 完整 Binder 调用链",
    "1. 系统架构全景（5层+Zygote/SystemServer启动）\n2. AMS（Activity启动+Task栈+oom_adj）\n3. PMS（APK安装+权限管理+签名校验）\n4. WMS（窗口管理+SurfaceFlinger+输入法层级）\n5. WatchDog（死锁监控+ANR触发）",
    "- 点击图标到 Activity 展示完整流程？\n- Zygote fork+COW 机制？\n- AMS 如何管理 Task 栈和 oom_adj？\n- PMS APK 安装流程？",
    "- 画出 Zygote→SystemServer→Launcher 流程图\n- 追踪 AMS.startActivity Binder 调用链\n- dumpsys activity 查看 Task 栈\n- 分析 ANR traces.txt",
    "- `adb shell dumpsys activity/package/window` / `cat /proc/<pid>/oom_adj`",
    "- Android 5层架构图 / Activity 启动 Binder 序列图 / oom_adj 等级表 / APK 安装流程图",
    "- Zygote→细胞分裂 / AMS→塔台调度 / PMS→海关检查 / Binder→邮局系统",
    "- Zygote fork+COW / Activity 启动 Binder 调用链 / oom_adj 回收优先级 / APK 安装流程 / SurfaceFlinger VSync",
    "- Kernel Panic+last_kmsg / FdMonitor 源码 / HAL 层接口",
    "- [ ] 画出 5 层系统架构图\n- [ ] 画出 Activity 启动 Binder 序列图\n- [ ] 解释 Zygote 加速原理\n- [ ] 用 dumpsys 排查问题",
    "| 系统架构 | ⬜ | — | — | — | |\n| AMS | ⬜ | — | — | — | |\n| PMS | ⬜ | — | — | — | |\n| WMS | ⬜ | — | — | — | |\n| WatchDog | ⬜ | — | — | — | |")

add("08-性能优化", "08 · 性能优化",
    "启动速度→UI卡顿→内存泄漏→功耗→包体积→网络优化，全链路覆盖",
    "- **项目**：对现有项目全链路性能诊断\n- **工具**：Systrace/Perfetto+Memory Profiler+CPU Profiler\n- **闭环目标**：找出 3 个优化点→量化效果→形成报告",
    "1. 启动速度（冷启动4阶段+StartUp+懒加载）\n2. UI卡顿（16ms渲染+过度绘制+RecyclerView优化）\n3. 内存泄漏（GC Root+5大泄漏场景+MAT+LeakCanary）\n4. 功耗（Battery Historian+WakeLock+WorkManager）\n5. 包体积（AndResGuard+R8+动态下发+WebP）\n6. 网络优化（HTTP/2+连接池+HTTPDNS+QUIC）",
    "- 冷启动分哪几个阶段？\n- Systrace 中如何判断掉帧？\n- 内存泄漏 3 种定位方法？\n- R8 三阶段各做了什么？\n- 网络请求耗时拆解？",
    "- Systrace/Perfetto 抓取启动 trace 分析\n- LeakCanary 检出并修复 3 个泄漏\n- APK Analyzer 分析包体积\n- 对比 R8 开启前后 APK 差异",
    "- `adb shell am start -W` / Systrace/Perfetto / LeakCanary / APK Analyzer",
    "- 性能优化检查清单 / Systrace 常见问题速查 / 内存泄漏 5 场景+方案 / 网络优化方案对比",
    "- 启动→汽车起步 / 内存泄漏→水槽漏水 / RecyclerView→流水线复用 / R8→文件压缩",
    "- 冷启动 4 阶段与优化 / Systrace Frame 渲染分析 / GC Root 可达性 / R8 三阶段 / OkHttp 连接池",
    "- Systrace 自定义 Trace 埋点 / Battery Historian 复杂分析 / QUIC 细节 / PGO",
    "- [ ] 独立完成 App 启动优化（量化效果）\n- [ ] Systrace/Perfetto 定位卡顿\n- [ ] 识别 5 种常见泄漏场景\n- [ ] 说出包体积优化完整方案",
    "| 启动速度 | ⬜ | — | — | — | |\n| UI卡顿 | ⬜ | — | — | — | |\n| 内存泄漏 | ⬜ | — | — | — | |\n| 功耗 | ⬜ | — | — | — | |\n| 包体积 | ⬜ | — | — | — | |\n| 网络优化 | ⬜ | — | — | — | |")

# ========== 9-22 模块（简化数据）==========

add("09-稳定性与异常处理", "09 · 稳定性与异常处理",
    "ANR 分析→崩溃捕获→SystemRestart→异常监控体系",
    "- **项目**：搭建异常上报系统\n- **闭环目标**：UncaughtExceptionHandler→持久化→上传→服务端聚合",
    "1. ANR 三类型超时+traces.txt 解读\n2. Java/Native Crash 捕获原理\n3. System Restart 分析\n4. 线上异常监控架构",
    "- ANR traces.txt 解读？\n- Java vs Native crash 捕获差异？\n- OOM 预防与监控？",
    "- 手动制造 ANR 并解读\n- 自定义 UncaughtExceptionHandler\n- 设计 crash 链路追踪",
    "- 核心：ANR 三类型+traces.txt / Java/Native Crash 捕获 / OOM 监控 / 全链路 traceId",
    "- Kernel Panic / Native Crash 信号处理 / system_server 重启",
    "- [ ] 解读 ANR traces.txt\n- [ ] 区分 crash 类型\n- [ ] 设计异常监控架构",
    "| ANR 分析 | ⬜ | — | — | — | |\n| 崩溃分析 | ⬜ | — | — | — | |\n| SystemRestart | ⬜ | — | — | — | |\n| 异常监控 | ⬜ | — | — | — | |")

add("10-原生开发与NDK", "10 · 原生开发与NDK",
    "JNI 类型映射→静态/动态注册→CMake 构建→Native 调试",
    "- **项目**：JNI 图像灰度处理\n- **闭环目标**：Java 传 Bitmap→Native 灰度算法→返回 Bitmap 显示",
    "1. JNI 基础（类型映射+注册方式+引用管理）\n2. CMake 构建+so 加载+ABI 兼容\n3. C++ 最佳实践",
    "- 动态注册 vs 静态注册？\n- 为何管理 JNI 引用？\n- Native 如何回调 Java？",
    "- 写 JNI 动态注册 Demo\n- CMake 编译 so 库\n- Native 回调 Java 方法",
    "- JNI 类型映射表 / 动态注册 vs 静态注册 / CMake 构建 / JNI 引用管理",
    "- C++ STL 线程安全 / tombstone 分析 / 交叉编译细节",
    "- [ ] 手写 JNI 动态注册\n- [ ] CMake 构建 NDK 项目\n- [ ] 排查 Native Crash",
    "| JNI 基础 | ⬜ | — | — | — | |\n| NDK 开发 | ⬜ | — | — | — | |\n| C++与安卓 | ⬜ | — | — | — | |")

add("11-音视频开发", "11 · 音视频开发",
    "编解码基础→播放器架构→推流协议→FFmpeg→ExoPlayer",
    "- **项目**：简易视频播放器\n- **闭环目标**：MediaCodec+SurfaceView→播放本地 MP4",
    "1. 编解码（H.264/AAC/MediaCodec）\n2. 播放器（解封装→解码→音画同步→渲染）\n3. 推流拉流（RTMP/HLS/WebRTC）\n4. FFmpeg\n5. ExoPlayer",
    "- MediaCodec 异步模式流程？\n- I/P/B 帧区别与 GOP？\n- RTMP vs HLS vs WebRTC？\n- 音画同步 PTS/DTS 计算？",
    "- MediaCodec 解码视频\n- 简易 RTMP 推流 Demo\n- FFmpeg 命令行转码",
    "- H.264 编码(I/P/B+NAL) / MediaCodec 异步模式 / 音画同步 / RTMP/HLS 协议对比",
    "- FFmpeg 滤镜链 / DRM/Widevine / SEI 数据注入 / WebRTC ICE/DTLS",
    "- [ ] 跑通 MediaCodec 硬解码\n- [ ] 说出协议区别\n- [ ] 画播放器架构图",
    "| 编解码 | ⬜ | — | — | — | |\n| 播放器 | ⬜ | — | — | — | |\n| 推流拉流 | ⬜ | — | — | — | |\n| FFmpeg | ⬜ | — | — | — | |\n| ExoPlayer | ⬜ | — | — | — | |")

add("12-跨平台开发", "12 · 跨平台开发",
    "Flutter 三树渲染→RN JS Bridge→CMP 共享 UI",
    "- **项目**：跨平台 Todo App（Flutter）\n- **闭环目标**：同 App 跑 Android+iOS",
    "1. Flutter（Widget/Element/RenderObject 三树+Engine+Platform Channel）\n2. React Native（JS Bridge+Fabric JSI+@ReactMethod）\n3. Compose Multiplatform（共享UI+expect/actual）",
    "- Flutter 三棵树渲染流程？\n- Flutter vs RN vs CMP 选型？\n- Platform Channel 通信原理？",
    "- Flutter 写跨平台页面\n- RN Fabric 写原生模块\n- 对比热重载体验",
    "- Flutter 三树渲染 / RN Bridge vs Fabric / CMP expect/actual",
    "- Flutter Engine Skia/Impeller 细节 / RN 旧 Bridge 瓶颈 / CMP iOS 渲染差异",
    "- [ ] 解释 Flutter 三树渲染\n- [ ] 说出三框架选型标准",
    "| Flutter | ⬜ | — | — | — | |\n| React Native | ⬜ | — | — | — | |\n| CMP | ⬜ | — | — | — | |")

add("13-构建与工程化", "13 · 构建与工程化",
    "Gradle 三阶段→CI/CD 流水线→测试金字塔→代码规范",
    "- **项目**：为一个模块写三层测试\n- **闭环目标**：JUnit 单元+Robolectric 集成+Espresso UI 测试",
    "1. Gradle（Init→Config→Exec+Task DAG+自定义插件）\n2. CI/CD（Jenkins/GitLab CI+AAB+自动签名）\n3. 测试（JUnit/Mockito/Robolectric/Espresso）\n4. 代码规范（ktlint/detekt/Git Flow）",
    "- Gradle 构建三阶段？\n- 如何写自定义 Gradle 插件？\n- 测试金字塔层次？\n- CI/CD 流水线设计？",
    "- 自定义 Gradle Task\n- GitLab CI 自动打包 AAB\n- ViewModel 完整单元测试",
    "- Gradle Task DAG / JUnit+Mockito+Robolectric / ktlint/detekt",
    "- Transform 字节码插桩(废弃) / Gradle Build Cache / Robolectric Shadow",
    "- [ ] 自定义 Gradle Task\n- [ ] 设计 CI/CD 流水线\n- [ ] 写三层测试",
    "| Gradle | ⬜ | — | — | — | |\n| CI/CD | ⬜ | — | — | — | |\n| 测试 | ⬜ | — | — | — | |\n| 规范 | ⬜ | — | — | — | |")

add("14-AI与安卓结合", "14 · AI与安卓结合",
    "AI 辅助开发→大模型端侧部署→AI 编程思维",
    "- **项目**：端侧图片分类 App\n- **闭环目标**：TFLite 加载量化模型→CameraX 实时识别→显示结果",
    "1. AI 辅助开发（Copilot/CodeGeeX+Prompt Engineering）\n2. 大模型落地（量化压缩+TFLite/ONNX+GPU加速）\n3. AI 编程思维（辅助重构+异常分析+APM智能告警）",
    "- 端侧部署大模型挑战？\n- TFLite vs ONNX Runtime？\n- 模型量化精度损失控制？",
    "- TFLite 部署量化模型\n- Copilot 生成单元测试\n- 对比 FP32 vs INT8 推理速度",
    "- 模型量化(FP32→INT8) / TFLite GPU Delegate / Prompt Engineering",
    "- 模型蒸馏 / ONNX Runtime 高级 / MediaPipe",
    "- [ ] 端侧跑量化模型\n- [ ] AI 工具提升效率\n- [ ] 说出模型压缩方法",
    "| AI 辅助开发 | ⬜ | — | — | — | |\n| 大模型落地 | ⬜ | — | — | — | |\n| AI 编程思维 | ⬜ | — | — | — | |")

add("15-性能优化工具专题", "15 · 性能优化工具专题",
    "系统级追踪→内存分析→CPU分析→APM监控→其他专项",
    "- **项目**：App 全链路诊断\n- **闭环目标**：Perfetto→Memory→CPU→Network 全流程+诊断报告",
    "1. 系统级追踪（Perfetto+Systrace）\n2. 内存分析（Memory Profiler+LeakCanary2+MAT）\n3. CPU/线程（CPU Profiler+Simpleperf）\n4. APM 线上（Matrix+KOOM+Sentry）",
    "- Perfetto vs Systrace 选型？\n- LeakCanary 检测原理？\n- Matrix 卡顿监控原理？\n- KOOM Fork Dump 优势？",
    "- Perfetto 录制 30s trace+SQL 查询\n- LeakCanary 检测真实泄漏\n- Matrix 接入项目",
    "- Perfetto SQL 查询 / LeakCanary ObjectWatcher→HeapDump→Shark / Matrix Choreographer+Looper / KOOM Fork+Suspend",
    "- Simpleperf 高级 / Sentry Session Replay / MAT OQL",
    "- [ ] Perfetto 完成启动 trace 分析\n- [ ] LeakCanary 完整流程\n- [ ] Matrix vs KOOM 对比",
    "| 系统级追踪 | ⬜ | — | — | — | |\n| 内存分析 | ⬜ | — | — | — | |\n| CPU分析 | ⬜ | — | — | — | |\n| APM监控 | ⬜ | — | — | — | |\n| 其他专项 | ⬜ | — | — | — | |")

add("16-物联网与通信", "16 · 物联网与通信",
    "BLE GATT 协议→Wi-Fi 局域网通信→Matter 智能家居",
    "- **项目**：BLE 心率监测 Demo\n- **闭环目标**：扫描→连接→读取心率 Service 数据→显示",
    "1. BLE（GATT+Service/Characteristic+扫描/连接/读写/通知）\n2. Wi-Fi 通信（P2P+mDNS+Socket）\n3. Matter 协议（智能家居统一应用层）",
    "- BLE GATT 协议结构？\n- BLE 与经典蓝牙区别？\n- mDNS 服务发现原理？",
    "- BLE 扫描+连接+读数据 Demo\n- mDNS 局域网设备发现\n- Matter 概念了解",
    "- BLE GATT Service/Characteristic / BluetoothGatt 连接流程 / mDNS 服务发现",
    "- Wi-Fi Aware(NAN) / Matter Thread/Wi-Fi 承载 / BLE MTU 细节",
    "- [ ] 跑通 BLE 连接读数据\n- [ ] 说出 BLE 与经典蓝牙区别",
    "| BLE 蓝牙 | ⬜ | — | — | — | |\n| Wi-Fi 通信 | ⬜ | — | — | — | |\n| Matter | ⬜ | — | — | — | |")

add("17-出海应用与适配", "17 · 出海应用与适配",
    "隐私权限→厂商兼容→国际化",
    "- **项目**：适配一个 App\n- **闭环目标**：Scoped Storage 文件访问+多语言资源+RTL 布局",
    "1. 隐私权限（Android10/11/13/14+GDPR/CCPA）\n2. 厂商兼容（华为HMS+后台限制）\n3. 国际化（strings-xx+RTL+ICU格式化+AAB分发）",
    "- Scoped Storage 影响与适配？\n- Android11+ 分区存储强制？\n- GDPR 核心要求？",
    "- 文件访问迁移 Scoped Storage\n- 英文/阿拉伯文多语言\n- 华为/小米/OPPO 兼容测试",
    "- Scoped Storage / GDPR 同意+删除权 / 多语言+RTL",
    "- 华为 HMS Push Kit / NAN / AAB 按需分发",
    "- [ ] 适配 Scoped Storage\n- [ ] 多语言+RTL\n- [ ] 说出 GDPR 要求",
    "| 隐私权限 | ⬜ | — | — | — | |\n| 厂商兼容 | ⬜ | — | — | — | |\n| 国际化 | ⬜ | — | — | — | |")

add("18-高频面试题汇总", "18 · 高频面试题汇总",
    "基础题→架构设计题→性能优化题→系统底层题",
    "- **项目**：每道架构题画一张架构图\n- **闭环目标**：STAR 方法回答每道架构设计题",
    "1. 基础题（Handler/HashMap/Glide/Activity）\n2. 架构设计题（图片加载/IM消息/组件化路由/网络层）\n3. 性能优化题（启动/内存泄漏/RecyclerView/包体积）\n4. 系统底层题（Activity启动/Binder/Zygote/View绘制）",
    "- 设计图片加载框架？\n- App 启动优化全链路？\n- Activity 展示完整流程？",
    "- 架构题画架构图\n- 性能题准备数据支撑\n- 系统题准备 Binder 序列图",
    "- Handler/Glide 源码级 / STAR 回答法+Trade-off / 源码调用链路",
    "- 冷门 API 细节 / 框架全源码",
    "- [ ] 架构题能画架构图\n- [ ] 性能题有量化数据\n- [ ] 系统题能画调用链",
    "| 基础题 | ⬜ | — | — | — | |\n| 架构题 | ⬜ | — | — | — | |\n| 性能题 | ⬜ | — | — | — | |\n| 系统题 | ⬜ | — | — | — | |")

add("19-开源框架专题", "19 · 开源框架专题",
    "Glide→OkHttp→Retrofit→ARouter→RxJava→EventBus→Tinker→MMKV→LeakCanary",
    "- **项目**：阅读 Glide Engine.load() 源码\n- **闭环目标**：画出 Glide 图片加载完整流程图",
    "1. Glide（三级缓存+Bitmap复用+生命周期）\n2. OkHttp（五大拦截器链+连接池）\n3. Retrofit（动态代理+注解解析）\n4. ARouter（APT路由表+拦截器）\n5. RxJava（操作符+线程调度+背压）\n6-9. EventBus/Tinker/MMKV/LeakCanary",
    "- Glide 三级缓存+Active Resources？\n- OkHttp 连接池复用？\n- Retrofit 动态代理原理？\n- ARouter 路由表生成？",
    "- 简化版 Glide\n- 简化版 OkHttp 拦截器链\n- Retrofit 动态代理 Demo",
    "- Glide 三级缓存 / OkHttp 5拦截器 / Retrofit 动态代理+ServiceMethod / ARouter APT",
    "- Glide Gif 细节 / OkHttp HTTP/2 Stream / RxJava lift()",
    "- [ ] 画 Glide 加载流程\n- [ ] 画 OkHttp 拦截器链\n- [ ] 解释 Retrofit 动态代理",
    "| Glide | ⬜ | — | — | — | |\n| OkHttp | ⬜ | — | — | — | |\n| Retrofit | ⬜ | — | — | — | |\n| ARouter | ⬜ | — | — | — | |\n| RxJava | ⬜ | — | — | — | |\n| EventBus | ⬜ | — | — | — | |\n| Tinker | ⬜ | — | — | — | |\n| MMKV | ⬜ | — | — | — | |\n| LeakCanary | ⬜ | — | — | — | |")

add("20-并发编程与线程安全", "20 · 并发编程与线程安全",
    "Java 并发→Android 线程模型→Kotlin 协程并发→线程安全→锁机制",
    "- **项目**：图片批量下载\n- **闭环目标**：对比线程池 vs 协程两种并发，对比吞吐量和内存",
    "1. Java 并发（ThreadPoolExecutor+Atomic+AQS）\n2. Android 线程模型（Looper+HandlerThread）\n3. Kotlin 协程并发（结构化+Mutex/Channel）\n4. 线程安全（不可变+ConcurrentHashMap+ThreadLocal）\n5. 锁机制（synchronized锁升级+ReentrantLock+死锁）",
    "- synchronized vs ReentrantLock？\n- ThreadPoolExecutor 参数计算？\n- ConcurrentHashMap 线程安全原理？\n- 协程取消协作？",
    "- 线程池下载 50 张图片\n- 协程改写并对比\n- 死锁 Demo+jstack 排查",
    "- synchronized 锁升级 / ThreadPoolExecutor 调参 / ConcurrentHashMap 演进 / 协程结构化并发",
    "- AQS 源码 / LockSupport / Actor 模式",
    "- [ ] 手写 ThreadPoolExecutor\n- [ ] 解释锁升级\n- [ ] 排查死锁",
    "| Java 并发 | ⬜ | — | — | — | |\n| Android 线程 | ⬜ | — | — | — | |\n| 协程并发 | ⬜ | — | — | — | |\n| 线程安全 | ⬜ | — | — | — | |\n| 锁机制 | ⬜ | — | — | — | |")

add("21-内存管理", "21 · 内存管理",
    "JVM 内存模型→ART GC 演进→内存分配→内存监控→Native 内存",
    "- **项目**：制造内存压力实验\n- **闭环目标**：分配对象→观察 GC 日志→触发 onTrimMemory→实现降级策略",
    "1. JVM 内存模型（堆/栈/方法区+对象创建+TLAB+逃逸分析）\n2. ART GC（Concurrent Copying GC+Baker Barrier）\n3. 内存分配（Bump Pointer+RosAlloc+RegionSpace）\n4. 内存监控（onTrimMemory+LMK oom_adj+降级策略）\n5. Native 内存（jemalloc+mmap+ashmem+泄漏检测）",
    "- ART GC 与 Dalvik GC 差异？\n- Concurrent Copying GC ~1ms 停顿原理？\n- onTrimMemory 触发时机？\n- LMK oom_adj 回收顺序？",
    "- 实验不同级别 onTrimMemory 回调\n- dumpsys meminfo 分析\n- 图片缓存降级策略",
    "- ART Concurrent Copying GC+Baker Read Barrier / onTrimMemory 6级别 / LMK oom_adj / jemalloc arena/bin/run+tcache",
    "- Dalvik GC 细节 / RegionSpace 管理 / malloc_debug",
    "- [ ] 解释 ART GC 低停顿原理\n- [ ] 实现 onTrimMemory 降级\n- [ ] 说出 LMK 回收顺序",
    "| JVM 内存 | ⬜ | — | — | — | |\n| ART GC | ⬜ | — | — | — | |\n| 内存分配 | ⬜ | — | — | — | |\n| 内存监控 | ⬜ | — | — | — | |\n| Native 内存 | ⬜ | — | — | — | |")

add("22-高性能编程", "22 · 高性能编程",
    "对象池化→零拷贝→序列化优化→IO优化→编译优化",
    "- **项目**：JSON vs ProtoBuf 序列化对比\n- **闭环目标**：同数据结构两种序列化耗时对比→量化报告",
    "1. 对象复用（Message池+RecyclerView缓存+Glide BitmapPool）\n2. 零拷贝（Binder mmap+sendfile+ashmem+DirectByteBuffer）\n3. 序列化优化（Parcelable vs Serializable+ProtoBuf vs JSON）\n4. IO优化（NIO vs BIO+mmap+WAL+DiskLruCache）\n5. 编译优化（R8三阶段+Baseline Profile+PGO）",
    "- Message 池化原理？\n- Binder 一次拷贝 vs sendfile？\n- ProtoBuf 比 JSON 快多少？\n- Baseline Profile 效果？\n- RecyclerView 四级缓存？",
    "- 对比 Parcelable vs Serializable 耗时\n- Message.obtain() vs new Message()\n- Baseline Profile 测量启动提升",
    "- Message 池化(sPool+享元) / RecyclerView 四级缓存 / ProtoBuf Varint+ZigZag / R8 三阶段",
    "- FlatBuffers vs ProtoBuf / PGO 细节 / jemalloc tcache",
    "- [ ] 解释 Message 池化\n- [ ] RecyclerView 四级缓存\n- [ ] 对比序列化优劣",
    "| 对象池化 | ⬜ | — | — | — | |\n| 零拷贝 | ⬜ | — | — | — | |\n| 序列化 | ⬜ | — | — | — | |\n| IO优化 | ⬜ | — | — | — | |\n| 编译优化 | ⬜ | — | — | — | |")


# ====== 生成函数 ======
def build_tree(skeleton, indent=0):
    lines = []
    for item in skeleton:
        if isinstance(item, str):
            lines.append("    " * indent + f"├── {item}")
        elif isinstance(item, list) and len(item) == 2:
            title, children = item
            lines.append("    " * indent + f"├── 📁 {title}")
            lines.extend(build_tree(children, indent + 1))
    return lines

def write_guide(module_id):
    guide = DATA[module_id].copy()
    # 添加树形骨架
    sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))
    from generate_xmind import MODULES as XMIND_MODULES
    if module_id in XMIND_MODULES:
        tree = build_tree(XMIND_MODULES[module_id]["skeleton"])
        guide["tree_skeleton"] = "\n".join(tree)
    else:
        guide["tree_skeleton"] = "（请查看 知识骨架.xmind）"
    # 添加原则
    for i in range(1, 11):
        guide[f"p{i}"] = PRINCIPLES[list(PRINCIPLES.keys())[i-1]]
    # 格式化为空字段给默认值
    for k in ["quick_start_apis","templates_to_save","analogy_mapping"]:
        if k not in guide or not guide[k]:
            guide[k] = "—"
    content = TEMPLATE.format(**guide)
    dir_path = os.path.join(PROJECT_ROOT, module_id)
    os.makedirs(dir_path, exist_ok=True)
    file_path = os.path.join(dir_path, "学习指南.md")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ {module_id} ({len(content)} 字)")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python generate_lg_v2.py <模块编号|all>")
        sys.exit(0)
    target = sys.argv[1]
    if target == "all":
        for mid in DATA:
            write_guide(mid)
        print(f"\n✅ 全部 {len(DATA)} 个模块学习指南已生成！")
    elif target in DATA:
        write_guide(target)
    else:
        print(f"❌ 未知: {target}")
