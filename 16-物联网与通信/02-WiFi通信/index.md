# 02 Wi-Fi 通信

## 1. 面试高频四问：Wi-Fi Direct / 局域网通信 / Wi-Fi Aware / NSD

### 1.1 Wi-Fi Direct (P2P) 的连接流程

**面试必问：请描述 Android Wi-Fi P2P 的完整连接流程。**

Wi-Fi Direct（Android 中称为 Wi-Fi P2P）允许两台设备在无需 AP（接入点）的情况下直接建立 Wi-Fi 连接。其完整流程如下：

```
┌─────────────┐                          ┌─────────────┐
│   Device A  │                          │   Device B  │
└──────┬──────┘                          └──────┬──────┘
       │                                        │
       │ (1) WifiP2pManager.initialize()        │
       │ (2) discoverPeers()                    │
       │                                        │
       │ ──── Probe Request (广播) ────────────→│
       │ ←─── Probe Response ────────────────── │
       │                                        │
       │ (3) WIFI_P2P_PEERS_CHANGED_ACTION      │
       │ (4) requestPeers() 获取设备列表          │
       │ (5) connect() 指定目标设备               │
       │                                        │
       │ ──── GO Negotiation Request ──────────→│
       │ ←─── GO Negotiation Response ───────── │
       │ ──── GO Negotiation Confirm ──────────→│
       │                                        │
       │ (6) WIFI_P2P_CONNECTION_CHANGED_ACTION │
       │ (7) requestConnectionInfo() 获取GroupInfo│
       │                                        │
       │ ════ Wi-Fi Direct 连接建立 ════════════│
       │ ──── DHCP (GO 分配 IP) ───────────────→│
       │                                        │
       │ (8) Socket 通信                         │
       │                                        │
```

**关键 API 调用链：**

```java
// Step 1: 初始化
WifiP2pManager manager = (WifiP2pManager) getSystemService(Context.WIFI_P2P_SERVICE);
WifiP2pManager.Channel channel = manager.initialize(this, getMainLooper(), null);

// Step 2: 注册 BroadcastReceiver 监听 P2P 事件
IntentFilter filter = new IntentFilter();
filter.addAction(WifiP2pManager.WIFI_P2P_STATE_CHANGED_ACTION);
filter.addAction(WifiP2pManager.WIFI_P2P_PEERS_CHANGED_ACTION);
filter.addAction(WifiP2pManager.WIFI_P2P_CONNECTION_CHANGED_ACTION);
filter.addAction(WifiP2pManager.WIFI_P2P_THIS_DEVICE_CHANGED_ACTION);

// Step 3: 发现对等设备
manager.discoverPeers(channel, new WifiP2pManager.ActionListener() {
    @Override
    public void onSuccess() { /* 发现启动成功 */ }
    @Override
    public void onFailure(int reason) { /* 失败处理 */ }
});

// Step 4: 获取对等设备列表（在 PEERS_CHANGED 回调中）
manager.requestPeers(channel, peers -> {
    for (WifiP2pDevice device : peers.getDeviceList()) {
        // 展示可用设备
    }
});

// Step 5: 发起连接
WifiP2pConfig config = new WifiP2pConfig();
config.deviceAddress = targetDevice.deviceAddress;
// WPS 配置：PBC（按键）或 PIN（输入PIN码）
config.wps.setup = WpsInfo.PBC;

manager.connect(channel, config, new WifiP2pManager.ActionListener() {
    @Override
    public void onSuccess() { /* 连接请求已发送 */ }
    @Override
    public void onFailure(int reason) { /* 失败处理 */ }
});
```

**面试要点：**
- `discoverPeers()` 会扫描约 60 秒，期间频繁调用会失败
- 连接成功后通过 `requestConnectionInfo()` 获取 GO 的 IP 地址（通常是 `192.168.49.1`）
- Android 13+ 需要 `NEARBY_WIFI_DEVICES` 运行时权限
- Wi-Fi Direct 的最大理论速率 ≈ 250 Mbps（取决于设备支持的 Wi-Fi 标准）

