# 03 Matter 协议

> 六层递进：面试高频问 → Cluster 模型与 Fabric 概念 → Commissioning 深入 → 网络拓扑图 → Android Matter SDK 实战(上) → Android Matter SDK 实战(下)

---

## 第一层：面试高频题（5 大核心考点）

### Q1: Matter 协议的核心设计理念是什么？统一应用层 / IP 承载 / Thread + Wi-Fi 分别扮演什么角色？

**Matter**（原名 Project CHIP，Connected Home over IP）是由 CSA（Connectivity Standards Alliance，原 Zigbee Alliance）主导，联合 Apple、Google、Amazon、Samsung 等巨头共同推出的智能家居统一标准。

**三大核心设计支柱：**

```
┌──────────────────────────────────────────────────────┐
│                  Matter 应用层                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ │
│  │ On/Off   │ │  Level   │ │  Color   │ │  Door   │ │
│  │ Cluster  │ │  Cluster │ │  Cluster │ │ Cluster │ │
│  └──────────┘ └──────────┘ └──────────┘ └─────────┘ │
├──────────────────────────────────────────────────────┤
│              统一数据模型 (Data Model)                │
├──────────────────────────────────────────────────────┤
│           Matter 交互协议 (Interaction Protocol)      │
├──────────────────────────────────────────────────────┤
│           Matter TCP/UDP (基于 IP)                   │
├────────────┬──────────────────┬──────────────────────┤
│ Thread     │      Wi-Fi       │    Ethernet          │
│ (802.15.4) │  (802.11 a/b/g/n)│   (802.3)           │
└────────────┴──────────────────┴──────────────────────┘
```

**① 统一应用层：**

Matter 的核心价值在于 **"写一次，到处运行"**。无论底层是 Thread、Wi-Fi 还是以太网，应用层的数据模型和交互逻辑完全一致。这通过标准化的 **Cluster（簇）** 来实现——每个 Cluster 定义了一种设备能力（如开/关、调光、测温），所有 Matter 设备使用相同的 Cluster 定义。

**② IP 承载（IP Bearer）：**

Matter 开创性地让智能家居设备**直接走 IP 协议栈**。这意味着：
- 设备自身拥有 IPv6 地址，可直接被局域网内任何设备发现和通信
- 不再需要厂商专用网关做协议转换，路由器就是天然的 "Hub"
- 利用成熟的 IP 安全基础设施（TLS/DTLS）
- 天然支持多管理员（Multi-Admin），一个设备可同时被 Apple Home、Google Home、Alexa 控制

**③ Thread + Wi-Fi 双传输层：**

| 传输层 | 适用场景 | 特点 |
|--------|---------|------|
| **Thread** | 电池供电设备（传感器、门锁、开关） | 低功耗、自组网 Mesh、基于 802.15.4、IPv6 原生支持 |
| **Wi-Fi** | 常供电设备（摄像头、音箱、网关） | 高带宽、现成基础设施、无需额外 Hub |
| **Ethernet** | 固定设备（电视、Hub） | 最稳定、零无线干扰 |

**面试关键点：**
- Matter **不是**一个新的物理层协议，而是基于 IP 的**应用层统一标准**
- Matter 的 IP 是 **IPv6 only**，利用 SLAAC（无状态地址自动配置）分配地址
- Thread 设备通过 **Thread Border Router（边界路由器）** 接入 Wi-Fi/IP 网络，Border Router 做 6LoWPAN ↔ IP 转换
- Matter Controller（如手机 App）通过 Wi-Fi/Ethernet 与 Thread 设备通信，全程 IP 路由

---

### Q2: Matter 的 Commissioning（入网）流程是怎样的？

Commissioning 是 Matter 设备首次加入 Fabric 的完整流程，设计了极高的安全标准。

