# Glide 图片加载框架 — 面试深度解析

> **目标**：掌握 Glide 核心原理，从面试高频问题出发，逐层深入源码级实现，最终覆盖自定义扩展与项目实战。

---

## 第一层：高频面试问题（5+ 道核心题）

### Q1：Glide 的四级缓存机制是怎样的？

**答案概要**：Glide 设计了四级缓存，按优先级从高到低依次为：

| 缓存级别 | 存储位置 | 特点 |
|---------|---------|------|
| **活动缓存 (ActiveResources)** | 内存 — `HashMap<Key, WeakReference<EngineResource>>` | 存放当前正在使用的图片，用弱引用防止内存泄漏；EngineResource 内部维护引用计数(acquire/release)，引用计数归零后降级到内存缓存 |
| **内存缓存 (MemoryCache)** | 内存 — `LruResourceCache`（基于 LinkedHashMap 的 LRU） | 最近最少使用淘汰策略；使用 Bitmap 自身大小的内存占用作为 LRU 权重；默认大小为每个进程可用内存的 0.4 倍（由 MemorySizeCalculator 计算） |
| **磁盘缓存 (DiskCache)** | 磁盘 — `DiskLruCacheWrapper`（基于 JakeWharton 的 DiskLruCache） | 默认 250MB；缓存原始图片(SOURCE)和变换后的图片(RESULT)；LRU 淘汰 |
| **网络/原始资源 (Source)** | 网络或本地文件系统 | 当所有缓存均未命中时，通过 HttpUrlFetcher 或对应 ModelLoader 获取原始数据 |

**典型追问**：为什么多了一层「活动缓存」？

> 活动缓存将正在使用的图片从 LruResourceCache 中移出，避免被 LRU 算法误淘汰。当 EngineResource 引用计数归零后，资源被放回 LruResourceCache，此时才进入 LRU 淘汰候选池。这一设计同时解决了"使用中图片被清除"和"内存抖动"两个问题。

---

### Q2：Glide 如何实现生命周期感知？

**答案概要**：Glide 通过在当前 Activity 中**注入一个无 UI 的 SupportRequestManagerFragment** 来感知生命周期。

核心机制：

```
Glide.with(activity)
  → RequestManagerRetriever.get(activity)
    → 查找或创建 SupportRequestManagerFragment(透明Fragment)
      → Fragment 绑定到 FM，监听 onStart/onStop/onDestroy
        → 通知 RequestManager 执行对应操作：
          onStart()  → resumeRequests()  恢复请求
          onStop()   → pauseRequests()   暂停请求（Activity 不可见时暂停，节省资源）
          onDestroy()→ clear()           取消请求并释放资源
```

**关键类关系**：

| 类 | 职责 |
|---|------|
| `RequestManagerRetriever` | 为不同上下文(Activity/Fragment/Application)创建/获取 RequestManager |
| `SupportRequestManagerFragment` | 无 UI Fragment，持有 `ActivityFragmentLifecycle`，转发生命周期事件 |
| `ActivityFragmentLifecycle` | 管理一组 LifecycleListener，事件通知中心 |
| `RequestManager` | LifecycleListener 的实现者，负责控制请求的暂停/恢复/取消 |

**拓展**：对于 Application 上下文，Glide 退化为全局单例 RequestManager，无生命周期感知，需手动管理。

---

### Q3：Glide 的 Bitmap 复用池（LruBitmapPool）是如何工作的？

**答案概要**：`LruBitmapPool` 是一个基于 LRU 策略的 Bitmap 对象池，核心目标**减少 Bitmap 的重复创建和销毁，降低 GC 压力**。

**核心原理**：

```java
// 策略接口
interface LruPoolStrategy {
    void put(Bitmap bitmap);
    Bitmap get(int width, int height, Bitmap.Config config);
    Bitmap removeLast();  // LRU 淘汰
    String logBitmap(Bitmap bitmap);
}
```

三种策略实现：

