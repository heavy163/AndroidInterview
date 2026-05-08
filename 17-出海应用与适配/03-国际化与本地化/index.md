# 03 国际化与本地化

> 六层递进：面试高频问（多语言管理/RTL/格式化/动态下发） → 资源选择机制（Configuration Qualifiers） → Qualifier 匹配深入 → 多语言资源加载流程 → 国际化多语言管理实践(上) → 国际化多语言管理实践(下)

---

## 第一层：面试高频题（4 大核心考点）

### Q1: Android 的 strings.xml 多语言管理策略是什么？如何避免翻译遗漏和 Key 冲突？

**参考答案：**

strings.xml 是 Android 最基础也最核心的本地化载体。一个成熟的国际化 App 通常需要管理 20+ 种语言，仅靠手动维护 strings.xml 极容易出错。

#### 标准目录结构

```
res/
├── values/              ← 默认语言（通常是英语/简体中文）
│   └── strings.xml
├── values-zh-rCN/       ← 简体中文（中国大陆）
│   └── strings.xml
├── values-zh-rTW/       ← 繁体中文（台湾）
│   └── strings.xml
├── values-ja/           ← 日语
│   └── strings.xml
├── values-ko/           ← 韩语
│   └── strings.xml
├── values-ar/           ← 阿拉伯语（RTL）
│   └── strings.xml
├── values-he/           ← 希伯来语（RTL）
│   └── strings.xml
├── values-es/           ← 西班牙语
│   └── strings.xml
├── values-pt-rBR/       ← 葡萄牙语（巴西）
│   └── strings.xml
└── values-fr/           ← 法语
    └── strings.xml
```

#### 三大管理策略

**① Key 命名规范（杜绝冲突）**

```xml
<!-- ❌ 坏做法：无命名空间，极易冲突 -->
<string name="title">设置</string>
<string name="confirm">确认</string>

<!-- ✅ 最佳实践：模块_页面_元素_状态 四级命名 -->
<string name="settings_profile_title">个人资料</string>
<string name="settings_profile_edit_hint">请输入昵称</string>
<string name="checkout_payment_confirm_btn">确认支付</string>
<string name="checkout_payment_error_insufficient">余额不足</string>
```

命名规范的核心原则：**单看 Key 名就能定位到具体 UI 位置和用途**，这能极大降低翻译人员的理解成本。

**② 翻译遗漏自动检测**

```kotlin
// Gradle 插件或 CI 脚本检测方案
// 方案 A：Android Lint 内置检查
// lintOptions { check 'MissingTranslation' } 会在 CI 中断构建

// 方案 B：自定义 Python 脚本对比 key 差异
// python scripts/check_translations.py --base values/ --target values-ja/
// 输出 values-ja/strings.xml 缺失的 key 列表

// 方案 C：使用 Lokalise/Crowdin 等翻译管理平台
// 平台自动标记未翻译项，提供翻译记忆库和机器翻译建议
```

**③ 占位符与复数处理**

```xml
<!-- 带参数的字符串 — 使用位置占位符 -->
<string name="cart_item_count">购物车中有 %1$d 件商品，合计 %2$.2f 元</string>
<!-- Kotlin: getString(R.string.cart_item_count, count, total) -->

<!-- 注意：不同语言语序不同，必须使用 %1$s 而非 %s -->
<!-- 英文：%1$s liked %2$s's post -->
<!-- 日文：%2$sの投稿に%1$sがいいねしました — 主宾位置颠倒，无编号会乱 -->

<!-- 复数规则（plurals）— 避免显示"1个苹果s" -->
<plurals name="apple_count">
    <item quantity="one">%d 个苹果</item>
    <item quantity="other">%d 个苹果</item>
</plurals>
<!-- 注意：阿拉伯语有 6 种复数形式(zero/one/two/few/many/other) -->
```

---

### Q2: RTL（Right-to-Left）布局如何适配？阿拉伯语和希伯来语有哪些常见坑？

**参考答案：**

RTL 适配是国际化面试的必考题。Android 从 4.2（API 17）开始提供原生 RTL 支持，但实际项目中仍有很多细节陷阱。

#### 快速开启 RTL

```xml
<!-- AndroidManifest.xml -->
<application android:supportsRtl="true">
```

声明 `supportsRtl="true"` 后，系统会自动将所有 `left/right` 属性**镜像翻转**为 `right/left`。但前提是：你必须使用 `start/end` 而非 `left/right`。

#### 属性对照表

