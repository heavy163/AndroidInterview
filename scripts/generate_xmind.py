#!/usr/bin/env python3
"""
XMind (Zen) 文件生成器
从 JSON 知识骨架规格生成 .xmind 文件，可在 XMind 8/Zen 中直接打开
"""
import json
import zipfile
import uuid
import os
import sys
from datetime import datetime


def gen_id():
    return uuid.uuid4().hex[:26]


def build_topic(title, children_specs=None, notes=None):
    """构建一个 topic 节点"""
    topic = {
        "id": gen_id(),
        "class": "topic",
        "title": title
    }
    if notes:
        topic["notes"] = {"plain": {"content": notes}}
    if children_specs:
        attached = []
        for child in children_specs:
            if isinstance(child, str):
                attached.append(build_topic(child))
            elif isinstance(child, dict):
                t = build_topic(
                    child["title"],
                    child.get("children"),
                    child.get("notes")
                )
                attached.append(t)
            elif isinstance(child, (list, tuple)):
                # [title, children_list]
                t = build_topic(child[0], child[1])
                attached.append(t)
        topic["children"] = {"attached": attached}
    return topic


def build_xmind_content(sheet_title, root_title, structure):
    """
    构建完整的 content.json
    structure: 树形结构 [title, [children...]]
    """
    root_topic = build_topic(root_title, structure)
    sheet = {
        "id": gen_id(),
        "class": "sheet",
        "title": sheet_title,
        "rootTopic": root_topic
    }
    return [sheet]


