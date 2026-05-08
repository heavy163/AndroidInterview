# MMKV 数据存储框架 — 面试深度解析

> **面试权重**: ⭐⭐⭐⭐⭐ | **难度**: ★★★★☆ | **字数**: 约 5000 字

---

## 第一层：常见面试问题（4+ 高频考点）

### Q1: MMKV 为什么比 SharedPreferences 快？mmap 的原理是什么？

**核心答案**: MMKV 使用 **mmap（内存映射文件）** 技术，将磁盘文件直接映射到进程的虚拟地址空间，使得文件 I/O 变成内存操作；而 SharedPreferences 基于 XML，每次读写都需要完整的文件 I/O 和 XML 解析。

**mmap 原理三要素**：

1. **零拷贝路径**: 传统 read/write 需要「磁盘→内核页缓存→用户缓冲区」两次拷贝；mmap 将文件映射到用户空间后，直接操作页缓存，省去内核到用户态的拷贝。
2. **页缓存复用**: 文件被映射后，操作系统以页（通常 4KB）为单位管理缓存；MMKV 写入时直接修改映射内存，由 OS 负责脏页回写（write-back）。
3. **延迟写**: mmap 使用 `MAP_SHARED` 标志，修改会最终写回文件，但不是立即触发磁盘 I/O——OS 会在合适的时机（内存压力、fsync 调用、定时冲刷）批量刷盘。

**一句话总结**: mmap 把磁盘文件变成了一塊可以直接用指针操作的内存，读写从「系统调用 + 数据拷贝」变成「内存访问 + OS 异步刷盘」。

---

### Q2: MMKV 如何实现多进程安全？用的是文件锁还是信号量？

**核心答案**: MMKV 使用 **文件锁（flock）** 实现多进程同步，而不是信号量或互斥锁。

**为什么不用信号量？**
- 信号量是内核持久对象，进程崩溃后需要手动清理，否则可能死锁。
- 文件锁绑定在文件描述符上，进程退出时自动释放，天然具备崩溃安全性。

**MMKV 的锁策略**：
1. **读锁（共享锁，LOCK_SH）**: 读操作获取共享锁，允许多个进程同时读取。
2. **写锁（排他锁，LOCK_EX）**: 写操作获取排他锁，阻塞所有其他读写。
3. **锁粒度**: 每个 MMKV 实例对应一个独立的锁文件（`xxx.mmkv.crc` 的 sibling 锁），不同 MMKV 实例之间不互斥。

**注意点**: `flock` 是劝告锁（advisory lock），不是强制锁——这意味着所有协作进程都必须遵守加锁协议。MMKV 在所有读写路径上都显式请求锁。

---

### Q3: Protobuf 编码相比 XML/JSON 的优势？

**核心答案**: MMKV 使用 Google 的 **Protocol Buffers** 作为序列化协议，对比 XML/JSON 在三个方面有质的提升：

| 对比维度 | MMKV (Protobuf) | SharedPreferences (XML) | DataStore (Protobuf) |
|---------|----------------|------------------------|----------------------|
| 编码方式 | 二进制 Varint | 文本 XML | 二进制 Protobuf |
| 存储格式 | 全量 KV 映射 | 单个 XML 文件 | 单个 .pb 文件 |
| 增量更新 | ✅ offset 定位直接覆盖 | ❌ 全量重写 XML | ❌ 全量写入 |
| 多进程 | ✅ 文件锁 | ❌ 不安全 | ❌ 不支持 |
| 主线程阻塞 | 极低（内存操作） | 高（I/O + XML 解析） | 低（协程异步） |

**Protobuf 三大优势**：

1. **Varint 变长编码**: 小整数只占 1 字节，XML 中 `<int>1</int>` 占 10 字节，空间节省 90% 以上。
2. **无 Schema 解析开销**: Protobuf 是 TLV（Tag-Length-Value）格式，解析时跳过未知字段，不需要像 XML 那样构建 DOM 树。
3. **增量更新能力**: MMKV 用 Protobuf 编码每条 KV 记录，记录之间用 offset 分隔，更新某条记录可以「原地覆盖」，不需要重写整个文件——这是 SP 永远做不到的。

---

