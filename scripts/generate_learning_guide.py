#!/usr/bin/env python3
"""
学习指南生成器 — 为每个模块生成遵循10条学习原则的学习指南
从 XMind 生成器中的 skeleton 数据直接生成结构化的 学习指南.md
"""
import os

PROJECT_ROOT = "/home/heavy/AndroidJob"

# ─── 10 条学习原则 ───
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

LEARNING_GUIDE_TEMPLATE = """# {module_title} — 学习指南

> 遵循「先框架后细节、先闭环后原理、先实战后理论、学即用常沉淀、拆解难点不贪多」核心心法

---

## 🗺️ 知识骨架全景图

打开本目录下的 `知识骨架.xmind` 查看完整知识结构。

{tree_skeleton}

---

## 🎯 10 条学习原则落地指南

### 1. 骨架先行 — 建立整体认知地图

> {p1_desc}

**本模块骨架**：{skeleton_desc}

**行动**：打开 `知识骨架.xmind`，花 5 分钟浏览全部节点，建立模块全局印象，再按阶段逐一攻克。

---

### 2. 最小闭环 — 先跑通再深挖

> {p2_desc}

**本模块最小闭环项目**：
{minimal_project}

**检查点**：能否独立跑通这个闭环？如果能，说明框架理解正确；如果不能，回头补最基础的 API 调用。

---

### 3. 问题驱动 — 缺什么学什么

> {p3_desc}

**核心面试问题驱动学习**：
{interview_questions}

**行动**：选一个问题 → 尝试自己回答 → 对比标准答案 → 补知识点 → 再回答一遍。

---

### 4. 单点击穿 — 一次只攻克一个

> {p4_desc}

**建议学习顺序**（一次只学一个子模块）：
{learning_sequence}

**规则**：当前子模块没跑通最小闭环前，绝不开下一个。

---

### 5. 学以致用 — 学了立刻用

> {p5_desc}

**每个子模块的实战任务**：
{practical_tasks}

**输出物**：每个任务完成后应有可运行的代码或可展示的 Demo。

---

### 6. 先会后懂 — 允许先会用

> {p6_desc}

**先用起来的关键 API**（暂时不需要深究源码）：
{quick_start_apis}

**边界**：知道「怎么用」和「什么时候用」就行，面试前再补「为什么这样设计」。

---

### 7. 模板沉淀 — 把知识变成资产

> {p7_desc}

**建议沉淀的模板**：
{templates_to_save}

**工具**：用 Obsidian/Notion 建立个人代码片段库，面试前直接复习。

---

### 8. 新旧嫁接 — 用已知类比未知

> {p8_desc}

**本模块的类比映射**：
{analogy_mapping}

**技巧**：每学一个新概念，问自己「这和我已知的 XX 有什么异同？」

---

### 9. 刻意屏蔽 — 先学核心再补边缘

> {p9_desc}

**本模块的核心主干**（必须掌握）：
{core_content}

**本模块的边缘知识**（先跳过，用到再学）：
{edge_content}

---

### 10. 闭环复盘 — 串联成体系

> {p10_desc}

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

# ─── 每个模块的具体内容 ───

MODULE_GUIDES = {}

def build_tree(skeleton, indent=0):
    """将骨架转为文本树形图"""
    lines = []
    for item in skeleton:
        if isinstance(item, str):
            lines.append("    " * indent + f"├── {item}")
        elif isinstance(item, list) and len(item) == 2:
            title, children = item
            lines.append("    " * indent + f"├── 📁 {title}")
            lines.extend(build_tree(children, indent + 1))
    return lines


# ========== 01-安卓语言基础 ==========
MODULE_GUIDES["01-安卓语言基础"] = {
    "module_title": "01 · 安卓语言基础",
    "tree_skeleton": "",
    "p1_desc": PRINCIPLES["骨架先行"],
    "skeleton_desc": "Kotlin 核心特性 → 协程并发 → Java 进阶 → KMM 跨平台，四层递进",
    "p2_desc": PRINCIPLES["最小闭环"],
    "minimal_project": """
- **项目**：天气预报 App
- **技术栈**：Kotlin + MVVM + 协程 + Flow + Retrofit
- **闭环目标**：搜索城市 → 网络请求 → UI 更新展示天气
- **预估时间**：2-3 小时跑通""",
    "p3_desc": PRINCIPLES["问题驱动"],
    "interview_questions": """
- ❓ suspend 函数的底层实现是怎样的？（CPS 转换 + 状态机）
- ❓ Flow vs LiveData vs StateFlow 各适用于什么场景？
- ❓ 协程取消为什么需要协作？（isActive / ensureActive）
- ❓ Kotlin inline 函数如何减少对象创建？
- ❓ JVM 内存模型与 GC 机制？""",
    "p4_desc": PRINCIPLES["单点击穿"],
    "learning_sequence": """
1. 先学 Kotlin 核心特性（扩展函数、高阶函数、委托、密封类、数据类）
2. 再学 Kotlin 协程（suspend → Flow → StateFlow → 结构化并发）
3. 然后补 Java 进阶（JVM 内存模型、GC、APT）
4. 最后了解 KMM 跨平台""",
    "p5_desc": PRINCIPLES["学以致用"],
    "practical_tasks": """
- 用扩展函数封装一个 View 的通用操作（如 show/hide/gone）
- 用 sealed class 定义一个网络请求状态机（Loading/Success/Error）
- 用 Flow 实现一个搜索防抖（debounce + flatMapLatest）
- 用协程写一个并发请求多个 API 的方法""",
    "p6_desc": PRINCIPLES["先会后懂"],
    "quick_start_apis": """
- `suspend fun`：标记挂起函数，自动生成 Continuation 回调
- `viewModelScope.launch { }`：在 ViewModel 作用域启动协程
- `flow { emit(value) }`：创建冷流
- `MutableStateFlow(initial)`：创建可观察状态""",
    "p7_desc": PRINCIPLES["模板沉淀"],
    "templates_to_save": """
- Kotlin 协程常用模板（网络请求 + 异常处理）
- sealed class 状态机模板（Loading/Success/Error/Empty）
- Flow 搜索防抖模板
- Kotlin 扩展函数常用工具类""",
    "p8_desc": PRINCIPLES["新旧嫁接"],
    "analogy_mapping": """
- Java 匿名内部类 → Kotlin lambda 表达式
- Java Future/Callback → Kotlin suspend 挂起函数
- Java RxJava → Kotlin Flow
- Java static 方法 → Kotlin 顶层函数/companion object""",
    "p9_desc": PRINCIPLES["刻意屏蔽"],
    "core_content": """
- Kotlin 扩展函数、高阶函数、委托属性、密封类、数据类
- 协程基础（suspend、Dispatchers、viewModelScope）
- Flow/StateFlow 基本用法
- JVM 堆栈结构、GC Roots""",
    "edge_content": """
- KMM expect/actual 详细用法（用到再学）
- inline/noinline/crossinline 编译细节
- Kotlin 编译器插件开发""",
    "p10_desc": PRINCIPLES["闭环复盘"],
    "review_checklist": """
- [ ] 能独立用 Kotlin + 协程写一个网络请求页面
- [ ] 能解释 suspend 函数的 CPS 转换原理
- [ ] 能说清楚 Flow vs LiveData vs StateFlow 的选择标准
- [ ] 能画出 JVM 内存区域分布图
- [ ] 有自己的 Kotlin 协程代码模板库""",
    "progress_table": """
