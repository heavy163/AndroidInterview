# Retrofit 网络封装框架 — 面试深度解析

> **面向 30k+ 面试：Retrofit 核心源码级原理，六层递进，从动态代理到自定义 Protobuf Converter。**

---

## 第一层：常见面试问题（5+ 高频题）

### Q1：Retrofit 是如何通过动态代理创建网络请求的？

**核心机制**：`Retrofit.create()` 内部使用 `Proxy.newProxyInstance()` 生成接口的动态代理对象。当你调用接口方法时，实际进入 `InvocationHandler.invoke()`，Retrofit 将 `java.lang.reflect.Method` 转换为 `ServiceMethod`，再构建 `OkHttpCall`，交给 `CallAdapter` 适配返回类型。

```java
// Retrofit.create() 核心源码简化
public <T> T create(final Class<T> service) {
    return (T) Proxy.newProxyInstance(service.getClassLoader(),
        new Class<?>[] { service },
        new InvocationHandler() {
            private final Platform platform = Platform.get();
            @Override
            public Object invoke(Object proxy, Method method, Object[] args) {
                // Object 类的方法直接调用（equals/hashCode/toString）
                if (method.getDeclaringClass() == Object.class) {
                    return method.invoke(this, args);
                }
                // 平台默认方法处理（Java 8 default方法）
                if (platform.isDefaultMethod(method)) {
                    return platform.invokeDefaultMethod(method, service, proxy, args);
                }
                // 核心：加载/解析 ServiceMethod，构建 OkHttpCall 并适配
                return loadServiceMethod(method).invoke(args);
            }
        });
}
```

**面试关键点**：
- 动态代理只在 JVM 运行时生成，无编译期代码生成（区别于 Dagger/Hilt）
- 每次方法调用都走 `InvocationHandler`，但 `ServiceMethod` 有缓存避免重复解析
- Kotlin 的 `suspend` 函数同样走此路径，由 `HttpServiceMethod` 特殊处理

---

### Q2：@GET / @POST 等注解是如何被解析的？

**解析入口**：`ServiceMethod.parseAnnotations()`，在 `loadServiceMethod()` 中首次调用时触发。

**解析流程**：
1. **方法注解**：解析 `@GET`、`@POST`、`@PUT`、`@DELETE`、`@HEAD`、`@PATCH`、`@HTTP`、`@Headers`，确定 HTTP method 和基础 URL
2. **参数注解**：按参数顺序解析 `@Path`、`@Query`、`@QueryMap`、`@Field`、`@FieldMap`、`@Part`、`@PartMap`、`@Body`、`@Header`、`@HeaderMap`、`@Url`、`@Tag`
3. **构建 `ParameterHandler` 数组**：每个参数对应一个 `ParameterHandler`（如 `Path` → `ParameterHandler.Path`）
4. **构建 `RequestFactory`**：保存 baseUrl、httpMethod、relativeUrl、headers、contentType 等

```java
// 关键数据结构
abstract class ParameterHandler<T> {
    abstract void apply(RequestBuilder builder, T value);

    // 各子类实现
    static final class Path<T> extends ParameterHandler<T> { ... }
    static final class Query<T> extends ParameterHandler<T> { ... }
    static final class Field<T> extends ParameterHandler<T> { ... }
    static final class Body<T> extends ParameterHandler<T> { ... }
    // ...
}
```

**追问点**：`@Url` 注解可以动态替换整个 URL（用于多 BaseUrl 场景），但会忽略 `@GET` 中配置的相对路径。

---

### Q3：ConverterFactory 和 CallAdapterFactory 的作用与区别？

| 维度 | ConverterFactory | CallAdapterFactory |
|:---|:---|:---|
| **作用** | 请求/响应体序列化 | 返回值类型适配 |
| **时机** | 请求时将 body 对象→`RequestBody`，响应时将 `ResponseBody`→对象 | `OkHttpCall` 包装完毕后，将 `Call<T>` 转为目标类型 |
| **典型实现** | `GsonConverterFactory`、`MoshiConverterFactory`、`ProtobufConverterFactory` | `RxJava2CallAdapterFactory`、`CoroutineCallAdapterFactory`(内置) |
| **多个工厂** | 按注册顺序，第一个匹配的生效 | 按注册顺序，第一个匹配的生效 |
| **接口方法** | `responseBodyConverter()` / `requestBodyConverter()` | `get(returnType, annotations, retrofit)` |