---

### 1.2 Wi-Fi 局域网通信 (Socket/TCP/UDP)

**面试必问：在同一局域网下，如何实现两台 Android 设备之间的 Socket 通信？**

在同一 Wi-Fi 局域网下，两台设备通过标准 TCP/UDP Socket 通信是最常见的方案。核心流程：

**服务端（Server）：**

```java
// 1. 创建 ServerSocket，监听指定端口
ServerSocket serverSocket = new ServerSocket(8888);
// 设置超时，避免无限阻塞
serverSocket.setSoTimeout(30000);

// 2. 阻塞等待客户端连接（放在子线程）
while (!isStopped) {
    Socket client = serverSocket.accept();
    // 3. 获取输入/输出流
    DataInputStream dis = new DataInputStream(client.getInputStream());
    DataOutputStream dos = new DataOutputStream(client.getOutputStream());

    // 4. 读取数据
    int length = dis.readInt();
    byte[] buffer = new byte[length];
    dis.readFully(buffer);

    // 5. 处理 + 响应
    dos.writeUTF("OK");
    client.close();
}
```

**客户端（Client）：**

```java
// 1. 连接服务端
Socket socket = new Socket();
socket.connect(new InetSocketAddress(serverIp, 8888), 5000); // 5s超时

// 2. 发送数据
DataOutputStream dos = new DataOutputStream(socket.getOutputStream());
byte[] data = "Hello".getBytes();
dos.writeInt(data.length);
dos.write(data);
dos.flush();

// 3. 接收响应
DataInputStream dis = new DataInputStream(socket.getInputStream());
String response = dis.readUTF();

socket.close();
```

**UDP 通信（适用于实时性要求高、允许少量丢包场景）：**

```java
// 服务端监听
DatagramSocket udpSocket = new DatagramSocket(9999);
byte[] buf = new byte[1024];
DatagramPacket packet = new DatagramPacket(buf, buf.length);
udpSocket.receive(packet); // 阻塞接收
String msg = new String(packet.getData(), 0, packet.getLength());
// 获取发送方地址，可回复
InetAddress senderAddr = packet.getAddress();
int senderPort = packet.getPort();

// 客户端发送
DatagramSocket clientSocket = new DatagramSocket();
byte[] data = "UDP Message".getBytes();
DatagramPacket sendPacket = new DatagramPacket(
    data, data.length,
    InetAddress.getByName("192.168.1.100"), 9999
);
clientSocket.send(sendPacket);
```

**TCP vs UDP 选择策略：**

| 维度 | TCP | UDP |
|------|-----|-----|
| 可靠性 | 可靠，有序，有重传 | 不可靠，无序，无重传 |
| 延迟 | 较高（三次握手/ACK） | 低（无连接，直接发） |
| 适用场景 | 文件传输、指令下发 | 实时音视频、屏幕镜像 |
| 开发复杂度 | 需处理粘包/拆包 | 需自行处理丢包/乱序 |

**面试要点：**
- 所有网络操作必须在**子线程**执行，否则 `NetworkOnMainThreadException`
- `Socket`/`ServerSocket` 使用后必须 `close()`，建议用 try-with-resources
- 局域网通信需要 `INTERNET` 权限（正常权限，无需动态申请）
- 从 Android 9 开始，明文 HTTP 默认被禁止；Socket 不受此限制
- 推荐使用 `java.nio`（Non-blocking I/O）处理高并发场景

---

### 1.3 Wi-Fi Aware（周边感知 / Neighbor Awareness Networking, NAN）

**面试必问：什么是 Wi-Fi Aware？与 Wi-Fi Direct 有何区别？**

Wi-Fi Aware 是 Android 8.0 (API 26) 引入的近距离感知技术，基于 Wi-Fi Alliance 的 NAN（Neighbor Awareness Networking）协议。它允许设备在**无需连接**的情况下发现周边设备并交换少量数据。

**核心特点：**

