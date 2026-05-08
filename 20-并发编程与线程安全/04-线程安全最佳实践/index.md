# 线程安全最佳实践面试题集

> 面向Android中高级开发者的线程安全知识体系，涵盖不可变对象、线程封闭、同步容器与并发容器对比、ConcurrentHashMap底层原理、CopyOnWriteArrayList等核心考点。

---

## 一、面试层：高频面试题精选（7题）

### 1. 不可变对象（Immutable）的设计原则和final关键字

**不可变对象（Immutable Object）** 是指对象一旦被创建后，其状态（字段值）在整个生命周期内不能改变。这是实现线程安全最彻底的方式——无需任何同步机制。

**设计原则（五要素）：**

| 原则 | 说明 | 示例 |
|------|------|------|
| **类声明为final** | 防止子类继承后改变行为 | `public final class Money` |
| **所有字段private final** | 字段私有且初始化后不可变 | `private final BigDecimal amount;` |
| **不提供setter** | 杜绝外部修改入口 | 只暴露getter |
| **防御性拷贝入参** | 构造时拷贝可变参数，防止外部持有引用后修改 | `this.list = new ArrayList<>(list);` |
| **防御性拷贝出参** | getter返回拷贝，防止内部引用泄漏被外部修改 | `return new ArrayList<>(this.list);` |

**经典不可变类案例：**

```java
public final class Money {
    private final String currency;
    private final BigDecimal amount;

    public Money(String currency, BigDecimal amount) {
        this.currency = currency;
        // 防御性拷贝：BigDecimal本身是不可变的，但为防止子类问题仍建议拷贝
        this.amount = new BigDecimal(amount.toString());
    }

    public String getCurrency() { return currency; }
    public BigDecimal getAmount() { return new BigDecimal(amount.toString()); }

    // 所有修改操作返回新对象（函数式风格）
    public Money add(Money other) {
        if (!this.currency.equals(other.currency))
            throw new IllegalArgumentException("Currency mismatch");
        return new Money(this.currency, this.amount.add(other.amount));
    }
}
```

**final关键字的多维度含义：**

| 使用位置 | 含义 | 线程安全保证 |
|----------|------|-------------|
| `final class` | 类不可被继承 | 防止子类破坏不可变性 |
| `final 方法` | 方法不可被重写 | 配合类不可变设计 |
| `final 变量`（基本类型） | 值不可改变 | 编译器保证 |
| `final 变量`（引用类型） | 引用不可改变，**对象内容可改变** | 引用对其它线程可见（JMM保证），但对象内部仍需同步 |
| `final` + 构造函数安全发布 | 构造完成后的final字段对所有线程可见 | JMM规定：构造函数中对final字段的写入与对象的引用赋值给其他线程之间没有重排序 |

**面试追问：final字段的JMM内存语义是什么？**

JSR-133规定：在构造函数中对final字段的写入happens-before于通过该引用访问该final字段的任意线程。具体实现上，编译器会在构造函数return之前插入StoreStore屏障（JDK5+），确保final字段的写入不被重排到构造函数之外，防止其他线程看到"半初始化"的final字段。

**Android中的应用场景：**
- `Intent` 的 `Extras` 传递：跨组件传递的数据应尽量不可变
- `LiveData` 的数据类：不可变数据避免界面展示过程中数据被暗中修改
- Compose中的 `State`：不可变数据是Compose重组优化的基础
- Kotlin `data class` + `val`：天然支持不可变设计

---

### 2. 线程封闭（ThreadLocal）的原理和内存泄漏风险

**线程封闭（Thread Confinement）** 是指将数据限制在单个线程内，不与其他线程共享——这是除不可变对象外第二安全的并发策略。

**ThreadLocal原理：**

每个`Thread`对象内部维护一个`ThreadLocal.ThreadLocalMap`成员变量：

```java
// Thread.java 源码（简化）
public class Thread {
    ThreadLocal.ThreadLocalMap threadLocals;  // 存储该线程所有ThreadLocal变量的值
}

// ThreadLocal.java 源码（简化）
public class ThreadLocal<T> {
    public T get() {
        Thread t = Thread.currentThread();
        ThreadLocalMap map = getMap(t);       // 获取当前线程的ThreadLocalMap
        if (map != null) {
            ThreadLocalMap.Entry e = map.getEntry(this); // this作为Key
            if (e != null) return (T) e.value;
        }
        return setInitialValue();
    }

    public void set(T value) {
        Thread t = Thread.currentThread();
        ThreadLocalMap map = getMap(t);
        if (map != null) map.set(this, value);
        else createMap(t, value);
    }
}
```

**内存泄漏风险分析：**

这是ThreadLocal面试中最容易被深挖的点：

```
Thread → ThreadLocalMap → Entry[] → Entry(WeakReference<ThreadLocal>, value)
                                         ↑                             ↑
                                    Key是弱引用                    Value是强引用
```

| 场景 | Key（ThreadLocal对象） | Value（存储的值） | 结果 |
|------|----------------------|-------------------|------|
| **ThreadLocal对象外部引用仍在** | 强可达 | 强可达 | 正常，无泄漏 |
| **ThreadLocal对象外部引用置null** | 弱可达→GC回收→Key=null | **强可达**（Entry持有强引用） | **Key为null的Entry无法被访问到，但Value不会被GC** |
| **线程存活且ThreadLocalMap未被清理** | Key=null | 强可达 | **内存泄漏！** Value被Entry强引用，但Entry无法通过正常API访问 |
| **线程终止** | Key=null | 线程终止后Thread对象被GC | ThreadLocalMap随Thread被回收，无泄漏 |

**结论：** 在线程池场景下（线程长期存活），如果ThreadLocal对象的外部强引用被置null，而该线程一直存活，则存储的Value会一直驻留在内存中无法被回收——因为Entry对Value是强引用，而Key（弱引用）已被GC回收。

**ThreadLocal的设计对策——探测式清理（expungeStaleEntry）：**

`get()`、`set()`、`remove()`操作时，会顺便扫描并清除Key为null的脏Entry：

```java
// ThreadLocal.ThreadLocalMap.expungeStaleEntry() 简化逻辑
private int expungeStaleEntry(int staleSlot) {
    Entry[] tab = table;
    int len = tab.length;

    // 1. 清除当前过期槽位
    tab[staleSlot].value = null;   // 断开Value引用
    tab[staleSlot] = null;         // 断开Entry引用
    size--;

    // 2. Rehash后续槽位，直到遇到null
    Entry e;
    int i;
    for (i = nextIndex(staleSlot, len);
         (e = tab[i]) != null;
         i = nextIndex(i, len)) {
        ThreadLocal<?> k = e.get();
        if (k == null) {            // 发现另一个过期Entry
            e.value = null;
            tab[i] = null;
            size--;
        } else {
            // 重新计算哈希位置，如果不在原槽位则移到正确位置（线性探测+开放地址法）
            int h = k.threadLocalHashCode & (len - 1);
            if (h != i) {
                tab[i] = null;
                while (tab[h] != null)
                    h = nextIndex(h, len);
                tab[h] = e;
            }
        }
    }
    return i;
}
```