### Q4: MMKV vs SharedPreferences vs DataStore 的选型决策？

**核心答案**:

| 场景 | 推荐方案 | 原因 |
|------|---------|------|
| 高频写入（埋点、实时状态） | **MMKV** | 内存级写入速度，支持增量更新 |
| 多进程数据共享 | **MMKV** | 唯一支持多进程安全的 KV 方案 |
| 简单配置（主题、语言） | **Jetpack DataStore** | 协程异步 + 类型安全 + Flow 响应式 |
| 老项目维护 | SharedPreferences | 避免引入新依赖风险 |
| 大量键值对（>500） | **MMKV** | 不受 XML 全量加载性能影响 |

**选型铁律**：
- 需要多进程 → 只有 MMKV
- 需要响应式（Flow/协程） → DataStore
- 追求极致性能 → MMKV
- 简单配置项 → DataStore（不再推荐 SP）

---

### Q5（补充）: MMKV 的内存映射会带来什么问题？

1. **虚拟地址空间占用**: 32 位进程只有 4GB 地址空间，映射大文件可能导致地址空间不足。Android 64 位无此问题。
2. **SIGBUS 错误**: 如果文件被外部截断，访问映射区域会触发 SIGBUS 信号——MMKV 在每个操作前检查映射合法性。
3. **文件大小限制**: mmap 映射大小必须 ≤ 文件大小；MMKV 在写入前先 `ftruncate` 扩容，再 `mmap` 重新映射。

---

## 第二层：mmap 的页缓存与写回策略（深度原理）

### 页缓存（Page Cache）本质

Linux 内核为每个打开的文件维护一套 **radix tree** 结构的页缓存：

```
文件偏移 → 物理页框
  0~4KB   → Page Frame A
  4~8KB   → Page Frame B
  8~12KB  → Page Frame C (脏页，等待写回)
```

当 MMKV 通过 mmap 写入数据时：
1. CPU 执行 `mov [mapped_addr], value` 指令。
2. MMU 发现对应虚拟地址的页表项存在，直接访问物理页框。
3. 该页被标记为 **脏页（Dirty Page）**。
4. **不会立即触发磁盘 I/O** —— 这是 mmap 性能的根本来源。

### 脏页写回（Writeback）触发条件

| 触发条件 | 细节 |
|---------|------|
| 定时冲刷 | 内核线程 `pdflush`（≤2.6.32）/ `flusher` 每 30 秒检查脏页 |
| 脏页比例 | 当脏页超过 `/proc/sys/vm/dirty_ratio`（默认 20%）时，进程自身执行写回 |
| 内存回收 | kswapd 回收页时，脏页先写回再回收 |
| 显式同步 | MMKV 在关键操作后调用 `msync(MS_SYNC)` 强制刷盘 |
| `munmap` | 解除映射时自动写回脏页 |

### MMKV 的同步策略

```cpp
// MMKV 源码中的同步逻辑（简化）
void MMKV::sync(bool sync) {
    if (sync) {
        msync(m_ptr, m_size, MS_SYNC);  // 同步刷盘，阻塞直到完成
    } else {
        msync(m_ptr, m_size, MS_ASYNC); // 异步刷盘，立即返回
    }
}

// Android 进程被杀前的最后防线
void MMKV::onExit() {
    msync(m_ptr, m_size, MS_SYNC);  // 确保数据不丢失
}
```

**关键面试点**: MMKV 默认使用 `MS_ASYNC`，数据安全性依赖 OS 的脏页写回机制。对于关键数据（如支付状态），需要主动调用 `sync()` 或使用 `MS_SYNC`。

---

## 第三层：Protobuf 的 Varint 编码（深度原理）

### Varint 编码规则

Varint（Variable-length Integer）用一个或多个字节表示整数，每个字节的最高位（MSB）是「继续位」：

- **MSB = 1**: 表示后面还有字节。
- **MSB = 0**: 表示这是最后一个字节。
- 其余 7 位存储实际数据，**小端序（低位在前）**。

### 编码示例