1. **零连接发现**：设备无需建立 Wi-Fi 连接，即可通过信标帧（Beacon）在 2.4GHz/5GHz 频段广播和接收服务信息
2. **极低功耗**：比传统 Wi-Fi 扫描省电，设备按固定间隔（典型 256ms ~ 512ms）苏醒收发
3. **短消息交换**：可在发现阶段直接传递小数据（≤255 字节），无需建立 Socket
4. **按需建链**：发现目标后，可无缝升级为 Wi-Fi Direct 或传统 Wi-Fi 连接传输大数据

**核心 API 流程：**

```java
// 1. 检查设备是否支持
if (!getPackageManager().hasSystemFeature(PackageManager.FEATURE_WIFI_AWARE)) {
    // 设备不支持
}

// 2. 创建 Aware 会话
WifiAwareManager awareManager = (WifiAwareManager)
    getSystemService(Context.WIFI_AWARE_SERVICE);

// 3. 发布服务（Publisher）
PublishConfig publishConfig = new PublishConfig.Builder()
    .setServiceName("com.example.service.transfer")
    .setServiceSpecificInfo("room_101".getBytes())  // ≤ 255 字节
    .build();

AwareSession session = awareManager.attach(attachCallback, identityCallback);
session.publish(publishConfig, discoverySessionCallback, null);

// 4. 订阅服务（Subscriber）
SubscribeConfig subscribeConfig = new SubscribeConfig.Builder()
    .setServiceName("com.example.service.transfer")
    .build();

session.subscribe(subscribeConfig, discoverySessionCallback, null);

// 5. 发现匹配后的回调
DiscoverySessionCallback discoverySessionCallback = new DiscoverySessionCallback() {
    @Override
    public void onServiceDiscovered(PeerHandle peerHandle,
            byte[] serviceSpecificInfo, List<byte[]> matchFilter) {
        // 发现匹配服务，可获取对方携带的数据
        // 此时可进一步建立 Network（Wi-Fi Direct 数据通道）
    }
};
```

**Wi-Fi Aware vs Wi-Fi Direct 对比：**

| 维度 | Wi-Fi Aware | Wi-Fi Direct |
|------|-------------|--------------|
| 是否需要连接 | 否 | 是 |
| 发现距离 | ~200m（室外） | 同普通 Wi-Fi |
| 发现阶段数据传输 | 支持（≤255B） | 不支持 |
| 大文件传输 | 需升级为 Aware Network | 原生支持 |
| 功耗 | 极低 | 较高 |
| API Level | 26+ | 14+ |
| 典型场景 | 就近共享、排队、签到 | 文件传输、屏幕共享 |

**面试要点：**
- 需要 `android.permission.ACCESS_WIFI_STATE` 和 `CHANGE_WIFI_STATE`
- Android 13+ 需要 `NEARBY_WIFI_DEVICES` 权限
- 发现阶段的数据非常小，适合传递房间号、设备名、token 等
- 目前国内主流手机厂商对 Wi-Fi Aware 支持参差不齐，实际落地需做兼容

---

### 1.4 网络服务发现（NSD / mDNS）

**面试必问：如何在局域网内自动发现服务？NSD 的原理是什么？**

Android NSD（Network Service Discovery）基于 DNS-SD（DNS Service Discovery）和 mDNS（Multicast DNS），允许设备在局域网内**零配置**地发布和发现服务。

**核心原理：**

mDNS 使用 5353 端口和组播地址 `224.0.0.251`（IPv4）/ `FF02::FB`（IPv6）。设备通过组播查询 `_service._proto.local` 格式的 PTR 记录来发现服务，服务提供方组播响应。

```
┌──────────────┐        组播查询           ┌──────────────┐
│   Client     │ ─── "_http._tcp.local" ──→ │    Server    │
│  (Discover)  │ ←─── 192.168.1.42:8080 ─── │  (Register)  │
└──────────────┘                            └──────────────┘
```

**服务端注册（NsdServiceInfo 发布）：**

