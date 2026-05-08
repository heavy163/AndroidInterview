# EventBus 事件通信框架 — 面试深度解析

> **目标**：掌握 EventBus 核心原理，从面试高频问题出发，逐层深入源码级实现，覆盖 Subscriber Index 编译期优化和主流事件总线选型对比。

---

## 第一层：高频面试问题（4+ 道核心题）

### Q1：EventBus 的订阅者注册流程是怎样的？索引如何建立？

**答案概要**：`EventBus.register(subscriber)` 是整个订阅体系的核心入口。注册时通过 `SubscriberMethodFinder` 遍历订阅者类及其父类，找到所有标注 `@Subscribe` 的方法，建立 `subscriptionsByEventType`（事件类型 → 订阅者列表）和 `typesBySubscriber`（订阅者 → 订阅事件类型列表）两个核心索引结构。

**注册流程**：

```
EventBus.getDefault().register(this)
  → subscriberMethodFinder.findSubscriberMethods(subscriberClass)
    → METHOD_CACHE.get(subscriberClass)        // 1. 优先查缓存
    → findUsingInfo(subscriberClass)           // 2. 缓存未命中，开始查找
      → findUsingReflection(subscriberClass)   // 3a. 默认：运行时反射
      → findUsingReflectionInSingleClass()     // 3b. 遍历单个类的所有方法
        → method.getAnnotation(Subscribe.class)// 4. 检查 @Subscribe 注解
        → 校验 method 参数数量、访问修饰符
        → new SubscriberMethod(method, eventType, threadMode, priority, sticky)
  → 将找到的 SubscriberMethod 列表加入 METHOD_CACHE
  → 对每个 SubscriberMethod 调用 subscribe(subscriber, subscriberMethod)
    → subscriptionsByEventType: 以 eventType 为 key，维护 CopyOnWriteArrayList<Subscription>
      → Subscription 按 priority 排序插入（优先级高的排前面）
    → typesBySubscriber: 以 subscriber 为 key，维护 List<Class<?>>
      → 记录该订阅者订阅了哪些事件类型
    → 若 sticky=true，立即查找并分发当前持有的粘性事件
```

**两个核心索引数据结构**：

| 索引 | 类型 | 用途 |
|-----|------|------|
| `subscriptionsByEventType` | `Map<Class<?>, CopyOnWriteArrayList<Subscription>>` | 事件分发时根据事件类型快速定位所有订阅者，按 priority 有序 |
| `typesBySubscriber` | `Map<Object, List<Class<?>>>` | unregister 时根据订阅者对象快速找到它订阅的所有事件类型，遍历清理 |

**关键面试点**：

- `CopyOnWriteArrayList`：事件分发时遍历订阅者列表时不加锁，适合读多写少场景
- 注册时完成排序：`Subscription` 在插入时按 `priority` 二分插入，分发时无需再排序
- 父类扫描：`findUsingReflection` 会递归扫描 `subscriberClass.getSuperclass()`，但跳过 `android.*`、`java.*`、`javax.*` 等系统类
- 缓存加速：`METHOD_CACHE` 是 `ConcurrentHashMap`，第二次注册同一类直接命中缓存

**追问**：为什么 subscriber 不用泛型约束？

> EventBus 的设计哲学是"隐式约定"，订阅者通过 `@Subscribe` 注解的方法参数类型声明它关心的事件类型，而不是通过接口约束。这种方式解耦更彻底——订阅者无需实现任何 EventBus 接口，完全 POJO。代价是编译期无法校验事件类型是否被某个订阅者消费，这是一个设计取舍。

---

### Q2：4 种 ThreadMode 的实现和区别？

**答案概要**：`@Subscribe(threadMode = ThreadMode.XXX)` 决定了订阅者方法在哪个线程执行。EventBus 通过 `Poster` 系列内部类在不同线程间切换。

| ThreadMode | 执行线程 | 实现机制 | 典型场景 |
|-----------|---------|---------|---------|
| `POSTING` | 与 post() 调用者同一线程（同步执行） | 直接反射调用订阅者方法，不经过任何线程切换 | 简单事件通知、默认模式、性能最高 |
| `MAIN` | Android 主线程 | 若当前已在主线程 → 直接调用；否则通过 `mainThreadPoster.enqueue()` 投递，`HandlerPoster`（关联 Main Looper）负责在主线程执行 | UI 更新、Toast/SnackBar |
| `MAIN_ORDERED` | Android 主线程（串行） | 类似 MAIN，但每次只执行一个事件，下一个事件等待上一个完成后执行，保证顺序 | 需要严格 UI 更新顺序的场景 |
| `BACKGROUND` | 后台线程池（单线程串行） | 若当前不在主线程 → 直接执行；若在主线程 → `backgroundPoster.enqueue()` 投递到 `ExecutorService`（单线程） | 轻量 IO、数据库操作 |
| `ASYNC` | 独立线程池（并发多线程） | 始终通过 `asyncPoster.enqueue()` 投递到 `Executors.newCachedThreadPool()` | 网络请求、耗时 IO |

**核心 Poster 实现类**：