| ❌ 不兼容 RTL | ✅ RTL 安全替代 | 说明 |
|:---|:---|:---|
| `android:layout_marginLeft` | `android:layout_marginStart` | 外边距 |
| `android:layout_marginRight` | `android:layout_marginEnd` | 外边距 |
| `android:paddingLeft` | `android:paddingStart` | 内边距 |
| `android:paddingRight` | `android:paddingEnd` | 内边距 |
| `android:gravity="left"` | `android:gravity="start"` | 对齐 |
| `android:layout_alignParentLeft` | `android:layout_alignParentStart` | RelativeLayout 对齐 |
| `android:drawableLeft` | `android:drawableStart` | TextView 图标位置 |
| `Gravity.LEFT` | `Gravity.START` | 代码中的 Gravity |

#### 典型 RTL 陷阱与解法

**陷阱 1：图片/图标方向不应翻转**

某些图标（如播放按钮、前进箭头）在 RTL 下**不应该**镜像翻转，否则语义错误。

```xml
<!-- ❌ 前进箭头在 RTL 下自动翻转 → 变成了后退箭头 -->
<ImageView android:src="@drawable/ic_arrow_forward" />

<!-- ✅ 方案 A：使用 android:autoMirrored="false"（VectorDrawable） -->
<vector ... android:autoMirrored="false">
    <path ... />
</vector>

<!-- ✅ 方案 B：在代码中手动控制 -->
if (isRtl) {
    imageView.rotationY = 180f  // 只翻转该翻转的
}
```

**陷阱 2：HorizontalScrollView / ViewPager 起始位置**

```kotlin
// ViewPager2 在 RTL 下自动反转页面顺序
// 如果你手动 setCurrentItem(0)，在 RTL 下会显示最后一页！
// ✅ 正确做法：
viewPager.setCurrentItem(if (isRtl) items.size - 1 else 0, false)
```

**陷阱 3：自定义 View 的 Canvas 绘制**

```kotlin
override fun onDraw(canvas: Canvas) {
    // ❌ 硬编码从左绘制
    canvas.drawText(text, 0f, y, paint)
    
    // ✅ 检测布局方向
    if (layoutDirection == View.LAYOUT_DIRECTION_RTL) {
        // 从右绘制
        canvas.drawText(text, width - paint.measureText(text), y, paint)
    }
}
```

**陷阱 4：动画方向**

```kotlin
// 进入动画：LTR 从右滑入 → RTL 从左滑入
val fromX = if (isRtl) -slideDistance else slideDistance
view.translationX = fromX
view.animate().translationX(0f).start()
```

#### RTL 调试工具

```kotlin
// 开发者选项 → 强制使用从右到左布局方向
// 或者在代码中强制开启测试模式：
// adb shell settings put global debug.force_rtl 1

// 单元测试中检测 RTL
@Test
fun `text alignment should respect RTL`() {
    val config = Configuration(resources.configuration).apply {
        setLayoutDirection(Locale("ar"))
    }
    // 创建 Context with 新 config，验证 textAlignment
}
```

---

### Q3: 时区/货币/日期格式化如何处理？ICU4J 和 java.time 分别在什么场景使用？

**参考答案：**

全球化的格式化需求远不止 `SimpleDateFormat` 那么简单。Android 生态经历了几次 API 变迁，面试官通常考察候选人对不同 API 的选用理解。

#### API 选型演化

```
Java 7 时代（API < 26）
    SimpleDateFormat / DateFormat
    ↓ 已知问题：非线程安全、时区处理 Bug、不支持伊斯兰历等
    ↓
Java 8 java.time（API 26+ / desugaring）
    DateTimeFormatter / ZonedDateTime
    ↓ 线程安全、不可变、API 设计更合理
    ↓ 但：格式化能力有限（复数、相对时间、排序规则不支持）
    ↓
ICU4J（com.ibm.icu / Android 9+ 内置 icu4j 子集）
    完整的 CLDR 数据、复数规则、断行算法、Unicode 整理
```

#### 实战：各场景推荐方案

**① 日期/时间格式**

```kotlin
// ✅ Android 最佳实践：使用 java.time + 用户 Locale
val now = ZonedDateTime.now(ZoneId.of("Asia/Tokyo"))
val formatter = DateTimeFormatter
    .ofLocalizedDateTime(FormatStyle.LONG)
    .withLocale(Locale.JAPAN)
// 输出: 2026年5月8日 16:58:00 JST

// 注意：永远不要硬编码格式 "yyyy-MM-dd"
// 不同 Locale 有不同习惯：美国 MM/dd/yyyy，欧洲 dd/MM/yyyy
```

**② 货币格式**

```kotlin
// ❌ 不要直接拼接货币符号
val price = 1299.99
"¥ $price"  // 日本用户看到 ¥，但人民币也是 ¥ 符号，且小数位习惯不同

// ✅ java.text.NumberFormat.getCurrencyInstance()
val jpyFormat = NumberFormat.getCurrencyInstance(Locale.JAPAN)
jpyFormat.format(1299.99)  // ￥1,300  (日元没有小数)

val usdFormat = NumberFormat.getCurrencyInstance(Locale.US)
usdFormat.format(1299.99)  // $1,299.99

val eurFormat = NumberFormat.getCurrencyInstance(Locale.GERMANY)
eurFormat.format(1299.99)  // 1.299,99 €  (注意千位符和货币位置)
```