```java
NsdServiceInfo serviceInfo = new NsdServiceInfo();
serviceInfo.setServiceName("MyFileTransfer");
serviceInfo.setServiceType("_http._tcp.");  // 服务类型
serviceInfo.setPort(8888);

// 可选：添加属性（TXT records）
Map<String, String> attributes = new HashMap<>();
attributes.put("version", "1.0");
attributes.put("device_name", Build.MODEL);
serviceInfo.setAttributes(attributes);

nsdManager.registerService(serviceInfo,
    NsdManager.PROTOCOL_DNS_SD,
    registrationListener);
```

**客户端发现：**

```java
nsdManager.discoverServices("_http._tcp.",
    NsdManager.PROTOCOL_DNS_SD,
    new NsdManager.DiscoveryListener() {
        @Override
        public void onServiceFound(NsdServiceInfo service) {
            // 发现服务，仅含名称和类型
            // 需要 resolveService() 获取详细 IP/Port
            nsdManager.resolveService(service, resolveListener);
        }

        @Override
        public void onServiceLost(NsdServiceInfo service) {
            // 服务下线通知
        }
    });

// resolveListener 拿到完整信息
ResolveListener resolveListener = new ResolveListener() {
    @Override
    public void onServiceResolved(NsdServiceInfo info) {
        InetAddress host = info.getHost();   // IP 地址
        int port = info.getPort();           // 端口
        String name = info.getServiceName(); // 服务名称
        // 获得 IP 和端口后，建立 Socket 连接
    }
};
```

**NSD vs 手动 IP 配置对比：**

| 方案 | 优点 | 缺点 |
|------|------|------|
| NSD/mDNS | 零配置、自动发现、动态 | 依赖组播（部分路由器可能过滤） |
| 手动 IP | 简单直接 | 需要用户输入/IP 变化失效 |
| QR 码传 IP | 用户友好 | 需要摄像头权限 |

**面试要点：**
- NSD 本质是 mDNS + DNS-SD，是 Apple Bonjour 的开放标准实现
- `discoverServices()` 和 `registerService()` 的生命周期需与 Activity 绑定，退出时必须 `unregisterService()` / `stopServiceDiscovery()`
- 部分 Android 厂商对 NSD 有定制行为，测试时应覆盖主流机型
- 服务类型命名遵循 IANA 规范，如 `_http._tcp`、`_ftp._tcp`、`_ipp._tcp`
- iOS 端对应实现为 Bonjour / NSNetService

---

## 2. Wi-Fi Direct 的 GO/Client 角色协商

**面试必问：Wi-Fi Direct 连接时 GO（Group Owner）如何确定？Intent 值的作用是什么？**

Wi-Fi Direct 的连接建立过程本质上是**角色协商（GO Negotiation）**：两台设备通过三轮握手确定谁成为 GO（Group Owner），谁成为 Client。

### 2.1 GO Negotiation 三轮握手

```
Device A (Intent=10)                         Device B (Intent=5)
       │                                            │
       │ ─── GO Negotiation Request ───────────────→│
       │     (携带 A 的 Intent 值 = 10)               │
       │                                            │
       │ ←─── GO Negotiation Response ───────────── │
       │      (携带 B 的 Intent 值 = 5)               │
       │                                            │
       │ ─── GO Negotiation Confirm ───────────────→│
       │                                            │
       │ ════════ Device A 成为 GO ════════════════│
       │ ════════ Device B 成为 Client ════════════ │
```

### 2.2 Intent 值的含义与计算

Intent 是一个 0~15 的整数值（越大越倾向成为 GO）：

```java
// 通过 WifiP2pConfig 设置 Intent
WifiP2pConfig config = new WifiP2pConfig();
config.deviceAddress = targetDevice.deviceAddress;

// groupOwnerIntent: 0~15, 默认值通常为 3~7
// 值越大，越可能成为 GO
config.groupOwnerIntent = 15; // 强烈期望成为 GO
```

**协商规则：**
1. 双方比较 Intent 值，**值大者**成为 GO
2. 若 Intent 相等，则比较 **Tie breaker bit**（随机位，0 或 1）
3. Tie breaker bit 为 1 的成为 GO
4. 极端情况下，设置 `config.groupOwnerIntent = 15` 可基本确保成为 GO
5. 设置 `config.groupOwnerIntent = 0` 则基本确保成为 Client