| 策略 | 适用版本 | 特点 |
|-----|---------|------|
| `SizeConfigStrategy` | API 19+ | 按尺寸 + Config 分组，内存利用更高效 |
| `AttributeStrategy` | API 11-18 | 仅按尺寸分组 |
| `SizeStrategy` | API < 11 | 简单尺寸排序 |

**复用流程**：
1. `Downsampler` 解码前调用 `BitmapPool.getDirty(w, h, config)` 尝试获取复用 Bitmap
2. 若命中，将复用的 Bitmap 传给 `BitmapFactory.Options.inBitmap`
3. 解码器直接写入复用 Bitmap 的内存，**零额外分配**
4. Bitmap 使用完毕后通过 `BitmapPool.put()` 放回池中

**面试亮点**：Bitmap 复用对解码有严格要求 — 复用对象的内存大小必须 ≥ 新图片所需大小，且 Config 必须兼容（API 19+ 放宽了 Config 约束）。

---

### Q4：Glide 的 Transformation 变换链是如何实现的？

**答案概要**：Glide 支持串联多个 Transformation，通过组合模式实现图片变换管道。

```kotlin
Glide.with(context)
    .load(url)
    .transform(CenterCrop(), RoundedCorners(16), GrayscaleTransformation())
    .into(imageView)
```

**核心类**：

| 类 | 职责 |
|---|------|
| `Transformation<T>` | 抽象基类，泛型 T 为 `Bitmap` 或 `BitmapDrawable` |
| `MultiTransformation<T>` | 组合模式，将多个 Transformation 串联为一组 |
| `BitmapTransformation` | 便利抽象类，用于 Bitmap 变换 |
| `TransformationUtils` | 提供 centerCrop、centerInside、fitCenter、rotateImage 等工具方法 |

**执行流程**：
1. `DecodeJob` 完成解码后调用 `transcode()` 获取 Bitmap
2. 遍历 Transformation 列表，依次调用 `transform(context, bitmap, width, height)`
3. 每个 transform 方法内必须调用 `pool.put()` 回收旧 Bitmap（否则内存泄漏）
4. 最终结果 Bitmap 被缓存为 `RESOURCE_DISK_CACHE_KEY`（变换后的图片可被磁盘缓存复用）

---

### Q5：Glide vs Picasso vs Fresco vs Coil 应该如何选型？

| 维度 | Glide | Picasso | Fresco | Coil |
|-----|-------|---------|--------|------|
| **包大小** | ~2.5MB | ~120KB | ~3MB | ~1.5MB |
| **内存** | RGB_565（默认），内存友好 | ARGB_8888（默认），1080P占用~8MB | 匿名共享内存(Ashmen)，彻底释放Java堆 | 默认ARGB_8888，Kotlin协程 |
| **缓存** | 四级（活动+内存+磁盘+源） | 二级（内存+磁盘） | 三级（内存+磁盘+源），可配置 | 两级（内存+磁盘） |
| **GIF** | 原生支持 | 不支持(需另配) | 原生支持 | 原生支持 |
| **生命周期** | Fragment 监听 | Activity 引用(弱) | DraweeController 管理 | Lifecycle 协程自动取消 |
| **语言** | Java | Java | Java | Kotlin |
| **最佳场景** | 综合，复杂图片加载 | 简单轻量 | 超大图/长图，需Native内存 | Kotlin/Compose 项目 |

---

## 第二层：核心原理深度解析 — Engine.load() 完整流程

### 加载入口

一切从 `Engine.load()` 启动，这是 Glide 加载引擎的核心入口方法：

