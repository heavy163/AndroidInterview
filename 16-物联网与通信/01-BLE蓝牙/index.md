# BLE 蓝牙面试深度解析

> 六层递进：面试高频题 → ATT/GATT 数据结构 → 广播与连接状态机 → 连接流程图 → 心率带实战(上) → 心率带实战(下)

---

## 第一层：面试高频题（5 大核心考点）

### Q1: 详细描述 BLE 的 GATT 协议（Service / Characteristic / Descriptor）

**GATT**（Generic Attribute Profile）是 BLE 设备间数据交互的核心协议，建立在 ATT（Attribute Protocol）之上。它定义了一套**"属性表"**的数据组织结构：

```
Profile（配置文件）
 └── Service（服务）── 一组相关功能的集合
      ├── Characteristic（特征）── 核心数据单元
      │    ├── Property（读写/通知权限位）
      │    ├── Value（实际数据）
      │    └── Descriptor（描述符）── 元数据/配置
      │         ├── CCCD (Client Characteristic Configuration Descriptor)
      │         │    用于使能 Notify/Indicate
      │         ├── CUD (Characteristic User Description)
      │         │    人类可读的特征名称
      │         └── CPF (Characteristic Presentation Format)
      └── Include（引用其他 Service）
```

**关键点：**

| 层级 | Handle 分配 | UUID 长度 | 作用 |
|------|-------------|-----------|------|
| Service | 声明句柄 | 16-bit（标准）/128-bit（自定义） | 逻辑分组，如心率服务 `0x180D` |
| Characteristic | 声明句柄 + Value 句柄 | 同上 | 数据载体，如心率测量 `0x2A37` |
| Descriptor | 独立句柄 | 同上 | 配置特征行为，CCCD UUID `0x2902` |

**面试追问**：CCCD 为什么是必须的？—— 因为 Notify/Indicate 需要客户端主动使能，服务端才能推送数据，这是 BLE 的"订阅模型"，避免不必要的数据传输从而省电。

---

### Q2: BLE 从扫描到读写的完整流程

完整流程分为 **6 个阶段**：

```
阶段1: 扫描 (Scanning)
  BluetoothLeScanner.startScan(ScanCallback)
  → onScanResult() 收到 ScanRecord（含广播包 + 扫描响应包）
  → 解析设备名、Service UUID、TxPower、Manufacturer Data

阶段2: 连接 (Connection)
  BluetoothDevice#connectGatt(context, autoConnect, gattCallback)
  → onConnectionStateChange(status, newState)
  → newState == STATE_CONNECTED 即进入连接态

阶段3: 服务发现 (Service Discovery)
  BluetoothGatt#discoverServices()
  → onServicesDiscovered(status)
  → gatt.getServices() 遍历 Service 树

阶段4: 使能通知 (Enable Notification)
  找到目标 Characteristic
  → gatt.setCharacteristicNotification(characteristic, true)
  → 写 CCCD = {0x01, 0x00} (Notify) 或 {0x02, 0x00} (Indicate)

阶段5: 数据读写
  gatt.readCharacteristic(characteristic)
  → onCharacteristicRead(characteristic, status)

  gatt.writeCharacteristic(characteristic, value, writeType)
  → WRITE_TYPE_DEFAULT (需要响应) / WRITE_TYPE_NO_RESPONSE

阶段6: 接收推送
  onCharacteristicChanged(characteristic, value)
  → 解析 value（字节序！）
```

**关键细节**：`discoverServices()` 是**同步阻塞**操作，必须在 `onConnectionStateChange` 的回调线程中调用。如果使用 Kotlin 协程，需要用 `suspendCoroutine` 包装。

---

### Q3: MTU 协商对传输性能的影响

**MTU**（Maximum Transmission Unit）指 ATT 层单次可传输的最大有效载荷字节数。

**协商流程**：
```
Android (Client)                     iOS/BLE Peripheral (Server)
    |                                        |
    |──── gatt.requestMtu(512) ────────────>|
    |<─── onMtuChanged(mtu=512, status) ────|
    |                                        |
    |──── 之后每次 ATT 读写 ≤ (MTU-3) 字节 ──|
```