| Kotlin 核心特性 | ⬜ 待学习 | — | — | — | |
| Kotlin 协程 | ⬜ 待学习 | — | — | — | |
| Java 进阶 | ⬜ 待学习 | — | — | — | |
| KMM 跨平台 | ⬜ 待学习 | — | — | — | |""",
}

# ========== 02-安卓核心机制 ==========
MODULE_GUIDES["02-安卓核心机制"] = {
    "module_title": "02 · 安卓核心机制",
    "skeleton_desc": "四大组件生命周期 → 组件通信 → Binder IPC → Handler 消息循环，从表象到底层",
    "minimal_project": """
- **项目**：IPC 跨进程通信 Demo
- **技术栈**：AIDL + Service
- **闭环目标**：定义 AIDL 接口 → Service 实现 → 客户端调用 → 复杂对象跨进程传输
- **预估时间**：1-2 小时跑通""",
    "interview_questions": """
- ❓ 点击桌面图标到 Activity 展示的完整流程？
- ❓ Binder 为什么只需要一次拷贝？（mmap 原理）
- ❓ Handler 消息延迟的原因有哪些？
- ❓ Activity 四种启动模式与 onNewIntent 的关系？
- ❓ Service 与 Thread 的本质区别？""",
    "learning_sequence": """
1. 四大组件全景（生命周期、启动模式、注册方式）
2. 生命周期管理（Activity/Fragment/异常恢复/ViewModel 存活原理）
3. 组件间通信方式对比（Intent → EventBus → LiveEventBus → ContentProvider）
4. Binder 机制深度（驱动层 mmap → AIDL 生成类 → ashmem 共享内存）
5. Handler 消息机制源码级（MessageQueue → Looper → 同步屏障 → IdleHandler）""",
    "practical_tasks": """
- 实现一个跨进程的 Service 调用（AIDL）
- 写一个 Handler 消息机制完整的 Demo（含同步屏障 + IdleHandler）
- 实现 Activity 四种启动模式的效果演示
- 对比 EventBus 和 LiveData 通信的差异""",
    "quick_start_apis": """
- `startActivity(Intent)` / `startActivityForResult`：Activity 启动
- `bindService(Intent, ServiceConnection, flags)`：Service 绑定
- `registerReceiver(BroadcastReceiver, IntentFilter)`：广播注册
- `Handler(Looper.getMainLooper()).post { }`：主线程发消息""",
    "templates_to_save": """
- Activity 生命周期回调完整模板
- AIDL 接口定义 + 实现模板
- Handler 消息机制图解（时序图）
- 四大组件对比速查表""",
    "analogy_mapping": """
- Binder → Linux 管道/socket（对比通信方式）
- Handler → 事件循环 EventLoop（类比 JS/Libuv）
- ContentProvider → RESTful API（都是数据抽象层）""",
    "core_content": """
- Activity 四种启动模式 + onNewIntent
- Service 启动/绑定/前台三种形态
- Handler 消息机制源码（MessageQueue + Looper + epoll）
- Binder 一次拷贝原理（mmap）""",
    "edge_content": """
- BroadcastReceiver 有序广播细节
- ContentProvider 批量操作
- Binder 线程池上限 16 线程的源码验证""",
    "review_checklist": """
- [ ] 能画出 Activity 启动流程图（从桌面到 onCreate）
- [ ] 能解释 Binder mmap 为什么只拷贝一次
- [ ] 能手写 Handler 消息机制的简化版
- [ ] 能说出四大组件各自的使用场景和限制""",
    "progress_table": """
| 四大组件全景 | ⬜ 待学习 | — | — | — | |
| 生命周期管理 | ⬜ 待学习 | — | — | — | |
| 组件间通信 | ⬜ 待学习 | — | — | — | |
| Binder 机制 | ⬜ 待学习 | — | — | — | |
| Handler 机制 | ⬜ 待学习 | — | — | — | |""",
}

# ========== 03-数据结构与算法 ==========
MODULE_GUIDES["03-数据结构与算法"] = {
    "module_title": "03 · 数据结构与算法",
    "skeleton_desc": "常用数据结构 API → 排序/查找算法 → 动态规划 → 安卓中的算法落地（SparseArray/消息池）",
    "minimal_project": """
- **刷题路径**：数组(5题) → 链表(5题) → 二叉树(5题) → DP(5题)
- **闭环目标**：每个数据结构的核心操作能手写，能口述时间复杂度
- **预估时间**：每天 1-2 题，2-3 周完成核心 20 题""",
    "interview_questions": """
- ❓ HashMap put 方法的完整流程（hash→index→链表→红黑树）？
- ❓ SparseArray 和 HashMap 的本质区别？为什么安卓推荐 SparseArray？
- ❓ 手写快排，分析时间/空间复杂度？
- ❓ LRU Cache 如何实现？LinkedHashMap 如何做到 O(1) 访问？""",
    "learning_sequence": """
1. 数据结构基础（ArrayList 扩容、HashMap 源码、SparseArray/ArrayMap）
2. 排序算法手写（快排、归并、堆排）+ 复杂度推导
3. 查找与遍历（二分查找、BFS/DFS、布隆过滤器）
4. 动态规划（0-1 背包、LCS）""",
    "practical_tasks": """
- 手写 HashMap 简化版（数组+链表）
- 手写 LRU Cache（LinkedHashMap 实现）
- 用 SparseArray 优化一个 key 为 int 的 Map 场景
- 手写快排 + 三路分区优化""",
    "quick_start_apis": """
- `HashMap.put/get` — O(1) 平均，O(n) 最坏（红黑树 O(log n)）
- `SparseArray.put/get` — 二分查找，适合 key 稀疏场景
- `ArrayDeque` — 双端队列，比 Stack/LinkedList 快
- `Collections.sort()` — TimSort，混合排序""",
    "templates_to_save": """
- 快排/归并/堆排手写模板
- BFS/DFS 框架模板
- LRU Cache 模板（LinkedHashMap）
- 常见数据结构 API 复杂度速查表""",
    "analogy_mapping": """
- HashMap 链表+红黑树 → 图书馆索引（先找楼层→找书架→找书）
- SparseArray 二分查找 → 字典按拼音索引
- BFS 层序遍历 → 水波纹扩散
- DFS 深度优先 → 走迷宫一直走到底""",
    "core_content": """
- HashMap 源码（put/get/resize/树化）
- ArrayList 扩容 1.5 倍（位运算优化）
- 快排 + 归并排序（手写 + 复杂度分析）
- 二分查找边界处理
- SparseArray 二分插入原理""",
    "edge_content": """
- 红黑树的自平衡操作细节
- 布隆过滤器的数学推导
- DP 复杂问题的状态压缩优化
- 图高级算法（Dijkstra/Floyd）""",
    "review_checklist": """
- [ ] 能手写 HashMap 简化版
- [ ] 能手写快排和归并排序
- [ ] 能解释 SparseArray 比 HashMap 省内存的原因
- [ ] LeetCode Hot 100 完成 30+ 题""",
    "progress_table": """
| 数据结构基础 | ⬜ 待学习 | — | — | — | |
| 排序算法 | ⬜ 待学习 | — | — | — | |
| 查找与遍历 | ⬜ 待学习 | — | — | — | |
| 动态规划 | ⬜ 待学习 | — | — | — | |""",
}

# ========== 04-UI与View体系 ==========
MODULE_GUIDES["04-UI与View体系"] = {
    "module_title": "04 · UI与View体系",
    "skeleton_desc": "View 树全景（Measure→Layout→Draw）→ 事件分发 → 自定义 View → 动画系统",
    "minimal_project": """
- **项目**：自定义圆形进度条
- **技术栈**：自定义 View + 属性动画
- **闭环目标**：onMeasure(处理wrap_content) → onDraw(画圆弧) → ValueAnimator(0→100)
- **预估时间**：2-3 小时""",
    "interview_questions": """
