# RxJava 响应式编程 — 面试深度解析

> **RxJava** 是基于观察者模式的异步事件驱动框架，核心思想是"一切皆流（Everything is a stream）"。
> 本文按六层递进结构，从面试考点出发，深入到源码原理，再到实战封装，全面覆盖 RxJava 知识体系。

---

## 第一层：高频面试题（5+）

### Q1：map / flatMap / concatMap 的区别与适用场景？

这是 RxJava 面试的必考题，三个操作符的核心区别在于 **如何展开内部 Observable** 以及 **事件顺序保障**。

| 操作符 | 展开方式 | 顺序保障 | 适用场景 |
|--------|----------|:---:|----------|
| **map** | 一对一同步转换（不展开 Observable） | ✅ 严格保持 | 简单数据转换 |
| **flatMap** | 并发展开，乱序合并 | ❌ 不保证 | 并行网络请求 |
| **concatMap** | 串行展开，严格顺序 | ✅ 严格保持 | 顺序依赖操作 |

**源码本质差异：**

- `map` 内部调用 `new ObservableMap()`，在 `onNext()` 中直接 `apply()` 转换后传给下游；
- `flatMap` 内部调用 `merge()`，对所有内部 Observable 同时订阅，事件到达即下发——因此顺序不可控；
- `concatMap` 内部调用 `concat()`，维护内部队列，上一个 Observable 不 `onComplete` 绝不订阅下一个。

**典型面试回答：**
> "map 用于同步数据转换，如把 Integer 转成 String；flatMap 用于并发场景，如批量上传文件，需注意乱序；concatMap 用于必须串行的场景，比如先登录获取 token 再请求用户信息。性能上 flatMap 最优但顺序不可控，concatMap 保证顺序但会阻塞后续 Observable 的启动。"

**补充陷阱：** `concatMap` 在内部 Observable 永不 `onComplete` 时会形成永久阻塞（内存泄漏风险），生产环境建议加 `timeout()` 兜底。

---

### Q2：Schedulers 线程调度模型（computation / io / newThread / single / trampoline）

RxJava 通过 `Schedulers` 解耦了"数据生产"与"数据消费"的执行线程，这是它相比传统异步方案最大的优势。

| 调度器 | 线程池类型 | 核心线程数 | 适用场景 |
|--------|-----------|:---:|----------|
| `Schedulers.computation()` | 固定线程池 | CPU核心数 | 计算密集型（JSON解析、数学运算） |
| `Schedulers.io()` | 弹性线程池（无界） | 按需增长 | IO密集型（网络、文件、数据库） |
| `Schedulers.newThread()` | 每任务新线程 | — | 耗时较长的独立任务 |
| `Schedulers.single()` | 单线程池 | 1 | 串行执行、全局顺序保障 |
| `Schedulers.trampoline()` | 当前线程队列 | — | 延迟执行、测试环境 |

**面试追问：为什么不能混用？**

> computation() 的线程数等于 `Runtime.getRuntime().availableProcessors()`，若在其中执行阻塞 IO 操作，会耗尽计算资源导致 CPU 饥饿。io() 使用 `CachedThreadPool`，线程可无限增长——适合 IO 阻塞等待，不适合 CPU 密集。

**Android 专属：`AndroidSchedulers.mainThread()`** 本质是向主线程 `Looper` 投递消息，内部使用 `Handler`。

---

### Q3：subscribeOn 与 observeOn 的调用链原理

这是 RxJava 线程切换的灵魂，核心区别一句话：

> **subscribeOn 改变"上游"的订阅线程，observeOn 改变"下游"的观察线程。**

**调用链原理：**

```
observable
    .subscribeOn(Schedulers.io())       // ① 数据生产在 io 线程
    .observeOn(AndroidSchedulers.mainThread())  // ② 下游消费切到主线程
    .map(data -> transform(data))       // ③ 在 main 线程执行
    .observeOn(Schedulers.computation()) // ④ 再次切线程
    .filter(data -> check(data))        // ⑤ 在 computation 线程执行
    .subscribe(observer);
```

**关键规则（面试高频）：**

