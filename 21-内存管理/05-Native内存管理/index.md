# Native 内存管理 — 面试深度解析

---

## 一、面试高频六问：Native 内存管理核心机制

### Q1: jemalloc 与 dlmalloc 的核心差异是什么？jemalloc 的 arena/bin/run 三级结构如何工作？

从 Android 5.0 开始，Android 将 Native 内存分配器从 **dlmalloc** 替换为 **jemalloc**，这是一次根本性的性能飞跃。

**dlmalloc 的局限：**

dlmalloc 是 Doug Lea 于 1987 年编写的经典分配器，采用单一全局锁 + 边界标记法（Boundary Tag）。其关键缺陷：

```
dlmalloc 单锁模型：
┌─────────────────────────────────────────┐
│              全局互斥锁                  │
│  ┌──────┐  ┌──────┐  ┌──────┐         │
│  │线程1 │  │线程2 │  │线程3 │  ...     │
│  │ 等待 │  │ 分配 │  │ 等待 │         │
│  └──────┘  └──────┘  └──────┘         │
└─────────────────────────────────────────┘
→ 多线程场景下锁竞争严重，分配/释放延迟非线性增长
→ 碎片管理依赖立即合并（immediate coalescing），频繁的边界标记遍历
```

**jemalloc 的革命性设计：**

jemalloc（Jason Evans, 2005, FreeBSD）为大规模多线程场景而生，核心是 **arena 分区 + 线程缓存 + 分级管理**：

```
jemalloc 三级结构全景：

┌─────────────────────────────────────────────────────────────────┐
│                         jemalloc                                │
│                                                                 │
│  ┌──────── arena 0 ────────┐  ┌──────── arena 1 ────────┐      │
│  │  ┌─────┐ ┌─────┐      │  │  ┌─────┐ ┌─────┐         │      │
│  │  │bin 0│ │bin 1│ ...  │  │  │bin 0│ │bin 1│  ...    │      │
│  │  │(8B) │ │(16B)│      │  │  │(8B) │ │(16B)│         │      │
│  │  └──┬──┘ └──┬──┘      │  │  └──┬──┘ └──┬──┘         │      │
│  │     │       │          │  │     │       │             │      │
│  │  ┌──┴───────┴────────┐ │  │  ┌──┴───────┴────────┐   │      │
│  │  │   runs (每个run   │ │  │  │   runs ...         │   │      │
│  │  │   管理多个同大小  │ │  │  │                    │   │      │
│  │  │   region)         │ │  │  │                    │   │      │
│  │  └───────────────────┘ │  │  └────────────────────┘   │      │
│  └────────────────────────┘  └───────────────────────────┘      │
│                                                                 │
│  ┌─────────── tcache (每线程) ───────────┐                      │
│  │  tcache_bin[0] → 8B   缓存            │                      │
│  │  tcache_bin[1] → 16B  缓存            │                      │
│  │  tcache_bin[2] → 32B  缓存            │                      │
│  │  ...                                  │                      │
│  │  tcache_bin[N] → 最大缓存             │                      │
│  └───────────────────────────────────────┘                      │
└─────────────────────────────────────────────────────────────────┘
```

**三级结构详解：**

| 层级 | 作用 | 锁粒度 | 关键特征 |
|------|------|--------|---------|
| **arena** | 独立的内存管理域 | 每个 arena 一把锁 | 通常等于 CPU 核数 × 4；线程通过哈希轮询绑定 arena |
| **bin** | 管理特定 size class 的内存 | 归属 arena 锁 | jemalloc 有 ~200 个 size class，每个 bin 管理一种 |
| **run** | 一块连续的页（page），按 size class 切分为等大 region | bin 内批量操作 | 每个 run 维护一个 bitmap 标记 region 的分配状态 |

**对比总结：**

```
                dlmalloc                    jemalloc
─────────────────────────────────────────────────────────
并发模型      全局单锁                     arena 级锁 + tcache 无锁
碎片管理      立即合并 + 边界标记          延迟合并 + 脏页清理
多线程性能    O(n) 退化                   接近线性扩展
线程缓存      无                           每线程 tcache（快速路径）
size class    粗粒度                      细粒度（~200个）
内存回收      立即归还 OS                  madvise + 惰性归还
适用场景      单线程 / 低并发              移动端 / 服务器多线程
Android 版本  ≤4.4（API 19）              ≥5.0（API 21）
```

**面试加分点：** jemalloc 的 arena 数量通过 `narenas` 控制（Android 上通常 2-8 个），线程通过 `malloc_ncpus` 取模哈希选择 arena。当 arena 内部碎片过多时，jemalloc 触发"purge"——通过 `madvise(MADV_DONTNEED)` 告知内核回收物理页，但保留虚拟地址空间以备后续分配。

---

### Q2: mmap 匿名映射与 Native 堆是什么关系？malloc 底层用了 mmap 吗？

这是面试中区分"背过"和"真懂"的关键问题。

**核心关系：**

```
Native 分配器（jemalloc/malloc）的内存来源只有两个系统调用：

┌──────────────────────────────────────────────────────────────┐
│                     sbrk() / brk()                           │
│                     ─────────────                            │
│  进程数据段增长 → [heap] 线性扩展                             │
│  优点：简单、无碎片                                           │
│  缺点：只能向高地址增长；释放后无法收缩（只能复用）              │
│  限制：Android 对 brk heap 有严格上限（~64MB 典型）            │
├──────────────────────────────────────────────────────────────┤
│                     mmap(MAP_ANONYMOUS | MAP_PRIVATE)         │
│                     ─────────────────────────────────────     │
│  任意地址映射 → 灵活分配/释放                                  │
│  优点：可独立释放(munmap)；无地址连续性限制                     │
│  缺点：每次映射至少一个页(4KB)；频繁 mmap/munmap 有开销         │
│  典型用途：大块分配(≥128KB)；arena 扩展                        │
└──────────────────────────────────────────────────────────────┘
```

