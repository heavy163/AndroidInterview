# 内存监控与压力 — 面试深度解析

---

## 一、面试高频六问：Android 内存压力体系

### Q1: onTrimMemory 的 6 个等级分别代表什么？各自触发时机和应对策略？

`onTrimMemory(int level)` 是 Android 内存压力体系的核心回调。系统通过 `ComponentCallbacks2` 接口向应用传递 **6 个内存压力等级**，分为两大类：

#### 第一类：进程运行时内存压力 (RUNNING 系列，共 4 级)

这些等级在 **应用进程在前台（或可见）时** 触发，表示系统内存不足但尚未到杀进程的地步。

| 等级 | 常量 | 数值 | 触发场景 | 应对策略 |
|------|------|:--:|----------|----------|
| ① 轻度 | `TRIM_MEMORY_RUNNING_MODERATE` | 5 | 系统内存开始紧张，但应用仍在运行 | 释放不必要的 UI 缓存（如过度绘制的 Bitmap 缓存） |
| ② 中度 | `TRIM_MEMORY_RUNNING_LOW` | 10 | 内存压力上升，设备可能开始变慢 | 释放页面级缓存、减少后台预加载队列 |
| ③ 严重 | `TRIM_MEMORY_RUNNING_CRITICAL` | 15 | 内存非常紧张，后台进程正在被回收 | 清除所有可重建的缓存（图片、数据、视图），停止非关键后台任务 |
| ④ 极端 | `TRIM_MEMORY_UI_HIDDEN` | 20 | 应用的 UI 已经不可见（切到后台） | **这是执行大规模清理的最佳时机**——释放所有 UI 资源、清理图片缓存、关闭数据库连接池 |

> **面试关键点：** `TRIM_MEMORY_UI_HIDDEN` 虽然名称不带 RUNNING，但它也属于前台进程可接收的回调——它表示"你的 UI 刚被隐藏了，现在是最佳的内存释放窗口"。面试官会追问：为什么在这个等级做清理比在 `RUNNING_CRITICAL` 更好？因为此时用户看不到 UI，释放资源不会造成视觉卡顿。

#### 第二类：后台进程内存压力 (BACKGROUND 系列，共 2 级)

这些等级在 **应用进程在后台（不可见）时** 触发，通常意味着系统正在考虑杀掉该进程。

| 等级 | 常量 | 数值 | 触发场景 | 应对策略 |
|------|------|:--:|----------|----------|
| ⑤ 后台中度 | `TRIM_MEMORY_BACKGROUND` | 40 | 进程在 LRU 列表中位置靠后，可能被回收 | 释放所有缓存、简化或关闭后台服务 |
| ⑥ 后台严重 | `TRIM_MEMORY_COMPLETE` | 80 | 进程在 LRU 列表最前端，下一个被杀的很可能就是它 | **最后的求生机会**：清空所有可重建状态，持久化关键数据，关闭所有非必要组件 |

**完整等级数值对照表：**

```
TRIM_MEMORY_RUNNING_MODERATE  = 5
TRIM_MEMORY_RUNNING_LOW       = 10
TRIM_MEMORY_RUNNING_CRITICAL  = 15
TRIM_MEMORY_UI_HIDDEN         = 20
                             ═══ 前台/后台分界线 ═══
TRIM_MEMORY_BACKGROUND        = 40
TRIM_MEMORY_COMPLETE          = 80
```

**面试追问：数值为什么不连续？**

> Android 设计时故意留有间隔（5→10→15→20 / 40→80），为未来可能的中间等级预留空间。实际上 Android N 之后确实增加了 `TRIM_MEMORY_RUNNING_CRITICAL_LOW` 等中间等级，但未在公开 API 暴露。

---

### Q2: memoryClass 和 largeHeap 的区别是什么？largeHeap 的申请条件和对 VM 的影响？

#### memoryClass — 每个应用的"标准内存配额"

```java
// 方式1：通过 ActivityManager 获取
ActivityManager am = (ActivityManager) getSystemService(Context.ACTIVITY_SERVICE);
int memoryClass = am.getMemoryClass(); // 单位：MB

// 方式2：通过 Runtime 间接验证
Runtime rt = Runtime.getRuntime();
long maxMemory = rt.maxMemory(); // 字节，约等于 memoryClass MB
```

`memoryClass` 是 Android 为每个应用分配的 **Java 堆最大内存**。值由设备总 RAM 和屏幕密度共同决定：

| 设备 RAM | 典型 memoryClass |
|----------|:---------------:|
| 512MB    | 48MB |
| 1GB      | 96MB |
| 2GB      | 128MB / 192MB |
| 4GB+     | 256MB / 384MB / 512MB |

**源码层面：** memoryClass 的值在系统启动时由 `ProcessList` 计算：

```java
// frameworks/base/services/core/java/com/android/server/am/ProcessList.java
// 根据 ro.config.low_ram 和 dalvik.vm.heapgrowthlimit 属性确定
mMemoryClass = parseHeapSize(SystemProperties.get("dalvik.vm.heapgrowthlimit", ""));
```

对应的 JVM/ART 参数是 `-XX:HeapGrowthLimit`。这个值是 **软限制**——应用堆在达到这个值之前可以自由增长；一旦达到，GC 会更激进地回收，系统也会通过 `onTrimMemory` 施加压力。

#### largeHeap — 特殊申请的高内存模式

```xml
<!-- AndroidManifest.xml -->
<application
    android:largeHeap="true"
    ... />
```

开启 `largeHeap` 后，`memoryClass` 会变为 `getLargeMemoryClass()` 的值，通常为普通配额的 **2~4 倍**：

| 设备 | memoryClass | largeMemoryClass |
|------|:----------:|:----------------:|
| 2GB RAM 手机 | 192MB | 512MB |
| 4GB RAM 手机 | 256MB | 512MB ~ 1024MB |

**底层原理：** ART 运行时读取 `largeHeap` 标记后，将 `-XX:HeapGrowthLimit` 提升为 `-XX:HeapMaxFree` 或更大值。

**面试核心观点——largeHeap 的代价：**