**③ 相对时间（ICU4J）**

```kotlin
// ICU4J 的 RelativeDateTimeFormatter 是标准库做不到的
// implementation 'com.ibm.icu:icu4j:74.2'

val rdtf = RelativeDateTimeFormatter.getInstance(ULocale.forLocale(Locale.SIMPLIFIED_CHINESE))
rdtf.format(3.0, Direction.NEXT, RelativeUnit.DAYS)   // "3天后"
rdtf.format(1.0, Direction.LAST, RelativeUnit.HOURS)   // "1小时前"
rdtf.format(0.0, Direction.PLAIN, RelativeUnit.MINUTES) // "现在"
```

**④ 复数和序数规则（ICU4J MessageFormat）**

```kotlin
// 俄语/阿拉伯语等复数规则比英语复杂得多
// ICU MessageFormat 支持 CLDR 复数规则
val pattern = """
    {count, plural, 
        =0 {没有新消息}
        one {# 条新消息}
        few {# 条新消息}
        many {# 条新消息}
        other {# 条新消息}
    }
""".trimIndent()

val msg = MessageFormat(pattern, ULocale("ru"))
msg.format(mapOf("count" to 1))   // "1 条新消息"
msg.format(mapOf("count" to 3))   // "3 条新消息"
msg.format(mapOf("count" to 21))  // "21 条新消息"
```

#### 面试加分点

- **java.time 使用 desugaring**：minSdk 21 也能用 `java.time`，不需要再等 API 26
- **避免使用 ThreeTenABP**：AGP 4.0+ 内置 desugaring 后不再需要
- **ICU4J 体积优化**：全量 ICU4J 约 10MB，Android 9+ 系统内置核心模块，低版本可按需裁剪

---

### Q4: 翻译文件如何动态下发？如何做到不发版更新多语言？

**参考答案：**

这是大厂海外 App 的标配能力——运营或翻译团队修复翻译错误、补充新语言时，不应该依赖客户端发版。

#### 方案一：基于 Firebase Remote Config 的轻量方案

```
┌──────────┐    ┌─────────────────┐    ┌────────────┐
│  运营后台  │───▶│ Firebase Remote  │───▶│  Android   │
│ 修正翻译   │    │ Config (key-val) │    │  客户端     │
└──────────┘    └─────────────────┘    └────────────┘
```

```kotlin
object DynamicStrings {
    private val fallbackStrings = mutableMapOf<String, String>()
    private val remoteStrings = ConcurrentHashMap<String, String>()
    
    fun init(context: Context) {
        // 1. 加载内置 strings.xml 作为兜底
        loadBuiltInStrings(context)
        
        // 2. 拉取 Remote Config 增量更新
        Firebase.remoteConfig.fetchAndActivate()
            .addOnSuccessListener {
                val keys = Firebase.remoteConfig.getKeysByPrefix("i18n_")
                keys.forEach { key ->
                    val stringKey = key.removePrefix("i18n_")
                    remoteStrings[stringKey] = Firebase.remoteConfig.getString(key)
                }
            }
    }
    
    fun getString(@StringRes resId: Int, vararg args: Any): String {
        val key = context.resources.getResourceEntryName(resId)
        return remoteStrings[key]?.format(*args) 
            ?: fallbackStrings[key]?.format(*args) 
            ?: context.getString(resId, *args)
    }
}
```

**优点**：接入成本低、实时下发、免费额度足够中小 App
**缺点**：KV 结构不适合大规模翻译管理、无审核流程、无法处理复数/复数形式

#### 方案二：基于 CDN + 本地缓存的专业方案

```
┌──────────┐    ┌──────────┐    ┌─────────┐    ┌──────────┐
│ 翻译管理   │───▶│  构建系统 │───▶│   CDN   │───▶│  Android  │
│ 平台修改   │    │ 打包JSON │    │ 分发文件 │    │  下载缓存  │
│ (Lokalise) │    │ 上传CDN  │    │         │    │           │
└──────────┘    └──────────┘    └─────────┘    └──────────┘
```

