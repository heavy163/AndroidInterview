# 02 厂商兼容性

> **面试权重：★★★★☆** | 出海应用必问，覆盖华为 HMS / GMS 双框架、各厂商 ROM 差异适配、后台限制与保活策略

---

## 一、面试核心考点速查

### 1.1 华为 HMS vs Google GMS 双框架适配

#### 问题 1：为什么要做 HMS + GMS 双框架？分别解决什么问题？

**标准回答：**

| 框架 | 覆盖市场 | 核心服务 | 限制 |
|------|---------|---------|------|
| **GMS** (Google Mobile Services) | 海外全球市场（除中国大陆） | 推送(FCM)、地图(Google Maps)、登录(Google Sign-In)、定位(FusedLocation)、支付(Google Pay) | 中国大陆不可用（Google 服务被墙） |
| **HMS** (Huawei Mobile Services) | 中国大陆华为设备 + 受制裁市场 | 推送(HMS Push Kit)、地图(Map Kit)、登录(Account Kit)、定位(Location Kit)、支付(IAP Kit) | 非华为设备需要安装 HMS Core |

**核心认知：** 出海应用面临"国内市场用不了 GMS、海外华为新机用不了 GMS（受美国制裁）"的双重困境。双框架的本质是**运行时动态选择服务提供商**，让同一份代码覆盖所有设备。

---

#### 问题 2：推送服务双框架如何设计？FCM 和 HMS Push 的差异是什么？

| 对比维度 | FCM (Firebase Cloud Messaging) | HMS Push Kit |
|----------|-------------------------------|--------------|
| **服务可用性** | 需要 Google Play Services | 需要 HMS Core (≥ 4.0) |
| **Token 获取** | `FirebaseMessaging.getInstance().getToken()` | `HmsInstanceId.getInstance().getToken()` |
| **消息格式** | JSON Payload (data/notification) | 类似结构，额外支持华为自定义字段 |
| **到达率保障** | Google Play Services 系统级长连接 | HMS Core 系统级长连接（华为设备） |
| **透传消息** | `RemoteMessage.data` | `RemoteMessage.data`（同名 API） |
| **通知栏点击** | 系统自动处理或自定义 Intent | 需主动调用 `HmsMessageService.onMessageReceived()` |

**关键差异：**

1. **华为设备上 HMS Push 优先级更高**——EMUI/HarmonyOS 对 HMS Core 有白名单保护，FCM 在华为设备上常被杀死
2. **Token 生命周期不同**——HMS Token 在 App 卸载重装后会变化，需要服务端及时更新
3. **角标支持**——华为提供 `BadgeManager` 设置桌面角标，而原生 Android 无统一角标 API

---

#### 问题 3：地图服务如何做双框架切换？HMS Map Kit 和 Google Maps 的 API 差异大吗？

**核心策略：抽象接口 + 工厂模式**

```
MapProvider (Interface)
├── GoogleMapProvider (implements MapProvider)
│   └── 封装 com.google.android.gms.maps.*
└── HuaweiMapProvider (implements MapProvider)
    └── 封装 com.huawei.hms.maps.*
```

**API 对照表：**

| 功能 | Google Maps SDK | HMS Map Kit | 差异程度 |
|------|----------------|-------------|----------|
| 地图显示 | `MapView` / `SupportMapFragment` | `MapView` / `SupportMapFragment` | ★ 同名同类 |
| 标记点 | `MarkerOptions` / `addMarker()` | `MarkerOptions` / `addMarker()` | ★ 几乎一致 |
| 定位蓝点 | `setMyLocationEnabled()` | `setMyLocationEnabled()` | ★ 一致 |
| 相机移动 | `CameraUpdateFactory` | `CameraUpdateFactory` | ★ 一致 |
| 多边形/路线 | `Polyline` / `Polygon` | `Polyline` / `Polygon` | ★ 一致 |
| 地址逆解析 | `Geocoder` (需 GMS) | 需接入 Site Kit | ★★★ 不同 |
| 地图样式 | JSON 样式字符串 | JSON 样式字符串 | ★ 一致 |