1. **GC 暂停时间变长：** 堆越大，Concurrent Copying GC 需要扫描和移动的对象越多。从 192MB 增加到 512MB，GC 暂停时间可能从 ~10ms 飙升至 ~50ms+。
2. **OS 级别的 LMK 压力增加：** 进程占用 RSS（物理内存）越大，`oom_score_adj` 越容易被调高，被杀概率上升。
3. **后台存活能力下降：** 大内存进程在后台 LRU 列表中权重更差，更容易被 LMK 选中回收。
4. **不能解决根本问题：** 如果内存泄漏存在，再大的堆最终也会被填满。

> **面试结论：** `largeHeap` 是"奢侈品"而非"解决方案"。适用于图库、视频编辑等确实需要大内存的场景，不应作为 OOM 的补丁。Google Play 审核会标记滥用 `largeHeap` 的应用。

**申请条件：**
- 在 `AndroidManifest.xml` 中声明 `android:largeHeap="true"`
- API Level 11+ (Android 3.0+) 支持
- 系统不保证一定分配——在低 RAM 设备上即使声明也可能受限

---

### Q3: ComponentCallbacks2 的 register 时机和场景有哪些？

`ComponentCallbacks2` 的注册是**获取内存压力回调的唯一通道**——不论你用的是 `Application`、`Activity`、`Service` 还是 `ContentProvider`，它们都间接实现了 `ComponentCallbacks2`。

#### 三种注册方式

**方式一：Application 级别注册（推荐，全局监听）**

```java
public class MyApplication extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        // Application 自动注册，无需手动 register
    }

    @Override
    public void onTrimMemory(int level) {
        super.onTrimMemory(level);
        // 全局内存压力处理
    }

    @Override
    public void onLowMemory() {
        super.onLowMemory();
        // onLowMemory 在 API 14+ 等同于 TRIM_MEMORY_COMPLETE
        // 但它是 ComponentCallbacks(不带2) 的回调，兼容老 API
    }
}
```

> **关键：** `Application` 在 `attach()` → `makeApplication()` 时，系统会调用 `context.registerComponentCallbacks(app)`，开发者无需手动注册。

**方式二：任意 Context 手动注册**

```java
public class ImageCacheManager implements ComponentCallbacks2 {

    private boolean registered = false;

    public void init(Context context) {
        // 使用 ApplicationContext 注册，避免 Activity 泄漏
        context.getApplicationContext()
               .registerComponentCallbacks(this);
        registered = true;

        // 注册时机：在需要感知内存压力的组件初始化时
        // 典型场景：图片缓存库、网络层、数据库层、WebView 池
    }

    @Override
    public void onTrimMemory(int level) {
        // 根据 level 执行降级策略
    }

    @Override
    public void onLowMemory() {
        // 兼容老版本
    }

    @Override
    public void onConfigurationChanged(Configuration newConfig) {
        // ComponentCallbacks2 还包含配置变化回调
    }

    public void destroy() {
        if (registered) {
            context.getApplicationContext()
                   .unregisterComponentCallbacks(this);
        }
    }
}
```

**方式三：Activity/Service 自动注册**

```java
public class MainActivity extends Activity {
    @Override
    public void onTrimMemory(int level) {
        super.onTrimMemory(level);
        // Activity 自动注册，当 Activity 可见时会收到 RUNNING 系列回调
        // 注意：onTrimMemory 同时包含 TRIM_MEMORY_UI_HIDDEN！
        // 此时 Activity 正在进入后台，是释放 UI 资源的最佳时机
    }
}
```

#### 注册本质：回调链的建立

```
registerComponentCallbacks(callback)
        │
        ▼
ContextImpl.registerComponentCallbacks()
        │
        ▼
mComponentCallbacks.add(callback)   // ArrayList<ComponentCallbacks>
        │
        ▼
当系统内存压力变化时：
ActivityManagerService
        │
        ▼ (Binder IPC)
ActivityThread.scheduleTrimMemory(level)
        │
        ▼
ActivityThread.handleTrimMemory(level)
        │
        ├──► Application.onTrimMemory(level)
        ├──► 遍历所有 Activity.onTrimMemory(level)
        ├──► 遍历所有 Service.onTrimMemory(level)
        └──► 遍历 ContextImpl.mComponentCallbacks → callback.onTrimMemory(level)
```

#### 面试追问：register 时机的最佳实践

| 组件 | 注册时机 | 注销时机 | 为什么 |
|------|----------|----------|--------|
| 全局缓存管理器 | Application.onCreate() | 永不注销 | 需覆盖整个应用生命周期 |
| Activity 级别缓存 | Activity.onCreate() | Activity.onDestroy() | 使用 Activity 自身的回调即可 |
| 单例图片库 (Glide/Coil) | 库初始化时 | 库 dispose 时 | 使用 ApplicationContext，避免 Activity 引用 |
| 自定义 View 内部 | onAttachedToWindow() | onDetachedFromWindow() | View 生命周期可能短于 Activity |

> **陷阱：** 若用 Activity Context 注册回调但忘记注销，回调列表会持有 Activity 引用 → **内存泄漏**。团队内最常见的泄漏之一。

---

### Q4: LMK (Low Memory Killer) 的 OOM Adj 和 score 机制是怎样的？

Low Memory Killer 是 Android 内核级的内存回收机制。当系统可用内存低于阈值时，LMK 根据 `oom_score_adj` 选择进程杀死，释放内存。

#### OOM Adj 等级体系

Android 将进程分为以下优先级（从高到低），每个等级对应一个 `oom_score_adj` 值：

```
进程优先级 (高 → 低)                     oom_score_adj    典型场景
═══════════════════════════════════════════════════════════════════
NATIVE (init/ueventd)                     -1000            系统守护进程
SYSTEM (system_server)                       -900            系统服务
PERSISTENT (Phone/SystemUI)                  -800            持久化应用
PERSISTENT_SERVICE                           -700            持久化服务
TOP_APP (前台 Activity)                         0             用户正在交互的应用
VISIBLE_APP (可见但非前台)                    100             弹窗遮盖的 Activity
PERCEPTIBLE_APP (可感知，如播放音乐)          200             前台 Service
BACKUP_APP (正在备份)                         300             备份中
HEAVY_WEIGHT_APP (重量级)                     400             未显示但未 paused
SERVICE (后台 Service)                        500             无界面的 Service
HOME_APP (Launcher)                           600             桌面
PREVIOUS_APP (上一个应用)                     700             用户刚切走的 App
SERVICE_B (B 列表 Service)                    800             老版本的 Service
CACHED_APP_MIN (缓存进程，最少使用)           900             LRU 列表头部
CACHED_APP_MAX (缓存进程，最多使用)           906             LRU 列表尾部
```