```kotlin
class TranslationManager(private val context: Context) {
    
    data class TranslationPack(
        val version: Int,
        val locale: String,
        val strings: Map<String, String>,    // key → 翻译文本
        val plurals: Map<String, Map<String, String>>  // key → {one: "..", other: ".."}
    )
    
    companion object {
        private const val CDN_BASE = "https://i18n-cdn.example.com/translations/"
        private const val PREFS_NAME = "i18n_prefs"
    }
    
    suspend fun sync(locale: Locale): Boolean = withContext(Dispatchers.IO) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val localVersion = prefs.getInt("version_${locale}", 0)
        
        // 1. 检查服务端最新版本号
        val metaUrl = "${CDN_BASE}${locale}/manifest.json"
        val manifest = downloadJson<Manifest>(metaUrl)
        if (manifest.version <= localVersion) return@withContext false
        
        // 2. 下载增量包（只下载变更的翻译）
        val deltaUrl = "${CDN_BASE}${locale}/delta_${localVersion}_${manifest.version}.json"
        val delta = downloadJson<TranslationPack>(deltaUrl)
        
        // 3. 合并到本地缓存
        val cacheFile = File(context.filesDir, "i18n/${locale}.json")
        mergeAndSave(cacheFile, delta)
        prefs.edit().putInt("version_${locale}", manifest.version).apply()
        
        true
    }
    
    fun getString(key: String, locale: Locale): String {
        return loadCache(locale)?.strings?.get(key)
            ?: getBuiltInString(key, locale)
    }
}
```

#### 方案三：App Bundle + 动态功能模块（Google Play）

```kotlin
// Google Play 支持按语言动态下发资源
// App Bundle 将各语言资源拆分为独立 Split APK
// 用户在 Play Store 下载时只获取设备语言的资源，后续切换语言时按需下载

// 使用 Play Core 库触发语言资源的动态加载
val manager = SplitInstallManagerFactory.create(context)
val request = SplitInstallRequest.newBuilder()
    .addLanguage(Locale.forLanguageTag("ar"))
    .build()

manager.startInstall(request)
    .addOnSuccessListener { /* 资源已安装，重启 Activity 生效 */ }
```

#### 面试关键点

| 维度 | Firebase Remote Config | CDN + 本地缓存 | Google Play Dynamic Delivery |
|:---|:---|:---|:---|
| 适用规模 | 小 (<100 keys) | 中大 (>500 keys) | 不限 |
| 更新时效 | 实时 | 分钟级 | 需走 Play Store |
| 审核流程 | 无 | 可按需加入 | Play 自带审核 |
| 离线支持 | 依赖前次 fetch 缓存 | 完善 | 依赖已下载模块 |
| 成本 | 免费额度 | CDN 费用 | 免费 |

---

## 第二层：Android 资源选择机制（Configuration Qualifiers）

### 资源的优先级匹配规则

Android 的资源系统是整个国际化能力的基石。当你在代码中写 `R.string.app_name` 时，系统根据**当前设备配置**从数十个 `values-xx` 目录中选择最优资源。

```
设备配置 = {
    语言: zh,
    地区: CN,
    屏幕密度: 480dpi,
    屏幕尺寸: 360dp × 800dp,
    方向: Portrait,
    夜间模式: No,
    ...
}
        ↓
    匹配算法（优先级从高到低）
        ↓
→ values-zh-rCN-h480dp-port/   ← 最精确匹配
→ values-zh-rCN-port/           ← 降级
→ values-zh-rCN/                ← 再降级
→ values-zh/                    ← 语言匹配
→ values/                       ← 默认兜底
```

### Qualifier 优先级表（Android 官方 20+ 种限定符）

按优先级从高到低排列（摘取常用项）：

| 优先级 | 限定符 | 示例值 | 说明 |
|:---:|:---|:---|:---|
| 1 | MCC/MNC | `mcc460-mnc01` | 移动国家代码/运营商代码 |
| 2 | 语言+地区 | `zh-rCN`, `en-rUS` | BCP 47 语言标签 |
| 3 | 布局方向 | `ldltr`, `ldrtl` | API 17+ |
| 4 | 屏幕最小宽度 | `sw360dp`, `sw600dp` | 最小宽度限定符 |
| 5 | 可用宽度 | `w720dp` | 当前可用宽度 |
| 6 | 可用高度 | `h720dp` | 当前可用高度 |
| 7 | 屏幕尺寸 | `small`, `normal`, `large`, `xlarge` | API 4+ |
| 8 | 屏幕方向 | `port`, `land` | 横竖屏 |
| 9 | UI 模式 | `car`, `desk`, `watch`, `television` | 设备类型 |
| 10 | 夜间模式 | `night`, `notnight` | API 8+ |
| 11 | 屏幕密度 | `mdpi`, `hdpi`, `xhdpi`, `xxhdpi`, `xxxhdpi`, `nodpi`, `anydpi` | 像素密度 |
| 12 | 平台版本 | `v21`, `v26`, `v31` | API Level |

### 关键规则

**规则一：非此即彼，不会合并**

```kotlin
// ❌ 常见误解：系统会先取 values-zh 的字符串，再叠加 values-land 的布局？
// 正确行为：对于 strings.xml，系统只选一个 values 目录，不会跨目录合并
// 每个资源类型独立匹配：字符串从 values-zh/ 取，布局从 layout-land/ 取
```