**核心认知：** HMS Map Kit 刻意保持与 Google Maps API 命名一致，绝大部分场景**只需改 import 路径**即可切换。MapView/MapFragment 的使用方式完全一致，这大大降低了适配成本。

---

#### 问题 4：登录服务如何适配？

| 功能 | GMS 方案 | HMS 方案 | 适配策略 |
|------|---------|---------|---------|
| 一键登录 | Google Sign-In (`GoogleSignInClient`) | Huawei Account Kit (`HuaweiIdAuthService`) | 各自 SDK，接口不同 |
| 获取用户信息 | `GoogleSignInAccount` | `AuthHuaweiId` | 统一转为内部 UserInfo 模型 |
| Token 刷新 | 自动静默刷新 | `silentSignIn()` | 服务端统一 Token 校验 |

**适配要点：** 服务端不直接依赖 Google/Huawei Token，而是建立自己的用户体系——前端拿到三方 Token 后换取服务端自有 Session Token。这样无论用户在哪个平台登录，后端统一处理。

---

### 1.2 厂商后台限制与保活策略

#### 问题 5：华为、小米、OPPO、Vivo 的后台限制机制有什么区别？

**OOM Adj 与进程优先级体系：**

| 进程类别 | oom_adj 值 | 典型场景 | 被杀优先级 |
|----------|-----------|---------|:----------:|
| 前台进程 (FOREGROUND) | 0 | 正在交互的 Activity / 前台 Service 且显示通知 | 最低 |
| 可见进程 (VISIBLE) | 1~3 | 可见但不可交互（如被对话框遮挡） | 低 |
| 服务进程 (SERVICE) | 4~6 | 后台 Service | 中 |
| 缓存进程 (CACHED) | 9~15 | 不可见 Activity、空进程 | 最高（最先被杀） |

**四大厂商的差异化策略：**

| 厂商 | 后台限制策略 | 自名单机制 | OOM Adj 调整 | 保活难度 |
|:---:|-------------|-----------|:-----------:|:------:|
| **华为** (EMUI/HarmonyOS) | 最严格。锁屏后 1 分钟内冻结后台进程（冷冻机制）、杀死 wakelock | 手动添加"受保护应用"、关联启动权限 | 前台 Service 可能被降级到 CACHED | ★★★★★ |
| **小米** (MIUI/HyperOS) | 神隐模式：非前台 App 禁止网络定位，严格限制后台自启 | 自启动管理、省电策略→无限制 | `ro.HOME_APP_ADJ=1` 桌面保活级别高 | ★★★★☆ |
| **OPPO** (ColorOS) | 后台冻结（5 分钟后冻结 CPU）、智能省电 | 允许后台运行、允许自启动、关联启动 | 后台 Service 会被 moveTaskToBack 降 Adj | ★★★☆☆ |
| **Vivo** (OriginOS) | iManager 电量管理，第三方 App 默认禁止后台运行 | 后台高耗电→允许继续运行、自启动 | 非白名单 App 后台 Service 直接强制停止 | ★★★★☆ |

**面试加分点——华为冷冻机制详解：**

华为的"冷冻机制"不是简单的杀进程，而是：
1. **CPU 冻结**：进程进入 freezer cgroup，所有线程被挂起（SIGSTOP 等效）
2. **网络冻结**：冻结网络套接字，所有 TCP 连接被断开或暂停
3. **Wakelock 剥夺**：持有的 wakelock 被系统强制释放
4. 当 App 回到前台时，进程解冻恢复执行（不是重启），但网络连接已断开需要重连

**合规保活方案（面试标准答案）：**

> 不要投机取巧用 1px Activity、双进程守护、播放无声音乐等灰色保活手段，Android 每个版本都在收紧限制。正确的做法是：

1. **前台 Service + 常驻通知**：合法的唯一保活方案（`startForeground()`）
2. **FCM/HMS 高优先级推送**：利用系统级长连接唤醒 App
3. **WorkManager 兜底**：非实时任务用 WorkManager 的 `setExpedited()` 获取短期前台执行权
4. **厂商白名单引导**：引导用户将 App 加入"受保护应用"列表
5. **华为/小米/OPPO/Vivo 的厂商推送通道**：走系统通道保证到达率