#### LMK 工作流程

```
系统可用内存下降
        │
        ▼
LMK 内核驱动检查 minfree 参数
        │
        ▼
/sys/module/lowmemorykiller/parameters/minfree
定义了 6 个可用内存阈值：
    18432, 23040, 27648, 32256, 36864, 46080 (单位：4KB 页)
    = 72MB,  90MB, 108MB, 126MB, 144MB, 180MB
        │
        ▼
当可用内存 < 某个阈值 → 杀死 oom_score_adj ≥ 对应值的进程：

minfree[0]=72MB  → 杀死 adj ≥ 0   (前台进程也会被杀！)
minfree[1]=90MB  → 杀死 adj ≥ 100 (可见进程)
minfree[2]=108MB → 杀死 adj ≥ 200 (可感知进程)
minfree[3]=126MB → 杀死 adj ≥ 500 (Service)
minfree[4]=144MB → 杀死 adj ≥ 700 (Previous App)
minfree[5]=180MB → 杀死 adj ≥ 900 (Cached App)
```

#### 每个进程的 score 如何计算？

LMK 最终杀死的是 **`oom_score` 最高**（即 `oom_score_adj` 最高）的进程。计算公式：

```
/proc/<pid>/oom_score = oom_score_adj × (total_ram_pages / 1000)
                         + (进程 RSS / 总物理页数) × 1000
```

实际内核中简化为：

```c
// drivers/staging/android/lowmemorykiller.c (Android 通用实现)
static unsigned long lowmem_oom_adj_to_oom_score_adj(int oom_adj) {
    return oom_adj * OOM_SCORE_ADJ_MAX / OOM_ADJ_MAX;
}

// 选择进程: 遍历所有进程，找到 oom_score_adj ≥ min_adj 中 oom_score 最大的
unsigned long badness = (tasksize / total_ram) * 1000 + oom_score_adj;
```

**两条核心规则：**
1. **同一 oom_score_adj 组内，RSS 越大越先被杀。** 所以 largeHeap 应用在后台更容易被选中。
2. **高 adj 的进程先于低 adj 的进程被杀。** 缓存进程（adj≥900）最先被清理。

#### 面试常见追问

**Q: 为什么同一应用的多个进程，有的被杀有的幸存？**

> Android 从 Android O 开始引入 **cgroup 内存限制**，每个进程有独立的 `memory.oom.group` 控制。另外，如果应用的多进程通过 `android:process` 声明了不同的进程优先级属性，它们的 oom_score_adj 可能不同。

**Q: 有什么方法可以提升应用的存活概率？**

```java
// 1. 使用前台 Service（提升到 adj=200）
startForeground(NOTIFICATION_ID, notification);

// 2. 使用 WorkManager 替代普通 Service（更智能的资源调度）

// 3. 降低内存占用（最根本的解决方案）
//    - 及时释放 Bitmap
//    - 避免内存泄漏
//    - 使用 LRU 缓存而非强引用持有

// 4. 监控自身 adj（调试用）
ActivityManager am = (ActivityManager) getSystemService(ACTIVITY_SERVICE);
List<RunningAppProcessInfo> processes = am.getRunningAppProcesses();
for (RunningAppProcessInfo info : processes) {
    if (info.pid == android.os.Process.myPid()) {
        Log.d("LMK", "my adj = " + info.importance); // importance ≈ adj
    }
}
```

---

### Q5: 内存压力下的降级策略具体有哪些？

这是面试的"系统设计"类问题。优秀答案需要分层次、有量化标准：

#### 降级策略分层架构

```
┌────────────────────────────────────────────────────┐
│                 内存压力降级金字塔                   │
├────────────────────────────────────────────────────┤
│                                                    │
│  TRIM_MEMORY_COMPLETE (80)                         │
│  ┌──────────────────────────────────────────────┐  │
│  │ ■ 清空所有图片缓存 (Glide/Coil dispose)      │  │
│  │ ■ 关闭 WebView 缓存池                        │  │
│  │ ■ 关闭数据库连接池 (释放 Cursor)             │  │
│  │ ■ 停止所有后台线程池 (除核心线程)             │  │
│  │ ■ 释放自定义 View 的离屏 Bitmap              │  │
│  │ ■ 清理 EventBus/RxJava 未消费事件            │  │
│  │ ■ 序列化关键状态到磁盘                       │  │
│  └──────────────────────────────────────────────┘  │
│                         ▲                          │
│  TRIM_MEMORY_BACKGROUND (40)                       │
│  ┌──────────────────────────────────────────────┐  │
│  │ ■ 清空 LruCache (内存缓存) 至 1/4            │  │
│  │ ■ 取消网络预加载队列                         │  │
│  │ ■ 释放非当前页的 ViewHolder                  │  │
│  │ ■ 减少 OkHttp 连接池大小                     │  │
│  └──────────────────────────────────────────────┘  │
│                         ▲                          │
│  TRIM_MEMORY_UI_HIDDEN (20)                        │
│  ┌──────────────────────────────────────────────┐  │
│  │ ■ RecyclerView 回收所有离屏 ViewHolder       │  │
│  │ ■ 释放 Activity/Fragment 的 DecorView 引用   │  │
│  │ ■ 关闭 Dialog 的 Window Token                │  │
│  └──────────────────────────────────────────────┘  │
│                         ▲                          │
│  TRIM_MEMORY_RUNNING_CRITICAL (15)                 │
│  ┌──────────────────────────────────────────────┐  │
│  │ ■ LruCache 缩小至 1/2                        │  │
│  │ ■ 暂停非关键动画                             │  │
│  │ ■ 减少列表预加载 item 数量                   │  │
│  └──────────────────────────────────────────────┘  │
│                         ▲                          │
│  TRIM_MEMORY_RUNNING_LOW (10)                      │
│  ┌──────────────────────────────────────────────┐  │
│  │ ■ LruCache 缩小至 3/4                        │  │
│  │ ■ 清理过期缓存项 (TTL > 5min)                │  │
│  └──────────────────────────────────────────────┘  │
│                         ▲                          │
│  TRIM_MEMORY_RUNNING_MODERATE (5)                  │
│  ┌──────────────────────────────────────────────┐  │
│  │ ■ 清理软引用/弱引用队列                       │  │
│  │ ■ 释放已关闭页面的 Bitmap 引用               │  │
│  └──────────────────────────────────────────────┘  │
│                                                    │
└────────────────────────────────────────────────────┘
```