**面试必答：如何避免ThreadLocal内存泄漏？**

1. **每次使用后必须调用`remove()`**（最重要）：尤其是在线程池场景下
2. **try-finally保证remove()执行**：
   ```java
   ThreadLocal<Context> local = new ThreadLocal<>();
   try {
       local.set(context);
       // 业务逻辑
   } finally {
       local.remove();  // 保证清理
   }
   ```
3. **使用静态ThreadLocal**：避免ThreadLocal对象本身被GC（Key不失效则不会泄漏）
4. **在线程池的afterExecute钩子中清理**：ThreadPoolExecutor可以重写`afterExecute()`统一清理

**Android中的ThreadLocal应用：**
- `Looper`：每个线程只能有一个Looper，通过`ThreadLocal<Looper>`存储（`Looper.prepare()` → `sThreadLocal.set(new Looper())`）
- `Choreographer`：帧回调通过ThreadLocal实现线程绑定
- EventBus的`ThreadLocal<PendingPost>`：复用PendingPost对象池避免GC

---

### 3. ConcurrentHashMap：JDK7分段锁 vs JDK8 CAS+synchronized

这是并发面试中几乎必问的"版本演进"对比题，考察对并发思想迭代的深度理解。

| 对比维度 | JDK 7 ConcurrentHashMap | JDK 8 ConcurrentHashMap |
|----------|------------------------|------------------------|
| **数据结构** | Segment[] + HashEntry[]（二次哈希） | Node[] + 链表/红黑树（与HashMap结构一致） |
| **锁粒度** | **分段锁**：默认16个Segment，每个Segment独立加锁 | **槽位锁**：对单个桶（bin）的头节点加synchronized（更细粒度） |
| **并发度** | 默认16（构造函数参数），固定不可变 | 等于数组长度（n个桶即n级并发，实际受CPU核数限制） |
| **查找操作** | `get()`不加锁（volatile保证可见性） | `get()`不加锁（Node.val/Node.next用volatile） |
| **写入操作** | Segment.lock()，同一Segment内串行 | CAS尝试写入空桶 + synchronized锁桶头节点 |
| **size()** | 三次不加锁计算+失败后锁所有Segment重试 | 使用`CounterCell`数组（类似LongAdder）分片累加，高并发下更高效 |
| **迭代器** | 弱一致性（不抛出ConcurrentModificationException） | 弱一致性，支持并发修改 |
| **扩容** | Segment内部独立扩容（与HashMap逻辑类似） | **多线程协同扩容**（transfer），每个线程负责一段槽位迁移 |
| **红黑树** | 不支持 | JDK8支持（当链表长度≥8且数组长度≥64时树化） |

**JDK7分段锁的架构图（核心理解）：**

```
ConcurrentHashMap
  │
  ├─ Segment[0]  ← ReentrantLock
  │    ├─ HashEntry → HashEntry → HashEntry (链表)
  │    └─ ...
  ├─ Segment[1]  ← ReentrantLock
  │    └─ HashEntry → ...
  ├─ ...
  └─ Segment[15] ← ReentrantLock
       └─ HashEntry → ...

put操作流程:
1. key.hashCode() 高位 → 定位Segment (hash >>> segmentShift & segmentMask)
2. Segment.tryLock() → lock() 获取Segment锁
3. key.hashCode() 低位 → 定位HashEntry桶
4. 遍历链表，更新或插入
5. 超过阈值则rehash（仅当前Segment内部rehash）
```

**JDK8 CAS+synchronized的put核心流程（简化）：**

```java
final V putVal(K key, V value, boolean onlyIfAbsent) {
    if (key == null || value == null) throw new NullPointerException();
    int hash = spread(key.hashCode());    // 扰动函数
    int binCount = 0;
    for (Node<K,V>[] tab = table;;) {     // 自旋
        Node<K,V> f; int n, i, fh;
        if (tab == null || (n = tab.length) == 0)
            tab = initTable();            // ① CAS初始化数组
        else if ((f = tabAt(tab, i = (n - 1) & hash)) == null) {
            // ② 桶为空：CAS插入（无锁）
            if (casTabAt(tab, i, null, new Node<K,V>(hash, key, value, null)))
                break;
        } else if ((fh = f.hash) == MOVED)  // ③ 检测到ForwardingNode
            tab = helpTransfer(tab, f);     //    协助扩容
        else {
            // ④ 桶非空：synchronized锁桶头节点
            V oldVal = null;
            synchronized (f) {
                if (tabAt(tab, i) == f) {   // 双重检查
                    if (fh >= 0) {           // 链表
                        // ...遍历链表，更新/插入
                    } else if (f instanceof TreeBin) { // 红黑树
                        // ...红黑树操作
                    }
                }
            }
        }
    }
    addCount(1L, binCount);               // ⑤ 计数+可能触发扩容
    return null;
}
```

**为什么JDK8从ReentrantLock换成了synchronized？**

| 原因 | 详解 |
|------|------|
| **synchronized锁升级优化（JDK6+）** | 偏向锁→轻量级锁→重量级锁的升级策略下，对于低竞争场景，synchronized性能已不输ReentrantLock |
| **内存占用更小** | 每个Segment都是独立的ReentrantLock+HashEntry[]，16个Segment的内存开销远大于直接使用Node[] |
| **更细粒度锁** | 分段锁固定16段，而桶锁的粒度等于数组长度（扩容后更多），并发度随扩容提升 |
| **代码维护性** | 实现更简洁，去掉Segment抽象层，与HashMap结构更接近 |
| **JVM优化** | synchronized由JVM直接优化（锁消除、锁粗化），ReentrantLock只是API层 |

**面试金句：** "JDK7的分段锁是空间换并发度的经典设计，但存在三个缺陷：Segment数量固定不可动态调整、内存开销大、两次哈希定位。JDK8用CAS+synchronized+ForwardingNode将扩容也变成并发的——这是思想上的质变。"

---

### 4. CopyOnWriteArrayList的写时复制和适用场景

**CopyOnWriteArrayList** 的核心思想：**读写分离**——读操作完全无锁，写操作通过创建底层数组的新副本实现。

**底层结构：**

```java
public class CopyOnWriteArrayList<E> {
    private transient volatile Object[] array;  // volatile保证多线程可见性

    final Object[] getArray() { return array; }
    final void setArray(Object[] a) { array = a; }
}
```

**add()源码分析——写时复制：**

```java
public boolean add(E e) {
    final ReentrantLock lock = this.lock;
    lock.lock();                           // ① 加锁（保证同时只有一个写操作）
    try {
        Object[] elements = getArray();
        int len = elements.length;
        Object[] newElements = Arrays.copyOf(elements, len + 1); // ② 复制数组（+1）
        newElements[len] = e;              // ③ 新元素放到副本末尾
        setArray(newElements);             // ④ volatile写，原子替换引用
        return true;
    } finally {
        lock.unlock();
    }
}
```