**规则二：最精确匹配优先，然后逐级回退**

```kotlin
// 查找优先级：
// values-mcc460-zh-rCN-ldltr-sw360dp-port-night-xhdpi-v31
//   → 找不到就从末尾逐级移除 qualifier，直到 values/ 兜底
```

**规则三：locale 的 BCP 47 注意点**

```kotlin
// 中文地区代码的正确写法
// ❌ values-zh-CN  (旧式，废弃)
// ✅ values-zh-rCN (Android 资源限定符格式)
// ✅ values-b+zh+Hans+CN (BCP 47 完整格式，API 21+)

// 注意：values-zh 会匹配所有中文用户，values-zh-rCN 只匹配中国大陆
// 如果没有 values-zh-rTW，台湾用户会 fallback 到 values-zh，再 fallback 到 values/
```

---

## 第三层：Qualifier 匹配深入 — 源码级解析

### AssetManager 的资源解析链

当调用 `context.getString(R.string.app_name)` 时，实际的调用链如下：

```
Resources.getString(int id)
    ↓
ResourcesImpl.getResourceValue(int id, TypedValue, boolean)
    ↓
AssetManager.getResourceValue(int id, int density, TypedValue, boolean)
    ↓
AssetManager.loadResourceValue(int id, short density, TypedValue, boolean)
    ↓ (native)
android_content_res_AssetManager_loadResourceValue()
    ↓
ResTable::getResource()
    ↓
ResTable::getEntry()  ← 遍历所有 ResourcePackage
    ↓
根据当前 Configuration 的 locale、density 等字段
    ↓
在编译期生成的 resources.arsc 表中二分查找最佳匹配的 entry
```

### resources.arsc 的内部结构

`resources.arsc` 是资源编译后的二进制索引表（类似符号表），结构简化如下：

```
ResourceTable {
    Package {
        id: 0x7f        // 应用包 ID（系统资源是 0x01）
        name: "com.example.app"
        
        Type {
            id: 0x01    // string type
            name: "string"
            entries: [
                Entry {
                    id: 0x0001
                    name: "app_name"
                    values: [
                        ResTable_config { locale: "zh-CN", ... } → "我的应用",
                        ResTable_config { locale: "ja", ... }    → "マイアプリ",
                        ResTable_config { locale: "default" }     → "My App"
                    ]
                },
                Entry {
                    id: 0x0002
                    name: "welcome_message"
                    values: [...]
                }
            ]
        }
    }
}
```

### Locale 匹配的具体算法

```cpp
// AOSP 源码简化版 (frameworks/base/libs/androidfw/ResourceTypes.cpp)
ssize_t ResTable::getEntry(
    const ResTable_config* requestedConfig,  // 当前设备配置
    const ResTable_type* type,
    ssize_t* outBestIndex
) {
    // 为每个可用的 config 评分，分数越高越匹配
    for (int i = 0; i < entryCount; i++) {
        ResTable_config thisConfig;
        // 获取此 entry 的 config (locale, density, orientation...)
        type->getConfig(i, &thisConfig);
        
        // 核心匹配函数：config.isBetterThan(bestConfig, requestedConfig)
        if (thisConfig.match(requestedConfig)) {
            if (thisConfig.isBetterThan(bestConfig, requestedConfig)) {
                bestConfig = thisConfig;
                bestIndex = i;
            }
        }
    }
    return bestIndex;
}

// isBetterThan() 的匹配规则（简化）:
// 1. 如果两个 config 都精确匹配 locale，选地区更精确的（zh-rCN > zh）
// 2. 如果只有一个精确匹配 locale，选精确匹配的
// 3. 如果都不精确匹配，选 locale 兼容度更高的
// 4. locale 相同的情况下，继续比较 density、orientation 等
```

### 面试要点

- `resources.arsc` 的生成发生在 **AAPT2 编译阶段**，资源 ID (`0x7f010001`) 是编译期确定的
- **同一个资源 ID 在不同语言下指向不同值** — 这就是资源系统的核心抽象
- `Resources.updateConfiguration()` 可以在运行时动态切换语言而不重启 App（需自行重建 Activity）
- `Locale.setDefault()` **不**会自动刷新已创建的 Resources 对象，必须手动重建

---

## 第四层：多语言资源加载流程 — 从资源 ID 到翻译文本的完整链路

### 完整加载时序图