### 2.3 GO 的职责

- 充当"微型 AP"（Access Point），运行 DHCP 服务器为 Client 分配 IP
- 维护 P2P Group 的生命周期
- GO 的 IP 通常是 `192.168.49.1`，Client 的 IP 由 GO 通过 DHCP 分配（如 `192.168.49.2`）
- 发送 Beacon 帧维持 Group
- 若 GO 断开，整个 Group 解散

### 2.4 使用 createGroup() 强制成为 GO

```java
// 不走协商，直接创建 Group 并成为 GO
manager.createGroup(channel, new WifiP2pManager.ActionListener() {
    @Override
    public void onSuccess() {
        // 本设备成为 GO，等待其他设备连接
    }
    @Override
    public void onFailure(int reason) {
        // 创建失败
    }
});

// 对方设备通过 connect() 加入该 Group
```

### 2.5 面试进阶：WPS 认证方式

连接时还需要处理 WPS（Wi-Fi Protected Setup）认证：

```java
// PBC（Push Button Configuration）：双方"按键"配对
config.wps.setup = WpsInfo.PBC;

// PIN Display：设备A显示PIN码，设备B输入
config.wps.setup = WpsInfo.DISPLAY;

// PIN Keypad：设备A输入PIN码，设备B的PIN是固定值
config.wps.setup = WpsInfo.KEYPAD;
```

**实际面试中的追问："如果用户不想弹窗确认怎么办？"**
- 使用 PBC 模式的 WPS 可减少用户交互
- Android 10+ 的 `WifiP2pConfig.Builder` 支持更简洁的配置
- 部分厂商 ROM 会忽略 WPS 设置，强制弹窗

---

## 3. GO/Client 协商的进阶问题

### 3.1 多设备连接拓扑

Wi-Fi Direct 支持星型拓扑：1 个 GO + 多个 Client（理论最多 255 个，实际约 3~8 个稳定）。

### 3.2 双模并发（Concurrent Mode）

部分设备支持同时连接 Wi-Fi AP 和 Wi-Fi Direct Group，即设备既是某个 AP 的 STA，又同时作为 P2P GO 或 Client。

### 3.3 Client 发现 GO 的时机

连接成功后，Client 通过 `requestConnectionInfo()` 获取 `WifiP2pInfo`：

```java
manager.requestConnectionInfo(channel, info -> {
    if (info.groupFormed) {
        String goIp = info.groupOwnerAddress.getHostAddress();
        boolean isGO = info.isGroupOwner;
        // Client 连接到 GO 的 IP 即可通信
    }
});
```

---