```java
// HandlerPoster — 主线程投递器
final class HandlerPoster extends Handler implements Poster {
    private final PendingPostQueue queue;  // 待处理事件队列
    
    @Override
    public void enqueue(Subscription subscription, Object event) {
        PendingPost pendingPost = PendingPost.obtainPendingPost(subscription, event);
        synchronized (this) {
            queue.enqueue(pendingPost);
        }
        sendMessage(obtainMessage()); // 触发 handleMessage
    }
    
    @Override
    public void handleMessage(Message msg) {
        PendingPost pendingPost;
        while ((pendingPost = queue.poll()) != null) {
            // 反射调用订阅者方法（在主线程执行）
            eventBus.invokeSubscriber(pendingPost);
        }
    }
}

// BackgroundPoster — 后台串行投递器
final class BackgroundPoster implements Runnable, Poster {
    private final PendingPostQueue queue;
    private volatile boolean executorRunning;
    
    @Override
    public void enqueue(Subscription subscription, Object event) {
        PendingPost pendingPost = PendingPost.obtainPendingPost(subscription, event);
        synchronized (this) {
            queue.enqueue(pendingPost);
            if (!executorRunning) {
                executorRunning = true;
                eventBus.getExecutorService().execute(this);
            }
        }
    }
    
    @Override
    public void run() {
        while (true) {
            PendingPost pendingPost = queue.poll(1000);
            if (pendingPost == null) {
                synchronized (this) {
                    pendingPost = queue.poll();
                    if (pendingPost == null) {
                        executorRunning = false;
                        return; // 队列为空，退出
                    }
                }
            }
            eventBus.invokeSubscriber(pendingPost);
        }
    }
}
```

**面试核心区别总结**：

> POSTING 是唯一同步模式，与方法调用无异；MAIN 通过 Handler + MessageQueue 切到主线程；BACKGROUND 使用单线程池保证串行（同一批事件顺序执行，不会被并发打断）；ASYNC 总是新开线程执行，每个事件可能在不同线程并发执行，订阅者方法必须自行保证线程安全。

**追问**：多个事件的执行顺序如何保证？

| ThreadMode | 顺序保证 |
|-----------|---------|
| POSTING | 自然顺序（调用栈顺序） |
| MAIN / MAIN_ORDERED | 按 post 顺序，由 PendingPostQueue（链表/FIFO）保证 |
| BACKGROUND | 按 post 顺序串行执行，同一批次事件顺序执行，新批次排队等待 |
| ASYNC | 无顺序保证！各事件并发在不同线程执行 |

---

### Q3：粘性事件（Sticky Event）的原理是什么？

**答案概要**：粘性事件在发送时被 EventBus 缓存起来，后续注册的订阅者可以立即收到之前发送的粘性事件，就像"迟到的人也能看到之前发出去的消息"。

**完整流程**：

```
// 发送粘性事件
postSticky(event)
  → stickyEvents.put(event.getClass(), event)  // 缓存到 ConcurrentHashMap
  → post(event)                                 // 走正常分发流程

// 后续注册的订阅者
register(subscriber)
  → findSubscriberMethods(subscriber)
  → 对每个 subscriberMethod:
      → subscribe(subscriber, subscriberMethod)
      → if (subscriberMethod.sticky) {
          // 从 stickyEvents 中找到对应类型的事件
          Object stickyEvent = stickyEvents.get(eventType);
          if (stickyEvent != null) {
              checkPostStickyEventToSubscription(subscription, stickyEvent);
              // 根据 threadMode 执行分发
          }
        }
```

**stickyEvents 存储结构**：

```java
private final Map<Class<?>, Object> stickyEvents;
// 类型 → 事件实例，每个事件类型只保留最新一条（覆盖式）
```

**关键设计细节**：

1. **单一持有**：同一事件类型只保留最新一条，`putSticky()` 会覆盖旧值
2. **手动清理**：需调用 `removeStickyEvent()` 或 `removeAllStickyEvents()` 移除，否则一直驻留内存
3. **注册时触发**：仅在 `register()` 时检查，不在 `postSticky()` 后对已注册订阅者做特殊处理（因为走的就是正常 post 流程）
4. **内存泄漏风险**：粘性事件持有时间长，事件对象不宜过大（避免持有 View/Context 等）
5. **ThreadMode 兼容**：粘性事件的分发同样遵守订阅者的 threadMode 配置

**追问**：粘性事件底层用的是什么数据结构？为何是 `ConcurrentHashMap`？

> `stickyEvents` 是 `Map<Class<?>, Object>` 的 `ConcurrentHashMap` 实现。选型原因：(1) `postSticky` 和 `register` 可能在不同线程并发调用，需要线程安全；(2) 读多写少的场景，`ConcurrentHashMap` 基于分段锁/CAS 实现，读操作几乎无锁竞争；(3) Key 是事件类型 Class，需要 O(1) 查找。

---

### Q4：Subscriber Index 是什么？EventBus 3.0 注解处理器优化了什么？

**答案概要**：EventBus 3.0 引入的 Subscriber Index 是**编译期代码生成 + 索引表**机制，用来替代运行时反射扫描，显著加速订阅者注册流程。