**get()——完全无锁读：**

```java
public E get(int index) {
    return elementAt(getArray(), index);   // 直接读当前array快照，无锁
}
```

**特性总结：**

| 特性 | 说明 |
|------|------|
| **读无锁** | get()直接读取array引用，不需要任何锁，性能极高 |
| **写加锁** | add/set/remove使用ReentrantLock保证串行写入 |
| **写时复制** | 每次写入都创建整个数组的副本（Arrays.copyOf） |
| **弱一致性** | 迭代器(COWIterator)持有创建时的数组快照，后续修改对迭代器不可见 |
| **内存开销大** | 每次写操作需要完整复制数组，如果在数组较大时频繁写入会频繁GC |

**适用场景（3个关键词）：读多写少 + 数据量小 + 弱一致性容忍**

| ✅ 适用场景 | ❌ 不适用场景 |
|-------------|--------------|
| 黑名单/白名单缓存（启动时加载，运行时极少修改） | 高频写操作（如每秒数百次add） |
| 监听器列表（很少增删监听器，频繁遍历通知） | 大数组（数万元素每次复制代价巨大） |
| 配置信息集合（启动加载，偶尔修改） | 需要强一致性的场景（读要看到最新写入） |
| 事件订阅者列表 | 实时交易订单队列 |

**ArrayList线程安全化的三种方案对比：**

| 方案 | 实现 | 读性能 | 写性能 | 适用 |
|------|------|--------|--------|------|
| `Collections.synchronizedList` | 所有方法synchronized包裹 | 差（竞争锁） | 差 | 读写均衡+能接受低性能 |
| `CopyOnWriteArrayList` | 写时复制+读无锁 | 极好 | 差（复制全数组） | 读多写极少 |
| `Collections.unmodifiableList` + 发布前构造完毕 | 不可变 | 极好 | 不可写 | 发布后永不修改 |

**Android中的实际应用：**
- `View` 的 `OnClickListener` 注册机制（内部使用类似COW的监听器数组）
- `SharedPreferences` 的 `OnSharedPreferenceChangeListener` 集合

---

### 5. Collections.synchronizedMap vs ConcurrentHashMap

这是面试官最爱问的"对比选择"题。

| 对比维度 | Collections.synchronizedMap | ConcurrentHashMap |
|----------|----------------------------|-------------------|
| **实现方式** | `SynchronizedMap`包装类，所有方法加synchronized(mutex) | 专用并发容器，CAS+synchronized |
| **锁对象** | 全局单一mutex（或传入的map本身） | 桶级锁（多个桶可并行写入） |
| **并发级别** | **1**（整个map一把大锁） | **N**（N=数组长度，随扩容增长） |
| **get性能** | 需要获取mutex锁 | **无锁读取**（volatile保证可见性） |
| **put性能** | 排他锁，所有线程串行 | 空桶CAS无锁写入，非空桶synchronized桶头节点 |
| **迭代器** | 需要手动synchronized包裹迭代代码 | 弱一致性迭代器，不抛ConcurrentModificationException |
| **线程扩容** | 无（底层HashMap单线程扩容） | 多线程协同扩容（transfer） |
| **null键/值** | 底层Map决定（HashMap支持） | **不支持null键和null值** |
| **size()** | 精确（加锁后计算） | 近似精确（分片累加，高并发下可能有微小偏差） |
| **内存开销** | 仅mutex对象 | CounterCell[] + 红黑树节点开销 |

**关键追问：为什么ConcurrentHashMap不允许null键值？**

歧义问题：`map.get(key)` 返回null时，无法区分是"key不存在"还是"value确实是null"。在单线程环境下通过`containsKey()`可区分，但在并发环境下`get()`和`containsKey()`之间可能发生修改——如果value允许null，则无法可靠判断。Doug Lea的设计哲学是在并发容器中直接禁止null来消除这种歧义。

**代码示例——synchronizedMap的迭代陷阱：**

```java
Map<String, String> syncMap = Collections.synchronizedMap(new HashMap<>());

// ❌ 错误！迭代未加锁，可能抛出ConcurrentModificationException
for (String key : syncMap.keySet()) {
    System.out.println(syncMap.get(key));
}

// ✅ 正确：手动锁定mutex进行迭代
synchronized (syncMap) {
    for (String key : syncMap.keySet()) {
        System.out.println(syncMap.get(key));
    }
}
```

**性能实测心智模型：**

```
并发线程数         synchronizedMap      ConcurrentHashMap
    1                 ≈相同               ≈相同
    4              下降30~50%          几乎不降
    16             下降80%+            线性扩展（受CPU核数限制）
    64             基本不可用           高效运行
```

---

### 6. ConcurrentHashMap的get()为什么不需要加锁？

这道题考察的是对Java内存模型、volatile语义和底层unsafe操作的深度理解。

**核心原因：Node的val和next字段都用volatile修饰：**

```java
static class Node<K,V> implements Map.Entry<K,V> {
    final int hash;
    final K key;
    volatile V val;           // ★ volatile保证可见性
    volatile Node<K,V> next;  // ★ volatile保证可见性

    Node(int hash, K key, V val, Node<K,V> next) {
        this.hash = hash;
        this.key = key;
        this.val = val;
        this.next = next;
    }
}
```

**volatile的可见性保证链：**

1. 写线程A执行`put()`插入/更新Node时，对`val`和`next`的赋值是volatile写
2. JMM规定：volatile写happens-before于后续volatile读
3. 读线程B的`get()`通过`Unsafe.getObjectVolatile()`读取table槽位节点→此为volatile读
4. 根据happens-before传递性，B一定能看到A写入的最新值

**Unsafe.getObjectVolatile()的作用：**

```java
// ConcurrentHashMap中的tabAt()方法
static final <K,V> Node<K,V> tabAt(Node<K,V>[] tab, int i) {
    return (Node<K,V>)U.getObjectVolatile(tab, ((long)i << ASHIFT) + ABASE);
}
```

这等价于对数组元素做一次volatile读，确保获取到最新的引用——类似于C++中的`memory_order_acquire`语义。

**关键细节：扩容期间的get()**

在扩容期间读取时，如果遇到`ForwardingNode`（hash==MOVED，即-1），说明当前桶已经迁移到新数组：

```java
// ForwardingNode.find() —— 扩容中转发查找
Node<K,V> find(int h, Object k) {
    outer: for (Node<K,V>[] tab = nextTable;;) {
        // 在新数组中重新定位桶位置并查找
    }
}
```

整个过程**完全无锁**——读操作永远不会阻塞，这是ConcurrentHashMap最精妙的设计之一。

---

### 7. 线程安全的4种实现方式总结对比

