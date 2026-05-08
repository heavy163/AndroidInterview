# 架构设计题 — 六层递进式面试解析

> 架构设计题是高级/资深 Android 面试中最能拉开差距的环节。面试官不是要你背诵源码，而是考察你**面对模糊需求时的拆解能力、权衡思维、以及从 0 到 1 的系统推演能力**。以下 4 道大题的每一道都严格遵循「**问题 → 需求分析 → 架构设计 → 核心模块 → 技术选型 → 加分点**」六层递进结构，覆盖了图片加载、IM 消息、组件化路由、网络层四大高频方向。

---

## 目录

- [一、设计图片加载框架](#一设计图片加载框架)
- [二、设计 IM 消息系统](#二设计-im-消息系统)
- [三、设计组件化路由框架](#三设计组件化路由框架)
- [四、设计网络层](#四设计网络层)

---

## 一、设计图片加载框架

### 1.1 问题

> 在一个大型 App 里，如果不使用任何图片加载库，直接用 BitmapFactory 解码并设置给 ImageView，会遇到什么问题？如何从零设计一个类似 Glide 的图片加载框架？

### 1.2 需求分析

| 需求维度 | 具体描述 | 优先级 |
|---------|---------|-------|
| **功能需求** | 支持网络/本地/资源/Assets 等多种图片源；支持占位图/错误图/缩略图渐变展示；支持圆角/圆形/高斯模糊等变换 | P0 |
| **性能需求** | 内存占用可控，避免 OOM；列表快速滑动时不加载图片，停止后再加载；图片解码尺寸与 View 大小匹配，避免浪费 | P0 |
| **稳定性需求** | 页面销毁时自动取消请求，避免内存泄漏；Bitmap 复用池降低 GC 频率 | P0 |
| **扩展需求** | 支持自定义编解码器（GIF/WebP/SVG）；支持 OkHttp/Volley 可替换网络层；支持渐进式 JPEG | P1 |

面试官期待的产出是：你不仅能说出来要做什么，还能说清楚**为什么这么做，以及做的时候有哪些坑**。

### 1.3 架构设计（分层架构）

```
┌─────────────────────────────────────────┐
│              调用层 (Glide.with)          │
├─────────────────────────────────────────┤
│          RequestBuilder (链式API)         │
├─────────────────────────────────────────┤
│             Engine (调度核心)              │
│  ┌──────┬──────┬──────┬──────┐          │
│  │Active│Memory│Disk  │Source│          │
│  │Cache │Cache │Cache │  Fet │          │
│  └──────┴──────┴──────┴──────┘          │
├─────────────────────────────────────────┤
│      Decode / Transform (解码变换层)      │
├─────────────────────────────────────────┤
│         网络层 / 本地IO (数据源)           │
└─────────────────────────────────────────┘
```

**核心设计原则：**

- **单一职责**：每一层只做一件事。RequestBuilder 只管参数组装，Engine 只管调度，Decoder 只管解码。
- **依赖倒置**：Engine 不直接依赖 OkHttp，而是依赖抽象的网络接口，方便替换。
- **生命周期感知**：通过添加无 UI 的 Fragment 感知 Activity/Fragment 生命周期，在 onStop/onDestroy 时自动暂停/取消请求。

### 1.4 核心模块详解

#### 模块一：缓存策略（四级缓存）

| 缓存级别 | 存储位置 | 特点 | 清除时机 |
|---------|---------|------|---------|
| **活跃资源 (ActiveResources)** | `Map<Key, WeakReference<EngineResource>>` | 正在使用的图片，弱引用持有 | 无引用时降级到 MemoryCache |
| **内存缓存 (MemoryCache)** | `LruCache<Key, EngineResource>` | LRU 淘汰策略，基于 LinkedHashMap | 内存紧张时按 LRU 淘汰 |
| **磁盘缓存 (DiskCache)** | 基于 DiskLruCache 的文件存储 | 持久化，跨进程可共享 | 超过容量上限时按 LRU 淘汰 |
| **原始数据 (Source)** | 网络/本地文件/ContentProvider | 不做缓存 | 每次重新请求 |

**面试亮点**：Glide 的 ActiveResources 层是一个容易被忽略但极其精妙的设计——它解决了"一张图片列表中有多个 ImageView 引用同一张图，如果直接用 LruCache 可能被误淘汰"的问题。活跃资源相当于一个「引用计数保护壳」，只有所有 View 都释放引用后，才降级到 LruCache 中参与淘汰。

**面试追问**：「三级缓存和四级缓存的本质区别是什么？」答案是：三级缓存（网络→磁盘→内存）是 Android 面试的基础题；四级缓存（活跃→内存→磁盘→网络）才是架构设计题的答案——多出来的一层解决的是**同一个资源被多个消费者持有时的安全淘汰问题**。

#### 模块二：生命周期管理

Glide 通过 **RequestManager + SupportRequestManagerFragment** 实现生命周期感知：

```
Glide.with(activity)
  → 获取/创建一个无 UI 的 Fragment 挂载到 Activity
  → Fragment 的 onStart/onStop/onDestroy 回调
  → 通知 RequestManager 控制请求的 暂停/恢复/取消
```

- **为什么用 Fragment 而不是 Application.registerActivityLifecycleCallbacks？** 因为 Fragment 的生命周期与宿主完全同步，且能精确控制粒度为单个 Activity；全局回调则需要额外维护映射表，且容易造成泄漏。
- **为什么不在 onDestroy 时直接取消？** Glide 在 onStop 时就暂停请求，onStart 时恢复——这样用户在按 Home 键回来后，图片能继续加载，而不是重新发起请求。

#### 模块三：线程池设计

| 线程池 | 核心线程 | 用途 |
|-------|---------|------|
| **Source 线程池** | CPU 核心数 | 网络请求 / 本地磁盘 IO |
| **DiskCache 线程池** | 1 | 磁盘缓存读写（单线程避免文件锁竞争） |
| **Decode 线程池** | CPU 核心数 | 图片解码 / 变换处理 |
| **主线程回调** | Handler(Looper.mainLooper) | 将结果回调到 UI 线程 |

**设计要点**：
- DiskCache 执行器必须单线程化：`Executors.newSingleThreadExecutor()`+`ThreadPoolExecutor` 配合 `PriorityBlockingQueue`，因为磁盘 IO 天然串行效率更高，多线程并发写同一缓存文件会引发竞态条件。
- Source 和 Decode 线程池要分离：解码是 CPU 密集型，网络是 IO 密集型，混用会导致线程饥饿。
- 优先级队列：滑动中的图片请求优先级高于预加载请求，通过 `PriorityBlockingQueue` 实现。

#### 模块四：变换 (Transformation)

变换链采用责任链模式：

```
原图 → CenterCrop → RoundCorner → Blur → 目标 Bitmap
```

**关键设计**：
- 输入输出都是 `Resource<Bitmap>`，保证链式可组合。
- 复用 Bitmap：通过 BitmapPool 复用中间产生的临时 Bitmap，减少内存抖动。
- 变换在子线程执行，避免阻塞主线程。

### 1.5 技术选型对比

| 方案 | 优点 | 缺点 | 适用场景 |
|-----|------|------|---------|
| Glide | 生命周期感知、四级缓存、API 简洁 | 包体积较大 | 通用场景首选 |
| Coil | Kotlin 协程、轻量级、Compose 友好 | 功能相对少 | 纯 Kotlin 项目 |
| Fresco | 独立的 Native 内存区、渐进式JPEG | 侵入性强、包体积大 | 图片密集型 App |
| Picasso | 轻量简洁 | 不支持 GIF、已停止维护 | 不建议新项目使用 |

### 1.6 加分点（面试翻盘区）

1. **Bitmap 复用池 (BitmapPool)**：LruPoolStrategy 将复用的 Bitmap 按尺寸分组，匹配时允许复用 ≥ 目标尺寸的 Bitmap，decode 时用 `inBitmap` 重用像素内存——Glide 4.x 默认复用配置为 ARGB_8888。
2. **降采样策略**：根据 ImageView 的宽高（或 Target 的期望尺寸），计算 `inSampleSize` 和 `inDensity`，使解码后的 Bitmap 刚好满足显示需求，避免加载一张 4000×3000 的图只显示在 200×150 的 ImageView 上。
3. **ARGB_8888 vs RGB_565 切换**：根据原图是否有透明通道自动选择格式。无透明通道的 JPEG 用 RGB_565，每像素省一半内存。可通过 `HeifDecoder` 等解码器提前读取 `BitmapFactory.Options.inPreferredConfig`。
4. **渐进式 JPEG 加载**：通过自定义 `InputStream` 包装，将网络流的多次回调分阶段喂给 `BitmapRegionDecoder`，实现「从模糊到清晰」的加载体验。
5. **Glide 为什么在 Android 9+ 上更快？** 因为 Android 9 引入了 `ImageDecoder`，内部使用更高效的硬件解码器，且自动处理动画（GIF/WebP 动画帧）。Glide 4.9+ 默认优先使用 `ImageDecoder`。
6. **缓存 Key 设计**：缓存 Key 不是简单的 URL，而是由十几项参数的 SHA-256 组成（URL + 宽高 + 变换列表 + 配置项等），任何一个参数变化都会导致 Key 不同，确保同一 URL 的不同尺寸/变换不会互相覆盖。
7. **Registry 机制（组件注册/替换）**：Glide 的核心扩展点——通过 Registry 可以替换 ModelLoader（数据来源）、ResourceDecoder（解码器）、Encoder（缓存编码器），使框架对扩展开放对修改关闭，是典型的**策略模式 + 注册表模式**应用。
8. **Kotlin 协程 vs RxJava**：Coil 的协程设计让其天然支持结构化并发和取消传播，代码比 Glide 的 ThreadPool 模式更简洁；但 Glide 的线程池对优先级队列的控制粒度更细。

---

## 二、设计 IM 消息系统

### 2.1 问题

> 你需要为 App 设计一个即时通讯（IM）消息系统，支持单聊、群聊、离线消息、消息已读/未读状态。请从架构层面给出设计。

### 2.2 需求分析

| 需求维度 | 具体描述 | 优先级 |
|---------|---------|-------|
| **实时性** | 消息端到端延迟 < 200ms；在线消息几乎实时到达 | P0 |
| **可靠性** | 消息不丢、不重、不乱序；弱网/断网重连后消息必达 | P0 |
| **一致性** | 多端登录时消息同步；已读状态跨端一致 | P0 |
| **离线消息** | 接收方不在线时，消息正常存储，上线后拉取 | P1 |
| **扩展性** | 支持文本/图片/语音/视频/自定义消息类型 | P1 |
| **安全性** | 消息端到端加密（可选）；信令通道 TLS 加密 | P2 |

**面试陷阱**：很多候选人上来就说用 WebSocket，但没想清楚底层连接的完整生命周期——连接断开怎么办？心跳怎么打？重连策略是什么？消息怎么去重？这些才是真正考察架构能力的点。

### 2.3 架构设计（分层架构）

```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  UI Layer    │  │  UI Layer    │  │  UI Layer    │
│ (ChatView)   │  │ (ConvList)   │  │ (Notify)     │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │
┌──────┴─────────────────┴─────────────────┴───────┐
│              MessageDispatcher (消息分发层)         │
│   ┌─────────┐  ┌──────────┐  ┌───────────────┐  │
│   │EventBus │  │Observer  │  │ConversationRepo│  │
│   └─────────┘  └──────────┘  └───────────────┘  │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────┐
│              MessageCore (消息核心层)              │
│  ┌────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │MsgSync │ │MsgACK    │ │MsgQueue(重发队列) │  │
│  │Service │ │Processor │ │                   │  │
│  └────────┘ └──────────┘ └───────────────────┘  │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────┐
│           ConnectionManager (连接管理层)           │
│  ┌────────────┐ ┌────────┐ ┌────────────────┐  │
│  │WebSocket   │ │Heart   │ │Reconnect       │  │
│  │Connection  │ │Beat    │ │Strategy        │  │
│  └────────────┘ └────────┘ └────────────────┘  │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────┐
│              Storage Layer (存储层)               │
│  ┌──────────┐  ┌───────────┐  ┌─────────────┐  │
│  │  Room DB  │  │ ProtoBuf  │  │  MMKV(配置)  │  │
│  └──────────┘  └───────────┘  └─────────────┘  │
└─────────────────────────────────────────────────┘
```

### 2.4 核心模块详解

#### 模块一：WebSocket 长连接管理

**完整连接状态机（7 种状态）：**

```
DISCONNECTED → CONNECTING → CONNECTED → AUTHED (鉴权通过)
                                          │
                                    ┌─────┴─────┐
                                    ↓           ↓
                               ACTIVE      KICKED_OUT
                                (正常工作)    (被踢下线)
                               │
                    ┌──────────┴──────────┐
                    ↓                     ↓
            RECONNECTING ←─── WAITING_FOR_NET
             (主动重连)          (等网络恢复)
```

**面试中必须说清楚的设计要点**：

- **握手阶段做鉴权**：WebSocket 连接建立后，第一帧必须是鉴权帧（携带 token），服务端验证通过后才下发离线消息。连接未鉴权前不允许发送业务消息。
- **合理使用单连接**：IM 场景下，一个 App 只需要一条长连接。多连接不仅浪费资源，还会导致消息顺序混乱、服务端推送冲突。
- **多进程共存问题**：如果你的 App 有多个进程（如 WebView 进程），长连接应该只在主进程维护，其他进程通过 ContentProvider 或 Binder 跨进程通信获取消息。否则会出现两个进程各维护一条连接，服务端收到两条相同 token 的连接相互踢线。

#### 模块二：心跳与重连策略

```
心跳机制（双向保活）：
├── 客户端 → 服务端: PING 帧 (30s 间隔)
├── 服务端 → 客户端: PONG 帧
└── 超时判定: 连续 3 次 PING 无 PONG → 认为连接断开 → 触发重连
```

**关键参数设计**：

| 参数 | 推荐值 | 说明 |
|-----|-------|------|
| 心跳间隔 | 30s (WiFi) / 60s (4G/5G) | 4G NAT 超时通常 2-5 分钟，30s 兜底足够；过短频繁唤醒耗电 |
| PING 超时 | 10s | 单次 PING 后等待 PONG 的超时时间 |
| 重连间隔 | 1s, 2s, 4s, 8s, 16s, 30s, 30s...（指数退避） | 前几次快速重连，后面逐渐放慢，避免服务器压力 |
| 最大重连次数 | 无限制，或限制 10 次后提示用户 | 理论上应无限重连，但可加兜底 |

**智能心跳（加分项）**：
- **自适应间隔**：App 在前台时心跳间隔为 30s，退到后台时变为 3min，降低功耗。
- **网络切换检测**：通过 `ConnectivityManager.NetworkCallback` 监听网络切换（4G → WiFi），网络恢复时立即发起重连，减少消息延迟。
- **App 活跃探测**：用户若在最近 1min 内发过消息，说明通道是通的，心跳可适当延后。

#### 模块三：消息 ACK 与去重

这是 IM 系统中最难设计、也最容易出问题的一环。需要区分三种 ACK：

| ACK 类型 | 含义 | 方向 | 触发时机 |
|---------|------|------|---------|
| **SERVER_ACK** | 服务端确认收到消息 | 服务端→发送方 | 消息入库，立即返回 |
| **CLIENT_RECEIVED** | 接收方客户端已收到 | 接收方→服务端→发送方 | 消息展示后发送 |
| **CLIENT_READ** | 接收方用户已读 | 接收方→服务端→发送方 | 用户真正看到消息 |

**消息状态流转（发送方视角）：**

```
SENDING → SERVER_ACKED → RECEIVED → READ
   │          │             │
   └──(超时)──→ FAILED      │
                            └──(超时未收到) → DELIVERED_BUT_NOT_RECEIVED
```

**去重机制**：

- **服务端去重**：每条消息生成全局唯一 `msgId`（Snowflake 算法或 UUIDv7），服务端以 `msgId` 为唯一索引，收到重复 msgId 直接丢弃但返回 ACK。为什么需要返回 ACK？——发送方可能因为网络波动没收到上一次 ACK 而重发。
- **客户端去重**：收到服务端推送的消息后，用本地 `Set<msgId>`（LRU 策略，保留最近 1000 条）去重，防止因断线重连/ACK 丢失导致服务端重推。
- **顺序保证**：每条消息携带 `seq`（会话内递增序号），客户端收到的消息按 seq 排序后再渲染。若发现 seq 跳跃（如收到 1,2,5，缺了 3,4），说明有消息丢失，触发增量拉取。

#### 模块四：离线消息与消息同步

离线消息方案对比：

| 方案 | 原理 | 优点 | 缺点 |
|-----|------|------|------|
| **拉模式** | 上线后主动拉取所有离线消息 | 简单可靠 | 延迟大，大量离线消息时拉取耗时长 |
| **推模式** | 上线后服务端批量推送 | 延迟低 | 服务端压力大，需要限流 |
| **推+拉结合（推荐）** | 先推最近 50 条，更多用户手动拉 | 体验好，兼顾首屏速度和完整性 | 实现复杂度高 |

**增量同步机制**：客户端维护每个会话的 `last_seq`，上线后服务端只需要把 `seq > last_seq` 的消息推送过来。这比全量同步高效得多。

**面试追问**：「如果一个用户有 1000 个群、每个群 100 条离线消息，上线时怎么办？」答案：不能全推——技术上用**增量同步 + 分页 + 按会话优先级推送**：先推送最近有过互动的 Top 10 会话，再按需加载其余会话。

### 2.5 技术选型对比

| 方案 | 协议 | 优点 | 缺点 |
|-----|------|------|------|
| **自建 WebSocket** | RFC 6455 | 全双工、浏览器原生支持、生态成熟 | 需自建重连/心跳/ACK |
| **MQTT** | ISO 标准 | 极轻量、IoT 原生支持、QoS 三级保证 | 性能上限低，不适合高并发大消息 |
| **Socket.io** | Engine.IO | 自动降级(WS→HTTP Long Polling) | 服务端限定 Node.js |
| **gRPC Stream** | HTTP/2 | 双向流、协议紧缩(ProtoBuf)、强类型 | 移动端支持不如 WS 成熟 |

### 2.6 加分点（面试翻盘区）

1. **消息分表策略**：按会话分表 `msg_<convId_hash%64>`，避免单表过大导致查询慢。SQLite 单表超过 50w 行后即使有索引，复杂查询也会明显变慢。
2. **ProtoBuf 序列化**：相比 JSON 体积减少 60-80%，解析速度快 3-10 倍。配合 `oneof` 特性优雅支持多态消息类型。
3. **本地消息的 WAL 模式**：开启 SQLite WAL（Write-Ahead Logging），写操作不阻塞读操作，提升消息并发读写性能。
4. **FCM/APNs 推送兜底**：长连接断线时，通过系统推送通知用户有新消息，同时 App 收到推送后立即建立长连接拉取消息。这是「长连接 + 短推送」的双通道保障模型。
5. **弱网消息合并**：弱网环境下多条连续消息合并为一个包发送。极端弱网下优先级排序：文本 > 图片缩略图 > 原图 > 视频。
6. **端到端加密 (E2EE)**：Signal Protocol（Double Ratchet 双棘轮算法）是目前业界标准，本地私钥用 Android Keystore 存储。面试中提到就是对安全的深度思考。
7. **秒开优化**：进入聊天页时优先从本地 DB 渲染消息列表，同时触发增量同步；而非等网络返回再渲染。
8. **多端消息漫游**：用户换设备登录后，服务端把 `msgId > 设备记录的最大 msgId` 的消息推下来——本质上是一个**基于游标的增量同步系统**。

---

## 三、设计组件化路由框架

### 3.1 问题

> 在一个组件化/模块化的 Android 项目中，模块之间不允许相互依赖，但模块之间的页面跳转、服务调用仍然不可避免。如何设计一个类似 ARouter 的组件化路由框架？

### 3.2 需求分析

| 需求维度 | 具体描述 | 优先级 |
|---------|---------|-------|
| **页面路由** | 通过 URL/path 跳转到任意模块的 Activity/Fragment；支持携带参数（基本类型、Parcelable、Serializable） | P0 |
| **模块解耦** | 调用方不依赖目标模块，只依赖路由 API 模块；编译期自动注册 | P0 |
| **拦截器** | 支持全局/局部拦截器链，可用于登录校验、权限检查、埋点等 | P1 |
| **服务发现** | 通过接口发现并获取其他模块提供的服务实现（IoC） | P1 |
| **降级策略** | 路由失败时的全局降级处理（如跳转到统一错误页或 H5 兜底） | P2 |

**面试核心：ARouter 的底层原理是 APT（Annotation Processing Tool）+ 编译期代码生成 + 运行时路由表。面试官想听的是你对 APT 的理解、拦截器链的设计、以及 SPI 式的服务发现机制。**

### 3.3 架构设计

```
编译期                             运行期
┌──────────────┐              ┌─────────────────────────┐
│ @Route 注解   │              │    ARouter.getInstance() │
│  ↓            │              │         ↓               │
│ Annotation   │  编译期生成   │    LogisticsCenter       │
│ Processor    │─────────────→│    (路由表加载与缓存)      │
│  ↓            │              │         ↓               │
│ 生成路由注册表│              │    _ARouter (核心路由)    │
│ (Java文件)   │              │    ┌─────┬──────┬─────┐  │
└──────────────┘              │    │跳转 │拦截器│服务 │  │
                              │    │模块 │链    │发现 │  │
                              │    └─────┴──────┴─────┘  │
                              └─────────────────────────┘
```

**模块依赖关系（关键！）：**

```
app 模块
  ├──> router-api (路由接口层，所有模块必须依赖)
  ├──> module-login (通过路由跳转，不直接依赖)
  ├──> module-chat
  └──> module-profile

router-api
  └──> router-annotation (注解定义，如 @Route、@Interceptor)

每个业务模块 (module-login/chat/profile)
  └──> router-annotation
  └──> router-api
  └──> router-compiler (annotationProcessor/kapt 依赖)
```

### 3.4 核心模块详解

#### 模块一：APT 生成路由表

这是 ARouter 的核心黑魔法。以一个页面注册为例：

```java
// Step 1: 业务模块中使用注解
@Route(path = "/login/LoginActivity")
public class LoginActivity extends AppCompatActivity { ... }
```

编译期 APT 处理器会扫描所有 `@Route` 注解，生成如下 Java 文件：

```java
// Step 2: 编译自动生成 ARouter$$Group$$login.java
public class ARouter$$Group$$login implements IRouteGroup {
    @Override
    public void loadInto(Map<String, RouteMeta> atlas) {
        atlas.put("/login/LoginActivity",
            RouteMeta.build(
                RouteType.ACTIVITY,
                LoginActivity.class,
                "/login/LoginActivity",
                "login"
            )
        );
    }
}
```

**面试追问**：「为什么 ARouter 在跨模块调用时可以不用依赖目标模块？」

- 关键在**反射**：`Class.forName("com.xxx.LoginActivity")`。编译期只需要生成包含**全限定类名的字符串**，运行期通过反射加载。APT 生成的文件在业务模块自己的编译产物中，归属权没有跨越模块边界。
- 运行时，所有模块的 `ARouter$$Group$$xxx` 类被统一注册到 `LogisticsCenter` 的 `Warehouse`（路由表仓库）。

**ARouter 的分组机制**：支持按 `group` 分组加载路由表，避免首次加载全部模块导致卡顿。如 `/login/xxx` 的 group 为 `login`，首次打开 `/login/LoginActivity` 时只加载 `login` 分组的表。这个设计非常经典——**懒加载策略在路由框架中的应用**。

#### 模块二：拦截器链

借鉴 OkHttp 的拦截器链设计，在路由跳转前后插入横切逻辑：

```
navigation() 调用
    ↓
[Interceptor1: 登录检查]──（未登录→跳转登录页，返回）
    ↓
[Interceptor2: 权限检查]──（无权限→提示，返回）
    ↓
[Interceptor3: 埋点上报]──（异步，不阻塞主流程）
    ↓
[Interceptor4: 参数校验]──（参数异常→降级处理）
    ↓
执行原始跳转 (startActivity / getFragment)
```

**设计要点**：

- **优先级排序**：每个拦截器定义 `priority`，低数字高优先级（类似 Linux nice 值）。登录检查 priority=1，埋点 priority=999。
- **异步拦截**：拦截器回调 `onInterrupt` 后可异步做网络校验（如检查 token 是否过期），校验完成后调用 `onContinue` 继续链式传递。需要维护一个状态机防止同时多次回调。
- **绿色通道**：某些 path（如登录页本身）需要明确跳过登录检查拦截器，否则会出现「要跳转登录页但登录检查拦截器拦截你跳转登录页」的死循环。ARouter 通过 `extras` 中的标志位实现。
- **链不能断**：`InterceptorChain` 的核心是 `index++` ——每个拦截器结束必须调用 `chain.proceed()` 驱动链条前进，否则路由卡死。

#### 模块三：服务发现 (IoC / SPI)

与 Dagger/Hilt 的 DI 不同，ARouter 的服务发现更轻量，适合模块间解耦：

```java
// router-api 模块中定义接口
public interface ILoginService extends IProvider {
    boolean isLogin();
    String getUserId();
}

// module-login 中实现
@Route(path = "/login/service")
public class LoginServiceImpl implements ILoginService { ... }

// module-chat 中调用（不依赖 module-login）
ILoginService service = ARouter.getInstance()
    .navigation(ILoginService.class);
if (service != null && service.isLogin()) {
    // ...
}
```

**原理**：ARouter 编译期为所有 `IProvider` 实现生成服务注册表，运行期通过接口 Class → 查找对应实现路径 → 反射实例化 → 缓存单例。

**与 Dagger/Hilt 的区别**：ARouter 的服务发现是跨模块、完全依赖倒置的——module-chat 不知道 ILoginService 是谁实现的，只在运行时通过 Router 发现。DI 框架通常需要在编译期确定注入目标，跨模块使用时仍然需要依赖接口所在的模块。

### 3.5 技术选型对比

| 方案 | 路由注册方式 | 优点 | 缺点 |
|-----|-----------|------|------|
| **ARouter** | APT 编译期 | 支持分组、拦截器、服务发现、性能好 | 仅限 Android |
| **TheRouter** | APT + Transform | Gradle 8+ 兼容好、支持 KMP | 生态略小于 ARouter |
| **Navigation Compose** | XML / 代码 | Google 官方、类型安全 | 不支持跨模块服务发现 |
| **DeepLink** | Manifest 注册 | 系统原生、支持外部唤起 | 不支持拦截器链、参数受限 |

### 3.6 加分点（面试翻盘区）

1. **Gradle 插件 Transform 扫描**：ARouter 老版本用 `AutoRegister` 插件在 Transform 阶段把各组的路由表汇总到一个注册类中，减少运行期扫描所有 dex 的开销。Gradle 8.0+ Transform API 被移除后需要用 ASM + `AsmClassVisitorFactory` 替代。
2. **路由表性能优化**：路由表实际是一个前缀树（Trie），匹配 `/login/activity` 时先按 group 取到分组再按完整路径 O(1) 查找。HashMap 直接存完整路径也可行，但 Trie 更节省内存且支持通配符匹配。
3. **降级策略**：全局降级（找不到路由→H5 兜底）+ 局部降级（特定 path 在特定条件下替代页面）。ARouter 的 `DegradeService` 和 `PathReplaceService` 各自负责一种降级。
4. **Fragment 路由**：获取目标 Fragment 实例后，通过 `FragmentTransaction` 注入到调用方的容器中。需要注意 Fragment 构造参数必须通过 `setArguments(Bundle)` 传递，不能使用带参构造函数（系统恢复时反射调用无参构造）。
5. **参数自动注入**：`@Autowired` 注解经 APT 生成 `xxx$$ARouter$$Autowired.java`，调用 `inject()` 时自动从 Intent/Arguments 取值赋值到字段。原理是生成的代码里直接 `target.name = target.getIntent().getStringExtra("name")`。
6. **多 Module 间路径冲突检测**：在 APT 中维护一个全局路由表（通过文件跨回合传递），编译时检测重复 path 直接报错。比运行时覆盖静默出错好得多。
7. **KSP (Kotlin Symbol Processing) 替代 kapt**：如果是 Kotlin 项目，用 KSP 替代 kapt 可以减少编译时间 60%+。KSP 直接解析 Kotlin 语法树而不是生成 Java stub。
8. **Hook 点设计**：ARouter 提供了导航前/后、拦截器命中、路由丢失等回调，方便做全链路路由监控——面试中提到 Hook 设计说明你有可观测性思维。

---

## 四、设计网络层

### 4.1 问题

> 在一个大型 App 中，很多地方都直接调用 Retrofit 接口，导致网络配置散落各处，异常处理不一致，切换环境困难。如何设计一个统一的网络层封装？

### 4.2 需求分析

| 需求维度 | 具体描述 | 优先级 |
|---------|---------|-------|
| **统一配置** | BaseUrl、超时、Header（token/版本号）、DNS 等全局统一管理 | P0 |
| **拦截器链** | 日志、Header 注入、重试、缓存策略、Mock 数据等职责清晰拆分 | P0 |
| **缓存策略** | 有网时返回最新数据并更新缓存；无网时返回缓存数据；支持强制刷新 | P1 |
| **异常处理** | 网络异常、业务异常（code!=0）、空数据、解析异常统一处理，上层感知友好 | P0 |
| **扩展性** | 支持环境切换（开发/测试/生产）；支持多 BaseUrl；支持静态/动态切换 BaseUrl | P1 |

### 4.3 架构设计

```
┌────────────────────────────────────────────────────────┐
│                    ViewModel / Repository               │
│  直接依赖抽象 API，不感知底层 OkHttp / Retrofit          │
└────────────────────────┬───────────────────────────────┘
                         │
┌────────────────────────┴───────────────────────────────┐
│               NetworkApi (接口定义层 — 声明式 API)        │
│  interface UserApi {                                   │
│      @GET("user/info")                                 │
│      suspend fun getUserInfo(): ApiResponse<User>      │
│  }                                                     │
└────────────────────────┬───────────────────────────────┘
                         │
┌────────────────────────┴───────────────────────────────┐
│          NetworkClient (网络客户端 — 单例，管理配置)       │
│  ┌──────────┐ ┌────────────┐ ┌───────────────────┐    │
│  │OkHttp    │ │Retrofit    │ │CacheManager       │    │
│  │Client    │ │Instance    │ │(OkHttp Cache)     │    │
│  └──────────┘ └────────────┘ └───────────────────┘    │
└────────────────────────┬───────────────────────────────┘
                         │
┌────────────────────────┴───────────────────────────────┐
│              拦截器链 (Interceptor Chain)                │
│  LoggingInterceptor → HeaderInterceptor →               │
│  TokenInterceptor → CacheInterceptor → RetryInterceptor │
└────────────────────────┬───────────────────────────────┘
                         │
┌────────────────────────┴───────────────────────────────┐
│              ApiResponse 包装 (统一返回格式)              │
│  sealed class ApiResult<T> {                           │
│      data class Success<T>(val data: T)                │
│      data class Error(val code: Int, val msg: String)  │
│  }                                                     │
└────────────────────────────────────────────────────────┘
```

### 4.4 核心模块详解

#### 模块一：Retrofit + OkHttp 统一配置

```kotlin
object NetworkConfig {
    // 动态 BaseUrl — 支持运行时切换
    var baseUrl: String by Delegates.observable(BASE_URL_DEBUG) { _, _, newUrl ->
        // BaseUrl 变化时重建 Retrofit 实例（或使用 Retrofit.baseUrl(Url) 动态更新）
        rebuildRetrofit(newUrl)
    }

    // 超时配置
    val connectTimeout: Long = 15_000L
    val readTimeout: Long = 30_000L
    val writeTimeout: Long = 30_000L

    // 缓存配置
    val cacheSize: Long = 10 * 1024 * 1024L  // 10MB
    val cacheDir: File = File(context.cacheDir, "http_cache")
}
```

**多 BaseUrl 方案**：

| 方案 | 实现 | 适用场景 |
|-----|------|---------|
| `@Url` 注解 | 接口方法参数传完整 URL，跳过 baseUrl | 少数非标准接口 |
| 多 Retrofit 实例 | 不同组 API 用不同的 Retrofit 实例 | 首页/用户/支付分开 |
| `BaseUrlInterceptor` | 拦截器中根据 Header 动态替换 URL | 动态调度/灰度 |

**面试追问**：「Retrofit 的动态 BaseUrl 原理是什么？」——其核心是 `HttpUrl` 和 `RequestBuilder`。Retrofit 内部把 `baseUrl` 解析为 `HttpUrl`，然后把 `@GET("user/info")` 的 path 拼接到 baseUrl 上。如果你需要动态 BaseUrl，可以通过拦截器拿到 `Request`，用 `request.newBuilder().url(newUrl)` 替换即可。

#### 模块二：拦截器链设计

```
发起请求 → [LoggingInterceptor]
          → [HeaderInterceptor: 注入公共 Header (App版本/设备ID/渠道)]
          → [TokenInterceptor: 注入 Token / Token过期自动刷新]
          → [CacheInterceptor: 缓存策略判断]
          → [RetryInterceptor: 网络失败自动重试]
          → 发送到网络
```

**作用**：将散落在各处的网络侧逻辑收敛为独立的拦截器，单一职责，可插拔。

**每个拦截器深度解析**：

**LoggingInterceptor**：
- 开发环境输出完整请求/响应日志（URL、Headers、Body），生产环境只输出错误日志。
- 格式化 JSON Body（用 `JSONObject` 标准格式化，不要直接打印原始字符串）。

**HeaderInterceptor**：
- 注入公共 Header：`App-Version`、`Device-Id`、`Platform` (Android)、`Accept-Language`。
- **注意**：如果使用 `addHeader()` 会追加而非替换，需要 `header()` 方法或先 `removeHeader()` 再 `addHeader()`。

**TokenInterceptor**（最难的一个）：
- 从本地存储（MMKV 或 DataStore）读取 token 注入 `Authorization` Header。
- 当收到 401 响应时，自动用 refreshToken 刷新 accessToken，刷新成功则重放原请求。
- **关键难题**：「如果多个请求同时返回 401，会同时去刷新 token，导致刷新接口被调用多次怎么办？」——用一个全局的 `AtomicBoolean isRefreshing` 锁住刷新过程，后续 401 请求等待同一个 `CountDownLatch` 或挂起协程，刷新完成后统一重放。

**CacheInterceptor**：
- 有网络：请求网络，返回数据，写入 OkHttp Cache。
- 无网络：从 OkHttp Cache 读取，返回并添加 `from-cache: true` Header 告知上层业务方。
- 强制刷新：添加 `Cache-Control: no-cache` 跳过缓存。

**RetryInterceptor**：
- 仅对网络错误重试（`UnknownHostException`、`SocketTimeoutException`、`ConnectException`），HTTP 4xx/5xx 默认不重试。
- 重试次数上限 3 次，指数退避（1s, 2s, 4s）。

#### 模块三：统一响应封装与错误处理

```kotlin
// 统一响应体基类
data class BaseResponse<T>(
    val code: Int,
    val message: String,
    val data: T?
)

// 业务层使用的密封类结果
sealed class ApiResult<out T> {
    data class Success<T>(val data: T, val fromCache: Boolean = false) : ApiResult<T>()
    data class Error(val code: Int, val msg: String, val exception: Throwable? = null) : ApiResult<Nothing>()
}

// Retrofit CallAdapter 将 BaseResponse<T> 转换为 ApiResult<T>
class ApiResultCallAdapter<T : Any>(
    private val type: Type
) : CallAdapter<T, Call<ApiResult<T>>> {
    override fun adapt(call: Call<T>): Call<ApiResult<T>> = ApiResultCall(call)
}

class ApiResultCall<T : Any>(private val delegate: Call<T>) : Call<ApiResult<T>> {
    override fun execute(): Response<ApiResult<T>> {
        val response = delegate.execute()
        return Response.success(parseResponse(response))
    }

    private fun parseResponse(response: Response<T>): ApiResult<T> {
        if (!response.isSuccessful) {
            return ApiResult.Error(response.code(), "HTTP ${response.code()}")
        }
        val body = response.body()
        if (body is BaseResponse<*>) {
            return if (body.code == 0) ApiResult.Success(body.data as T, fromCache = false)
            else ApiResult.Error(body.code, body.message)
        }
        return ApiResult.Success(body!!, fromCache = false)
    }
}
```

**异常分类（5 类）**：

| 异常类型 | 示例 | 用户提示 |
|---------|------|---------|
| **网络异常** | SocketTimeoutException、UnknownHostException | "网络连接失败，请检查网络设置" |
| **HTTP 错误** | 404、500、502 | "服务器开小差了，请稍后再试" |
| **业务错误** | code!=0（如余额不足、无权限） | 展示服务端返回的 message |
| **数据解析异常** | JsonSyntaxException、空数据 | "数据格式异常" |
| **取消异常** | CancellationException（协程取消） | 吞掉不提示 |

**封装的价值**：上层 ViewModel 只需要处理 `Success` 和 `Error` 两种结果，所有的 try-catch、状态码判断、异常转换全部下沉到网络层内部。

#### 模块四：缓存策略

```
请求数据:
┌────────────────────────┐
│  选择策略:              │
│  ONLY_NETWORK  (仅网络) │
│  ONLY_CACHE    (仅缓存) │
│  CACHE_FIRST   (先缓存) │← 默认
│  NETWORK_FIRST (先网络) │
└────────────────────────┘
```

**CACHE_FIRST 模式**：先返回缓存（如果有），再请求网络，网络数据返回后通过 Flow/Channel 二次发送，UI 层自动刷新——这就是「页面秒开 + 静默刷新」的标准实践。

### 4.5 技术选型对比

| 组件 | 选型 | 理由 |
|-----|------|------|
| HTTP 引擎 | OkHttp 4.x | 连接池复用、HTTP/2、QUIC 预览支持 |
| 声明式 API | Retrofit 2.x | 注解 + 动态代理，与 OkHttp 无缝集成 |
| 序列化 | Kotlinx Serialization | 编译期代码生成，无反射，Kotlin 原生支持 |
| 协程 | 原生 kotlinx.coroutines | Retrofit 2.6+ 原生 suspend 支持 |
| 缓存 | OkHttp Cache (DiskLruCache) | 遵循 HTTP/1.1 Cache-Control Header 标准 |
| 日志 | 自定义 HttpLoggingInterceptor | 生产环境按级别过滤 |

### 4.6 加分点（面试翻盘区）

1. **连接池复用**：OkHttp 默认维护 5 个空闲连接，`keepAliveDuration` 为 5 分钟。HTTP/2 下通过多路复用，一个连接可并发处理多个请求，大幅度减少握手开销。
2. **DNS 优化**：替换默认 DNS 为 `HttpDns`（如阿里/腾讯），防止运营商 LocalDNS 劫持和调度不准确。OkHttp 通过 `.dns()` 替换接口实现。
3. **请求合并**：多个相同请求（如首页多个模块都请求用户信息）在短短 100ms 内合并为一个真实网络请求，结果分发给所有调用方。可以用 `Channel` 或 `Flow.shareIn()` 实现。
4. **数据预加载**：首页数据在 Application.onCreate 或 Splash 阶段预先请求，进入首页时直接读缓存，避免白屏等待。
5. **Mock 能力**：拦截器检测 `Mock-Enable: true` Header，返回本地 JSON 文件中的数据，支持前后端并行开发。拦截器中 `response.body()` 可以直接构造 `ResponseBody.create()`。
6. **网络质量监控**：通过 `ConnectivityManager` 监听 + 定期 ping 网关，评估当前网络质量（优秀/一般/差），动态调整超时时间和图片质量。
7. **安全防篡改**：拦截器中计算请求体 MD5，通过 `Sign` Header 传给服务端校验，防止中间人篡改。服务端每次响应也带签名，客户端校验。
8. **gRPC 替代 REST 的思考**：对于高频数据同步场景（如消息列表），gRPC 双向流 + ProtoBuf 比 REST + JSON 更高效；但 REST 调试方便、跨团队对接成本低。面试中谈到「按场景选择协议」展现架构权衡能力。
9. **Certificate Pinner**：通过 `CertificatePinner` 绑定信任的证书链，防止中间人攻击抓包——但注意如果证书到期未及时更新会导致大面积线上故障，需要配合「忽略证书」的紧急开关。

---

## 附录：面试回答框架方法论

面试官在架构设计题中考察的有一条**隐性评估线**：

| 层级 | 考察点 | 典型表现 |
|-----|-------|---------|
| L1 | 知道用什么 | 「用 Glide 加载图片」 |
| L2 | 知道为什么 | 「Glide 用四级缓存，因为…」 |
| L3 | 知道怎么实现 | 「ActiveResources 是弱引用 Map…」 |
| L4 | 知道权衡取舍 | 「ARouter vs Navigation 各有利弊…」 |
| L5 | 知道边界与坑 | 「Token 刷新时多请求并发 401 要用锁…」 |
| L6 | 能举一反三 | 「这个设计模式在 XX 框架里也是同样的思路…」 |

**建议的答题节奏**：

1. **先画图**（30s — 在白板/草稿上画出分层架构图，给面试官一个视觉锚点）
2. **讲核心模块**（5min — 挑 2-3 个最重要的模块深入展开，不要面面俱到但蜻蜓点水）
3. **主动抛出权衡**（1min — 每个设计都有 trade-off，说出来证明你思考过）
4. **留一个钩子**（30s — 抛出一个加分点但不展开，看面试官是否追问）

> **注意**：以上所有框架/库的分析均为原理性、教育性解析。实际面试中请结合实际项目经验进行融会贯通，而非机械背诵。

---

*本文档为架构设计题面试备战内容，适用于 Android 中高级/资深工程师面试准备。建议结合具体项目经验，用 STAR 法则组织回答（Situation → Task → Action → Result）。*