```
用户视角                          Android Framework                     Native 层
──────                           ────────────────                     ────────
                                 
App 启动
  │
  ├── Activity.onCreate()
  │     │
  │     └── setContentView(layout)
  │           │
  │           └── LayoutInflater.inflate()
  │                 │
  │                 └── 解析 XML，遇到 TextView
  │                       │
  │                       ├── 读取 android:text="@string/welcome"
  │                       │     │
  │                       │     └── 解析为资源引用 0x7f010003
  │                       │
  │                       └── textView.setText(0x7f010003)
  │                             │
  │                             └── context.getString(0x7f010003)
  │                                   │
  │                                   ├── Resources.getString(id)
  │                                   │     │
  │                                   │     ├── 检查缓存（ResourcesImpl.sPreloadedDrawables 等）
  │                                   │     │
  │                                   │     └── Assets.loadResourceValue(id)
  │                                   │           │
  │                                   │           └── [JNI] Native AssetManager2
  │                                   │                 │
  │                                   │                 ├── 解包 0x7f010003
  │                                   │                 │    package=0x7f, type=0x01, entry=0x0003
  │                                   │                 │
  │                                   │                 ├── 查找 resources.arsc
  │                                   │                 │    └── Package(0x7f) → Type(string) → Entry(0x0003)
  │                                   │                 │
  │                                   │                 ├── 匹配最佳 config
  │                                   │                 │    当前设备: zh-CN, xxhdpi, port...
  │                                   │                 │    → 候选1: zh-CN → "欢迎回来"
  │                                   │                 │    → 候选2: zh    → "欢迎回来"
  │                                   │                 │    → 候选3: en    → "Welcome back"
  │                                   │                 │    → 最佳: zh-CN "欢迎回来" ✓
  │                                   │                 │
  │                                   │                 └── 返回 CharSequence "欢迎回来"
  │                                   │
  │                                   └── TextView.setText("欢迎回来")
  │
  └── 用户看到 "欢迎回来"
```

### 资源加载的性能考虑

```kotlin
// ❌ 反模式：每次调用都触发完整的 arsc 查找链
for (i in 0..1000) {
    val s = context.getString(R.string.some_key)  // 每次都查 arsc
}

// ✅ 最佳实践：Resources 内部的 TypedValue 缓存机制
// Android 对最近访问的资源有缓存，但不应完全依赖

// ✅ 对于高频访问的字符串，可以自己做 Application 级别缓存
object StringCache {
    private val cache = LruCache<Int, String>(200)
    
    fun get(context: Context, @StringRes resId: Int): String {
        return cache.get(resId) ?: run {
            context.getString(resId).also { cache.put(resId, it) }
        }
    }
}
```

### 动态切换语言的正确姿势

```kotlin
// 很多面试者只知道 Locale.setDefault()，这是不够的

class LocaleHelper {
    
    companion object {
        fun setLocale(context: Context, languageTag: String): Context {
            val locale = Locale.forLanguageTag(languageTag)
            Locale.setDefault(locale)
            
            val config = Configuration(context.resources.configuration)
            
            // API 24+ 使用 setLocales() 而非废弃的 setLocale()
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
                config.setLocales(LocaleList(locale))
            } else {
                @Suppress("DEPRECATION")
                config.locale = locale
            }
            
            // 创建新 Context，否则已加载的 Activity 不会刷新
            return context.createConfigurationContext(config)
        }
    }
}

// 使用方式（在 Activity.attachBaseContext 中拦截）
class MyActivity : AppCompatActivity() {
    override fun attachBaseContext(newBase: Context?) {
        val langPref = PreferenceManager.getDefaultSharedPreferences(newBase!!)
            .getString("app_language", "zh-CN") ?: "zh-CN"
        super.attachBaseContext(LocaleHelper.setLocale(newBase, langPref))
    }
}
```

---

## 第五层：国际化 App 的多语言管理实践（上）

### 工程化架构：从开发到交付的完整流水线

```
┌────────────┐    ┌────────────┐    ┌────────────┐    ┌────────────┐    ┌────────────┐
│  开发者提交  │───▶│   CI 检查   │───▶│ 翻译平台    │───▶│  翻译完成   │───▶│  打包/下发  │
│  strings.xml│    │ key 完整性  │    │ 自动同步    │    │ Webhook    │    │  APK/CDN   │
└────────────┘    └────────────┘    └────────────┘    └────────────┘    └────────────┘
```

#### 第一环：开发者提交规范

```xml
<!-- 开发分支只维护默认语言的 strings.xml -->
<!-- res/values/strings.xml（英语） -->
<resources>
    <!-- [模块: 登录] -->
    <string name="login_title">Sign In</string>
    <string name="login_email_hint">Email address</string>
    <string name="login_password_hint">Password</string>
    
    <!-- ⚠️ 关键：所有需要翻译的字符串必须在默认 values/ 中定义 -->
    <!-- 翻译平台从 values/ 提取源字符串，推送到各语言 -->
</resources>

<!-- 其他语言文件由翻译平台自动生成，不允许手动编辑 -->
<!-- res/values-ja/strings.xml ← 由 CI 从翻译平台拉取并覆盖 -->
```