| 方式 | 核心思想 | 同步开销 | 典型场景 | 代表 |
|------|---------|---------|---------|------|
| **不可变对象** | 状态不可变，天然线程安全 | 零开销 | 值对象、配置 | String, Integer, Money |
| **线程封闭** | 数据不共享，限定在单线程 | 零开销（无竞争） | 线程局部状态 | ThreadLocal, Looper |
| **互斥同步** | 锁机制保证互斥访问 | 上下文切换+阻塞 | 通用共享数据 | synchronized, ReentrantLock |
| **非阻塞同步** | CAS自旋，冲突重试 | CPU自旋开销 | 低竞争场景 | AtomicInteger, ConcurrentHashMap的get |

---

## 二、ThreadLocal的ThreadLocalMap底层结构深度解析

### ThreadLocalMap的数据结构

与HashMap不同，ThreadLocalMap使用**开放地址法**（线性探测）解决哈希冲突，而不是链表法。

```java
static class ThreadLocalMap {
    static class Entry extends WeakReference<ThreadLocal<?>> {
        Object value;                    // value是强引用！
        Entry(ThreadLocal<?> k, Object v) {
            super(k);                    // Key通过WeakReference持有（弱引用）
            value = v;
        }
    }

    private Entry[] table;               // 数组（初始容量16，2的幂）
    private int size = 0;
    private int threshold;               // 扩容阈值 = len * 2/3

    // 哈希算法：使用AtomicInteger的递增值（0x61c88647是黄金分割数的32位表示）
    private static final int HASH_INCREMENT = 0x61c88647;
}
```

### 哈希冲突解决——线性探测

```java
// 计算初始位置
int i = key.threadLocalHashCode & (len - 1);

// 如果table[i] != null 且 key != 当前key，则线性探测下一个
for (Entry e = table[i]; e != null; e = table[i = nextIndex(i, len)]) {
    ThreadLocal<?> k = e.get();
    if (k == key)      return e;        // 找到了
    if (k == null)     expungeStaleEntry(i); // 清理过期槽位
}
```

**为什么用开放地址法而非链表法？**

1. ThreadLocal的Key是弱引用，需要频繁清理过期Entry——开放地址法的连续内存更容易扫描和清理
2. ThreadLocal数量通常不会太大（每个线程通常只有几个到几十个），链表的优势不明显
3. 线性探测的缓存局部性更好

### 脏Entry清理机制（三种清理方式）

| 清理方式 | 触发时机 | 范围 | 说明 |
|----------|----------|------|------|
| **探测式清理（expungeStaleEntry）** | get/set遇到过期Entry时 | 从过期槽位到下一个null槽位之间的连续段 | 清理过期槽位并重新哈希有效槽位 |
| **启发式清理（cleanSomeSlots）** | 添加新Entry后 | 对数扫描（log₂(n)次，直到连续扫描到过期Entry的次数满足条件） | 快速扫描不脏则不清理 |
| **全量清理（rehash→expungeStaleEntries→resize）** | size >= threshold时 | 全表 | 先清理所有过期槽位，再决定扩容 |

### 扩容机制

```java
private void resize() {
    Entry[] oldTab = table;
    int oldLen = oldTab.length;
    int newLen = oldLen * 2;                // 2倍扩容
    Entry[] newTab = new Entry[newLen];
    int count = 0;

    for (int j = 0; j < oldLen; ++j) {
        Entry e = oldTab[j];
        if (e != null) {
            ThreadLocal<?> k = e.get();
            if (k == null) {
                e.value = null;             // 明确释放
            } else {
                int h = k.threadLocalHashCode & (newLen - 1);
                while (newTab[h] != null)
                    h = nextIndex(h, newLen);
                newTab[h] = e;
                count++;
            }
        }
    }
    setThreshold(newLen);
    size = count;
    table = newTab;
}
```

**扩容触发条件不同于HashMap的0.75：** ThreadLocalMap的阈值是 `len * 2/3`，且扩容前会先执行全量清理（`expungeStaleEntries`）——如果清理后size仍≥threshold的3/4才真正扩容。

---

## 三、ConcurrentHashMap的sizeCtl和扩容transfer原理

### sizeCtl的多重含义

`sizeCtl`是ConcurrentHashMap中最精妙的控制变量，它是多用途的：

```java
private transient volatile int sizeCtl;
```

| sizeCtl的值 | 含义 |
|-------------|------|
| **0** | 默认初始容量（第一次put时才初始化数组） |
| **-1** | 正在初始化数组（某个线程执行initTable） |
| **-(1 + n)** | 正在扩容，有n个线程在帮助扩容（低16位记录扩容线程数+1） |
| **> 0（初始化后）** | 下次扩容的阈值（数组长度 × 0.75） |

**解读扩容标记：** 当sizeCtl = -3时，表示有2个线程（-3 = -(1+2)）正在协同扩容。

### initTable()——CAS初始化

```java
private final Node<K,V>[] initTable() {
    Node<K,V>[] tab; int sc;
    while ((tab = table) == null || tab.length == 0) {
        if ((sc = sizeCtl) < 0)
            Thread.yield();             // 其他线程正在初始化，让出CPU
        else if (U.compareAndSwapInt(this, SIZECTL, sc, -1)) {
            // CAS将sizeCtl设为-1表示"我正在初始化"
            try {
                if ((tab = table) == null || tab.length == 0) {
                    int n = (sc > 0) ? sc : DEFAULT_CAPACITY;
                    Node<K,V>[] nt = (Node<K,V>[])new Node<?,?>[n];
                    table = tab = nt;
                    sc = n - (n >>> 2);     // n * 0.75
                }
            } finally {
                sizeCtl = sc;               // 设置为扩容阈值
            }
            break;
        }
    }
    return tab;
}
```

### 扩容触发条件

```java
// addCount()中检查扩容
private final void addCount(long x, int check) {
    // ...计数逻辑...

    // 检查是否需要扩容
    while (s >= (long)(sc = sizeCtl) && (tab = table) != null &&
           (n = tab.length) < MAXIMUM_CAPACITY) {
        // 触发扩容...
        transfer(tab, null);
    }
}
```

两个触发点：
1. **put/addCount**：链表插入后size超过阈值
2. **treeifyBin**：链表长度≥8但数组长度<64时，优先扩容而非树化

### transfer()——多线程协同扩容详解

这是ConcurrentHashMap精华中的精华：