**jemalloc 的实际策略：**

```
jemalloc 分配决策流程：
                     ┌─────────────┐
                     │  分配请求    │
                     └──────┬──────┘
                            ▼
                    ┌───────────────┐
                    │ tcache 命中？ │──是──→ 返回（无锁）
                    └───────┬───────┘
                            │否
                            ▼
                    ┌───────────────┐
                    │ bin 中 run    │──是──→ 从 run 分配 region
                    │ 有空闲？      │         批量填充 tcache
                    └───────┬───────┘
                            │否
                            ▼
                    ┌───────────────┐
                    │ 需要新 run？  │
                    └───────┬───────┘
                            │
              ┌─────────────┼─────────────┐
              ▼                           ▼
       ┌────────────┐            ┌────────────────┐
       │  小 run    │            │   大 run/huge   │
       │  (<2MB)    │            │   (≥2MB/≥8MB)   │
       └──────┬─────┘            └───────┬────────┘
              │                          │
              ▼                          ▼
       ┌────────────┐            ┌────────────────┐
       │ brk/sbrk   │            │ mmap 匿名映射   │
       │ (数据段)    │            │ (独立映射区)    │
       └────────────┘            └────────────────┘
```

**面试追问——为什么 Android 不能像 Linux 服务器那样无限用 brk？**

1. **Android 的 zygote 进程模型**：所有应用进程 fork 自 zygote。brk heap 在 fork 时采用 COW（Copy-On-Write），如果子进程大量使用 brk 会导致物理内存膨胀。
2. **低内存设备限制**：Android 通过 `dalvik.vm.heapgrowthlimit` 和 `dalvik.vm.heapsize` 限制 Java 堆，Native 堆虽无硬上限但受 LMK（Low Memory Killer）间接约束。
3. **64 位地址空间优势**：在 64 位 Android（≥5.0）上，mmap 的地址空间近乎无限，避免了 brk 碎片问题。

**关键命令验证：**

```bash
# 查看进程的内存映射
cat /proc/<pid>/maps
# 典型输出中你会看到：
# 12c00000-12d00000 rw-p 00000000 00:00 0          [anon:libc_malloc]  ← brk heap
# 7a1c000000-7a1c200000 rw-p 00000000 00:00 0      [anon:scudo:alloc]  ← mmap 区域
```

---

### Q3: ashmem 共享内存的原理是什么？如何实现跨进程通信？

**ashmem（Android Shared Memory）** 是 Android 独有的共享内存机制，基于 Linux 的 `tmpfs` 内核模块实现。

**设计动机——为什么不用 System V shm 或 POSIX shm？**

| 机制 | 问题 |
|------|------|
| System V shm | 全局命名空间，需 root 权限清理，无引用计数 |
| POSIX shm | 挂载在 `/dev/shm`，全局可见，大小固定 |
| mmap 文件共享 | 需要实际文件系统支持，有 IO 开销 |

ashmem 解决了：**引用计数自动回收 + 基于 FD 的权限控制 + 物理内存按需释放（pin/unpin）**。

**核心工作原理：**

```
ashmem 创建与共享流程：

进程A（服务端）                          进程B（客户端）
─────────────                          ─────────────

1. ashmem_create_region()              
   → open("/dev/ashmem")               
   → ioctl(ASHMEM_SET_NAME)            
   → ioctl(ASHMEM_SET_SIZE)            
   返回 fd_A                           
        │                               
2. mmap(fd_A) → 映射到                 3. Binder 传递 fd_A
   进程A的虚拟地址空间                       → Binder 驱动复制 fd → fd_B
        │                               
4. 直接写入共享内存区域                       5. mmap(fd_B) → 映射到
                                             进程B的虚拟地址空间
        └──────────────┬──────────────────┘
                       ▼
              ┌────────────────────┐
              │  同一物理内存页     │
              │  (COW 机制保护)    │
              └────────────────────┘
```

**pin/unpin 机制——ashmem 的杀手锏：**

这是 ashmem 区别于普通 mmap 文件的核心能力：

```c
// pinning: 锁定物理页，告知内核这些页不能被回收
int pin_status = ASHMEM_IS_PINNED;  // 1 = 被 pin
ioctl(fd, ASHMEM_PIN, &pin_range);

// unpinning: 解除锁定，内核可在内存压力下回收这些页
int unpin_status = ASHMEM_IS_UNPINNED;  // 0 = 未 pin
ioctl(fd, ASHMEM_UNPIN, &unpin_range);
```

```
pin/unpin 生命周期：

  ┌─────────┐     unpin      ┌──────────┐   内存压力触发
  │  PINNED │ ───────────────→│ UNPINNED │ ──────────────→ 内核回收
  │ (活跃)  │←───────────────│ (可回收)  │               物理页（清零）
  └─────────┘     pin         └──────────┘
                                    │
                           下次访问时 → SIGBUS 或自动填零页
```

**面试重点——ashmem 的内存回收与 LRU：**

unpinned 的 ashmem 页面被内核标记为"可回收"。当 LMK 或 kswapd 触发时：
1. 内核遍历 unpinned 页 → 加入 LRU 尾端
2. 物理页回收到 buddy allocator（内容丢失）
3. 进程再次访问 → 触发缺页异常 → 返回全零页
4. 调用者需要通过 **协议层** 感知数据丢失（ashmem 本身不告知）

**典型面试追问——ashmem vs mmap tmpfs 文件对比：**

| 维度 | ashmem | mmap + tmpfs |
|------|--------|-------------|
| 内存回收 | pin/unpin 精确控制 | 依赖内核 VFS 缓存回收 |
| FD 传递 | Binder 原生支持 | Binder 传递但语义不同 |
| 引用计数 | 驱动层引用计数 → 自动释放 | 依赖文件引用计数 |
| 物理页释放 | 可主动释放（unpin + madvise） | 仅 unlink + 等待引用归零 |
| Android 审计 | Kernel 内存审计可见 | 混淆在 tmpfs 中 |