---

### 1.3 各厂商 ROM 差异实战

#### 问题 6：通知渠道（Notification Channel）在各厂商上的表现有什么差异？

Android 8.0+ 引入了 Notification Channel，但各厂商 ROM 对其支持程度不同：

| 特性 | 原生 Android | 华为 EMUI | 小米 MIUI | OPPO ColorOS | Vivo OriginOS |
|------|:-----------:|:--------:|:--------:|:------------:|:-------------:|
| 通知渠道创建 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 用户自定义渠道设置 | ✅ | ✅（入口深） | ✅ | ✅ | ✅ |
| 渠道重要性级别 | IMPORTANCE_HIGH~NONE | 0~5（映射到华为体系） | 0~4 | 0~5 | 0~4 |
| 通知分类（系统级） | 无 | ✅ 社交/服务/广告等 | ✅ | ✅ | ✅ |
| 默认关闭通知 | 不会 | 非白名单默认折叠 | 部分机型默认关闭 | 智能静默 | 默认静默部分类别 |
| 角标支持 | 点(API 26) / 数字 | ✅ 数字角标 | ✅ 数字角标 | ✅ 数字角标（需适配） | ✅ 数字角标 |

**实战要点：**

- 华为系设备会自动将通知划分为"社交""服务""广告"等类别，服务类通知可能被折叠到"不重要通知"中
- 小米 MIUI 12+ 引入了"通知过滤规则"，第三方 App 通知默认可能不弹窗
- OPPO/Vivo 首装 App 默认禁止通知权限（Android 13+ 特性），必须主动请求 `POST_NOTIFICATIONS` 权限

#### 问题 7：自启动管理在各厂商上的差异？

| 厂商 | 自启动管理路径 | 默认状态 | 引导方式 |
|:---:|--------------|:------:|---------|
| **华为** | 手机管家 → 应用启动管理 → 允许自启动/关联启动/后台活动 | **禁止**（默认手动管理） | `Intent` 跳转系统设置页 |
| **小米** | 安全中心 → 授权管理 → 自启动管理 | **禁止** | 只能引导用户手动开启 |
| **OPPO** | 设置 → 安全 → 自启动管理 | **禁止** | 跳转 `com.coloros.safecenter` |
| **Vivo** | i管家 → 应用管理 → 权限管理 → 自启动 | **禁止** | 跳转 `com.vivo.permissionmanager` |

**统一处理方案：**

```kotlin
// 品牌判断 + 特定跳转
fun getAutoStartIntent(context: Context): Intent? {
    return when {
        isHuawei() -> Intent().apply {
            component = ComponentName("com.huawei.systemmanager",
                "com.huawei.systemmanager.startupmgr.ui.StartupNormalAppListActivity")
        }
        isXiaomi() -> Intent().apply {
            component = ComponentName("com.miui.securitycenter",
                "com.miui.permcenter.autostart.AutoStartManagementActivity")
        }
        isOppo() -> Intent().apply {
            component = ComponentName("com.coloros.safecenter",
                "com.coloros.safecenter.permission.startup.StartupAppListActivity")
        }
        isVivo() -> Intent().apply {
            component = ComponentName("com.vivo.permissionmanager",
                "com.vivo.permissionmanager.activity.BgStartUpManagerActivity")
        }
        else -> Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
            data = Uri.parse("package:${context.packageName}")
        }
    }
}
```

**注意：** 各厂商的跳转 Activity 可能随系统版本变化，线上要做好 try-catch 兜底，失败后跳转通用应用详情页。

---

### 1.4 统一推送联盟（UPS）

#### 问题 8：统一推送联盟是什么？现状如何？

**背景：** 2017 年由工信部指导成立，旨在建立统一的 Android 推送通道，解决 App 各自维护长连接导致的电量消耗和后台滥用问题。