```java
private final void transfer(Node<K,V>[] tab, Node<K,V>[] nextTab) {
    int n = tab.length, stride;
    // ① 计算每个线程负责的迁移槽位数（最小16）
    if ((stride = (NCPU > 1) ? (n >>> 3) / NCPU : n) < MIN_TRANSFER_STRIDE)
        stride = MIN_TRANSFER_STRIDE;

    // ② 初始化新数组（第一个进入transfer的线程创建）
    if (nextTab == null) {
        try {
            Node<K,V>[] nt = (Node<K,V>[])new Node<?,?>[n << 1];
            nextTab = nt;
        } catch (Throwable ex) {
            sizeCtl = Integer.MAX_VALUE;
            return;
        }
        nextTable = nextTab;
        transferIndex = n;              // 迁移起始索引（从旧数组尾部向前分配）
    }

    int nextn = nextTab.length;
    ForwardingNode<K,V> fwd = new ForwardingNode<K,V>(nextTab);

    boolean advance = true;
    boolean finishing = false;

    // ③ i = 当前线程负责的槽位索引, bound = 分配区间的下限
    for (int i = 0, bound = 0;;) {
        Node<K,V> f; int fh;
        while (advance) {
            int nextIndex, nextBound;
            if (--i >= bound || finishing)
                advance = false;
            else if ((nextIndex = transferIndex) <= 0) {
                i = -1;
                advance = false;
            }
            // CAS抢占迁移区间 [nextBound, nextIndex)
            else if (U.compareAndSwapInt(this, TRANSFERINDEX, nextIndex,
                      nextBound = (nextIndex > stride ? nextIndex - stride : 0))) {
                bound = nextBound;
                i = nextIndex - 1;
                advance = false;
            }
        }

        if (i < 0 || i >= n || i + n >= nextn) {
            int sc;
            if (finishing) {               // 全部迁移完成
                nextTable = null;
                table = nextTab;
                sizeCtl = (n << 1) - (n >>> 1);  // 新阈值 = 2n * 0.75
                return;
            }
            // 当前线程迁移完成，减少扩容线程计数
            if (U.compareAndSwapInt(this, SIZECTL, sc = sizeCtl, sc - 1)) {
                if ((sc - 2) != resizeStamp(n) << RESIZE_STAMP_SHIFT)
                    return;                // 还有其他线程在扩容，退出
                finishing = advance = true;
                i = n;
            }
        }
        else if ((f = tabAt(tab, i)) == null)
            advance = casTabAt(tab, i, null, fwd);   // 空桶直接放置ForwardingNode
        else if ((fh = f.hash) == MOVED)
            advance = true;                           // 已迁移，跳过
        else {
            synchronized (f) {                        // 锁定头节点进行迁移
                if (tabAt(tab, i) == f) {
                    Node<K,V> ln, hn;                 // lowNode, highNode
                    if (fh >= 0) {                    // 链表迁移
                        int runBit = fh & n;          // 关键：利用n是2的幂的特征
                        // ... 查找最后一段相同runBit的连续节点
                        // ln链表 = runBit==0 的节点 → 新数组原位置i
                        // hn链表 = runBit==1 的节点 → 新数组位置i+n
                        setTabAt(nextTab, i, ln);
                        setTabAt(nextTab, i + n, hn);
                        setTabAt(tab, i, fwd);        // 旧桶放置ForwardingNode
                    }
                    // ... 红黑树迁移（TreeBin）
                }
            }
        }
    }
}
```

**多线程协同扩容核心机制：**

```
原数组 (n=16):
[0][1][2]...[15]
              ↑
         transferIndex = 16

线程A CAS抢占: transferIndex 16→8, 负责槽位[8,15]
线程B CAS抢占: transferIndex 8→0,  负责槽位[0,7]
线程C CAS抢占: transferIndex=0, 无区间分配, 退出

每个线程迁移完成后通过ForwardingNode标记：
- 其他put线程遇到ForwardingNode → 帮助扩容(helpTransfer)
- 其他get线程遇到ForwardingNode → 在新数组中查找(无锁)
```

**链表迁移的精妙算法——高低位分割：**

由于n是2的幂，`hash & n`的结果只有0或1：
- `hash & n == 0`：该节点在新数组的位置 **不变**（i位置）→ lowNode链表
- `hash & n == 1`：该节点在新数组的位置为 **i+n** → highNode链表

这个算法将原链表完美切分为两个子链表，无需重新计算每个节点的位置，时间复杂度O(L)。

**迁移完成后的收尾：**

当最后一个线程完成迁移时（CAS减小sizeCtl后发现自己倒数第二个完成的线程已经执行了最后检查），将新数组赋值给table，sizeCtl恢复为新阈值。

---

## 四、同步容器 vs 并发容器的选型决策流程图

### 决策流程图

```
需要线程安全的容器？
        │
  ┌─────┴─────┐
  │   YES     │    NO → 普通容器即可
  └─────┬─────┘
        │
  操作特征是？
        │
  ┌─────┼─────────────────┐
  │     │                 │
读多写极少          读写均衡            写多读少
  │     │                 │
CopyOnWrite      并发容器             互斥/锁分段
ArrayList/Set    ConcurrentHashMap    synchronized+普通容器
                 ConcurrentLinkedQueue
                 ConcurrentSkipListMap
        │                │                  │
   ┌────┴────┐      ┌────┴────┐       ┌────┴────┐
   │         │      │         │       │         │
需要排序？  K-V？  需要排序？  K-V？  需要排序？  K-V？
   │         │      │         │       │         │
Concurrent- CHM    Concurrent- CHM    TreeMap+  HashMap+
SkipList            SkipList           锁        锁
Set/Map             Map
```

### 各场景最佳选择速查表

| 场景 | 推荐容器 | 备选 | 理由 |
|------|---------|------|------|
| **高并发K-V缓存** | ConcurrentHashMap | - | 桶级锁+无锁读，最佳并发性能 |
| **监听器/观察者列表** | CopyOnWriteArrayList | - | 遍历远多于修改 |
| **配置集合** | CopyOnWriteArraySet | ConcurrentHashMap.newKeySet() | 读多写极少 |
| **并发队列（生产者-消费者）** | ConcurrentLinkedQueue(无界) | LinkedBlockingQueue(有界) | 无锁CAS实现 |
| **并发双端队列** | ConcurrentLinkedDeque | LinkedBlockingDeque | ForkJoinPool工作窃取 |
| **高并发有序Map** | ConcurrentSkipListMap | - | 跳表实现，并发排序 |
| **写密集Map** | synchronized + HashMap | ConcurrentHashMap | 写远多于读时CHM优势降低 |
| **需要批量操作的Map** | synchronized + HashMap | ConcurrentHashMap | CHM不支持跨多个put的原子操作 |
| **需要Null键值** | synchronized + HashMap | - | CHM禁止null |
| **Android内存敏感场景** | ArrayMap + synchronized | ConcurrentHashMap | ArrayMap比HashMap省内存 |
| **大量小集合** | 不可变集合 + 安全发布 | - | 零同步开销 |

### 复合操作陷阱

ConcurrentHashMap的单个方法是原子的，但复合操作不是：