---

### Q4: Native 内存泄漏如何检测？malloc_debug / nativeheapdump / libtrackmem 三剑客对比

Native 内存泄漏比 Java 堆泄漏更难排查——没有强引用追踪、没有 GC Root、没有 HPROF。

**方案一：malloc_debug（Android 平台内置）**

```bash
# 开启 malloc_debug
adb shell setprop libc.debug.malloc.options "backtrace leak_track"
adb shell setprop libc.debug.malloc.program <package_name>
# 重启应用后生效

# 工作原理：
#   malloc_debug 通过 LD_PRELOAD 注入，拦截所有 malloc/free/realloc/calloc
#   leak_track 模式记录每次分配的调用栈和大小
#   在进程退出时，dump 所有未释放的分配地址 → backtrace → 调用栈
```

```
malloc_debug 启动流程（AOSP bionic/libc）：

1. setprop → __libc_debug_malloc_init()
2. 读取 android.malloc.debug.options
3. 初始化 MallocDebug 结构体，启用 hook
4. 每次 malloc 时 → debug_malloc() → 记录 header(分配大小+backtrace+guard)
5. 每次 free 时   → debug_free()   → 标记释放、检测 double-free
6. 进程退出时     → debug_final()  → 遍历未释放链表 → dump 到 logcat

关键源码（bionic/libc/malloc_debug/）：
- malloc_debug.cpp:  入口初始化
- Backtrace.cpp:     调用栈收集（使用 libunwind）
- DebugData.cpp:     泄漏记录管理
```

**方案二：nativeheapdump（Android ≥10）**

```bash
# 运行时触发 native heap dump（无需重启应用）
adb shell am dumpheap -n <pid> /data/local/tmp/native.txt

# 或通过代码：
#include <malloc.h>
// 调用 android_mallopt(M_DUMP_HEAP, ...)
```

```
nativeheapdump 输出格式：

z Zygote  Allocations 67  (total size: 4567K)
   size    allocations    total-size   backtrace
   4096    25             102400       #00 pc 000abcd  /system/lib/libc.so (malloc+84)
                                       #01 pc 0012345  /system/lib/libandroid_runtime.so
                                       ...
   1024    42             43008        #00 pc 000defg  /vendor/lib/libutils.so
                                       ...
```

**方案三：libtrackmem（Android 内部）**

libtrackmem 是 Android 团队的内部分析工具，特点：
- 基于 `__malloc_hook`（已废弃）或 PLT hook
- 按调用栈聚合内存，生成 **火焰图（flame graph）**
- 支持差分分析（diff 两次 dump，定位增长点）

**三种方案对比：**

| 方案 | 侵入性 | 性能开销 | 是否需要重启 | 适用场景 |
|------|--------|---------|-------------|---------|
| malloc_debug | 低（系统内置） | 极高（5x-10x） | 是 | 开发/测试阶段完整分析 |
| nativeheapdump | 零 | 低（仅 dump 时刻） | 否 | 线上/灰度，按需 dump |
| libtrackmem | 中 | 中（持续记录） | 否 | CI/自动化回归 |
| heapprofd (Perfetto) | 零 | 极低 | 否 | **Android 10+ 首选** |

**面试加分项——heapprofd（Perfetto 原生内存分析器）：**

```bash
# Android 10+ 推荐：基于 Perfetto 的 heapprofd
# 原理：内核 eBPF/linker 注入 + 环形缓冲区采样
# 无需修改代码，1% 以下性能开销
# 支持：按调用栈聚合、时间线视图、差分对比

# 配置示例
adb shell perfetto -c - --txt <<EOF
buffers: { size_kb: 65536 }
data_sources: {
  config {
    name: "android.heapprofd"
    target_buffer: 0
    heapprofd_config {
      sampling_interval_bytes: 4096
      process_cmdline: "com.example.app"
    }
  }
}
EOF
```

---

### Q5: Bitmap 内存在各 Android 版本的存储位置是如何变迁的？

这是面试中"Android 版本演进"的经典问题，考查对系统设计的整体理解。

```
Bitmap 内存存储位置演进时间线：

Android 2.3 及之前 (API ≤10)
┌────────────────────────────────────────────────────────┐
│                Java Heap（Dalvik 堆）                   │
│  ┌──────────────────────────────────────────────┐      │
│  │  Bitmap.java                                 │      │
│  │  └── byte[] mBuffer (像素数据在 Java 堆)      │      │
│  │  → 受 GC 管理，GC 触发即可能卡顿              │      │
│  │  → 统计内存在 "Java 已分配" 中                │      │
│  └──────────────────────────────────────────────┘      │
│  问题：单个 Bitmap 可达数十 MB → 频繁 GC → 掉帧        │
└────────────────────────────────────────────────────────┘

Android 3.0 ~ 7.0 (API 11-25)
┌────────────────────────────────────────────────────────┐
│                  Native Heap（C/C++ 堆）                │
│  ┌──────────────────────────────────────────────┐      │
│  │  Bitmap.java                                 │      │
│  │  └── long mNativeBitmap (指向 Native 内存)    │      │
│  │                                             │      │
│  │  BitmapFactory.cpp                           │      │
│  │  └── pixel storage → jemalloc/malloc          │      │
│  └──────────────────────────────────────────────┘      │
│  优势：不参与 Java GC，性能稳定                        │
│  问题：需手动 recycle()；内存统计不透明                 │
└────────────────────────────────────────────────────────┘

Android 8.0+ (API 26+)
┌────────────────────────────────────────────────────────┐
│              ashmem + Hardware Buffer                  │
│  ┌──────────────────────────────────────────────┐      │
│  │  Bitmap.java                                 │      │
│  │  ├── 普通 Bitmap → Native Heap (同 7.0)       │      │
│  │  └── Hardware Bitmap → GraphicBuffer         │      │
│  │       └── ashmem 共享内存区域                 │      │
│  │                                             │      │
│  │  关键变化：                                   │      │
│  │  ● Hardware Bitmap 可通过 AHardwareBuffer    │      │
│  │    实现零拷贝跨进程共享                       │      │
│  │  ● 内存由 Gralloc HAL 管理                    │      │
│  │  ● 支持 GPU 纹理直读（无 CPU 拷贝）           │      │
│  └──────────────────────────────────────────────┘      │
└────────────────────────────────────────────────────────┘
```