1. **subscribeOn 只有第一次生效**：链中多次调用 `subscribeOn(A).subscribeOn(B)`，最终以最靠近 `create()` 的那个为准（即 A），因为订阅是从下往上的；
2. **observeOn 每次调用都切换**：每遇到一个 `observeOn`，其后操作符就切换到对应线程执行；
3. **subscribeOn 决定 `onSubscribe()` 的线程**：subscribe 上游的 `doOnSubscribe` 受 subscribeOn 影响（往下走到订阅点时触发）。

**源码精髓：**
- `subscribeOn` 通过 `ObservableSubscribeOn` 包装上游，在其 `subscribeActual()` 中用 Scheduler 的 `Worker.schedule()` 把整体订阅动作扔到指定线程；
- `observeOn` 通过 `ObservableObserveOn` 包装下游，在其 `onNext()` 中用 Worker 把每个数据项调度到指定线程再发给下游。

---

### Q4：背压策略 — Flowable 的 BackpressureStrategy

**背压（Backpressure）** 是生产者发射速度远大于消费者处理速度时的一种流量控制机制。

Observable（1.x/2.x）不支持背压，RxJava 2 引入了 `Flowable` 来专门解决此问题。

| 策略 | 枚举值 | 行为 | 适用场景 |
|------|--------|------|----------|
| **MISSING** | `MISSING` | 不缓存也不丢弃，下游自己处理 | 下游使用 `onBackpressureXxx()` 自行控制 |
| **ERROR** | `ERROR` | 超出默认128缓存时抛出 `MissingBackpressureException` | 要求生产=消费的严格场景 |
| **BUFFER** | `BUFFER` | 无限缓冲区（可能 OOM） | 可预见数据量不大的场景 |
| **DROP** | `DROP` | 丢弃无法消费的新数据 | 实时的、允许丢数据的场景 |
| **LATEST** | `LATEST` | 只保留最新一条，之前未消费的全部丢弃 | UI 展示最新状态（如搜索联想） |

**面试回答要点：**

> "背压的核心是 Flowable 内置的一个大小为 128 的水位缓冲区。当缓冲区满时，根据策略决定行为。DROP 直接丢弃，LATEST 保留最后一个，BUFFER 无限缓存，ERROR 直接抛异常。生产环境推荐 LATEST + `onBackpressureLatest()` 组合用于实时数据流，网络请求场景推荐使用 Observable 就够了因为不太可能出现背压。"

**源码要点：** `FlowableCreate` 内部通过 `BackpressureHelper` 维护一个 `AtomicLong requested`，下游通过 `request(n)` 向上游告知处理能力。

---

### Q5：链式调用中操作符的执行顺序

RxJava 的链式调用采用 **装饰器模式（Decorator Pattern）**，每个操作符返回一个新的 Observable 包裹前一个。

```java
Observable.just(1, 2, 3)
    .map(i -> i * 2)          // ObservableMap
    .filter(i -> i > 3)       // ObservableFilter
    .subscribe(observer);     // ObservableFilter.subscribeActual()
```

**订阅阶段（自下而上）：**

```
subscribe(observer)
 → ObservableFilter.subscribeActual(observer)
   → ObservableMap.subscribeActual(filterObserver)
     → ObservableJust.subscribeActual(mapObserver)
       → observer.onSubscribe()
       → observer.onNext(1,2,3)  // 发射数据
```

**发射阶段（自上而下）：**

```
ObservableJust 发射 onNext(1)
 → ObservableMap.onNext(1) → apply() → onNext(2) 发给下游
   → ObservableFilter.onNext(2) → test() → 不满足条件，不发给下游
→ ObservableJust 发射 onNext(2)
 → ObservableMap.onNext(2) → onNext(4)
   → ObservableFilter.onNext(4) → test() → onNext(4) 发给最终 observer
```

**核心结论：** 订阅从下游往上溯，数据从上往下流。期间每个操作符可拦截、转换、过滤、甚至拦截整个事件序列。

---

## 第二层：标准答案与要点解析

### 要点1：Observable 五种创建方式的底层差异

| 创建方式 | 底层类 | 线程特征 | 背压支持 |
|----------|--------|:---:|:---:|
| `Observable.just()` | `ObservableJust` → `ScalarCallable` | 同步发射 | — |
| `Observable.create()` | `ObservableCreate` | 由 emitter 决定 | ✅ Flowable |
| `Observable.fromIterable()` | `ObservableFromIterable` | 同步迭代 | ✅ Flowable |
| `Observable.interval()` | `ObservableInterval` | 异步（computation） | ✅ Flowable |
| `Observable.defer()` | `ObservableDefer` | 每次订阅重新创建 | — |