**核心协议：** UPS 基于 OMA Push 标准，定义了统一的推送接口规范。终端厂商（华为/小米/OPPO/Vivo/魅族等）在系统级实现推送 SDK，App 接入统一接口即可。

**现状（面试如实说）：**

- ✅ 接口标准已发布，技术规范成熟
- ✅ 华为/小米/OPPO/Vivo/魅族等均已接入
- ⚠️ 实际进度缓慢，各厂商仍力推自有推送 SDK
- ⚠️ 市场渗透率有限，大部分 App 依然选择直接接入各厂商 SDK
- 📌 趋势：单一推送服务商（如个推/极光）封装了各个厂商通道，实际落地仍以第三方聚合 SDK 为主

---

## 二、HMS Core 替代服务完整映射表（GMS → HMS）

> **面试高分秘籍**：能脱口而出 GMS 与 HMS 的完整映射关系，展现你对华为生态的深入理解。

### 2.1 核心服务映射

| GMS 服务 | HMS 对应服务 | 功能说明 | 适配难度 |
|---------|------------|---------|:------:|
| Firebase Cloud Messaging (FCM) | Push Kit | 消息推送 | ★★ |
| Google Maps SDK | Map Kit | 地图显示与交互 | ★ (API 高度一致) |
| Google Sign-In | Account Kit / Auth Service | 账号登录与认证 | ★★★ |
| FusedLocationProvider | Location Kit | 融合定位 | ★★ |
| Google Analytics | Analytics Kit | 用户行为分析 | ★★ |
| Google Pay | IAP Kit / Wallet Kit | 应用内支付 | ★★★ |
| AdMob | Ads Kit | 广告变现 | ★★★ |
| ML Kit | ML Kit (HMS) | 机器学习（文本/图像/语音） | ★★ |
| SafetyNet | Safety Detect | 设备安全检测 | ★★★ |
| Google Drive API | Drive Kit | 云存储 | ★★★ |
| Google Fit | Health Kit | 运动健康数据 | ★★★ |
| Nearby Connections | Nearby Service | 近距离通信 | ★★ |
| ARCore | AR Engine | 增强现实 | ★★★ |
| Google Cast | Cast+ / OneHop | 投屏 | ★★ |
| reCAPTCHA | Safety Detect CAPTCHA | 人机验证 | ★ |

### 2.2 依赖替换对照

```groovy
// build.gradle 双框架依赖
dependencies {
    // GMS
    gmsImplementation 'com.google.android.gms:play-services-maps:18.1.0'
    gmsImplementation 'com.google.firebase:firebase-messaging:23.2.0'
    gmsImplementation 'com.google.android.gms:play-services-auth:20.7.0'
    gmsImplementation 'com.google.android.gms:play-services-location:21.0.1'
    
    // HMS
    hmsImplementation 'com.huawei.hms:maps:6.11.0.300'
    hmsImplementation 'com.huawei.hms:push:6.11.0.300'
    hmsImplementation 'com.huawei.hms:hwid:6.11.0.300'
    hmsImplementation 'com.huawei.hms:location:6.11.0.300'
}
```

---

## 三、双框架架构设计

### 3.1 整体分层架构图