**性能公式**：
```
单包有效数据 = MTU - 3（ATT 头部）
传输速率   = 单包有效数据 × 连接间隔内的包数 × 连接间隔频率

示例：
  MTU=23 (默认) → 20 bytes/pkt → 传输 1KB 需要 52 包
  MTU=512       → 509 bytes/pkt → 传输 1KB 需要 3 包
  速度提升约 10~17 倍
```

**Android 实践要点**：
- Android 5.0+ 支持 `requestMtu()`，但不同厂商实现有差异
- 建议在 `onServicesDiscovered` 后立即请求 MTU，不要在连接前
- MTU 是链路层协商结果，断开后失效，每次连接都需重新请求
- **长包分包**：超过 `(MTU-3)` 的数据需业务层手动分包（或用 `writeCharacteristic` 内部处理）

---

### Q4: BLE 的省电策略（连接参数 + 扫描策略）

BLE 的核心设计目标就是低功耗，省电策略贯穿链路层到应用层：

#### 一、连接参数优化（Connection Parameters）

```
连接间隔 (Connection Interval) = 7.5ms ~ 4s（步进 1.25ms）

  ┌──── 连接事件 ────┐                     ┌── 连接事件 ──┐
  │  TX↔RX  │        │        休眠         │  TX↔RX      │
  └─────────┘        └────────────────────└──────────────┘
  |<──────── 连接间隔 (如 300ms) ──────────────────────>|

功耗 ←──── 高 ──── 延迟低 ──── 吞吐高 ──→ 低功耗 ──── 延迟高 ────→
         (7.5ms)                            (4s)
```

| 场景 | 推荐连接间隔 | 从机延迟 |
|------|-------------|----------|
| 实时音频/心率 | 20~50ms | 0 |
| 普通穿戴设备 | 50~150ms | 0~3 |
| 温湿度传感器 | 500ms~2s | 4~10 |
| 长续航标签 | 2~4s | 10+ |

**从机延迟（Slave Latency）**：允许从机跳过 N 个连接事件不回应，大幅降低功耗。

**Android 端请求**：
```java
// API 21+
bluetoothGatt.requestConnectionPriority(
    CONNECTION_PRIORITY_HIGH,      // 11.25~15ms
    CONNECTION_PRIORITY_BALANCED,  // 30~50ms
    CONNECTION_PRIORITY_LOW_POWER  // 100~125ms
);
```

#### 二、扫描策略

```java
ScanSettings.Builder builder = new ScanSettings.Builder()
    .setScanMode(ScanSettings.SCAN_MODE_LOW_POWER)  // 占空比最低
    // SCAN_MODE_BALANCED         // 平衡
    // SCAN_MODE_LOW_LATENCY      // 最高功耗，最快发现
    .setMatchMode(ScanSettings.MATCH_MODE_AGGRESSIVE)
    .setNumOfMatches(ScanSettings.MATCH_NUM_ONE_ADVERTISEMENT);

// Android 7.0+ 后台扫描限制：30分钟内最多扫30分钟
// 建议使用 PendingIntent 方案或前台 Service
```

#### 三、应用层策略

- 读完数据立刻 `disconnect()` + `close()`，不保持长连接
- 使用 Notify 代替轮询 Read
- 批量写数据用 `WRITE_TYPE_NO_RESPONSE`（无 ACK 省电）
- PHY 选择：2M PHY 比 1M PHY 传得更快，总射频时间更短

---

### Q5: BLE 与 Classic Bluetooth 全面对比

| 维度 | BLE (4.0+) | Classic Bluetooth (2.0~3.0) |
|------|------------|---------------------------|
| **设计目标** | 低功耗、间歇数据传输 | 持续大流量数据传输 |
| **功耗** | 纽扣电池数月~数年 | 需频繁充电 |
| **连接建立** | ~3ms（快速） | ~100ms |
| **数据速率** | 125Kbps~2Mbps（BLE 5.x） | 1~3Mbps (EDR) |
| **信道数** | 40 个（3 广播 + 37 数据） | 79 个 |
| **网络拓扑** | 星型 / Mesh（BLE 5） | 微微网（Piconet） |
| **协议栈** | ATT/GATT | RFCOMM / SPP / L2CAP |
| **应用场景** | 穿戴、传感器、信标 | 音频、文件传输、车载 |
| **配对方式** | Just Works / Passkey / OOB / Numeric Comparison | PIN 码 / SSP |
| **Android API** | `BluetoothLeScanner` + `BluetoothGatt` | `BluetoothSocket` + `BluetoothServerSocket` |