```java
// 简化的 Engine.load() 流程
public <R> LoadStatus load(
    GlideContext glideContext,
    Object model,           // 图片源（URL/File/Uri等）
    Key signature,          // 签名（变化时失效缓存）
    int width, int height,  // 目标宽高
    Class<?> resourceClass,
    Class<R> transcodeClass,
    Priority priority,
    DiskCacheStrategy diskCacheStrategy,
    Map<Class<?>, Transformation<?>> transformations,
    boolean isTransformationRequired,
    boolean isScaleOnlyOrNoTransform,
    Options options,
    boolean isMemoryCacheable,
    boolean useUnlimitedSourceExecutorPool,
    boolean useAnimationPool,
    boolean onlyRetrieveFromCache,
    ResourceCallback cb,
    Executor callbackExecutor) {

    EngineKey key = keyFactory.buildKey(...); // 1. 构建缓存Key

    // 2. 检查活动缓存 (ActiveResources)
    EngineResource<?> active = loadFromActiveResources(key);
    if (active != null) {
        cb.onResourceReady(active, DataSource.MEMORY_CACHE);
        return null; // 直接返回，不走后续流程
    }

    // 3. 检查内存缓存 (LruResourceCache)
    EngineResource<?> cached = loadFromCache(key);
    if (cached != null) {
        cb.onResourceReady(cached, DataSource.MEMORY_CACHE);
        return null; // 命中也直接返回
    }

    // 4. 检查是否有正在进行的加载任务 (Jobs)
    EngineJob<?> current = jobs.get(key, onlyRetrieveFromCache);
    if (current != null) {
        current.addCallback(cb, callbackExecutor);
        return new LoadStatus(cb, current); // 合并请求，避免重复加载
    }

    // 5. 构建 EngineJob + DecodeJob，提交到线程池
    EngineJob<R> engineJob = engineJobFactory.build(...);
    DecodeJob<R> decodeJob = decodeJobFactory.build(...);
    jobs.put(key, engineJob);
    engineJob.start(decodeJob);
    return new LoadStatus(cb, engineJob);
}
```

### DecodeJob — 解码任务的核心调度器

`DecodeJob` 是 `Runnable` 的子类，负责将加载全流程编排为**有限状态机**：

**阶段一：RunReason（启动原因）**

| 值 | 含义 |
|---|------|
| `INITIALIZE` | 首次加载 |
| `SWITCH_TO_SOURCE_SERVICE` | 磁盘缓存未命中，降级到源数据 |
| `DECODE_DATA` | 磁盘命中，直接解码 |

**阶段二：Stage（解码阶段）**

| 值 | 含义 |
|---|------|
| `INITIALIZE` | 初始状态 |
| `RESOURCE_CACHE` | 尝试从磁盘读取变换后的图片 |
| `DATA_CACHE` | 尝试从磁盘读取原始数据 |
| `SOURCE` | 从网络/文件获取原始数据 |
| `ENCODE` | 将变换后的图片写入磁盘缓存 |
| `FINISHED` | 完成 |

**阶段三：DataFetcher — 获取原始数据**

```java
interface DataFetcher<T> {
    void loadData(Priority priority, DataCallback<? super T> callback);
    void cleanup();
    void cancel();
    Class<T> getDataClass();
    DataSource getDataSource();
}
```

核心实现：

| 实现类 | 数据来源 |
|-------|---------|
| `HttpUrlFetcher` | HTTP/HTTPS 网络 |
| `AssetUriFetcher` | Asset 目录 |
| `FileUriFetcher` | 本地文件 |
| `ResourceUriFetcher` | res/drawable 等资源 |
| `ByteBufferFetcher` | 字节流 |
| `InputStreamFetcher` | 输入流 |

---

## 第三层：内存缓存 LRU 实现原理 & ResourceDecoder 链

### 3.1 LruResourceCache — 手写 LRU 的实现选型

Glide 的 `LruResourceCache` 继承自 Android SDK 的 `LruCache<Key, EngineResource<?>>`：