**面试追问：`just()` 和 `defer()` 的区别？**
> `just()` 在 Observable 创建时数据就已确定（不管有没有人 subscribe），`defer()` 每次 subscribe 时才懒创建 Observable，适合动态获取最新状态的场景（比如缓存实时读取）。

### 要点2：Subject 与 Processor

- **Subject**：既是 Observable 也是 Observer，可以手动调用 `onNext()` 发射数据，常用于事件总线（RxBus）；
- **Processor**：支持背压的 Subject（`AsyncProcessor`、`BehaviorProcessor`、`PublishProcessor`、`ReplayProcessor`）；
- `BehaviorSubject` / `BehaviorProcessor` 会缓存最近一个值，新订阅者立即收到最近的缓存值，适用于状态管理。

### 要点3：Disposable 资源管理

- `dispose()`：主动切断订阅链并释放资源，调用后不可恢复；
- `clear()`：仅清空 `CompositeDisposable` 中的引用，不调用 `dispose()`；
- **最佳实践**：在 Activity/Fragment 的生命周期中使用 `CompositeDisposable` 统一管理，在 `onDestroy()` 中调用 `compositeDisposable.clear()` 或 `dispose()`。

---

## 第三层：核心原理深度讲解（源码分析）

### 3.1 ObservableCreate 的订阅流程

`Observable.create()` 是理解 RxJava 订阅机制的最佳入口。

```java
// Observable.java (核心代码简化)
public static <T> Observable<T> create(ObservableOnSubscribe<T> source) {
    return RxJavaPlugins.onAssembly(new ObservableCreate<>(source));
}
```

**ObservableCreate 内部结构：**

```java
public final class ObservableCreate<T> extends Observable<T> {
    final ObservableOnSubscribe<T> source;

    public ObservableCreate(ObservableOnSubscribe<T> source) {
        this.source = source;
    }

    @Override
    protected void subscribeActual(Observer<? super T> observer) {
        // 1. 创建发射器（Emitter），包装下游 Observer
        CreateEmitter<T> emitter = new CreateEmitter<>(observer);

        // 2. 先回调 observer.onSubscribe(emitter)，让下游获取 Disposable
        observer.onSubscribe(emitter);

        try {
            // 3. 执行用户定义的订阅逻辑（如发射数据）
            source.subscribe(emitter);
        } catch (Throwable ex) {
            emitter.onError(ex);
        }
    }
}
```

**CreateEmitter 关键逻辑：**

```java
static final class CreateEmitter<T> implements ObservableEmitter<T> {
    final Observer<? super T> observer;
    volatile boolean disposed;

    @Override
    public void onNext(T t) {
        if (!disposed) {
            observer.onNext(t);  // 直接透传给下游 Observer
        }
    }

    @Override
    public void onComplete() {
        if (!disposed) {
            disposed = true;
            observer.onComplete();
        }
    }

    @Override
    public void dispose() {
        disposed = true;  // 标记已取消，后续 onNext 不再透传
    }
}
```

**订阅流程时序（逐帧）：**

1. `observable.create(...)` → `new ObservableCreate(source)`（只是保存 source，未执行）
2. `observable.subscribe(observer)` → 调用 `subscribeActual(observer)`
3. `subscribeActual` 内部创建 `CreateEmitter`（持有下游 observer）
4. 回调 `observer.onSubscribe(emitter)`（下游拿到 disposable 句柄）
5. 执行 `source.subscribe(emitter)`（用户代码开始执行，调用 emitter.onNext/onError/onComplete）
6. 每次 `emitter.onNext(t)` 检查 `disposed` 状态，未取消则透传
7. `emitter.onComplete()` 设置 `disposed=true`，后续 `onNext` 无效

**关键设计模式：** `CreateEmitter` 同时实现了 `ObservableEmitter`（给上游发数据用）和 `Disposable`（给下游取消用），这种"一体两面"的设计是 RxJava 资源管理的核心。

---

### 3.2 lift() 操作符变换原理

`lift()` 是 RxJava 操作符系统的基石，几乎所有变换操作符底层都通过 `lift()` 实现。