**关键差异总结**：
- BLE 的 **Not all GATT** 模型替代了 Classic 的 SPP 透传
- BLE 5.0 新增 **LE Audio**（LC3 编码），开始侵蚀 Classic 音频场景
- Classic 的 SDP（Service Discovery Protocol）被 BLE 的 **GATT Service Discovery** 取代

---

## 第二层：ATT 协议 + GATT 数据结构精讲

### ATT（Attribute Protocol）—— 底层通信机制

ATT 是 GATT 的**传输层协议**，定义 Client-Server 模型和 PDU 格式：

```
ATT PDU 结构：
┌──────────┬──────────┬────────────────────┐
│ Opcode   │ Handle   │ Data               │
│  1 byte  │  2 bytes │ variable (0~MTU-3) │
└──────────┴──────────┴────────────────────┘

主要 Opcode（6 类）：
1. Read Request (0x0A)  →  Read Response (0x0B)
2. Read Blob Request (0x0C) → Read Blob Response (0x0D)  // 长包续读
3. Write Request (0x12)  →  Write Response (0x13)
4. Write Command (0x52)  →  无需响应（省电）
5. Handle Value Notification (0x1B) → 无需确认
6. Handle Value Indication (0x1D) → Handle Value Confirmation (0x1E)
```

**Notify vs Indicate 本质区别**：

```
Notify（通知）：         Indicate（指示）：
Client                  Server                    Client                  Server
  |                       |                         |                       |
  |   ←─── Notification ──|  (无 ACK，快)           |   ←─── Indication ────|
  |                       |                         |─── Confirmation ────>|
  |   ←─── Notification ──|                         |                       |
                              (有 ACK，可靠但慢)
```

面试关键点：Notify 丢包由应用层保证；Indicate 由 ATT 层保证可靠，但吞吐量受限于"发一包 → 等 ACK → 再发包"的停等协议。

### UUID 全解析

```
UUID 格式：
  ┌──────────────────────────────────────────────────────┐
  │ 0000xxxx-0000-1000-8000-00805F9B34FB  ← Bluetooth Base UUID │
  └──────────────────────────────────────────────────────┘
                ↑
           16-bit 短 UUID 替换此位置

例如：
  0x180D (心率服务)    → 0000180D-0000-1000-8000-00805F9B34FB
  0x2A37 (心率测量值)  → 00002A37-0000-1000-8000-00805F9B34FB
  0x2902 (CCCD)        → 00002902-0000-1000-8000-00805F9B34FB
```

**UUID 分类**：

| 类型 | 标志位 | 示例 |
|------|--------|------|
| SIG 标准 Service UUID | `0×18xx` | 0x180A（设备信息）、0x180F（电池）、0x181C（用户数据） |
| SIG 标准 Characteristic UUID | `0x2Axx` | 0x2A19（电池电量）、0x2A29（制造商名称） |
| SIG 标准 Descriptor UUID | `0x29xx` | 0x2902 (CCCD)、0x2901 (CUD) |
| 自定义 Vendor UUID | 128-bit 全自定义 | 任何合法 128-bit UUID |

---

## 第三层：BLE 广播与连接状态机

### 广播状态机（GAP Broadcaster / Observer）

```
                          ┌──────────────────┐
                          │    Standby（空闲）  │
                          └──────┬───────┬───┘
                                 │       │
                     startAdvertising()  startScan()
                                 │       │
                    ┌────────────▼─┐  ┌──▼────────────┐
                    │  Advertising │  │   Scanning    │
                    │  (广播态)     │  │   (扫描态)     │
                    └──────┬───────┘  └──┬────────────┘
                           │              │
                    收到连接请求    onScanResult →
                           │         connectGatt()
              ┌────────────▼──────────────▼──┐
              │      Connection（连接态）      │
              └──────────────────────────────┘
```

### 广播包结构（AD Structure）

```
┌──────────┬──────────┬───────────────┐
│ Length   │ AD Type  │ AD Data       │
│ 1 byte   │  1 byte  │ Length-1 byte │
└──────────┴──────────┴──────────────┘

常见 AD Type（GAP Data Types）：
  0x01 — Flags（BR/EDR Support、LE General Discoverable...）
  0x02 — Incomplete List of 16-bit Service UUIDs
  0x03 — Complete List of 16-bit Service UUIDs
  0x08 — Shortened Local Name
  0x09 — Complete Local Name
  0x0A — Tx Power Level（用于距离估算）
  0xFF — Manufacturer Specific Data（自定义数据，iBeacon 核心）
```