```
┌──────────────────────────────────────────────────────────────────┐
│                        App 业务层                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ 推送业务逻辑  │  │ 地图业务逻辑  │  │  登录/支付/定位业务逻辑  │  │
│  └──────┬──────┘  └──────┬──────┘  └───────────┬─────────────┘  │
│         │                │                      │                │
├─────────┼────────────────┼──────────────────────┼────────────────┤
│         ▼                ▼                      ▼                │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │              抽象服务接口层 (Service Interfaces)              │ │
│  │  ┌───────────────┐ ┌───────────────┐ ┌───────────────────┐  │ │
│  │  │ IPushService   │ │ IMapService   │ │ IAuthService      │  │ │
│  │  │ - getToken()   │ │ - showMap()   │ │ - signIn()        │  │ │
│  │  │ - subscribe()  │ │ - addMarker() │ │ - signOut()       │  │ │
│  │  │ - onMessage()  │ │ - moveCamera()│ │ - getProfile()    │  │ │
│  │  └───────┬───────┘ └───────┬───────┘ └────────┬──────────┘  │ │
│  └──────────┼─────────────────┼──────────────────┼─────────────┘ │
│             │                 │                  │                │
├─────────────┼─────────────────┼──────────────────┼────────────────┤
│             ▼                 ▼                  ▼                │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │            服务实现层 (Service Implementations)              │ │
│  │                                                              │ │
│  │   ┌─────────────────────┐    ┌─────────────────────────┐    │ │
│  │   │  GmsPushService     │    │  HmsPushService          │    │ │
│  │   │  GmsMapService      │    │  HmsMapService           │    │ │
│  │   │  GmsAuthService     │    │  HmsAuthService          │    │ │
│  │   │  GmsLocationService │    │  HmsLocationService      │    │ │
│  │   └──────────┬──────────┘    └───────────┬─────────────┘    │ │
│  │              │                           │                   │ │
│  └──────────────┼───────────────────────────┼───────────────────┘ │
│                 │                           │                      │
├─────────────────┼───────────────────────────┼──────────────────────┤
│                 ▼                           ▼                      │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │                   框架检测层 (Framework Detector)             │ │
│  │  ┌────────────────────────────────────────────────────────┐  │ │
│  │  │  FrameworkDetector.detect(context) → Framework          │  │ │
│  │  │  - GMS: GoogleApiAvailability.isGooglePlayServicesAvail │  │ │
│  │  │  - HMS: HuaweiApiAvailability.isHuaweiMobileServicesAvail│  │ │
│  │  └────────────────────────────────────────────────────────┘  │ │
│  └──────────────────────────────────────────────────────────────┘ │
├───────────────────────────────────────────────────────────────────┤
│                        系统层 (Android OS)                         │
│    ┌─────────────────┐              ┌─────────────────┐          │
│    │  Google Play     │              │  HMS Core        │          │
│    │  Services (GMS)  │              │  (Huawei)        │          │
│    └─────────────────┘              └─────────────────┘          │
└──────────────────────────────────────────────────────────────────┘
```

### 4.2 框架检测与路由决策流程

```
                    ┌──────────────┐
                    │  App 启动     │
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐
                    │ 检测 HMS Core │
                    │ 是否可用？     │
                    └──────┬───────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
         HMS 可用                    HMS 不可用
              │                         │
              ▼                         ▼
   ┌──────────────────┐       ┌──────────────────┐
   │ 设备是华为品牌？   │       │ 检测 GMS 是否可用？│
   └────┬────────┬────┘       └────┬────────┬────┘
        │        │                 │        │
     华为牌   非华为牌            GMS可用  GMS不可用
        │        │                 │        │
        ▼        ▼                 ▼        ▼
    ┌──────┐ ┌──────┐         ┌──────┐  ┌──────────┐
    │ 优先 │ │ GMS  │         │ GMS  │  │ 降级方案  │
    │ HMS  │ │ 优先 │         │ 模式 │  │(无推送)   │
    └──────┘ └──────┘         └──────┘  └──────────┘
```

**路由策略（面试标准答案）：**

1. **华为手机 + HMS 可用** → 优先 HMS（华为对 HMS Core 有系统级保护，保活和推送到达率远优于第三方通道）
2. **非华为手机 + HMS 可用** → 优先 GMS（GMS 是 Android 生态标准，非华为设备对 HMS 的保护较弱）
3. **GMS 可用（海外手机）** → 使用 GMS
4. **两者都不可用** → 降级方案（WebSocket 自建长连接 / 无地图功能 / 仅账密登录）

---

## 四、实战：GMS + HMS 双框架推送模块完整实现

### 5.1 推送服务接口定义