```java
// Observable.java
public final <R> Observable<R> lift(ObservableOperator<? extends R, ? super T> lifter) {
    return RxJavaPlugins.onAssembly(new ObservableLift<>(this, lifter));
}
```

**ObservableOperator 接口：**

```java
public interface ObservableOperator<Downstream, Upstream> {
    Observer<? super Upstream> apply(Observer<? super Downstream> observer) throws Exception;
}
```

核心思想：**把下游 Observer 包装成一个新的 Observer 返回给上游**——即"狸猫换太子"。

**以 map 为例：**

```java
// ObservableMap 本质上是通过 lift 实现的简化版
public final <R> Observable<R> map(Function<? super T, ? extends R> mapper) {
    return lift(new ObservableMap<>(mapper));
}

class ObservableMap<T, R> implements ObservableOperator<R, T> {
    final Function<? super T, ? extends R> mapper;

    @Override
    public Observer<? super T> apply(Observer<? super R> downstream) {
        // 返回一个新的 Observer，拦截 upstream 发来的 T，转成 R 后给 downstream
        return new MapObserver<>(downstream, mapper);
    }
}

class MapObserver<T, R> extends BasicFuseableObserver<T, R> {
    @Override
    public void onNext(T t) {
        R result = mapper.apply(t);   // T → R 转换
        downstream.onNext(result);    // 发射转换后的数据
    }
}
```

**lift() 变换流程（以 `.map().filter()` 为例）：**

```
原始: Observable → lift(mapOp) → 返回 ObservableLift → lift(filterOp) → 返回 ObservableLift → subscribe

subscribe(observer):
  ObservableLift₂.subscribeActual(observer)
    → filterOp.apply(observer) 得到 filterObserver
    → 上游 ObservableLift₁.subscribeActual(filterObserver)
      → mapOp.apply(filterObserver) 得到 mapObserver
      → 上游 Observable.subscribeActual(mapObserver)
```

**设计精髓：**
- 每个操作符都是一个 `ObservableOperator`，它不直接操作数据，而是"改造 Observer"；
- 订阅时自下而上层层包装 Observer，数据发射时自上而下一个一个 `onNext` 传递；
- 这种"代理/包装"模式使得操作符可以无限组合（链式调用），是 RxJava 函数式编程思想的最佳体现。

---

## 第四层：原理流程图（时序图）

### 订阅 + 操作符链 全流程时序图

```
时间轴 →

下游 subscribe()                    Observer链构建                     上游发射数据
═══════════════                   ═══════════════                    ══════════════

subscribe(observer)
    │
    ▼
ObservableLift(Map)
    │  subscribeActual(observer)
    │
    ▼                                                  CreateEmitter(mapObserver)
ObservableLift(Filter)                                 │
    │  subscribeActual(mapObserver)                    ▼
    │                                                 mapObserver.onSubscribe(emitter)
    ▼                                                  │
ObservableCreate                                       ▼
    │  subscribeActual(filterObserver)                 filterObserver.onSubscribe(d)
    │                                                  │
    ▼ 创建 CreateEmitter(filterObserver)               ▼
    │  filterObserver.onSubscribe(emitter)             observer.onSubscribe(d)  ← 下游拿到Disposable
    │                                                  │
    │★ source.subscribe(emitter) ────────────────────►│
    │                                                  │ emitter.onNext("A")
    │                                                  ▼
    │                                        filterObserver.onNext("A")
    │                                                  │  apply("A") → 转大写
    │                                                  ▼
    │                                        mapObserver.onNext("A")
    │                                                  │  test("A") → 是否满足条件
    │                                                  ▼
    │                                        observer.onNext("A") ✅
    │
    │  emitter.onComplete() ─────────────────────────►│
    │                                        filterObserver.onComplete()
    │                                                  │
    │                                                  ▼
    │                                        mapObserver.onComplete()
    │                                                  │
    │                                                  ▼
    │                                        observer.onComplete()
    ▼
（订阅完成，整个链式调用结束）
```

**关键时序说明：**