- ❓ View 绘制流程三阶段各自做了什么？
- ❓ MeasureSpec 是如何确定的？（父View限制 + 子View LayoutParams）
- ❓ 事件分发的三方法调用链是什么？ACTION_CANCEL 何时触发？
- ❓ requestLayout 和 invalidate 的区别？各自的触发链路？
- ❓ 滑动冲突如何解决？（外部拦截法 vs 内部拦截法）""",
    "learning_sequence": """
1. View 绘制流程源码走读（Measure → Layout → Draw → ViewRootImpl）
2. 事件分发机制（三方法调用链 + 源码分析 + 滑动冲突）
3. 自定义 View 实战（onMeasure/onLayout/onDraw + Canvas 绘制）
4. 动画系统（补间/帧/属性/过渡动画）""",
    "practical_tasks": """
- 实现一个流式布局（自动换行的 ViewGroup）
- 解决 ViewPager 嵌套 RecyclerView 的滑动冲突
- 用贝塞尔曲线实现一个波浪动画
- 自定义一个带动画的评分组件""",
    "quick_start_apis": """
- `View.measure(widthMeasureSpec, heightMeasureSpec)`：测量
- `View.layout(l, t, r, b)`：布局
- `View.draw(canvas)`：绘制
- `ValueAnimator.ofInt(0, 100).start()`：属性动画""",
    "templates_to_save": """
- 自定义 View 模板（onMeasure + onDraw 骨架代码）
- 事件分发流程图
- 滑动冲突解决方案模板（外部拦截/内部拦截）
- 属性动画常用写法模板""",
    "analogy_mapping": """
- View 绘制流程 → 画家作画（量画布→定位置→画内容）
- 事件分发 → 领导审批链（上传下达，中间可拦截）
- 属性动画 → 遥控器调音量（实时改变真实属性）""",
    "core_content": """
- MeasureSpec 三种模式（EXACTLY/AT_MOST/UNSPECIFIED）
- 事件分发三方法调用链+源码
- 自定义 View：onMeasure + onDraw + 自定义属性
- 属性动画 vs 补间动画本质区别""",
    "edge_content": """
- Transition 过渡动画高级用法
- SurfaceView vs TextureView 底层差异
- RenderNode 硬件加速细节""",
    "review_checklist": """
- [ ] 能画出 View 绘制三阶段流程图
- [ ] 能画出事件分发完整调用链
- [ ] 能独立写一个自定义 View（含自定义属性）
- [ ] 能解决常见的嵌套滑动冲突""",
    "progress_table": """
| View 绘制流程 | ⬜ 待学习 | — | — | — | |
| 事件分发 | ⬜ 待学习 | — | — | — | |
| 自定义 View | ⬜ 待学习 | — | — | — | |
| 动画系统 | ⬜ 待学习 | — | — | — | |""",
}

# ========== 05-Jetpack组件体系 ==========
MODULE_GUIDES["05-Jetpack组件体系"] = {
    "module_title": "05 · Jetpack组件体系",
    "skeleton_desc": "ViewModel/LiveData（状态管理基石）→ Room（持久化）→ Navigation（导航）→ Hilt（DI）→ Compose（声明式 UI）",
    "minimal_project": """
- **项目**：记事本 App
- **技术栈**：Compose + Room + Hilt + MVVM
- **闭环目标**：笔记增删改查 + Flow 响应式列表
- **预估时间**：3-4 小时""",
    "interview_questions": """
- ❓ ViewModel 如何在横竖屏切换时保持数据？
- ❓ Compose 重组机制与 View invalidate 的本质区别？
- ❓ Room 的 Flow 查询如何感知数据变更？
- ❓ Hilt 的 Scope 层级和作用域管理？
- ❓ StateFlow vs LiveData 的选择策略？""",
    "learning_sequence": """
1. ViewModel + LiveData（生命周期感知 + SavedStateHandle）
2. Room 数据库（三剑客注解 + Migration + Flow 查询）
3. Navigation（NavGraph + SafeArgs + DeepLink）
4. Hilt 依赖注入（Scope 层级 + @Binds/@Provides）
5. Compose（重组机制 + 状态管理 + 副作用 API）
6. 其他组件（WorkManager + DataStore + Paging 3）""",
    "practical_tasks": """
- 用 ViewModel + StateFlow 改造一个 LiveData 项目
- 写 Room Migration 测试（版本 1→2 新增字段）
- 实现一个 DeepLink 从通知跳转到详情页
- 用 Compose 写一个带搜索的列表页（LazyColumn + Flow）""",
    "quick_start_apis": """
- `ViewModelProvider(this).get(MyViewModel::class.java)`：获取 ViewModel
- `liveData.observe(lifecycleOwner) { }`：观察 LiveData
- `@Entity data class User(...)`：Room 实体定义
- `@Composable fun Greeting(name: String) { }`：Compose 组件""",
    "templates_to_save": """
- ViewModel + StateFlow 标准模板
- Room DAO CRUD 模板
- Hilt Module 定义模板
- Compose 状态管理模板（remember + mutableStateOf）""",
    "analogy_mapping": """
- ViewModel → 乐队指挥（不管乐手换人，乐谱不变）
- Room → Excel 表格（定义列→增删改查→自动刷新）
- Hilt → 外卖平台（声明需求→自动配送）
- Compose → 公式推导（输入变了，结果自动重算）""",
    "core_content": """
- ViewModel 生命周期 + SavedStateHandle
- Room @Entity/@DAO/@Database + Migration
- Hilt Scope 层级(Singleton/ViewModel/Fragment)
- Compose 重组、remember、mutableStateOf、副作用
- Navigation SafeArgs + DeepLink""",
    "edge_content": """
- Compose 与 View 互操作细节
- Room FTS4 全文搜索
- Paging 3 RemoteMediator 双源加载""",
    "review_checklist": """
- [ ] 能用 Compose + Room + Hilt 写一个完整 CRUD 页面
- [ ] 能解释 Compose 重组和智能跳过的原理
- [ ] 能画出 Hilt 依赖注入的 Scope 层级图
- [ ] 能说出 ViewModel 和 onSaveInstanceState 的互补关系""",
    "progress_table": """
| ViewModel+LiveData | ⬜ 待学习 | — | — | — | |
| Room 数据库 | ⬜ 待学习 | — | — | — | |
| Navigation | ⬜ 待学习 | — | — | — | |
| Hilt 依赖注入 | ⬜ 待学习 | — | — | — | |
| Compose | ⬜ 待学习 | — | — | — | |
| 其他组件 | ⬜ 待学习 | — | — | — | |""",
}

# ========== 06-应用架构设计 ==========
MODULE_GUIDES["06-应用架构设计"] = {
    "module_title": "06 · 应用架构设计",
    "skeleton_desc": "MVVM（数据驱动）→ MVI（单向数据流）→ Clean Architecture（分层解耦）→ 组件化（模块隔离）→ 插件化（动态化）",
    "minimal_project": """
- **项目**：三模块组件化 Demo
- **技术栈**：app(壳) + home + profile + ARouter
- **闭环目标**：壳工程组装模块 → ARouter 路由跳转 → 模块间服务调用
- **预估时间**：3-4 小时""",
    "interview_questions": """
- ❓ MVVM 和 MVI 的核心区别是什么？各适合什么场景？
- ❓ 组件化模块间通信方案有哪些？（路由/接口下沉/SPI/事件总线）
- ❓ ARouter 路由表是如何生成的？（APT 编译期）
- ❓ Clean Architecture 三层职责和依赖方向？
- ❓ 插件化（Tinker）的 Dex 差量替换原理？""",
    "learning_sequence": """