```java
// ❌ 竞态条件——非原子复合操作
if (map.containsKey(key)) {
    map.put(key, map.get(key) + 1);  // 两个原子操作之间状态可能改变
}

// ✅ 使用原子复合方法
map.compute(key, (k, v) -> v == null ? 1 : v + 1);         // JDK8+
map.merge(key, 1, Integer::sum);                            // JDK8+
// 或
LongAdder counter = map.computeIfAbsent(key, k -> new LongAdder());
counter.increment();
```

**JDK8新增的原子复合方法：**

| 方法 | 功能 | 原子性 |
|------|------|--------|
| `compute(K, BiFunction)` | 根据key计算新值 | ✅ 原子 |
| `computeIfAbsent(K, Function)` | 不存在时计算 | ✅ 原子 |
| `computeIfPresent(K, BiFunction)` | 存在时计算 | ✅ 原子 |
| `merge(K, V, BiFunction)` | 合并值 | ✅ 原子 |
| `forEach` / `search` / `reduce` | 并行遍历/搜索/归约 | 弱一致性 |

---

## 五、ConcurrentHashMap.put()完整源码走读 + 扩容transfer()

### put()的完整调用链

```
ConcurrentHashMap.put(K, V)
  └─ putVal(K, V, onlyIfAbsent=false)
       ├─ spread(key.hashCode())        // 扰动函数
       ├─ initTable()                   // ① 延迟初始化数组（CAS）
       ├─ casTabAt()                    // ② 空桶CAS插入
       ├─ helpTransfer()                // ③ 遇到ForwardingNode则协助扩容
       ├─ synchronized(f) { ... }       // ④ 锁桶头节点，遍历/树操作
       ├─ addCount()                    // ⑤ 计数 + 可能触发扩容
       │    ├─ CounterCell计数
       │    └─ transfer()               //    多线程协同扩容
       └─ return oldVal
```

### Step-by-step 源码走读

```java
public V put(K key, V value) {
    return putVal(key, value, false);  // onlyIfAbsent=false
}

final V putVal(K key, V value, boolean onlyIfAbsent) {
    // ====== 第0步：参数校验 ======
    if (key == null || value == null)
        throw new NullPointerException();

    // ====== 第1步：哈希计算 ======
    int hash = spread(key.hashCode());

    int binCount = 0;
    for (Node<K,V>[] tab = table;;) {  // ★ 自旋循环
        Node<K,V> f; int n, i, fh;

        // ====== 第2步：数组未初始化 → 初始化 ======
        if (tab == null || (n = tab.length) == 0)
            tab = initTable();          // CAS将sizeCtl设为-1，初始化后设为阈值

        // ====== 第3步：目标桶为空 → CAS插入 ======
        else if ((f = tabAt(tab, i = (n - 1) & hash)) == null) {
            if (casTabAt(tab, i, null,
                         new Node<K,V>(hash, key, value, null)))
                break;                  // ★ CAS成功，直接返回（无锁！）
        }

        // ====== 第4步：当前正在扩容 → 协助扩容 ======
        else if ((fh = f.hash) == MOVED)
            tab = helpTransfer(tab, f); // 帮助迁移后，重新在新数组中循环

        // ====== 第5步：桶非空 → synchronized锁桶 ======
        else {
            V oldVal = null;
            synchronized (f) {          // ★ 锁桶头节点
                if (tabAt(tab, i) == f) { // 双重检查：桶头未被改

                    if (fh >= 0) {      // hash>=0 → 链表
                        binCount = 1;
                        for (Node<K,V> e = f;; ++binCount) {
                            K ek;
                            // 找到相同key → 更新value
                            if (e.hash == hash &&
                                ((ek = e.key) == key ||
                                 (ek != null && key.equals(ek)))) {
                                oldVal = e.val;
                                if (!onlyIfAbsent)
                                    e.val = value;
                                break;
                            }
                            // 到尾节点 → 尾部插入
                            Node<K,V> pred = e;
                            if ((e = e.next) == null) {
                                pred.next =
                                    new Node<K,V>(hash, key, value, null);
                                break;
                            }
                        }
                    }
                    else if (f instanceof TreeBin) { // 红黑树
                        Node<K,V> p;
                        binCount = 2;
                        if ((p = ((TreeBin<K,V>)f).putTreeVal(
                                hash, key, value)) != null) {
                            oldVal = p.val;
                            if (!onlyIfAbsent)
                                p.val = value;
                        }
                    }
                }
            }

            if (binCount != 0) {
                // ====== 第6步：链表长度≥8 → 树化或扩容 ======
                if (binCount >= TREEIFY_THRESHOLD)
                    treeifyBin(tab, i);
                if (oldVal != null)
                    return oldVal;
                break;
            }
        }
    }

    // ====== 第7步：计数 + 扩容检查 ======
    addCount(1L, binCount);
    return null;
}
```

### 关键设计点深度解析

**1. spread()扰动函数：**

```java
static final int spread(int h) {
    return (h ^ (h >>> 16)) & HASH_BITS;  // 高16位与低16位异或，再去掉符号位
}
```

与HashMap的扰动函数不同，CHM去掉了高16位异或低16位后的再次位移操作，因为CHM的数组更大时对哈希分散性要求更高。

**2. treeifyBin()的双重检查：**

```java
private final void treeifyBin(Node<K,V>[] tab, int index) {
    Node<K,V> b; int n, sc;
    if (tab != null) {
        // 数组长度<64 → 优先扩容，不树化！
        if ((n = tab.length) < MIN_TREEIFY_CAPACITY)
            tryPresize(n << 1);  // 触发扩容
        else if ((b = tabAt(tab, index)) != null && b.hash >= 0) {
            synchronized (b) {
                if (tabAt(tab, index) == b) {
                    TreeNode<K,V> hd = null, tl = null;
                    // 将Node链表转换为TreeNode双向链表
                    for (Node<K,V> e = b; e != null; e = e.next) {
                        TreeNode<K,V> p =
                            new TreeNode<K,V>(e.hash, e.key, e.val, null, null);
                        if ((p.prev = tl) == null)
                            hd = p;
                        else
                            tl.next = p;
                        tl = p;
                    }
                    // 用TreeBin包装（TreeBin持有红黑树根节点）
                    setTabAt(tab, index, new TreeBin<K,V>(hd));
                }
            }
        }
    }
}
```

**3. addCount()计数剖析：**

```java
private final void addCount(long x, int check) {
    CounterCell[] as; long b, s;
    // 尝试CAS更新baseCount
    if ((as = counterCells) != null ||
        !U.compareAndSwapLong(this, BASECOUNT, b = baseCount, s = b + x)) {
        // CAS失败 → 使用CounterCell分片计数（类似LongAdder）
        CounterCell a; long v; int m;
        boolean uncontended = true;
        if (as == null || (m = as.length - 1) < 0 ||
            (a = as[ThreadLocalRandom.getProbe() & m]) == null ||
            !(uncontended =
              U.compareAndSwapLong(a, CELLVALUE, v = a.value, v + x))) {
            fullAddCount(x, uncontended);  // CounterCell初始化或扩容
            return;
        }
        if (check <= 1) return;
        s = sumCount();  // 汇总baseCount + 所有CounterCell
    }
    // 扩容检查...
}
```