```java
public class LruCache<T, Y> {
    private final LinkedHashMap<T, Y> cache = new LinkedHashMap<>(100, 0.75f, true);
    // 第三个参数 accessOrder=true：按访问顺序排序，最近访问的排到链表末尾

    public final Y get(T key) {
        // ...同步操作
        Y value = cache.get(key);
        if (value == null) return null;
        // 命中后更新访问记录
        return value;
    }

    protected int sizeOf(T key, Y value);  // 子类覆写，返回条目大小
    protected void entryRemoved(T key, Y oldValue, Y newValue);  // 淘汰回调

    private void trimToSize(int maxSize) {
        while (size > maxSize && !cache.isEmpty()) {
            Map.Entry<T, Y> toEvict = cache.entrySet().iterator().next(); // 最久未访问
            T key = toEvict.getKey();
            Y value = toEvict.getValue();
            cache.remove(key);
            size -= safeSizeOf(key, value);
            entryRemoved(true, key, value, null);
            evictionCount++;
        }
    }
}
```

**LinkedHashMap accessOrder 原理**：
- `accessOrder = true` 时，每次 `get()`/`put()` 都把该节点移到链表尾部
- `trimToSize()` 移除头部（最久未访问）节点
- 时间复杂度 O(1) 淘汰

**Glide 的 sizeOf 实现**：
```java
@Override
protected int sizeOf(Key key, EngineResource<?> resource) {
    // EngineResource 内部持有 Resource，Resource 返回 Bitmap 字节数
    return resource.getSize(); // ≈ width × height × (RGB_565=2 or ARGB_8888=4)
}
```

### 3.2 MemorySizeCalculator — 动态计算缓存上限

```java
class MemorySizeCalculator {
    static int getDefaultMemoryCacheSize() {
        ActivityManager am = context.getSystemService(ACTIVITY_SERVICE);
        int memoryClassBytes = am.getMemoryClass() * 1024 * 1024;
        boolean isLowMemoryDevice = am.getMemoryClass() <= 64
            || am.isLowRamDevice();

        // 默认使用40%的可用内存
        float targetMemoryCacheSize = isLowMemoryDevice ? 0.33f : 0.4f;
        return Math.round(memoryClassBytes * targetMemoryCacheSize);
    }
}
```

### 3.3 ResourceDecoder 链 — 策略模式解码

ResourceDecoder 是 Glide 将**原始数据解码为 Resource** 的核心抽象：

```java
interface ResourceDecoder<T, Z> {
    // T：原始数据类型 (InputStream, ByteBuffer, etc.)
    // Z：解码后类型 (Bitmap, GifDrawable, etc.)
    boolean handles(T source, Options options) throws IOException;
    Resource<Z> decode(T source, int width, int height, Options options) throws IOException;
}
```

**核心解码器链**：

```
InputStream → ByteBufferGifDecoder  → GifDrawable (GIF)
           → StreamBitmapDecoder    → Bitmap      (静态)
           → VideoDecoder           → Bitmap      (视频缩略帧)
           → SvgDecoder             → PictureDrawable (SVG)

ByteBuffer → ByteBufferBitmapDecoder → Bitmap
           → ByteBufferGifDecoder    → GifDrawable

ParcelFileDescriptor → FileDecoder → stream → ...（管道中转）
```

**Downsampler — 降采样核心**：

```java
// Downsampler 使用 BitmapFactory.Options 进行二次采样
BitmapFactory.Options options = new BitmapFactory.Options();
options.inJustDecodeBounds = true;   // 第一阶段：只读尺寸
BitmapFactory.decodeStream(input, null, options);

// 计算 sampleSize（总是2的幂次，向下取）
options.inSampleSize = calculateSampleSize(
    options.outWidth, options.outHeight, targetWidth, targetHeight);

options.inJustDecodeBounds = false;  // 第二阶段：实际解码
options.inBitmap = pool.getDirty(...);  // 尝试复用 Bitmap（关键优化！）
return BitmapFactory.decodeStream(input, null, options);
```

**Registry — 解码器注册中心**：