1. MVVM 架构（ViewModel + Repository + DataBinding）
2. MVI 架构（State/Intent/Action + 单向数据流）
3. Clean Architecture（Domain/Data/Presentation + UseCase + DIP）
4. 组件化（ARouter + 接口下沉 + Gradle 模块管理）
5. 插件化（Tinker Dex 差量替换 + Shadow ClassLoader Hook）""",
    "practical_tasks": """
- 对比 MVVM 和 MVI 实现同一个功能页
- 将一个单模块项目拆分为 3 个模块 + 壳工程
- 实现 ARouter 拦截器（登录校验）
- 集成 Tinker 热修复到 Demo 项目""",
    "quick_start_apis": """
- `@HiltViewModel class MyVM @Inject constructor(...) : ViewModel()`：MVVM ViewModel
- `@Composable fun Screen(state: State, onIntent: (Intent) -> Unit)`：MVI 模式
- `@Route(path = "/home/main") class HomeActivity`：ARouter 路由
- `interface IAccountService { fun isLogin(): Boolean }`：SPI 服务接口""",
    "templates_to_save": """
- MVVM 标准项目结构模板
- MVI State/Intent/Reducer 模板
- 组件化模块划分模板（app/base/feature-xxx）
- ARouter 路由配置模板""",
    "analogy_mapping": """
- MVVM → 观察者模式（View 观察 ViewModel 状态变化）
- MVI → 银行柜台（提交表单→处理→更新余额）
- Clean Architecture → 三层办公楼（高层不直接找低层，通过中间层）
- 组件化 → 乐高积木（独立开发，统一组装）""",
    "core_content": """
- MVVM vs MVI 数据流向差异
- Repository 模式（数据层抽象）
- 组件化模块间通信 4 种方案
- ARouter APT 路由表生成原理
- Clean Architecture 分层职责""",
    "edge_content": """
- 插件化 ClassLoader 双亲委派机制突破
- Tinker 资源补丁 Resource Patch
- VirtualAPK 方案对比""",
    "review_checklist": """
- [ ] 能画出 MVVM 和 MVI 的数据流向图
- [ ] 能画出 Clean Architecture 三层依赖图
- [ ] 能解释组件化与插件化的本质区别
- [ ] 能独立设计一个中大型 App 的架构方案""",
    "progress_table": """
| MVVM 架构 | ⬜ 待学习 | — | — | — | |
| MVI 架构 | ⬜ 待学习 | — | — | — | |
| Clean Architecture | ⬜ 待学习 | — | — | — | |
| 组件化 | ⬜ 待学习 | — | — | — | |
| 插件化 | ⬜ 待学习 | — | — | — | |""",
}

# ========== 07-安卓系统与Framework ==========
MODULE_GUIDES["07-安卓系统与Framework"] = {
    "module_title": "07 · 安卓系统与Framework",
    "skeleton_desc": "5 层系统架构全景 → AMS（Activity 启动）→ PMS（包管理）→ WMS（窗口管理）→ WatchDog（死锁监控）",
    "minimal_project": """
- **项目**：源码追踪
- **技术栈**：AOSP 源码阅读
- **闭环目标**：画出 AMS.startActivity 到 ActivityThread.main 的完整 Binder 调用链
- **预估时间**：2-3 小时""",
    "interview_questions": """
- ❓ 点击桌面图标到 Activity 展示的完整流程？
- ❓ Zygote fork + COW（写时拷贝）机制如何加速应用启动？
- ❓ AMS 如何管理 Task 栈和进程优先级（oom_adj）？
- ❓ PMS 安装 APK 的完整流程？（解析→签名校验→dexopt→安装）""",
    "learning_sequence": """
1. 系统架构全景（5 层 + Zygote/SystemServer 启动流程）
2. AMS 详解（Activity 启动链路 + Task 栈 + oom_adj）
3. PMS 详解（APK 安装流程 + 权限管理 + 签名校验）
4. WMS 详解（窗口管理 + SurfaceFlinger + 输入法层级）
5. WatchDog（死锁监控 + ANR 触发流程）""",
    "practical_tasks": """
- 画出 Zygote → SystemServer → Launcher 启动流程图
- 追踪 AMS.startActivity 的 Binder 调用链
- 实验：用 dumpsys activity 查看 Task 栈状态
- 分析一个 ANR 的 traces.txt 输出""",
    "quick_start_apis": """
- `adb shell dumpsys activity`：查看 AMS 状态
- `adb shell dumpsys package`：查看 PMS 状态
- `adb shell dumpsys window`：查看 WMS 状态
- `adb shell cat /proc/<pid>/oom_adj`：查看进程优先级""",
    "templates_to_save": """
- Android 5 层系统架构图
- Activity 启动流程 Binder 调用序列图
- oom_adj 等级表
- APK 安装流程步骤图""",
    "analogy_mapping": """
- Zygote → 细胞分裂（fork 后共享 DNA，写时才复制）
- AMS → 机场塔台调度（管理所有航班起降）
- PMS → 海关检查（解析→验证→放行）
- Binder → 邮局系统（收发双方都不直接见面）""",
    "core_content": """
- Zygote fork + COW 机制
- Activity 启动完整 Binder 调用链
- oom_adj 与进程回收优先级
- APK 安装：PackageParser→scanPackageLI→dexopt
- SurfaceFlinger VSync 合成""",
    "edge_content": """
- Kernel Panic + last_kmsg 分析
- FdMonitor 文件描述符监控源码
- HAL 层硬件抽象接口""",
    "review_checklist": """
- [ ] 能画出 Android 5 层系统架构图
- [ ] 能画出 Activity 启动完整 Binder 序列图
- [ ] 能解释 Zygote 为什么能加速应用启动
- [ ] 能用 dumpsys 命令排查问题""",
    "progress_table": """
| 系统架构全景 | ⬜ 待学习 | — | — | — | |
| AMS 详解 | ⬜ 待学习 | — | — | — | |
| PMS 详解 | ⬜ 待学习 | — | — | — | |
| WMS 详解 | ⬜ 待学习 | — | — | — | |
| WatchDog | ⬜ 待学习 | — | — | — | |""",
}

# ========== 08-性能优化 ==========
MODULE_GUIDES["08-性能优化"] = {
    "module_title": "08 · 性能优化",
    "skeleton_desc": "启动速度 → UI 卡顿 → 内存泄漏 → 功耗 → 包体积 → 网络优化，全链路覆盖",
    "minimal_project": """
- **项目**：对现有项目做全链路性能诊断
- **工具**：Systrace/Perfetto + Memory Profiler + CPU Profiler
- **闭环目标**：找出 3 个优化点 → 量化效果 → 形成优化报告
- **预估时间**：一天""",
    "interview_questions": """
- ❓ 冷启动分为哪几个阶段？每个阶段有什么优化手段？
- ❓ Systrace 中如何判断掉帧？Frame 圆圈的颜色代表什么？
- ❓ 内存泄漏的 3 种定位方法及优劣对比？
- ❓ R8 的三阶段各做了什么？为什么比 ProGuard 更强？
- ❓ 网络请求的一次完整耗时拆解？""",
    "learning_sequence": """
1. 启动速度优化（冷启动 4 阶段 + StartUp 框架 + 懒加载）
2. UI 卡顿优化（16ms 渲染 + 过度绘制 + RecyclerView 优化）
3. 内存泄漏优化（GC Root + 5 大泄漏场景 + MAT + LeakCanary）
4. 功耗优化（Battery Historian + WakeLock + WorkManager 调度）
5. 包体积优化（AndResGuard + R8 + 动态下发 + WebP）
6. 网络优化（HTTP/2 + 连接池 + HTTPDNS + QUIC）""",
    "practical_tasks": """