```java
Retrofit retrofit = new Retrofit.Builder()
    .baseUrl("https://api.example.com/")
    .addConverterFactory(GsonConverterFactory.create())      // 顺序1
    .addConverterFactory(ProtobufConverterFactory.create())  // 顺序2：Gson 优先
    .addCallAdapterFactory(RxJava2CallAdapterFactory.create())
    .build();
```

**深入追问**：Retrofit 2.6+ 内置了协程支持（`KotlinExtensions.await()`），不需要额外注册 `CallAdapterFactory`。底层通过 `HttpServiceMethod` 的 `isKotlinSuspendFunction` 判断实现。

---

### Q4：Retrofit 如何与 OkHttp、RxJava、协程协同工作？

**与 OkHttp 的关系**：
- Retrofit 是 OkHttp 的上层封装——将接口定义转为 `okhttp3.Call`
- 共享同一个 `OkHttpClient`（拦截器、连接池、缓存、DNS 等配置统一）
- `OkHttpCall` 内部持有 `okhttp3.Call.Factory`（即 `OkHttpClient`），调用 `enqueue/execute` 执行网络请求

**与 RxJava 的集成**：
```java
// 接口定义
@GET("users/{id}")
Observable<User> getUser(@Path("id") long id);

// 内部流程
// 1. loadServiceMethod → ServiceMethod.parseAnnotations()
// 2. CallAdapter 匹配 → RxJava2CallAdapter
// 3. OkHttpCall.enqueue() 回调 → ObservableEmitter.onNext/onError
// 4. 支持背压（Flowable）、单次发射（Single）、可能空（Maybe）、完成通知（Completable）
```

**与协程的集成**（Retrofit 2.6+ 内置）：
```kotlin
// suspend 函数自动适配
@GET("users/{id}")
suspend fun getUser(@Path("id") long id): User

// 底层原理
// 1. HttpServiceMethod 检测 suspend 修饰符
// 2. 使用 suspendCancellableCoroutine 挂起协程
// 3. OkHttpCall.enqueue() 回调 → continuation.resume()
// 4. 协程取消时 → call.cancel()
```

---

### Q5：Retrofit 如何处理异步请求？

Retrofit 本身不直接处理异步，完全委托给 OkHttp：

```java
// 同步执行
@GET("users/{id}")
Call<User> getUser(@Path("id") long id);
// → OkHttpCall.execute() → 阻塞当前线程

// 异步执行
@GET("users/{id}")
Call<User> getUser(@Path("id") long id);
// → OkHttpCall.enqueue() → OkHttp Dispatcher 线程池执行
```

**关键类**：`OkHttpCall` 包装了 `okhttp3.Call`，实现了 Retrofit 的 `Call<T>` 接口，在 `enqueue()` 方法中完成：
1. 用 `okhttp3.Call` 发出异步请求
2. 在回调中用 `Converter` 解析 `ResponseBody`
3. 通过 `Callback<T>` 将结果返回给调用方

---

## 第二层：标准答案与要点解析

### `loadServiceMethod()` 的缓存与解析机制

这是 Retrofit 的性能核心——避免每次方法调用都重新解析注解。

```java
private final Map<Method, ServiceMethod<?>> serviceMethodCache = new ConcurrentHashMap<>();

ServiceMethod<?> loadServiceMethod(Method method) {
    ServiceMethod<?> result = serviceMethodCache.get(method);
    if (result != null) return result;

    synchronized (serviceMethodCache) {
        result = serviceMethodCache.get(method);
        if (result == null) {
            result = ServiceMethod.parseAnnotations(this, method);
            serviceMethodCache.put(method, result);
        }
    }
    return result;
}
```

**设计要点**：
- **双重检查锁定（DCL）**：`ConcurrentHashMap.get()` + `synchronized` 块，兼顾线程安全和性能
- **缓存 Key = `java.lang.reflect.Method`**：每个接口方法唯一，天然去重
- **解析时机**：首次调用时懒加载，而非 `create()` 时预热（减少启动耗时）
- **不可变对象**：解析完成后 `ServiceMethod` 不可变，线程安全共享