#### 代码示例：分级降级实现

```java
public class MemoryPressureHandler implements ComponentCallbacks2 {

    private final LruCache<String, Bitmap> bitmapCache;
    private final ExecutorService backgroundExecutor;
    private final OkHttpClient httpClient;

    @Override
    public void onTrimMemory(int level) {
        switch (level) {
            case TRIM_MEMORY_RUNNING_MODERATE: // 5
                // L1: 软引用清理
                System.gc();                   // 建议 GC 清理 ReferenceQueue
                bitmapCache.trimToSize(bitmapCache.maxSize() * 9 / 10);
                break;

            case TRIM_MEMORY_RUNNING_LOW: // 10
                bitmapCache.trimToSize(bitmapCache.maxSize() * 3 / 4);
                break;

            case TRIM_MEMORY_RUNNING_CRITICAL: // 15
                bitmapCache.trimToSize(bitmapCache.maxSize() / 2);
                // 暂停非关键后台任务
                backgroundExecutor.shutdownNow();
                break;

            case TRIM_MEMORY_UI_HIDDEN: // 20
                // 最佳清理时机：UI 不可见
                bitmapCache.evictAll();
                // 清理 OkHttp 空闲连接
                httpClient.connectionPool().evictAll();
                break;

            case TRIM_MEMORY_BACKGROUND: // 40
                bitmapCache.evictAll();
                // 关闭非必要资源
                break;

            case TRIM_MEMORY_COMPLETE: // 80
                // 最后的生存机会
                bitmapCache.evictAll();
                persistCriticalState();  // 持久化
                releaseAllResources();   // 释放一切
                break;
        }
    }

    @Override
    public void onLowMemory() {
        // 等价于 TRIM_MEMORY_COMPLETE
        bitmapCache.evictAll();
    }

    @Override
    public void onConfigurationChanged(Configuration newConfig) {
        // 处理配置变化（如屏幕旋转）
    }

    private void persistCriticalState() {
        // 将关键状态写入 SharedPreferences / DataStore / 文件
    }

    private void releaseAllResources() {
        bitmapCache.evictAll();
        httpClient.connectionPool().evictAll();
        backgroundExecutor.shutdownNow();
        // 关闭数据库、释放 Cursor 等
    }
}
```

#### 降级策略的三大原则

1. **可重建性：** 释放的资源必须能无副作用地重建。例如 Bitmap 缓存清空后，下次从磁盘/网络重新加载即可。
2. **渐进性：** 不要一开始就全部释放。根据等级逐步降级，优先释放"重建成本低"的缓存（如内存缓存），最后才释放"有持久化成本"的数据（如用户草稿）。
3. **静默性：** 降级过程不应弹 Toast/Dialog——用户不知道系统正在回收内存，突然弹出提示会造成困惑。

---

## 二～三、底层监控机制：系统级内存信息获取

### ActivityManager.getMemoryInfo() — 应用视角的内存快照

```java
ActivityManager am = (ActivityManager) getSystemService(Context.ACTIVITY_SERVICE);
ActivityManager.MemoryInfo memoryInfo = new ActivityManager.MemoryInfo();
am.getMemoryInfo(memoryInfo);
```

**MemoryInfo 的核心字段：**

| 字段 | 类型 | 含义 | 典型值 (4GB RAM) |
|------|------|------|:----------------:|
| `totalMem` | long | **设备总物理内存**（字节），API 16+ | ~3.7 GB (可用部分) |
| `availMem` | long | **系统当前可用内存**（字节），包含缓存页 | 动态变化 |
| `threshold` | long | **低内存阈值**（字节），低于此值系统认为内存不足 | 约 144MB (与 minfree 相关) |
| `lowMemory` | boolean | **是否处于低内存状态**，`availMem < threshold` 时为 true | true / false |

**源码对应（框架层）：**

```java
// frameworks/base/core/java/android/app/ActivityManager.java
public void getMemoryInfo(MemoryInfo outInfo) {
    // 通过 Binder 调用 ActivityManagerService
    mService.getMemoryInfo(outInfo);
}

// frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java
public void getMemoryInfo(MemoryInfo mi) {
    // totalMem: 从 /proc/meminfo 读取 MemTotal
    mi.totalMem = MemInfoReader.getTotalSize();

    // availMem: MemAvailable (Linux 3.14+) 或 MemFree + Cached + Buffers
    mi.availMem = getService().getHostMemory().getAvailMem();

    // threshold: 从 LMK minfree 参数的最后一个值换算
    mi.threshold = ProcessList.computeThreshold();

    // lowMemory: availMem + threshold < 0 ? true : false
    mi.lowMemory = mi.availMem < mi.threshold;
}
```

**面试追问：`availMem` 为什么不等于 `freeMem`？**

> Linux 内存管理中，"可用内存" (`MemAvailable`) 不只包含 `MemFree`，还包含可以安全回收的缓存页 (Cached/Buffers)。Android 使用 `MemAvailable` 而非 `MemFree` 来判断内存压力，避免在大量缓存可回收时错误触发 LMK。

---

### LMK 的 minfree 参数 — 内核级配置

```
/sys/module/lowmemorykiller/parameters/
├── minfree      # 6 个可用内存阈值（单位：4KB 页）
├── adj          # 6 个对应的 oom_score_adj 阈值
└── debug_level  # 调试日志级别
```

**minfree 参数详解：**