**核心问题**：默认的 `findUsingReflection()` 存在两个痛点：
1. **运行时反射**：每个类首次注册都要反射遍历所有方法查找 `@Subscribe` 注解 —— 耗时
2. **无法混淆**：ProGuard/R8 可能重命名方法或剔除被反射引用的方法

**Subscriber Index 方案**：

```java
// 1. Gradle 引入注解处理器
annotationProcessor 'org.greenrobot:eventbus-annotation-processor:3.3.1'

// 2. 编译期自动生成索引类（以 com.example.MyActivity 为例）
public class MyEventBusIndex implements SubscriberInfoIndex {
    private static final Map<Class<?>, SubscriberInfo> SUBSCRIBER_INDEX;

    static {
        SUBSCRIBER_INDEX = new HashMap<>();
        putIndex(new SimpleSubscriberInfo(MyActivity.class, true,
            new SubscriberMethodInfo[] {
                new SubscriberMethodInfo("onMessageEvent",
                    MessageEvent.class,
                    ThreadMode.MAIN,  // threadMode
                    0,                 // priority
                    false),            // sticky
                new SubscriberMethodInfo("onDataUpdate",
                    DataUpdateEvent.class,
                    ThreadMode.BACKGROUND, 1, true)
            }
        ));
    }

    @Override
    public SubscriberInfo getSubscriberInfo(Class<?> subscriberClass) {
        return SUBSCRIBER_INDEX.get(subscriberClass);
    }
}

// 3. 配置 EventBus 使用索引
EventBus.builder()
    .addIndex(new MyEventBusIndex())
    .installDefaultEventBus();
```

**查找流程优化（findUsingInfo）**：

```
findUsingInfo(subscriberClass)
  → 优先查 SubscriberInfoIndex（O(1) HashMap 查找）
  → 命中 → 直接从 SubscriberInfo 构建 SubscriberMethod 列表（零反射）
  → 未命中 → 回退到 findUsingReflection() 常规反射扫描
  → 两阶段结果合并
```

**注解处理器工作原理**：

APT 在编译期扫描所有带 `@Subscribe` 注解的方法，提取：
- 方法名（字符串）
- 事件参数类型
- ThreadMode 枚举值
- priority 值
- sticky 布尔值

将这些信息编码为 `SubscriberMethodInfo` 数组，生成到固定格式的 `SubscriberInfoIndex` 实现类中。

**面试亮点**：

| 维度 | 无索引（反射） | 有索引（APT） |
|-----|-------------|-------------|
| 注册性能 | O(N×M) — N个类×M个方法都要反射 | O(1) — HashMap 查表 |
| 启动速度 | 首次注册有 CPU 开销 | 几乎零开销 |
| 混淆兼容 | 需 keep 规则 | 方法名字符串硬编码，天然兼容 |
| APK 体积 | 无额外代码 | +少量索引类（通常 < 50KB） |
| 维护成本 | 低 | 需配置 annotationProcessor，模块化项目注意索引合并 |

**追问**：多模块项目中 Subscriber Index 如何合并？

> 每个模块独立生成自己的索引类。在 App 模块配置 EventBus 时，将所有模块的索引类都 `addIndex()` 进去。EventBus 内部使用 `CompositeIndex` 聚合，查找时依次查询每个子索引。第三方库也有自动合并方案（如 `eventbus-index-plugin`）。

---

## 第二层：SubscriberMethodFinder — 查找与缓存

### 2.1 类层次结构

```
EventBus
  ├── SubscriberMethodFinder     ← 查找入口
  │     ├── METHOD_CACHE          ← ConcurrentHashMap<Class, List<SubscriberMethod>>
  │     ├── subscriberInfoIndexes ← List<SubscriberInfoIndex> (编译生成)
  │     ├── findSubscriberMethods()
  │     ├── findUsingInfo()       ← 优先索引，回退反射
  │     └── findUsingReflection() ← 运行时反射扫描
  └── SubscriberMethod           ← 数据类
        ├── Method method
        ├── Class<?> eventType
        ├── ThreadMode threadMode
        ├── int priority
        └── boolean sticky
```

### 2.2 缓存机制 DCL（双重检查锁定）

```java
List<SubscriberMethod> findSubscriberMethods(Class<?> subscriberClass) {
    List<SubscriberMethod> subscriberMethods = METHOD_CACHE.get(subscriberClass);
    if (subscriberMethods != null) {
        return subscriberMethods;              // 缓存命中，直接返回
    }

    // 支持 ignoreGeneratedIndex 开关
    if (ignoreGeneratedIndex) {
        subscriberMethods = findUsingReflection(subscriberClass);
    } else {
        subscriberMethods = findUsingInfo(subscriberClass);
    }

    if (subscriberMethods.isEmpty()) {
        throw new EventBusException("Subscriber " + subscriberClass
            + " and its super classes have no public methods with the @Subscribe annotation");
    } else {
        METHOD_CACHE.put(subscriberClass, subscriberMethods); // 加入缓存
        return subscriberMethods;
    }
}
```

**缓存策略分析**：

- `METHOD_CACHE` 是 `ConcurrentHashMap`，读操作无阻塞
- 写入没有加锁（只是 `put`），假设同一 Class 的查找结果恒定
- 缓存生命周期：跟随 `SubscriberMethodFinder` 实例 → 全局单例 → App 进程生命周期
- 不会过期/清理，适合 Class 数量有限的场景