### CallAdapter 的 RxJava / 协程适配原理

**统一接口**：
```java
public interface CallAdapter<R, T> {
    Type responseType();                              // 原始返回类型
    T adapt(Call<R> call);                            // 将 Call 转为目标类型
}
```

**RxJava2CallAdapter 实现**：
```java
// 简化的 Observable 适配
class RxJava2CallAdapter implements CallAdapter<Object, Observable<?>> {
    @Override
    public Observable<?> adapt(Call<Object> call) {
        // 同步 Observable（在订阅时执行）
        Observable<?> observable = Observable.create(emitter -> {
            // 执行同步请求
            Response<Object> response = call.execute();
            if (!emitter.isDisposed()) {
                emitter.onNext(response.body());
                emitter.onComplete();
            }
        });
        // 异步 Observable（后台线程执行）
        return observable.subscribeOn(Schedulers.io());
    }
}
```

**协程适配（内置 `HttpServiceMethod`）**：
```kotlin
// 核心逻辑简化
override fun adapt(call: Call<ResponseT>): Any? {
    // 检测是否为 Kotlin suspend 函数
    if (isKotlinSuspendFunction) {
        return suspendCancellableCoroutine { continuation ->
            call.enqueue(object : Callback<ResponseT> {
                override fun onResponse(call: Call<ResponseT>, response: Response<ResponseT>) {
                    if (response.isSuccessful) {
                        continuation.resume(response.body()!!)
                    } else {
                        continuation.resumeWithException(HttpException(response))
                    }
                }
                override fun onFailure(call: Call<ResponseT>, t: Throwable) {
                    continuation.resumeWithException(t)
                }
            })
            // 协程取消时同步取消网络请求
            continuation.invokeOnCancellation { call.cancel() }
        }
    }
    // ...非 suspend 的处理
}
```

---

## 第三层：核心原理深度讲解

### ServiceMethod 的完整解析链路

```
┌────────────────────────────────────────────────────────┐
│  ServiceMethod.parseAnnotations(retrofit, method)       │
├────────────────────────────────────────────────────────┤
│  1. RequestFactory.parseAnnotations()                  │
│     ├─ 解析方法注解 → httpMethod, headers, contentType │
│     ├─ 解析参数注解 → ParameterHandler[]               │
│     ├─ 处理 @Url 参数（标记 gotUrl）                    │
│     └─ 构建相对 URL 模板（含 {placeholder}）           │
│                                                         │
│  2. 解析返回类型                                        │
│     ├─ Type returnType = method.getGenericReturnType()  │
│     └─ 提取泛型信息（如 Call<User> → User）             │
│                                                         │
│  3. 匹配 CallAdapter                                    │
│     ├─ 遍历 callAdapterFactories                         │
│     ├─ factory.get(returnType, annotations, retrofit)    │
│     └─ 第一个返回非 null 的工厂生效                     │
│                                                         │
│  4. 匹配 Converter                                      │
│     ├─ responseConverter: ResponseBody → 目标类型       │
│     └─ requestConverter: 请求体对象 → RequestBody       │
└────────────────────────────────────────────────────────┘
```

### CallAdapter 匹配策略详解

```java
// Retrofit 内置的默认 CallAdapter（兜底）
// 仅处理返回类型为 Call.class 的情况
static final class DefaultCallAdapterFactory extends CallAdapter.Factory {
    @Override
    public CallAdapter<?, ?> get(Type returnType, Annotation[] annotations, Retrofit retrofit) {
        if (getRawType(returnType) != Call.class) return null;  // 不匹配则跳过
        final Type responseType = getCallResponseType(returnType);
        return new CallAdapter<Object, Call<?>>() {
            @Override public Type responseType() { return responseType; }
            @Override public Call<?> adapt(Call<Object> call) { return call; }
        };
    }
}
```

**自定义 CallAdapter 工厂的添加顺序影响**：
- 内置 `DefaultCallAdapterFactory` 在 `platform.defaultCallAdapterFactories()` 中添加
- 用户通过 `addCallAdapterFactory()` 添加的工厂在列表**头部**
- 匹配时**从头到尾**遍历，第一个 `get() != null` 的生效
- 这意味着用户的工厂优先级高于内置默认工厂

---

## 第四层：Retrofit.create() 完整调用链（时序图）