```java
// Glide 初始化时注册所有解码器
registry
    .append(InputStream.class, Bitmap.class, new StreamBitmapDecoder(downsampler))
    .append(InputStream.class, GifDrawable.class, new ByteBufferGifDecoder(...))
    .append(ByteBuffer.class, Bitmap.class, new ByteBufferBitmapDecoder(downsampler))
    .append(ParcelFileDescriptor.class, Bitmap.class, new VideoBitmapDecoder())
    .append(InputStream.class, SvgDrawable.class, new SvgDecoder())
    ...;
```

---

## 第四层：Glide 加载完整流程图

```
                    ┌─────────────────────────────────────┐
                    │          Glide.with(context)         │
                    │     创建/复用 RequestManager         │
                    └─────────────┬───────────────────────┘
                                  │
                                  ▼
                    ┌─────────────────────────────────────┐
                    │       RequestBuilder.load(url)       │
                    │      配置 URL、占位图、变换等         │
                    └─────────────┬───────────────────────┘
                                  │
                                  ▼
                    ┌─────────────────────────────────────┐
                    │          into(imageView)             │
                    │      触发目标视图绑定                │
                    └─────────────┬───────────────────────┘
                                  │
                                ╔═▼═════════════════════════╗
                                ║    Engine.load(key)       ║
                                ╚═╤═════════════════════════╝
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
          ┌───────────┐   ┌───────────┐   ┌───────────┐
          │ 活动缓存   │   │ 内存LRU   │   │ 正在Job?  │
          │ ActiveRes │   │ LruCache  │   │ Jobs合并  │
          └──┬───┬────┘   └──┬───┬────┘   └──┬───┬────┘
         命中│   │未命中   命中│   │未命中  命中│   │未命中
            │   │            │   │            │   │
         ◄──┘   └──►         ◄┘   └──►         ◄┘   │
                                                    │
                        ┌───────────────────────────▼──────┐
                        │       DecodeJob.run()             │
                        │   ┌───────────────────────────┐  │
                        │   │ Stage.RESOURCE_CACHE       │  │
                        │   │ 磁盘 → 变换后图片          │  │
                        │   └─────────┬─────────────────┘  │
                        │             │ 未命中              │
                        │   ┌─────────▼─────────────────┐  │
                        │   │ Stage.DATA_CACHE           │  │
                        │   │ 磁盘 → 原始数据            │  │
                        │   └─────────┬─────────────────┘  │
                        │             │ 未命中              │
                        │   ┌─────────▼─────────────────┐  │
                        │   │ Stage.SOURCE               │  │
                        │   │ ModelLoader → DataFetcher  │  │
                        │   │ (网络/文件/资源)            │  │
                        │   └─────────┬─────────────────┘  │
                        │             │ 获取到 InputStream  │
                        │   ┌─────────▼─────────────────┐  │
                        │   │ ResourceDecoder 链         │  │
                        │   │ StreamBitmapDecoder/       │  │
                        │   │ GifDecoder/Downsampler     │  │
                        │   └─────────┬─────────────────┘  │
                        │             │ Bitmap              │
                        │   ┌─────────▼─────────────────┐  │
                        │   │ Transformation 链           │  │
                        │   │ CenterCrop/CircleCrop/...  │  │
                        │   └─────────┬─────────────────┘  │
                        │             │ 变换后 Bitmap       │
                        │   ┌─────────▼─────────────────┐  │
                        │   │ Stage.ENCODE               │  │
                        │   │ 写入磁盘缓存 (RESULT)       │  │
                        │   └───────────────────────────┘  │
                        └────────────────┬─────────────────┘
                                         │
                                         ▼
                              ┌──────────────────────┐
                              │ EngineJob.onComplete  │
                              │ 回调 → UI线程         │
                              └──────────┬───────────┘
                                         │
                                         ▼
                              ┌──────────────────────┐
                              │ Target(Drawable)      │
                              │ 显示到 ImageView      │
                              └──────────────────────┘
```

**关键路径总结**：