```kotlin
// IPushService.kt —— 抽象推送服务接口
interface IPushService {

    /** 获取推送 Token */
    suspend fun getToken(): Result<String>

    /** 订阅主题 */
    suspend fun subscribeToTopic(topic: String): Result<Unit>

    /** 取消订阅主题 */
    suspend fun unsubscribeFromTopic(topic: String): Result<Unit>

    /** 设置消息回调 */
    fun setMessageCallback(callback: PushMessageCallback)

    /** 处理推送消息（由 Service 层调用） */
    fun onMessageReceived(remoteMessage: PushMessage)

    /** 处理 Token 刷新 */
    fun onNewToken(token: String)

    /** 是否可用 */
    fun isAvailable(): Boolean
}

// 统一消息模型
data class PushMessage(
    val messageId: String,
    val title: String?,
    val body: String?,
    val data: Map<String, String>,
    val sentTime: Long
)

interface PushMessageCallback {
    fun onMessageReceived(message: PushMessage)
    fun onTokenRefreshed(token: String)
}
```

### 5.2 GMS 推送实现

```kotlin
// GmsPushService.kt
class GmsPushService(
    private val context: Context
) : IPushService {

    private var callback: PushMessageCallback? = null

    override fun isAvailable(): Boolean {
        return try {
            GoogleApiAvailability.getInstance()
                .isGooglePlayServicesAvailable(context) == ConnectionResult.SUCCESS
        } catch (e: Exception) {
            false
        }
    }

    override suspend fun getToken(): Result<String> {
        return try {
            val token = FirebaseMessaging.getInstance().token.await()
            Result.success(token)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override suspend fun subscribeToTopic(topic: String): Result<Unit> {
        return try {
            FirebaseMessaging.getInstance().subscribeToTopic(topic).await()
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override suspend fun unsubscribeFromTopic(topic: String): Result<Unit> {
        return try {
            FirebaseMessaging.getInstance().unsubscribeFromTopic(topic).await()
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override fun setMessageCallback(callback: PushMessageCallback) {
        this.callback = callback
    }

    override fun onMessageReceived(remoteMessage: PushMessage) {
        callback?.onMessageReceived(remoteMessage)
    }

    override fun onNewToken(token: String) {
        callback?.onTokenRefreshed(token)
    }

    // FCM Service 中调用此方法
    fun handleFcmMessage(fcmMessage: com.google.firebase.messaging.RemoteMessage) {
        val pushMessage = PushMessage(
            messageId = fcmMessage.messageId ?: "",
            title = fcmMessage.notification?.title,
            body = fcmMessage.notification?.body,
            data = fcmMessage.data as Map<String, String>,
            sentTime = fcmMessage.sentTime
        )
        onMessageReceived(pushMessage)
    }
}
```

### 5.3 HMS 推送实现

```kotlin
// HmsPushService.kt
class HmsPushService(
    private val context: Context
) : IPushService {

    private var callback: PushMessageCallback? = null

    override fun isAvailable(): Boolean {
        return try {
            HuaweiApiAvailability.getInstance()
                .isHuaweiMobileServicesAvailable(context) == com.huawei.hms.api.ConnectionResult.SUCCESS
        } catch (e: Exception) {
            false
        }
    }

    override suspend fun getToken(): Result<String> {
        return try {
            val appId = context.getString(R.string.hms_app_id)
            val token = HmsInstanceId.getInstance(context)
                .getToken(appId, HmsMessaging.DEFAULT_TOKEN_SCOPE)
            Result.success(token)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override suspend fun subscribeToTopic(topic: String): Result<Unit> {
        return try {
            HmsMessaging.getInstance(context).subscribe(topic).await()
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override suspend fun unsubscribeFromTopic(topic: String): Result<Unit> {
        return try {
            HmsMessaging.getInstance(context).unsubscribe(topic).await()
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override fun setMessageCallback(callback: PushMessageCallback) {
        this.callback = callback
    }

    override fun onMessageReceived(remoteMessage: PushMessage) {
        callback?.onMessageReceived(remoteMessage)
    }

    override fun onNewToken(token: String) {
        callback?.onTokenRefreshed(token)
    }

    // HMS Message Service 中调用此方法
    fun handleHmsMessage(hmsMessage: com.huawei.hms.push.RemoteMessage) {
        val pushMessage = PushMessage(
            messageId = hmsMessage.messageId ?: "",
            title = hmsMessage.notification?.title,
            body = hmsMessage.notification?.body,
            data = hmsMessage.dataOfMap ?: emptyMap(),
            sentTime = hmsMessage.sentTime
        )
        onMessageReceived(pushMessage)
    }
}
```