```
数值 1:
  二进制: 0000 0001
  Varint: 0000 0001  (1 字节，MSB=0 表示结束)

数值 300:
  二进制: 1 0010 1100
  Varint: 1010 1100  0000 0010
           ^ MSB=1    ^ MSB=0
           低 7 位    高 7 位
  解码: (000 0010 << 7) | 010 1100 = 256 + 44 = 300

数值 -1 (sint32 采用 ZigZag 编码):
  ZigZag: (n << 1) ^ (n >> 31) = (-1 << 1) ^ (-1 >> 31)
        = (-2) ^ (-1) = 1
  Varint: 0000 0001  (1 字节)
```

### 为什么 MMKV 选择 Protobuf？

1. **紧凑性**: `int32` 值在 [0, 127] 范围只需 1 字节；XML 中 `<int name="key" value="1" />` 至少 25 字节。
2. **自描述性**: TLV 结构中 Tag 字段标识了数据类型和字段编号，解码器无需外部 Schema 也能解析。
3. **向前兼容**: 新增字段只需分配新 Tag 编号，旧版本解码器自动跳过未知 Tag。
4. **增量更新**: MMKV 在文件中为每条记录保留空间（写入时预分配），后续更新可直接覆盖，无需重写整个文件。

### MMKV 的增量更新机制

```
MMKV 文件结构:
[总长度(4B)] [记录1] [记录2] ... [记录N] [CRC校验(4B)]

每条记录 = [Key (Protobuf编码)] [Value (Protobuf编码)]

增量更新流程:
1. 查询 offset → 定位到记录位置
2. 新值编码后长度 ≤ 旧值长度 → 原地覆盖，剩余空间填充 0
3. 新值编码后长度 > 旧值长度 → 标记旧记录为无效，追加到文件末尾
4. 无效空间超过阈值 → 触发 compact（全量整理）
```

**面试亮点**: 这种 append-only + 原地覆盖 的混合策略，既保证了写入性能，又避免了 SP 的全量重写开销。

---

## 第四层：MMKV 读写流程图

### 初始化流程

```
┌──────────┐    ┌───────────┐    ┌──────────┐    ┌──────────┐
│  用户调用  │───▶│  open()   │───▶│  flock   │───▶│  mmap()  │
│ MMKV.mmkv │    │  打开文件  │    │ 获取文件锁│    │ 内存映射 │
│  WithID() │    │           │    │          │    │          │
└──────────┘    └───────────┘    └──────────┘    └──────────┘
                                                        │
                                                        ▼
                                                ┌──────────────┐
                                                │ 校验 CRC/长度 │
                                                │ 加载已有数据   │
                                                └──────────────┘
```

### 写入流程

```
┌─────────┐    ┌───────────┐    ┌───────────┐    ┌──────────────┐
│  putX()  │───▶│ 编码 KV   │───▶│ 获取写锁  │───▶│ 计算新值长度  │
│ 调用入口  │    │ (Protobuf)│    │ (LOCK_EX) │    │              │
└─────────┘    └───────────┘    └───────────┘    └──────┬───────┘
                                                        │
                            ┌───────────────────────────┼────────────┐
                            ▼                           ▼            │
                    ┌──────────────┐           ┌──────────────┐      │
                    │ 新值 ≤ 旧值?   │           │ 新值 > 旧值?   │      │
                    └──────┬───────┘           └──────┬───────┘      │
                           ▼ YES                      ▼ YES          │
                    ┌──────────────┐           ┌──────────────┐      │
                    │ 原地覆盖+补零  │           │ 追加到文件末尾 │      │
                    └──────┬───────┘           └──────┬───────┘      │
                           │                          │              │
                           └──────────┬───────────────┘              │
                                      ▼                              │
                              ┌──────────────┐                       │
                              │ 更新 CRC      │◀──────────────────────┘
                              └──────┬───────┘
                                     ▼
                              ┌──────────────┐
                              │ 释放写锁      │
                              │ (LOCK_UN)    │
                              └──────┬───────┘
                                     ▼
                              ┌──────────────┐
                              │ msync 刷盘   │
                              │ (ASYNC)      │
                              └──────────────┘
```

### 读取流程