| 命中层级 | 耗时 | 发生概率 |
|---------|----|--------|
| 活动缓存 | ~0ms | 10-20%（同一页面反复使用） |
| 内存缓存 | ~1-5ms | 20-40%（近期访问过） |
| 磁盘缓存(已变换) | ~10-50ms | 15-30%（曾用相同变换加载） |
| 磁盘缓存(原始) | ~20-100ms | 10-20%（换变换但同源） |
| 网络/源文件 | ~100-3000ms | 5-10%（首次加载或缓存过期） |

---

## 第五层：自定义 GlideModule

### 5.1 GlideModule 的作用

`GlideModule` 是 Glide 的插件化扩展点，允许开发者在不修改框架源码的前提下：

- 替换默认组件（网络层、缓存、编解码器等）
- 注册新的 ModelLoader / ResourceDecoder
- 配置全局默认参数

### 5.2 实现 AppGlideModule

```kotlin
// 1. 添加 kapt 依赖
// kapt 'com.github.bumptech.glide:compiler:4.16.0'

@GlideModule
class MyGlideModule : AppGlideModule() {

    override fun applyOptions(context: Context, builder: GlideBuilder) {
        // 自定义缓存上限
        builder.setMemoryCache(LruResourceCache(128 * 1024 * 1024L)) // 128MB

        // 自定义磁盘缓存
        builder.setDiskCache(
            InternalCacheDiskCacheFactory(context, "my_glide_cache", 500L * 1024 * 1024)
        )

        // 自定义 Bitmap 池
        builder.setBitmapPool(LruBitmapPool(64 * 1024 * 1024L))

        // 自定义线程池
        builder.setSourceExecutor(GlideExecutor.newSourceExecutor(4))
        builder.setDiskCacheExecutor(GlideExecutor.newDiskCacheExecutor(2))

        // 全局默认请求选项
        builder.setDefaultRequestOptions(
            RequestOptions()
                .format(DecodeFormat.PREFER_RGB_565)   // 内存减半
                .disallowHardwareConfig()               // 关闭硬件位图（某些场景兼容性）
                .timeout(30_000)                        // 超时30s
        )

        // 自定义日志级别
        builder.setLogLevel(Log.DEBUG)
        builder.setLogRequestOrigins(true) // 记录调用堆栈
    }

    override fun registerComponents(context: Context, glide: Glide, registry: Registry) {
        // 注册自定义 ModelLoader（例如：从自定义协议加载）
        registry.prepend(
            MyCustomUrl.class,
            InputStream.class,
            MyCustomModelLoader.Factory()
        )

        // 注册自定义解码器
        registry.prepend(
            InputStream.class,
            MyCustomDrawable.class,
            MyCustomDecoder()
        )

        // 替换网络层（例如使用 OkHttp 替代 HttpURLConnection）
        registry.replace(
            GlideUrl::class.java,
            InputStream::class.java,
            OkHttpUrlLoader.Factory(okHttpClient)
        )
    }

    // 禁用清单解析（提升启动性能）
    override fun isManifestParsingEnabled(): Boolean = false
}
```

### 5.3 编译时注解生成

标注 `@GlideModule` 后，Glide 注解处理器自动生成：

- `GlideApp` 类（继承 Glide，具备流式API）
- `GlideRequests` 类（预配置的 RequestManager）
- `GlideOptions` 类（预配置的 RequestOptions，可链式调用）

```kotlin
// 编译后使用 GlideApp 替代 Glide
GlideApp.with(context)
    .load(url)
    .placeholder(R.drawable.placeholder)
    .circleCrop()
    .override(600, 600)
    .into(imageView)
```

---

## 第六层：自定义图片变换（Transformation）

### 6.1 实现 BitmapTransformation