```
阶段 0: 设备发现
  用户扫描 QR 码 / NFC / 手动输入配对码
  → 配对码 (Manual Pairing Code) = 11 位或 21 位数字
  → 包含: VendorID + ProductID + Discriminator + Passcode

阶段 1: 建立安全通道 (PASE - Password Authenticated Session Establishment)
  Commissioner (手机) 和 Device 通过 Passcode 派生共享密钥
  → 使用 SPAKE2+ 协议（基于密码的密钥交换）
  → 建立加密的 PASE Session
  → 此阶段使用 BLE / SoftAP / 已存在的 IP 网络

阶段 2: 设备认证
  Commissioner 验证设备的 DAC (Device Attestation Certificate)
  → DAC 由 CSA 授权的 PAA (Product Attestation Authority) 签发
  → 验证链路: DAC → PAI → PAA → CSA Root CA
  → 确保设备是正品 Matter 认证设备

阶段 3: 网络配置
  Commissioner 发送 Wi-Fi SSID+Password 或 Thread 网络凭据
  → 设备连接到目标 IP 网络
  → 获得 IPv6 地址

阶段 4: 建立运营通道 (CASE - Certificate Authenticated Session Establishment)
  设备已在线，双方通过证书重新建立更安全的会话
  → 使用 Sigma 协议（基于证书的密钥交换）
  → 生成 Operational Key Pair (NOC + ICAC + RCAC)

阶段 5: Fabric 加入
  Commissioner 将设备的 NOC 加入 Fabric
  → 分配 Fabric ID + Node ID
  → 此后设备与该 Fabric 绑定，设备可被该 Fabric 内的任意 Controller 控制
  → ACL (Access Control List) 配置：决定哪些 Controller 能访问哪些 Cluster
```

**面试追问：为什么要有 PASE 和 CASE 两次会话建立？**

- **PASE**：设备还没 Wi-Fi 密码，只能通过近距离的配对码建立临时信任。安全边界是"物理接近 + 知道配对码"。
- **CASE**：设备联网后，使用正式的证书链重新认证，提供更强的安全保证。PASE 只是"引荐人"，CASE 是"正式身份"。

---

### Q3: Matter vs Zigbee vs Z-Wave 全面对比

| 维度 | Matter | Zigbee 3.0 | Z-Wave |
|------|--------|------------|--------|
| **协议栈层级** | 应用层（基于 IP） | 全栈（网络+应用层） | 全栈（私有协议） |
| **传输层** | Thread / Wi-Fi / Ethernet | IEEE 802.15.4 | 私有射频（Sub-GHz） |
| **IP 原生** | ✅ IPv6 | ❌ 需网关做协议转换 | ❌ 需网关 |
| **多管理员** | ✅ Multi-Admin 原生支持 | ❌ 一般绑定单一网关 | ❌ 绑定单一控制器 |
| **互操作性** | 跨品牌跨生态 | 理论上跨品牌（Cluster Library） | Z-Wave 认证设备间 |
| **安全性** | DAC + NOC 证书链，TLS 1.3 | 网络密钥 + 链路密钥 | S2 Security（ECDH） |
| **生态系统** | Apple/Google/Amazon/Samsung | Philips Hue/IKEA/Bosch | Ring/Schlage/2GIG |
| **频段** | 2.4GHz (Thread/Wi-Fi) | 2.4GHz | 800-900MHz（各国不同） |
| **Mesh** | Thread 原生 Mesh | Zigbee 原生 Mesh | Z-Wave 原生 Mesh |
| **节点数** | ~250/Thread 网络 | ~65,000（理论） | ~232 |
| **数据速率** | Thread: 250kbps | 250kbps | 9.6/40/100kbps |
| **兼容现有设备** | ❌ 需 Matter 认证新设备 | ✅ 存量 Zigbee 设备 | ✅ 存量 Z-Wave 设备 |

**面试关键总结：**
- **Matter 不是 Zigbee 的替代者，而是统一了"上面的那层"**。Zigbee 设备可以通过 Zigbee-Matter Bridge 接入 Matter 生态。
- Matter 的最大优势是 **"去网关化"** 和 **"多生态共享"**——你买的 Matter 灯泡可以同时出现在 Apple Home 和 Google Home 里。
- Z-Wave 由于使用 Sub-GHz 频段（穿墙能力强），在北美安防市场仍有较强生命力，但生态封闭。

---

## 第二层：Matter Cluster 模型深度解析

### Cluster 模型设计哲学

Matter 将设备能力抽象为 **Cluster（簇）**，这是其最核心的设计范式。一个物理设备 = N 个 Cluster 的集合。