### 5.4 AndroidManifest 双 Service 注册

```xml
<!-- AndroidManifest.xml -->
<application>
    <!-- FCM Service -->
    <service
        android:name=".push.FcmMessagingService"
        android:exported="false">
        <intent-filter>
            <action android:name="com.google.firebase.MESSAGING_EVENT" />
        </intent-filter>
    </service>

    <!-- HMS Push Service -->
    <service
        android:name=".push.HmsMessagingService"
        android:exported="false">
        <intent-filter>
            <action android:name="com.huawei.push.action.MESSAGING_EVENT" />
        </intent-filter>
    </service>

    <!-- 统一推送入口 Service（可选，根据运行时检测分发） -->
    <service
        android:name=".push.UnifiedMessagingService"
        android:exported="false">
    </service>
</application>
```

### 5.5 统一推送管理器（PushManager）

```kotlin
// PushManager.kt —— 业务层唯一入口
class PushManager private constructor(private val context: Context) {

    companion object {
        @Volatile private var instance: PushManager? = null

        fun getInstance(context: Context): PushManager {
            return instance ?: synchronized(this) {
                instance ?: PushManager(context.applicationContext).also { instance = it }
            }
        }
    }

    enum class Framework { GMS, HMS, NONE }

    // 当前活跃的推送服务
    private var activeService: IPushService? = null
    var currentFramework: Framework = Framework.NONE
        private set

    /**
     * 初始化推送服务 —— 自动检测并选择最佳框架
     */
    suspend fun initialize(callback: PushMessageCallback): Framework {
        val gmsService = GmsPushService(context)
        val hmsService = HmsPushService(context)

        // 华为设备优先使用 HMS
        if (isHuaweiDevice() && hmsService.isAvailable()) {
            activeService = hmsService
            currentFramework = Framework.HMS
        }
        // 其他设备优先使用 GMS
        else if (gmsService.isAvailable()) {
            activeService = gmsService
            currentFramework = Framework.GMS
        }
        // HMS 作为兜底（非华为设备也安装了 HMS Core 的情况）
        else if (hmsService.isAvailable()) {
            activeService = hmsService
            currentFramework = Framework.HMS
        }
        // 两者都不可用
        else {
            activeService = null
            currentFramework = Framework.NONE
            return Framework.NONE
        }

        activeService?.setMessageCallback(callback)

        // 获取 Token 并上报服务端
        activeService?.getToken()?.onSuccess { token ->
            callback.onTokenRefreshed(token)
            uploadTokenToServer(token, currentFramework)
        }

        return currentFramework
    }

    /**
     * 业务方调用 —— 订阅主题
     */
    suspend fun subscribeToTopic(topic: String): Result<Unit> {
        return activeService?.subscribeToTopic(topic)
            ?: Result.failure(IllegalStateException("Push service not initialized"))
    }

    /**
     * 上报 Token 到后端
     */
    private suspend fun uploadTokenToServer(token: String, framework: Framework) {
        // POST /api/push/register
        // Body: { "token": token, "platform": "ANDROID", "channel": "GMS|HMS" }
        // 服务端根据 channel 字段选择对应的推送通道下发消息
    }

    private fun isHuaweiDevice(): Boolean {
        return Build.MANUFACTURER.equals("HUAWEI", ignoreCase = true) ||
               Build.BRAND.equals("HUAWEI", ignoreCase = true) ||
               Build.BRAND.equals("HONOR", ignoreCase = true)
    }
}
```

### 5.6 服务端推送通道选择策略

```python
# 服务端推送分发逻辑（伪代码）
def send_push(user_id, title, body, data):
    # 查询用户注册的最新 Token
    registration = db.query("""
        SELECT token, channel, updated_at 
        FROM push_registrations 
        WHERE user_id = ? AND active = 1
    """, user_id)
    
    if not registration:
        return False
    
    if registration.channel == "GMS":
        return send_via_fcm(registration.token, title, body, data)
    elif registration.channel == "HMS":
        return send_via_hms_push(registration.token, title, body, data)
    else:
        # 降级：App 内轮询或其他方式
        return send_via_local_polling(user_id, title, body, data)
```