**变迁原因深度分析：**

```
2.3 之前：像素在 Java 堆
  → 问题：Bitmap 通常很大（1080p ARGB_8888 = 8MB），触发 GC 频繁
  → GC 暂停时间长（Dalvik 时代 Mark-Sweep，无并发）
  → 用户感知：滚屏掉帧、动画卡顿

3.0-7.0：像素迁移到 Native 堆
  → 引用：Bitmap.java 只持有 long mNativeBitmap（8字节指针）
  → GC：Java GC 只扫描8字节引用，不扫描像素数据
  → 但：Bitmap.recycle() 时机依赖 finalize()，不够可靠
  → 引入 BitmapFactory.Options.inBitmap（复用已有 Bitmap 内存）

8.0+：引入 Hardware Bitmap 和 ashmem
  → Hardware Bitmap：像素存在 GraphicBuffer（GPU 可直接访问）
  → ashmem：实现 RenderThread/SurfaceFlinger/App 共享同一块像素内存
  → zero-copy：避免了 SF→App 的像素拷贝，显著降低内存占用
  → Bitmap.Config.HARDWARE：不可直接在 CPU 端访问像素
```

**面试追问——不同 Bitmap.Config 的内存占用计算：**

```
计算公式：width × height × 每像素字节数

Config          每像素字节   1080p屏幕(2.1MP)   4000×3000照片(12MP)
────────────────────────────────────────────────────────────
ALPHA_8         1B           2.1MB              12MB
RGB_565         2B           4.2MB              24MB
ARGB_8888       4B           8.4MB              48MB
RGBA_F16        8B           16.8MB             96MB
HARDWARE        GPU 管理     取决于驱动实现     取决于驱动实现

注意：RGBA_F16 自 Android 8.0 引入，用于广色域显示
```

---

### Q6（补充）: Native 内存与 Java 堆内存的边界在哪里？如何理解 PSS/VSS/RSS/USS？

```
进程内存统计层次（使用 adb shell dumpsys meminfo <pid>）：

┌───────────────────────────────────────────────────────────┐
│                        PSS (Proportional Set Size)        │
│  ┌───────────────────────────────────────────────────┐   │
│  │                    USS (Unique Set Size)           │   │
│  │  ┌─────────────────────────────────────────┐      │   │
│  │  │           RSS (Resident Set Size)        │      │   │
│  │  │  ┌──────────────────────────────┐       │      │   │
│  │  │  │      VSS (Virtual Set Size)  │       │      │   │
│  │  │  │   (全部虚拟地址空间)          │       │      │   │
│  │  │  └──────────────────────────────┘       │      │   │
│  │  │     物理驻留但含共享库                   │      │   │
│  │  └─────────────────────────────────────────┘      │   │
│  │      独占物理内存（进程私有脏页）                   │   │
│  └───────────────────────────────────────────────────┘   │
│     按比例分摊共享内存（最重要的 OOM 判定指标）            │
└───────────────────────────────────────────────────────────┘

dumpsys meminfo 输出解读：

                 Pss      Private     Shared
  Native Heap    15624    15320       304      ← malloc/jemalloc 分配
  Dalvik Heap    28456    28100       356      ← Java 对象（ART 管理）
  Stack          4096     4096        0        ← 线程栈
  Ashmem         8192     0           8192     ← 共享内存
  Gfx dev        16384    16384       0        ← GPU 相关
  Unknown        2048     1024        1024
  ─────────────────────────────────────────────
  TOTAL          76800    64924       11876
```

---

## 二/三、jemalloc 分配路径与 ashmem 回收机制

### jemalloc 完整分配路径：tcache → bin → arena

```
malloc(64字节) 的完整路径：

步骤1：tcache 快速路径（无锁）
  ┌──────────────────────────────────────────────┐
  │ 线程 T1                                     │
  │   tcache_bin[对应64B的size class]           │
  │   命中？→ 弹出栈顶 → 返回指针（~10 CPU指令） │
  │   未命中？→ 进入步骤2                       │
  └──────────────────────────────────────────────┘

步骤2：tcache refill → bin 慢路径（arena 锁）
  ┌──────────────────────────────────────────────┐
  │ 获取 arena->lock                            │
  │   bin[对应64B的size class]                  │
  │     → bin->run 链表中找有空闲 region 的 run │
  │     → 批量取出 N 个空闲 region 填充到 tcache │
  │     → 返回一个给调用方                       │
  │   如果 bin 中所有 run 都满了？→ 步骤3        │
  └──────────────────────────────────────────────┘

步骤3：创建新 run（系统调用）
  ┌──────────────────────────────────────────────┐
  │ 从 arena 管理的 extent 池中获取页            │
  │   → 优先从 extent_dirty 复用（延迟合并）     │
  │   → 若无可用 extent → 步骤4                  │
  └──────────────────────────────────────────────┘

步骤4：向 OS 申请内存
  ┌──────────────────────────────────────────────┐
  │ run 大小 < 阈值 → sbrk() 扩展数据段          │
  │ run 大小 ≥ 阈值 → mmap(MAP_ANONYMOUS)        │
  │   返回 extent → 切分为 run → 切分为 region   │
  │   → 初始化 bitmap → 填充 tcache → 返回       │
  └──────────────────────────────────────────────┘

关键延迟数据（Pixel 6, 64位）：
  tcache 命中：        ~10 ns   （最快，无锁）
  tcache refill：      ~200 ns  （需 arena 锁）
  新 run 创建：         ~2 μs    （含页分配）
  mmap 系统调用：       ~5 μs    （内核态切换）
```