**CounterCell设计思想：** 与`LongAdder`相同——将单一热点变量拆分成baseCount + CounterCell[]数组，每个线程通过探测值（probe）选择不同Cell进行CAS累加，大幅降低高并发下的CAS失败率。

---

## 六、在安卓中如何设计一个线程安全的缓存类

### 需求分析

设计一个Android应用级的内存缓存，需要满足：
- **读多写少**：图片/数据缓存以读取为主
- **LRU淘汰策略**：限制内存占用上限
- **线程安全**：多线程并发读写
- **低延迟**：读取操作不能阻塞主线程
- **防止OOM**：需要大小限制和引用管理

### 方案一：LruCache + 自定义线程安全包装

Android SDK自带的`LruCache`本身是线程安全的（内部方法有synchronized），但并发场景有限制：

```java
/**
 * 线程安全的内存缓存类
 * 基于LruCache + ConcurrentHashMap实现两级缓存
 *
 * 设计思路：
 * 1. LruCache提供LRU淘汰（synchronized，适用于大小敏感淘汰）
 * 2. ConcurrentHashMap提供高并发快速查找（无锁读）
 * 3. 两级缓存冗余存储，牺牲少量内存换取极致读性能
 */
public class ThreadSafeCache<K, V> {

    // 一级缓存：ConcurrentHashMap —— 用于快速查找（读无锁）
    // 存储"热门"数据，读操作完全无锁
    private final ConcurrentHashMap<K, V> fastCache;

    // 二级缓存：LruCache —— 用于大小敏感淘汰
    // 存储所有缓存条目，维护LRU顺序
    private final LruCache<K, V> lruCache;

    private final int maxSize;

    public ThreadSafeCache(int maxSize) {
        this.maxSize = maxSize;
        this.fastCache = new ConcurrentHashMap<>();
        this.lruCache = new LruCache<K, V>(maxSize) {
            @Override
            protected int sizeOf(K key, V value) {
                return sizeOfValue(value);  // 子类可重写
            }

            @Override
            protected void entryRemoved(boolean evicted, K key,
                                        V oldValue, V newValue) {
                // LRU淘汰时同步清除一级缓存
                if (evicted) {
                    fastCache.remove(key);
                }
            }
        };
    }

    /**
     * 读取（完全无锁路径）
     * 优先从ConcurrentHashMap读取，miss时回退到LruCache
     */
    public V get(K key) {
        // ① 无锁快路径
        V value = fastCache.get(key);
        if (value != null) return value;

        // ② 加锁慢路径（LruCache有synchronized）
        synchronized (lruCache) {
            value = lruCache.get(key);
            if (value != null) {
                // 提升到一级缓存（热数据）
                fastCache.put(key, value);
            }
        }
        return value;
    }

    /**
     * 写入
     */
    public V put(K key, V value) {
        // 先写一级缓存
        fastCache.put(key, value);
        // 再写二级缓存（LRU淘汰会触发entryRemoved清理一级缓存）
        synchronized (lruCache) {
            return lruCache.put(key, value);
        }
    }

    /**
     * 批量预加载（初始化阶段使用）
     */
    public void putAll(Map<K, V> map) {
        fastCache.putAll(map);
        synchronized (lruCache) {
            for (Map.Entry<K, V> entry : map.entrySet()) {
                lruCache.put(entry.getKey(), entry.getValue());
            }
        }
    }

    /**
     * 删除
     */
    public V remove(K key) {
        fastCache.remove(key);
        synchronized (lruCache) {
            return lruCache.remove(key);
        }
    }

    /**
     * 清空
     */
    public void evictAll() {
        fastCache.clear();
        synchronized (lruCache) {
            lruCache.evictAll();
        }
    }

    /**
     * 子类重写以计算value的大小（用于LRU计算）
     */
    protected int sizeOfValue(V value) {
        return 1;  // 默认每个条目计为1
    }

    /**
     * 获取当前缓存大小
     */
    public int size() {
        synchronized (lruCache) {
            return lruCache.size();
        }
    }

    /**
     * 获取最大缓存大小
     */
    public int maxSize() {
        synchronized (lruCache) {
            return lruCache.maxSize();
        }
    }
}
```

### 方案二：无锁化设计（极致性能——读写锁替代）

对于读多写多但仍需淘汰的场景，使用`StampedLock`或`ReadWriteLock`：

```java
/**
 * 基于ReadWriteLock的通用线程安全缓存
 * 适用场景：读写皆频繁，需要大小限制
 */
public class ReadWriteLockCache<K, V> {
    private final Map<K, CacheEntry<V>> cache;
    private final ReadWriteLock lock = new ReentrantReadWriteLock();
    private final Lock readLock = lock.readLock();
    private final Lock writeLock = lock.writeLock();
    private final int maxSize;
    private final Deque<K> accessOrder;  // 访问顺序队列（手动维护LRU）

    public ReadWriteLockCache(int maxSize) {
        this.maxSize = maxSize;
        this.cache = new HashMap<>();
        this.accessOrder = new ArrayDeque<>(maxSize);
    }

    public V get(K key) {
        readLock.lock();
        try {
            CacheEntry<V> entry = cache.get(key);
            if (entry == null) return null;
            if (entry.isExpired()) {  // 惰性过期检查
                // 升级为写锁
                readLock.unlock();
                writeLock.lock();
                try {
                    cache.remove(key);
                    accessOrder.remove(key);
                } finally {
                    writeLock.unlock();
                    readLock.lock();  // 降级回读锁
                }
                return null;
            }
            return entry.value;
        } finally {
            readLock.unlock();
        }
    }

    public void put(K key, V value, long ttlMillis) {
        writeLock.lock();
        try {
            CacheEntry<V> entry = new CacheEntry<>(
                value, System.currentTimeMillis() + ttlMillis);

            CacheEntry<V> old = cache.put(key, entry);
            if (old == null) {
                accessOrder.addLast(key);
            } else {
                accessOrder.remove(key);
                accessOrder.addLast(key);  // 刷新访问顺序
            }

            // LRU淘汰
            while (cache.size() > maxSize) {
                K eldest = accessOrder.pollFirst();
                if (eldest != null) cache.remove(eldest);
            }
        } finally {
            writeLock.unlock();
        }
    }

    private static class CacheEntry<V> {
        final V value;
        final long expireTime;

        CacheEntry(V value, long expireTime) {
            this.value = value;
            this.expireTime = expireTime;
        }

        boolean isExpired() {
            return System.currentTimeMillis() > expireTime;
        }
    }
}
```

### 方案三：Android图片缓存实战设计