```
┌─────────────────────────────────────────────────────┐
│              Matter 智能灯泡 (Endpoint 0)             │
│                                                       │
│  ┌─────────────────┐  ┌────────────┐  ┌───────────┐ │
│  │  On/Off Cluster  │  │  Level     │  │  Color    │ │
│  │  (ID: 0x0006)    │  │  Control   │  │  Control  │ │
│  │                  │  │  (0x0008)  │  │  (0x0300) │ │
│  ├─────────────────┤  ├────────────┤  ├───────────┤ │
│  │ Attributes:     │  │ Attributes:│  │ Attrs:    │ │
│  │ • OnOff: bool   │  │ • Current  │  │ • Hue     │ │
│  │ • GlobalScene   │  │   Level    │  │ • Sat     │ │
│  │   Control       │  │ • Min/Max  │  │ • ColorTemp│ │
│  ├─────────────────┤  ├────────────┤  ├───────────┤ │
│  │ Commands:       │  │ Commands:  │  │ Commands: │ │
│  │ • On            │  │ • MoveTo   │  │ • MoveTo  │ │
│  │ • Off           │  │   Level    │  │   Hue     │ │
│  │ • Toggle        │  │ • Step     │  │ • MoveTo  │ │
│  ├─────────────────┤  ├────────────┤  │   ColorTemp│ │
│  │ Events:         │  │ Events:    │  └───────────┘ │
│  │ • OnOffChanged  │  │ • LevelChanged             │ │
│  └─────────────────┘  └────────────────────────────────┘
│                                                       │
│  ┌─────────────────────────────────────────────────┐ │
│  │  Descriptor Cluster (0x001D) — 每个设备必须实现   │ │
│  │  • DeviceTypeList • ServerList • ClientList      │ │
│  └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

**Cluster 三大核心元素：**

| 元素 | 说明 | 示例 |
|------|------|------|
| **Attribute（属性）** | 设备状态数据，支持读/写/订阅 | `OnOff: true` |
| **Command（命令）** | 触发设备执行动作 | `On` / `Toggle` |
| **Event（事件）** | 设备主动上报的状态变化 | `OnOffChanged` |

**Server vs Client 角色：**
- **Server Cluster**：持有属性和执行命令的一方（如灯泡的 OnOff Server）
- **Client Cluster**：发起命令和读取属性的一方（如手机 App 的 OnOff Client）

---

### OnOff Cluster 深度剖析（ID: 0x0006）

以最简单的 OnOff Cluster 为例，展示 Matter 的交互细节：

```
OnOff Cluster (Server)
┌─────────────────────────────────────────────┐
│ Attributes:                                  │
│   OnOff (0x0000): bool, default=false       │
│     → 读写属性，支持订阅                      │
│   GlobalSceneControl (0x4000): bool         │
│   OnTime (0x4001): uint16                   │
│   OffWaitTime (0x4002): uint16              │
│   StartUpOnOff (0x4003): enum               │
│     → 上电默认状态: Off/On/Toggle/Previous   │
├─────────────────────────────────────────────┤
│ Commands (Server 接收):                      │
│   Off (0x00): 无参数                         │
│   On (0x01): 无参数                          │
│   Toggle (0x02): 无参数                      │
│   OffWithEffect (0x40)                      │
│   OnWithRecallGlobalScene (0x41)            │
│   OnWithTimedOff (0x42)                     │
├─────────────────────────────────────────────┤
│ 生成的 Events:                               │
│   OnOffChanged → 属性变化后自动上报          │
└─────────────────────────────────────────────┘
```

**Invoke 交互流程（以 Turn On 为例）：**

```
Controller (手机App)                        Device (灯泡)
    │                                           │
    │── InvokeRequest ────────────────────────→│
    │   {                                       │
    │     CommandPath: {                        │
    │       EndpointId: 1,                      │
    │       ClusterId: 0x0006,                  │
    │       CommandId: 0x01  // On              │
    │     },                                    │
    │     CommandFields: null (On 无参数)        │
    │   }                                       │
    │                                           │
    │   // 设备执行开灯，更新属性                   │
    │   // OnOff Attribute = true                │
    │                                           │
    │←── InvokeResponse ───────────────────────│
    │   { Status: SUCCESS }                     │
    │                                           │
    │←── ReportData (订阅上报) ────────────────│
    │   {                                       │
    │     AttributeReport: {                    │
    │       AttributeData: {                    │
    │         Path: {ClusterId:6, AttributeId:0},│
    │         Data: true  // OnOff = true       │
    │       }                                   │
    │     }                                     │
    │   }                                       │