```bash
# 查看当前 minfree 配置
$ cat /sys/module/lowmemorykiller/parameters/minfree
18432,23040,27648,32256,36864,46080

# 换算为 MB: 每个值 × 4KB ÷ 1024
# Page[0]: 18432 × 4KB = 72MB
# Page[1]: 23040 × 4KB = 90MB
# Page[2]: 27648 × 4KB = 108MB
# Page[3]: 32256 × 4KB = 126MB
# Page[4]: 36864 × 4KB = 144MB
# Page[5]: 46080 × 4KB = 180MB
```

**adj 参数详解：**

```bash
$ cat /sys/module/lowmemorykiller/parameters/adj
0,100,200,500,800,900
```

这两个数组是**一一对应**的：

| 索引 | minfree (页数) | minfree (MB) | adj 阈值 | 被杀进程类型 |
|:----:|:-------------:|:-----------:|:--------:|-------------|
| 0 | 18432 | 72 | ≥ 0 | 前台进程也会被杀 |
| 1 | 23040 | 90 | ≥ 100 | 可见进程 |
| 2 | 27648 | 108 | ≥ 200 | 可感知进程 |
| 3 | 32256 | 126 | ≥ 500 | 后台 Service |
| 4 | 36864 | 144 | ≥ 800 | 后台 Service (B列表) |
| 5 | 46080 | 180 | ≥ 900 | 缓存进程 |

**配置来源（Android 框架层）：**

minfree 值并非硬编码，而是由系统根据设备 RAM 大小动态计算：

```java
// frameworks/base/services/core/java/com/android/server/am/ProcessList.java
private void updateOomLevels(int displayWidth, int displayHeight, 
                              boolean write) {
    // 根据总内存 (mTotalMemMb) 和屏幕分辨率计算 minfree
    // 大内存设备 (4GB+) → 更高的 minfree 绝对值，但比例更低
    // 小内存设备 (512MB) → 更激进的回收策略
    long totalMemMb = mTotalMemMb;

    for (int i = 0; i < mOomAdj.length; i++) {
        // minfree[i] = totalMemMb * scaleFactor[i] / 100
        // 例如 CACHED_APP_MIN (adj=900) 保留总 RAM 的 ~4%
    }

    // 写入内核接口
    if (write) {
        writeFile("/sys/module/lowmemorykiller/parameters/minfree", minfreeStr);
        writeFile("/sys/module/lowmemorykiller/parameters/adj", adjStr);
    }
}
```

**实际查看当前进程的 adj 值：**

```bash
# Android 12 之前
$ cat /proc/<pid>/oom_adj        # 旧版，范围 -17 ~ 15
$ cat /proc/<pid>/oom_score_adj  # 新版，范围 -1000 ~ 1000
$ cat /proc/<pid>/oom_score      # 综合评分，越大越容易被杀

# Android 12+ (部分厂商隐藏)
$ cat /proc/<pid>/oom_score_adj  # 可能需要 root
```

---

## 四、Android 内存压力响应体系全景图

```
                          ┌─────────────────────────────────────┐
                          │         应用层 (App Process)          │
                          │                                     │
                          │  Application.onTrimMemory(level)     │
                          │  Activity.onTrimMemory(level)        │
                          │  Service.onTrimMemory(level)         │
                          │  ComponentCallbacks2.onTrimMemory()   │
                          │  ComponentCallbacks.onLowMemory()     │
                          │                                     │
                          │  ActivityManager.getMemoryInfo()     │
                          │  Runtime.getRuntime().maxMemory()    │
                          │  Debug.getNativeHeapSize()           │
                          └──────────────┬──────────────────────┘
                                         │
                              Binder IPC (跨进程调用)
                                         │
                          ┌──────────────▼──────────────────────┐
                          │      系统服务层 (System Server)       │
                          │                                     │
                          │  ActivityManagerService              │
                          │  ├── updateOomAdjLocked()            │
                          │  │   └── 计算/更新每个进程的 adj      │
                          │  ├── applyOomAdjLocked()             │
                          │  │   └── 写入 /proc/<pid>/oom_score_adj│
                          │  └── dispatchTrimMemory()            │
                          │      └── 向进程发送 TRIM_MEMORY 信号  │
                          │                                     │
                          │  ProcessList                        │
                          │  ├── updateOomLevels()               │
                          │  │   └── 计算并写入 LMK minfree/adj  │
                          │  └── computeThreshold()              │
                          │      └── 返回低内存阈值              │
                          └──────────────┬──────────────────────┘
                                         │
                              /proc 文件系统 + sysfs 接口
                                         │
                          ┌──────────────▼──────────────────────┐
                          │        Linux 内核层 (Kernel)         │
                          │                                     │
                          │  Low Memory Killer (LMK)             │
                          │  ├── drivers/staging/android/        │
                          │  │   lowmemorykiller.c               │
                          │  ├── 参数: /sys/module/              │
                          │  │   lowmemorykiller/parameters/     │
                          │  │   ├── minfree (内存阈值)          │
                          │  │   ├── adj     (adj 阈值)          │
                          │  │   └── debug_level                 │
                          │  └── 逻辑:                            │
                          │      当 availMem < minfree[i]        │
                          │      杀死 oom_score_adj ≥ adj[i]     │
                          │      中 oom_score 最高的进程         │
                          │                                     │
                          │  Android LMKD (Android 9+)           │
                          │  ├── 用户态守护进程替代内核驱动       │
                          │  ├── 使用 PSI (Pressure Stall Info)  │
                          │  ├── 更精细的杀进程决策              │
                          │  └── 支持 cgroup v2 内存控制         │
                          │                                     │
                          │  /proc/meminfo                       │
                          │  ├── MemTotal / MemFree              │
                          │  ├── MemAvailable                    │
                          │  ├── Cached / Buffers                │
                          │  └── SwapTotal / SwapFree (zram)     │
                          │                                     │
                          │  /proc/<pid>/                        │
                          │  ├── oom_score                       │
                          │  ├── oom_score_adj                   │
                          │  ├── smaps / smaps_rollup            │
                          │  └── status (VmRSS, VmSize, Threads) │
                          └─────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════

                 内存压力信号的完整传递链路:

  [内核] ──PSI事件──► [lmkd守护进程] ──socket──► [ActivityManager]
      │                                                │
      │ (内核 LMK 直接杀进程)                           │
      │                                                ▼
      │                                     updateOomAdjLocked()
      │                                          │
      │                               ┌──────────┼──────────┐
      │                               ▼          ▼          ▼
      │                          更新 /proc/  发送 TRIM   调整
      │                          oom_score   _MEMORY   进程优先级
      │                            _adj       通知
      │                               │          │
      └─────► 杀死进程 ◄──────────────┘          ▼
                                       Application.onTrimMemory()
```