### 2.3 findUsingInfo — 两阶段查找

```java
private List<SubscriberMethod> findUsingInfo(Class<?> subscriberClass) {
    FindState findState = prepareFindState();
    findState.initForSubscriber(subscriberClass);

    while (findState.clazz != null) {
        findState.subscriberInfo = getSubscriberInfo(findState);
        if (findState.subscriberInfo != null) {
            // 阶段1：索引命中 — 直接从编译期生成的 SubscriberInfo 构建
            SubscriberMethod[] array = findState.subscriberInfo.getSubscriberMethods();
            for (SubscriberMethod subscriberMethod : array) {
                if (findState.checkAdd(subscriberMethod.method, subscriberMethod.eventType)) {
                    findState.subscriberMethods.add(subscriberMethod);
                }
            }
        } else {
            // 阶段2：索引未命中 — 回退运行时反射扫描
            findUsingReflectionInSingleClass(findState);
        }
        findState.moveToSuperclass(); // 继续扫描父类
    }
    return getMethodsAndRelease(findState);
}
```

**FindState 复用池**：`FindState` 不是每次 new，而是通过 `POOL`（固定大小 4）复用，减少 GC 压力。

### 2.4 findUsingReflectionInSingleClass — 反射扫描细节

```java
private void findUsingReflectionInSingleClass(FindState findState) {
    Method[] methods;
    try {
        // 优先用 getDeclaredMethods() 减少搜索范围
        methods = findState.clazz.getDeclaredMethods();
    } catch (Throwable th) {
        // 某些系统类可能抛异常，兜底使用 getMethods()
        methods = findState.clazz.getMethods();
        findState.skipSuperClasses = true;
    }

    for (Method method : methods) {
        int modifiers = method.getModifiers();
        // 只处理 public 的非 abstract、非 static 方法
        if ((modifiers & Modifier.PUBLIC) != 0
                && (modifiers & MODIFIERS_IGNORE) == 0) {
            Class<?>[] parameterTypes = method.getParameterTypes();
            if (parameterTypes.length == 1) {  // 必须只有一个参数
                Subscribe subscribeAnnotation = method.getAnnotation(Subscribe.class);
                if (subscribeAnnotation != null) {
                    Class<?> eventType = parameterTypes[0];
                    if (findState.checkAdd(method, eventType)) {
                        ThreadMode threadMode = subscribeAnnotation.threadMode();
                        findState.subscriberMethods.add(new SubscriberMethod(
                            method, eventType, threadMode,
                            subscribeAnnotation.priority(), subscribeAnnotation.sticky()));
                    }
                }
            }
        }
    }
}
```

**checkAdd 的防重复逻辑**：如果子类和父类都定义了监听同一事件的方法，`checkAdd` 通过 `method.getName()` + `eventType` 去重，子类方法优先保留。

---

## 第三层：事件分发 — PendingPost 队列与 ThreadMode 切换

### 3.1 post() 流程全景

```java
public void post(Object event) {
    PostingThreadState postingState = currentPostingThreadState;
    List<Object> eventQueue = postingState.eventQueue;
    eventQueue.add(event);    // 加入当前线程的事件队列

    if (!postingState.isPosting) {
        postingState.isMainThread = isMainThread();
        postingState.isPosting = true;
        try {
            while (!eventQueue.isEmpty()) {
                postSingleEvent(eventQueue.remove(0), postingState);
            }
        } finally {
            postingState.isPosting = false;
        }
    }
}
```

**PostingThreadState** 是 ThreadLocal 变量：

```java
private final ThreadLocal<PostingThreadState> currentPostingThreadState = 
    new ThreadLocal<PostingThreadState>() {
        @Override
        protected PostingThreadState initialValue() {
            return new PostingThreadState();
        }
    };

final static class PostingThreadState {
    final List<Object> eventQueue = new ArrayList<>(); // 事件队列(FIFO)
    boolean isPosting;             // 是否正在分发(防重入)
    boolean isMainThread;          // 当前线程是否主线程
    Subscription subscription;     // 当前处理的订阅对象
    Object event;                  // 当前事件
    boolean canceled;              // 是否已取消
}
```

**ThreadLocal 的作用**：每个线程拥有独立的 `PostingThreadState`，多线程并发 post 时互不干扰。

### 3.2 postSingleEvent — 事件类型解析与订阅者查找

```java
private void postSingleEvent(Object event, PostingThreadState postingState) throws Error {
    Class<?> eventClass = event.getClass();
    boolean subscriptionFound = false;
    
    // lookupAllEventTypes 向上遍历所有父类和接口
    List<Class<?>> eventTypes = lookupAllEventTypes(eventClass);
    for (Class<?> clazz : eventTypes) {
        subscriptionFound |= postSingleEventForEventType(event, postingState, clazz);
    }
    if (!subscriptionFound) {
        // 没有订阅者 → 发送 NoSubscriberEvent（如已配置）
        if (sendNoSubscriberEvent) {
            post(new NoSubscriberEvent(this, event));
        }
    }
}
```