#### 第二环：CI 检查流水线

```kotlin
// build.gradle.kts — 配置 lint 阻断未翻译项
android {
    lint {
        check += "MissingTranslation"
        check += "ExtraTranslation"
        check += "Typos" 
        // 将 MissingTranslation 设为 error → 阻断构建
        fatal("MissingTranslation")
    }
}

// CI 脚本检查示例（GitHub Actions）
// 1. 运行 lintDebug
// 2. 解析 lint-report.xml，若缺失翻译 → 阻断 PR merge
// 3. 同步到翻译平台（Lokalise CLI）
//
//   lokalise2 file upload \
//     --file res/values/strings.xml \
//     --lang-iso en \
//     --replace-modified \
//     --project-id $LOKALISE_PROJECT_ID
```

#### 第三环：翻译平台工作流

```
翻译平台（如 Lokalise / Crowdin）职责：
├── 自动提取源语言 key（从 values/strings.xml）
├── 提供翻译记忆库 (TM — Translation Memory)
│   └── 若 "login_title" 在上一个版本已翻译为 "サインイン"，
│       新版本自动匹配，不需要重复翻译
├── 机器翻译建议（Google Translate / DeepL）
├── 翻译审核流程（校对员 → 审核员 → 发布）
├── 占位符保护：%1$s 不能被破坏或遗漏
│   └── 平台自动校验占位符数量是否匹配
└── 截图上下文：为每个 key 关联 UI 截图
    └── 翻译员可以看到 "login_title" 实际显示位置
```

#### 第四环：翻译回归确认

```kotlin
// 常见的"翻译 Bug"：
// 1. 德语翻译太长，导致 TextView 被截断 → 需要伪本地化（Pseudolocalization）测试
// 2. 占位符被破坏 → 平台自动校验
// 3. RTL 语言布局错乱 → RTL 专项测试

// 伪本地化：自动生成超长/带重音字符的"翻译"，暴露 UI 硬编码问题
// 设置：开发者选项 → 伪语言区域 → English (XA) 或 عربى (XB)
// English (XA): 所有英文字符加注音调符号 [Ĥéļļô Ŵôŕļð]
// Arabic (XB): 所有字符 RTL 化，发现 left/right 硬编码
```

---

## 第六层：国际化 App 的多语言管理实践（下）— 高级主题

### 主题一：基于 App Bundle 的多语言 Split

Google Play App Bundle 会自动为每种语言生成独立的资源 Split APK。

```
Base APK (必装)
├── classes.dex
├── resources.arsc (不含语言资源)
└── AndroidManifest.xml

Split APK — strings_ja (按需下载)
├── resources.arsc (仅包含日语字符串)
└── res/values-ja/strings.xml.cpb

Split APK — strings_ar (按需下载)
├── resources.arsc (仅包含阿拉伯语字符串)
└── res/values-ar/strings.xml.cpb
```

**实际效果**：用户只需下载自己语言对应的 Split，App 体积显著减小。当用户在系统设置中切换语言时，Google Play 自动触发缺失语言 Split 的下载。

```kotlin
// 手动触发语言 Split 安装
val manager = SplitInstallManagerFactory.create(context)
val requestedLanguage = listOf(Locale.forLanguageTag("ar"))

val request = SplitInstallRequest.newBuilder()
    .addLanguage(requestedLanguage)
    .build()

val listener = SplitInstallStateUpdatedListener { state ->
    when (state.status()) {
        SplitInstallSessionStatus.DOWNLOADING -> {
            // 显示下载进度
            val progress = (state.bytesDownloaded() * 100 / state.totalBytesToDownload()).toInt()
        }
        SplitInstallSessionStatus.INSTALLED -> {
            // 重新创建 Activity 以加载新资源
            activity.recreate()
        }
        SplitInstallSessionStatus.FAILED -> {
            // 回退到默认语言
        }
    }
}
manager.registerListener(listener)
manager.startInstall(request)
```

### 主题二：服务端驱动的翻译覆盖（Server-Driven Localization）

适用于**不发版修复翻译错误**和**AB 测试不同翻译文案**的场景。

```kotlin
class TranslationOverlay(
    private val remoteTranslations: Map<String, Map<String, String>>  // key → {locale → text}
) {
    
    fun resolve(resources: Resources, resId: Int, targetLocale: Locale): String {
        val key = resources.getResourceEntryName(resId)
        
        // 优先级：服务端覆盖 > 本地资源文件 > key 名（降级）
        return remoteTranslations[key]?.get(targetLocale.toLanguageTag())
            ?: remoteTranslations[key]?.get(targetLocale.language)  // fallback 只按语言
            ?: resources.getString(resId)
    }
}

// 框架层注入 — 替换 Resources.getString() 的行为
// 可以通过自定义 ContextWrapper 拦截所有资源访问
class I18nContextWrapper(base: Context, private val overlay: TranslationOverlay) :
    ContextWrapper(base) {
    
    override fun getResources(): Resources {
        return I18nResources(super.getResources(), overlay)
    }
}

class I18nResources(
    private val delegate: Resources,
    private val overlay: TranslationOverlay
) : Resources(delegate.assets, delegate.displayMetrics, delegate.configuration) {
    
    override fun getString(id: Int): String {
        val locale = configuration.locales[0]
        return overlay.resolve(delegate, id, locale)
    }
}
```