---

## 五、onTrimMemory 在 ActivityThread 中的分发源码分析

### 5.1 分发入口：ActivityThread.handleTrimMemory()

```java
// frameworks/base/core/java/android/app/ActivityThread.java
@Override
public void handleTrimMemory(int level) {
    // ① 首先通过 WindowManagerGlobal 通知所有窗口
    WindowManagerGlobal.getInstance().trimMemory(level);

    // ② 遍历所有 ViewRootImpl，通知每个窗口树
    if (mActivities != null) {
        for (ActivityClientRecord r : mActivities.values()) {
            if (r.activity != null) {
                // 调用 Activity 的 onTrimMemory
                r.activity.onTrimMemory(level);
            }
        }
    }

    // ③ 如果 level >= TRIM_MEMORY_COMPLETE (80)
    //    额外触发 onLowMemory() 兼容回调
    if (level >= ComponentCallbacks2.TRIM_MEMORY_COMPLETE) {
        handleLowMemory();
    }
}
```

### 5.2 Activity.onTrimMemory() 的上层调用

```java
// frameworks/base/core/java/android/app/Activity.java
public void onTrimMemory(int level) {
    // 标记当前是否被回调过
    mCalled = true;

    // 分发到 FragmentManager
    // FragmentManager 会进一步分发到所有 Fragment.onTrimMemory()
    mFragments.dispatchTrimMemory(level);

    // Activity 自己的处理...
}
```

### 5.3 Application 的自动注册时机

```java
// frameworks/base/core/java/android/app/LoadedApk.java
public Application makeApplication(boolean forceDefaultAppClass,
        Instrumentation instrumentation) {
    // ...
    Application app = mApplicationClass.newInstance();

    // 关键：将 Application 注册到 ContextImpl 的回调列表
    ContextImpl appContext = ContextImpl.createAppContext(mActivityThread, this);
    appContext.registerComponentCallbacks(app);   // ← 自动注册！

    // 现在 Application 就能收到 onTrimMemory 了
    app.onCreate();
    return app;
}
```

### 5.4 ContextImpl 的回调分发

```java
// frameworks/base/core/java/android/app/ContextImpl.java
private final ArrayList<ComponentCallbacks> mComponentCallbacks = new ArrayList<>();

@Override
public void registerComponentCallbacks(ComponentCallbacks callback) {
    synchronized (mComponentCallbacks) {
        mComponentCallbacks.add(callback);
    }
}

// 当 ActivityThread 调过来时
void dispatchTrimMemory(int level) {
    // 拷贝一份避免 ConcurrenModificationException
    ComponentCallbacks[] callbacks;
    synchronized (mComponentCallbacks) {
        callbacks = mComponentCallbacks.toArray(
            new ComponentCallbacks[mComponentCallbacks.size()]);
    }

    for (ComponentCallbacks cb : callbacks) {
        if (cb instanceof ComponentCallbacks2) {
            ((ComponentCallbacks2) cb).onTrimMemory(level);
        }
        cb.onLowMemory();  // 同时触发 onLowMemory（保持兼容）
    }
}
```

### 5.5 触发源头：ActivityManagerService 如何决定发送 TRIM？

```java
// frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java
final boolean updateOomAdjLocked(ProcessRecord app, ...) {
    // 计算新的 oom_score_adj
    int newAdj = computeOomAdjLocked(app, ...);

    // 如果 adj 变化 → 更新 /proc/<pid>/oom_score_adj
    if (newAdj != app.curAdj) {
        applyOomAdjLocked(app, ...);
    }

    // 判断是否需要发送 TRIM_MEMORY 信号
    // 当进程从前台变为后台，或 adj 升高时
    if (app.curProcState > ActivityManager.PROCESS_STATE_TOP) {
        // 进程不在前台...
        if (app.trimMemoryLevel < ComponentCallbacks2.TRIM_MEMORY_UI_HIDDEN
                && app.curProcState >= ActivityManager.PROCESS_STATE_IMPORTANT_BACKGROUND) {
            // 进程刚变为不可见 → 发送 TRIM_MEMORY_UI_HIDDEN
            scheduleTrimMemory(app, ComponentCallbacks2.TRIM_MEMORY_UI_HIDDEN);
        }
    }

    // 根据 LRU 位置和可用内存决定更高等级的 TRIM
    if (isMemoryUnderPressure()) {
        int lruIndex = getLruIndex(app);
        if (lruIndex > CACHED_APP_THRESHOLD) {
            scheduleTrimMemory(app, ComponentCallbacks2.TRIM_MEMORY_BACKGROUND);
        }
        if (lruIndex > CRITICAL_CACHED_THRESHOLD) {
            scheduleTrimMemory(app, ComponentCallbacks2.TRIM_MEMORY_COMPLETE);
        }
    }
}

void scheduleTrimMemory(ProcessRecord app, int level) {
    if (app.thread == null) return;
    try {
        // 通过 ApplicationThread Binder 跨进程调用
        app.thread.scheduleTrimMemory(level);
        app.trimMemoryLevel = level;
    } catch (RemoteException e) {
        // 进程已死
    }
}
```

### 5.6 完整时序图