**tcache 内部结构（源码对应 jemalloc/include/jemalloc/internal/tcache_inlines.h）：**

```c
// tcache 核心数据结构（简化）
typedef struct tcache_s {
    // 每个 size class 一个缓存槽
    tcache_bin_t tbins[TCACHE_NBINS];  // 小对象缓存
    // 缓存统计
    uint64_t gc_count;                  // 垃圾回收计数
    uint64_t alloc_count;               // 分配计数
} tcache_t;

typedef struct tcache_bin_s {
    void **avail;      // 可用对象栈（LIFO）
    uint32_t ncached;  // 当前缓存数量
    uint32_t low_water; // 低水位（触发 refill）
} tcache_bin_t;

// 快速路径分配伪代码
void* tcache_alloc(tcache_t* tcache, size_t size) {
    unsigned binind = size_to_bin(size);
    tcache_bin_t* tbin = &tcache->tbins[binind];
    
    // 无锁栈弹出
    if (tbin->ncached > 0) {
        tbin->ncached--;
        void* ret = *tbin->avail;
        tbin->avail++;
        return ret;
    }
    // cache miss → 走慢路径
    return arena_tcache_refill(binind, tbin);
}
```

**gc_count 与脏页清理：**

```c
// jemalloc 的惰性回收（关键面试点）
// 当 tcache->gc_count 达到阈值时触发
void tcache_gc_event(tcache_t* tcache) {
    tcache->gc_count++;
    if (tcache->gc_count >= opt_tcache_gc_incr_bytes) {
        tcache_flush(tcache);  // 清理 tcache 中长时间未使用的缓存
        tcache->gc_count = 0;
    }
}
```

---

### ashmem 的 pin/unpin 与内存回收深度解析

**pin 机制：**

```c
// AOSP system/core/libcutils/ashmem-dev.cpp
int ashmem_pin_region(int fd, size_t offset, size_t length) {
    struct ashmem_pin pin = {
        .offset = offset,
        .len = length,
    };
    return ioctl(fd, ASHMEM_PIN, &pin);
}
// 内核 ashmem 驱动：
//   → 遍历 [offset, offset+len] 范围内的页
//   → 清除 ASHMEM_IS_UNPINNED 标志
//   → 锁定物理页不可回收
//   → 当所有页都 unpin 后 → 整个 ashmem 区域可被回收
```

**unpin 触发内存回收的完整流程：**

```
时间线：unpin → 内存压力 → 回收 → 缺页恢复

T0: 进程调用 ashmem_unpin(fd, 0, len)
    → 内核清除页标志 → 页进入 UNPINNED 状态
    → 进程仍持有虚拟映射（页表条目还在）

T1: 系统内存压力（LMK / kswapd）
    → 内核 shrinker 扫描 unpinned ashmem 页
    → 找到 UNPINNED 页 → 加入 LRU 尾部
    → 回收物理页到 buddy allocator
    → PTE 置为不存在（页被换出）

T2: 进程再次访问该地址（读/写）
    → MMU 触发缺页异常
    → 内核检查 VMA：ashmem 区域，未 pin
    → 分配新物理页 → 填零（ZERO_PAGE）
    → 更新 PTE → 返回用户态

关键：进程看到的始终是零页！
      → 上层必须用标志位/Binder 通信
      → 感知"数据已丢失，需要重新生成"
```

**面试追问——Bitmap 如何使用 ashmem 实现内存优化：**

```java
// Android 8.0+ Bitmap 的 Hardware 路径
// frameworks/base/graphics/java/android/graphics/Bitmap.java

// 创建 Hardware Bitmap 时
// → nativeCreateHardwareBitmap()
// → GraphicBuffer::allocate()
// → Gralloc HAL::allocate()
// → ion/ashmem 分配器分配共享内存
// → Gralloc 注册到 SurfaceFlinger
// → RenderThread 直接渲染到该内存 → 零拷贝显示

// 内存对比：
//   普通 Bitmap (ARGB_8888, 1080p):
//     App 进程:    8MB Native Heap
//     SF 进程:     8MB 拷贝 ← 总计 16MB

//   Hardware Bitmap (1080p):
//     App 进程:    8MB ashmem 映射
//     SF 进程:     同一块 ashmem 映射 ← 总计 8MB
//     → 节省 50% 内存，零拷贝
```

---

## 四、Native 内存分配全景图