---

## 五、面试常见追问与参考答案

### Q1: HMS 和 GMS 的包大小影响？怎么处理？

**答：** 两个 SDK 都比较大（各约 5-10MB），如果同时打包 APK 会显著增大体积。两种方案：
- **方案 A（推荐）：** 使用 Gradle `productFlavors`，分别打 GMS 包和 HMS 包，华为应用市场上传 HMS 包，Google Play 上传 GMS 包
- **方案 B：** 动态加载，仅在运行时检测到对应框架时才初始化 SDK，减少初始化开销，但包体仍然较大

### Q2: 如何处理华为设备上既有 HMS 又有 GMS 的情况（比如海外华为老机型）？

**答：** 在同时存在的情况下，根据设备品牌决策：华为/荣耀设备优先走 HMS（系统级保护更好），非华为设备优先走 GMS（生态标准）。`FrameworkDetector` 中的优先级逻辑已经体现了这一策略。

### Q3: 推送到达率在各厂商能达到多少？

| 通道 | 国内到达率 | 海外到达率 | 说明 |
|------|:-------:|:-------:|------|
| FCM（非华为/小米设备） | N/A | 95%+ | Google Play Services 绑定 |
| FCM（华为/小米设备国内） | 10-30% | N/A | 系统杀死 Google 服务 |
| HMS Push（华为设备） | 90%+ | 90%+ | 系统级保护 |
| 小米 Push（MIUI） | 85%+ | N/A | 需接入小米推送 SDK |
| OPPO Push（ColorOS） | 80%+ | N/A | 需接入 OPPO 推送 SDK |
| 个推/极光（聚合通道） | 70-85% | 60-75% | 聚合多个厂商通道 |
| 自建长连接 | 30-50% | 30-50% | 容易被系统杀死 |

### Q4: 如果只做国内市场，是否只需要接 HMS？

**答：** 不对。国内市场除了华为，还有小米、OPPO、Vivo 等厂商，它们使用 GMS（国内版也有 Google Play Services 的简化版或替代版）或自建推送。最佳实践是接入第三方聚合推送 SDK（如个推、极光），它们内部已封装华为/小米/OPPO/Vivo/FCM 等多个通道。

---

## 六、总结与面试话术

### 一句话总结

> "出海应用厂商兼容性的核心是**运行时框架检测 + 接口抽象 + 工厂路由**，通过 `FrameworkDetector` 自动识别设备能力，动态选择 GMS 或 HMS 实现，业务层通过 `IPushService`/`IMapService` 等统一接口调用，完全不感知底层实现差异。"

### 面试回答模板

当面试官问"你们 App 是怎么做华为和海外适配的？"，按以下结构回答：

1. **问题背景**（15秒）：国内用不了 GMS，海外华为用不了 GMS，需要双框架
2. **架构设计**（30秒）：接口抽象 + 工厂模式，业务层依赖接口不依赖具体实现
3. **框架检测**（15秒）：运行时检测 `GoogleApiAvailability` / `HuaweiApiAvailability`，华为设备优先 HMS
4. **具体案例**（30秒）：以推送为例，`IPushService` 定义统一接口，`GmsPushService` 和 `HmsPushService` 分别实现，`PushManager` 自动选择并初始化
5. **打包策略**（15秒）：productFlavors 分别出包，华为市场用 HMS 包，Google Play 用 GMS 包
6. **补充厂商适配**（15秒）：除了 GMS/HMS，还要处理通知渠道兼容、自启动引导、后台限制差异

---

> **参考资源：**
> - [华为 HMS Core 开发文档](https://developer.huawei.com/consumer/cn/hms/)
> - [Firebase Cloud Messaging](https://firebase.google.com/docs/cloud-messaging)
> - [Android 后台执行限制](https://developer.android.com/guide/background)