```
┌─────────┐    ┌───────────┐    ┌───────────┐    ┌──────────────┐
│  getX()  │───▶│ 获取读锁   │───▶│ 查HashMap  │───▶│ 命中?        │
│          │    │ (LOCK_SH) │    │ 获取offset │    │              │
└─────────┘    └───────────┘    └───────────┘    └──┬───┬───────┘
                                                     │   │
                                               YES ◀─┘   └─▶ NO
                                                │            │
                                                ▼            ▼
                                        ┌──────────┐  ┌──────────┐
                                        │ 从mmap   │  │ 返回默认 │
                                        │ 内存读取  │  │ 值/null  │
                                        └────┬─────┘  └──────────┘
                                             │
                                             ▼
                                        ┌──────────┐
                                        │ Protobuf │
                                        │ 解码     │
                                        └────┬─────┘
                                             │
                                             ▼
                                        ┌──────────┐
                                        │ 返回结果  │
                                        └──────────┘
```

**面试要点**: 读操作不需要刷盘，不需要解码整个文件，只需要从 `HashMap<Key, Offset>` 定位到具体位置，从 mmap 内存中直接截取对应字节段进行 Protobuf 解码。整个过程只有「加读锁 → 查 HashMap → 内存读取 → 解码」，所以读速度极快。

---

## 第五层：核心源码分析 — MMKV 替代 SP 的迁移方案

### 方案一：非侵入式代理（推荐）

```kotlin
/**
 * MMKV 代理 SharedPreferences — 零业务代码改动
 */
class MMKVSharedPreferences(
    private val mmkv: MMKV
) : SharedPreferences {

    override fun getAll(): MutableMap<String, *> {
        return mmkv.allKeys().associateWith { key ->
            getAny(key) ?: ""
        }.toMutableMap()
    }

    override fun getString(key: String, defValue: String?): String? {
        return mmkv.decodeString(key, defValue)
    }

    override fun getInt(key: String, defValue: Int): Int {
        return mmkv.decodeInt(key, defValue)
    }

    override fun getBoolean(key: String, defValue: Boolean): Boolean {
        return mmkv.decodeBool(key, defValue)
    }

    override fun getLong(key: String, defValue: Long): Long {
        return mmkv.decodeLong(key, defValue)
    }

    override fun getFloat(key: String, defValue: Float): Float {
        return mmkv.decodeFloat(key, defValue)
    }

    override fun getStringSet(key: String, defValues: MutableSet<String>?): MutableSet<String> {
        return mmkv.decodeStringSet(key, defValues) ?: mutableSetOf()
    }

    override fun contains(key: String): Boolean = mmkv.containsKey(key)

    override fun edit(): SharedPreferences.Editor = MMKVEditor(mmkv)

    override fun registerOnSharedPreferenceChangeListener(listener: OnSharedPreferenceChangeListener?) {
        // MMKV 原生不支持 Listener，需自行桥接
        // 可通过值拦截 + 反射通知实现
    }

    override fun unregisterOnSharedPreferenceChangeListener(listener: OnSharedPreferenceChangeListener?) {}

    inner class MMKVEditor(private val mmkv: MMKV) : SharedPreferences.Editor {
        private val pending = mutableMapOf<String, Any?>()
        private var clearFlag = false

        override fun putString(key: String, value: String?): Editor {
            pending[key] = value; return this
        }
        override fun putInt(key: String, value: Int): Editor {
            pending[key] = value; return this
        }
        override fun putBoolean(key: String, value: Boolean): Editor {
            pending[key] = value; return this
        }
        override fun putLong(key: String, value: Long): Editor {
            pending[key] = value; return this
        }
        override fun putFloat(key: String, value: Float): Editor {
            pending[key] = value; return this
        }
        override fun putStringSet(key: String, values: MutableSet<String>?): Editor {
            pending[key] = values; return this
        }
        override fun remove(key: String): Editor {
            pending[key] = null; return this
        }
        override fun clear(): Editor {
            clearFlag = true; pending.clear(); return this
        }

        override fun commit(): Boolean {
            apply()
            return true
        }

        override fun apply() {
            if (clearFlag) mmkv.clear()
            pending.forEach { (key, value) ->
                when (value) {
                    null -> mmkv.removeValueForKey(key)
                    is String -> mmkv.encode(key, value as String)
                    is Int -> mmkv.encode(key, (value as Int).toInt())
                    is Boolean -> mmkv.encode(key, value as Boolean)
                    is Long -> mmkv.encode(key, value as Long)
                    is Float -> mmkv.encode(key, value as Float)
                    is Set<*> -> mmkv.encode(key, value as Set<String>)
                }
            }
            pending.clear()
        }
    }

    // ========== 辅助方法：类型推断读取 ==========
    @Suppress("UNCHECKED_CAST")
    private fun <T> getAny(key: String): T? {
        // 尝试按类型逐个解码
        // MMKV 不保留类型信息，业务层需自行约定类型
        return null
    }
}
```