```

**面试要点：**
- Invoke 是同步确认模型——发命令 → 等响应 → 收状态上报
- 属性订阅（Subscribe）是 Matter 的高效推送机制，避免轮询
- 每个 Cluster 的 Attribute ID 和 Command ID 是**全局唯一且跨厂商一致**的

---

## 第三层：Fabric 概念深入

### 什么是 Fabric？

**Fabric**（织物）是 Matter 中的**安全域/管理域**概念，代表一个独立的控制生态系统。每个 Matter 设备可同时属于多个 Fabric（最多 5 个）。

```
                    ┌──────────────────────────────────────────┐
                    │          Matter Smart Lock                │
                    │                                          │
                    │  Fabric 1 (Apple Home)                   │
                    │    NOC_1 | ACL_1 | Node ID: 0x1001       │
                    │    Bob的iPhone → 可开锁                   │
                    │                                          │
                    │  Fabric 2 (Google Home)                  │
                    │    NOC_2 | ACL_2 | Node ID: 0x2002       │
                    │    Living Room Display → 可开锁           │
                    │                                          │
                    │  Fabric 3 (Amazon Alexa)                 │
                    │    NOC_3 | ACL_3 | Node ID: 0x3003       │
                    │    Echo Dot → 仅可查看状态（不可开锁）     │
                    │                                          │
                    │  Fabric 4-5 (空，可额外添加)              │
                    └──────────────────────────────────────────┘
```

**Fabric 的核心组成：**

| 组件 | 全称 | 作用 |
|------|------|------|
| **NOC** | Node Operational Certificate | 设备在该 Fabric 中的身份证书，由 Controller 签发 |
| **ICAC** | Intermediate CA Certificate | 中间 CA 证书（可选） |
| **RCAC** | Root CA Certificate | Fabric 的根 CA 证书 |
| **ACL** | Access Control List | 控制哪些 Controller / 哪些 Subject 能访问哪些 Cluster |
| **Fabric ID** | 64-bit 标识符 | 全局唯一标识一个 Fabric |
| **Node ID** | 64-bit 标识符 | 设备在该 Fabric 内的唯一编号 |

---

### Multi-Admin（多管理员）—— Matter 的杀手锏

Multi-Admin 允许一个设备同时被多个生态系统控制，无需重新配对：

```
Commissioning 流程：
  1. 用户用 Apple Home 给灯泡配网 → Fabric 1 建立
  2. 用户打开 Google Home → 选择"添加 Matter 设备"
  3. 灯泡已在线，Google Home 通过 CASE 建立新会话
  4. 用户确认添加后 → Google Home 签发新的 NOC → Fabric 2 建立
  5. 灯泡现在可同时被 Apple Home 和 Google Home 控制！
```

**安全边界：**
- 每个 Fabric 有独立的证书体系和 ACL
- Fabric 之间互相隔离，一个 Fabric 的 Controller 看不到另一个 Fabric 的配置
- 设备的 DAC（出厂证书）与 Fabric 绑定无关，移除 Fabric 不影响设备的 Matter 认证身份

**面试追问：Fabric 数量为何限制为 5 个？**

每个 Fabric 需要存储：NOC（~300 bytes）+ ICAC（~300 bytes）+ RCAC（~300 bytes）+ ACL（~200 bytes）≈ 1.1 KB/fabric。对于资源受限的 Thread 设备（如门锁仅有 256KB Flash），5 个 Fabric 是工程权衡的结果。

---

## 第四层：Matter 网络拓扑图

### 典型智能家居 Matter 网络拓扑

```
                         ┌──────────────────────────────────────────────┐
                         │              互联网 (IPv4/IPv6)                 │
                         └──────┬───────────────────┬───────────────────┘
                                │                   │
                    ┌───────────┴──────┐   ┌────────┴──────────┐
                    │  Matter Hub /    │   │   Remote Access   │
                    │  Border Router   │   │   (云端控制)       │
                    │  (Apple TV/      │   └───────────────────┘
                    │   Nest Hub/      │
                    │   SmartThings)   │
                    └──┬──────────┬────┘
                       │          │
          ┌────────────┴─┐  ┌────┴──────────────────────────────┐
          │  Wi-Fi 网络   │  │  Thread 网络 (802.15.4 Mesh)      │
          │  (2.4/5GHz)  │  │                                    │
          │              │  │  ┌──────────┐    ┌──────────┐     │
          │ ┌──────────┐ │  │  │ Thread   │    │ Thread   │     │
          │ │Matter    │ │  │  │ End      │◄──►│ Router   │     │
          │ │Camera    │ │  │  │ Device   │    │ Device   │     │
          │ │(Wi-Fi)   │ │  │  │(Sensor)  │    │(Smart    │     │
          │ └──────────┘ │  │  └──────────┘    │ Plug)    │     │
          │              │  │        │         └────┬─────┘     │
          │ ┌──────────┐ │  │        │              │           │
          │ │Matter    │ │  │  ┌──────┴──────┐  ┌───┴───────┐  │
          │ │Speaker   │ │  │  │ Thread      │  │ Thread    │  │
          │ │(Wi-Fi)   │ │  │  │ Router      │  │ End Device│  │
          │ └──────────┘ │  │  │(Light Bulb) │  │(Door Lock)│  │
          │              │  │  └─────────────┘  └───────────┘  │
          │              │  │       ▲                           │
          │              │  │       │  Thread Border Router     │
          │              │  │       │  (在 Matter Hub 内)        │
          └──────────────┘  └───────┼───────────────────────────┘
                                    │
                         ┌──────────┴──────────┐
                         │  Zigbee-Matter      │
                         │  Bridge             │
                         │  (如 Philips Hue    │
                         │   Bridge v2)        │
                         └──────┬──────────────┘
                                │ Zigbee
                    ┌───────────┼───────────┐
               ┌────┴───┐  ┌───┴────┐  ┌───┴────┐
               │ Zigbee │  │ Zigbee │  │ Zigbee │
               │ Bulb   │  │ Sensor │  │ Switch │
               └────────┘  └────────┘  └────────┘