def create_xmind(filepath, sheet_title, root_title, structure):
    """生成 .xmind 文件"""
    content = build_xmind_content(sheet_title, root_title, structure)
    metadata = {
        "creator": {"name": "AndroidInterviewPrep", "version": "1.0"},
        "created": int(datetime.now().timestamp() * 1000)
    }
    manifest = {"file-entries": {
        "content.json": {},
        "metadata.json": {}
    }}

    os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else ".", exist_ok=True)

    with zipfile.ZipFile(filepath, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("content.json", json.dumps(content, ensure_ascii=False, indent=2))
        zf.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    print(f"✅ 生成 XMind: {filepath}")


# ─── 22个模块的知识骨架定义 ───

MODULES = {}

def register(module_id, title, skeleton):
    MODULES[module_id] = {"title": title, "skeleton": skeleton}


# ========== 01 - 安卓语言基础 ==========
register("01-安卓语言基础", "安卓语言基础 (Java/Kotlin/协程/KMM)", [
    ["🐍 核心心法", [
        "先跑通：Kotlin 写一个完整页面（MVVM+协程）",
        "骨架先行：语言特性→协程并发→KMM 共享",
        "新旧嫁接：Java 老手 → Kotlin 新特性对照表",
        "模板沉淀：协程写法模板 / sealed class 状态机模板"
    ]],
    ["📚 学习路径 (4阶段)", [
        ["阶段1: Kotlin 核心特性", [
            "扩展函数 — 不侵入类，增加功能",
            "高阶函数与 lambda — inline/noinline/crossinline",
            "委托属性 — lazy / observable / vetoable",
            "密封类 sealed class — 受限类层次",
            "数据类 data class — equals/hashCode/copy"
        ]],
        ["阶段2: Kotlin 协程", [
            "挂起函数 suspend — 非阻塞异步",
            "调度器 Dispatchers — Main/IO/Default/Unconfined",
            "Flow 冷流 — 背压、操作符(map/flatMapLatest)",
            "StateFlow/SharedFlow — 热流与状态管理",
            "结构化并发 — coroutineScope/supervisorScope",
            "Channel — 协程间通信"
        ]],
        ["阶段3: Java 进阶", [
            "JVM 内存模型 — 堆/栈/方法区/程序计数器",
            "GC 机制 — 可达性分析/GC Roots/四种引用",
            "注解处理器 APT — 编译时代码生成",
            "volatile & synchronized — 可见性/原子性/有序性"
        ]],
        ["阶段4: KMM 跨平台", [
            "expect/actual 机制 — 平台抽象",
            "共享业务逻辑层 — 网络/数据库/领域模型",
            "与 Compose Multiplatform 关系"
        ]]
    ]],
    ["🎯 面试重点", [
        "suspend 函数底层实现 (CPS 转换 + 状态机)",
        "Flow vs LiveData vs StateFlow 选用场景",
        "协程取消的协作机制 (isActive / ensureActive)",
        "Kotlin inline 函数为何减少 lambda 对象创建",
        "HashMap 扩容与红黑树转换 (Java 基础)"
    ]],
    ["⚡ 最小闭环项目", [
        "项目: 天气预报 App",
        "Kotlin + MVVM + 协程 + Flow + Retrofit",
        "跑通：搜索城市 → 网络请求 → UI 更新"
    ]],
    ["🔧 避坑指南", [
        "协程泄漏: viewModelScope 释放时机",
        "Flow 重复订阅: shareIn(WhileSubscribed)",
        "StateFlow 粘性: 用 Channel 转 Flow 替代",
        "GlobalScope 禁止在业务代码中使用"
    ]]
])


# ========== 02 - 安卓核心机制 ==========
register("02-安卓核心机制", "安卓核心机制 (四大组件/生命周期/Binder/Handler)", [
    ["🐍 核心心法", [
        "先搞懂四大组件生命周期线，再深入 Binder/Handler 底层",
        "问题驱动：从「Activity 启动流程」反推 AMS/WMS",
        "模块化单点：一次只啃一个组件，学完即用",
        "模板沉淀：组件通信方式速查表 / Handler 消息机制图解"
    ]],
    ["📚 学习路径 (5阶段)", [
        ["阶段1: 四大组件全景", [
            "Activity — 4种启动模式 + TaskAffinity",
            "Service — start/bind/foreground 三种形态",
            "BroadcastReceiver — 静态/动态注册 + 有序广播",
            "ContentProvider — 跨进程数据共享 + Cursor"
        ]],
        ["阶段2: 生命周期管理", [
            "Activity 生命周期 — onCreate→onStart→onResume→onPause...",
            "Fragment 生命周期 — 与 Activity 绑定关系",
            "异常恢复 — onSaveInstanceState/onRestoreInstanceState",
            "ViewModel 存活原理 — 横竖屏切换不销毁"
        ]],
        ["阶段3: 组件间通信", [
            "Intent/Bundle — 基础通信",
            "接口回调 + EventBus — 模块内通信",
            "LiveEventBus — 生命周期感知的事件总线",
            "ContentProvider — 跨进程数据共享"
        ]],
        ["阶段4: Binder 机制 (面试核心区分点)", [
            "Binder 驱动层 — mmap 一次拷贝原理",
            "AIDL 生成类分析 — Stub/Proxy 模式",
            "匿名共享内存 ashmem — 大数据跨进程传输",
            "Binder 线程池 — 16 个线程上限"
        ]],
        ["阶段5: Handler 消息机制", [
            "MessageQueue — 单向链表 + epoll 唤醒",
            "Looper — ThreadLocal + loop() 死循环",
            "同步屏障 sync barrier — 优先处理异步消息",
            "IdleHandler — 空闲时执行低优先级任务"
        ]]
    ]],
    ["🎯 面试重点", [
        "点击桌面图标到 Activity 展示的完整流程",
        "Binder 为什么只拷贝一次 (mmap 原理)",
        "Handler 消息延迟原因分析",
        "Activity 启动模式与 onNewIntent 关系",
        "Service 与 Thread 区别"
    ]],
    ["⚡ 最小闭环项目", [
        "项目: IPC 进程间通信 Demo",
        "AIDL 定义接口 → Service 实现 → 客户端调用",
        "跑通：跨进程传输复杂对象"
    ]],
    ["🔧 避坑指南", [
        "Fragment 重叠: 保存/恢复时重复 add",
        "静态广播接收器 Android 8+ 限制",
        "Handler 内存泄漏: 匿名内部类持有 Activity 引用",
        "Binder 传输 1MB 限制及 ashmem 替代方案"
    ]]
])


# ========== 03 - 数据结构与算法 ==========
register("03-数据结构与算法", "数据结构与算法", [
    ["🐍 核心心法", [
        "先背 10 大常用数据结构的 API 和复杂度（骨架）",
        "最小闭环：手写快排/二分/链表反转，反复刷",
        "问题驱动：LeetCode Hot 100 按标签刷",
        "安卓嫁接：SparseArray/ArrayMap 就是算法落地的例子"
    ]],
    ["📚 学习路径 (4阶段)", [
        ["阶段1: 数据结构基础", [
            "数组 ArrayList — 扩容机制(1.5倍)",
            "链表 LinkedList — 双向链表",
            "栈/队列 ArrayDeque — 双端队列",
            "HashMap — 数组+链表+红黑树，扩容(2倍)",
            "SparseArray/ArrayMap — 安卓优化的 key-value 结构"
        ]],
        ["阶段2: 排序算法", [
            "快速排序 — 分治 + pivot，O(nlogn)",
            "归并排序 — 稳定排序，外部排序基础",
            "堆排序 — 优先队列底层",
            "手写实现 + 复杂度推导"
        ]],
        ["阶段3: 查找与遍历", [
            "二分查找 — 边界处理（开闭区间）",
            "BFS — 队列实现层序遍历",
            "DFS — 递归/栈实现，回溯框架",
            "布隆过滤器 — 空间高效判重"
        ]],
        ["阶段4: 动态规划", [
            "0-1 背包问题",
            "最长公共子序列 LCS",
            "最长递增子序列 LIS",
            "状态转移方程推导"
        ]]
    ]],
    ["🎯 面试重点", [
        "HashMap put/get 源码流程 (hash→index→链表→红黑树)",
        "SparseArray 二分查找插入",
        "快排三路分区优化",
        "LRU Cache 实现 (LinkedHashMap)"
    ]],
    ["⚡ 最小闭环项目", [
        "刷题路径: 数组→链表→二叉树→DP (各5题)",
        "每个数据结构写一个安卓场景的 Demo"
    ]],
    ["🔧 避坑指南", [
        "HashMap 多线程扩容死循环 (JDK7)",
        "二分查找边界 off-by-one",
        "递归爆栈 → 用迭代+栈替代"
    ]]
])


# ========== 04 - UI与View体系 ==========
register("04-UI与View体系", "UI与View体系 (View绘制/事件分发/自定义View/动画)", [
    ["🐍 核心心法", [
        "先画一张 View 树全景图 → Measure→Layout→Draw",
        "事件分发：背下三方法调用链，画流程图",
        "自定义 View：先抄一个圆角 ImageView，再改",
        "动画：属性动画优先，补间动画辅助"
    ]],
    ["📚 学习路径 (4阶段)", [
        ["阶段1: View 绘制流程", [
            "Measure — MeasureSpec(EXACTLY/AT_MOST/UNSPECIFIED)",
            "Layout — 确定子 View 位置 (l,t,r,b)",
            "Draw — Canvas 绘制 (背景→自身→子View→装饰)",
            "ViewRootImpl — 连接 WindowManager 和 DecorView",
            "requestLayout vs invalidate vs postInvalidate"
        ]],
        ["阶段2: 事件分发机制", [
            "三方法: dispatchTouchEvent→onInterceptTouchEvent→onTouchEvent",
            "ACTION_DOWN/MOVE/UP/CANCEL 流程",
            "滑动冲突解决: 外部拦截法 / 内部拦截法",
            "ViewGroup 事件分发源码走读"
        ]],
        ["阶段3: 自定义 View", [
            "onMeasure — 处理 wrap_content",
            "onDraw — Canvas/Paint/Path/Matrix",
            "贝塞尔曲线 — 二阶/三阶曲线",
            "自定义属性 — declare-styleable + TypedArray"
        ]],
        ["阶段4: 动画系统", [
            "补间动画 — 只改视觉效果，不改变属性",
            "帧动画 — AnimationDrawable，OOM 风险",
            "属性动画 — ValueAnimator/ObjectAnimator",
            "TimeInterpolator — 插值器",
            "过渡动画 — Transition/SharedElement"
        ]]
    ]],
    ["🎯 面试重点", [
        "MeasureSpec 如何确定 (父View限制+子View LayoutParams)",
        "事件分发完整流程图",
        "滑动冲突解决方案",
        "requestLayout 和 invalidate 触发链路区别"
    ]],
    ["⚡ 最小闭环项目", [
        "项目: 自定义圆形进度条",
        "Measure→Draw→属性动画 全流程"
    ]],
    ["🔧 避坑指南", [
        "自定义 View wrap_content 不处理 = match_parent",
        "onMeasure 多次调用 — 用标志位优化",
        "属性动画内存泄漏 — onDetachedFromWindow 取消",
        "View.post() 获取宽高 — Activity 未 attach 时失效"
    ]]
])


# ========== 05 - Jetpack组件体系 ==========
register("05-Jetpack组件体系", "Jetpack组件体系 (ViewModel/Room/Navigation/Hilt/Compose)", [
    ["🐍 核心心法", [
        "先跑通一个 Compose + MVVM 的完整页面（闭环）",
        "ViewModel/LiveData → 状态管理基石，先掌握",
        "Room → 声明式数据库，背下三剑客注解",
        "Hilt → DI 减少样板代码，理解 Scope 层级",
        "Compose → 声明式 UI 是未来，先学再用 View"
    ]],
    ["📚 学习路径 (6阶段)", [
        ["阶段1: ViewModel + LiveData", [
            "ViewModel — 生命周期感知 + SavedStateHandle",
            "LiveData — 粘性事件 + observe/livedata-ktx",
            "MediatorLiveData — 多源合并",
            "StateFlow vs LiveData — 选用策略"
        ]],
        ["阶段2: Room 数据库", [
            "@Entity/@DAO/@Database 三剑客",
            "Migration — 手动迁移 + 自动迁移(2.4+)",
            "TypeConverter — 复杂类型转换",
            "Flow 响应式查询 — 数据变更自动通知"
        ]],
        ["阶段3: Navigation", [
            "NavGraph — 声明式导航图",
            "SafeArgs — 类型安全传参",
            "DeepLink — URI/PendingIntent 跳转",
            "多返回栈 — Android 12+ support"
        ]],
        ["阶段4: Hilt 依赖注入", [
            "@HiltAndroidApp → @AndroidEntryPoint → @Inject",
            "Scope 层级: Singleton > ViewModel > Fragment",
            "与 Dagger 对比 — 模板代码减少 80%",
            "自定义 Scope + @Binds/@Provides"
        ]],
        ["阶段5: Compose 声明式 UI", [
            "重组 Recomposition — 核心机制",
            "remember/mutableStateOf — 状态管理",
            "Modifier 链 — 样式/行为/布局",
            "副作用: LaunchedEffect/DisposableEffect/SideEffect"
        ]],
        ["阶段6: 其他组件", [
            "WorkManager — 约束条件调度",
            "DataStore — Proto/Preferences 替换 SP",
            "Paging 3 — 分页加载"
        ]]
    ]],
    ["🎯 面试重点", [
        "ViewModel 如何在横竖屏切换时存活",
        "Compose 重组 vs View invalidate 区别",
        "Hilt 与 Dagger 核心区别",
        "Room Flow 查询如何感知数据变更"
    ]],
    ["⚡ 最小闭环项目", [
        "项目: 记事本 App (Compose + Room + Hilt + MVVM)",
        "增删改查 + Flow 响应式列表"
    ]],
    ["🔧 避坑指南", [
        "LiveData setValue/postValue 线程限制",
        "Room 主线程查询 StrictMode 检测",
        "Compose 状态提升 — 避免状态下沉",
        "Hilt Fragment 必须用 @AndroidEntryPoint"
    ]]
])


# ========== 06 - 应用架构设计 ==========
register("06-应用架构设计", "应用架构设计 (MVVM/MVI/Clean/组件化/插件化)", [
    ["🐍 核心心法", [
        "先理解 MVVM（最通用），再扩展 MVI/Clean",
        "组件化 = 代码隔离 + 模块通信 + 壳工程",
        "最小闭环：搭一个 3 模块的组件化项目",
        "架构没有银弹，掌握选型决策能力"
    ]],
    ["📚 学习路径 (5阶段)", [
        ["阶段1: MVVM 架构", [
            "数据驱动 UI — View 观察 ViewModel",
            "Databinding/ViewBinding — 双向绑定",
            "Repository 模式 — 数据层抽象",
            "ViewModel + LiveData/StateFlow 桥接"
        ]],
        ["阶段2: MVI 架构", [
            "单向数据流 UDF — State→View→Intent→Reducer",
            "State 不可变 — 快照 + diff 更新",
            "与 MVVM 对比 — 适用场景分析"
        ]],
        ["阶段3: Clean Architecture", [
            "Domain/Data/Presentation 三层分离",
            "UseCase 层 — 单一职责的业务逻辑",
            "依赖倒置 DIP — 高层不依赖低层",
            "SOLID 原则落地"
        ]],
        ["阶段4: 组件化与模块化", [
            "ARouter 路由 — 模块间页面跳转",
            "接口下沉 + SPI — 模块间服务调用",
            "Gradle composite build — 模块依赖管理",
            "壳工程 — 组装所有模块"
        ]],
        ["阶段5: 插件化技术", [
            "Tinker 热修复 — DexDiff + 资源补丁",
            "Shadow — ClassLoader Hook",
            "插件化 vs 组件化 — 线上动态化 vs 编译期隔离"
        ]]
    ]],
    ["🎯 面试重点", [
        "MVVM vs MVI 核心区别与选用场景",
        "组件化模块间通信方案对比",
        "ARouter 路由表生成原理 (APT)",
        "Clean Architecture 分层职责与依赖方向"
    ]],
    ["⚡ 最小闭环项目", [
        "项目: 三模块组件化 Demo",
        "app(壳) + home + profile，ARouter 跳转"
    ]],
    ["🔧 避坑指南", [
        "组件化循环依赖 — 接口下沉到 base 层",
        "ViewModel 持有 Context — 用 AndroidViewModel",
        "MVI 状态膨胀 — 拆分 SubState + combine",
        "插件化兼容性 — Android 版本 + 厂商 ROM"
    ]]
])


# ========== 07 - 安卓系统与Framework ==========
register("07-安卓系统与Framework", "安卓系统与Framework (AMS/PMS/WMS/WatchDog)", [
    ["🐍 核心心法", [
        "先画 Android 系统架构 5 层全景图（骨架）",
        "AMS 是核心：从 Activity 启动流程切入",
        "PMS/WMS/WatchDog：按职责边界理解",
        "源码走读：只看核心链路，不陷入细节"
    ]],
    ["📚 学习路径 (5阶段)", [
        ["阶段1: 系统架构全景", [
            "5 层架构: App→Framework→Native→HAL→Kernel",
            "Zygote 启动流程 — fork + COW",
            "SystemServer — 启动所有系统服务",
            "init.rc → Zygote → SystemServer → Launcher"
        ]],
        ["阶段2: AMS 详解", [
            "Activity 启动流程 — Launcher→AMS→Zygote→ActivityThread",
            "Task 栈管理 — standard/singleTop/singleTask/singleInstance",
            "进程优先级 — oom_adj FOREGROUND→VISIBLE→SERVICE→CACHED"
        ]],
        ["阶段3: PMS 详解", [
            "APK 安装流程 — PackageParser → scanPackageLI",
            "权限管理 — 运行时权限 vs 安装时权限",
            "签名校验 — V1 JAR/V2 APK/V3 密钥轮转"
        ]],
        ["阶段4: WMS 详解", [
            "窗口管理 — WindowToken/WindowState",
            "SurfaceFlinger — 图层合成 + VSync",
            "输入法窗口层级 — Dialog/Toast/IME"
        ]],
        ["阶段5: WatchDog", [
            "系统死锁监控 — MonitorChecker",
            "ANR 触发流程 — Input/Service/Broadcast 超时",
            "FdMonitor — 文件描述符监控"
        ]]
    ]],
    ["🎯 面试重点", [
        "Activity 启动完整流程（Binder 调用链）",
        "Zygote fork + COW 机制",
        "oom_adj 与进程保活",
        "Window 添加流程 (WMS.addView)"
    ]],
    ["⚡ 最小闭环项目", [
        "读源码: AMS.startActivity → ActivityThread.main",
        "画出完整 Binder 调用序列图"
    ]],
    ["🔧 避坑指南", [
        "源码版本差异 — 基于 Android 12+ 阅读",
        "不要试图读完整个 AMS — 按问题驱动读"
    ]]
])


# ========== 08 - 性能优化 ==========
register("08-性能优化", "性能优化 (启动/卡顿/内存/功耗/包体积/网络)", [
    ["🐍 核心心法", [
        "先有量化指标，后优化（数据驱动，不能盲猜）",
        "启动优化最容易出成绩，优先攻克",
        "内存/卡顿用 Systrace/Perfetto 解决 80% 问题",
        "包体积 → 瘦身三板斧: 混淆/压缩/动态下发"
    ]],
    ["📚 学习路径 (6阶段)", [
        ["阶段1: 启动速度优化", [
            "冷启动 4 阶段: fork→bindApp→Activity.onCreate→首帧",
            "启动框架: App Startup / 异步初始化 DAG",
            "懒加载: ViewStub/Stub 占位",
            "Theme 优化: windowBackground 秒开白屏",
            "量化: adb shell am start -W 测量"
        ]],
        ["阶段2: UI 卡顿优化", [
            "16ms 渲染帧率 — VSync 信号驱动",
            "过度绘制检测 — GPU 呈现模式分析",
            "布局优化: merge/ViewStub/ConstraintLayout",
            "RecyclerView 优化: setHasFixedSize/ViewPool/DiffUtil"
        ]],
        ["阶段3: 内存泄漏优化", [
            "GC Root 可达性分析",
            "5 大泄漏场景: Handler/匿名内部类/静态变量/单例/资源",
            "MAT 支配树 — 找 Retained Heap 最大对象",
            "LeakCanary 2 自动化检测"
        ]],
        ["阶段4: 功耗优化", [
            "Battery Historian v2 — 电量分析",
            "WakeLock — 避免持锁不释放",
            "JobScheduler/WorkManager — 统一调度",
            "Doze/App Standby — 系统省电模式适配"
        ]],
        ["阶段5: 包体积优化", [
            "AndResGuard — 资源混淆（微信方案）",
            "ProGuard/R8 — 代码混淆三阶段",
            "动态下发 — 动态 so/资源按需下载",
            "WebP/SVG — 替换 PNG 图片资源"
        ]],
        ["阶段6: 网络优化", [
            "HTTP/2 — 多路复用 + 头部压缩",
            "连接池 — OkHttp ConnectionPool(5,5)",
            "HTTPDNS — 域名解析防劫持",
            "弱网优化 — QUIC / 预加载"
        ]]
    ]],
    ["🎯 面试重点", [
        "冷启动完整阶段及每阶段优化手段",
        "Systrace 中掉帧判断（Frame 圆圈颜色）",
        "内存泄漏的 3 种定位方法及对比",
        "R8 三阶段做了什么",
        "网络请求耗时拆解 (DNS→TCP→TLS→Request→Response)"
    ]],
    ["⚡ 最小闭环项目", [
        "拿一个真实项目 → Systrace 抓取 → 找出 3 个优化点",
        "量化优化效果 → 形成优化报告"
    ]],
    ["🔧 避坑指南", [
        "不要过早优化 — 先 profiling 再优化",
        "启动优化误区: 全部异步 → 依赖错乱",
        "LeakCanary 线上不要开（性能开销大）",
        "WebP 兼容性 — Android 4.0+ 原生支持"
    ]]
])


# ========== 09 - 稳定性与异常处理 ==========
register("09-稳定性与异常处理", "稳定性与异常处理 (ANR/崩溃/SystemRestart/监控)", [
    ["🐍 核心心法", [
        "Crash 率 < 0.1% 是硬指标，ANR 率 < 0.05%",
        "先建立监控（发现率），再做修复（解决率）",
        "ANR → traces.txt 解读是关键技能",
        "崩溃 → 堆栈符号化 → 归因 → 闭环"
    ]],
    ["📚 学习路径 (4阶段)", [
        ["阶段1: ANR 分析与解决", [
            "三种 ANR: Input(5s)/Service(20s/10s)/Broadcast(10s/60s)",
            "traces.txt 解读 — 找主线程状态 (native/java/waiting)",
            "常见原因: 主线程 IO、死锁、Binder 阻塞",
            "ANR-WatchDog — 开源的 ANR 监控方案"
        ]],
        ["阶段2: 崩溃分析", [
            "Java Crash — UncaughtExceptionHandler 拦截",
            "Native Crash — 信号处理器 + tombstone",
            "OOM — Runtime.maxMemory 监控 + 内存泄漏链路",
            "Crash 堆栈符号化 — ndk-stack / addr2line"
        ]],
        ["阶段3: System Restart", [
            "system_server 重启 — WatchDog 触发",
            "Kernel Panic — last_kmsg 分析",
            "重启信息收集 — 开机后读取 /sys/fs/pstore"
        ]],
        ["阶段4: 异常监控体系", [
            "自定义 UncaughtExceptionHandler 链",
            "全链路追踪 traceId — 从客户端到服务端",
            "OOM 监控 — 定时采集 Runtime 内存 + 阈值告警",
            "ANR 监控 — FileObserver 监听 /data/anr/"
        ]]
    ]],
    ["🎯 面试重点", [
        "ANR traces.txt 中主线程 'waiting to lock' vs 'native' 的区别",
        "Java crash vs Native crash 捕获机制差异",
        "OOM 预防：大图加载 + LRU 缓存 + 降采样",
        "线上异常监控架构设计"
    ]],
    ["⚡ 最小闭环项目", [
        "搭建一个简单的异常上报系统",
        "UncaughtExceptionHandler → 持久化 → 上传"
    ]],
    ["🔧 避坑指南", [
        "UncaughtExceptionHandler 链 — 保留系统默认处理",
        "Native Crash 信号处理不能做复杂操作",
        "OOM 监控 — fork 子进程 dump hprof (KOOM 方案)"
    ]]
])


# ========== 10 - 原生开发与NDK ==========
register("10-原生开发与NDK", "原生开发与NDK (JNI/NDK/C++)", [
    ["🐍 核心心法", [
        "JNI 三步：声明 native → 生成头文件 → 实现 C/C++",
        "动态注册 > 静态注册（加载更快）",
        "NDK 应用场景: 音视频编解码/加解密/图形处理/AI推理"
    ]],
    ["📚 学习路径 (3阶段)", [
        ["阶段1: JNI 基础", [
            "类型映射 — jstring↔String, jint↔int",
            "静态注册 — Java_包名_类名_方法名",
            "动态注册 — JNI_OnLoad + RegisterNatives",
            "全局引用 vs 局部引用 vs 弱全局引用"
        ]],
        ["阶段2: NDK 开发", [
            "CMake 构建脚本 — add_library/target_link_libraries",
            "so 库加载 — System.loadLibrary + ABI 兼容",
            "ndk-stack — Native 堆栈符号化"
        ]],
        ["阶段3: C++ 与安卓", [
            "智能指针 — shared_ptr/unique_ptr/weak_ptr",
            "JNI 线程模型 — JavaVM + AttachCurrentThread",
            "跨语言异常处理 — JNIEnv.ExceptionCheck()"
        ]]
    ]],
    ["🎯 面试重点", [
        "动态注册 vs 静态注册优劣对比",
        "JNI 引用管理（为何 DeleteLocalRef）",
        "Native 层如何回调 Java 方法"
    ]],
    ["⚡ 最小闭环项目", [
        "项目: JNI 图像处理 Demo",
        "Java 传 Bitmap → Native 灰度处理 → 返回"
    ]],
    ["🔧 避坑指南", [
        "JNI 函数签名写错 → MethodNotFoundException",
        "局部引用溢出 — 循环中手动 DeleteLocalRef",
        "Native 线程使用 JNI — 必须先 AttachCurrentThread"
    ]]
])


# ========== 11 - 音视频开发 ==========
register("11-音视频开发", "音视频开发 (编解码/播放器/推流/FFmpeg/ExoPlayer)", [
    ["🐍 核心心法", [
        "先理解 H.264 + AAC 编码基础概念",
        "最小闭环: MediaCodec 硬解码播放一个视频",
        "FFmpeg = 万能瑞士军刀（解封装→解码→处理→编码→封装）",
        "直播 = 采集→编码→推流→拉流→解码→渲染"
    ]],
    ["📚 学习路径 (5阶段)", [
        ["阶段1: 编解码基础", [
            "H.264 — I/P/B 帧 + GOP + NAL 单元",
            "H.265(HEVC) — 更高压缩率",
            "AAC — ADTS/ADIF 封装格式",
            "MediaCodec — 异步模式编解码流程"
        ]],
        ["阶段2: 播放器开发", [
            "播放器架构: 解封装→解码→音画同步→渲染",
            "缓冲策略 — 预加载 + 边播边缓存",
            "SEI 数据注入 — 帧级信息携带",
            "音画同步 — 视频同步到音频时钟"
        ]],
        ["阶段3: 推流拉流", [
            "RTMP — 握手→建连→推流 (TCP 可靠)",
            "HLS — m3u8 + ts 切片 (CDN 友好)",
            "WebRTC — SDP/ICE/DTLS (低延迟)"
        ]],
        ["阶段4: FFmpeg 应用", [
            "交叉编译 — toolchain 配置",
            "核心结构体: AVFormatContext/AVCodecContext/AVFrame/AVPacket",
            "解封装→解码→滤镜→编码→封装 管线"
        ]],
        ["阶段5: ExoPlayer", [
            "架构: TrackSelector → LoadControl → Renderer",
            "自定义 DataSource — 边播边缓存",
            "自定义 Extractor — 私有协议支持",
            "DRM — Widevine 支持"
        ]]
    ]],
    ["🎯 面试重点", [
        "MediaCodec 异步模式完整流程",
        "I/P/B 帧区别与 GOP 概念",
        "RTMP vs HLS vs WebRTC 适用场景",
        "ExoPlayer vs MediaPlayer 架构差异",
        "音画同步的 PTS/DTS 计算"
    ]],
    ["⚡ 最小闭环项目", [
        "项目: 简易视频播放器",
        "MediaCodec + SurfaceView → 播放本地 MP4"
    ]],
    ["🔧 避坑指南", [
        "MediaCodec 颜色格式 — COLOR_FormatYUV420Flexible",
        "硬解码兼容性 — 不同芯片支持格式不同",
        "FFmpeg 交叉编译 → so 体积膨胀 (按需裁剪)"
    ]]
])


# ========== 12 - 跨平台开发 ==========
register("12-跨平台开发", "跨平台开发 (Flutter/RN/Compose Multiplatform)", [
    ["🐍 核心心法", [
        "Flutter 是新项目首选（自渲染引擎 + 热重载）",
        "RN 适合快速迭代/Web 团队转型",
        "CMP 适合 Kotlin 团队共享 UI 代码"
    ]],
    ["📚 学习路径 (3阶段)", [
        ["阶段1: Flutter", [
            "Widget/Element/RenderObject 三树",
            "Engine 层 — Skia(旧)/Impeller(新) 渲染",
            "Platform Channel — MethodChannel 原生通信",
            "状态管理: Provider/Bloc/Riverpod"
        ]],
        ["阶段2: React Native", [
            "JS Bridge — 批量异步通信",
            "Fabric 新架构 — JSI/TurboModules",
            "@ReactMethod — 原生模块导出"
        ]],
        ["阶段3: Compose Multiplatform", [
            "共享 UI — 声明式跨平台",
            "expect/actual — 平台特定实现",
            "与 Compose Android 差异"
        ]]
    ]],
    ["🎯 面试重点", [
        "Flutter 三棵树渲染流程",
        "Flutter vs RN vs CMP 选型依据",
        "Platform Channel 通信原理"
    ]],
    ["⚡ 最小闭环项目", [
        "跨平台 Todo App — Flutter 版"
    ]],
    ["🔧 避坑指南", [
        "Flutter 嵌套层级过深 → 性能问题",
        "RN Bridge 瓶颈 → Fabric JSI 优化"
    ]]
])


# ========== 13 - 构建与工程化 ==========
register("13-构建与工程化", "构建与工程化 (Gradle/CI:CD/测试/规范)", [
    ["🐍 核心心法", [
        "Gradle = Task DAG 图，理解三阶段",
        "CI/CD = 自动构建→测试→发布，减少人为失误",
        "测试金字塔: 单元(70%) > 集成(20%) > UI(10%)"
    ]],
    ["📚 学习路径 (4阶段)", [
        ["阶段1: Gradle 构建系统", [
            "三阶段: Init→Config→Exec",
            "Task DAG — 有向无环图依赖",
            "自定义 Task — doFirst/doLast",
            "Transform — 字节码插桩 (AGP 7.0 废弃，用 AsmClassVisitorFactory)",
            "自定义 Gradle 插件"
        ]],
        ["阶段2: CI/CD 流程", [
            "Jenkins Pipeline — Groovy 脚本化构建",
            "GitLab CI — .gitlab-ci.yml",
            "AAB 动态功能模块",
            "Firebase App Distribution — 内测分发"
        ]],
        ["阶段3: 测试体系", [
            "JUnit 4/5 — 单元测试基础",
            "Mockito/MockK — mock 依赖",
            "Robolectric — Android 环境模拟",
            "Espresso — UI 自动化测试"
        ]],
        ["阶段4: 代码规范", [
            "ktlint — Kotlin 代码格式化",
            "detekt — 静态分析 + 代码异味检测",
            "Git Flow / Trunk-Based Development",
            "Code Review 最佳实践"
        ]]
    ]],
    ["🎯 面试重点", [
        "Gradle 构建三阶段做了什么",
        "自定义 Gradle 插件实现",
        "CI/CD 流水线设计",
        "测试金字塔与覆盖率指标"
    ]],
    ["⚡ 最小闭环项目", [
        "为一个模块写完整的三层测试"
    ]],
    ["🔧 避坑指南", [
        "Gradle 构建慢 → buildSrc + 依赖缓存",
        "Transform 已废弃 → 迁移到 AsmClassVisitorFactory",
        "Robolectric 与真实设备差异"
    ]]
])


# ========== 14 - AI与安卓结合 ==========
register("14-AI与安卓结合", "AI与安卓结合 (AI辅助开发/大模型落地/AI编程思维)", [
    ["🐍 核心心法", [
        "先用 AI 工具辅助日常开发（Copilot/CodeGeeX）",
        "大模型落地 = 模型压缩 + 端侧推理 + 性能控制",
        "AI 编程思维 = AI 做体力活，你审核心逻辑"
    ]],
    ["📚 学习路径 (3阶段)", [
        ["阶段1: AI 辅助开发工具", [
            "GitHub Copilot — 代码补全/生成/重构",
            "CodeGeeX — 开源替代方案",
            "Prompt Engineering — 提示词工程",
            "AI 生成单元测试 — 边界用例覆盖"
        ]],
        ["阶段2: AI 大模型落地", [
            "模型压缩 — 量化(INT8/FP16→INT4)/蒸馏/剪枝",
            "端侧推理 — TFLite/ONNX Runtime/MediaPipe",
            "离线运行 — 模型打包到 APK 内",
            "性能损耗控制 — GPU Delegate/NNAPI 加速"
        ]],
        ["阶段3: AI 编程思维", [
            "AI 辅助代码重构 — 识别代码异味",
            "异常日志智能分析 — Anomaly Detection",
            "APM + AI — 智能告警归因",
            "AI 辅助性能优化方案生成"
        ]]
    ]],
    ["🎯 面试重点", [
        "端侧部署大模型的挑战与方案",
        "TFLite vs ONNX Runtime 选型",
        "AI 辅助开发的实际提效案例",
        "模型量化精度损失控制"
    ]],
    ["⚡ 最小闭环项目", [
        "项目: 端侧图片分类 App",
        "TFLite 加载量化模型 → CameraX 实时识别"
    ]],
    ["🔧 避坑指南", [
        "TFLite GPU Delegate 兼容性 — 部分算子不支持",
        "量化模型精度损失 — 混合精度(Float16+Int8)",
        "AI 生成代码不加审查直接使用"
    ]]
])


# ========== 15 - 性能优化工具专题 ==========
register("15-性能优化工具专题", "性能优化工具专题 (按工具性质分类/按先进程度排序)", [
    ["🐍 核心心法", [
        "工具只是手段，数据驱动的优化思维才是核心",
        "先用 Profiler 定位热点，再用 Systrace/Perfetto 分析链路",
        "线上用 APM 工具(Matrix/KOOM)，线下用 Studio 工具"
    ]],
    ["📚 学习路径 (5类别)", [
        ["🔍 系统级追踪", [
            "Perfetto ⭐⭐⭐⭐⭐ — SQL 查询 trace + 长时录制",
            "Systrace ⭐⭐⭐⭐ — CPU/GPU/IO 全链路"
        ]],
        ["🧠 内存分析", [
            "Memory Profiler ⭐⭐⭐⭐⭐ — 实时分配追踪 + hprof",
            "LeakCanary 2 ⭐⭐⭐⭐⭐ — 自动泄漏检测→定位",
            "MAT ⭐⭐⭐⭐ — 支配树/OQL 离线深度分析"
        ]],
        ["⚡ CPU/线程分析", [
            "CPU Profiler ⭐⭐⭐⭐⭐ — 火焰图/方法采样",
            "Simpleperf ⭐⭐⭐⭐ — Native 层 CPU 采样"
        ]],
        ["📊 APM 线上监控", [
            "Matrix(微信) ⭐⭐⭐⭐⭐ — 卡顿/内存/IO 三位一体",
            "KOOM(快手) ⭐⭐⭐⭐⭐ — Fork 无痛 OOM Dump",
            "Sentry ⭐⭐⭐⭐ — 崩溃聚合 + Session Replay"
        ]],
        ["🔋 其他专项", [
            "Battery Historian v2 — 电量耗电分析",
            "Network Profiler — 网络请求时间线",
            "APK Analyzer — 包体积构成分析"
        ]]
    ]],
    ["🎯 面试重点", [
        "Perfetto vs Systrace 区别与选择",
        "LeakCanary 检测原理 (WeakReference + GC + Dump)",
        "Matrix 卡顿监控原理 (Choreographer + Looper)",
        "KOOM Fork 子进程 Dump 原理"
    ]],
    ["⚡ 最小闭环项目", [
        "对一个 App 全链路诊断: Perfetto→Memory→CPU→Network",
        "生成性能诊断报告"
    ]],
    ["🔧 避坑指南", [
        "Systrace 在新设备上被 Perfetto 替代",
        "MAT 需要 hprof 转换: hprof-conv",
        "LeakCanary 线上版本性能开销大"
    ]]
])


# ========== 16 - 物联网与通信 ==========
register("16-物联网与通信", "物联网与通信 (BLE/Wi-Fi/Matter)", [
    ["🐍 核心心法", [
        "BLE = GATT 协议 + Service/Characteristic 模型",
        "Wi-Fi 通信 = 局域网发现(mDNS) + Socket",
        "Matter = 智能家居统一应用层协议"
    ]],
    ["📚 学习路径 (3阶段)", [
        ["阶段1: BLE 蓝牙", [
            "GATT 协议 — Service/Characteristic/Descriptor",
            "扫描→连接 BluetoothGatt → 发现服务",
            "读写 + Notify/Indicate 通知",
            "MTU 协商 — 提升单包传输效率"
        ]],
        ["阶段2: Wi-Fi 通信", [
            "Wi-Fi Direct P2P — 设备直连",
            "局域网发现 — mDNS/NSD",
            "Socket 通信 — TCP/UDP",
            "Wi-Fi Aware — 邻近感知(NAN)"
        ]],
        ["阶段3: Matter 协议", [
            "智能家居统一应用层",
            "Thread/Wi-Fi — 底层承载",
            "设备配网 — QR Code/Manual Pairing Code"
        ]]
    ]],
    ["🎯 面试重点", [
        "BLE 连接流程与 GATT 协议",
        "BLE 与经典蓝牙区别",
        "mDNS 服务发现原理"
    ]],
    ["⚡ 最小闭环项目", [
        "项目: BLE 心率监测 Demo",
        "扫描→连接→读取心率 Service 数据"
    ]],
    ["🔧 避坑指南", [
        "BLE 连接不稳定 — 重试 + 超时机制",
        "蓝牙权限 — Android 12+ BLUETOOTH_SCAN/CONNECT",
        "Matter — 目前生态不成熟，了解概念即可"
    ]]
])


# ========== 17 - 出海应用与适配 ==========
register("17-出海应用与适配", "出海应用与适配 (隐私/厂商兼容/国际化)", [
    ["🐍 核心心法", [
        "隐私权限是出海第一道坎：Scoped Storage + GDPR",
        "厂商适配 = 华为HMS + 国内厂商后台限制",
        "国际化 = strings资源 + RTL布局 + ICU格式化"
    ]],
    ["📚 学习路径 (3阶段)", [
        ["阶段1: 隐私权限适配", [
            "Android 10 — Scoped Storage 分区存储",
            "Android 11 — 强制分区存储",
            "Android 13 — 通知运行时权限",
            "Android 14 — 部分照片访问",
            "GDPR/CCPA — 用户同意 + 数据删除权"
        ]],
        ["阶段2: 厂商兼容性", [
            "华为 HMS — GMS 双框架适配",
            "小米/OPPO/Vivo — 后台限制差异",
            "厂商 ROM Bug 规避 — 反射 + try-catch 兜底"
        ]],
        ["阶段3: 国际化与本地化", [
            "多语言资源 — strings-xx/values-xx",
            "RTL 布局 — mirroring 自动镜像",
            "时区/货币/日期 — ICU 格式化",
            "AAB 按需语言分发"
        ]]
    ]],
    ["🎯 面试重点", [
        "Scoped Storage 对文件访问的影响与适配",
        "Android 11+ 分区存储强制执行",
        "GDPR 核心要求与客户端实现"
    ]],
    ["⚡ 最小闭环项目", [
        "适配一个 App: Scoped Storage + 多语言"
    ]],
    ["🔧 避坑指南", [
        "MANAGE_EXTERNAL_STORAGE — Google Play 严格审核",
        "华为推送 — 必须接入 HMS Push Kit",
        "RTL 布局 — 部分 View 不自动镜像"
    ]]
])


# ========== 18 - 高频面试题汇总 ==========
register("18-高频面试题汇总", "高频面试题汇总 (基础/架构/性能/系统)", [
    ["🐍 核心心法", [
        "先建立知识框架，再背高频题（框架→细节）",
        "每道题都按「问题→答案→原理→源码→场景」回答",
        "架构题和性能题是区分 20k vs 30k+ 的分水岭"
    ]],
    ["📚 学习路径 (4类别)", [
        ["基础面试题", [
            "Activity 启动模式与 onNewIntent",
            "Handler 消息机制源码级",
            "HashMap 扩容与红黑树",
            "Glide 三级缓存原理"
        ]],
        ["架构设计题 (高区分度)", [
            "设计一个图片加载框架",
            "IM 消息架构设计",
            "组件化路由设计",
            "网络层架构设计"
        ]],
        ["性能优化题 (高区分度)", [
            "App 启动优化全链路 + 量化指标",
            "内存泄漏场景 + 定位 + 解决",
            "RecyclerView 卡顿排查",
            "包体积优化全方案"
        ]],
        ["系统与底层题 (高区分度)", [
            "点击图标到 Activity 展示完整流程",
            "Binder 一次拷贝原理 + 驱动源码",
            "Zygote fork + COW",
            "View 绘制流程 + 事件分发"
        ]]
    ]],
    ["🎯 面试重点", [
        "架构设计题的 STAR 回答法（场景→任务→行动→结果）",
        "性能题的量化思维（优化前 xx → 优化后 yy）",
        "系统题的源码追踪能力"
    ]],
    ["⚡ 最小闭环项目", [
        "每道架构题画一张架构图",
        "性能题配 Systrace 截图证明"
    ]],
    ["🔧 避坑指南", [
        "架构设计题不要只说方案，要讲 trade-off",
        "系统题不要背诵，要画流程图表达理解"
    ]]
])


# ========== 19 - 开源框架专题 ==========
register("19-开源框架专题", "开源框架专题 (Glide/OkHttp/Retrofit/ARouter等)", [
    ["🐍 核心心法", [
        "每个框架答三点：设计思想 + 核心链路 + 亮点优化",
        "Glide/OkHttp/Retrofit 是必考三件套",
        "不要背源码，要理解架构决策(Trade-off)"
    ]],
    ["📚 学习路径 (9框架)", [
        ["Glide 图片加载 ⭐⭐⭐⭐⭐", [
            "LRU 缓存策略 — Active/LRU/Disk 三级",
            "Bitmap 复用池 — LruBitmapPool + inBitmap",
            "生命周期感知 — RequestManager + Fragment 绑定",
            "加载流程: Engine.load → DecodeJob → 编码→解码"
        ]],
        ["OkHttp 网络请求 ⭐⭐⭐⭐⭐", [
            "五大拦截器链 — Retry/Redirect/Cache/Connect/CallServer",
            "连接池 — CleanupRunnable + 5min 空闲回收",
            "HTTP/2 — 多路复用 Stream 管理",
            "DNS 优化 — 自定义 DNS 解析"
        ]],
        ["Retrofit 网络封装 ⭐⭐⭐⭐⭐", [
            "动态代理 — Proxy.newProxyInstance",
            "ServiceMethod — 注解解析",
            "Converter/CallAdapter — 序列化/响应适配工厂",
            "与 OkHttp 的关系 — Retrofit 封装 OkHttp"
        ]],
        ["ARouter 路由 ⭐⭐⭐⭐⭐", [
            "APT 编译期路由表生成",
            "分组懒加载 — 按需加载路由组",
            "拦截器链 — 绿色通道(登录校验)",
            "IProvider 服务发现"
        ]],
        ["RxJava 响应式 ⭐⭐⭐⭐⭐", [
            "map/flatMap/concatMap 区别",
            "线程调度 Schedulers — IO/Computation/Main",
            "背压策略 Flowable",
            "操作符 lift() 变换原理"
        ]],
        ["EventBus ⭐⭐⭐⭐", [
            "订阅者索引 SubscriberMethodFinder",
            "4 种 ThreadMode",
            "粘性事件 stickyEvents"
        ]],
        ["Tinker 热修复 ⭐⭐⭐⭐", [
            "Dex 差量替换 BSDiff",
            "资源补丁 Resource Patch",
            "ApplicationLike 代理"
        ]],
        ["MMKV ⭐⭐⭐⭐", [
            "mmap 内存映射",
            "Protobuf 编码 — Varint + ZigZag",
            "多进程安全 — 文件锁"
        ]],
        ["LeakCanary ⭐⭐⭐⭐", [
            "WeakReference + ReferenceQueue 检测",
            "主动 GC + HeapDump",
            "Shark 引擎 BFS 最短路径"
        ]]
    ]],
    ["🎯 面试重点", [
        "Glide vs Picasso vs Coil 选用对比",
        "OkHttp 连接池复用机制",
        "Retrofit 动态代理原理",
        "ARouter 路由表是如何生成的"
    ]],
    ["⚡ 最小闭环项目", [
        "阅读 Glide Engine.load() 源码 → 画流程图"
    ]],
    ["🔧 避坑指南", [
        "Glide with(fragment) 避免 Application Context",
        "OkHttp response.body() 只能读一次",
        "EventBus 索引混淆 — APT 生成的类需 keep"
    ]]
])


# ========== 20 - 并发编程与线程安全 ==========
register("20-并发编程与线程安全", "并发编程与线程安全 (Java并发/线程池/协程并发/线程安全/锁)", [
    ["🐍 核心心法", [
        "并发三要素：原子性(synchronized/Atomic) + 可见性(volatile) + 有序性(happens-before)",
        "线程池 = 核心线程→队列→最大线程→拒绝策略",
        "协程 = 更轻量的并发，结构化并发是精髓"
    ]],
    ["📚 学习路径 (5阶段)", [
        ["阶段1: Java 并发基础", [
            "Thread/Runnable/Callable/Future",
            "ThreadPoolExecutor — 7 参数调参",
            "CAS 与 Atomic 类 — 无锁并发",
            "AQS 框架 — ReentrantLock/CountDownLatch 的基石"
        ]],
        ["阶段2: Android 线程模型", [
            "主线程 Looper — ActivityThread.main()",
            "HandlerThread — 带 Looper 的后台线程",
            "IntentService 废弃 — 替代方案(WorkManager)",
            "线程优先级 — THREAD_PRIORITY_BACKGROUND"
        ]],
        ["阶段3: Kotlin 协程并发", [
            "结构化并发 — coroutineScope/supervisorScope",
            "Mutex/Semaphore — 协程同步原语",
            "Channel — 协程间通信管道",
            "协程取消 — Job.cancel() + isActive 协作"
        ]],
        ["阶段4: 线程安全实践", [
            "不可变对象 — final + 防御性拷贝",
            "ThreadLocal — 原理与内存泄漏",
            "ConcurrentHashMap — JDK7(分段锁)→JDK8(CAS+synchronized)",
            "CopyOnWriteArrayList — 读写分离"
        ]],
        ["阶段5: 锁机制", [
            "synchronized 锁升级 — 偏向→轻量→重量",
            "ReentrantLock — 公平/非公平 + Condition",
            "读写锁 — ReadWriteLock",
            "死锁排查 — jstack + stuck thread 检测"
        ]]
    ]],
    ["🎯 面试重点", [
        "synchronized vs ReentrantLock 区别与使用场景",
        "ThreadPoolExecutor 参数计算（CPU密集 vs IO密集）",
        "ConcurrentHashMap 为什么线程安全",
        "协程取消的协作机制"
    ]],
    ["⚡ 最小闭环项目", [
        "项目: 图片批量下载",
        "线程池 + 协程 两种实现对比"
    ]],
    ["🔧 避坑指南", [
        "线程池 OOM — 无界队列 + 大量任务",
        "ThreadLocal 内存泄漏 — 忘记 remove()",
        "协程 GlobalScope 滥用"
    ]]
])


# ========== 21 - 内存管理 ==========
register("21-内存管理", "内存管理 (JVM内存/ART GC/内存分配/内存监控/Native内存)", [
    ["🐍 核心心法", [
        "内存 = 分配 + 回收 + 监控 三位一体",
        "ART GC 演进 = 停顿时间越来越短 (10ms→1ms)",
        "onTrimMemory = 系统内存压力的最后防线"
    ]],
    ["📚 学习路径 (5阶段)", [
        ["阶段1: JVM 内存模型", [
            "运行时数据区 — 堆/栈/方法区/程序计数器/本地方法栈",
            "对象创建 5 步 — 类加载→分配内存→零值→对象头→init",
            "MarkWord + KlassPointer 布局",
            "TLAB — 线程本地分配缓冲",
            "逃逸分析 + 栈上分配"
        ]],
        ["阶段2: ART 内存与 GC", [
            "Dalvik→ART GC 演进",
            "Concurrent Copying GC — 主回收器",
            "Baker Read Barrier — 并发复制不暂停",
            "Region-based → 分代 GC",
            "GC 暂停时间 ~1ms"
        ]],
        ["阶段3: 内存分配策略", [
            "Bump Pointer — 指针碰撞分配",
            "RosAlloc — Bump + Slot 混合",
            "RegionSpace — 区域空间管理",
            "对象 8 字节对齐"
        ]],
        ["阶段4: 内存监控", [
            "onTrimMemory — TRIM_MEMORY_RUNNING_MODERATE~COMPLETE",
            "memoryClass/largeHeap",
            "LMK — LowMemoryKiller + OOM Adj 机制",
            "内存压力降级策略 — 缓存→图片质量→功能"
        ]],
        ["阶段5: Native 内存管理", [
            "jemalloc — arena/bin/run + tcache",
            "mmap 匿名映射",
            "ashmem 共享内存",
            "Native 泄漏检测 — malloc_debug",
            "Bitmap 内存演进 — Native→Java堆→Native(8.0)"
        ]]
    ]],
    ["🎯 面试重点", [
        "ART GC 与 Dalvik GC 的核心差异",
        "Concurrent Copying GC 如何做到低停顿",
        "onTrimMemory 触发时机与降级策略",
        "LMK OOM Adj 等级与进程回收顺序"
    ]],
    ["⚡ 最小闭环项目", [
        "实验: 制造内存压力 → 观察 onTrimMemory 回调"
    ]],
    ["🔧 避坑指南", [
        "largeHeap=true 非万能 — 仅在图片/视频类 App 使用",
        "onTrimMemory 在不同厂商 ROM 行为不一致"
    ]]
])


# ========== 22 - 高性能编程 ==========
register("22-高性能编程", "高性能编程 (对象池/零拷贝/序列化/IO优化/编译优化)", [
    ["🐍 核心心法", [
        "高性能 = 减少分配(对象池) + 减少拷贝(零拷贝) + 减少解析(序列化选型)",
        "安卓里处处是优化: Message 池/RecyclerView 缓存/Glide BitmapPool",
        "Profile-Guided Optimization(PGO) = 让系统帮你优化"
    ]],
    ["📚 学习路径 (5阶段)", [
        ["阶段1: 对象复用与池化", [
            "Message 池化 — sPool 链表（享元模式）",
            "RecyclerView 四级缓存 — mAttachedScrap/Cache/ViewCacheExtension/RecycledViewPool",
            "Glide BitmapPool — LruBitmapPool + inBitmap",
            "装箱陷阱 — Integer.valueOf 缓存(-128~127)"
        ]],
        ["阶段2: 零拷贝", [
            "Binder mmap — 一次拷贝原理",
            "sendfile/FileChannel.transferTo — DMA gather",
            "ashmem — 匿名共享内存",
            "DirectByteBuffer — 堆外内存，避免 JVM 堆拷贝"
        ]],
        ["阶段3: 序列化优化", [
            "Parcelable vs Serializable — 速度 10x 差距",
            "ProtoBuf/FlatBuffers vs JSON — 空间 3-10x 差距",
            "Moshi vs Gson vs kotlinx.serialization",
            "SharedPreferences apply vs commit ANR 风险"
        ]],
        ["阶段4: IO 与存储优化", [
            "NIO vs BIO — Channel + Buffer 模型",
            "mmap 文件读写 — MMKV 底层",
            "WAL 日志 — SQLite 写性能提升",
            "DiskLruCache — 磁盘缓存策略"
        ]],
        ["阶段5: 编译优化", [
            "R8 三阶段 — Shrinking→Optimization→Obfuscation",
            "方法内联/去虚拟化/分支剪枝",
            "Baseline Profile — AOT 预编译热点代码",
            "PGO — 运行时收集 + 重编译优化"
        ]]
    ]],
    ["🎯 面试重点", [
        "Message 池化原理（享元模式）",
        "Binder 一次拷贝与 Linux sendfile 对比",
        "ProtoBuf vs FlatBuffers 适用场景",
        "Baseline Profile 原理与效果",
        "RecyclerView 四级缓存触发条件"
    ]],
    ["⚡ 最小闭环项目", [
        "对比: JSON(Parser) vs ProtoBuf 序列化耗时"
    ]],
    ["🔧 避坑指南", [
        "对象池不要过度设计 — 只在热点路径使用",
        "DirectByteBuffer 释放时间不确定",
        "Baseline Profile 需要 Cloud Profiles 配合"
    ]]
])


# ====== 主入口 ======
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python generate_xmind.py <模块编号>")
        print("示例: python generate_xmind.py 01")
        print("      python generate_xmind.py all  # 生成全部")
        print("\n可用模块:")
        for k, v in MODULES.items():
            print(f"  {k} — {v['title']}")
        sys.exit(0)

    target = sys.argv[1]

    if target == "all":
        for module_id, module_data in MODULES.items():
            out_path = f"/home/heavy/AndroidJob/{module_id}/知识骨架.xmind"
            create_xmind(
                out_path,
                module_data["title"],
                module_data["title"],
                module_data["skeleton"]
            )
        print(f"\n✅ 全部 {len(MODULES)} 个模块的 XMind 已生成！")
    elif target in MODULES:
        module_data = MODULES[target]
        out_path = f"/home/heavy/AndroidJob/{target}/知识骨架.xmind"
        create_xmind(
            out_path,
            module_data["title"],
            module_data["title"],
            module_data["skeleton"]
        )
    else:
        print(f"❌ 未知模块: {target}")
        print(f"可用: {', '.join(MODULES.keys())}")
        sys.exit(1)