```
Caller                    Retrofit                  ServiceMethod              OkHttpCall
  │                          │                          │                          │
  │──create(ApiService)─────>│                          │                          │
  │                          │──Proxy.newProxyInstance()                          │
  │                          │  (生成动态代理对象)     │                          │
  │<────apiService实例────────│                          │                          │
  │                          │                          │                          │
  │──api.getUser(1)─────────>│                          │                          │
  │  ↓ 进入 InvocationHandler                          │                          │
  │                          │──loadServiceMethod(m)───>│                          │
  │                          │  查缓存(Miss)            │                          │
  │                          │                          │──parseAnnotations()      │
  │                          │                          │  ├─RequestFactory.parse  │
  │                          │                          │  ├─匹配CallAdapter       │
  │                          │                          │  └─匹配Converter         │
  │                          │<──返回ServiceMethod──────│                          │
  │                          │                          │                          │
  │                          │──serviceMethod.invoke()──│                          │
  │                          │                          │──callAdapter.adapt()────>│
  │                          │                          │                          │──创建OkHttp Call
  │                          │                          │<──返回Call<T>────────────│
  │                          │<──返回代理Call──────────│                          │
  │<────Call<User>───────────│                          │                          │
  │                          │                          │                          │
  │──call.enqueue()─────────────────────────────────────────────────────────────>│
  │                          │                          │                          │──okHttpCall.enqueue()
  │                          │                          │                          │   ↓
  │                          │                          │                          │──ResponseBody
  │                          │                          │                          │──converter.convert()
  │                          │                          │                          │──callback.onResponse()
  │<────User 对象─────────────────────────────────────────────────────────────────│
```

**关键时序节点**：
1. `create()` 仅创建代理对象，不做任何解析（懒加载）
2. 首次方法调用触发 `loadServiceMethod()` → `parseAnnotations()`（约 0.5-2ms）
3. 后续调用直接从 `serviceMethodCache` 获取（O(1) HashMap 查询）
4. `OkHttpCall` 在每次方法调用时新建，请求执行完毕即废弃

---

## 第五层：核心源码分析

### Retrofit.create() 线程安全与性能设计

```java
// 源码关键片段（Retrofit.java）
public <T> T create(final Class<T> service) {
    validateServiceInterface(service);  // 1. 校验是否为接口
    return (T) Proxy.newProxyInstance(
        service.getClassLoader(),
        new Class<?>[] { service },
        new InvocationHandler() {
            private final Object[] emptyArgs = new Object[0];  // 复用空参数数组
            private final Platform platform = Platform.get();

            @Override
            public Object invoke(Object proxy, Method method, @Nullable Object[] args)
                    throws Throwable {
                // 处理 Object 方法
                if (method.getDeclaringClass() == Object.class) {
                    return method.invoke(this, args);
                }
                // 处理 default 方法（Android API 24+ / Java 8）
                if (platform.isDefaultMethod(method)) {
                    return platform.invokeDefaultMethod(method, service, proxy, args);
                }
                // 空安全参数
                args = args != null ? args : emptyArgs;
                // 平台特定处理（Android vs Java）
                return platform.isDefaultMethod(method)
                    ? platform.invokeDefaultMethod(method, service, proxy, args)
                    : loadServiceMethod(method).invoke(args);
            }
        });
}
```

**设计精华**：
- `emptyArgs` 复用：无参方法调用时避免反复创建空数组
- `validateServiceInterface()`：启动即失败（fail-fast），防止运行时出现诡异错误
- `platform` 分离：Android 用 API 24+ 的 `MethodHandle` 处理 default 方法，Java 用反射

### ServiceMethod.invoke() 的请求构建

```java
// HttpServiceMethod.invoke() 简化逻辑
@Override
final @Nullable ReturnT invoke(Object[] args) {
    // 1. 用 ParameterHandler 数组将参数写入 RequestBuilder
    // 2. 构建 okhttp3.Call
    return callAdapter.adapt(
        new OkHttpCall<>(requestFactory, args, callFactory, responseConverter)
    );
}

// OkHttpCall 创建 okhttp3.Request 的过程
private okhttp3.Call createRawCall() throws IOException {
    // RequestFactory.create() 使用 args 构建完整 Request
    okhttp3.Call call = callFactory.newCall(requestFactory.create(args));
    if (call == null) {
        throw new NullPointerException("Call.Factory returned null.");
    }
    return call;
}
```