### 连接状态机（GAP Peripheral / Central）

```
Peripheral（外设）侧：                 Central（中心设备）侧：
                                      
  Standby                              Standby
    │                                     │
    │ startAdvertising()                  │ startScan()
    ▼                                     ▼
  Advertising ───────────────────> Scanning
    │       (广播包携设备信息)              │
    │                                     │ onScanResult()
    │  ◄── CONNECT_IND ──────────────── connectGatt()  
    ▼                                     ▼
  Connected ──────── 双向通信 ────────> Connected
    │                                     │
    │ disconnect() 或 超时                  │ disconnect()
    ▼                                     ▼
  Standby                               Standby
```

**连接参数请求过程**：
```
Peripheral                       Central
    |                               |
    |── CONNECTION_PARAM_REQ ──────>|  （从机发起参数更新）
    |       interval_min            |
    |       interval_max            |
    |       slave_latency           |
    |       timeout                 |
    |                               |
    |<── CONNECTION_PARAM_RSP ──────|  （主机同意/拒绝）
```

**面试重点**：Android 作为 Central 时，`requestConnectionPriority()` 只是**建议**，iOS 作为 Peripheral 有最终的参数决定权（SIG 规定 Peripheral 发起参数更新时 Central 必须接受）。

---

## 第四层：BLE 连接全流程（时序图）

```
┌──────────┐          ┌──────────┐          ┌──────────────┐
│  Android │          │  BLE     │          │   Peripheral │
│  Client  │          │  Stack   │          │   (GATT Srv) │
└────┬─────┘          └────┬─────┘          └──────┬───────┘
     │                     │                       │
     │  ① startScan()      │                       │
     │────────────────────>│                       │
     │                     │   ADV_IND (广播包)      │
     │                     │<──────────────────────│
     │  onScanResult()     │                       │
     │<────────────────────│                       │
     │  (device, rssi,     │                       │
     │   scanRecord)       │                       │
     │                     │                       │
     │  ② connectGatt()    │                       │
     │────────────────────>│  CONNECT_IND           │
     │                     │───────────────────────>│
     │                     │                       │
     │                     │  LL_ENC_REQ           │
     │                     │<──────────────────────>│  (配对/加密)
     │                     │                       │
     │  onConnectionState  │                       │
     │  Change(CONNECTED)  │                       │
     │<────────────────────│                       │
     │                     │                       │
     │  ③ discoverServices │                       │
     │────────────────────>│                       │
     │                     │  Read By Group Type   │
     │                     │    Request (遍历服务)   │
     │                     │───────────────────────>│
     │                     │  Read By Type Request  │
     │                     │    (遍历特征+描述符)     │
     │                     │───────────────────────>│
     │                     │<──────── 响应 ─────────│
     │                     │                       │
     │  onServicesDiscovered│                      │
     │<────────────────────│                       │
     │                     │                       │
     │  ④ requestMtu(512)  │                       │
     │────────────────────>│  ATT MTU Exchange     │
     │                     │───────────────────────>│
     │  onMtuChanged(512)  │                       │
     │<────────────────────│                       │
     │                     │                       │
     │  ⑤ 使能 Notify       │                       │
     │  setCharaNotification│                       │
     │  (true)              │                       │
     │────────────────────>│                       │
     │  writeDescriptor     │                       │
     │  (CCCD=0x0001)       │                       │
     │────────────────────>│  Write CCCD           │
     │                     │───────────────────────>│
     │  onDescriptorWrite   │                       │
     │<────────────────────│                       │
     │                     │                       │
     │  ⑥ readCharacteristic│                      │
     │────────────────────>│  Read Request          │
     │                     │───────────────────────>│
     │                     │  Read Response (data)  │
     │                     │<───────────────────────│
     │  onCharacteristicRead│                      │
     │<────────────────────│                       │
     │                     │                       │
     │  ⑦ 数据推送（循环）    │                       │
     │                     │  Handle Value          │
     │                     │    Notification (data) │
     │                     │<───────────────────────│
     │  onCharacteristic   │                       │
     │  Changed(data)      │                       │
     │<────────────────────│                       │
     │                     │                       │
     │  ⑧ disconnect()     │                       │
     │────────────────────>│  LL_TERMINATE_IND     │
     │                     │───────────────────────>│
     │  onConnectionState  │                       │
     │  Change(DISCONNECTED)│                      │
     │                     │                       │
     │  close() 释放资源    │                       │
     └─────────────────────┴───────────────────────┘
```

