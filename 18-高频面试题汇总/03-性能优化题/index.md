# 03 性能优化题

> 面向 30k+ 岗位的性能优化深度解析，覆盖启动、卡顿、内存、包体积四大核心优化领域。每道题按"六层递进"结构展开：面试官问法还原 → 答题思路框架 → 核心知识点精讲 → 工具实操演示 → 加分扩展延伸 → 常见误区与避坑，帮你从"会用工具"升级到"能讲原理、能建体系"。

---

## 目录

1. [启动优化完整链路](#1-启动优化完整链路)
2. [卡顿定位全流程](#2-卡顿定位全流程)
3. [内存泄漏排查体系](#3-内存泄漏排查体系)
4. [包体积优化方案](#4-包体积优化方案)

---

## 1. 启动优化完整链路

### 第一层：面试官问法还原

> "你们 App 的冷启动耗时是多少？对整个启动流程做过哪些优化？如何用 Systrace 定位启动阶段的瓶颈？启动优化后指标提升了多少？"

面试官关注三个层次：
- **有没有做**：是否建立启动耗时监控，是否量化指标（TTID/TTFD）。
- **怎么做的**：用什么工具定位瓶颈，用什么策略优化。
- **做到了什么程度**：从多少 ms 优化到多少 ms，效果如何。

---

### 第二层：答题思路框架

```
冷启动时间线：
点击图标 →  fork 进程 →  bindApplication →  Application.onCreate()
→  attachBaseContext() →  ContentProvider.onCreate() →  Application.onCreate()
→  Activity.onCreate() →  onStart() →  onResume()
→  首帧绘制（TTID 终点） →  首帧数据展示（TTFD 终点）
```

回答逻辑：**先定义指标**（TTID/TTFD/冷温热启动）→ **讲启动过程**（各阶段做了什么）→ **Systrace 定位**（如何分析）→ **优化方案**（异步化、延迟初始化、预加载）→ **量化效果**。

---

### 第三层：核心知识点精讲

#### 3.1 冷启动的六个关键阶段

| 阶段 | 做什么 | 可优化空间 |
|------|--------|-----------|
| ① 点击图标→fork 进程 | AMS 通过 Zygote fork 新进程 | 基本不可控 |
| ② bindApplication | 加载 APK、ClassLoader、Provider | 减少 Provider 数量 |
| ③ Application.attachBaseContext | MultiDex 安装、Tinker 等 | 异步加载 / 预编译 |
| ④ ContentProvider.onCreate | 所有 Provider 初始化 | 延迟到用时再初始化 |
| ⑤ Application.onCreate | SDK 初始化、全局配置 | 异步化 / 懒加载 |
| ⑥ Activity.onCreate→首帧 | 布局 inflate、数据请求、首帧渲染 | 布局优化、预加载 |

**关键认知**：Application.onCreate() 在主线程同步执行，**所有 SDK 的初始化都会阻塞首帧**。

#### 3.2 三种启动类型

| 类型 | 定义 | 典型耗时 |
|------|------|---------|
| 冷启动（Cold Start） | 进程被杀死后从头启动 | 最长（> 500ms） |
| 温启动（Warm Start） | 进程存活但 Activity 被销毁 | 中等（~200ms） |
| 热启动（Hot Start） | Activity 在后台直接回到前台 | 最短（~100ms） |

#### 3.3 核心指标定义

- **TTID（Time To Initial Display）**：从点击图标到首帧 Activity 绘制完成。通过 `adb shell am start -W` 获取，或系统日志 `Displayed` 过滤。
- **TTFD（Time To Full Display）**：从点击图标到首帧数据完全展示（网络上数据渲染完）。需手动打点 `reportFullyDrawn()`。
- **API 33+ 官方指标**：`ActivityManager.getHistoricalProcessStartReasons()` 和 `ApplicationStartInfo`。

#### 3.4 异步初始化策略

**基础方案（有坑）**：

```kotlin
// ❌ 简单开线程——线程竞争导致更慢
Thread { initSdk1() }.start()
Thread { initSdk2() }.start()
Thread { initSdk3() }.start()
```

**进阶方案：拓扑排序启动器**

```kotlin
// 定义 Task 依赖关系
class StartupTask(val name: String, val dependsOn: List<String> = emptyList()) {
    var executor: Executor? = null  // 指定线程池
    var waitOnMainThread: Boolean = false  // 是否需要主线程等待
}

// 按拓扑排序执行
// IdleHandler 空闲时执行最低优先级 Task
```

**核心设计思想**：
1. 梳理所有 SDK 依赖关系，构建有向无环图（DAG）。
2. 拓扑排序，确定哪些必须在主线程、哪些可以异步、哪些可以等待空闲。
3. 分阶段执行：核心路径（同步）→ 重要异步（子线程）→ 不重要（IdleHandler）。

**Jetpack Startup 库**：
- 替代传统 ContentProvider 初始化方式。
- `Initializer<T>` 接口 + `@Initializer` 注解 + 依赖声明。
- 底层合并所有 ContentProvider 为一个 `InitializationProvider`，减少 Provider 数量。

---

### 第四层：工具实操演示

#### Systrace 分析启动耗时

```bash
# 抓取启动阶段的 Trace
# Android 10+ 使用 Perfetto（替代 Systrace）
# 方式一：命令行
python systrace.py -o startup.html -a com.example.app gfx view res am wm dalvik

# 方式二：Perfetto（推荐）
# chrome://tracing 或 ui.perfetto.dev 打开 trace 文件
```

**Systrace 中重点关注**：

| 标记 | 含义 | 分析要点 |
|------|------|---------|
| `bindApplication` | 进程初始化 | 看 Provider 数量和耗时 |
| `activityStart` | Activity 创建 | 看 onCreate 内各方法耗时 |
| `inflate` | 布局加载 | 看层级深度和 inflate 时间 |
| `Choreographer#doFrame` | 帧绘制 | 看掉帧情况（> 16.67ms 的帧） |

**自定义 Trace 打点**：

```kotlin
// 应用内打点（配合 Systrace 显示）
Trace.beginSection("Init_ImageLoader")
ImageLoader.init()
Trace.endSection()

// 或使用 AndroidX 的 Tracing
androidx.tracing.Trace.beginAsyncSection("Init_Network", 0)
// ... 异步初始化 ...
androidx.tracing.Trace.endAsyncSection("Init_Network", 0)
```

**常见 Systrace 分析结论**：
- 看到主线程有大段绿色（Running）但没有 trace section → 未打点区域，可能遗漏的耗时方法。
- 看到多个线程在 `binder transaction` → IPC 调用过多，考虑批量或缓存。
- 看到 `Choreographer#doFrame` 红色长条 → 主线程阻塞超过 16.67ms，掉帧。

---

### 第五层：加分扩展延伸

**1. 预加载与预热**

```kotlin
// Application.attachBaseContext 阶段
// - Class 预加载：把首页必要 Class 提前 load
// - 资源预加载：把首页图片提前解码到内存
// - WebView 预热：提前创建 WebView 进程和内核
```

**2. 启动窗口（Splash Screen）策略**

- **Android 12+**：系统 SplashScreen API，自动生成启动画面（取 `windowSplashScreenBackground` + icon）。
- **旧版本**：`windowBackground` 设置一个 layer-list drawable，在首帧绘制前瞬间展示，给用户"秒开"感受。
- **注意**：不是真的加快启动，而是提升**体感启动速度**。

**3. 多进程架构对启动的影响**

- 主进程 + WebView 进程 + Push 进程 + ... → fork 次数增多，每个进程有独立 Application。
- `android:process=":xxx"` 的进程不要做无关初始化。

**4. 线上监控体系**

```kotlin
// 监控启动耗时并上报
class StartupMonitor {
    // 打点记录
    var processStartTime: Long  // Process.getStartElapsedRealtime()
    var appOnCreateStart: Long
    var appOnCreateEnd: Long
    var firstActivityOnCreateStart: Long
    var firstFrameDrawn: Long  // ViewTreeObserver.OnDrawListener / IdleHandler

    fun report() {
        val total = firstFrameDrawn - processStartTime
        // 上报到 APM 平台（如 Firebase Performance）
    }
}
```

**5. Android 15 的启动优化新特性**

- **SDK 沙箱（Privacy Sandbox）**：减少跨进程通信开销。
- **16KB 页面大小**：可能需要重新编译 SO 库以适配。

---

### 第六层：常见误区与避坑

| 误区 | 正确做法 |
|------|---------|
| ❌ 所有初始化都放到子线程 | 注意线程安全，部分 SDK 要求主线程初始化（如 UI 库） |
| ❌ 使用 `new Thread()` 大量创建线程 | 用线程池统一管理，避免线程竞争 |
| ❌ 只看 TTID，不看 TTFD | TTID 可能只是一个白屏，TTFD 才是真正的"数据可见" |
| ❌ 过度使用 IdleHandler 延迟初始化 | IdleHandler 在主线程空闲时回调，如果消息队列一直有任务，可能永远不会执行 |
| ❌ 不监控线上启动耗时 | 线下测试和线上真实环境差距很大，必须有线上指标 |
| ❌ ContentProvider 里做重初始化 | Provider 的 `onCreate` 在 `Application.attachBaseContext` 后立即执行，会阻塞启动 |

---

## 2. 卡顿定位全流程

### 第一层：面试官问法还原

> "用户反馈列表滑动卡顿，你怎么定位？Systrace 怎么分析帧耗时？CPU Profiler 怎么用？你们做过哪些布局优化？"

这道题考察你**能否端到端解决一个卡顿问题**——从用户反馈到根因定位再到修复上线。

---

### 第二层：答题思路框架

```
卡顿定位三步走：
第一步：复现并量化（线下复现+帧率监控）
第二步：系统级定位（Systrace 找帧问题）
第三步：代码级定位（CPU Profiler 找方法耗时）
第四步：针对性优化（布局/IO/算法/线程）
```

**一句话定义**：卡顿的本质是**主线程做了不该在主线程做的事，导致无法在 16.67ms 内完成一帧的渲染**。

---

### 第三层：核心知识点精讲

#### 3.1 卡顿的底层原理

Android 渲染流水线（每秒 60 帧 = 16.67ms/帧）：

```
VSYNC 信号 → Input 处理 → Animation → Measure → Layout → Draw
→ RenderThread → SurfaceFlinger 合成 → 屏幕显示
```

如果这一套流水在 16.67ms 内没完成：
- 掉 1 帧 → 轻微感觉
- 掉 3-5 帧 → 明显卡顿（60ms+ 无响应）
- 掉 10+ 帧 → 严重卡顿（用户可感知的"卡死"）

#### 3.2 常见卡顿原因分类

| 类别 | 具体原因 | 解决方案 |
|------|---------|---------|
| **布局复杂** | 层级过深、过度绘制、频繁 requestLayout | 布局优化 |
| **主线程 IO** | SharedPreference 读写、文件操作、DB 查询 | 异步 IO |
| **主线程计算** | JSON 解析、图片解码、加密解密 | 子线程处理 |
| **GC 频繁** | 大量对象创建导致 GC 暂停主线程 | 对象池、避免装箱 |
| **锁竞争** | 主线程等子线程释放锁 | 重构锁逻辑 |
| **Binder 调用** | 大量跨进程调用 | 缓存、批量 |

#### 3.3 过度绘制（Overdraw）

**定义**：同一个像素点在单帧内被绘制了多次。

**检测方法**：
```
设置 → 开发者选项 → 调试 GPU 过度绘制 → 显示过度绘制区域
```

颜色含义：
- **原色**：1x 绘制（正常）
- **蓝色**：2x 绘制（可接受）
- **绿色**：3x 绘制（需要优化）
- **粉色**：4x 绘制（严重）
- **红色**：5x+ 绘制（必须优化）

**优化方案**：
1. 移除 Window 默认背景：`getWindow().setBackgroundDrawable(null)` （如果 Activity 的根布局会完全覆盖）。
2. 减少不必要的背景：父布局有背景时子布局不要再设置背景。
3. `clipChildren` / `clipToPadding`：减少绘制区域。

#### 3.4 布局优化核心策略

```xml
<!-- 1. 使用 merge 减少层级 -->
<!-- 父布局是 FrameLayout 时，子布局根节点用 merge 替代 -->
<merge xmlns:android="...">
    <TextView ... />
    <Button ... />
</merge>

<!-- 2. ViewStub 延迟加载 -->
<!-- 不常用但耗时的布局，用时再 inflate -->
<ViewStub
    android:id="@+id/stub_detail"
    android:layout="@layout/layout_detail"
    android:inflatedId="@+id/panel_detail" ... />

// Kotlin 中使用
binding.stubDetail.viewStub?.inflate()

<!-- 3. 使用 ConstraintLayout 扁平化 -->
<!-- 替代多层嵌套的 LinearLayout -->
<androidx.constraintlayout.widget.ConstraintLayout ...>
    <!-- 通过约束关系减少层级 -->
</androidx.constraintlayout.widget.ConstraintLayout>
```

**异步 inflate**：

```kotlin
// AsyncLayoutInflater（AndroidX 提供）
AsyncLayoutInflater(this).inflate(R.layout.complex_layout, null) { view, resId, parent ->
    // 在主线程回调
    parent?.addView(view)
}
// 注意：inflate 的 View 不能直接操作，必须在回调中处理
```

---

### 第四层：工具实操演示

#### 4.1 Systrace 分析卡顿

```bash
# 完整抓取命令
python systrace.py -o jank.html -t 10 gfx input view wm am dalvik res sched freq idle

# Perfetto（Android 10+）
# 开发者选项 → 系统跟踪 → 录制跟踪记录
```

**Systrace 中识别卡顿**：

- 查找 `Choreographer#doFrame` 行 → F 标记（绿色）表示正常帧，红色/橙色表示掉帧。
- 点击红色帧 → 看下面哪个线程在 Running 状态 → 如果主线程 Running 但不在 `doFrame`，说明有其他代码占用了主线程。
- 查看 CPU 调度：是否因为 CPU 频率低、被其他线程抢占。

**按 `W` 键放大，按 `M` 键标记选中区域看耗时。**

#### 4.2 CPU Profiler 定位热点方法

**使用步骤**：
1. Android Studio → View → Tool Windows → Profiler → CPU。
2. 选择 **Callstack Sample**（低开销）或 **Trace Java Methods**（详细但开销大）。
3. 操作 App 到卡顿场景，点击 Stop 生成报告。

**如何读报告**：

| 视图 | 用途 |
|------|------|
| **Top Down** | 从入口方法向下展开，适合看调用链 |
| **Bottom Up** | 从底层方法向上聚合，**最适合找热点方法** |
| **Flame Chart** | 火焰图，看方法调用耗时占比（横轴宽度 = 耗时） |
| **Call Chart** | 按时间线展示方法调用 |

**关键指标**：
- **Self Time**：方法自身执行耗时（不含子方法），直接定位问题方法。
- **Children Time**：方法总耗时（含子方法），看整体影响。

---

### 第五层：加分扩展延伸

**1. 流畅度指标量化**

| 指标 | 计算方式 | 达标线 |
|------|---------|--------|
| **帧率 FPS** | 每秒绘制帧数 | > 55 帧 |
| **掉帧率** | 掉帧次数 / 总帧数 | < 5% |
| **卡顿率** | 超过 700ms 的卡顿次数 / 操作次数 | < 0.1% |
| **SM（流畅度）** | 基于帧耗时的加权评分 | 各家定义不同 |

**2. Android Vitals（Google Play 官方指标）**：
- **Slow rendering**：超过 50% 的帧渲染时间超过 16ms。
- **Frozen frames**：超过 700ms 的 UI 冻结帧。
- 可以直接在 Play Console 中看到用户侧数据，是 Google 排名因子之一。

**3. 线上卡顿监控方案**

```kotlin
// 方案一：Choreographer 帧回调监控
Choreographer.getInstance().postFrameCallback(object : Choreographer.FrameCallback {
    override fun doFrame(frameTimeNanos: Long) {
        val dropped = (frameTimeNanos - lastFrameTimeNanos) / 16_666_666 - 1
        if (dropped > 3) reportJank(dropped)
        lastFrameTimeNanos = frameTimeNanos
        Choreographer.getInstance().postFrameCallback(this)
    }
})

// 方案二：Looper Printer 监控
// 通过 setMessageLogging 在每个 Message 前后打点，计算耗时
Looper.getMainLooper().setMessageLogging { log ->
    if (log.startsWith(">>>>> Dispatching")) {
        dispatchStart = System.currentTimeMillis()
    } else if (log.startsWith("<<<<< Finished")) {
        val cost = System.currentTimeMillis() - dispatchStart
        if (cost > threshold) reportBlock(cost, stackTrace)
    }
}
```

**4. Matrix 的卡顿监控原理**
- 微信开源的 APM 框架 Matrix。
- 核心方案：**Looper Monitor + 堆栈采样**。
- 当消息处理超时时，获取主线程堆栈并分析，区分卡顿和正常耗时。

**5. Baseline Profiles（云配置文件）**
- Android 9+ 支持，通过 Play Store 下发预编译配置。
- 在安装时提前 AOT 编译关键路径代码，减少运行时 JIT 的热度积累时间。
- 对启动速度和页面切换流畅度有明显提升。

---

### 第六层：常见误区与避坑

| 误区 | 正确做法 |
|------|---------|
| ❌ Systrace 只看彩色条，不看 CPU 调度 | CPU 频率低、大核没跑起来也会导致掉帧 |
| ❌ CPU Profiler 开 Trace Java Methods 太久 | 采样模式（Sample）足够定位问题，Instrumented 模式开销极大 |
| ❌ 发现卡顿就优化布局 | 先确认是布局慢还是数据慢（measure 耗时 vs onDraw 耗时 vs 数据处理耗时） |
| ❌ `android:layerType="software"` 随意加 | 软件层会关闭硬件加速，可能导致其他渲染问题 |
| ❌ 过度使用 `ViewStub` | inflate 本身也要耗时，核心流程中不建议太多 ViewStub |
| ❌ 线上不开卡顿监控 | 用户手机千差万别，线下低端机不一定能暴露所有问题 |

---

## 3. 内存泄漏排查体系

### 第一层：面试官问法还原

> "你们项目遇到过哪些内存泄漏？怎么用 LeakCanary 排查？如果线上不能用 LeakCanary 怎么定位？MAT 怎么分析 hprof 文件？你们的内存监控体系是怎么建的？"

这道题考察**能否建立完整的内存问题定位和监控体系**，而不仅仅是"用过 LeakCanary"。

---

### 第二层：答题思路框架

```
内存泄漏排查四步法：
Step 1：发现泄漏（LeakCanary 线下 / KOOM 线上 / OOM 异常）
Step 2：分析泄漏链（LeakCanary 自动解析 / MAT 手动分析）
Step 3：定位原因（看引用链，找到谁持有了不该持有的对象）
Step 4：修复并建立监控（修复代码 + 建立线上监控和报警）
```

**一句话总结**：内存泄漏 = GC Root →（引用链）→ 本应被回收的对象。**Reference Chain 越短，根因越明显。**

---

### 第三层：核心知识点精讲

#### 3.1 GC Root 与引用链

Java 的 GC 从 **GC Root** 出发，沿着引用链遍历，未被访问到的对象被回收。

**GC Root 有哪些**：
- 栈帧中的局部变量（方法中的引用）
- 静态变量（类的 static 字段）
- JNI 全局引用
- 活跃的线程
- 同步锁持有的对象

**内存泄漏的本质**：一个 GC Root 持有了一个不再需要但尚未释放的引用，导致目标对象无法被回收。

#### 3.2 高频泄漏场景与修复

**场景一：Handler / Runnable 匿名内部类**

```kotlin
// ❌ 泄漏：匿名 Runnable 持有 Activity
class LeakActivity : Activity() {
    private val handler = Handler(Looper.getMainLooper())
    fun postDelayed() {
        handler.postDelayed({
            // 这个 lambda 持有外部 Activity 的引用
            doSomething()
        }, 60_000)  // 1 分钟延迟，Activity 可能已销毁
    }
}

// ✅ 修复：在 onDestroy 中移除所有消息
override fun onDestroy() {
    handler.removeCallbacksAndMessages(null)
    super.onDestroy()
}
```

**场景二：单例持有 Activity Context**

```kotlin
// ❌ LeakCanary 必报
object ToastHelper {
    fun init(context: Context) {
        // context 是 Activity → Activity 被单例持有 → 泄漏
        this.appContext = context
    }
}

// ✅ 传入 ApplicationContext
ToastHelper.init(context.applicationContext)
```

**场景三：静态集合持有 View/Activity**

```kotlin
object ViewPool {
    val views = mutableListOf<View>()  // ❌ 静态持有
    fun add(view: View) = views.add(view)
    fun remove(view: View) = views.remove(view)
}
// Activity 销毁时 View 仍在静态集合中 → 泄漏
```

**场景四：资源未关闭**

- **FileInputStream / FileOutputStream**
- **Cursor**（数据库查询后未关闭）
- **Bitmap**（大图未 recycle）
- **BroadcastReceiver / ContentObserver** 未反注册
- **RxJava / Flow** 订阅未取消（`dispose()` / `collect` 协程未 cancel）

```kotlin
// ✅ Kotlin 的 use 自动关闭
FileInputStream(file).use { stream ->
    // 离开 use 块自动 close
}

// ✅ Lifecycle 感知的协程
lifecycleScope.launch {
    // 自动在 onDestroy 时取消
}
```

**场景五：动画未取消**

```kotlin
// ❌ 属性动画持有 View 的引用
ObjectAnimator.ofFloat(view, "alpha", 0f, 1f).apply {
    repeatCount = ValueAnimator.INFINITE
    start()
}
// Activity 销毁后动画仍在运行 → 泄漏
// ✅ onDestroy 中 cancel()
override fun onDestroy() {
    animator.cancel()
    super.onDestroy()
}
```

---

### 第四层：工具实操演示

#### 4.1 LeakCanary 使用与原理

**接入**（一行代码）：

```kotlin
// build.gradle
debugImplementation 'com.squareup.leakcanary:leakcanary-android:2.12'

// 2.x 版本无需手动初始化，ContentProvider 自动注入
// 检测到泄漏后自动弹出通知，展示泄漏链
```

**LeakCanary 原理（面试常考）**：

```
1. Activity/Fragment 销毁后，用 WeakReference 包装
2. GC 触发后检查 ReferenceQueue，如果 WeakReference 仍未被回收 → 疑似泄漏
3. Dump 内存（Debug.dumpHprofData）→ Shark 解析 hprof → 分析引用链
4. 找到最短的强引用路径（LeakTrace）→ 展示给开发者
```

**Shark 是 LeakCanary 2.x 的重写版 hprof 解析器，比 MAT 更轻量，可直接嵌入 App。**

#### 4.2 MAT（Memory Analyzer Tool）分析 hprof

**获取 hprof 文件**：

```bash
# 方式一：Profiler 导出
# Android Studio → Profiler → Memory → Dump Java Heap → Export

# 方式二：命令行
adb shell am dumpheap com.example.app /data/local/tmp/heap.hprof
adb pull /data/local/tmp/heap.hprof

# 方式三：代码触发
Debug.dumpHprofData("/sdcard/heap.hprof")
```

**hprof 转换**（Android 的 hprof 格式与标准 Java 不同）：

```bash
# 使用 Android SDK 自带的 hprof-conv
hprof-conv android_heap.hprof mat_heap.hprof
```

**MAT 分析步骤**：

| 步骤 | 操作 | 查找内容 |
|------|------|---------|
| 1 | **Histogram**（直方图） | 按类统计对象数量，找数量异常的类 |
| 2 | **Dominator Tree**（支配树） | 看谁"主导"了最多内存 |
| 3 | **Path to GC Roots** | 找泄漏对象的 GC Root 路径 |
| 4 | **Merge Shortest Paths to GC Roots** | 同类型对象聚合分析 |
| 5 | **OQL**（对象查询语言） | `SELECT * FROM com.example.MyActivity` |

**MAT 中关键概念**：

- **Shallow Heap**：对象自身占用的内存（不含引用对象）。
- **Retained Heap**：对象自身 + 它独占引用的所有对象的内存。**Retained Heap 是判断泄漏严重程度的核心指标**。
- 一个 Activity 的 Retained Heap 超过 5MB → 严重泄漏。

---

### 第五层：加分扩展延伸

**1. 线上内存监控方案（KOOM）**

快手开源的 KOOM（Kwai OOM）核心思路：

```
1. 后台线程定时检测内存占用
2. 接近阈值时触发内存 dump（fork 子进程 dump，避免冻结主进程）
3. dump 完成后分析 hprof（核心能力：分治解析 + 裁剪无用数据）
4. 上传分析结果而非完整 hprof（减少数据量）
5. 服务端聚合分析 + 报警
```

**为什么线上不能用 LeakCanary？**
- Dump hprof 会暂停 ART（Stop-The-World），导致 App 卡顿数秒。
- 线上频繁 dump 严重影响用户体验。
- LeakCanary 主要用于 Debug 阶段。

**2. 内存抖动（Memory Churn）**

和内存泄漏不同，内存抖动是**短时间内大量对象创建和释放**，导致 GC 频繁。

**检测**：
- Profiler Memory → 看 Memory 曲线锯齿状波动。
- Allocation Tracking → 看哪些方法大量分配对象。

**常见原因**：
- `onDraw` 中创建对象（如 `new Paint()`、`new Path()`）
- 循环中拼接字符串（用 `StringBuilder`）
- 频繁装箱拆箱

**3. WeakReference 与 ReferenceQueue**

```kotlin
val refQueue = ReferenceQueue<Activity>()
val weakRef = WeakReference(activity, refQueue)

// 当 activity 被 GC 后，weakRef 进入 refQueue
// 可用来监控对象是否被正确回收
```

**4. Native 内存泄漏**

Android 8.0+ 的 NativeAllocationRegistry：
- Java 对象通过 `nativeNew` 分配 Native 内存，通过 `nativeFree` 释放。
- `NativeAllocationRegistry` 在 Java 对象 GC 时自动调用 `nativeFree`。
- 如果 Java 对象因泄漏未 GC → Native 内存也泄漏。

**排查工具**：
- AddressSanitizer（ASan）
- Malloc Debug（`wrap.sh`）
- Perfetto Memory Trace

**5. Android 14+ 的内存管理新特性**

- **App 内存限制更严格**：后台 App 内存限制降低。
- **MEMORY_SAVER Intent**：系统通知 App 进入内存节省模式。
- **onTrimMemory(TRIM_MEMORY_RUNNING_CRITICAL)**：更激进的 trim 信号。

---

### 第六层：常见误区与避坑

| 误区 | 正确做法 |
|------|---------|
| ❌ 只看 LeakCanary 报告，不验证是否真的泄漏 | 多次进出页面确认，有些只是 GC 延迟 |
| ❌ 看到 Activity 泄漏就加 `WeakReference` 了事 | WeakReference 能防止对象不被回收，但不会阻止对象提前被回收；如果对象还需要用，应从根本上解除引用 |
| ❌ MAT 中只看 Histogram，不分析 Dominator Tree | 同一 Activity 被多个不同 GC Root 间接持有，Dominator Tree 更容易找到根因 |
| ❌ 只在 Debug 包发现问题，Release 包不管 | Release 包 R8 优化可能引入不同的泄漏模式 |
| ❌ 内存问题只关注 Java Heap | Native Heap、Graphics Memory、Code Memory 也可能导致 OOM |
| ❌ 修复后不复测 | 使用 LeakCanary 的 Instrumentation Test 集成，自动回归检测 |

---

## 4. 包体积优化方案

### 第一层：面试官问法还原

> "你们的 APK 现在多大？做过哪些包体积优化？从多少减到多少？代码混淆怎么配？ABI 分包你们怎么做的？动态下发是怎么设计的？"

这道题考察**系统性优化能力**和**工程化思维**——不是零散的优化点，而是完整的优化链路和量化效果。

---

### 第二层：答题思路框架

```
包体积优化全景图：
├── 资源优化（40-60% 体积占比）
│   ├── 图片：WebP 转换、矢量图、压缩、TinyPNG
│   ├── 语言：只保留需要的语言资源
│   ├── 密度：只保留需要的 dpi
│   └── 无用资源：lint + shrinkResources
├── 代码优化（20-40% 体积占比）
│   ├── 混淆：ProGuard / R8 压缩 + 混淆 + 优化
│   ├── 移除无用代码：shrinkResources
│   └── 枚举 → 常量
├── SO 优化（10-30% 体积占比）
│   ├── ABI 分包：App Bundle / 多 APK
│   └── SO 裁剪：只保留需要的架构
└── 动态下发（终极方案）
    ├── 动态功能模块（Dynamic Feature Module）
    ├── 插件化（VirtualAPK / Shadow）
    └── 资源云端化
```

---

### 第三层：核心知识点精讲

#### 3.1 图片压缩（最高 ROI 的优化项）

**图片在 APK 中通常占 40-60%，是第一优先级优化项。**

| 方案 | 压缩率 | 适用场景 | 工具 |
|------|--------|---------|------|
| **PNG → WebP** | 25-35% | 所有位图（Android 4.0+ 支持有损，4.3+ 支持无损） | Android Studio 右键转换 |
| **PNG 无损压缩** | 10-20% | PNG 图标、需要透明通道的图 | TinyPNG / ImageOptim |
| **矢量图（SVG → VectorDrawable）** | 极大 | 图标、简单图形、非照片 | Android Studio Vector Asset |
| **JPG 质量压缩** | 30-50% | 照片、大图背景 | Mozi / Guetzli |

**WebP vs PNG 对比（实测数据）**：

```bash
# 一张 1080x1080 的启动页背景图
PNG:  1.2 MB
WebP (有损 80%): 180 KB  → 85% 压缩
WebP (无损):     800 KB → 33% 压缩
```

**VectorDrawable 灰度问题**：
- Android 5.0 以下需要兼容库（`vectorDrawables.useSupportLibrary = true`）。
- 复杂矢量图渲染性能不及位图（路径过长），不适合超复杂图形。

#### 3.2 代码混淆与压缩

**R8 三大功能**：

```
R8 = 压缩（Shrinking）+ 混淆（Obfuscation）+ 优化（Optimization）
```

| 功能 | 原理 | 体积收益 |
|------|------|---------|
| **Shrinking** | 分析入口点，移除未使用的类/方法/字段 | 10-40% |
| **Obfuscation** | 类名/方法名缩短为 a/b/c 等 | 5-15% |
| **Optimization** | 内联、移除无副作用代码、简化逻辑 | 3-10% |

**ProGuard 关键配置**：

```proguard
# 1. 开启 R8 完整模式（gradle.properties）
android.enableR8.fullMode=true

# 2. 保留反射调用的类
-keep class com.example.model.** { *; }

# 3. 保留 Native 方法
-keepclasseswithmembernames class * {
    native <methods>;
}

# 4. 保留序列化类
-keepclassmembers class * implements android.os.Parcelable {
    public static final ** CREATOR;
}

# 5. 保留 WebView JS 接口
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}

# 6. 移除日志（Release 包）
-assumenosideeffects class android.util.Log {
    public static boolean isLoggable(java.lang.String, int);
    public static int v(...);
    public static int d(...);
    public static int i(...);
}
```

**R8 进阶技巧**：

- **`-whyareyoukeeping`**：排查为什么某个类没被移除。
- **`printusage`**：输出被移除的代码清单，用于安全审计。
- **`-optimizationpasses 5`**：指定优化轮次（R8 会自动调整）。

#### 3.3 ABI 分包策略

**问题**：一个大 SO 库（如 ffmpeg、chromium）常包含多架构版本：

```
app/libs/
├── armeabi-v7a/libnative.so   (8 MB)
├── arm64-v8a/libnative.so     (10 MB)
└── x86/libnative.so           (9 MB)
```
→ 打到一个 APK 中 = **27 MB 浪费**

**方案一：App Bundle（推荐）**

```
Android App Bundle (.aab)
  → Google Play 动态生成 Split APK
    → 用户只下载对应架构的 APK
```

Google Play 根据设备自动分发：
- 设备是 arm64-v8a → 只下发 arm64-v8a 的 SO。
- 同时按 dpi 和语言拆分资源。

**方案二：多 APK（国内应用市场）**

```groovy
// build.gradle
android {
    splits {
        abi {
            enable true
            reset()
            include 'armeabi-v7a', 'arm64-v8a'
            universalApk false  // 不生成全架构包
        }
    }
}
// 构建产物：app-armeabi-v7a-release.apk, app-arm64-v8a-release.apk
```

**方案三：运行时 SO 下载**

- APK 中只包含最小的 SO。
- 首次启动时根据 CPU 架构从服务器下载对应 SO 到 `lib/` 目录。
- 通过 `System.load()` 加载。

#### 3.4 资源优化（shrinkResources）

```groovy
// build.gradle
android {
    buildTypes {
        release {
            shrinkResources true  // 移除无用资源
            minifyEnabled true    // 必须同时开启
        }
    }
}
```

**额外资源优化**：

```groovy
android {
    defaultConfig {
        // 只保留中文和英文
        resConfigs "zh", "en"
        // 只保留 xxhdpi（系统会自动缩放）
        // 注意：ldpi/mdpi 设备会因缩放消耗更多内存
    }
}
```

---

### 第四层：工具实操演示

#### 4.1 APK 体积分析工具

**Android Studio APK Analyzer**：

```
Build → Analyze APK → 选择 APK 文件
```

可以看到：
- 各文件/目录的体积占比（raw file size + download size）
- 单个文件的详细信息
- 对比优化前后的体积变化

**Matrix APK Checker**（微信开源）：

```bash
# 命令行分析 APK 体积
java -jar matrix-apk-canary.jar --config config.json
```

输出报告包括：
- 冗余文件检测
- 未压缩文件列表
- 大文件列表
- 重复文件检测

#### 4.2 无用资源检测

```bash
# Android Lint 检测无用资源
./gradlew lint

# 输出在 app/build/reports/lint-results.html
# 查找 "UnusedResources" 分类
```

**注意**：Lint 只能检测 `R.xxx` 引用，反射获取的资源会被误报为"无用"。

#### 4.3 BundleTool 分析 App Bundle

```bash
# 安装 bundletool
brew install bundletool  # macOS

# 分析 .aab 包体积
bundletool build-apks --bundle=app.aab --output=app.apks
bundletool get-size total --apks=app.apks

# 按设备规格查看下载大小
bundletool get-size total --apks=app.apks --device-spec=device.json
```

---

### 第五层：加分扩展延伸

**1. 动态功能模块（Dynamic Feature Module）**

```
// 主 APK 按需下载功能模块
val splitInstallManager = SplitInstallManagerFactory.create(context)
val request = SplitInstallRequest.newBuilder()
    .addModule("feature_editor")   // 视频编辑模块
    .addModule("feature_ar")       // AR 模块
    .build()

splitInstallManager.startInstall(request)
```

适用场景：
- 首次启动不需要的功能（如视频编辑、AR 相机）
- 低频使用的功能（如帮助中心、用户反馈）
- 体积大的功能模块

**2. SO 裁剪与优化**

```groovy
// 1. 只保留需要的架构
ndk {
    abiFilters 'armeabi-v7a', 'arm64-v8a'
}

// 2. 去除 SO 中的符号表和调试信息
android {
    buildTypes {
        release {
            ndk {
                debugSymbolLevel 'none'  // 不打包 debug 符号
            }
        }
    }
}

// 3. 使用 android:extractNativeLibs="false"
// Android 6.0+ 支持直接从 APK 中加载未压缩的 SO
// 注意：SO 在 APK 中必须未压缩（store 模式）
```

**3. 字体文件瘦身**

```kotlin
// 如果用了自定义字体，可以使用字体子集化
// 只保留实际用到的字符（如中文只保留常用 3500 字）
// 工具：fonttools（Python）
// pyftsubset font.ttf --text-file=used_chars.txt --output-file=font_subset.ttf
```

**4. 线上包体积监控**

```yaml
# CI/CD 中集成包体积监控
# 每次 MR 自动对比 APK 体积变化
- step: Build APK
- step: Analyze APK Size
- step: Compare with Baseline
- step: Alert if Increase > 100KB
```

**5. 包体积优化效果验证**

| 优化项 | 优化前 | 优化后 | 减少 |
|--------|--------|--------|------|
| 图片转 WebP | 15 MB | 5 MB | -67% |
| 开启 R8 + shrinkResources | 12 MB | 8 MB | -33% |
| ABI 分包 | 30 MB (全架构) | 10 MB (单架构) | -67% |
| 移除无用 SO | 8 MB | 3 MB | -63% |
| 动态功能模块 | 主包 50 MB | 主包 20 MB | -60% |

**综合效果示例**：50 MB → 15 MB（-70%），国内大厂常态是控制在 15-30 MB 以内。

**6. 新一代包体积方案**：
- **Android App Bundle → Play Asset Delivery**：大型游戏资源按需下载。
- **Android 15 的 `16 KB` 页面对齐**：重新编译 SO 以适应 16KB 内存页大小。

---

### 第六层：常见误区与避坑

| 误区 | 正确做法 |
|------|---------|
| ❌ 混淆后不测试 | 反射、序列化、JNI、JS Bridge 都可能因混淆失效，必须有混淆后的全量回归测试 |
| ❌ `shrinkResources` 把所有资源删了 | 通过 `tools:keep` 保留运行时需要的资源（如 WebView 加载的本地 HTML） |
| ❌ 所有图都用矢量图 | 复杂图形 VectorDrawable 渲染比位图慢；照片类图片不应矢量化 |
| ❌ ABI 分包后不复测兼容性 | 部分 SO 可能只有 32 位版本，分包后 64 位设备找不到 SO 崩溃 |
| ❌ 压缩图片不看质量 | 过高压缩导致启动页模糊，用户感知是 Bug 而非优化 |
| ❌ 只看 APK 下载大小不看安装大小 | APK 安装后解压，实际占用空间更大（尤其是未压缩的 SO 资源） |
| ❌ 动态下发不考虑网络 | 弱网/无网时用户无法使用功能 → 主包必须包含核心流程 |

---

## 附录：性能优化面试自查清单

### 启动优化
- [ ] 能画出冷启动各阶段时间线
- [ ] 能使用 Systrace / Perfetto 定位启动瓶颈
- [ ] 能设计异步初始化框架（拓扑排序 + IdleHandler）
- [ ] 知道 TTID / TTFD 的定义和获取方式
- [ ] 了解 Jetpack Startup 和 App Startup 库

### 卡顿定位
- [ ] 能使用 Systrace 分析帧耗时和掉帧原因
- [ ] 能使用 CPU Profiler 定位热点方法
- [ ] 能检测和优化过度绘制
- [ ] 掌握 merge / ViewStub / ConstraintLayout 布局优化
- [ ] 了解线上卡顿监控方案（Choreographer / Looper Monitor）

### 内存泄漏
- [ ] 能列举 5+ 种常见泄漏场景及修复
- [ ] 理解 LeakCanary 原理（WeakReference + GC + Shark）
- [ ] 能使用 MAT 分析 hprof（Histogram / Dominator Tree / Path to GC Roots）
- [ ] 了解线上内存监控方案（KOOM）
- [ ] 知道内存抖动的概念和检测方法

### 包体积优化
- [ ] 掌握图片压缩方案（WebP / VectorDrawable / TinyPNG）
- [ ] 能配置 ProGuard / R8 的压缩混淆
- [ ] 了解 ABI 分包策略（App Bundle / splits / 运行时下载）
- [ ] 了解动态功能模块（Dynamic Feature Module）
- [ ] 能使用 APK Analyzer 定量分析包体积

---

> **一句话总结**：性能优化的核心不是"用什么工具"，而是**建立监控 → 发现瓶颈 → 定位根因 → 优化修复 → 验证效果 → 持续监控**的完整闭环。