```
时间线 ──────────────────────────────────────────────────────►

[AMS]  updateOomAdjLocked()
  │
  ├── 1. computeOomAdjLocked() → 计算新的 oom_score_adj
  │
  ├── 2. applyOomAdjLocked()   → writeFile("/proc/<pid>/oom_score_adj", newAdj)
  │
  ├── 3. 判断进程状态变化
  │      if (进程从前台→后台) {
  │          scheduleTrimMemory(TRIM_MEMORY_UI_HIDDEN)  // level=20
  │      }
  │
  │      if (内存压力上升 && LRU位置靠后) {
  │          scheduleTrimMemory(TRIM_MEMORY_BACKGROUND)  // level=40
  │          scheduleTrimMemory(TRIM_MEMORY_COMPLETE)    // level=80
  │      }
  │
  └── 4. app.thread.scheduleTrimMemory(level)
          │
          │  [Binder IPC 跨进程]
          │
          ▼
[App] ActivityThread.ApplicationThread.scheduleTrimMemory(level)
  │
  └── H.sendMessage(H.TRIM_MEMORY, level)
        │
        │  [Handler 切换到主线程]
        │
        ▼
[App] ActivityThread.handleTrimMemory(level)
  │
  ├── WindowManagerGlobal.trimMemory(level)
  │     └── 遍历所有 ViewRootImpl，释放硬件加速缓存
  │
  ├── 遍历 ActivityClientRecord → activity.onTrimMemory(level)
  │     └── mFragments.dispatchTrimMemory(level)
  │           └── 遍历所有 Fragment → fragment.onTrimMemory(level)
  │
  └── ContextImpl.dispatchTrimMemory(level)
        └── 遍历 mComponentCallbacks → callback.onTrimMemory(level)
              └── Application 也在列表中
```

---

## 六、实战设计：内存感知的图片缓存系统

### 6.1 设计目标

设计一个能够**根据内存压力自动调整缓存大小**的图片缓存系统，核心需求：

- ✅ 正常状态下最大化缓存命中率
- ✅ 内存压力上升时自动缩小缓存
- ✅ 内存压力下降时（系统恢复）自动扩大缓存
- ✅ 区分前台/后台场景，后台更激进地释放
- ✅ 线程安全，不影响图片加载性能

### 6.2 核心设计

```java
/**
 * 内存感知的图片缓存 — 根据 onTrimMemory 自动调整 LruCache 大小
 */
public class MemoryAwareImageCache implements ComponentCallbacks2 {

    // ─── 缓存核心 ───
    private final LruCache<String, Bitmap> cache;
    private final DiskLruCache diskCache;  // 磁盘缓存作为后备

    // ─── 状态追踪 ───
    private volatile int currentLevel = TRIM_MEMORY_RUNNING_MODERATE;
    private volatile boolean isBackground = false;

    // ─── 三段式缓存容量（以最大堆的百分比定义） ───
    private final int maxCacheSize;        // 100% — 正常状态
    private final int criticalCacheSize;   // 50% — RUNNING_CRITICAL
    private final int backgroundCacheSize; // 25% — BACKGROUND
    private final int minimalCacheSize;    // 10% — COMPLETE

    /**
     * @param maxMemoryPercent 正常状态下缓存占最大堆的百分比 (建议 1/8)
     */
    public MemoryAwareImageCache(Context context, float maxMemoryPercent) {
        ActivityManager am = (ActivityManager) context.getSystemService(
                Context.ACTIVITY_SERVICE);

        // 获取堆限制
        int maxMemoryMb = am.getMemoryClass();  // or getLargeMemoryClass()
        long maxMemoryBytes = maxMemoryMb * 1024L * 1024L;

        // 计算各级缓存大小
        this.maxCacheSize = (int)(maxMemoryBytes * maxMemoryPercent);
        this.criticalCacheSize = maxCacheSize / 2;
        this.backgroundCacheSize = maxCacheSize / 4;
        this.minimalCacheSize = maxCacheSize / 10;

        // 初始化 LruCache
        this.cache = new LruCache<String, Bitmap>(maxCacheSize) {
            @Override
            protected int sizeOf(String key, Bitmap bitmap) {
                // API 19+ 使用 getAllocationByteCount() 获取精确大小
                return bitmap.getAllocationByteCount();
            }

            @Override
            protected void entryRemoved(boolean evicted, String key,
                                         Bitmap oldValue, Bitmap newValue) {
                if (evicted && oldValue != null && !oldValue.isRecycled()) {
                    // 可选：将淘汰的 Bitmap 降级到磁盘缓存
                    diskCache.put(key, oldValue);
                }
            }
        };

        // 注册内存压力监听
        context.getApplicationContext().registerComponentCallbacks(this);
    }

    // ─── 内存压力响应 ───

    @Override
    public void onTrimMemory(int level) {
        currentLevel = level;

        int newSize;
        switch (level) {
            case TRIM_MEMORY_RUNNING_MODERATE:  // 5
                newSize = (int)(maxCacheSize * 0.9);
                break;

            case TRIM_MEMORY_RUNNING_LOW:       // 10
                newSize = (int)(maxCacheSize * 0.75);
                break;

            case TRIM_MEMORY_RUNNING_CRITICAL:  // 15
                newSize = criticalCacheSize;
                break;

            case TRIM_MEMORY_UI_HIDDEN:         // 20
                isBackground = true;
                newSize = backgroundCacheSize;  // 激进缩减
                break;

            case TRIM_MEMORY_BACKGROUND:        // 40
                isBackground = true;
                newSize = minimalCacheSize;
                break;

            case TRIM_MEMORY_COMPLETE:          // 80
                isBackground = true;
                cache.evictAll();               // 全部清空
                return;                         // 不需要 resize

            default:
                return;
        }

        resizeCache(newSize);
    }

    @Override
    public void onLowMemory() {
        cache.evictAll();
    }

    @Override
    public void onConfigurationChanged(Configuration newConfig) {
        // 屏幕旋转等配置变化，无需特殊处理
    }

    /**
     * 当应用回到前台时调用（需在 Activity.onResume 中触发）
     * 恢复缓存到正常大小
     */
    public void onForeground() {
        isBackground = false;
        if (currentLevel <= TRIM_MEMORY_UI_HIDDEN) {
            // 内存压力已缓解 → 恢复到正常大小
            resizeCache(maxCacheSize);
            currentLevel = TRIM_MEMORY_RUNNING_MODERATE;
        }
    }

    // ─── 缓存操作 ───

    public Bitmap get(String key) {
        Bitmap bitmap = cache.get(key);
        if (bitmap == null) {
            // 内存缓存未命中 → 查磁盘缓存
            bitmap = diskCache.get(key);
            if (bitmap != null) {
                // 磁盘命中 → 重新放入内存缓存
                cache.put(key, bitmap);
            }
        }
        return bitmap;
    }

    public void put(String key, Bitmap bitmap) {
        if (bitmap == null || bitmap.isRecycled()) return;
        cache.put(key, bitmap);
        // 异步写入磁盘缓存
        diskCache.putAsync(key, bitmap);
    }

    // ─── 自适应调整 ───

    private synchronized void resizeCache(int newMaxSize) {
        int currentMax = cache.maxSize();
        if (newMaxSize == currentMax) return;

        Log.d("MemoryCache", String.format(
                "Resize: %dKB → %dKB (level=%d, bg=%b)",
                currentMax / 1024, newMaxSize / 1024, currentLevel, isBackground));

        if (newMaxSize < currentMax) {
            // 缩小：trimToSize 会触发 entryRemoved，自动淘汰多余条目
            cache.resize(newMaxSize);
        } else {
            // 扩大：直接修改 maxSize，后续 put 时自然填充
            cache.resize(newMaxSize);
            // 可选：预热缓存（从磁盘恢复热点图片）
            // warmUpFromDisk();
        }
    }

    public void destroy() {
        cache.evictAll();
        diskCache.close();
    }
}
```