```

**关键角色说明：**

| 角色 | 作用 | 典型产品 |
|------|------|---------|
| **Matter Controller** | 控制设备、管理 Fabric | 手机 App（Apple Home / Google Home） |
| **Matter Hub / Border Router** | Thread ↔ Wi-Fi 路由、远程访问、本地自动化 | Apple TV 4K / Nest Hub / SmartThings Station |
| **Matter End Device** | 被控制的终端设备 | 灯泡、门锁、传感器 |
| **Bridge** | 将非 Matter 协议设备桥接进 Matter | Philips Hue Bridge / Aqara Hub |

**面试追问：Matter Hub 断网了还能用吗？**

可以。本地局域网通信不依赖云端，Matter Controller（手机）与 Matter Device 在同一 IP 网络下即可直接控制。但远程访问（从 4G/5G 控制家中设备）需要 Hub 做云代理转发。

---

## 第五层：Android 集成 Matter SDK（上）—— 环境搭建与设备发现

### Matter SDK for Android 架构

```
┌─────────────────────────────────────────────┐
│          Android App (Kotlin/Java)          │
├─────────────────────────────────────────────┤
│       Matter API (Google Play Services)     │
│    ┌─────────────────────────────────────┐  │
│    │  CommissioningClient                │  │
│    │  • discoverCommissioners()          │  │
│    │  • commissionDevice()               │  │
│    ├─────────────────────────────────────┤  │
│    │  MatterClient                       │  │
│    │  • getDevices()                     │  │
│    │  • readAttribute()                  │  │
│    │  • invokeCommand()                  │  │
│    │  • subscribeAttribute()             │  │
│    └─────────────────────────────────────┘  │
├─────────────────────────────────────────────┤
│    Google Play Services (Matter Module)     │
├─────────────────────────────────────────────┤
│         Matter Native Stack (C++)           │
└─────────────────────────────────────────────┘
```

**Android 端集成 Matter 有两种方案：**

| 方案 | 优点 | 缺点 |
|------|------|------|
| **Google Play Services Matter API** | 自动更新、免编译原生栈、包体小 | 依赖 GPS，旧设备不支持 |
| **自编译 Matter SDK** | 完全控制、可深度定制 | 包体大（~15MB .so）、需处理 OTA 更新 |

---

### Step 1: 添加依赖与权限

```kotlin
// build.gradle.kts (Module)
dependencies {
    // Google Play Services Matter API (推荐)
    implementation("com.google.android.gms:play-services-matter:1.0.0")
    
    // 或者使用自编译 AAR（从 Matter GitHub 源码构建）
    // implementation(files("libs/CHIPController.aar"))
}

// AndroidManifest.xml
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.CHANGE_WIFI_MULTICAST_STATE" />
<uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />
<uses-permission android:name="android.permission.CHANGE_WIFI_STATE" />
<!-- Android 12+ 需要以下权限连接 Wi-Fi 设备 -->
<uses-permission android:name="android.permission.NEARBY_WIFI_DEVICES" />
<!-- BLE 扫描（Commissioning 阶段需要） -->
<uses-permission android:name="android.permission.BLUETOOTH_SCAN" />
<uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />
<!-- 前台 Service（保持 Commissioning 不被打断） -->
<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />

<application>
    <!-- 声明 Matter Service -->
    <service
        android:name="com.google.android.gms.matter.MatterService"
        android:exported="true">
        <intent-filter>
            <action android:name="com.google.android.gms.matter.START" />
        </intent-filter>
    </service>
</application>
```

---

### Step 2: 设备发现（Discovery）

```kotlin
class MatterDiscoveryManager(private val context: Context) {
    
    private val matterClient: MatterClient by lazy {
        Matter.getClient(context)
    }
    
    /**
     * 启动 Commissioning 发现
     * 扫描通过 BLE 或 mDNS 广播的待配网 Matter 设备
     */
    fun startDiscovery(): Flow<MatterDevice> = callbackFlow {
        val request = CommissioningRequest.Builder()
            .setDiscoveryMode(DiscoveryMode.ALL) // BLE + mDNS
            .setDiscoveryTimeoutSeconds(30)
            .build()
        
        val task = matterClient.commissioningClient
            .startDiscovery(request)
            .addOnSuccessListener { discoveries ->
                discoveries.forEach { device ->
                    trySend(
                        MatterDevice(
                            discriminator = device.discriminator,
                            vendorId = device.vendorId,
                            productId = device.productId,
                            deviceName = device.deviceName ?: "Unknown",
                            pairingHint = device.pairingHint
                        )
                    )
                }
                close()
            }
            .addOnFailureListener { e ->
                close(e.cause)
            }
        
        awaitClose {
            task.cancel()
        }
    }
    
    data class MatterDevice(
        val discriminator: Int,       // 12-bit 鉴别码
        val vendorId: Int,            // CSA 分配的厂商 ID
        val productId: Int,           // 产品 ID
        val deviceName: String,       // 设备名称
        val pairingHint: Int          // 配对方式提示 (QR/BLE/NFC)
    )
}
```

**发现阶段的关键点：**
- Discriminator：12-bit 数值（0x000~0xFFF），在 QR 码中编码，用于初步区分设备
- 发现走 mDNS（Wi-Fi 网络下的 Service Discovery）或 BLE 广播
- Vendor ID + Product ID 可查询 CSA 数据库确认设备类型（灯泡/门锁/传感器等）

---

## 第六层：Android 集成 Matter SDK（下）—— Commissioning 与设备控制

### Step 3: Commissioning（配网入 Fabric）

```kotlin
class MatterCommissioningManager(private val context: Context) {
    
    private val matterClient: MatterClient by lazy {
        Matter.getClient(context)
    }
    
    /**
     * 执行完整的 Commissioning 流程
     * @param setupPayload 从 QR 码或 Manual Pairing Code 解析的配网信息
     * @param wifiSsid 目标 Wi-Fi SSID
     * @param wifiPassword 目标 Wi-Fi 密码
     */
    suspend fun commissionDevice(
        setupPayload: SetupPayload,
        wifiSsid: String,
        wifiPassword: String
    ): CommissioningResult = suspendCoroutine { continuation ->
        
        // 1. 解析配网码
        val payload = when (setupPayload) {
            is SetupPayload.QRCode -> {
                // 从 QR 码解析: MT:Y.K90QY01E0648G00
                // MT = Matter, Y = 版本, K90 = Vendor, QY01E = Product...
                SetupPayloadParser.parseQrCode(setupPayload.qrContent)
            }
            is SetupPayload.ManualCode -> {
                // 从 Manual Pairing Code 解析: 34970112332
                SetupPayloadParser.parseManualPairingCode(setupPayload.code)
            }
        }
        
        // 2. 构建 Wi-Fi 凭据
        val networkCredentials = NetworkCredentials.Builder()
            .setWiFiCredentials(
                WiFiCredentials.Builder()
                    .setSsid(wifiSsid.toByteArray())
                    .setPassword(wifiPassword.toByteArray())
                    .setSecurityType(WiFiSecurityType.WPA2_PSK)
                    .build()
            )
            .build()
        
        // 3. 执行 Commissioning
        val request = CommissioningRequest.Builder()
            .setSetupPayload(payload)
            .setNetworkCredentials(networkCredentials)
            .setFabricId(generateFabricId()) // 当前生态的 Fabric ID
            .setCommissioningTimeoutSeconds(120)
            .build()
        
        matterClient.commissioningClient
            .commissionDevice(request)
            .addOnSuccessListener { result ->
                continuation.resume(
                    CommissioningResult(
                        nodeId = result.nodeId,
                        fabricId = result.fabricId,
                        deviceType = result.deviceType
                    )
                )
            }
            .addOnFailureListener { e ->
                continuation.resumeWithException(e)
            }
    }
    