**事件继承的关键逻辑**：如果你发送的事件对象是 `LoginSuccessEvent extends BaseEvent`，那么订阅 `BaseEvent` 的方法也会收到此事件。`lookupAllEventTypes()` 向上遍历所有父类和接口，包括间接父类。

**终止条件**：遍历到 `Object.class` 停止。

### 3.3 postToSubscription — ThreadMode 分发

```java
private void postToSubscription(Subscription subscription, Object event, boolean isMainThread) {
    switch (subscription.subscriberMethod.threadMode) {
        case POSTING:
            invokeSubscriber(subscription, event);
            break;
        case MAIN:
            if (isMainThread) {
                invokeSubscriber(subscription, event);
            } else {
                mainThreadPoster.enqueue(subscription, event);
            }
            break;
        case MAIN_ORDERED:
            if (mainThreadPoster != null) {
                mainThreadPoster.enqueue(subscription, event);
            } else {
                invokeSubscriber(subscription, event);
            }
            break;
        case BACKGROUND:
            if (isMainThread) {
                backgroundPoster.enqueue(subscription, event);
            } else {
                invokeSubscriber(subscription, event);
            }
            break;
        case ASYNC:
            asyncPoster.enqueue(subscription, event);
            break;
        default:
            throw new IllegalStateException(...);
    }
}
```

### 3.4 invokeSubscriber — 反射调用

```java
void invokeSubscriber(Subscription subscription, Object event) {
    try {
        subscription.subscriberMethod.method.invoke(
            subscription.subscriber, event);
    } catch (InvocationTargetException e) {
        handleSubscriberException(subscription, event, e.getCause());
    } catch (IllegalAccessException e) {
        throw new IllegalStateException("Unexpected exception", e);
    }
}
```

**性能注意**：每次 invoke 都是一次反射调用。Subscriber Index 避免了查找阶段的反射，但调用阶段仍然需要反射。Android N+ 对反射性能有较大优化，但高频事件仍建议考虑接口回调替代。

### 3.5 PendingPost 对象池

```java
final class PendingPost {
    private final static List<PendingPost> pendingPostPool = new ArrayList<>();
    
    Object event;
    Subscription subscription;
    PendingPost next;  // 链表节点
    
    static PendingPost obtainPendingPost(Subscription subscription, Object event) {
        synchronized (pendingPostPool) {
            int size = pendingPostPool.size();
            if (size > 0) {
                PendingPost pendingPost = pendingPostPool.remove(size - 1);
                pendingPost.event = event;
                pendingPost.subscription = subscription;
                pendingPost.next = null;
                return pendingPost;
            }
        }
        return new PendingPost(event, subscription);
    }
    
    static void releasePendingPost(PendingPost pendingPost) {
        pendingPost.event = null;
        pendingPost.subscription = null;
        pendingPost.next = null;
        synchronized (pendingPostPool) {
            if (pendingPostPool.size() < 10000) {
                pendingPostPool.add(pendingPost);
            }
        }
    }
}
```

**对象池设计要点**：
- `ArrayList` 作为栈，获取和归还都在末尾操作 → O(1)
- 池上限 10000 避免无限膨胀
- `next` 字段形成链表，`PendingPostQueue` 基于此实现无锁单向链表队列

---

## 第四层：事件分发流程图

```
┌──────────────────────────────────────────────────────────────┐
│                    EventBus.post(event)                       │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
                  ┌───────────────────────┐
                  │ 获取 ThreadLocal       │
                  │ PostingThreadState    │
                  └───────────────────────┘
                              │
                              ▼
                  ┌───────────────────────────┐
                  │ eventQueue.add(event)     │
                  │ 若正在分发 → 直接返回      │
                  └───────────────────────────┘
                              │
                              ▼
                  ╔═══════════════════════════╗
                  ║  while (eventQueue 非空)  ║
                  ╚═══════════════════════════╝
                              │
                              ▼
                  ┌───────────────────────────────┐
                  │  postSingleEvent(event, ps)   │
                  │  解析事件类型及所有父类/接口    │
                  └───────────────────────────────┘
                              │
                              ▼
                  ┌────────────────────────────────────┐
                  │  lookupAllEventTypes(eventClass)   │
                  │  向上遍历父类 → List<Class<?>>     │
                  │  例如: LoginEvent → BaseEvent →    │
                  │        Object (到此处停止)          │
                  └────────────────────────────────────┘
                              │
                              ▼
                  ┌──────────────────────────────────────┐
                  │  postSingleEventForEventType()       │
                  │  遍历每个 eventType                   │
                  └──────────────────────────────────────┘
                              │
                              ▼
                  ┌─────────────────────────────────────────────┐
                  │  subscriptionsByEventType.get(eventType)    │
                  │  拿到 CopyOnWriteArrayList<Subscription>    │
                  │  (已按 priority 排序)                        │
                  └─────────────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │ for 遍历所有      │
                    │   Subscription   │
                    └──────────────────┘
                              │
                              ▼
              ┌───────────────────────────────────┐
              │   postToSubscription()            │
              │   根据 ThreadMode 选择执行方式:     │
              └───────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────────┐
          ▼                   ▼                       ▼
┌─────────────────┐ ┌─────────────────┐  ┌──────────────────────┐
│ POSTING         │ │ MAIN            │  │ BACKGROUND           │
│ → invokeSub()   │ │ → HandlerPoster │  │ → BackgroundPoster   │
│ 直接反射调用     │ │ (主线程Looper)  │  │ (单线程池,串行)       │
└─────────────────┘ └─────────────────┘  └──────────────────────┘
                              │
          ┌───────────────────┼───────────────────────┐
          ▼                                         ▼
┌──────────────────┐                    ┌──────────────────────┐
│ MAIN_ORDERED     │                    │ ASYNC                │
│ → HandlerPoster  │                    │ → AsyncPoster        │
│ 每次只执行一个    │                    │ (CachedThreadPool,   │
│ 保证严格顺序      │                    │  多线程并发)         │
└──────────────────┘                    └──────────────────────┘
                              │
                              ▼
              ┌─────────────────────────────────┐
              │ invokeSubscriber(sub, event)     │
              │ method.invoke(subscriber, event) │
              │ 反射调用 @Subscribe 方法          │
              └─────────────────────────────────┘
                              │
                              ▼
              ┌─────────────────────────────────┐
              │  异常处理:                       │
              │  handleSubscriberException()     │
              │  → 默认打印 log，不中断循环       │
              │  → 可配置 EventBusExceptionHandler│
              └─────────────────────────────────┘
```