### 6.3 使用示例：与 Activity 生命周期联动

```java
public class ImageGalleryActivity extends AppCompatActivity {

    private MemoryAwareImageCache imageCache;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // 全局单例缓存（在 Application 中初始化更佳）
        imageCache = ((MyApp) getApplication()).getImageCache();
    }

    @Override
    protected void onResume() {
        super.onResume();
        // 回到前台 → 恢复缓存
        imageCache.onForeground();
    }

    @Override
    public void onTrimMemory(int level) {
        super.onTrimMemory(level);
        // Activity 自身的回调也会触发，与 ImageCache 的注册形成双保险
        // 但建议使用 Application 级别的 ComponentCallbacks2，避免重复处理
    }
}
```

### 6.4 设计要点总结

| 设计点 | 方案 | 理由 |
|--------|------|------|
| 缓存容量计算 | 基于 `memoryClass × 百分比` | 适配不同设备的内存配额 |
| 分级降级 | 5 级逐步缩减，最高级清空 | 渐进式放水而非断崖式清空 |
| 前后台区分 | `UI_HIDDEN` 时大幅缩减 | 后台无需保持大缓存 |
| 垃圾桶机制 | 淘汰条目降级到磁盘缓存 | 内存释放但数据不丢失 |
| 线程安全 | `synchronized` resize + volatile 状态 | LruCache 本身线程安全，resize 需要同步 |
| 与 Glide 对比 | Glide 内置 `trimMemory()` 集成 | Glide 在 API≥14 自动注册，覆盖了本文的设计 |

> **面试加分点：** 如果你能说出 Glide/Coil 源码中 `MemorySizeCalculator` 和 `ArrayPool` 的设计，以及它们如何配合 `onTrimMemory` 动态调整，这是区分中级和高级工程师的关键差异。

---

### 6.5 进阶：如何在 Android Profiler 中验证缓存效果

```java
// 在 Application 中添加调试代码
public class MemoryDebugHelper {

    /**
     * 周期性打印当前内存状态（仅 Debug 构建）
     */
    public static void logMemoryState() {
        Runtime rt = Runtime.getRuntime();
        long usedMem = (rt.totalMemory() - rt.freeMemory()) / 1024 / 1024;
        long maxMem = rt.maxMemory() / 1024 / 1024;
        long freeMem = rt.freeMemory() / 1024 / 1024;

        ActivityManager am = (ActivityManager)
                MyApp.getInstance().getSystemService(Context.ACTIVITY_SERVICE);
        ActivityManager.MemoryInfo mi = new ActivityManager.MemoryInfo();
        am.getMemoryInfo(mi);

        Log.d("MemoryDebug", String.format(
                "App: %d/%dMB | System: %d/%dMB | LowMemory: %b | Threshold: %dMB",
                usedMem, maxMem,
                (mi.totalMem - mi.availMem) / 1024 / 1024,
                mi.totalMem / 1024 / 1024,
                mi.lowMemory,
                mi.threshold / 1024 / 1024
        ));
    }
}
```

**验证步骤：**
1. 在 Android Studio Profiler 中观察 Memory 曲线
2. 使用 `adb shell am send-trim-memory <package> RUNNING_LOW` 模拟内存压力
3. 观察缓存大小日志，验证 resize 行为
4. 使用 `adb shell dumpsys meminfo <package>` 查看 PSS/RSS

---

## 面试自检清单

| # | 问题 | 自查 |
|---|------|:--:|
| 1 | onTrimMemory 的 6 个等级名称和数值能背出来吗？ | ☐ |
| 2 | RUNNING_CRITICAL 和 BACKGROUND 的触发场景分别是什么？ | ☐ |
| 3 | memoryClass 的默认值由什么决定？largeHeap 开启后为什么更容易被杀？ | ☐ |
| 4 | 如何在代码中获取当前进程的 oom_score_adj？ | ☐ |
| 5 | LMK 的 minfree 参数格式是什么？6 个值分别对应什么进程类型？ | ☐ |
| 6 | ActivityManager.getMemoryInfo() 的 threshold 是怎么算出来的？ | ☐ |
| 7 | 为什么在 TRIM_MEMORY_UI_HIDDEN 时做清理比 RUNNING_CRITICAL 好？ | ☐ |
| 8 | 如何设计一个根据内存压力自动调整缓存大小的系统？ | ☐ |
| 9 | Android 9+ 的 lmkd 用户态守护进程与内核 LMK 有什么区别？ | ☐ |
| 10 | ComponentCallbacks2 的 register/unregister 配对不当会导致什么？ | ☐ |

---

> **延伸阅读：** Android 9+ 引入了用户态的 `lmkd` 守护进程，使用 PSI (Pressure Stall Information) 内核接口来更精准地判断内存压力。它与内核 LMK 的重大区别在于：能区分"内存回收延迟"和"真正的内存不足"，减少误杀。是面试中展示深度知识的高级话题。