```
                    Native 内存分配全景图
                    ═══════════════════════

                        应用程序层
                    ┌──────────────────────────────┐
                    │  BitmapFactory (JNI)          │
                    │  MediaCodec / MediaPlayer     │
                    │  OpenGL ES (EGL/GLES)         │
                    │  NDK 应用 (malloc/new)        │
                    │  RenderScript / Vulkan        │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────┴───────────────┐
                    │      Bionic libc              │
                    │  ┌──────────────────────┐     │
                    │  │ malloc/free/realloc   │     │
                    │  │ calloc/memalign       │─────┼──→ malloc_debug hook 点
                    │  │ posix_memalign        │     │
                    │  └──────────┬───────────┘     │
                    └──────────────┼───────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                     ▼
    ┌─────────────────┐  ┌─────────────────┐  ┌──────────────────┐
    │   jemalloc      │  │   scudo         │  │   dlmalloc       │
    │  (Android 5-10) │  │ (Android 11+    │  │  (Android ≤4.4)  │
    │                 │  │  默认分配器)     │  │                  │
    └────────┬────────┘  └────────┬────────┘  └────────┬─────────┘
             │                    │                     │
             └────────────────────┼─────────────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │       系统调用层           │
                    │  ┌──────────────────────┐ │
                    │  │ sbrk/brk (数据段)     │ │
                    │  │ mmap(MAP_ANONYMOUS)   │ │
                    │  └──────────────────────┘ │
                    └─────────────┬─────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │       内核层              │
                    │  ┌──────────────────────┐ │
                    │  │ VMA (虚拟内存区域)     │ │
                    │  │ Page Table (页表)      │ │
                    │  │ Buddy Allocator       │ │
                    │  │ Slab Allocator        │ │
                    │  │ Page Cache            │ │
                    │  └──────────────────────┘ │
                    └─────────────┬─────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │      物理内存 (DDR)        │
                    └───────────────────────────┘


              跨进程共享路径（ashmem / ION / dma-buf）:

  ┌──────────┐    Binder+FD    ┌─────────────┐
  │  App     │◄────────────────│SurfaceFlinger│
  │ 进程     │   ashmem fd     │  进程        │
  │          │────────────────►│              │
  │  mmap    │   共享物理页    │  mmap        │
  │  同一区域 │                │  同一区域     │
  └──────────┘                └─────────────┘
         │                          │
         └──────────┬───────────────┘
                    ▼
         ┌─────────────────────┐
         │  /dev/ashmem (驱动) │
         │  → 引用计数管理      │
         │  → pin/unpin 控制   │
         │  → 内核回收集成     │
         └─────────────────────┘

  ┌──────────┐    Binder+FD    ┌─────────────┐
  │  Camera  │────────────────►│  Media      │
  │  HAL     │  dma-buf/ION fd │  Codec      │
  │          │  零拷贝传递帧    │             │
  └──────────┘                └─────────────┘
```

**Android 11+ 的 Scudo 分配器（新增面试考点）：**

从 Android 11 开始，默认 Native 分配器从 jemalloc 切换为 **Scudo**（硬化的分配器）：

```
Scudo vs jemalloc 关键差异：

维度            jemalloc                  Scudo
────────────────────────────────────────────────────
首要目标       性能最优                  安全性最优
内存保护       无                        Header/Footer canary + 校验和
UAF 防护       无                        Quarantine 延迟释放
Double-free     未定义行为              检查后 abort
缓冲区溢出     未定义行为               概率性检测（canary 校验）
性能          基准 (1x)                  ~1.05x-1.15x
堆布局随机化   有限                      完全随机化

引用（Android 11 CDD）：
  "Scudo is the default native allocator for Android 11,
   providing hardened malloc with minimal performance overhead."
```

---

## 五、BitmapFactory 的 nativeDecodeStream 源码解析

```cpp
// frameworks/base/core/jni/android/graphics/BitmapFactory.cpp

// Java 调用链：
//   BitmapFactory.decodeStream(InputStream) 
//   → nativeDecodeStream(InputStream, byte[], Options)
//   → doDecode()

static jobject nativeDecodeStream(JNIEnv* env, jobject clazz,
                                   jobject is,       // Java InputStream
                                   jbyteArray storage,
                                   jobject padding,
                                   jobject options) {
    
    // 1. 创建 Skia 流适配器——将 Java InputStream 包装为 SkStream
    SkStream* stream = CreateJavaInputStreamAdaptor(env, is, storage);
    if (!stream) return nullptr;

    // 2. 获取 Options 中的复用 Bitmap（inBitmap）
    //    这是内存优化的关键：复用已有 Bitmap 的 Native 像素缓冲区
    jobject javaBitmap = nullptr;
    if (options) {
        javaBitmap = env->GetObjectField(options, gOptions_bitmapFieldID);
    }

    // 3. 调用核心解码函数
    jobject bitmap = doDecode(env, stream, padding, options,
                              /*inBitmap=*/javaBitmap);

    // 4. 清理 SkStream
    delete stream;
    return bitmap;
}

// ── doDecode 核心逻辑 ──
static jobject doDecode(JNIEnv* env, SkStreamRewindable* stream,
                        jobject padding, jobject options,
                        jobject inBitmap) {
    
    // 步骤1: 采样率处理（inSampleSize）
    int sampleSize = 1;
    if (options) {
        sampleSize = env->GetIntField(options, gOptions_sampleSizeFieldID);
        // 如果设置了 inJustDecodeBounds，仅解码头信息，不分配像素
        bool justDecodeBounds = env->GetBooleanField(options, 
            gOptions_justDecodeBoundsFieldID);
        
        if (justDecodeBounds) {
            // 仅解析图片头 → 获取宽高/类型 → 零内存分配
            SkCodec::Result result = SkCodec::MakeFromStream(stream)
                ->getInfo(&info);
            // 填充 Options.outWidth / outHeight / outMimeType
            // 返回 null（无 Bitmap 对象）
            return nullptr;
        }
    }

    // 步骤2: 创建 SkCodec（Skia 的多格式图片解码器）
    std::unique_ptr<SkCodec> codec = SkCodec::MakeFromStream(stream);
    if (!codec) return nullptr;

    SkImageInfo imageInfo = codec->getInfo()
        .makeColorType(prefColorType)      // 色彩空间转换
        .makeAlphaType(prefAlphaType);      // Alpha 通道

    // 步骤3: 内存分配——这是 Native 内存分配的核心
    // 根据 Android 版本和 Config 决定像素内存的位置
    SkBitmap bitmap;
    bool isHardware = isHardwareConfig(prefConfig);  // API 26+
    
    if (isHardware) {
        // ── Android 8.0+ Hardware Bitmap 路径 ──
        // 通过 GraphicBuffer + Gralloc 在 ashmem 中分配
        // 像素数据由 GPU 直接访问，CPU 端不可读写
        GraphicBuffer* buffer = new GraphicBuffer(
            width, height, 
            PIXEL_FORMAT_RGBA_8888,
            GRALLOC_USAGE_HW_TEXTURE | GRALLOC_USAGE_SW_READ_OFTEN);
        
        // 关联到 HardwareBuffer → 创建 Hardware Bitmap
        bitmap.setHardwareBuffer(buffer);
        
    } else if (inBitmap != nullptr) {
        // ── inBitmap 复用路径 ──
        // 复用已有 Bitmap 的像素缓冲区（避免重复分配）
        SkBitmap* reuseBitmap = &bitmap;  // 尝试复用
        if (!reuseBitmap->tryAllocPixels(imageInfo)) {
            // 复用失败：尺寸/格式不匹配
            // fallback 到普通分配
            bitmap.allocPixels(imageInfo);  // → malloc (Native Heap)
        }
        
    } else {
        // ── 普通 Native 分配路径 ──
        // SkBitmap::allocPixels → 底层调用 malloc
        // jemalloc/scudo 的 tcache → bin → arena 路径
        bitmap.allocPixels(imageInfo);
        // 1080p ARGB_8888: 1920×1080×4 ≈ 8.3MB Native 内存
    }

    // 步骤4: 执行实际解码——写入像素数据
    SkCodec::Result result = codec->getPixels(imageInfo, 
        bitmap.getPixels(),      // 目标像素缓冲区（Native 内存）
        bitmap.rowBytes());      // 每行字节数

    // 步骤5: 包装为 Java Bitmap 对象（JNI）
    // Bitmap.java 只持有 long mNativePtr → 指向 Native 像素缓冲区
    jobject javaBitmap = GraphicsJNI::createBitmap(env, &bitmap, 
        bitmapCreateFlags, bytesArrayStorage);
    
    return javaBitmap;
}
```