### 注册流程（补充时序图）

```
register(subscriber)
    │
    ├─► SubscriberMethodFinder.findSubscriberMethods(subscriberClass)
    │       │
    │       ├─► METHOD_CACHE.get(subscriberClass)  ← 缓存命中则直接返回
    │       │
    │       └─► findUsingInfo(subscriberClass)     ← 缓存未命中
    │               │
    │               ├─► SubscriberInfoIndex 查表  ← APT 编译生成
    │               │       │
    │               │       └─► [命中] SubscriberInfo → SubscriberMethod[]
    │               │       └─► [未命中] 回退 findUsingReflection()
    │               │               └─► 遍历 getDeclaredMethods()
    │               │                   → 检查 @Subscribe 注解
    │               │                   → 校验 public、1个参数、非静态
    │               │                   → 构建 SubscriberMethod
    │               │
    │               └─► 循环 moveToSuperclass() 扫描父类
    │
    └─► subscribe(subscriber, subscriberMethod)  × N 次
            │
            ├─► subscriptionsByEventType[eventType].add(Subscription)
            │       └─► 按 priority 排序插入
            │
            ├─► typesBySubscriber[subscriber].add(eventType)
            │
            └─► [sticky=true] → stickyEvents.get(eventType)
                    └─► checkPostStickyEventToSubscription()
                        └─► postToSubscription() (走正常 ThreadMode 分发)
```

---

## 第五层：核心源码分析 — EventBus 架构全景

### 5.1 核心类职责速查

| 类 | 职责 | 关键字段/方法 |
|---|------|-------------|
| `EventBus` | 入口单例，统筹全局 | `register()` / `unregister()` / `post()` / `postSticky()` |
| `SubscriberMethodFinder` | 查找和缓存订阅者方法 | `findSubscriberMethods()` / `findUsingInfo()` |
| `SubscriberMethod` | 数据类，包装订阅方法元数据 | method, eventType, threadMode, priority, sticky |
| `Subscription` | 订阅关系实体 | subscriber(对象), subscriberMethod, next(链表) |
| `PendingPost` | 待投递事件对象 | event, subscription, next → 对象池复用 |
| `PendingPostQueue` | FIFO 队列（无锁链表） | enqueue() / poll() |
| `HandlerPoster` | 主线程投递，extend Handler | innerPendingPostQueue → handleMessage() |
| `BackgroundPoster` | 后台串行投递，implements Runnable | 单线程池队列 |
| `AsyncPoster` | 并发投递，implements Runnable | CachedThreadPool，每次 new |
| `PostingThreadState` | ThreadLocal 每线程状态 | eventQueue, isPosting, isMainThread |

### 5.2 EventBus Builder 模式

```java
EventBus eventBus = EventBus.builder()
    .logNoSubscriberMessages(false)       // 无订阅者时不打 log
    .sendNoSubscriberEvent(false)         // 无订阅者时不发 NoSubscriberEvent
    .sendSubscriberExceptionEvent(false)  // 订阅者异常时不发 SubscriberExceptionEvent
    .throwSubscriberException(true)       // 订阅者异常时直接抛出
    .eventInheritance(false)              // 禁用事件继承查找
    .ignoreGeneratedIndex(false)          // 是否忽略编译期生成的 Index
    .strictMethodVerification(true)       // 严格校验 @Subscribe 方法签名
    .addIndex(new MyEventBusIndex())      // 注册 Subscriber Index
    .executorService(myThreadPool)        // 自定义线程池
    .installDefaultEventBus();            // 安装为默认实例
```

### 5.3 unregister 清理流程