## 4. Wi-Fi Direct 连接流程图

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Wi-Fi Direct 完整连接流程                       │
└──────────────────────────────────────────────────────────────────────┘

  Device A (发起方)                          Device B (接收方)
  ════════════════                          ════════════════

  ┌─────────────┐                           ┌─────────────┐
  │ ① 初始化    │                           │ ① 初始化    │
  │ initialize()│                           │ initialize()│
  │ 注册Receiver│                           │ 注册Receiver│
  └──────┬──────┘                           └──────┬──────┘
         │                                         │
  ┌──────▼──────┐                           ┌──────▼──────┐
  │ ② 设备发现  │                           │ ② 等待发现  │
  │discoverPeers│◄──── Probe Request ───────│  被动响应    │
  │  扫描60秒   │───── Probe Response ─────►│             │
  └──────┬──────┘                           └──────┬──────┘
         │                                         │
  ┌──────▼──────┐                                  │
  │ ③ PEERS_    │                                  │
  │  CHANGED    │                                  │
  │ requestPeers│                                  │
  │ 获取设备列表 │                                  │
  └──────┬──────┘                                  │
         │                                         │
  ┌──────▼──────┐                                  │
  │ ④ 用户选择  │                                  │
  │ 目标设备    │                                  │
  └──────┬──────┘                                  │
         │                                         │
  ┌──────▼──────┐    GO Negotiation Request    ┌───▼────────┐
  │ ⑤ connect() │─────────────────────────────→│  收到连接    │
  │ Intent=10   │◄── GO Negotiation Response ──│  Intent=5   │
  │             │─── GO Negotiation Confirm ──►│             │
  └──────┬──────┘                              └──────┬──────┘
         │                                            │
  ┌──────▼──────┐                              ┌──────▼──────┐
  │⑥ 成为 GO    │                              │⑥ 成为Client │
  │ 启动DHCP服务 │                              │ 请求DHCP IP │
  │ IP:         │                              │ 获取IP:     │
  │192.168.49.1 │                              │192.168.49.x │
  └──────┬──────┘                              └──────┬──────┘
         │                                            │
  ┌──────▼──────┐                              ┌──────▼──────┐
  │⑦ CONNECTION │                              │⑦ CONNECTION │
  │  _CHANGED   │                              │  _CHANGED   │
  │requestConn- │                              │requestConn- │
  │ Info()      │                              │ Info()      │
  └──────┬──────┘                              └──────┬──────┘
         │                                            │
         └────────── Socket 通信 ─────────────────────┘
                   (TCP/UDP on GO's IP)

  ┌──────────────────────────────────────────────────────────────────┐
  │ ⑧ 断开连接: manager.removeGroup(channel, listener)               │
  │    或 directly disconnect via cancelConnect()                    │
  └──────────────────────────────────────────────────────────────────┘
```

---

## 5. 局域网文件传输的实现

**面试必问：如何实现一个局域网内的文件传输功能？请描述完整架构设计。**

### 5.1 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                   文件传输架构                            │
├──────────────┬──────────────────┬───────────────────────┤
│   发现层     │     传输层       │      应用层            │
│              │                  │                       │
│ NSD/mDNS     │  TCP Socket      │  文件分块/断点续传     │
│ Wi-Fi Direct │  HTTP Server     │  进度回调              │
│ QR码扫码     │  WebSocket       │  多文件队列            │
│ 手动IP输入   │  UDP (实时性)    │  校验(MD5/SHA256)      │
└──────────────┴──────────────────┴───────────────────────┘
```

### 5.2 方案一：TCP Socket 直连传输

**发送端核心代码：**

```java
public class FileSender {
    public static void sendFile(Socket socket, File file,
            ProgressCallback callback) throws IOException {
        DataOutputStream dos = new DataOutputStream(
            new BufferedOutputStream(socket.getOutputStream()));

        // 1. 发送文件元信息
        String fileName = file.getName();
        long fileSize = file.length();
        dos.writeUTF(fileName);
        dos.writeLong(fileSize);
        dos.flush();

        // 2. 发送文件内容（分块读取，避免 OOM）
        byte[] buffer = new byte[64 * 1024]; // 64KB chunk
        long sent = 0;
        try (FileInputStream fis = new FileInputStream(file)) {
            int bytesRead;
            while ((bytesRead = fis.read(buffer)) != -1) {
                dos.write(buffer, 0, bytesRead);
                sent += bytesRead;
                if (callback != null) {
                    int progress = (int) ((sent * 100) / fileSize);
                    callback.onProgress(fileName, progress);
                }
            }
        }
        dos.flush();
    }

    public interface ProgressCallback {
        void onProgress(String fileName, int percent);
    }
}
```

**接收端核心代码：**

```java
public class FileReceiver {
    public static void receiveFile(Socket socket, String saveDir,
            ProgressCallback callback) throws IOException {
        DataInputStream dis = new DataInputStream(
            new BufferedInputStream(socket.getInputStream()));

        // 1. 读取文件元信息
        String fileName = dis.readUTF();
        long fileSize = dis.readLong();

        // 2. 安全检查：防止路径穿越
        File saveFile = new File(saveDir,
            new File(fileName).getName());

        // 3. 读取并写入文件
        byte[] buffer = new byte[64 * 1024];
        long received = 0;
        try (FileOutputStream fos = new FileOutputStream(saveFile)) {
            int bytesRead;
            long remaining = fileSize;
            while (remaining > 0 &&
                   (bytesRead = dis.read(buffer, 0,
                       (int) Math.min(buffer.length, remaining))) != -1) {
                fos.write(buffer, 0, bytesRead);
                received += bytesRead;
                remaining -= bytesRead;
                if (callback != null) {
                    callback.onProgress(fileName,
                        (int) ((received * 100) / fileSize));
                }
            }
        }
    }
}
```

### 5.3 方案二：HTTP 内网服务器（NanoHTTPD）

在发送方设备上启动轻量 HTTP Server，接收方通过浏览器或 HttpClient 下载：

```java
// 使用 NanoHTTPD 搭建简易文件服务器
public class FileHttpServer extends NanoHTTPD {
    private final File rootDir;

    public FileHttpServer(int port, File rootDir) throws IOException {
        super(port);        // 如 8080
        this.rootDir = rootDir;
        start(NanoHTTPD.SOCKET_READ_TIMEOUT, false);
    }

    @Override
    public Response serve(IHTTPSession session) {
        String uri = session.getUri();
        File file = new File(rootDir, uri);

        if (!file.exists() || file.isDirectory()) {
            // 返回文件列表 HTML
            return newFixedLengthResponse(Response.Status.OK,
                "text/html", generateFileListHtml());
        }

        // 支持 Range 请求（断点续传）
        String rangeHeader = session.getHeaders().get("range");
        if (rangeHeader != null) {
            return serveRangeRequest(file, rangeHeader);
        }

        // 完整文件响应
        try {
            FileInputStream fis = new FileInputStream(file);
            return newChunkedResponse(Response.Status.OK,
                getMimeType(file.getName()), fis);
        } catch (FileNotFoundException e) {
            return newFixedLengthResponse(Response.Status.NOT_FOUND,
                "text/plain", "File Not Found");
        }
    }
}
```

### 5.4 关键设计决策

| 设计维度 | 推荐方案 | 原因 |
|---------|---------|------|
| 传输协议 | TCP | 文件传输要求可靠，UDP 丢包不可接受 |
| 分块大小 | 64KB | 平衡内存占用和网络利用率 |
| 并发传输 | 线程池 | `Executors.newFixedThreadPool(N)` 管理多文件 |
| 进度通知 | `LiveData` / `Flow` | MVVM 架构下进度更新 UI |
| 异步处理 | `Dispatchers.IO` | Kotlin 协程避免主线程阻塞 |
| 断点续传 | HTTP Range + 本地记录 | 大文件传输中断后可恢复 |
| 数据校验 | MD5 / SHA-256 | 传输完成后校验完整性 |

---

## 6. 局域网文件传输的高级实现

### 6.1 断点续传

```java
public class ResumableDownload {
    // 本地记录已下载的字节数
    private long getDownloadedBytes(String fileId) {
        SharedPreferences sp = context.getSharedPreferences(
            "download_state", Context.MODE_PRIVATE);
        return sp.getLong(fileId, 0);
    }

    // HTTP Range 请求
    public void resumeDownload(String url, String fileId) {
        long downloaded = getDownloadedBytes(fileId);
        HttpURLConnection conn = (HttpURLConnection)
            new URL(url).openConnection();
        conn.setRequestProperty("Range",
            "bytes=" + downloaded + "-");

        // 从 downloaded 位置继续写入
        FileOutputStream fos = new FileOutputStream(
            targetFile, true); // append mode
        // ... 读取并写入
    }
}
```

### 6.2 多文件传输队列管理

```java
public class TransferManager {
    private final BlockingQueue<TransferTask> taskQueue =
        new LinkedBlockingQueue<>();
    private final ExecutorService executor =
        Executors.newFixedThreadPool(3); // 最多3个并发传输

    public void enqueue(TransferTask task) {
        taskQueue.offer(task);
        processQueue();
    }

    private void processQueue() {
        executor.submit(() -> {
            while (!taskQueue.isEmpty()) {
                TransferTask task = taskQueue.poll();
                if (task != null) {
                    task.execute(); // 执行传输
                    // LiveData 通知 UI 队列状态更新
                }
            }
        });
    }
}
```

### 6.3 传输完整性校验

```java
public static String getFileMD5(File file) throws Exception {
    MessageDigest md = MessageDigest.getInstance("MD5");
    byte[] buffer = new byte[8192];
    try (FileInputStream fis = new FileInputStream(file)) {
        int bytesRead;
        while ((bytesRead = fis.read(buffer)) != -1) {
            md.update(buffer, 0, bytesRead);
        }
    }
    byte[] digest = md.digest();
    StringBuilder sb = new StringBuilder();
    for (byte b : digest) {
        sb.append(String.format("%02x", b));
    }
    return sb.toString();
}

// 发送端传输完成后发送 MD5
// 接收端计算本地文件 MD5 并比对
// 不一致则触发重传
```

### 6.4 Kotlin 协程封装（现代实践）

```kotlin
suspend fun transferFile(socket: Socket, file: File,
    onProgress: (Int) -> Unit
) = withContext(Dispatchers.IO) {
    val dos = DataOutputStream(
        BufferedOutputStream(socket.getOutputStream()))
    val fileName = file.name
    val fileSize = file.length()

    dos.use { out ->
        out.writeUTF(fileName)
        out.writeLong(fileSize)

        file.inputStream().buffered().use { input ->
            val buffer = ByteArray(64 * 1024)
            var sent = 0L
            while (true) {
                val bytesRead = input.read(buffer)
                if (bytesRead == -1) break
                out.write(buffer, 0, bytesRead)
                sent += bytesRead
                withContext(Dispatchers.Main) {
                    onProgress((sent * 100 / fileSize).toInt())
                }
            }
        }
    }
}
```

---

## 附录：面试速查表

### Wi-Fi Direct 核心 API

| API | 功能 | 回调 |
|-----|------|------|
| `initialize()` | 初始化 P2P 通道 | `ChannelListener` |
| `discoverPeers()` | 发现对等设备 | `ActionListener` |
| `requestPeers()` | 获取设备列表 | `PeerListListener` |
| `connect()` | 发起连接 | `ActionListener` |
| `createGroup()` | 创建 Group 成为 GO | `ActionListener` |
| `removeGroup()` | 解散 Group | `ActionListener` |
| `requestConnectionInfo()` | 获取连接信息(GO IP等) | `ConnectionInfoListener` |

### 关键权限

```xml
<!-- Wi-Fi Direct 核心权限 -->
<uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />
<uses-permission android:name="android.permission.CHANGE_WIFI_STATE" />
<uses-permission android:name="android.permission.INTERNET" />

<!-- Android 13+ (API 33) -->
<uses-permission android:name="android.permission.NEARBY_WIFI_DEVICES" />

<!-- Wi-Fi Aware 额外权限 (API 26+) -->
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
```

### 常见面试陷阱

1. **不要在主线程执行网络操作** → `NetworkOnMainThreadException`
2. **`discoverPeers()` 调用过于频繁** → 返回 `BUSY` 错误码
3. **忘记 `unregisterService()` / `stopServiceDiscovery()`** → 内存泄漏 + 持续耗电
4. **Socket 通信未指定超时** → 网络异常时永久阻塞
5. **Wi-Fi Direct 连接后 IP 获取时机** → 必须等 `CONNECTION_CHANGED` 后 `requestConnectionInfo()`
6. **文件传输未处理粘包/拆包** → 数据错乱，需自定义协议头（长度+类型+数据）
7. **Android 13+ 未申请 `NEARBY_WIFI_DEVICES`** → 扫描不到设备

---

> **总结**：Wi-Fi 通信面试的核心考察点在于对 Android 网络编程模型的整体理解——从设备发现（NSD/Wi-Fi Direct/Wi-Fi Aware）到连接建立（GO Negotiation/DHCP），再到数据传输（TCP/UDP/HTTP），最后到工程实践（断点续传/队列管理/协程封装）。掌握这套完整链路，足以应对绝大多数物联网通信相关面试题。