    /**
     * Commissioning 进度监听
     */
    fun observeCommissioningProgress(): Flow<CommissioningStep> = callbackFlow {
        val listener = CommissioningStateListener { state ->
            val step = when (state) {
                is CommissioningState.Discovering -> 
                    CommissioningStep.Discovering
                is CommissioningState.EstablishingPaseSession -> 
                    CommissioningStep.EstablishingPase
                is CommissioningState.Authenticating -> 
                    CommissioningStep.Authenticating(state.percent)
                is CommissioningState.ConfiguringNetwork -> 
                    CommissioningStep.ConfiguringNetwork
                is CommissioningState.EstablishingCaseSession -> 
                    CommissioningStep.EstablishingCase
                is CommissioningState.Completed -> 
                    CommissioningStep.Completed(state.nodeId)
                is CommissioningState.Failed -> 
                    CommissioningStep.Failed(state.errorMessage)
            }
            trySend(step)
        }
        
        matterClient.commissioningClient
            .addCommissioningStateListener(listener)
        
        awaitClose {
            matterClient.commissioningClient
                .removeCommissioningStateListener(listener)
        }
    }
}

sealed class CommissioningStep {
    object Discovering : CommissioningStep()
    object EstablishingPase : CommissioningStep()
    data class Authenticating(val percent: Int) : CommissioningStep()
    object ConfiguringNetwork : CommissioningStep()
    object EstablishingCase : CommissioningStep()
    data class Completed(val nodeId: Long) : CommissioningStep()
    data class Failed(val error: String) : CommissioningStep()
}
```

---

### Step 4: 设备控制（读/写/订阅）

```kotlin
class MatterDeviceController(
    private val context: Context,
    private val nodeId: Long
) {
    private val matterClient: MatterClient by lazy { 
        Matter.getClient(context) 
    }
    
    /**
     * 开关灯（OnOff Cluster）
     */
    suspend fun toggleLight(): Boolean = suspendCoroutine { cont ->
        val request = InvokeCommandRequest.Builder()
            .setNodeId(nodeId)
            .setEndpointId(1)               // Endpoint 1 = 灯泡
            .setClusterId(0x0006)           // OnOff Cluster
            .setCommandId(0x02)             // Toggle 命令
            .build()
        
        matterClient.deviceClient
            .invokeCommand(request)
            .addOnSuccessListener { response ->
                cont.resume(response.status == CommandStatus.SUCCESS)
            }
            .addOnFailureListener { cont.resumeWithException(it) }
    }
    
    /**
     * 读取当前开关状态
     */
    suspend fun readOnOffState(): Boolean = suspendCoroutine { cont ->
        val request = ReadAttributeRequest.Builder()
            .setNodeId(nodeId)
            .setEndpointId(1)
            .setClusterId(0x0006)           // OnOff Cluster
            .setAttributeId(0x0000)         // OnOff Attribute
            .build()
        
        matterClient.deviceClient
            .readAttribute(request)
            .addOnSuccessListener { response ->
                // OnOff 属性是 bool 类型
                val value = response.attributeValue.asBoolean()
                cont.resume(value)
            }
            .addOnFailureListener { cont.resumeWithException(it) }
    }
    
    /**
     * 订阅 OnOff 状态变化（实时推送）
     */
    fun subscribeOnOffState(): Flow<Boolean> = callbackFlow {
        val request = SubscribeAttributeRequest.Builder()
            .setNodeId(nodeId)
            .setEndpointId(1)
            .setClusterId(0x0006)
            .setAttributeId(0x0000)
            .setMinIntervalSeconds(0)       // 最小报告间隔
            .setMaxIntervalSeconds(60)      // 最大报告间隔（心跳）
            .build()
        
        val listener = AttributeChangeListener { report ->
            val newValue = report.attributeValue.asBoolean()
            trySend(newValue)
        }
        
        matterClient.deviceClient
            .subscribeAttribute(request, listener)
            .addOnFailureListener { close(it.cause) }
        
        awaitClose {
            matterClient.deviceClient
                .unsubscribeAttribute(nodeId, 1, 0x0006, 0x0000)
        }
    }
    
    /**
     * 设置色温（Color Control Cluster）
     */
    suspend fun setColorTemperature(mireds: Int): Boolean {
        val request = InvokeCommandRequest.Builder()
            .setNodeId(nodeId)
            .setEndpointId(1)
            .setClusterId(0x0300)           // Color Control Cluster
            .setCommandId(0x000A)           // MoveToColorTemperature
            .setCommandFields(
                mapOf(
                    0 to mireds,            // ColorTemperatureMireds
                    2 to 0                  // TransitionTime (0=即时)
                )
            )
            .build()
        
        return suspendCoroutine { cont ->
            matterClient.deviceClient
                .invokeCommand(request)
                .addOnSuccessListener { 
                    cont.resume(it.status == CommandStatus.SUCCESS) 
                }
                .addOnFailureListener { cont.resumeWithException(it) }
        }
    }
}
```

---

### Step 5: 多设备管理与 Fabric 维护

```kotlin
class MatterFabricManager(private val context: Context) {
    