---

## 第六层：实际应用场景 — 自定义 Protobuf Converter

### 为什么需要自定义 Converter？

1. **Gson/Jackson 性能瓶颈**：JSON 序列化在大量数据传输场景下 CPU 和内存开销大
2. **Protobuf 优势**：二进制编码，体积小（30%-50%），解析快（3-10x），强类型校验
3. **实际场景**：IM 消息推送、IoT 设备通信、大数据量 API

### 自定义 Protobuf Converter 完整实现

```java
public class ProtoConverterFactory extends Converter.Factory {
    private final Map<Class<?>, Parser<?>> parserCache = new ConcurrentHashMap<>();

    public static ProtoConverterFactory create() {
        return new ProtoConverterFactory();
    }

    @Override
    public @Nullable Converter<ResponseBody, ?> responseBodyConverter(
            Type type, Annotation[] annotations, Retrofit retrofit) {
        // 只处理实现了 MessageLite 接口的类型（Protobuf 消息基类）
        if (!(type instanceof Class<?>)) return null;
        Class<?> clazz = (Class<?>) type;
        if (!MessageLite.class.isAssignableFrom(clazz)) return null;

        return new ProtoResponseBodyConverter<>(clazz);
    }

    @Override
    public @Nullable Converter<?, RequestBody> requestBodyConverter(
            Type type, Annotation[] parameterAnnotations,
            Annotation[] methodAnnotations, Retrofit retrofit) {
        if (!(type instanceof Class<?>)) return null;
        Class<?> clazz = (Class<?>) type;
        if (!MessageLite.class.isAssignableFrom(clazz)) return null;

        return new ProtoRequestBodyConverter<>();
    }

    // 响应转换：ResponseBody → Protobuf Message
    static class ProtoResponseBodyConverter<T extends MessageLite>
            implements Converter<ResponseBody, T> {
        private final Class<?> clazz;

        ProtoResponseBodyConverter(Class<?> clazz) { this.clazz = clazz; }

        @Override
        public T convert(ResponseBody value) throws IOException {
            try {
                // 通过反射找到 parser() 静态方法
                Method parserMethod = clazz.getDeclaredMethod("parser");
                @SuppressWarnings("unchecked")
                Parser<T> parser = (Parser<T>) parserMethod.invoke(null);
                // 解析二进制流
                return parser.parseFrom(value.byteStream());
            } catch (Exception e) {
                throw new IOException("Protobuf parsing failed for " + clazz.getName(), e);
            } finally {
                value.close();
            }
        }
    }

    // 请求转换：Protobuf Message → RequestBody
    static class ProtoRequestBodyConverter<T extends MessageLite>
            implements Converter<T, RequestBody> {
        private static final MediaType MEDIA_TYPE =
            MediaType.parse("application/x-protobuf");

        @Override
        public RequestBody convert(T value) {
            byte[] bytes = value.toByteArray();
            return RequestBody.create(MEDIA_TYPE, bytes);
        }
    }
}
```

**使用示例**：
```java
// 1. 定义 .proto 文件
// message User { required int64 id = 1; required string name = 2; }

// 2. Retrofit 配置
Retrofit retrofit = new Retrofit.Builder()
    .baseUrl("https://api.example.com/")
    .addConverterFactory(ProtoConverterFactory.create())  // Protobuf 优先
    .addConverterFactory(GsonConverterFactory.create())   // JSON 兜底
    .build();

// 3. 接口定义
interface ApiService {
    @GET("users/{id}")
    Call<UserProto.User> getUserProto(@Path("id") long id);  // 走 Protobuf

    @GET("users/{id}")
    Call<User> getUserJson(@Path("id") long id);             // 走 Gson
}
```

**关键设计要点**：
- **类型检查**：通过 `MessageLite.isAssignableFrom()` 判断是否为 Protobuf 消息
- **parser 反射**：Protobuf 每个消息类都有静态 `parser()` 方法，通过反射调用
- **Content-Type**：请求头设置为 `application/x-protobuf`，服务端据此识别
- **工厂顺序**：Protobuf 工厂在 Gson 之前注册，优先匹配 Protobuf 返回类型