- 对一个 App 用 Systrace/Perfetto 抓取启动 trace，分析瓶颈
- 用 LeakCanary 检出 3 个内存泄漏并修复
- 用 Android Studio APK Analyzer 分析包体积构成
- 对比 R8 开启前后的 APK 体积差异""",
    "quick_start_apis": """
- `adb shell am start -W <package>/<activity>`：测量启动时间
- `Systrace/Perfetto`：系统级追踪
- `LeakCanary 2`：自动内存泄漏检测
- `APK Analyzer`：包体积分析""",
    "templates_to_save": """
- 性能优化检查清单（启动/内存/卡顿/包体积）
- Systrace 常见问题速查表
- 内存泄漏 5 大场景 + 解决方案模板
- 网络优化方案对比表""",
    "analogy_mapping": """
- 启动优化 → 汽车起步（发动机预热→挂挡→松刹车→踩油门）
- 内存泄漏 → 水槽漏水（一直滴水，最终溢出）
- RecyclerView 优化 → 流水线复用（用过的工人不销毁，回头再用）
- R8 混淆 → 压缩文件（去空格→缩写→删注释）""",
    "core_content": """
- 冷启动 4 阶段与优化手段
- Systrace Frame 渲染分析（绿/黄/红圆圈）
- GC Root 可达性分析
- R8 Shrinking→Optimization→Obfuscation
- OkHttp 连接池复用机制""",
    "edge_content": """
- Systrace 自定义 Trace 埋点
- Battery Historian 复杂场景分析
- QUIC 协议细节
- Profile-Guided Optimization(PGO)""",
    "review_checklist": """
- [ ] 能独立完成一个 App 的启动优化（量化效果）
- [ ] 能用 Systrace/Perfetto 定位 UI 卡顿
- [ ] 能识别 5 种常见内存泄漏场景
- [ ] 能说出包体积优化的完整方案""",
    "progress_table": """