### 主题三：时区敏感的业务设计

```kotlin
// 跨时区功能设计原则：
// ① 服务端存储统一使用 UTC 时间戳（Long）
// ② 客户端根据用户时区格式化显示
// ③ 定时任务使用 AlarmManager + 绝对时间触发

// ❌ 错误：用字符串存储时间
data class Order(val createTime: String)  // "2026-05-08 16:58:00" ← 哪个时区？

// ✅ 正确：用 Instant / 时间戳
data class Order(val createTimeMillis: Long)  // UTC 时间戳

fun formatOrderTime(utcMillis: Long, userZone: ZoneId): String {
    return Instant.ofEpochMilli(utcMillis)
        .atZone(userZone)
        .format(DateTimeFormatter.ofLocalizedDateTime(FormatStyle.MEDIUM))
}

// 活动倒计时示例：全球同时开始的活动
// 服务端下发: { "startTime": 1746691080000, "endTime": 1746694680000 }
// 客户端计算: Duration.between(Instant.now(), Instant.ofEpochMilli(startTime))
// 倒计时"还剩 2 小时 30 分"对所有时区用户都一致
```

### 主题四：本地化测试策略

```
完整的本地化测试矩阵：

┌──────────────────┬──────────┬──────────┬──────────┬──────────┐
│ 测试类型          │ 中文     │ 日语     │ 阿拉伯语  │ 英语     │
├──────────────────┼──────────┼──────────┼──────────┼──────────┤
│ UI 截断测试       │ ✓        │ ✓ ✓ ✓   │ ✓ ✓     │ ✓        │
│ (日语/德语通常更长)│           │          │          │          │
├──────────────────┼──────────┼──────────┼──────────┼──────────┤
│ RTL 布局测试      │ -        │ -        │ ✓ ✓ ✓   │ -        │
├──────────────────┼──────────┼──────────┼──────────┼──────────┤
│ 占位符完整性      │ ✓        │ ✓        │ ✓        │ ✓        │
├──────────────────┼──────────┼──────────┼──────────┼──────────┤
│ 伪本地化测试      │ ✓ ✓ ✓    │ ✓ ✓ ✓    │ ✓ ✓ ✓   │ ✓ ✓ ✓   │
├──────────────────┼──────────┼──────────┼──────────┼──────────┤
│ 时区切换测试      │ ✓        │ ✓        │ ✓        │ ✓        │
├──────────────────┼──────────┼──────────┼──────────┼──────────┤
│ 语言切换测试      │ ✓        │ ✓        │ ✓        │ ✓        │
│ (App 内切换语言)   │           │          │          │          │
└──────────────────┴──────────┴──────────┴──────────┴──────────┘

自动化方案：
- Firebase Test Lab + Robo Test → 自动截图 20+ 语言 × 10+ 页面
- Screenshot diff → 与前版本对比，发现意外布局变化
- Lint 规则 CheckInvalidPlurals / CheckInvalidFormat → 占位符校验
```

---

## 总结：面试考察层级与自检清单

| 层级 | 考察深度 | 典型问题 | 你需要掌握 |
|:---:|:---|:---|:---|
| L1 | 基础认知 | "多语言怎么做？" | strings.xml 目录结构、占位符使用、supportsRtl |
| L2 | 实践经验 | "RTL 适配遇到过什么坑？" | start/end vs left/right、图标镜像控制、ViewPager 方向 |
| L3 | API 理解 | "时区和货币用什么 API？" | java.time vs ICU4J、NumberFormat、DateTimeFormatter |
| L4 | 架构能力 | "翻译怎么动态下发？" | Remote Config 方案、CDN 增量更新、App Bundle Split |
| L5 | 工程化 | "翻译管理流水线怎么搭？" | CI 检测、Lokalise/Crowdin 集成、伪本地化测试 |
| L6 | 系统深入 | "资源匹配算法是怎样的？" | resources.arsc、AssetManager 源码、Configuration.isBetterThan |

**一句话总结**：Android 国际化不是简单的"翻译字符串"，而是一个涉及**资源系统、布局适配、格式化标准、工程流水线和运行时动态覆盖**的系统工程。面试中要展示你从"能用"到"好用"到"工程化"的完整思考链条。