```java
public synchronized void unregister(Object subscriber) {
    List<Class<?>> subscribedTypes = typesBySubscriber.get(subscriber);
    if (subscribedTypes != null) {
        for (Class<?> eventType : subscribedTypes) {
            unsubscribeByEventType(subscriber, eventType);
        }
        typesBySubscriber.remove(subscriber);
    } else {
        logger.log(Level.WARNING, "Subscriber was not registered: " + subscriber.getClass());
    }
}

private void unsubscribeByEventType(Object subscriber, Class<?> eventType) {
    List<Subscription> subscriptions = subscriptionsByEventType.get(eventType);
    if (subscriptions != null) {
        int size = subscriptions.size();
        for (int i = 0; i < size; i++) {
            Subscription subscription = subscriptions.get(i);
            if (subscription.subscriber == subscriber) {
                subscription.active = false;          // 标记失效
                subscriptions.remove(i);
                i--; size--;                         // 调整索引继续遍历
            }
        }
    }
}
```

**unregister 关键点**：
- `synchronized` 保证线程安全
- 同时清理 `subscriptionsByEventType` 和 `typesBySubscriber`
- `subscription.active = false` 先标记失效，防止正在分发中的事件回调已注销的订阅者
- 被标记为 `active=false` 的 subscription 在 `postToSubscription()` 中有判空检查

### 5.4 异常处理机制

```java
// 默认：吞掉异常，打印 log
try {
    subscription.subscriberMethod.method.invoke(subscription.subscriber, event);
} catch (InvocationTargetException e) {
    handleSubscriberException(subscription, event, e.getCause());
}

// 可配置：发送 SubscriberExceptionEvent（如果有订阅者监听）
private void handleSubscriberException(Subscription subscription, Object event, Throwable cause) {
    if (event instanceof SubscriberExceptionEvent) {
        // 防止无限递归：异常事件处理中再次异常不处理
        try {
            logger.log(Level.SEVERE, "...", cause);
        } finally {
            return;
        }
    }
    if (throwSubscriberException) {
        throw new EventBusException("Invoking subscriber failed", cause);
    }
    if (sendSubscriberExceptionEvent) {
        SubscriberExceptionEvent exEvent = new SubscriberExceptionEvent(this, cause, event,
            subscription.subscriber);
        post(exEvent);
    }
}
```

---

## 第六层：EventBus vs RxBus vs LiveData — 事件总线选型

### 6.1 三种方案对比

| 维度 | EventBus | RxBus（基于 RxJava） | LiveData / StateFlow |
|-----|----------|---------------------|---------------------|
| **库依赖** | 独立库 (~50KB) | 依赖 RxJava (~2MB) | Jetpack 内置 / Kotlin 协程内置 |
| **线程调度** | 内置 ThreadMode（5种），声明式 | RxJava 丰富的 Scheduler，链式操作 | LiveData 自动主线程；StateFlow 可切换 |
| **粘性事件** | 原生支持 sticky | 用 `BehaviorSubject` / `ReplaySubject` 模拟 | LiveData 天然粘性！(最新值始终保留) |
| **生命周期感知** | 手动 register/unregister | 手动订阅 + `CompositeDisposable` 管理 | LiveData 自动感知（observe 绑定 LifecycleOwner） |
| **事件继承** | 原生支持（父类和接口） | 需自行实现（Operatormap/classOf） | 不支持，类型严格匹配 |
| **学习曲线** | 低 — 注解 + 发送者/订阅者模型 | 高 — 需理解响应式编程范式 | 低 — 观察者模式 |
| **调试难度** | 中等（post 无返回值，调用栈不清晰） | 高（链式调用栈深） | 低（observe 直接关联） |
| **null 支持** | 不支持 post null | 支持（但 RxJava 2+ 不推荐） | LiveData 支持 null；StateFlow 不支持 null |
| **有序性保证** | MAIN_ORDERED + BACKGROUND 有序；ASYNC 无序 | 通过 Scheduler 精确控制 | LiveData 主线程串行；StateFlow 可配置 |
| **最佳场景** | 组件间解耦通信、大型项目全局事件 | 复杂异步流处理、背压控制 | View-ViewModel 通信、配置变更存活 |

### 6.2 代码对比

**场景：数据更新 → UI 刷新**

```java
// ==================== EventBus ====================
// 发送
EventBus.getDefault().post(new DataUpdateEvent(data));

// 订阅
@Subscribe(threadMode = ThreadMode.MAIN)
public void onDataUpdate(DataUpdateEvent event) {
    // 更新 UI
}
// onStart: EventBus.getDefault().register(this)
// onStop:  EventBus.getDefault().unregister(this)


// ==================== RxBus ====================
// 全局单例
public class RxBus {
    private final Subject<Object> bus = PublishSubject.create().toSerialized();
    public void post(Object event) { bus.onNext(event); }
    public <T> Observable<T> toObservable(Class<T> eventType) {
        return bus.ofType(eventType);
    }
}

// 订阅
CompositeDisposable disposables = new CompositeDisposable();
disposables.add(
    RxBus.getInstance().toObservable(DataUpdateEvent.class)
        .subscribeOn(Schedulers.io())
        .observeOn(AndroidSchedulers.mainThread())
        .subscribe(event -> { /* 更新 UI */ })
);
// onDestroy: disposables.clear()


// ==================== LiveData ====================
// ViewModel 中
class SharedViewModel extends ViewModel {
    private final MutableLiveData<Data> dataUpdate = new MutableLiveData<>();
    public LiveData<Data> getDataUpdate() { return dataUpdate; }
    public void updateData(Data data) { dataUpdate.setValue(data); }
}

// Activity/Fragment 中
sharedViewModel.getDataUpdate().observe(getViewLifecycleOwner(), data -> {
    // 自动在主线程更新 UI，配置变更时自动存活
});
```