1. **构建阶段（紫色）**：从下往上（subscribe → filter → map → create），每个操作符生成自己的 Observer 传给上游，形成 Observer 链；
2. **回调 onSubscribe 阶段（蓝色）**：从上往下（create → map → filter → observer），把 Disposable（Emitter）层层透传到最终订阅者；
3. **数据发射阶段（橙色）**：从上往下（create 发射 → filter 处理 → map 处理 → observer 接收），数据在 Observer 链中顺序流转；
4. **取消机制**：任一层 Observer 调用 `dispose()`，都会阻止后续 `onNext` 向下传递，且通过 `CreateEmitter.disposed` 可拦截上游继续发射。

---

## 第五层：核心源码分析（补充）

### 5.1 Scheduler 调度机制源码

`subscribeOn` 如何改变订阅线程：

```java
public final class ObservableSubscribeOn<T> extends AbstractObservableWithUpstream<T, T> {
    final Scheduler scheduler;

    @Override
    public void subscribeActual(Observer<? super T> observer) {
        // 1. 创建一个在指定 Scheduler 上执行的 Observer 包装
        SubscribeOnObserver<T> parent = new SubscribeOnObserver<>(observer);

        // 2. 先回调下游 onSubscribe（在当前线程）
        observer.onSubscribe(parent);

        // 3. 把"订阅上游"这个动作扔到 Scheduler 线程执行
        parent.setDisposable(scheduler.scheduleDirect(new SubscribeTask(parent)));
    }

    // 在 Scheduler 线程中执行
    final class SubscribeTask implements Runnable {
        @Override
        public void run() {
            // ★ 这里是关键：在 Scheduler 线程中订阅上游 Observable
            source.subscribe(parent);
        }
    }
}
```

**observeOn 如何切换线程：**

```java
public final class ObservableObserveOn<T> extends AbstractObservableWithUpstream<T, T> {
    final Scheduler scheduler;

    @Override
    protected void subscribeActual(Observer<? super T> observer) {
        // 创建 Worker（绑定线程）
        Scheduler.Worker w = scheduler.createWorker();
        // 包装下游 Observer
        ObserveOnObserver<T> parent = new ObserveOnObserver<>(observer, w);
        // 订阅上游（但上游 onNext 时会被切换到 Scheduler 线程再发给下游）
        source.subscribe(parent);
    }
}

// ObserveOnObserver 中
@Override
public void onNext(T t) {
    // ★ 把 onNext 任务扔到 Scheduler 线程执行，再调用下游 observer.onNext()
    worker.schedule(() -> downstream.onNext(t));
}
```

**核心区别总结：**
- `subscribeOn` → 改变 `source.subscribe(parent)` 的执行线程（整个上游订阅动作切换）；
- `observeOn` → 改变 `downstream.onNext(t)` 的执行线程（每个数据项的下发动作切换）。

---

## 第六层：实际应用场景与项目经验

### 6.1 网络请求 + 数据库查询的 RxJava 链式封装（Retrofit + Room）

```java
/**
 * 场景：先从本地数据库获取缓存数据显示到 UI，再发起网络请求获取最新数据，
 *       成功后更新数据库和 UI，失败则只展示本地缓存。
 */
public class UserRepository {

    private final UserApi userApi;          // Retrofit 接口
    private final UserDao userDao;          // Room DAO

    /**
     * 获取用户信息（缓存优先 + 网络更新）
     */
    public Observable<User> getUser(long userId) {
        return Observable.concatArrayEager(
            // ① 先从数据库获取缓存（快速返回）
            userDao.getUserById(userId)
                .subscribeOn(Schedulers.io())
                .doOnNext(user -> Log.d("Repo", "命中缓存: " + user.getName())),

            // ② 从网络获取最新数据
            userApi.getUser(userId)
                .subscribeOn(Schedulers.io())
                .doOnNext(user -> {
                    // ③ 网络数据入数据库（Room 事务）
                    userDao.insertUser(user);
                    Log.d("Repo", "网络更新: " + user.getName());
                })
                .onErrorResumeNext(Observable.empty()) // 网络失败不崩溃
        )
        .distinctUntilChanged()  // 数据没变化不刷新 UI
        .observeOn(AndroidSchedulers.mainThread());
    }

    /**
     * 搜索防抖（debounce）+ 去重（distinct）
     */
    public Observable<List<User>> searchUsers(Observable<String> queryObservable) {
        return queryObservable
            .debounce(300, TimeUnit.MILLISECONDS)    // 300ms 防抖
            .distinctUntilChanged()                    // 搜索词不变不请求
            .filter(query -> query.length() >= 2)      // 至少 2 个字符才搜索
            .switchMap(query ->                        // ★ 关键：switchMap 自动取消上次请求
                userApi.searchUsers(query)
                    .subscribeOn(Schedulers.io())
                    .onErrorReturn(throwable -> Collections.emptyList())
            )
            .observeOn(AndroidSchedulers.mainThread());
    }

    /**
     * 多数据源合并：同时请求两个接口，合并结果
     */
    public Observable<UserProfile> getUserProfile(long userId) {
        return Observable.zip(
            userApi.getUserBaseInfo(userId).subscribeOn(Schedulers.io()),
            userApi.getUserExtInfo(userId).subscribeOn(Schedulers.io()),
            (baseInfo, extInfo) -> new UserProfile(baseInfo, extInfo)
        )
        .timeout(10, TimeUnit.SECONDS)  // 超时保护
        .observeOn(AndroidSchedulers.mainThread())
        .doOnError(throwable -> Log.e("Repo", "获取用户资料失败", throwable));
    }
}
```