**使用方式**：

```kotlin
// 原来的代码：
// val sp = context.getSharedPreferences("config", Context.MODE_PRIVATE)
// val token = sp.getString("token", "")

// 替换为：
val sp = MMKVSharedPreferences(MMKV.mmkvWithID("config"))
val token = sp.getString("token", "")  // 接口完全兼容！
```

---

### 方案二：数据迁移脚本（有历史数据的场景）

```kotlin
object MMKVMigration {
    /**
     * 将 SP 中的所有数据迁移到 MMKV
     * @return 迁移的键值对数量
     */
    fun migrateFromSP(context: Context, spName: String, mmkvID: String): Int {
        val sp = context.getSharedPreferences(spName, Context.MODE_PRIVATE)
        val mmkv = MMKV.mmkvWithID(mmkvID)
        val allEntries = sp.all
        var count = 0

        allEntries.forEach { (key, value) ->
            when (value) {
                is String -> mmkv.encode(key, value)
                is Int -> mmkv.encode(key, value)
                is Boolean -> mmkv.encode(key, value)
                is Long -> mmkv.encode(key, value)
                is Float -> mmkv.encode(key, value)
                is Set<*> -> {
                    @Suppress("UNCHECKED_CAST")
                    mmkv.encode(key, value as Set<String>)
                }
                else -> {
                    // 不支持的原始类型，尝试 encode 为 JSON String
                    mmkv.encode(key, Gson().toJson(value))
                }
            }
            count++
        }

        // ⚠️ 迁移完成后不要立即删 SP，灰度观察一周再清理
        // context.getSharedPreferences(spName, Context.MODE_PRIVATE).edit().clear().apply()

        // 强制刷盘确保数据落盘
        mmkv.sync()
        return count
    }
}
```

---

### 方案三：逐步灰度的 ABTest 策略

```kotlin
object MMKVSwitch {
    private var useMMKV: Boolean = false

    fun init(remoteConfig: Boolean) {
        useMMKV = remoteConfig  // 由远程配置中心控制
    }

    fun getBoolean(key: String, defValue: Boolean): Boolean {
        return if (useMMKV) {
            MMKV.defaultMMKV().decodeBool(key, defValue)
        } else {
            getSp().getBoolean(key, defValue)
        }
    }

    fun putBoolean(key: String, value: Boolean) {
        if (useMMKV) {
            MMKV.defaultMMKV().encode(key, value)
        }
        // 双写策略：灰度期间两个存储都写入
        getSp().edit().putBoolean(key, value).apply()
    }

    private fun getSp() =
        App.instance.getSharedPreferences("config", Context.MODE_PRIVATE)
}
```

---

## 第六层：实际应用场景与项目经验

### 场景 1：APM 性能监控埋点数据缓存

**痛点**: 埋点 SDK 每秒产生上百条事件，SharedPreferences 写入导致 ANR。

**方案**:
```kotlin
class EventReporter {
    private val mmkv = MMKV.mmkvWithID("apm_events", MMKV.MULTI_PROCESS_MODE)

    fun report(event: Event) {
        // 先本地缓存，批量上报
        val key = "event_${System.currentTimeMillis()}"
        mmkv.encode(key, event.toByteArray())
    }

    fun batchUpload(): Int {
        val keys = mmkv.allKeys() ?: return 0
        var uploaded = 0
        keys.forEach { key ->
            val data = mmkv.decodeBytes(key) ?: return@forEach
            if (uploadToServer(data)) {
                mmkv.removeValueForKey(key)
                uploaded++
            }
        }
        return uploaded
    }
}
```