### 6.3 选型决策树

```
需要组件间全局通信？
    ├─ 是 → 需要复杂事件流处理（过滤/合并/背压）？
    │       ├─ 是 → RxBus / Kotlin Flow
    │       └─ 否 → EventBus
    │              （注解式声明，线程模式丰富，零学习成本）
    │
    └─ 否 → 通信双方在同一生命周期作用域？
            ├─ 是 → LiveData / StateFlow
            │       （最简单，自动生命周期管理，无泄漏风险）
            └─ 否 → 考虑 SharedFlow / Channel
                    （Kotlin 协程原生支持，热流/冷流可控）
```

### 6.4 EventBus 优势总结

1. **注解声明式**：`@Subscribe` 声明意图清晰，代码自文档化
2. **ThreadMode 丰富**：5 种模式覆盖所有线程切换需求，声明即生效
3. **粘性事件**：开箱即用，无需额外 Subject 承载
4. **事件继承**：发送 `LoginSuccessEvent extends BaseEvent`，订阅 `BaseEvent` 也能收到——适合事件分组
5. **体积极小**：~50KB，无额外脚手架依赖
6. **Subscriber Index**：APT 编译期优化，注册性能 O(1)，混淆友好

### 6.5 EventBus 劣势与注意事项

1. **强引用持有**：`typesBySubscriber` 持有 subscriber 强引用，忘记 unregister 会内存泄漏（尤其是 Activity/Fragment）
2. **反射调用**：即使有 Index 优化查找，最终方法调用仍需反射（`method.invoke()`），高频事件有性能损耗
3. **调试困难**：post() 发出去后调用链路不透明，出问题难以追踪事件流向
4. **类型不安全**：post 参数为 `Object`，编译期无法校验事件是否被消费
5. **事件满天飞**：缺乏结构化的事件管理机制，大项目容易陷入"事件地狱"
6. **不适合数据流**：不像 RxJava/Flow 支持 Operators（filter/map/debounce），纯事件通信

### 6.6 现代替代方案：Kotlin SharedFlow

```kotlin
// 全局事件总线 — 极简 SharedFlow 实现
object EventBus {
    private val _events = MutableSharedFlow<Any>(
        replay = 1,                    // 可选：替代粘性事件
        extraBufferCapacity = 64       // 缓冲区大小
    )
    val events: SharedFlow<Any> = _events.asSharedFlow()

    fun post(event: Any) {
        _events.tryEmit(event)
    }
}

// 使用
lifecycleScope.launch {
    EventBus.events
        .filterIsInstance<DataUpdateEvent>()
        .flowOn(Dispatchers.Default)
        .collect { event ->
            // 处理事件
        }
}
```

**SharedFlow 对比 EventBus**：
- ✅ 类型安全 + 编译期检查
- ✅ 协程原生取消，无需手动 unregister
- ✅ 丰富的流操作符
- ❌ 无内置线程切换声明式注解
- ❌ 需 Kotlin 协程环境

---

## 面试回答模板

当被问到"说说你理解的 EventBus 原理"，可按以下结构回答：

```
1. 【定位】EventBus 是 Android 组件间解耦通信的事件总线，核心机制是
   "订阅-发布"模式 + ThreadMode 声明式线程切换。

2. 【注册流程】register() → SubscriberMethodFinder 查找 @Subscribe 方法
   → 建立两个 Map 索引：subscriptionsByEventType（按事件类型快速定位订阅者）
   和 typesBySubscriber（unregister 时快速清理）。

3. 【事件分发】post() → ThreadLocal 事件队列 → 解析事件类型继承链 →
   遍历订阅者 → 根据 ThreadMode 选择 Poster 执行：
   POSTING 同步、MAIN 通过 Handler 切主线程、BACKGROUND 单线程池串行、
   ASYNC 多线程并发。

4. 【性能优化】EventBus 3.0 Subscriber Index：APT 编译期生成索引类，
   将反射扫描降为 HashMap O(1) 查表，解决反射慢和混淆问题。

5. 【粘性事件】postSticky 时将事件缓存到 ConcurrentHashMap，
   后续 register 时自动分发给 sticky=true 的订阅者。

6. 【实践心得】注意 onDestroy 中 unregister 防止内存泄漏；
   高频事件场景考虑 LiveData/StateFlow 替代；大项目建议用
   @Subscribe(threadMode = ThreadMode.MAIN_ORDERED) 保证 UI 更新有序。
```

---

*本文档覆盖 EventBus 面试六层递进内容：高频面试题 → SubscriberMethodFinder 查找缓存 → 事件分发/Poster/PendingPost → 流程图 → 核心源码架构 → EventBus vs RxBus vs LiveData 选型。*
