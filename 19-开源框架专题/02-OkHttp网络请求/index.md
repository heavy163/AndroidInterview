# 02 OkHttp 网络请求

> 面向中高级 Android 岗位的 OkHttp 深度面试内容，覆盖拦截器链、连接池复用、HTTP/2 多路复用等核心机制。按六层递进结构展开：面试问题 → 标准答案 → 原理深挖 → 流程图 → 源码分析 → 实战应用。

---

## 目录

1. [OkHttp 五大拦截器链详解](#1-okhttp-五大拦截器链详解)
2. [连接池复用机制与 CleanupRunnable](#2-连接池复用机制与-cleanuprunnable)
3. [HTTP/2 多路复用原理](#3-http2-多路复用原理)
4. [DNS 优化策略](#4-dns-优化策略)
5. [RealInterceptorChain 责任链模式深度解析](#5-realinterceptorchain-责任链模式深度解析)
6. [连接池淘汰算法源码分析](#6-连接池淘汰算法源码分析)
7. [Http2Connection 流管理机制](#7-http2connection-流管理机制)
8. [拦截器链完整流程图](#8-拦截器链完整流程图)
9. [自定义拦截器实战](#9-自定义拦截器实战)

---

## 1. OkHttp 五大拦截器链详解

### 问题

> "OkHttp 的拦截器链包含哪些拦截器？它们的执行顺序是怎样的？每个拦截器都在做什么？如果让你设计，你会怎么安排它们的顺序？"

### 答题思路

回答这道题要从**宏观架构**到**微观职责**逐层展开。先说五大拦截器的名称和顺序，再逐个讲清职责，最后总结为什么是这个顺序（不可颠倒——比如 Bridge 必须在 Cache 之后因为需要先确定缓存策略；Connect 必须在 CallServer 之前因为需要先建立连接）。如果能画出拦截器链的串联关系图，会是非常漂亮的加分项。

### 标准答案

OkHttp 内部定义了**五大内置拦截器**，按固定顺序链式执行：

```
用户自定义拦截器 (addInterceptor)
        ↓
RetryAndFollowUpInterceptor     ← ① 重试与重定向
        ↓
BridgeInterceptor               ← ② 桥接与应用层头部
        ↓
CacheInterceptor                ← ③ 缓存策略
        ↓
ConnectInterceptor              ← ④ 建立连接
        ↓
用户网络拦截器 (addNetworkInterceptor)
        ↓
CallServerInterceptor           ← ⑤ 发送请求与读取响应
```

---

#### ① RetryAndFollowUpInterceptor — 重试与重定向

**职责**：失败重试 + 重定向跟随。

```java
// okhttp3/internal/http/RetryAndFollowUpInterceptor.java
@Override public Response intercept(Chain chain) throws IOException {
    Request request = chain.request();
    RealInterceptorChain realChain = (RealInterceptorChain) chain;
    Transmitter transmitter = realChain.transmitter();

    int followUpCount = 0;
    Response priorResponse = null;
    while (true) {
        transmitter.prepareToConnect(request);

        if (transmitter.isCanceled()) {
            throw new IOException("Canceled");
        }

        Response response;
        boolean success = false;
        try {
            response = realChain.proceed(request, transmitter, null);
            success = true;
        } catch (RouteException e) {
            // 路由异常 → 检查是否可恢复重试
            if (!recover(e.getLastConnectException(), transmitter, false, request)) {
                throw e.getFirstConnectException();
            }
            continue; // 重试
        } catch (IOException e) {
            // IO 异常 → 检查是否已建立连接
            boolean requestSendStarted = !(e instanceof ConnectionShutdownException);
            if (!recover(e, transmitter, requestSendStarted, request)) throw e;
            continue; // 重试
        } finally {
            if (!success) {
                transmitter.exchangeDoneDueToException();
            }
        }

        // 处理重定向 / 认证
        Request followUp = followUpRequest(response);
        if (followUp == null) {
            return response; // 无需重定向，返回响应
        }

        // 超过最大重定向次数 (默认 20 次)
        if (++followUpCount > MAX_FOLLOW_UPS) {
            throw new ProtocolException("Too many follow-up requests: " + followUpCount);
        }
        request = followUp;
        priorResponse = response;
    }
}
```

核心能力：
- **路由异常恢复**：如果 DNS 解析失败或连接超时，尝试下一个 Route
- **连接关闭恢复**：如果服务端主动关闭了连接 (ConnectionShutdownException)，创建新连接重试
- **重定向处理**：301/302/303/307/308/401(认证)/503(Retry-After)
- **最大重定向次数**：默认 20 次，防止无限重定向循环

**是否可重试的判断逻辑** (`recover` 方法)：

```java
private boolean recover(IOException e, Transmitter transmitter,
                        boolean requestSendStarted, Request userRequest) {
    // 1. 客户端配置不允许重试 → false
    if (!client.retryOnConnectionFailure()) return false;

    // 2. 请求已发送（无法安全重试的幂等性问题）→ false
    if (requestSendStarted && requestIsOneShot(e, userRequest)) return false;

    // 3. 非致命异常 → false
    if (!isRecoverable(e, requestSendStarted)) return false;

    // 4. 无更多路由可用 → false
    if (!transmitter.canRetry()) return false;

    return true;
}
```

---

#### ② BridgeInterceptor — 桥接与应用层头部

**职责**：将用户构建的 `Request` 转换为符合 HTTP 规范的网络请求，并将网络响应转换回对用户友好的 `Response`。

```java
// okhttp3/internal/http/BridgeInterceptor.java
@Override public Response intercept(Chain chain) throws IOException {
    Request userRequest = chain.request();
    Request.Builder requestBuilder = userRequest.newBuilder();

    RequestBody body = userRequest.body();
    if (body != null) {
        // 自动添加 Content-Type
        MediaType contentType = body.contentType();
        if (contentType != null) {
            requestBuilder.header("Content-Type", contentType.toString());
        }
        // 自动添加 Content-Length / Transfer-Encoding
        long contentLength = body.contentLength();
        if (contentLength != -1) {
            requestBuilder.header("Content-Length", Long.toString(contentLength));
            requestBuilder.removeHeader("Transfer-Encoding");
        } else {
            requestBuilder.header("Transfer-Encoding", "chunked");
            requestBuilder.removeHeader("Content-Length");
        }
    }

    // 自动添加 Host 头
    if (userRequest.header("Host") == null) {
        requestBuilder.header("Host", hostHeader(userRequest.url(), false));
    }

    // 自动添加 Connection: Keep-Alive
    if (userRequest.header("Connection") == null) {
        requestBuilder.header("Connection", "Keep-Alive");
    }

    // 自动添加 Accept-Encoding: gzip（并自动处理 gzip 解压）
    boolean transparentGzip = false;
    if (userRequest.header("Accept-Encoding") == null
        && userRequest.header("Range") == null) {
        transparentGzip = true;
        requestBuilder.header("Accept-Encoding", "gzip");
    }

    // 自动添加 Cookie（通过 CookieJar）
    List<Cookie> cookies = cookieJar.loadForRequest(userRequest.url());
    if (!cookies.isEmpty()) {
        requestBuilder.header("Cookie", cookieHeader(cookies));
    }

    // 自动添加 User-Agent
    if (userRequest.header("User-Agent") == null) {
        requestBuilder.header("User-Agent", Version.userAgent());
    }

    // 执行网络请求
    Response networkResponse = chain.proceed(requestBuilder.build());

    // 保存 Cookie
    HttpHeaders.receiveHeaders(cookieJar, userRequest.url(), networkResponse.headers());

    // 自动处理 gzip 解压（如果开启了 transparentGzip）
    Response.Builder responseBuilder = networkResponse.newBuilder()
        .request(userRequest);
    if (transparentGzip
        && "gzip".equalsIgnoreCase(networkResponse.header("Content-Encoding"))
        && HttpHeaders.hasBody(networkResponse)) {
        GzipSource responseBody = new GzipSource(networkResponse.body().source());
        Headers strippedHeaders = networkResponse.headers().newBuilder()
            .removeAll("Content-Encoding")
            .removeAll("Content-Length")
            .build();
        responseBuilder.headers(strippedHeaders);
        responseBuilder.body(new RealResponseBody(strippedHeaders,
            Okio.buffer(responseBody)));
    }

    return responseBuilder.build();
}
```

关键补全的头部一览：

| 头部 | 自动添加逻辑 |
|------|-------------|
| `Content-Type` | 从 RequestBody 读取 |
| `Content-Length` / `Transfer-Encoding` | 根据请求体长度决定 |
| `Host` | 从 URL 提取 host + port |
| `Connection` | 默认 `Keep-Alive` |
| `Accept-Encoding` | 添加 `gzip` 并自动解压 |
| `Cookie` | 通过 `CookieJar` 管理 |
| `User-Agent` | `okhttp/4.x.x` |

---

#### ③ CacheInterceptor — 缓存策略

**职责**：基于 RFC 7234 实现 HTTP 缓存，根据 `CacheStrategy` 决定是使用缓存、更新缓存还是直接网络请求。

核心流程：

```
请求到达 → 从 DiskLruCache 查找候选缓存
              ↓
    CacheStrategy 计算策略
              ↓
    ┌─── 策略：使用缓存 (cacheResponse != null && networkRequest == null)
    │    → 直接返回缓存响应
    ├─── 策略：网络请求 (networkRequest != null && cacheResponse == null)
    │    → 发起网络请求，响应写入缓存
    └─── 策略：条件请求 (networkRequest != null && cacheResponse != null)
         → 发起带 If-None-Match / If-Modified-Since 的请求
         → 若 304 → 使用缓存；否则用新响应更新缓存
```

**CacheStrategy 计算规则**：

```java
// okhttp3/internal/cache/CacheStrategy.java
public static class Factory {
    private CacheStrategy getCandidate() {
        // 1. 无缓存 → 网络请求
        if (cacheResponse == null) {
            return new CacheStrategy(request, null);
        }

        // 2. HTTPS 但缺少必要握手信息 → 网络请求
        if (request.isHttps() && cacheResponse.handshake() == null) {
            return new CacheStrategy(request, null);
        }

        // 3. 缓存不可缓存（根据响应码和头部）→ 网络请求
        if (!isCacheable(cacheResponse, request)) {
            return new CacheStrategy(request, null);
        }

        // 4. noCache 请求头 → 网络请求
        CacheControl requestCaching = request.cacheControl();
        if (requestCaching.noCache() || hasConditions(request)) {
            return new CacheStrategy(request, null);
        }

        // 5. 检查缓存新鲜度
        //    新鲜 → 直接用缓存
        //    不新鲜 → 条件请求（带 ETag/Last-Modified）
        // ...
    }
}
```

---

#### ④ ConnectInterceptor — 建立连接

**职责**：从连接池中获取或创建一个到目标服务器的连接。

```java
// okhttp3/internal/connection/ConnectInterceptor.java
@Override public Response intercept(Chain chain) throws IOException {
    RealInterceptorChain realChain = (RealInterceptorChain) chain;
    Request request = realChain.request();
    Transmitter transmitter = realChain.transmitter();

    boolean doExtensiveHealthChecks = !request.method().equals("GET");
    Exchange exchange = transmitter.newExchange(chain, doExtensiveHealthChecks);

    return realChain.proceed(request, transmitter, exchange);
}
```

这里的核心是 `Transmitter.newExchange()`，它内部会调用 `ExchangeFinder.find()`：

```java
// ExchangeFinder.find()
// 1. 尝试从连接池 (RealConnectionPool) 中获取已有连接
RealConnection connection = connectionPool.transmitterAcquirePooledConnection(
    address, transmitter, null, requireMultiplexed);

// 2. 如果没有可用连接 → 建立新连接
if (connection == null) {
    // 3. DNS 解析 (通过 RouteSelector)
    // 4. TCP 三次握手
    // 5. TLS 握手 (如果 HTTPS)
    // 6. 创建 RealConnection
    connection = new RealConnection(connectionPool, route);
    // 7. 放入连接池
    connectionPool.put(connection);
}
```

**连接建立的详细步骤**（在 `RealConnection.connect()` 中）：

1. **DNS 解析**：通过 `RouteSelector` 获取 IP 列表
2. **代理选择**：检查系统代理配置
3. **TCP 连接**：`Socket.connect(address, connectTimeout)`
4. **TLS 握手**：`SSLSocket.startHandshake()` + 证书校验
5. **HTTP/2 协商**：如果支持，进行协议升级或 ALPN 协商
6. **连接健康检查**：标记连接存活时间

---

#### ⑤ CallServerInterceptor — 发送请求与读取响应

**职责**：将 HTTP 请求写入 Socket 输出流，并从输入流中读取 HTTP 响应。

```java
// okhttp3/internal/http/CallServerInterceptor.java
@Override public Response intercept(Chain chain) throws IOException {
    RealInterceptorChain realChain = (RealInterceptorChain) chain;
    Exchange exchange = realChain.exchange();
    Request request = realChain.request();

    // 1. 写入请求头
    exchange.writeRequestHeaders(request);

    // 2. 写入请求体（如果有）
    if (HttpMethod.permitsRequestBody(request.method()) && request.body() != null) {
        BufferedSink bufferedRequestBody = Okio.buffer(
            exchange.createRequestBody(request, false));
        request.body().writeTo(bufferedRequestBody);
        bufferedRequestBody.close();
    }

    exchange.finishRequest();

    // 3. 读取响应头
    Response.Builder responseBuilder = exchange.readResponseHeaders(false);

    // 4. 读取响应体
    Response response = responseBuilder
        .request(request)
        .build();
    response = exchange.openResponseBody(response);

    return response;
}
```

---

### 为什么拦截器顺序不可颠倒？

| 拦截器 | 排序原因 |
|--------|---------|
| **RetryAndFollowUpInterceptor** 在最外层 | 任何网络错误都需要在最外层捕获并决定是否重试；如果放在内层，重试机制就无法覆盖连接建立等步骤 |
| **BridgeInterceptor** 在 CacheInterceptor 之前 | 需要先把用户请求转换为标准 HTTP 格式，Cache 才能以规范 key 查找缓存 |
| **CacheInterceptor** 在 ConnectInterceptor 之前 | 缓存命中时可以直接返回，避免不必要的网络连接；节省资源 |
| **ConnectInterceptor** 在 CallServer 之前 | 必须有可用连接才能发送请求，这是物理前提 |
| **CallServerInterceptor** 在最内层 | 真正执行 I/O 的"最后一公里" |

### 加分扩展

**Application Interceptor vs Network Interceptor：**

```java
// addInterceptor() — 应用拦截器
// 只调用一次，即使有重定向也不重复执行
// 不关心中间响应（重定向、重试）
client.addInterceptor(chain -> {
    Log.d("App", "Request: " + chain.request().url());
    return chain.proceed(chain.request());
});

// addNetworkInterceptor() — 网络拦截器
// 每次网络请求都执行（包括重定向）
// 可以访问携带的 Connection 信息
client.addNetworkInterceptor(chain -> {
    Log.d("Net", "Connection: " + chain.connection());
    Log.d("Net", "Protocol: " + chain.connection().protocol());
    return chain.proceed(chain.request());
});
```

---

## 2. 连接池复用机制与 CleanupRunnable

### 问题

> "OkHttp 的连接池是怎么复用的？连接什么时候被清理？如果并发请求打到同一个域名，OkHttp 是怎么处理的？"

### 答题思路

这道题考察对 `RealConnectionPool` 及其后台清理线程 `CleanupRunnable` 的理解。核心要点：连接池如何匹配、连接的 keep-alive 时间、清理线程的定时检查机制。回答时要讲清楚 put/get/evict 三个操作，以及 5 分钟闲置超时。

### 标准答案

OkHttp 的 `RealConnectionPool` 实现了**基于地址的连接复用**，后台以 `CleanupRunnable` 线程周期性清理闲置连接。

**核心数据结构：**

```java
// okhttp3/internal/connection/RealConnectionPool.kt (OkHttp 4.x)
final class RealConnectionPool(
    private val maxIdleConnections: Int,      // 最大空闲连接数，默认 5
    val keepAliveDurationNs: Long,             // keep-alive 时间，默认 5 分钟
    private val timeUnit: TimeUnit
) {
    // 线程安全队列，存储所有空闲连接
    private val connections = ConcurrentLinkedQueue<RealConnection>()

    private val cleanupRunnable = CleanupRunnable()  // 后台清理任务
    private val executor = ThreadPoolExecutor(0, 1, 60L, TimeUnit.SECONDS,
        SynchronousQueue(),
        threadFactory("OkHttp ConnectionPool", true))
}
```

**连接池默认配置：**

```java
// OkHttpClient 默认构造函数
public Builder() {
    // ...
    connectionPool = new ConnectionPool(
        5,                          // maxIdleConnections
        5, TimeUnit.MINUTES         // keepAliveDuration
    );
}
```

---

#### 连接获取流程 (get)

```java
// RealConnectionPool.transmitterAcquirePooledConnection()
RealConnection transmitterAcquirePooledConnection(
    Address address, Transmitter transmitter,
    List<Route> routes, boolean requireMultiplexed
) {
    for (RealConnection connection : connections) {
        if (requireMultiplexed && !connection.isMultiplexed()) continue;

        // ★ 核心匹配条件：
        // 1. Address 完全匹配（scheme + host + port + proxy + DNS + SSLSocketFactory...）
        // 2. 连接未超过最大分配数
        if (connection.isEligible(address, routes)) {
            transmitter.acquireConnectionNoEvents(connection);
            return connection;
        }
    }
    return null;
}
```

`isEligible` 的详细匹配逻辑：

```java
// RealConnection.isEligible()
boolean isEligible(Address address, List<Route> routes) {
    // 1. 已分配的 Stream 数不能超过限制
    //    HTTP/1.x: 最多 1 个并发
    //    HTTP/2:  最多 connection.maxConcurrentStreams() 个
    if (transmitters.size() >= allocationLimit
        || noNewExchanges) {
        return false;
    }

    // 2. 非主机名 (IP 地址) 匹配 — 直接比较 Address
    //    DNS 负载均衡，同一个 IP 上的多个域名可以共享连接
    if (!address.url().host().equals(this.route().address().url().host())) {
        // 不同主机，仍需 Address 匹配，但不能用主机名比较
        // HTTP/2 允许不同主机名的连接复用（connection coalescing）
        if (http2Connection == null) return false;
        if (!supportsMultiplexedConnection(address)) return false;
        if (!address.hostnameVerifier() == HostnameVerifier.areEqual(hostname, address)) return false;
    }

    // 3. 证书固定 (Certificate Pinner) 检查
    // ...
    return true;
}
```

---

#### 连接清理 (CleanupRunnable)

`CleanupRunnable` 是连接池的"守护者"，以 `ScheduledExecutorService` 调度下一次清理任务：

```java
// RealConnectionPool 中的清理逻辑
long cleanup(long now) {
    int inUseConnectionCount = 0;
    int idleConnectionCount = 0;
    RealConnection longestIdleConnection = null;
    long longestIdleDurationNs = Long.MIN_VALUE;

    synchronized (this) {
        // 遍历所有连接，找出闲置最久的
        for (RealConnection connection : connections) {
            // 检查每个连接的 transmitter 是否还有在用
            pruneAndGetAllocationCount(connection, now);
            if (connection.isIdle()) {
                idleConnectionCount++;
                long idleDurationNs = now - connection.idleAtNs;
                if (idleDurationNs > longestIdleDurationNs) {
                    longestIdleDurationNs = idleDurationNs;
                    longestIdleConnection = connection;
                }
            } else {
                inUseConnectionCount++;
            }
        }

        // ★ 策略一：闲置超时 → 移除连接
        if (longestIdleDurationNs >= this.keepAliveDurationNs
            || idleConnectionCount > this.maxIdleConnections) {
            // 移除闲置最久的连接
            connections.remove(longestIdleConnection);
            return 0; // 立即安排下一次清理
        }
        // ★ 策略二：闲置且没有超过最大限制 → 计算下次清理时间
        else if (idleConnectionCount > 0) {
            return keepAliveDurationNs - longestIdleDurationNs;
        }
        // ★ 策略三：没有闲置连接且正在使用的连接数 > 0 → 等待
        else if (inUseConnectionCount > 0) {
            return keepAliveDurationNs;
        }
        // ★ 策略四：没有任何连接 → 不再执行清理
        else {
            cleanupRunning = false;
            return -1；
        }
    }
}
```

**清理时机总结：**

```
条件                                 → 动作
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
闲置超过 5 分钟                       → 立即移除
闲置连接数超过 5 个                   → 移除闲置最久的
空闲但未超时                          → 等到超时再检查
所有连接都在使用                      → 5 分钟后再次检查
连接池为空                            → 停止清理线程
```

---

#### 连接生命周期图

```
RealConnection 被创建
       │
       ▼
  ┌─────────┐  acquireConnection    ┌──────────┐
  │  IDLE   │ ──────────────────→   │ IN_USE   │
  │  闲置   │                       │  使用中   │
  └─────────┘                       └──────────┘
       ▲                                  │
       │         releaseConnection         │
       └──────────────────────────────────┘
       │
       │ 闲置 > 5min 或 数量 > 5
       ▼
  ┌─────────┐
  │ EVICTED │  → connection.socket.close()
  └─────────┘
```

### 加分扩展

**HTTP/2 的连接合并 (Connection Coalescing)：**

HTTP/2 允许不同域名共享同一条 TCP 连接，只要满足：
- 证书覆盖两个域名（SAN 中包含）
- IP 地址相同
- TLS 策略一致

```java
// 场景：api.example.com 和 cdn.example.com 解析到同一 IP
// HTTP/2 连接合并后，两个域名的请求可以在同一条 TCP 连接上并发
```

**连接驱逐的端口/路由区分：**

连接池以 `Address` 为粒度管理。`Address` 包含：`scheme`、`host`、`port`、`proxy`、`dns`、`sslSocketFactory`、`hostnameVerifier`、`certificatePinner`。任何一个字段不同，都会创建不同的连接。

---

## 3. HTTP/2 多路复用原理

### 问题

> "OkHttp 是如何支持 HTTP/2 的？多路复用具体是怎么实现的？底层是怎么管理流（Stream）的？"

### 答题思路

从三个层面回答：(1) 协议协商 — ALPN；(2) 多路复用 — Stream 帧复用；(3) OkHttp 的实现 — `Http2Connection` + `Http2Stream`。如果面试官追问细节，再展开帧结构（HEADERS/DATA/SETTINGS/WINDOW_UPDATE 等）和流量控制。

### 标准答案

OkHttp 对 HTTP/2 的支持贯穿三阶段：

---

#### 阶段一：协议协商 (ALPN)

在 TLS 握手时通过 **ALPN (Application-Layer Protocol Negotiation)** 协商协议：

```java
// RealConnection.connectTls()
private void connectTls(ConnectionSpecSelector connectionSpecSelector) {
    // ...
    if (route.address().protocols().contains(Protocol.H2_PRIOR_KNOWLEDGE)) {
        // H2_PRIOR_KNOWLEDGE — 明文 HTTP/2（无需 TLS）
        protocol = Protocol.H2_PRIOR_KNOWLEDGE;
    } else {
        // 通过平台 ALPN 支持协商
        Platform.get().configureTlsExtensions(sslSocket, host, protocols);
        sslSocket.startHandshake();
        // 获取协商结果
        String maybeProtocol = Platform.get().getSelectedProtocol(sslSocket);
        protocol = maybeProtocol != null
            ? Protocol.get(maybeProtocol)
            : Protocol.HTTP_1_1;
    }
}
```

如果服务端不支持 HTTP/2，自动降级到 HTTP/1.1。

---

#### 阶段二：帧多路复用 (Frame Multiplexing)

HTTP/2 的核心是一个**二进制帧协议**，在单条 TCP 连接上交错发送属于不同 Stream 的帧：

```
HTTP/1.1（串行）：
Client                  Server
  │──── Request 1 ──────→│
  │←── Response 1 ──────│
  │──── Request 2 ──────→│
  │←── Response 2 ──────│

HTTP/2（多路复用）：
Client                  Server
  │── Stream1: HEADERS ─→│
  │── Stream3: HEADERS ─→│
  │── Stream1: DATA    ─→│
  │── Stream2: HEADERS ─→│
  │←── Stream1: DATA   ──│
  │── Stream3: DATA    ─→│
  │←── Stream2: DATA   ──│
```

每个帧都携带 **Stream ID**，接收方根据 Stream ID 重新组装完整的请求/响应。

---

#### 阶段三：Http2Connection 的流管理

OkHttp 内部 `Http2Connection` 通过 `Http2Writer` 和 `Http2Reader` 两个核心类处理帧的读写：

```java
// Http2Connection 核心属性 (简化)
class Http2Connection {
    // 从 1 开始递增 (client 使用奇数，server 使用偶数)
    int nextStreamId;
    // 当前活跃的流
    final Map<Integer, Http2Stream> streams = new LinkedHashMap<>();
    // 对端声明的最大并发流数
    int maxConcurrentStreams = Integer.MAX_VALUE;
    // 流控制窗口大小
    long windowSize = DEFAULT_INITIAL_WINDOW_SIZE; // 65535 字节

    // 创建一个新的 HTTP/2 流
    Http2Stream newStream(int outFinished, boolean inFinished) {
        int streamId = nextStreamId;
        nextStreamId += 2; // client 流 ID 为奇数
        Http2Stream stream = new Http2Stream(streamId, this,
            outFinished, inFinished, null);
        streams.put(streamId, stream);
        return stream;
    }
}
```

**关键概念：**

| 概念 | 说明 |
|------|------|
| **Stream ID** | 客户端发起的流使用奇数 ID (1,3,5...)，服务端发起的流使用偶数 ID (2,4,6...) |
| **并发流限制** | `SETTINGS_MAX_CONCURRENT_STREAMS`，默认无限制，服务端可配置（如 nginx 默认 128） |
| **流量控制** | 基于 `WINDOW_UPDATE` 帧，连接级别 + 流级别双重流量控制 |
| **头部压缩** | HPACK 算法，通过静态/动态表压缩 HTTP 头部 |

---

#### HTTP/2 vs HTTP/1.1 差异表

| 特性 | HTTP/1.1 | HTTP/2 |
|------|----------|--------|
| 连接复用 | 串行（Keep-Alive 可复用但队头阻塞） | 多路复用（无队头阻塞） |
| 头部压缩 | 无（每次携带完整头部） | HPACK 压缩 |
| 服务器推送 | 不支持 | 支持 Server Push |
| 请求优先级 | 不支持 | 支持（流优先级） |
| 协议格式 | 文本 | 二进制帧 |
| TCP 连接数 | 通常 6-8 个并发 | 1 个即可 |

### 加分扩展

**队头阻塞 (Head-of-Line Blocking) 的真正含义：**

- **HTTP/1.1 的队头阻塞**：发生在应用层。连接上的第一个请求未完成（如大文件下载），后续请求必须等待
- **HTTP/2 的队头阻塞**：理论上消除了应用层的 HOLB，但 TCP 层面的丢包重传仍然会导致流之间的阻塞
- **HTTP/3 (QUIC)**：在 UDP 基础上彻底消除了 TCP 层面的 HOLB

**Server Push 的 OkHttp 处理：**

```java
// Http2Connection 收到 PUSH_PROMISE 帧
void pushStream(int streamId, List<Header> requestHeaders) {
    // 创建 Push 流，通知 PushObserver
    Http2Stream pushStream = new Http2Stream(streamId, ...);
    pushObserver.onPush(streamId, requestHeaders);
    // 客户端可以选择接收 (ACCEPT) 或拒绝 (CANCEL) 服务端推送
}
```

---

## 4. DNS 优化策略

### 问题

> "OkHttp 默认的 DNS 解析有什么问题？在弱网或海外场景下怎么优化？你用过 HTTP-DNS 吗？怎么集成到 OkHttp 里？"

### 答题思路

先说出系统 DNS 的三大痛点（LocalDNS 劫持、解析慢、无法精准调度），再给出三种优化方案（替换 DNS 接口、HTTP-DNS、预解析），最后完整展示 OkHttp 集成 HTTP-DNS 的代码。如果能补充 DNS 缓存和容灾策略，属于高级加分项。

### 标准答案

---

#### 系统 DNS 的三大痛点

**痛点一：LocalDNS 劫持 / 运营商劫持**
- 运营商在 DNS 响应中插入广告或跳转错误 IP
- 海外场景下 LocalDNS 可能无法正确解析国内域名

**痛点二：域名解析慢**
- UDP 包丢失导致超时重试（默认 5s）
- 递归查询链路长（根域名服务器 → 顶级域名服务器 → 权威 DNS）

**痛点三：无法精准调度**
- DNS 解析结果取决于 LocalDNS 的出口 IP，而非用户的真实 IP
- CDN 调度不准确，用户被分配到远的边缘节点

---

#### 方案一：替换 OkHttp 的 DNS 接口

OkHttp 提供了 `Dns` 接口供自定义：

```java
// OkHttp 默认 DNS（调用系统 InetAddress.getAllByName）
public static final Dns SYSTEM = hostname -> {
    return DnsCompanion.dns.lookup(hostname);
};

// 自定义 DNS — 使用 HTTP-DNS
class HttpDns implements Dns {
    @Override
    public List<InetAddress> lookup(String hostname) throws UnknownHostException {
        // 1. 通过 HTTP-DNS 服务商（如阿里云、腾讯云）获取 IP
        String ip = requestHttpDns(hostname);

        if (ip != null) {
            return Arrays.asList(InetAddress.getByName(ip));
        }

        // 2. 降级到系统 DNS
        return Dns.SYSTEM.lookup(hostname);
    }

    private String requestHttpDns(String hostname) {
        // HTTP 请求到 HTTP-DNS 服务，携带真实 IP
        String url = "https://dns.aliyuncs.com/dns-query"
            + "?host=" + hostname
            + "&ip=" + getUserRealIp();
        // ... 发起 HTTP 请求解析 JSON
    }
}

// 配置到 OkHttpClient
OkHttpClient client = new OkHttpClient.Builder()
    .dns(new HttpDns())
    .build();
```

---

#### 方案二：DNS 预解析

在应用启动或关键时机提前做 DNS 解析，减少第一次请求的耗时：

```java
class DnsPreFetcher {
    private static final List<String> PRE_FETCH_HOSTS = Arrays.asList(
        "api.example.com",
        "cdn.example.com",
        "image.example.com"
    );

    public static void preFetch() {
        Executors.newSingleThreadExecutor().execute(() -> {
            for (String host : PRE_FETCH_HOSTS) {
                try {
                    InetAddress.getAllByName(host);
                } catch (UnknownHostException ignored) {
                }
            }
        });
    }
}

// Application.onCreate() 中调用
DnsPreFetcher.preFetch();
```

---

#### 方案三：DNS 缓存 + 并发解析

```java
class OptimizedDns implements Dns {
    private final Map<String, List<InetAddress>> cache = new ConcurrentHashMap<>();
    private final Map<String, Long> cacheTime = new ConcurrentHashMap<>();
    private static final long TTL = 5 * 60 * 1000; // 5 分钟

    @Override
    public List<InetAddress> lookup(String hostname) throws UnknownHostException {
        // 查缓存
        List<InetAddress> cached = cache.get(hostname);
        Long timestamp = cacheTime.get(hostname);
        if (cached != null && System.currentTimeMillis() - timestamp < TTL) {
            return cached;
        }

        // 系统 DNS + HTTP-DNS 并发解析，取先返回的结果
        List<InetAddress> result = concurrentLookup(hostname);
        cache.put(hostname, result);
        cacheTime.put(hostname, System.currentTimeMillis());
        return result;
    }

    private List<InetAddress> concurrentLookup(String hostname) {
        // 用 CountDownLatch 并发执行两种 DNS 解析
        // ...
    }
}
```

---

### 加分扩展

**DNS 解析在连接建立中的位置：**

```
RouteSelector.next()
    → 收集路由 (Proxy + InetAddress)
    → 对于每个 Proxy，调用 Dns.lookup(hostname)
    → 返回 List<InetAddress> (可能有多个 IP)
    → 按顺序尝试每个 Route
```

**HTTP-DNS 的常见服务商：**
- 阿里云 HTTP-DNS
- 腾讯云 HTTP-DNS
- DNSPod
- 自建 HTTP-DNS 服务

---

## 5. RealInterceptorChain 责任链模式深度解析

### 问题

> "OkHttp 的拦截器链是怎么实现的？RealInterceptorChain 的核心逻辑是什么？为什么不直接用递归而用迭代？"

### 答题思路

先讲清楚 RealInterceptorChain 的核心字段和 `proceed()` 方法逻辑，再对比递归 vs 迭代实现，最后点出责任链模式在 OkHttp 中的巧妙之处——每次调用 `proceed` 都创建一个新的 Chain 实例，传递 index+1。

### 标准答案

OkHttp 通过 `RealInterceptorChain` 实现了经典的责任链模式：

```java
// okhttp3/internal/http/RealInterceptorChain.kt
class RealInterceptorChain(
    private val interceptors: List<Interceptor>,  // 拦截器列表
    private val index: Int,                        // 当前拦截器下标
    private val exchange: Exchange?,               // 网络交换器
    private val request: Request,                  // 当前请求
    private val transmitter: Transmitter,          // 应用层与网络层的桥梁
    private val call: Call,
    private val connectTimeout: Int,
    private val readTimeout: Int,
    private val writeTimeout: Int
) : Interceptor.Chain {

    // ★ 核心方法：推进到下一个拦截器
    override fun proceed(request: Request): Response {
        // 1. 检查 index 是否越界
        check(index < interceptors.size)

        // 2. ★ 核心：创建下一个 Chain，index + 1
        val next = RealInterceptorChain(
            interceptors = interceptors,
            index = index + 1,       // ← 关键：下标递增
            exchange = exchange,
            request = request,
            transmitter = transmitter,
            call = call,
            connectTimeout = connectTimeout,
            readTimeout = readTimeout,
            writeTimeout = writeTimeout
        )

        // 3. 获取当前拦截器
        val interceptor = interceptors[index]

        // 4. ★ 执行当前拦截器，将 next 作为 chain 参数传入
        val response = interceptor.intercept(next)

        // 5. 后续检查（不允许 exchange 为 null 且 response body 不为空的情况）
        check(response.body != null) { "interceptor $interceptor returned null body" }
        return response
    }
}
```

**执行流程（以 3 个拦截器为例）：**

```
初始 Chain(index=0).proceed(request)
  → interceptor[0].intercept(Chain(index=1))
    → Chain(index=1).proceed(request)
      → interceptor[1].intercept(Chain(index=2))
        → Chain(index=2).proceed(request)
          → interceptor[2].intercept(Chain(index=3))
            → 没有更多拦截器 → 最后一个通常是 CallServerInterceptor
          ← 返回 Response
        ← 返回 Response (可能被 interceptor[1] 修改)
      ← 返回 Response (可能被 interceptor[0] 修改)
    ← 最终 Response 返回给调用方
```

---

### 为什么不用递归而用迭代+新建 Chain？

**原因一：一致性**。每次 `proceed()` 创建新 Chain，确保"链"的概念清晰——责任链的每一个环节都持有"剩余链"的引用。

**原因二：避免递归深度过大**。虽然拦截器数量通常很少（内置 5 个 + 用户几个），但这种设计天然避免了递归栈溢出的风险。

**原因三：拦截器可以修改 Request**。每个拦截器在调用 `chain.proceed()` 之前，可以构造一个新的 Request 传递下去。新 Chain 机制保证了每个拦截器看到的都是独立的链状态。

**原因四：适合网络拦截器**。`addNetworkInterceptor` 可以拿到 `chain.connection()`，这在递归模式下难以传递。

```java
// 拦截器可以在 proceed 前后添加逻辑
class LoggingInterceptor implements Interceptor {
    @Override public Response intercept(Chain chain) throws IOException {
        Request request = chain.request();
        long t1 = System.nanoTime();
        Log.d("OkHttp", "Sending request " + request.url());

        // ★ 调用 chain.proceed() — 传递到下一个拦截器
        Response response = chain.proceed(request);

        long t2 = System.nanoTime();
        Log.d("OkHttp", "Received response for "
            + response.request().url()
            + " in " + ((t2 - t1) / 1e6d) + "ms");

        return response;
    }
}
```

---

## 6. 连接池淘汰算法源码分析

### 问题

> "OkHttp 的连接淘汰策略是什么？用的是 LRU 吗？和 HttpClient 的连接管理有什么不同？"

### 答题思路

OkHttp 的连接清理不是传统 LRU，而是**基于闲置时间的线性扫描 + 两个条件触发**。详细展开 `cleanup()` 方法的四种场景，画出淘汰决策树。

### 标准答案

OkHttp 的连接淘汰策略是一种**定时检查 + 基于闲置时间的扫荡式淘汰**，而非传统 LRU。

#### 淘汰算法核心代码

```java
// RealConnectionPool.cleanup()
long cleanup(long now) {
    int inUseConnectionCount = 0;
    int idleConnectionCount = 0;
    RealConnection longestIdleConnection = null;
    long longestIdleDurationNs = Long.MIN_VALUE;

    synchronized (this) {
        for (RealConnection connection : connections) {
            // ★ 核心：检查并清理已死亡的 transmitter 引用
            // 如果连接的 transmitter 列表中有已经不再使用的，
            // 从连接的 transmitter 列表中移除它们
            if (pruneAndGetAllocationCount(connection, now) > 0) {
                inUseConnectionCount++;
            } else {
                idleConnectionCount++;
                // 记录闲置最久的连接
                long idleDurationNs = now - connection.idleAtNs;
                if (idleDurationNs > longestIdleDurationNs) {
                    longestIdleDurationNs = idleDurationNs;
                    longestIdleConnection = connection;
                }
            }
        }

        if (longestIdleDurationNs >= this.keepAliveDurationNs         // 条件A: 闲置超时
            || idleConnectionCount > this.maxIdleConnections) {       // 条件B: 闲置数量超限

            // ★ 移除闲置最久的连接（只移除一个！）
            connections.remove(longestIdleConnection);
            Util.closeQuietly(longestIdleConnection.socket());
            return 0; // 立即执行下一次清理

        } else if (idleConnectionCount > 0) {
            // 有闲置连接但未超时/未超限
            // 返回距超时还差多少时间
            return keepAliveDurationNs - longestIdleDurationNs;

        } else if (inUseConnectionCount > 0) {
            // 所有连接都在使用，5 分钟后再次检查
            return keepAliveDurationNs;

        } else {
            // 没有连接，停止清理
            cleanupRunning = false;
            return -1;
        }
    }
}
```

---

#### 淘汰决策树

```
┌── 检查所有连接
│
├── 连接使用中 (inUseCount > 0)
│   ├── 闲置连接 > 0?
│   │   ├── 闲置 > 5min 或 闲置数量 > 5?
│   │   │   └── YES → 移除闲置最久的连接，立即再次检查
│   │   └── NO → 等到超时再检查（返回剩余时间）
│   └── 闲置连接 == 0?
│       └── 5 分钟后再次检查
│
├── 无活跃连接，有闲置连接
│   └── 等待闲置超时后移除
│
└── 无任何连接
    └── 停止 CleanupRunnable
```

---

#### 为什么不是标准 LRU？

标准 LRU 基于"访问时间"淘汰，每次访问都会更新节点位置。但 OkHttp 的场景不同：

- **连接"活跃"不等于"刚被使用"**：一个正在传输数据的连接不应被淘汰，但 LRU 无法区分"活跃"和"近期访问过"
- **每次淘汰只移除一个**：清理是逐步进行的，避免一次性关闭大量连接影响体验
- **闲置时间是主要维度**：HTTP Keep-Alive 场景下，连接的生死完全取决于闲置时长

---

#### 和 HttpClient 连接管理的对比

| 维度 | OkHttp | Apache HttpClient | Cronet (Chrome) |
|------|--------|-------------------|-----------------|
| 连接池实现 | `RealConnectionPool` + `ConcurrentLinkedQueue` | `CPool` + `LinkedList` | Chromium 网络栈 |
| 淘汰策略 | 闲置超时 + 数量上限 | LRU + 闲置超时 | 更复杂的 Socket 池 |
| 最大空闲连接数 | 5 | 20 (默认) | ~256 |
| 闲置超时 | 5 分钟 | 配置项 | 动态 |
| HTTP/2 连接合并 | ✅ | ❌ | ✅ |
| 后台清理线程 | CleanupRunnable (单个) | IdleConnectionEvictor | 内建 |

---

## 7. Http2Connection 流管理机制

### 问题

> "在 HTTP/2 模式下，OkHttp 如何管理多个并发的流？连接和流的关系是什么？流量控制是怎么做的？"

### 答题思路

从对象模型出发：一个 `Http2Connection` 包含多个 `Http2Stream`；然后展开流创建/关闭、帧读写、WINDOW_UPDATE 流量控制。如果能画出连接→流→帧的三级关系图会更好。

### 标准答案

---

#### 对象模型：Connection → Stream

```
OkHttpClient
    └── RealConnectionPool
         └── RealConnection (TCP + TLS 封装)
              └── Http2Connection (HTTP/2 协议层)
                   ├── Http2Stream 1 (id=1, 某 GET 请求)
                   ├── Http2Stream 3 (id=3, 某 POST 请求)
                   ├── Http2Stream 5 (id=5, 某 GET 请求)
                   ├── ...
                   └── Http2Stream N (id=N, 客户端流 ID 始终奇数)
              └── Http2Reader (读线程)
              └── Http2Writer (写线程)
```

---

#### 流创建：newStream()

```java
// Http2Connection.newStream()
Http2Stream newStream(List<Header> requestHeaders, boolean out) {
    // 1. 检查是否超过并发流限制
    synchronized (this) {
        if (nextStreamId > Integer.MAX_VALUE / 2) {
            // 流 ID 耗尽，优雅关闭
            shutdown(ErrorCode.REFUSED_STREAM);
        }
        // 2. 检查服务端最大并发流数限制
        if (streams.size() >= maxConcurrentStreams) {
            throw new IOException("Too many concurrent streams");
        }
        // 3. 分配新 Stream ID
        streamId = nextStreamId;
        nextStreamId += 2;
    }

    // 4. 创建 Http2Stream 并注册
    Http2Stream stream = new Http2Stream(streamId, this, ...);
    streams.put(streamId, stream);

    // 5. 同步发送 HEADERS 帧
    if (out) {
        writer.headers(streamId, requestHeaders);
    }

    return stream;
}
```

---

#### 流状态机

```
                        IDLE
                         │
                  send HEADERS frame
                         │
                   ┌─────▼──────┐
                   │   OPEN     │
                   └──┬──────┬──┘
              END_STREAM│      │ RST_STREAM
                   ┌────▼─┐  ┌─▼────────┐
                   │HALF  │  │ CLOSED   │
                   │CLOSE │  └──────────┘
                   └──┬───┘
              END_STREAM│
                   ┌────▼─────┐
                   │  CLOSED  │
                   └──────────┘
```

---

#### 流量控制 (Flow Control)

HTTP/2 使用**双重流量控制**：连接级别 + 流级别。

```java
// Http2Connection 的窗口更新处理
void updateConnectionWindow(long delta) {
    connectionWindowSize += delta;
    // 当窗口大小从 ≤ 0 变为 > 0 时，恢复被阻塞的流
    if (connectionWindowSize > 0) {
        resumeStreams();
    }
}

// 发送 DATA 帧时的窗口检查
void writeData(int streamId, boolean outFinished, Buffer buffer, int byteCount) {
    // 1. 检查流级别窗口
    // 2. 检查连接级别窗口
    // 3. 取两者最小值作为可发送字节数
    int toWrite = Math.min(
        Math.min(byteCount, stream.windowSize),
        connectionWindowSize
    );
    // 4. 写入帧
    writer.data(streamId, outFinished, buffer, toWrite);
    // 5. 扣除窗口
    stream.windowSize -= toWrite;
    connectionWindowSize -= toWrite;
}
```

**WINDOW_UPDATE 帧的处理：**

```java
// Http2Reader 读取到 WINDOW_UPDATE 帧
void windowUpdate(int streamId, int increment) {
    if (streamId == 0) {
        // 连接级别的窗口更新
        updateConnectionWindow(increment);
    } else {
        // 流级别的窗口更新
        Http2Stream stream = streams.get(streamId);
        stream.updateWindow(increment);
        // 这个流可能之前被阻塞，现在可以继续发送数据了
    }
}
```

---

#### SYN_STREAM 和 SYN_REPLY 在 HTTP/2 中的对应

HTTP/1.1 文本协议中的请求行和状态行，在 HTTP/2 中被编码为 **HEADERS 帧**：

```
HTTP/1.1:
GET /api/user HTTP/1.1
Host: example.com
→ 被编码为 →
HTTP/2 HEADERS 帧:
  :method: GET
  :path: /api/user
  :authority: example.com
  :scheme: https
```

### 加分扩展

**设置帧（SETTINGS）的协商：**

连接建立后，双方会发送 SETTINGS 帧来协商参数：

```java
// 可配置的 SETTINGS 参数
SETTINGS_HEADER_TABLE_SIZE        // HPACK 动态表大小
SETTINGS_MAX_CONCURRENT_STREAMS   // 最大并发流数
SETTINGS_INITIAL_WINDOW_SIZE      // 初始窗口大小
SETTINGS_MAX_FRAME_SIZE           // 最大帧大小
SETTINGS_MAX_HEADER_LIST_SIZE     // 最大头部列表大小
```

---

## 8. 拦截器链完整流程图

### 问题

> "如果让你画一张 OkHttp 从请求到响应的完整流程图，你会怎么画？包含同步/异步两种调用路径。"

### 答题思路

用 Mermaid 时序图完整展示从 `client.newCall()` 到拿到 `Response` 的全过程，关键节点标注源码核心方法名。同步和异步的差异点在 `Dispatcher` 层体现。

### 标准答案

#### 同步请求 (execute) 时序图

```
┌──────┐   ┌──────┐   ┌──────────┐   ┌──────────────┐   ┌──────┐
│Caller │   │RealCall│  │ RealInterceptorChain │   │Server│
└──┬───┘   └───┬───┘   └─────┬───────┘          └──┬───┘
   │           │              │                      │
   │ execute() │              │                      │
   │──────────→│              │                      │
   │           │ synchronized│                      │
   │           │ (避免重复执行)│                      │
   │           │──────────────│                      │
   │           │ getResponseWithInterceptorChain()   │
   │           │──────────────│                      │
   │           │              │                      │
   │           │    ┌─ ① RetryAndFollowUpInterceptor │
   │           │    │  realChain.proceed()           │
   │           │    ├─ ② BridgeInterceptor           │
   │           │    │  补充HTTP头部/Cookie/gzip      │
   │           │    ├─ ③ CacheInterceptor            │
   │           │    │  查DiskLruCache/条件请求       │
   │           │    ├─ ④ ConnectInterceptor          │
   │           │    │  从连接池取/新建连接            │
   │           │    │  ├─ DNS解析 (RouteSelector)    │
   │           │    │  ├─ TCP握手 (Socket.connect)   │
   │           │    │  └─ TLS握手/ALPN协商           │
   │           │    ├─ ⑤ CallServerInterceptor       │
   │           │    │  ├─ writeRequestHeaders        │
   │           │    │  ├─ writeRequestBody           │──────→│
   │           │    │  ├─ readResponseHeaders        │←──────│
   │           │    │  └─ readResponseBody           │←──────│
   │           │    └─ Response返回(逆序回溯)         │
   │           │              │                      │
   │           │←─────────────│                      │
   │←──────────│              │                      │
```

#### 异步请求 (enqueue) 的 Dispatcher 调度

```
Call.enqueue(Callback)
    │
    ▼
RealCall.enqueue()
    │
    ▼
Dispatcher.enqueue(AsyncCall)
    │
    ├── runningCalls.size() < maxRequests (64)
    │   && runningCallsForHost < maxRequestsPerHost (5)
    │   │
    │   ├── YES → runningCalls.add(call)
    │   │         executorService().execute(call)
    │   │               │
    │   │               ▼
    │   │         AsyncCall.run()
    │   │               │
    │   │               ▼
    │   │         getResponseWithInterceptorChain()
    │   │               │
    │   │               ▼
    │   │         callback.onResponse()
    │   │               │
    │   │               ▼
    │   │         Dispatcher.finished(call)
    │   │               │
    │   │         runningCalls.remove(call)
    │   │         promoteCalls()  ← 从 readyCalls 中取
    │   │
    │   └── NO  → readyCalls.add(call)
    │             等待 promoteCalls() 调度
```

#### 连接获取流程详解

```
ConnectInterceptor.intercept()
    │
    ▼
Transmitter.newExchange()
    │
    ▼
ExchangeFinder.find()
    │
    ├── 1. connectionPool.transmitterAcquirePooledConnection()
    │       ├── 匹配 Address (scheme/host/port/proxy/ssl/...)
    │       ├── 检查 HTTP/2 连接合并
    │       ├── 检查并发流数限制
    │       └── 返回 RealConnection 或 null
    │
    ├── 2. 若连接池未命中 → 创建新连接
    │       ├── RouteSelector.next() → 收集 Proxy + IP
    │       ├── RealConnection.connect()
    │       │    ├── connectSocket() → TCP 握手
    │       │    ├── connectTunnel() → HTTP 代理隧道
    │       │    └── establishProtocol()
    │       │         ├── HTTP/2: startHttp2() → ALPN → Http2Connection
    │       │         └── HTTP/1.1: 直接使用 Socket
    │       └── connectionPool.put(connection)
    │
    └── 3. 返回 Exchange (封装了 ExchangeCodec)
```

---

## 9. 自定义拦截器实战

### 问题

> "如果让你为 OkHttp 写自定义拦截器，你会写哪些？请分别写出日志拦截器、缓存拦截器和重试拦截器的实现。"

### 答题思路

展示三个有实用价值的自定义拦截器，每个都要有完整的可运行代码。强调拦截器的职责单一原则，以及在 `chain.proceed()` 前后分别能做什么。

### 标准答案

---

#### 实战一：日志拦截器 — 打印完整请求响应

```java
/**
 * 日志拦截器：记录请求 URL、耗时、响应码、请求/响应体大小。
 * 使用 application interceptor 确保只记录一次。
 */
class LoggingInterceptor implements Interceptor {
    private static final String TAG = "OkHttpLog";
    private final Logger logger;

    interface Logger {
        void log(String message);
    }

    LoggingInterceptor(Logger logger) {
        this.logger = logger;
    }

    @Override public Response intercept(Chain chain) throws IOException {
        Request request = chain.request();

        long startTime = System.nanoTime();

        // ★ proceed 之前：记录请求信息
        StringBuilder requestLog = new StringBuilder();
        requestLog.append("→ REQUEST ")
            .append(request.method()).append(' ')
            .append(request.url()).append('\n');

        // 记录请求头
        Headers requestHeaders = request.headers();
        for (int i = 0, size = requestHeaders.size(); i < size; i++) {
            requestLog.append("  ")
                .append(requestHeaders.name(i)).append(": ")
                .append(requestHeaders.value(i)).append('\n');
        }

        // 记录请求体大小
        RequestBody requestBody = request.body();
        if (requestBody != null) {
            try {
                Buffer buffer = new Buffer();
                requestBody.writeTo(buffer);
                requestLog.append("  Body: ").append(buffer.size()).append(" bytes\n");
            } catch (IOException ignored) {
                requestLog.append("  Body: [binary or stream, size unknown]\n");
            }
        }

        logger.log(requestLog.toString());

        // ★ 执行下一个拦截器
        Response response;
        try {
            response = chain.proceed(request);
        } catch (Exception e) {
            logger.log("← HTTP FAILED: " + e.getMessage());
            throw e;
        }

        long duration = System.nanoTime() - startTime;

        // ★ proceed 之后：记录响应信息
        StringBuilder responseLog = new StringBuilder();
        responseLog.append("← RESPONSE ")
            .append(response.code()).append(' ')
            .append(response.message()).append(' ')
            .append(request.url()).append('\n');
        responseLog.append("  Duration: ")
            .append(duration / 1_000_000.0).append("ms\n");

        // 记录响应头
        Headers responseHeaders = response.headers();
        for (int i = 0, size = responseHeaders.size(); i < size; i++) {
            responseLog.append("  ")
                .append(responseHeaders.name(i)).append(": ")
                .append(responseHeaders.value(i)).append('\n');
        }

        // 记录响应体大小（不消费流！）
        ResponseBody responseBody = response.body();
        long contentLength = responseBody.contentLength();
        if (contentLength != -1) {
            responseLog.append("  Body: ").append(contentLength).append(" bytes\n");
        } else {
            responseLog.append("  Body: [chunked or unknown size]\n");
        }

        logger.log(responseLog.toString());

        return response;
    }
}
```

---

#### 实战二：缓存增强拦截器 — 离线缓存

```java
/**
 * 离线缓存拦截器：在有网络时使用网络数据并缓存；
 * 在无网络时强制使用缓存（即使缓存已过期）。
 */
class OfflineCacheInterceptor implements Interceptor {
    private static final int MAX_STALE_SECONDS = 60 * 60 * 24 * 7; // 7 天
    private final Context context;

    OfflineCacheInterceptor(Context context) {
        this.context = context;
    }

    @Override public Response intercept(Chain chain) throws IOException {
        Request request = chain.request();

        // 无网络时，强制使用缓存
        if (!isNetworkAvailable()) {
            request = request.newBuilder()
                .cacheControl(CacheControl.FORCE_CACHE)
                .build();
        }

        Response response = chain.proceed(request);

        // 有网络时，缓存响应（覆盖服务端的 Cache-Control）
        if (isNetworkAvailable()) {
            response = response.newBuilder()
                .header("Cache-Control",
                    "public, max-age=" + MAX_STALE_SECONDS)
                .build();
        }

        return response;
    }

    private boolean isNetworkAvailable() {
        ConnectivityManager cm = (ConnectivityManager)
            context.getSystemService(Context.CONNECTIVITY_SERVICE);
        NetworkInfo netInfo = cm.getActiveNetworkInfo();
        return netInfo != null && netInfo.isConnected();
    }
}
```

---

#### 实战三：智能重试拦截器 — 处理瞬时故障

```java
/**
 * 智能重试拦截器：当请求遇到特定的瞬时故障时自动重试。
 * 配合 addInterceptor 使用，避免和内置 RetryAndFollowUpInterceptor 冲突。
 */
class RetryInterceptor implements Interceptor {
    private static final int MAX_RETRY_COUNT = 3;
    private static final long RETRY_DELAY_MS = 1000;

    // 需要重试的 HTTP 状态码
    private static final Set<Integer> RETRYABLE_STATUS_CODES = new HashSet<>(
        Arrays.asList(429, 500, 502, 503, 504)
    );

    @Override public Response intercept(Chain chain) throws IOException {
        Request request = chain.request();
        int retryCount = 0;
        Response response = null;

        while (retryCount < MAX_RETRY_COUNT) {
            try {
                response = chain.proceed(request);
                break; // 成功，跳出循环
            } catch (IOException e) {
                retryCount++;
                if (retryCount >= MAX_RETRY_COUNT) {
                    throw e; // 重试耗尽，抛出异常
                }
                // 等待后重试
                sleep(retryCount * RETRY_DELAY_MS);
            }
        }

        // 处理可重试的状态码
        if (response != null && RETRYABLE_STATUS_CODES.contains(response.code())) {
            while (retryCount < MAX_RETRY_COUNT) {
                retryCount++;
                response.close();
                sleep(retryCount * RETRY_DELAY_MS);

                try {
                    response = chain.proceed(request);
                    if (!RETRYABLE_STATUS_CODES.contains(response.code())) {
                        break; // 成功
                    }
                } catch (IOException e) {
                    if (retryCount >= MAX_RETRY_COUNT) throw e;
                }
            }
        }

        return response;
    }

    private void sleep(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
```

---

#### 实战四：请求头统一添加拦截器（生产常用）

```java
/**
 * 统一添加公共请求头：Token、设备信息、版本号等。
 */
class HeaderInterceptor implements Interceptor {
    private static final String AUTH_TOKEN_KEY = "Authorization";

    @Override public Response intercept(Chain chain) throws IOException {
        Request originalRequest = chain.request();

        // 构建带公共头的 Request
        Request newRequest = originalRequest.newBuilder()
            .header("User-Agent", getUserAgent())
            .header("X-Client-Version", getAppVersion())
            .header("X-Device-Id", getDeviceId())
            .header("X-Platform", "android")
            .header("X-Request-Id", UUID.randomUUID().toString())
            // 动态注入 Token
            .header(AUTH_TOKEN_KEY, getAuthToken())
            .build();

        return chain.proceed(newRequest);
    }

    private String getUserAgent() {
        return String.format("MyApp/%s (Android %s; %s)",
            getAppVersion(),
            Build.VERSION.RELEASE,
            Build.MODEL);
    }

    private String getAppVersion() {
        // 从 PackageInfo 读取
        return "1.0.0";
    }

    private String getDeviceId() {
        // 从 Settings.Secure.ANDROID_ID 或自生成 UUID 读取
        return "device-uuid-xxx";
    }

    private String getAuthToken() {
        // 从本地存储或内存读取登录 Token
        return "Bearer " + TokenManager.getToken();
    }
}
```

---

### 拦截器设计原则总结

| 原则 | 说明 |
|------|------|
| **单一职责** | 每个拦截器只做一件事（日志、缓存、加头、重试） |
| **关注 proceed 前后** | proceed 前修改 Request，proceed 后修改 Response |
| **不要消费 ResponseBody** | 日志拦截器中不调用 `response.body().string()`，否则后续拦截器拿不到 body |
| **区分 ApplicationInterceptor 和 NetworkInterceptor** | 前者只执行一次，后者每次网络请求都执行 |
| **避免和内置拦截器冲突** | 不要重复实现 RetryAndFollowUpInterceptor 的功能 |

---

## 总结：OkHttp 面试高频考点速查表

| 考点 | 核心知识 | 面试权重 |
|------|---------|:-------:|
| 五大拦截器 | Retry → Bridge → Cache → Connect → CallServer | ★★★★★ |
| 连接池 | RealConnectionPool + CleanupRunnable + 5min 超时 | ★★★★☆ |
| HTTP/2 多路复用 | ALPN 协商 + Stream ID + WINDOW_UPDATE 流量控制 | ★★★★☆ |
| DNS 优化 | 自定义 Dns 接口 + HTTP-DNS + 预解析 | ★★★☆☆ |
| 责任链模式 | RealInterceptorChain + index 递增 + new Chain | ★★★★☆ |
| 连接淘汰 | 闲置时长扫描 + 只移除一个 + 非 LRU | ★★★☆☆ |
| 同步/异步 | Dispatcher 线程池 + maxRequests(64) + maxRequestsPerHost(5) | ★★★★☆ |
| 缓存机制 | CacheStrategy + DiskLruCache + RFC 7234 | ★★★☆☆ |
| 自定义拦截器 | addInterceptor vs addNetworkInterceptor | ★★★★☆ |

---

> **参考资料**
> - OkHttp 官方文档：https://square.github.io/okhttp/
> - OkHttp 源码仓库：https://github.com/square/okhttp
> - HTTP/2 规范 (RFC 7540)：https://tools.ietf.org/html/rfc7540
> - HTTP 缓存规范 (RFC 7234)：https://tools.ietf.org/html/rfc7234