**效果**: 写入耗时从 SP 的 50~200ms 降到 <1ms，ANR 率下降 30%。

---

### 场景 2：跨进程配置同步（主进程 + WebView 进程 + Push 进程）

**痛点**: Android 多进程架构下，SP 无法保证数据一致性。

**方案**:
```kotlin
// 任何进程都能安全读写
object CrossProcessConfig {
    private val mmkv = MMKV.mmkvWithID("cross_config", MMKV.MULTI_PROCESS_MODE)

    var userId: String
        get() = mmkv.decodeString("userId", "")
        set(value) = mmkv.encode("userId", value)

    var isLogin: Boolean
        get() = mmkv.decodeBool("isLogin", false)
        set(value) = mmkv.encode("isLogin", value)

    // 复杂对象用 JSON + String 存储
    var userInfo: UserInfo?
        get() {
            val json = mmkv.decodeString("userInfo")
            return if (json.isNullOrEmpty()) null
            else Gson().fromJson(json, UserInfo::class.java)
        }
        set(value) {
            mmkv.encode("userInfo", Gson().toJson(value))
        }
}
```

**面试亮点**: MMKV 是 Android 生态中唯一「开箱即用」支持多进程的 KV 存储方案。ContentProvider 虽然也能跨进程，但实现复杂且性能差。

---

### 场景 3：App 启动优化 — 用 MMKV 做启动配置缓存

**问题**: App 冷启动时读取 ABTest 配置、Feature Flag、用户设置等信息，传统 SP 读取阻塞主线程 50~100ms。

**优化**:
```kotlin
// Application.onCreate() 中
fun initConfig() {
    val mmkv = MMKV.mmkvWithID("boot_config")
    // 读取全部启动配置，耗时 <5ms
    BootConfig.isDarkMode = mmkv.decodeBool("dark_mode", false)
    BootConfig.apiBaseUrl = mmkv.decodeString("api_base", DEFAULT_URL)!!
    BootConfig.featureFlags = mmkv.decodeStringSet("feature_flags", emptySet())!!
}
```

**效果**: 启动阶段 I/O 耗时从 80ms 降到 3ms，对低端机（Android Go）尤其明显。

---

### 场景 4：IM 消息草稿与状态缓存

**问题**: IM 应用需要实时保存消息草稿、会话列表、未读计数，高频写入场景 SP 完全无法胜任。

**方案**:
```kotlin
class IMMessageCache {
    private val draftKV = MMKV.mmkvWithID("im_draft")
    private val unreadKV = MMKV.mmkvWithID("im_unread")

    fun saveDraft(conversationId: String, text: String) {
        draftKV.encode("draft_$conversationId", text)
        // 不需要 sync() — mmap 会自动写回
    }

    fun incrementUnread(conversationId: String) {
        val current = unreadKV.decodeInt("unread_$conversationId", 0)
        unreadKV.encode("unread_$conversationId", current + 1)
    }
}
```

---

## 总结：面试答题框架

当被问到「说说你对 MMKV 的理解」时，按以下层次组织回答：

1. **一句话定义**: MMKV 是基于 mmap 的 Android KV 存储框架，由腾讯微信团队开源。
2. **核心技术**: mmap（零拷贝）+ Protobuf（紧凑编码）+ 文件锁（多进程安全）+ 增量更新（append-only）。
3. **性能优势**: 写入 ≈ 内存操作，相比 SP 快 10~100 倍；读操作查 HashMap + 内存截取，零 I/O。
4. **适用场景**: 高频写入、多进程共享、大容量 KV、需要极低延迟的场景。
5. **注意事项**: 32 位地址空间限制、SIGBUS 处理、关键数据主动 sync、Protobuf 无类型信息需自行约定。
6. **替代 SP 策略**: 非侵入式代理 → 数据迁移脚本 → 灰度 ABTest → 全量切换。

---

> **参考源码路径（微信开源）**:
> - [Tencent/MMKV](https://github.com/Tencent/MMKV)
> - 核心文件: `MMKV.cpp`, `MMKV_IO.cpp`, `MMKV_Android.cpp`, `CodedInputData.cpp`, `CodedOutputData.cpp`