**解码流程中的内存分配关键点总结：**

```
BitmapFactory.decodeStream 内存分配决策树：

                    解码请求
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
  inJustDecodeBounds  inBitmap    普通解码
  = true              复用           (新分配)
        │              │              │
        ▼              ▼              ▼
  零内存分配      复用已有 Native   malloc(Native堆)
  (仅读头信息)     缓冲区           ─────────────────
                  ──────────        Android 8.0+:
                  失败 → fallback   Config.HARDWARE?
                                       │
                              ┌────────┴────────┐
                              ▼                 ▼
                          是 → ashmem       否 → Native堆
                          (Gralloc分配)     (jemalloc/scudo)
                          zero-copy GPU     CPU可读写
```

---

## 六、实战：使用 malloc_debug 定位 Native 内存增长

### 场景：应用 Native 内存持续增长，Java 堆稳定

**步骤1：开启 malloc_debug 并获取完整 backtrace**

```bash
# 开启详细调试（在开发设备上）
adb root
adb shell setprop libc.debug.malloc.options "backtrace=64 leak_track fill_on_alloc"
adb shell setprop libc.debug.malloc.program com.example.leakapp
adb shell am force-stop com.example.leakapp
adb shell am start com.example.leakapp/.MainActivity

# 参数说明：
#   backtrace=64         → 每帧记录 64 层调用栈（默认16）
#   leak_track           → 记录所有未释放的分配
#   fill_on_alloc        → 填充 0xeb（辅助 use-after-free 检测，不可用于泄漏检测）
#   泄漏检测建议值：backtrace leak_track

# 观察 logcat 输出
adb logcat -s libc:V | grep "malloc_debug"
# 输出示例：
# malloc_debug: Total unfreed allocations: 1523
# malloc_debug: Largest 10 leaks:
#   size: 1048576, allocations: 12, backtrace:
#     #00 pc 00000000000abcde  /apex/com.android.runtime/lib64/bionic/libc.so (malloc+176)
#     #01 pc 0000000000123456  /system/lib64/libandroid_runtime.so
#     #02 pc 00000000007890ab  /system/framework/arm64/boot-framework.oat
```

**步骤2：使用脚本聚合和分析泄漏栈**

```bash
# 将 native heap dump 转存到文件
adb shell am dumpheap -n <pid> /data/local/tmp/native_heap.txt
adb pull /data/local/tmp/native_heap.txt .

# 自定义聚合脚本（Python）
cat > analyze_native_heap.py <<'PYEOF'
import re
import sys
from collections import defaultdict, Counter

def parse_native_heap(filepath):
    leaks = defaultdict(lambda: {'total_size': 0, 'count': 0, 'traces': []})
    
    with open(filepath) as f:
        lines = f.readlines()
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # 匹配格式:   size  allocations  total-size  backtrace
        m = re.match(r'^\s+(\d+)\s+(\d+)\s+(\d+)', line)
        if m:
            size = int(m.group(1))
            alloc_count = int(m.group(2))
            total_size = int(m.group(3))
            
            # 收集调用栈
            trace = []
            i += 1
            while i < len(lines) and lines[i].strip().startswith('#'):
                trace.append(lines[i].strip())
                i += 1
            
            trace_key = '\n'.join(trace[:5])  # 前5帧作为聚合键
            leaks[trace_key]['total_size'] += total_size
            leaks[trace_key]['count'] += alloc_count
            leaks[trace_key]['traces'] = trace[:10]
            continue
        i += 1
    
    # 按 total_size 降序排列
    sorted_leaks = sorted(leaks.items(), key=lambda x: x[1]['total_size'], reverse=True)
    return sorted_leaks

if __name__ == '__main__':
    leaks = parse_native_heap(sys.argv[1])
    print("=== TOP 20 Native 内存泄漏点 ===\n")
    for i, (trace_key, info) in enumerate(leaks[:20]):
        print(f"[{i+1}] 泄漏 {info['total_size']/1024:.1f}KB  "
              f"({info['count']} 次分配, 均次 {info['total_size']/info['count']:.0f}B)")
        print(f"    调用栈:")
        for frame in info['traces'][:5]:
            print(f"      {frame}")
        print()
PYEOF

python3 analyze_native_heap.py native_heap.txt
```