| 启动速度 | ⬜ 待学习 | — | — | — | |
| UI 卡顿 | ⬜ 待学习 | — | — | — | |
| 内存泄漏 | ⬜ 待学习 | — | — | — | |
| 功耗优化 | ⬜ 待学习 | — | — | — | |
| 包体积 | ⬜ 待学习 | — | — | — | |
| 网络优化 | ⬜ 待学习 | — | — | — | |""",
}

# ========== 模块 9-22 使用精简模板 ==========

def quick_guide(module_title, skeleton_desc, minimal_project, learning_sequence,
                interview_questions, practical_tasks, core_content, edge_content,
                review_checklist, progress_table):
    """生成精简学习指南"""
    return LEARNING_GUIDE_TEMPLATE.format(
        module_title=module_title,
        tree_skeleton="",
        p1_desc=PRINCIPLES["骨架先行"],
        skeleton_desc=skeleton_desc,
        p2_desc=PRINCIPLES["最小闭环"],
        minimal_project=minimal_project,
        p3_desc=PRINCIPLES["问题驱动"],
        interview_questions=interview_questions,
        p4_desc=PRINCIPLES["单点击穿"],
        learning_sequence=learning_sequence,
        p5_desc=PRINCIPLES["学以致用"],
        practical_tasks=practical_tasks,
        p6_desc=PRINCIPLES["先会后懂"],
        quick_start_apis="",
        p7_desc=PRINCIPLES["模板沉淀"],
        templates_to_save="",
        p8_desc=PRINCIPLES["新旧嫁接"],
        analogy_mapping="",
        p9_desc=PRINCIPLES["刻意屏蔽"],
        core_content=core_content,
        edge_content=edge_content,
        p10_desc=PRINCIPLES["闭环复盘"],
        review_checklist=review_checklist,
        progress_table=progress_table,
    )


# ========== 批量填充剩余模块 ==========

MODULE_GUIDES["09-稳定性与异常处理"] = quick_guide(
    "09 · 稳定性与异常处理",
    "ANR 分析 → 崩溃捕获 → System Restart 分析 → 异常监控体系",
    "- **项目**：搭建异常上报系统\n- **闭环目标**：UncaughtExceptionHandler → 持久化 → 上传 → 服务端聚合",
    "1. ANR 三类型超时机制 + traces.txt 解读\n2. Java/Native Crash 捕获原理\n3. System Restart 分析\n4. 线上异常监控架构设计",
    "- ANR traces.txt 中 'waiting to lock' vs 'native' 的含义？\n- Java crash vs Native crash 捕获机制差异？\n- OOM 如何预防和监控？\n- 线上异常监控架构如何设计？",
    "- 手动制造 ANR 并解读 traces.txt\n- 实现自定义 UncaughtExceptionHandler\n- 设计一个 crash 上报的链路追踪方案",
    "- ANR 三类型 + traces.txt 解读\n- Java/Native Crash 捕获机制\n- OOM 监控方案（Runtime.maxMemory + KOOM）\n- 全链路追踪 traceId",
    "- Kernel Panic + last_kmsg\n- Native Crash 信号处理细节\n- system_server 重启流程",
    "- [ ] 能解读 ANR traces.txt\n- [ ] 能区分 Java crash 和 Native crash\n- [ ] 能设计线上异常监控架构",
    "| ANR 分析 | ⬜ | — | — | — | |\n| 崩溃分析 | ⬜ | — | — | — | |\n| System Restart | ⬜ | — | — | — | |\n| 异常监控 | ⬜ | — | — | — | |",
)

MODULE_GUIDES["10-原生开发与NDK"] = quick_guide(
    "10 · 原生开发与NDK",
    "JNI 类型映射 → 静态/动态注册 → CMake 构建 → Native 调试",
    "- **项目**：JNI 图像灰度处理\n- **闭环目标**：Java 传 Bitmap → Native 灰度算法 → 返回 Bitmap 显示",
    "1. JNI 基础（类型映射 + 注册方式 + 引用管理）\n2. CMake 构建 + so 加载 + ABI 兼容\n3. C++ 最佳实践（智能指针 + JNI 线程模型）",
    "- 动态注册 vs 静态注册优劣？\n- 为什么要管理 JNI 引用（DeleteLocalRef）？\n- Native 层如何回调 Java 方法？\n- so 库瘦身策略？",
    "- 写一个 JNI 动态注册的 Demo\n- 用 CMake 编译一个 so 库并调用\n- Native 层调用 Java 静态方法和实例方法",
    "- JNI 类型映射表\n- 动态注册 vs 静态注册\n- CMake 构建配置\n- JNI 引用管理（Global/Local/Weak）",
    "- C++ STL 线程安全\n- Native Crash tombstone 分析\n- 交叉编译 toolchain 细节",
    "- [ ] 能手写 JNI 动态注册\n- [ ] 能用 CMake 构建 NDK 项目\n- [ ] 能排查 Native Crash",
    "| JNI 基础 | ⬜ | — | — | — | |\n| NDK 开发 | ⬜ | — | — | — | |\n| C++ 与安卓 | ⬜ | — | — | — | |",
)

MODULE_GUIDES["11-音视频开发"] = quick_guide(
    "11 · 音视频开发",
    "编解码基础 → 播放器架构 → 推流协议 → FFmpeg → ExoPlayer",
    "- **项目**：简易视频播放器\n- **闭环目标**：MediaCodec + SurfaceView → 播放本地 MP4 文件",
    "1. 编解码基础（H.264/AAC/MediaCodec）\n2. 播放器开发（解封装→解码→音画同步→渲染）\n3. 推流拉流（RTMP/HLS/WebRTC）\n4. FFmpeg 应用\n5. ExoPlayer 架构",
    "- MediaCodec 异步模式完整流程？\n- I/P/B 帧区别与 GOP 概念？\n- RTMP vs HLS vs WebRTC 适用场景？\n- 音画同步的 PTS/DTS 如何计算？",
    "- 用 MediaCodec 解码一个视频文件\n- 实现简易的 RTMP 推流 Demo\n- 用 FFmpeg 命令行转码一个视频",
    "- H.264 编码（I/P/B 帧 + NAL）\n- MediaCodec 异步模式\n- 音画同步（视频同步到音频时钟）\n- RTMP/HLS 协议对比",
    "- FFmpeg 滤镜链\n- DRM/Widevine\n- SEI 数据注入\n- WebRTC ICE/DTLS 细节",
    "- [ ] 能跑通 MediaCodec 硬解码\n- [ ] 能说出 RTMP vs HLS vs WebRTC 区别\n- [ ] 能画播放器架构图",
    "| 编解码 | ⬜ | — | — | — | |\n| 播放器开发 | ⬜ | — | — | — | |\n| 推流拉流 | ⬜ | — | — | — | |\n| FFmpeg | ⬜ | — | — | — | |\n| ExoPlayer | ⬜ | — | — | — | |",
)

MODULE_GUIDES["12-跨平台开发"] = quick_guide(
    "12 · 跨平台开发",
    "Flutter 三树渲染 → RN JS Bridge → CMP 共享 UI",
    "- **项目**：跨平台 Todo App（Flutter 版）\n- **闭环目标**：同一个 App 跑在 Android + iOS 上",
    "1. Flutter（Widget/Element/RenderObject 三树 + Engine + Platform Channel）\n2. React Native（JS Bridge + Fabric JSI + @ReactMethod）\n3. Compose Multiplatform（共享 UI + expect/actual）",
    "- Flutter 三棵树渲染流程？\n- Flutter vs RN vs CMP 选型依据？\n- Platform Channel 通信原理？",
    "- 用 Flutter 写一个跨平台页面\n- 用 RN 的 Fabric 新架构写一个原生模块\n- 对比 Flutter 和 RN 的热重载体验",
    "- Flutter Widget/Element/RenderObject 三树\n- RN JS Bridge vs Fabric JSI\n- CMP expect/actual 机制",
    "- Flutter Engine Skia/Impeller 细节\n- RN 旧架构 Bridge 瓶颈\n- CMP iOS 渲染差异",
    "- [ ] 能解释 Flutter 三棵树渲染流程\n- [ ] 能说出三框架选型判断标准",
    "| Flutter | ⬜ | — | — | — | |\n| React Native | ⬜ | — | — | — | |\n| CMP | ⬜ | — | — | — | |",
)

MODULE_GUIDES["13-构建与工程化"] = quick_guide(
    "13 · 构建与工程化",
    "Gradle 三阶段 → CI/CD 流水线 → 测试金字塔 → 代码规范",
    "- **项目**：为一个模块写三层测试\n- **闭环目标**：JUnit 单元测试 + Robolectric 集成测试 + Espresso UI 测试",
    "1. Gradle（Init→Config→Exec + Task DAG + 自定义插件）\n2. CI/CD（Jenkins/GitLab CI + AAB + 自动签名）\n3. 测试（JUnit/Mockito/Robolectric/Espresso）\n4. 代码规范（ktlint/detekt/Git Flow）",
    "- Gradle 构建三阶段各做了什么？\n- 如何写一个自定义 Gradle 插件？\n- 测试金字塔的层次划分？\n- CI/CD 流水线如何设计？",
    "- 写一个自定义 Gradle Task\n- 配置 GitLab CI 自动打包 AAB\n- 为一个 ViewModel 写完整的单元测试",
    "- Gradle Task DAG 执行流程\n- JUnit+Mockito+Robolectric 三层测试\n- ktlint/detekt 静态分析",
    "- Transform 字节码插桩（已废弃）\n- Gradle Build Cache 原理\n- Robolectric Shadow 机制",
    "- [ ] 能自定义 Gradle Task\n- [ ] 能设计 CI/CD 流水线\n- [ ] 能写完整的三层测试",
    "| Gradle | ⬜ | — | — | — | |\n| CI/CD | ⬜ | — | — | — | |\n| 测试 | ⬜ | — | — | — | |\n| 规范 | ⬜ | — | — | — | |",
)

MODULE_GUIDES["14-AI与安卓结合"] = quick_guide(
    "14 · AI与安卓结合",
    "AI 辅助开发（Copilot/CodeGeeX）→ 大模型端侧部署（TFLite/ONNX）→ AI 编程思维",
    "- **项目**：端侧图片分类 App\n- **闭环目标**：TFLite 加载量化模型 → CameraX 实时识别 → 显示结果",
    "1. AI 辅助开发工具（GitHub Copilot/CodeGeeX + Prompt Engineering）\n2. 大模型落地（量化压缩 + TFLite/ONNX 端侧推理 + GPU 加速）\n3. AI 编程思维（AI 辅助重构 + 异常日志分析 + APM 智能告警）",
    "- 端侧部署大模型的挑战和方案？\n- TFLite vs ONNX Runtime 选型？\n- 模型量化如何控制精度损失？\n- AI 辅助开发的实际提效案例？",
    "- 用 TFLite 部署一个量化模型到 App\n- 用 Copilot 生成一个功能的单元测试\n- 对比 FP32 vs INT8 模型的推理速度",
    "- 模型量化（FP32→INT8）\n- TFLite GPU Delegate 加速\n- Prompt Engineering 技巧",
    "- 模型蒸馏\n- ONNX Runtime 高级特性\n- MediaPipe 集成方案",
    "- [ ] 能在端侧跑一个量化模型\n- [ ] 能用 AI 工具提升开发效率\n- [ ] 能说出模型压缩的方法对比",
    "| AI 辅助开发 | ⬜ | — | — | — | |\n| 大模型落地 | ⬜ | — | — | — | |\n| AI 编程思维 | ⬜ | — | — | — | |",
)

MODULE_GUIDES["15-性能优化工具专题"] = quick_guide(
    "15 · 性能优化工具专题",
    "系统级追踪（Perfetto/Systrace）→ 内存分析（Memory Profiler/LeakCanary/MAT）→ CPU 分析 → APM 监控（Matrix/KOOM/Sentry）",
    "- **项目**：对一个 App 全链路诊断\n- **闭环目标**：Perfetto→Memory→CPU→Network 全流程分析，生成诊断报告",
    "1. 系统级追踪（Perfetto + Systrace）\n2. 内存分析（Memory Profiler + LeakCanary 2 + MAT）\n3. CPU/线程分析（CPU Profiler + Simpleperf）\n4. APM 线上监控（Matrix + KOOM + Sentry）",
    "- Perfetto vs Systrace 区别与选型？\n- LeakCanary 检测原理（WeakReference + GC + HeapDump）？\n- Matrix 卡顿监控原理（Choreographer + Looper）？\n- KOOM Fork 子进程 Dump 的优势？",
    "- 用 Perfetto 录制 30s trace 并 SQL 查询分析\n- 用 LeakCanary 检测一个真实泄漏\n- 用 Matrix 接入一个项目做线上监控",
    "- Perfetto SQL 查询 trace\n- LeakCanary ObjectWatcher→HeapDump→Shark\n- Matrix 卡顿监控 Choreographer+Looper\n- KOOM Fork + Suspend 原理",
    "- Simpleperf 高级用法\n- Sentry Session Replay\n- MAT OQL 高级查询",
    "- [ ] 能用 Perfetto 完成一次启动 trace 分析\n- [ ] 能说出 LeakCanary 完整检测流程\n- [ ] 能对比 Matrix vs KOOM 适用场景",
    "| 系统级追踪 | ⬜ | — | — | — | |\n| 内存分析 | ⬜ | — | — | — | |\n| CPU 分析 | ⬜ | — | — | — | |\n| APM 监控 | ⬜ | — | — | — | |\n| 其他专项 | ⬜ | — | — | — | |",
)

MODULE_GUIDES["16-物联网与通信"] = quick_guide(
    "16 · 物联网与通信",
    "BLE GATT 协议 → Wi-Fi 局域网通信 → Matter 智能家居协议",
    "- **项目**：BLE 心率监测 Demo\n- **闭环目标**：扫描→连接→读取心率 Service 数据→显示",
    "1. BLE（GATT + Service/Characteristic + 扫描/连接/读写/通知）\n2. Wi-Fi 通信（P2P + mDNS + Socket）\n3. Matter 协议（智能家居统一应用层）",
    "- BLE GATT 协议的结构？\n- BLE 与经典蓝牙的区别？\n- mDNS 服务发现原理？",
    "- 写一个 BLE 扫描 + 连接 + 读取数据的 Demo\n- 用 mDNS 实现局域网设备发现\n- 了解 Matter 设备配网流程（概念级别）",
    "- BLE GATT Service/Characteristic\n- BluetoothGatt 连接流程\n- mDNS 服务发现",
    "- Wi-Fi Aware(NAN) 邻近感知\n- Matter Thread/Wi-Fi 承载\n- BLE MTU 协商细节",
    "- [ ] 能跑通 BLE 连接读数据流程\n- [ ] 能说出 BLE 与经典蓝牙的区别",
    "| BLE 蓝牙 | ⬜ | — | — | — | |\n| Wi-Fi 通信 | ⬜ | — | — | — | |\n| Matter | ⬜ | — | — | — | |",
)

MODULE_GUIDES["17-出海应用与适配"] = quick_guide(
    "17 · 出海应用与适配",
    "隐私权限（Scoped Storage + GDPR）→ 厂商兼容（HMS/后台限制）→ 国际化（多语言/RTL）",
    "- **项目**：适配一个 App\n- **闭环目标**：Scoped Storage 文件访问 + 多语言资源 + RTL 布局",
    "1. 隐私权限（Android 10/11/13/14 版本演进 + GDPR/CCPA）\n2. 厂商兼容（华为 HMS + 小米/OPPO/Vivo 后台限制）\n3. 国际化（strings-xx + RTL + ICU 格式化 + AAB 按需分发）",
    "- Scoped Storage 对文件访问的影响和适配方案？\n- Android 11+ 分区存储强制执行如何应对？\n- GDPR 核心要求与客户端实现？",
    "- 将 App 的文件访问迁移到 Scoped Storage\n- 添加英文/阿拉伯文多语言支持\n- 测试 App 在华为/小米/OPPO 上的表现",
    "- Scoped Storage 分区存储\n- GDPR 用户同意 + 数据删除权\n- 多语言 strings-xx + RTL 镜像",
    "- 华为 HMS Push Kit\n- Wi-Fi Aware(NAN)\n- AAB 按需语言分发",
    "- [ ] 能适配 Scoped Storage\n- [ ] 能添加多语言 + RTL 布局\n- [ ] 能说出 GDPR 核心要求",
    "| 隐私权限 | ⬜ | — | — | — | |\n| 厂商兼容 | ⬜ | — | — | — | |\n| 国际化 | ⬜ | — | — | — | |",
)

MODULE_GUIDES["18-高频面试题汇总"] = quick_guide(
    "18 · 高频面试题汇总",
    "基础题 → 架构设计题 → 性能优化题 → 系统底层题，按难度递进",
    "- **项目**：每道架构题画一张架构图\n- **闭环目标**：用 STAR 方法回答每道架构设计题（场景→任务→行动→结果）",
    "1. 基础题（Handler/HashMap/Glide/Activity 启动模式）\n2. 架构设计题（图片加载框架/IM 消息/组件化路由/网络层）\n3. 性能优化题（启动优化/内存泄漏/RecyclerView 卡顿/包体积）\n4. 系统底层题（Activity 启动流程/Binder/Zygote/View 绘制）",
    "- 设计一个图片加载框架要考虑哪些方面？\n- App 启动优化的全链路方案？\n- 点击图标到 Activity 展示的完整流程？",
    "- 为每个架构题画一张系统架构图\n- 性能优化题准备数据支撑（优化前 xx → 优化后 yy）\n- 系统题准备 Binder 调用序列图",
    "- 基础题：Handler/Glide 源码级原理\n- 架构题：STAR 回答法 + Trade-off 分析\n- 系统题：源码调用链路追踪",
    "- 冷门 API 细节记忆\n- 每个框架的全部源码背诵",
    "- [ ] 每道架构题能画出架构图\n- [ ] 性能题有量化数据支撑\n- [ ] 系统题能画出完整调用链",
    "| 基础面试题 | ⬜ | — | — | — | |\n| 架构设计题 | ⬜ | — | — | — | |\n| 性能优化题 | ⬜ | — | — | — | |\n| 系统底层题 | ⬜ | — | — | — | |",
)

MODULE_GUIDES["19-开源框架专题"] = quick_guide(
    "19 · 开源框架专题",
    "Glide → OkHttp → Retrofit → ARouter → RxJava → EventBus → Tinker → MMKV → LeakCanary，三件套 + 高频框架",
    "- **项目**：阅读 Glide Engine.load() 源码\n- **闭环目标**：画出 Glide 图片加载完整流程图",
    "1. Glide（三级缓存 + Bitmap 复用 + 生命周期感知）\n2. OkHttp（五大拦截器链 + 连接池）\n3. Retrofit（动态代理 + 注解解析）\n4. ARouter（APT 路由表生成 + 拦截器）\n5. RxJava（操作符变换 + 线程调度 + 背压）\n6-9. EventBus/Tinker/MMKV/LeakCanary",
    "- Glide 三级缓存策略？Active Resources 的作用？\n- OkHttp 连接池复用机制？\n- Retrofit 如何通过动态代理生成接口实现？\n- ARouter 路由表是如何生成的？",
    "- 实现一个简化版 Glide（LRU 缓存 + 网络加载 + 显示）\n- 实现一个简化版 OkHttp（拦截器链）\n- 写一个 Retrofit 动态代理的 Demo",
    "- Glide Active/LRU/Disk 三级缓存\n- OkHttp 5 大拦截器链\n- Retrofit 动态代理 + ServiceMethod\n- ARouter APT 路由表生成",
    "- Glide 加载 Gif 细节\n- OkHttp HTTP/2 Stream 管理\n- RxJava lift() 源码",
    "- [ ] 能画出 Glide 加载流程\n- [ ] 能画出 OkHttp 拦截器链\n- [ ] 能解释 Retrofit 动态代理原理",
    "| Glide | ⬜ | — | — | — | |\n| OkHttp | ⬜ | — | — | — | |\n| Retrofit | ⬜ | — | — | — | |\n| ARouter | ⬜ | — | — | — | |\n| RxJava | ⬜ | — | — | — | |\n| EventBus | ⬜ | — | — | — | |\n| Tinker | ⬜ | — | — | — | |\n| MMKV | ⬜ | — | — | — | |\n| LeakCanary | ⬜ | — | — | — | |",
)

MODULE_GUIDES["20-并发编程与线程安全"] = quick_guide(
    "20 · 并发编程与线程安全",
    "Java 并发基础 → Android 线程模型 → Kotlin 协程并发 → 线程安全 → 锁机制",
    "- **项目**：图片批量下载\n- **闭环目标**：对比线程池 vs 协程两种并发实现，对比吞吐量和内存",
    "1. Java 并发（ThreadPoolExecutor 7参数 + CAS/Atomic + AQS）\n2. Android 线程模型（主线程 Looper + HandlerThread）\n3. Kotlin 协程并发（结构化并发 + Mutex/Channel）\n4. 线程安全（不可变对象 + ConcurrentHashMap + ThreadLocal）\n5. 锁机制（synchronized 锁升级 + ReentrantLock + 死锁排查）",
    "- synchronized vs ReentrantLock 区别？\n- ThreadPoolExecutor 核心参数如何计算？\n- ConcurrentHashMap 线程安全原理？\n- 协程取消为什么是协作式的？",
    "- 实现一个线程池下载 50 张图片\n- 用协程改写同样的功能并对比\n- 写一个死锁 Demo 并用 jstack 排查",
    "- synchronized 锁升级(偏向→轻量→重量)\n- ThreadPoolExecutor 调参\n- ConcurrentHashMap JDK7→8 演进\n- 协程结构化并发",
    "- AQS 源码分析\n- LockSupport park/unpark\n- Actor 协程模式",
    "- [ ] 能手写 ThreadPoolExecutor 配置\n- [ ] 能解释 synchronized 锁升级过程\n- [ ] 能排查死锁问题",
    "| Java 并发 | ⬜ | — | — | — | |\n| Android 线程 | ⬜ | — | — | — | |\n| 协程并发 | ⬜ | — | — | — | |\n| 线程安全 | ⬜ | — | — | — | |\n| 锁机制 | ⬜ | — | — | — | |",
)

MODULE_GUIDES["21-内存管理"] = quick_guide(
    "21 · 内存管理",
    "JVM 内存模型 → ART GC 演进 → 内存分配策略 → 内存监控 → Native 内存管理",
    "- **项目**：制造内存压力实验\n- **闭环目标**：分配大量对象 → 观察 GC 日志 → 触发 onTrimMemory → 实现降级策略",
    "1. JVM 内存模型（堆/栈/方法区 + 对象创建 + TLAB + 逃逸分析）\n2. ART GC（Dalvik→ART 演进 + Concurrent Copying GC + Baker Barrier）\n3. 内存分配策略（Bump Pointer + RosAlloc + RegionSpace）\n4. 内存监控（onTrimMemory + LMK oom_adj + 内存压力降级）\n5. Native 内存（jemalloc + mmap + ashmem + Native 泄漏检测）",
    "- ART GC 与 Dalvik GC 的核心差异？\n- Concurrent Copying GC 如何做到 ~1ms 停顿？\n- onTrimMemory 触发时机与降级策略？\n- LMK oom_adj 等级与进程回收顺序？",
    "- 实验：制造不同级别的 onTrimMemory 回调\n- 用 adb shell dumpsys meminfo 分析内存\n- 实现一个带降级策略的图片缓存（根据内存压力调整质量）",
    "- ART Concurrent Copying GC + Baker Read Barrier\n- onTrimMemory 6 个等级\n- LMK oom_adj 回收优先级\n- jemalloc arena/bin/run + tcache",
    "- Dalvik GC 详细算法\n- RegionSpace 空间管理细节\n- malloc_debug Native 泄漏检测",
    "- [ ] 能解释 ART GC 低停顿原理\n- [ ] 能实现 onTrimMemory 降级策略\n- [ ] 能说出 LMK 进程回收顺序",
    "| JVM 内存 | ⬜ | — | — | — | |\n| ART GC | ⬜ | — | — | — | |\n| 内存分配 | ⬜ | — | — | — | |\n| 内存监控 | ⬜ | — | — | — | |\n| Native 内存 | ⬜ | — | — | — | |",
)

MODULE_GUIDES["22-高性能编程"] = quick_guide(
    "22 · 高性能编程",
    "对象池化 → 零拷贝 → 序列化优化 → IO 优化 → 编译优化",
    "- **项目**：JSON vs ProtoBuf 序列化对比\n- **闭环目标**：同样的数据结构 → JSON(Parser) vs ProtoBuf 序列化耗时对比 → 量化报告",
    "1. 对象复用（Message 池 + RecyclerView 缓存 + Glide BitmapPool）\n2. 零拷贝（Binder mmap + sendfile + ashmem + DirectByteBuffer）\n3. 序列化优化（Parcelable vs Serializable + ProtoBuf vs JSON）\n4. IO 优化（NIO vs BIO + mmap + WAL + DiskLruCache）\n5. 编译优化（R8 三阶段 + Baseline Profile + PGO）",
    "- Message 池化原理（享元模式）？\n- Binder 一次拷贝与 Linux sendfile 对比？\n- ProtoBuf 比 JSON 快多少？为什么？\n- Baseline Profile 原理和效果？\n- RecyclerView 四级缓存触发条件？",
    "- 对比 Parcelable vs Serializable 序列化耗时\n- 用 Message.obtain() 替代 new Message() 并统计效果\n- 配置 Baseline Profile 并测量启动速度提升",
    "- Message 池化(sPool 链表 + 享元模式)\n- RecyclerView 四级缓存\n- ProtoBuf Varint + ZigZag 编码\n- R8 Shrinking→Optimization→Obfuscation",
    "- FlatBuffers vs ProtoBuf\n- PGO 运行时收集机制\n- jemalloc tcache 细节",
    "- [ ] 能解释 Message 池化原理\n- [ ] 能说出 RecyclerView 四级缓存触发条件\n- [ ] 能对比序列化方案优劣",
    "| 对象池化 | ⬜ | — | — | — | |\n| 零拷贝 | ⬜ | — | — | — | |\n| 序列化 | ⬜ | — | — | — | |\n| IO 优化 | ⬜ | — | — | — | |\n| 编译优化 | ⬜ | — | — | — | |",
)


# ====== 主入口 ======
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python generate_learning_guide.py <模块编号>")
        print("示例: python generate_learning_guide.py 01")
        print("      python generate_learning_guide.py all")
        sys.exit(0)

    target = sys.argv[1]

    def write_guide(module_id):
        guide = MODULE_GUIDES[module_id]
        # 生成树形骨架
        from generate_xmind import MODULES as XMIND_MODULES
        tree_lines = ""
        if module_id in XMIND_MODULES:
            tree = build_tree(XMIND_MODULES[module_id]["skeleton"])
            tree_lines = "\n".join(tree)

        if isinstance(guide, str):
            # quick_guide 已预格式化
            content = guide
        else:
            guide["tree_skeleton"] = tree_lines
            content = LEARNING_GUIDE_TEMPLATE.format(**guide)

        dir_path = os.path.join(PROJECT_ROOT, module_id)
        os.makedirs(dir_path, exist_ok=True)
        file_path = os.path.join(dir_path, "学习指南.md")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ 生成学习指南: {file_path} ({len(content)} 字)")

    if target == "all":
        for mid in MODULE_GUIDES:
            write_guide(mid)
        print(f"\n✅ 全部 {len(MODULE_GUIDES)} 个模块的学习指南已生成！")
    elif target in MODULE_GUIDES:
        write_guide(target)
    else:
        print(f"❌ 未知模块: {target}")
        sys.exit(1)