```kotlin
class BlurTransformation(private val radius: Int = 25) : BitmapTransformation() {

    override fun transform(
        pool: BitmapPool,
        toTransform: Bitmap,
        outWidth: Int,
        outHeight: Int
    ): Bitmap {
        // 1. 从池中获取目标 Bitmap（复用！）
        val result = pool.get(outWidth, outHeight, Bitmap.Config.ARGB_8888)

        // 2. 创建 Canvas 绑定
        val canvas = Canvas(result)
        val paint = Paint(Paint.FILTER_BITMAP_FLAG)

        // 3. 缩放并居中绘制
        val scale = max(
            outWidth.toFloat() / toTransform.width,
            outHeight.toFloat() / toTransform.height
        )
        val scaledW = (toTransform.width * scale).toInt()
        val scaledH = (toTransform.height * scale).toInt()
        val dx = (outWidth - scaledW) / 2f
        val dy = (outHeight - scaledH) / 2f

        // 4. 应用模糊（使用 RenderScript 或自定义算法）
        val scaled = Bitmap.createScaledBitmap(toTransform, scaledW, scaledH, true)
        val blurred = applyBlur(scaled, radius)
        canvas.drawBitmap(blurred, dx, dy, paint)

        // 5. 清理临时对象
        if (scaled != toTransform && !pool.put(scaled)) {
            scaled.recycle()
        }
        if (blurred != result && !pool.put(blurred)) {
            blurred.recycle()
        }

        return result
    }

    private fun applyBlur(bitmap: Bitmap, radius: Int): Bitmap {
        // RenderScript 模糊（API 17-31）或 ToolKit.blur() 回退
        if (Build.VERSION.SDK_INT < 31) {
            return try {
                val rs = RenderScript.create(RuntimeEnvironment.application)
                val input = Allocation.createFromBitmap(rs, bitmap)
                val output = Allocation.createTyped(rs, input.type)
                val script = ScriptIntrinsicBlur.create(rs, Element.U8_4(rs))
                script.setRadius(radius.toFloat())
                script.setInput(input)
                script.forEach(output)
                output.copyTo(bitmap)
                rs.destroy()
                bitmap
            } catch (e: Exception) {
                bitmapStackBlur(bitmap, radius) // 纯 Java 回退算法
                bitmap
            }
        } else {
            // Android 12+：使用 RenderEffect
            bitmapStackBlur(bitmap, radius)
            bitmap
        }
    }

    override fun updateDiskCacheKey(messageDigest: MessageDigest) {
        messageDigest.update("blur_$radius".toByteArray(StandardCharsets.UTF_8))
    }

    companion object {
        // 快速堆栈模糊算法（Java纯实现，Mario Klingemann 发明）
        private fun bitmapStackBlur(sentBitmap: Bitmap, radius: Int) {
            // ... 像素级卷积模糊实现（略，约200行代码）
        }
    }
}
```

### 6.2 组合变换 — 圆角 + 模糊 + 灰度

```kotlin
Glide.with(context)
    .load(imageUrl)
    .transform(
        MultiTransformation(
            BlurTransformation(20),        // 高斯模糊
            RoundedCorners(24),            // 24dp 圆角
            GrayscaleTransformation(),     // 灰度
            CenterCrop()                   // 居中裁剪
        )
    )
    .into(imageView)
```

**注意**：变换顺序影响最终效果。`CenterCrop` 通常放在前面先裁剪，再做艺术效果变换。

### 6.3 磁盘缓存 Key 的重要性

每个自定义 Transformation 必须正确实现 `updateDiskCacheKey()`：

```kotlin
// ❌ 错误：未覆写，可能导致不同参数使用相同缓存
class BadTransform(private val level: Int) : BitmapTransformation() {
    // 未覆写 updateDiskCacheKey → 所有实例返回相同 key → 缓存错乱！
}

// ✅ 正确：将所有影响输出的参数写入 Key
class GoodTransform(private val level: Int) : BitmapTransformation() {
    override fun updateDiskCacheKey(digest: MessageDigest) {
        digest.update("GoodTransform_$level".toByteArray())
    }

    override fun equals(other: Any?): Boolean {
        return other is GoodTransform && other.level == this.level
    }

    override fun hashCode(): Int = "GoodTransform_$level".hashCode()
}
```