**步骤3：使用 addr2line / ndk-stack 符号化调用栈**

```bash
# 方法1: addr2line（需要带符号的 .so）
aarch64-linux-android-addr2line -f -e obj/local/arm64-v8a/libnative-lib.so 000000000000abcde

# 方法2: ndk-stack（从 logcat 流中符号化）
adb logcat | $NDK/ndk-stack -sym obj/local/arm64-v8a/

# 方法3: Android Studio Profiler → Native Memory → Capture heap dump
# 图形化分析，自动符号化
```

**步骤4：典型泄漏模式与修复**

```cpp
// ── 泄漏模式1: JNI 局部引用溢出 ──
// 问题代码（在 JNI 循环中）：
extern "C" JNIEXPORT void JNICALL
Java_com_example_NativeLib_processFrames(JNIEnv* env, jobject, jobjectArray frames) {
    jsize len = env->GetArrayLength(frames);
    for (jsize i = 0; i < len; i++) {
        // ❌ 每次循环创建新的 LocalRef，不释放
        // 本地引用表最多 512 个（默认），溢出导致崩溃或泄漏
        jobject frame = env->GetObjectArrayElement(frames, i);
        // ... 处理 frame ...
        // 缺少: env->DeleteLocalRef(frame);
    }
    // 修复1: 显式释放
    //   env->DeleteLocalRef(frame);
    // 修复2: 使用 PushLocalFrame/PopLocalFrame
    //   env->PushLocalFrame(256);
    //   // ... 循环处理 ...
    //   env->PopLocalFrame(nullptr);
}

// ── 泄漏模式2: Native 线程未 detach JNI ──
// 问题代码：
void native_thread_func() {
    JNIEnv* env;
    // ❌ 线程从未 AttachCurrentThread → JNI 内部分配的资源不会释放
    // 或者 Attach 了但从未 Detach
    jvm->AttachCurrentThread(&env, nullptr);
    // ... 工作 ...
    // 缺少: jvm->DetachCurrentThread();
}

// ── 泄漏模式3: malloc 没有配对的 free ──
// 问题代码：
extern "C" JNIEXPORT jlong JNICALL
Java_com_example_NativeLib_createBuffer(JNIEnv* env, jobject, jint size) {
    // ❌ 直接在 JNI 中返回 Native 指针，依赖 Java finalize 释放
    void* buffer = malloc(size);
    if (!buffer) {
        // ❌ OOM 时抛异常，但没有 Java 异常对象
        return 0;  // 调用方无法区分 OOM 和其他错误
    }
    return reinterpret_cast<jlong>(buffer);
}

// ── 泄漏模式4: 第三方 .so 内部泄漏 ──
// 解决方法：
//   1. 使用 wrap.sh 重定向 malloc_debug 到特定 .so
//   2. 对第三方 .so 进行 PLT hook 注入检测
//   3. 使用 heapprofd 按 .so 过滤
```

**步骤5：建立 Native 内存监控基线**

```bash
# 使用 Perfetto/heapprofd 建立自动化基线
# Android 10+ 推荐方案

cat > heapprofd_config.txt <<EOF
buffers: {
  size_kb: 131072  # 128MB 缓冲区
}
data_sources: {
  config {
    name: "android.heapprofd"
    heapprofd_config {
      sampling_interval_bytes: 8192   # 每 8KB 采样一次
      process_cmdline: "com.example.app"
      shmem_size_bytes: 8388608       # 8MB 共享内存
      block_client: false
    }
  }
}
duration_ms: 300000  # 采集 5 分钟
EOF

# 启动采集
adb push heapprofd_config.txt /data/local/tmp/
adb shell perfetto --txt -c /data/local/tmp/heapprofd_config.txt \
    -o /data/local/tmp/native_profile.pftrace

# 拉取并在 Perfetto UI (https://ui.perfetto.dev) 中分析
adb pull /data/local/tmp/native_profile.pftrace .

# 分析重点：
#   ● Heap Graph 视图 → 按调用栈聚合的内存分布
#   ● Flamegraph 视图 → 定位分配热点
#   ● Timeline 视图 → 观察内存增长的时间曲线
#   ● Diff 模式 → 对比两个时间点，精确定位增量
```

---

## 总结：Native 内存管理面试核心要点

```
┌─────────────────────────────────────────────────────────────┐
│              Native 内存管理 — 面试速查表                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ★ 分配器演进: dlmalloc(≤4.4) → jemalloc(5.0-10) → Scudo(11+)│
│                                                             │
│  ★ jemalloc 三级: arena(锁域) → bin(size class) → run(page) │
│     + tcache(线程无锁快速路径)                                │
│                                                             │
│  ★ 系统调用: sbrk(小,数据段) / mmap(大,匿名映射)              │
│                                                             │
│  ★ ashmem: Android 特有共享内存, pin/unpin 控制回收            │
│                                                             │
│  ★ Bitmap 演进: Java堆(≤2.3) → Native堆(3.0-7.0)            │
│     → ashmem+Hardware(8.0+)                                 │
│                                                             │
│  ★ 泄漏检测: malloc_debug → nativeheapdump → heapprofd       │
│                                                             │
│  ★ 内存统计: PSS(最重要的OOM指标) > USS > RSS > VSS          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

> **面霸心得：** Native 内存管理的面试题往往从"Bitmap 放哪里"这种表面问题切入，真正考察的是你对 **Android 内存层次（Java堆/Native堆/ashmem/Gralloc）** 的完整理解。回答时要主动串联：从 jemalloc 的 bin 结构讲到 Bitmap 的像素分配，从 ashmem 讲到 Hardware Bitmap 的零拷贝。展示全链路思维是区分 3 年经验与 5 年经验的关键。