```java
/**
 * 图片加载框架的线程安全缓存层设计
 * 结合内存缓存 + 活动引用追踪（防止正在使用的Bitmap被回收）
 */
public class ImageMemoryCache {
    // L1：强引用缓存（当前正在显示的图片，永不回收）
    // 使用synchronizedSet因为写操作极少（仅attach/detach时）
    private final Set<String> activeResources =
        Collections.synchronizedSet(new HashSet<>());

    // L2：LRU缓存（最近使用的图片，按内存大小淘汰）
    private final LruCache<String, Bitmap> lruCache;

    // L3：弱引用缓存（被LRU淘汰但尚未被GC的图片，可能被复活）
    // ConcurrentHashMap支持高并发get
    private final ConcurrentHashMap<String, WeakReference<Bitmap>> weakCache;

    // 锁：保护LRU与弱引用之间的转移操作
    private final Object evictionLock = new Object();

    public ImageMemoryCache(int maxMemoryBytes) {
        this.lruCache = new LruCache<String, Bitmap>(maxMemoryBytes) {
            @Override
            protected int sizeOf(String key, Bitmap bitmap) {
                return bitmap.getAllocationByteCount();  // API 19+
            }

            @Override
            protected void entryRemoved(boolean evicted, String key,
                                        Bitmap oldValue, Bitmap newValue) {
                if (evicted) {
                    // 被LRU淘汰 → 降级到弱引用缓存
                    synchronized (evictionLock) {
                        weakCache.put(key, new WeakReference<>(oldValue));
                    }
                }
            }
        };
        this.weakCache = new ConcurrentHashMap<>();
    }

    /**
     * 标记为活动资源（View正在显示该图片）
     * 调用时机：ImageView.setImageBitmap()时
     */
    public void acquire(String key) {
        activeResources.add(key);
    }

    /**
     * 释放活动标记
     * 调用时机：View onDetachedFromWindow / onDestroy
     */
    public void release(String key) {
        activeResources.remove(key);
    }

    /**
     * 获取Bitmap（三级查找链）
     */
    public Bitmap get(String key) {
        // L1: 活动资源（被View持有的不可回收资源）
        if (activeResources.contains(key)) {
            synchronized (lruCache) {
                Bitmap bitmap = lruCache.get(key);
                if (bitmap != null) return bitmap;
            }
        }

        // L2: LRU缓存
        synchronized (lruCache) {
            Bitmap bitmap = lruCache.get(key);
            if (bitmap != null) {
                // LRU.get()会自动更新访问顺序
                return bitmap;
            }
        }

        // L3: 弱引用缓存（GC幸存者复活）
        synchronized (evictionLock) {
            WeakReference<Bitmap> ref = weakCache.get(key);
            if (ref != null) {
                Bitmap bitmap = ref.get();
                if (bitmap != null) {
                    // 复活！重新放入LRU缓存
                    synchronized (lruCache) {
                        lruCache.put(key, bitmap);
                    }
                    weakCache.remove(key);
                    return bitmap;
                } else {
                    // 已被GC回收
                    weakCache.remove(key);
                }
            }
        }

        return null;  // 所有缓存层都miss
    }

    /**
     * 存入缓存
     */
    public void put(String key, Bitmap bitmap) {
        // 检查Bitmap是否已回收
        if (bitmap.isRecycled()) return;

        synchronized (lruCache) {
            Bitmap old = lruCache.put(key, bitmap);
            // 防止重复的old Bitmap残留
            if (old != null && !old.isRecycled() && !old.sameAs(bitmap)) {
                // 旧值降级到弱引用
                synchronized (evictionLock) {
                    weakCache.put(key + "@old", new WeakReference<>(old));
                }
            }
        }
    }

    /**
     * 清理所有非活动资源（内存紧张时调用）
     */
    @RequiresApi(api = Build.VERSION_CODES.KITKAT)
    public void trimMemory(int level) {
        if (level >= ComponentCallbacks2.TRIM_MEMORY_MODERATE) {
            // 清理弱引用缓存
            weakCache.clear();
        }
        if (level >= ComponentCallbacks2.TRIM_MEMORY_BACKGROUND) {
            // 清理一半LRU缓存
            synchronized (lruCache) {
                lruCache.trimToSize(lruCache.maxSize() / 2);
            }
        }
    }
}
```

### 设计原则总结

| 原则 | 说明 | 实现方式 |
|------|------|----------|
| **快路径无锁化** | 读操作走ConcurrentHashMap，避免与写操作竞争 | ConcurrentHashMap为一级查找缓存 |
| **写操作隔离** | 写操作尽量独立加锁，不影响读性能 | 分级锁：LruCache锁 + evictionLock |
| **引用分级** | 强→弱→GC的渐进淘汰，提升命中率 | 活动资源(强) → LRU(强) → WeakReference |
| **惰性淘汰** | 过期检查分散到读操作中，而非独立清理线程 | get()时惰性检查expireTime |
| **批量操作原子化** | 跨容器的操作需要一致性保证 | putAll时先写CHM再统一写LruCache |
| **泄漏防护** | 防止正在使用的资源被回收 | activeResources追踪视图持有的引用 |

---

## 附录：知识体系速查

### 线程安全实现方案的性能对比

| | 不可变对象 | ThreadLocal | synchronized | ReentrantLock | ConcurrentHashMap | CopyOnWriteArrayList |
|---|---|---|---|---|---|---|
| 读性能 | ★★★★★ | ★★★★★ | ★★★ | ★★★ | ★★★★★ | ★★★★★ |
| 写性能 | ★★★★★(新建) | ★★★★★ | ★★★ | ★★★ | ★★★★ | ★ |
| 内存效率 | ★★★ | ★★★★ | ★★★★★ | ★★★★★ | ★★★★ | ★ |
| 使用复杂度 | ★★★ | ★★★ | ★★★★★ | ★★★★ | ★★★★ | ★★★★★ |
| 可伸缩性 | ★★★★★ | ★★★★★ | ★ | ★ | ★★★★★ | ★ |

### 常见并发Bug清单

| Bug类型 | 示例 | 解决方案 |
|---------|------|----------|
| 竞态条件 | check-then-act | 使用原子复合方法 / 加锁保护整个操作 |
| 数据竞争 | 多线程读写非volatile字段 | volatile / synchronized / Atomic类 |
| 死锁 | 嵌套锁/反向加锁顺序 | 统一加锁顺序 / tryLock超时 |
| 活锁 | 线程不断重试但始终失败 | 添加随机退避 / 限制重试次数 |
| 发布逸出 | 构造函数中启动线程 | 不在构造函数中启动线程/注册监听器 |
| 内存泄漏 | ThreadLocal未remove | try-finally保证remove / 静态ThreadLocal |

---

> **面试提示：** 线程安全最佳实践的面试，不仅是背答案，更要能**结合Android场景**说明选型理由。口头禅："在这个场景下，读多写少 → CopyOnWriteArrayList；需要高并发K-V → ConcurrentHashMap；每个线程独立数据 → ThreadLocal但要防泄漏。"

*生成日期：2026-05-08*