### 6.4 实战：超大图加载与 SubSamplingScaleImageView 集成

对于超大图（如 5000×8000），标准 Downsampler 仍可能 OOM，可使用分块加载方案：

```kotlin
class BigImageTransformation : BitmapTransformation() {
    override fun transform(
        pool: BitmapPool, toTransform: Bitmap, outWidth: Int, outHeight: Int
    ): Bitmap {
        // 分块区域解码
        val regionDecoder = BitmapRegionDecoder.newInstance(
            /* InputStream */, false
        )
        val options = BitmapFactory.Options()
        options.inPreferredConfig = Bitmap.Config.RGB_565
        options.inBitmap = pool.get(outWidth, outHeight, Bitmap.Config.RGB_565)

        regionDecoder.decodeRegion(
            Rect(0, 0, outWidth, outHeight), options
        )
        regionDecoder.recycle()
        return options.inBitmap!!
    }

    override fun updateDiskCacheKey(digest: MessageDigest) {
        digest.update("bigImage".toByteArray())
    }
}
```

---

## 附录：Glide 关键类速查表

| 包/类 | 层级 | 职责 |
|-------|-----|------|
| `Glide` | 入口 | 单例，全局配置持有者 |
| `RequestManager` | 请求管理 | 绑定生命周期，管理请求队列 |
| `RequestBuilder` | 请求构建 | 流式 API，配置加载参数 |
| `Engine` | 加载引擎 | 四级缓存调度，Job 合并 |
| `DecodeJob` | 解码调度 | 状态机，编排加载→解码→变换→缓存 |
| `EngineJob` | 任务调度 | 管理加载状态，回调分发 |
| `Registry` | 注册中心 | 组件注册表（ModelLoader/Decoder/Encoder） |
| `ModelLoader` | 数据源 | 将 Model(URL/File) 转换为 Data(InputStream) |
| `DataFetcher` | 数据获取 | 实际获取数据的 IO 操作 |
| `ResourceDecoder` | 解码器 | 将数据解码为 Resource(Bitmap/Drawable) |
| `Transformation` | 变换 | 对解码后的 Bitmap 二次处理 |
| `ResourceEncoder` | 编码器 | 将 Resource 编码写入磁盘缓存 |
| `MemorySizeCalculator` | 工具 | 根据设备内存计算缓存池大小 |
| `LruResourceCache` | 内存缓存 | 基于 LinkedHashMap 的 LRU 缓存 |
| `LruBitmapPool` | Bitmap 池 | Bitmap 对象池，减少重复分配 |
| `BitmapPreFillRunner` | 预填充 | 后台预分配 Bitmap 填充池 |
| `ActiveResources` | 活动缓存 | 弱引用+引用计数，防止使用中资源被回收 |

---

## 总结：面试回答模板

当被问到"说说你对 Glide 的理解"，可按以下结构回答：

```
1. 【总述】Glide 是 Google 推荐的 Android 图片加载库，核心优势在于四级缓存、
      生命周期感知和高效的 Bitmap 复用机制。

2. 【缓存】四级缓存：活动缓存(弱引用+引用计数)→内存LRU→磁盘(原始+变换后)→网络。
      活动缓存解决了使用中资源被 LRU 误淘汰的问题。

3. 【生命周期】通过注入透明 Fragment 监听 Activity 生命周期，
      自动暂停/恢复/取消图片请求，避免内存泄漏。

4. 【解码优化】Downsampler 二次采样 + BitmapPool 复用，
      结合 RGB_565 配置可将内存占用减少 50% 以上。

5. 【扩展性】通过 AppGlideModule 可替换网络层(OkHttp)、注册自定义解码器、
      自定义 Transformation 实现圆角/模糊等效果。
```

---

> **参考资料**：[Glide 官方文档](https://bumptech.github.io/glide/) | [源码仓库](https://github.com/bumptech/glide) | [Glide v4 中文教程](https://muyangmin.github.io/glide-docs-cn/)