**在 ViewModel / Presenter 中的使用：**

```java
public class UserViewModel extends ViewModel {
    private final UserRepository repository;
    private final CompositeDisposable disposables = new CompositeDisposable();
    private final MutableLiveData<User> userLiveData = new MutableLiveData<>();

    public void loadUser(long userId) {
        disposables.add(
            repository.getUser(userId)
                .doOnSubscribe(d -> loadingLiveData.setValue(true))
                .doFinally(() -> loadingLiveData.setValue(false))
                .subscribe(
                    user -> userLiveData.setValue(user),
                    throwable -> errorLiveData.setValue(throwable.getMessage())
                )
        );
    }

    @Override
    protected void onCleared() {
        disposables.clear();  // ★ 必须清理，防止内存泄漏
    }
}
```

### 6.2 实战技巧总结

| 技巧 | 实现方式 | 说明 |
|------|----------|------|
| **防抖输入** | `debounce()` + `switchMap()` | switchMap 自动取消旧请求，防抖+去重是搜索标配 |
| **轮询** | `interval()` + `switchMap()` | 定时轮询服务器，新轮询自动取消旧请求 |
| **多请求合并** | `zip()` / `combineLatest()` | zip 等所有请求完成才合并，combineLatest 任一更新即合并 |
| **错误重试** | `retry(n)` / `retryWhen()` | retry(n) 固定次数重试，retryWhen 可实现指数退避 |
| **缓存策略** | `concatArrayEager()` | 先缓存后网络，并行订阅但保证缓存先到达 |
| **生命周期绑定** | `RxLifecycle` / `AutoDispose` | 不推荐但可理解，推荐用 `CompositeDisposable` 手动管理 |

---

## 附录：RxJava 版本对照

| 特性 | RxJava 1.x | RxJava 2.x | RxJava 3.x |
|------|:---:|:---:|:---:|
| 背压 | ❌（Observable 无背压） | ✅ Flowable | ✅ Flowable |
| null 安全 | 允许 null | ❌ 禁止 null | ❌ 禁止 null |
| 函数式接口 | Action1, Func1 | Action, Function | Action, Function |
| 包名 | `rx.*` | `io.reactivex.*` | `io.reactivex.rxjava3.*` |
| Maybe 类型 | ❌ | ✅ | ✅ |
| Java 版本 | Java 6 | Java 6+ | Java 8+ |

> **面试建议：** 大部分公司目前仍以 RxJava 2.x 为主，但核心设计思想（观察者模式、操作符链、背压）三版一脉相承，掌握 2.x 即可覆盖全部考点。

---

## 总结

RxJava 的核心竞争力在于**用同步的代码写法处理异步的数据流**。面试备战牢记三条主线：

1. **操作符链 = Decorator 装饰器链**：订阅自下而上，数据自上而下；
2. **线程切换 = subscribeOn（上游订阅线程）+ observeOn（下游观察线程）**；
3. **背压 = Flowable + BackpressureStrategy**，核心是下游 request(n) 告知上游消费能力的"握手协议"。

把这三条线讲清楚，再加上 Retrofit + Room 的实战封装经验，RxJava 面试基本可以应对自如。