**流程要点**：
1. ①②③ 必须**严格串行**执行，不可并发
2. `discoverServices()` 耗时 500~3000ms（取决于服务数量和信号质量）
3. ⑤ 必须在 ③ 之后，因为需要拿到 Characteristic 实例
4. ⑧ 之后必须 `close()`，否则 BLE Stack 资源泄漏

---

## 第五层：BLE 心率带数据读取 —— 完整实现（上）

### 业务背景

标准 BLE 心率服务定义在 [Heart Rate Profile (HRP)](https://www.bluetooth.com/specifications/specs/heart-rate-profile-1-0/)：

- **Service UUID**: `0x180D` (Heart Rate)
- **Characteristic UUID**: `0x2A37` (Heart Rate Measurement — **Notify**)
- **Characteristic UUID**: `0x2A38` (Body Sensor Location — **Read**)
- **Characteristic UUID**: `0x2A39` (Heart Rate Control Point — **Write**)
- **Descriptor UUID**: `0x2902` (CCCD — 使能通知)

### 心率数据格式解析

```
Heart Rate Measurement Value 标志字节：
┌──────────────────────┐
│ Flags (1 byte)        │
│  Bit 0: HR Value 格式 │── 0=UINT8, 1=UINT16
│  Bit 1: Sensor Contact│
│  Bit 2: Contact Support│
│  Bit 3: Energy Expended│
│  Bit 4: RR-Interval   │
│  Bits 5-7: Reserved   │
├──────────────────────┤
│ HR Value (1 or 2 B)  │  ← UINT8 或 UINT16（小端序）
├──────────────────────┤
│ (可选) Energy Expended│
├──────────────────────┤
│ (可选) RR-Interval[]  │
└──────────────────────┘
```

### Android 完整实现代码

```java
public class HeartRateManager {
    private static final UUID HR_SERVICE_UUID =
        UUID.fromString("0000180D-0000-1000-8000-00805F9B34FB");
    private static final UUID HR_MEASUREMENT_UUID =
        UUID.fromString("00002A37-0000-1000-8000-00805F9B34FB");
    private static final UUID CCCD_UUID =
        UUID.fromString("00002902-0000-1000-8000-00805F9B34FB");
    private static final UUID BODY_SENSOR_LOCATION_UUID =
        UUID.fromString("00002A38-0000-1000-8000-00805F9B34FB");

    private BluetoothGatt bluetoothGatt;
    private HeartRateCallback callback;

    public interface HeartRateCallback {
        void onHeartRateUpdated(int heartRate, @Nullable int[] rrIntervals);
        void onSensorLocation(String location);
        void onConnectionFailed(int status);
    }

    // ─── 扫描 ───
    public void startScan(BluetoothLeScanner scanner) {
        ScanFilter filter = new ScanFilter.Builder()
            .setServiceUuid(new ParcelUuid(HR_SERVICE_UUID))
            .build();

        ScanSettings settings = new ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
            .build();

        scanner.startScan(
            Collections.singletonList(filter), settings, scanCallback);
    }

    private final ScanCallback scanCallback = new ScanCallback() {
        @Override
        public void onScanResult(int callbackType, ScanResult result) {
            BluetoothDevice device = result.getDevice();
            scanner.stopScan(this);
            connectToDevice(device);
        }
    };

    // ─── 连接 + 服务发现 ───
    private void connectToDevice(BluetoothDevice device) {
        bluetoothGatt = device.connectGatt(
            context, false, gattCallback, BluetoothDevice.TRANSPORT_LE);

        // 超时保护
        handler.postDelayed(() -> {
            if (!connected) {
                disconnect();
                callback.onConnectionFailed(BluetoothGatt.GATT_FAILURE);
            }
        }, 10000);
    }

    private final BluetoothGattCallback gattCallback = new BluetoothGattCallback() {
        @Override
        public void onConnectionStateChange(BluetoothGatt gatt,
                                             int status, int newState) {
            if (newState == BluetoothProfile.STATE_CONNECTED) {
                connected = true;
                gatt.discoverServices(); // ⬅ 关键：连接成功后立即发现服务
            } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                connected = false;
                gatt.close();
            }
        }

        @Override
        public void onServicesDiscovered(BluetoothGatt gatt, int status) {
            if (status != BluetoothGatt.GATT_SUCCESS) {
                callback.onConnectionFailed(status);
                return;
            }

            // 请求提高 MTU（提高吞吐）
            gatt.requestMtu(512);

            // 读取传感器位置
            readBodySensorLocation(gatt);

            // 使能心率通知
            enableHeartRateNotification(gatt);
        }
    };

    // ─── 使能 Notify ───
    private void enableHeartRateNotification(BluetoothGatt gatt) {
        BluetoothGattService service = gatt.getService(HR_SERVICE_UUID);
        if (service == null) return;

        BluetoothGattCharacteristic characteristic =
            service.getCharacteristic(HR_MEASUREMENT_UUID);
        if (characteristic == null) return;

        // ① 开启本地通知
        gatt.setCharacteristicNotification(characteristic, true);

        // ② 写 CCCD 使能远端推送
        BluetoothGattDescriptor cccd =
            characteristic.getDescriptor(CCCD_UUID);
        if (cccd != null) {
            cccd.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE);
            gatt.writeDescriptor(cccd);
        }
    }

    // ─── 解析心率数据 ───
    @Override
    public void onCharacteristicChanged(BluetoothGatt gatt,
                                         BluetoothGattCharacteristic ch) {
        if (!HR_MEASUREMENT_UUID.equals(ch.getUuid())) return;

        byte[] data = ch.getValue();
        int flags = data[0] & 0xFF;

        boolean isUint16 = (flags & 0x01) != 0;
        boolean hasRRInterval = (flags & 0x10) != 0;

        int index = 1;
        int heartRate;
        if (isUint16) {
            // 小端序：低字节在前
            heartRate = ((data[index + 1] & 0xFF) << 8)
                      |  (data[index] & 0xFF);
            index += 2;
        } else {
            heartRate = data[index] & 0xFF;
            index += 1;
        }

        // 跳过 Energy Expended（如果存在）
        if ((flags & 0x08) != 0) index += 2;

        // 解析 RR-Interval
        int[] rrIntervals = null;
        if (hasRRInterval) {
            int count = (data.length - index) / 2;
            rrIntervals = new int[count];
            for (int i = 0; i < count; i++) {
                rrIntervals[i] = ((data[index + 1] & 0xFF) << 8)
                               |  (data[index] & 0xFF);
                index += 2;
            }
        }

        callback.onHeartRateUpdated(heartRate, rrIntervals);
    }

    // ─── 断开连接 ───
    public void disconnect() {
        if (bluetoothGatt != null) {
            bluetoothGatt.disconnect();
            bluetoothGatt.close(); // ⬅ 必须 close，释放资源
        }
        handler.removeCallbacksAndMessages(null);
    }
}
```

---

## 第六层：BLE 心率带数据读取 —— 完整实现（下）

### 线程模型与并发安全

BLE 回调默认运行在 **Binder 线程池**中，不是主线程。这意味着：

```java
// ❌ 错误：直接在回调中更新 UI（可能崩溃）
@Override
public void onCharacteristicChanged(...) {
    tvHeartRate.setText(String.valueOf(heartRate));
}

// ✅ 正确：切换到主线程
@Override
public void onCharacteristicChanged(...) {
    new Handler(Looper.getMainLooper()).post(() -> {
        tvHeartRate.setText(String.valueOf(heartRate));
    });
}
```

**串行化操作队列**：Android BLE Stack 不支持并发 ATT 操作，所有 `readCharacteristic()` / `writeCharacteristic()` / `writeDescriptor()` 必须串行执行：

```java
public class SerialBleOperator {
    private final Queue<Runnable> queue = new LinkedList<>();
    private boolean isOperating = false;

    public synchronized void enqueue(Runnable operation) {
        queue.offer(operation);
        if (!isOperating) executeNext();
    }

    private synchronized void executeNext() {
        Runnable next = queue.poll();
        if (next == null) {
            isOperating = false;
            return;
        }
        isOperating = true;
        next.run();
    }

    // 每个 GATT 回调中调用 executeNext() 触发下一个
    public void onOperationComplete() {
        executeNext();
    }
}
```

### 错误处理与重连机制

```java
// 通用错误码
private String getGattError(int status) {
    switch (status) {
        case 0x00: return "SUCCESS";
        case 0x01: return "GATT_INVALID_HANDLE";
        case 0x02: return "GATT_READ_NOT_PERMIT";
        case 0x03: return "GATT_WRITE_NOT_PERMIT";
        case 0x08: return "GATT_INSUF_AUTHENTICATION";
        case 0x0F: return "GATT_INSUF_ENCRYPTION";
        case 0x85: return "GATT_CONN_TERMINATE_PEER_USER";  // 133
        case 0x8D:
        case 0x8F: return "GATT_CONN_TIMEOUT";             // 超时
        default: return "UNKNOWN(" + status + ")";
    }
}

// 状态 133 (0x85) 是 Android 最常见的 BLE 错误
// 原因：设备已断开但本地未感知、GATT 对象失效、并发冲突
// 修复：disconnect() → close() → 重新 scan → connect
```

### Kotlin 协程封装（现代写法）

```kotlin
// 使用 kotlinx-coroutines 将回调转为 Flow
fun BluetoothGatt.connectAsFlow(): Flow<GattEvent> = callbackFlow {
    val c = object : BluetoothGattCallback() {
        override fun onConnectionStateChange(gatt: BluetoothGatt,
                                              status: Int, newState: Int) {
            trySend(GattEvent.ConnectionState(status, newState))
        }
        override fun onServicesDiscovered(gatt: BluetoothGatt, status: Int) {
            trySend(GattEvent.ServicesDiscovered(status))
        }
        override fun onCharacteristicChanged(
            gatt: BluetoothGatt, c: BluetoothGattCharacteristic) {
            trySend(GattEvent.DataReceived(c))
        }
    }
    send(GattEvent.Attached(this@connectAsFlow))
    awaitClose { close() }
}.flowOn(Dispatchers.IO)

// 使用方式
lifecycleScope.launch {
    device.connectGatt(ctx, false, /*callback*/)
        .connectAsFlow()
        .collect { event ->
            when (event) {
                is GattEvent.ConnectionState -> { /* 处理连接 */ }
                is GattEvent.DataReceived -> { /* 更新UI */ }
            }
        }
}
```

### 实战常见坑与最佳实践

| 坑 | 表现 | 解决方案 |
|----|------|----------|
| **133 错误** | `onConnectionStateChange(status=133)` | disconnect → close → 延迟500ms重连 |
| **服务发现失败** | `onServicesDiscovered(status=257)` | 确认 MTU 请求时机在发现服务之后 |
| **Notify 不生效** | `onCharacteristicChanged` 不触发 | 检查 CCCD 是否写入成功，确认特征 Property 包含 NOTIFY |
| **并发操作 crash** | BLE 操作返回 busy | 使用队列串行化所有 ATT 操作 |
| **连接泄露** | `onConnectionStateChange` 不回调 | 设置超时定时器，超时后 `disconnect()` + `close()` |
| **Android 6.0 权限** | `startScan` 无回调 | `Manifest.permission.ACCESS_FINE_LOCATION` 必须授予 |
| **后台扫描限制** | Android 8.0+ 后台无法扫描 | 前台 Service + `startForeground()` |
| **蓝牙关闭** | 操作失败 | 注册 `BluetoothAdapter.ACTION_STATE_CHANGED` 广播监听 |

### 总结：BLE 开发三原则

1. **串行化** — 所有 GATT 操作必须排队执行，禁止并发
2. **连接即 close** — 每个 `connectGatt()` 必须有对应的 `close()`，不可遗漏
3. **超时必有** — 扫描、连接、每个 GATT 操作都要设超时，因为 BLE 信号随时可能中断

---

*本文涵盖了 BLE 面试的核心考点，从协议原理到实战代码，覆盖 GATT/ATT 数据结构、广播与连接状态机、MTU 协商、省电策略，以及心率带完整实现。建议结合 Android 官方 [BLE 指南](https://developer.android.com/guide/topics/connectivity/bluetooth-le) 和 BLE 抓包工具（如 nRF Connect、Wireshark）深入实践。*