    private val matterClient: MatterClient by lazy {
        Matter.getClient(context)
    }
    
    /**
     * 获取当前 Fabric 下所有设备
     */
    suspend fun getDevices(): List<MatterDeviceInfo> {
        return suspendCoroutine { cont ->
            matterClient.deviceClient
                .getDevices()
                .addOnSuccessListener { devices ->
                    cont.resume(devices.map { device ->
                        MatterDeviceInfo(
                            nodeId = device.nodeId,
                            vendorId = device.vendorId,
                            productId = device.productId,
                            deviceType = resolveDeviceType(
                                device.vendorId, 
                                device.productId
                            ),
                            isOnline = device.isOnline,
                            lastSeenTimestamp = device.lastSeenTimestamp
                        )
                    })
                }
                .addOnFailureListener { cont.resumeWithException(it) }
        }
    }
    
    /**
     * 从 Fabric 中移除设备（解绑）
     * 注意：只是该 Fabric 解绑，设备仍属于其他 Fabric
     */
    suspend fun removeDevice(nodeId: Long): Boolean {
        return suspendCoroutine { cont ->
            matterClient.commissioningClient
                .removeDevice(nodeId)
                .addOnSuccessListener { cont.resume(true) }
                .addOnFailureListener { cont.resume(false) }
        }
    }
    
    /**
     * 工厂重置设备（清除所有 Fabric 绑定）
     * 需要设备物理操作确认（如长按按钮）
     */
    suspend fun factoryResetDevice(nodeId: Long): Boolean {
        val request = InvokeCommandRequest.Builder()
            .setNodeId(nodeId)
            .setEndpointId(0)               // Endpoint 0
            .setClusterId(0x0030)           // General Commissioning Cluster
            .setCommandId(0x0003)           // ArmFailSafe
            .setCommandFields(mapOf(0 to 0)) // ExpiryLengthSeconds=0 立即触发
            .build()
        
        return suspendCoroutine { cont ->
            matterClient.deviceClient
                .invokeCommand(request)
                .addOnSuccessListener { cont.resume(true) }
                .addOnFailureListener { cont.resume(false) }
        }
    }
    
    data class MatterDeviceInfo(
        val nodeId: Long,
        val vendorId: Int,
        val productId: Int,
        val deviceType: String,
        val isOnline: Boolean,
        val lastSeenTimestamp: Long
    )
}
```

---

### Android 端集成关键注意事项

| 注意事项 | 说明 |
|----------|------|
| **线程模型** | Matter SDK 的回调可能不在主线程，所有 UI 更新需 `post` 到主线程 |
| **生命周期绑定** | Commissioning 是长流程（~30-120s），必须绑定前台 Service 防止被系统 Kill |
| **GPS 依赖** | GPS Matter API 依赖 Google Play Services ≥ 22.0，需运行时检查可用性 |
| **Wi-Fi 频段** | Thread 设备配网时不支持 5GHz Only 的 Wi-Fi，需确保手机连接 2.4GHz |
| **BLE 兼容性** | 部分 Android 设备 BLE 扫描在 Commissioning 阶段不稳定，需增加重试逻辑 |
| **内存管理** | 自编译 .so 约 15MB，需考虑 split APK 或 App Bundle 按架构分发 |
| **测试设备** | 建议使用 ESP32-C6（Thread + Wi-Fi 双模）开发板做 Matter 设备端调试 |

---

**总结：Matter 协议通过 "统一应用层 + IP 承载 + Cluster 模型 + Multi-Fabric" 四大设计，正在重塑智能家居的互操作性格局。对于 Android 开发者而言，理解 Cluster 模型和 Commissioning 流程是集成 Matter SDK 的基础，而利用 Multi-Admin 能力打造跨生态体验则是核心竞争优势。**