---

## 进阶面试追问

### 追问 1：如果接口方法返回 `LiveData<User>` 怎么支持？

需要自定义 `CallAdapterFactory`，将 `LiveDataCallAdapter` 注册到 Retrofit：
```java
class LiveDataCallAdapterFactory extends CallAdapter.Factory {
    @Override
    public CallAdapter<?, ?> get(Type returnType, Annotation[] annotations, Retrofit retrofit) {
        if (getRawType(returnType) != LiveData.class) return null;
        Type observableType = getParameterUpperBound(0, (ParameterizedType) returnType);
        return new LiveDataCallAdapter<>(observableType);
    }
}

class LiveDataCallAdapter<R> implements CallAdapter<R, LiveData<R>> {
    @Override public Type responseType() { return responseType; }
    @Override public LiveData<R> adapt(Call<R> call) {
        return new LiveData<R>() {
            @Override protected void onActive() {
                call.enqueue(new Callback<R>() { /* ... */ });
            }
        };
    }
}
```

### 追问 2：Retrofit 怎样实现多 BaseUrl 支持？

方法级 `@Url` 注解可以覆盖全局 baseUrl：
```java
interface ApiService {
    @GET  // 不写相对路径
    Call<User> getUserDynamic(@Url String fullUrl);
}
// 调用时传入完整 URL
apiService.getUserDynamic("https://other-api.example.com/users/1");
```

更优雅的方案是自定义 `BaseUrlInterceptor`（OkHttp 拦截器），根据请求头动态替换 host。

### 追问 3：静态代理 vs 动态代理，Retrofit 为什么选动态代理？

| 对比维度 | 静态代理（编译期生成） | 动态代理（运行时生成） |
|:---|:---|:---|
| **实现方式** | APT + 代码生成（类似 Dagger） | `Proxy.newProxyInstance()` |
| **构建速度** | 增加编译时间 | 无额外编译开销 |
| **调试** | 可查看生成代码 | 代理类不可见 |
| **灵活性** | 编译期确定 | 运行时动态适配 |
| **性能** | 直接调用，零反射 | 首次反射解析有微小开销 |

Retrofit 选动态代理的原因：接口定义简单清晰，运行时解析开销可控（有缓存），无需引入 APT 复杂度。

---

## 总结：Retrofit 面试知识图谱

```
Retrofit.create()
    │
    ├── Proxy.newProxyInstance()          ← 动态代理核心
    │       └── InvocationHandler.invoke()
    │               │
    │               ├── loadServiceMethod()   ← 缓存(DCL) + 懒解析
    │               │       └── ServiceMethod.parseAnnotations()
    │               │               ├── RequestFactory     ← @GET/@POST 解析
    │               │               ├── ParameterHandler[]  ← @Path/@Query/@Body
    │               │               ├── Converter           ← JSON/Protobuf
    │               │               └── CallAdapter         ← RxJava/Coroutine
    │               │
    │               └── serviceMethod.invoke(args)
    │                       └── OkHttpCall                  ← 包装 okhttp3.Call
    │                               ├── enqueue()           ← 异步
    │                               └── execute()           ← 同步
    │
    └── OkHttpClient                     ← 底层网络引擎
            ├── 拦截器链
            ├── 连接池
            ├── 缓存
            └── Dispatcher 线程池
```

**面试核心话术**：

> "Retrofit 的核心是动态代理 + 注解解析 + 工厂模式。`Retrofit.create()` 通过 `Proxy.newProxyInstance()` 生成接口代理，每次方法调用进入 `InvocationHandler`，触发 `loadServiceMethod()` 解析注解（首次会缓存），构建 `ServiceMethod` 对象。`ServiceMethod` 包含 `RequestFactory`（负责构建 HTTP 请求）、`Converter`（负责序列化/反序列化）、`CallAdapter`（负责返回类型适配，如 RxJava Observable、Kotlin 协程）。最终通过 `OkHttpCall` 将所有信息转换为 `okhttp3.Call` 并执行网络请求。这种设计实现了接口定义与网络实现完全解耦，同时保持了极高的可扩展性。"

---

*本文档为 Retrofit 面试六层递进内容，覆盖动态代理、注解解析、Converter/CallAdapter 机制、源码调用链及自定义 Protobuf Converter。*
