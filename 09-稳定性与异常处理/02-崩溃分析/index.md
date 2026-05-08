# 崩溃分析 — Android 稳定性面试深度解析

---

## 一、面试问题（6+ 高频真题）

以下整理了 Android 崩溃分析方向最常见的面试问题，涵盖 Java 层、Native 层、OOM 以及崩溃收集平台四大维度：

### 1.1 Java 崩溃相关

**Q1：线上收到一条 NullPointerException 的崩溃堆栈，如何快速定位根因？**

> 考察点：堆栈解读能力、NPE 常见场景（链式调用、自动拆箱、集合元素为 null、异步回调中 Context 被回收）。

**Q2：ClassCastException 通常在什么场景下发生？如何从堆栈中区分是布局文件问题还是代码强转问题？**

> 考察点：布局 inflate 时的类型不匹配 vs 代码中 `(TargetType) object` 强转失败的堆栈差异。

**Q3：OutOfMemoryError 的堆栈中，`java.lang.OutOfMemoryError` 后面的 message 有几种典型形式？分别代表什么含义？**

> 考察点：`Java heap space`、`pthread_create (1040KB stack) failed`、`Could not allocate JNI Env`、`FD limit exceeded` 四种关键 message 的区分。

### 1.2 Native 崩溃相关

**Q4：线上收到一个 `SIGSEGV (signal 11)` 的 tombstone 文件，其中只有内存地址没有函数名，你如何将其还原为可读的调用栈？**

> 考察点：符号化流程——addr2line、ndk-stack、Android Studio 的 `Analyze Stacktrace`、上传符号表的时机。

**Q5：tombstone 文件中的 `Abort message` 行通常包含什么关键信息？`Build fingerprint` 为什么重要？**

> 考察点：tombstone 关键字段解读，Abort message 中 art 的 check failed、Build fingerprint 用于匹配符号表。

### 1.3 OOM 专题

**Q6：线上 OOM 率居高不下，你如何区分是 Java Heap 问题、线程数问题还是 FD 泄漏？各自用什么工具或指标排查？**

> 考察点：Android Profiler 的 Memory 视图、`/proc/pid/limits` 查看 FD 上限、`/proc/pid/status` 查看 Threads 数、`dumpsys meminfo` 分析内存分布。

### 1.4 崩溃收集与治理

**Q7：UncaughtExceptionHandler 的原理是什么？如果 App 中有多个地方设置了它（如 Bugly + 自定义），会发生什么？**

> 考察点：`Thread.setDefaultUncaughtExceptionHandler` 的链式调用模式、前一个 handler 的保存与调用、多 SDK 共存时的冲突处理。

**Q8：崩溃率的统计口径是怎样的？UV 崩溃率和 PV 崩溃率有什么区别？业界通常用哪个？**

> 考察点：UV 崩溃率 = 崩溃设备数 / 启动设备数，PV 崩溃率 = 崩溃次数 / 启动次数。UV 更真实反映用户影响面。

**Q9：Bugly/Crashlytics 是如何做到在 App 崩溃后仍能上报日志的？进程都挂了为什么还能发网络请求？**

> 考察点：崩溃收集 SDK 的核心机制——`UncaughtExceptionHandler` 中做最小化上报（写入文件或直接发送），Native 层通过信号处理函数在崩溃线程执行；下次冷启动补报。

---

## 二、标准答案与崩溃分类

### 2.1 崩溃分类全景图

```
Android 崩溃
├── Java 层崩溃
│   ├── 未捕获异常（Uncaught Exception）
│   │   ├── NullPointerException
│   │   ├── ClassCastException
│   │   ├── IndexOutOfBoundsException
│   │   ├── IllegalStateException
│   │   ├── ConcurrentModificationException
│   │   └── NumberFormatException
│   ├── Error 类
│   │   ├── OutOfMemoryError           ← Java Heap 不足
│   │   ├── StackOverflowError         ← 递归过深
│   │   └── NoClassDefFoundError       ← 类加载失败
│   └── 系统 Kill
│       ├── ANR → 系统发送 SIGQUIT
│       └── Low Memory Killer (LMK)
│
├── Native 层崩溃
│   ├── 信号崩溃（Signal Crash）
│   │   ├── SIGSEGV (11)  ← 段错误，空指针/野指针/内存越界
│   │   ├── SIGABRT (6)   ← abort() 调用，art 内部 check failed
│   │   ├── SIGBUS (7)    ← 总线错误，未对齐访问/mmap 失败
│   │   ├── SIGFPE (8)    ← 除零或整数溢出
│   │   ├── SIGILL (4)    ← 非法指令
│   │   └── SIGTRAP (5)   ← 断点/调试陷阱
│   ├── 超时崩溃
│   │   ├── ANR → system_server 发送 SIGQUIT
│   │   └── Watchdog 超时
│   └── OOM 相关 Native 崩溃
│       ├── pthread_create 失败 (线程数超限)
│       ├── FD 超过上限 (open/mmap/socket 失败)
│       └── 虚拟内存耗尽 (/proc/pid/maps 地址空间不足)
│
└── 第三方 SDK 崩溃
    ├── WebView 内部崩溃
    ├── 音视频编解码库崩溃
    └── 广告/地图 SDK 内部异常
```

### 2.2 Java 崩溃标准排查流程

**以 NPE 为例：**

1. **定位崩溃行号**：堆栈第一行 `at com.xxx.MyClass.method(MyClass.java:123)` — 注意混淆后需 mapping 还原；
2. **分析代码上下文**：该行哪个对象可能为 null？是方法返回值、全局变量、还是参数传入？
3. **推断触发场景**：
   - 异步回调中 Activity 已销毁 → `getString()` NPE；
   - `Integer` 自动拆箱 → `null.intValue()` 抛出 NPE（堆栈中会显示在 `Integer.intValue` 行）；
   - 集合操作 → `HashMap.get()` 返回 null 后直接使用；
4. **复现与修复**：补充 null 判断、使用 `@Nullable`/`@NonNull` 注解、采用 Kotlin 的空安全类型。

### 2.3 Native 崩溃标准答案

**核心原理**：Native 代码崩溃时，Linux 内核向进程发送对应的信号（如 SIGSEGV）。Android 的 `debuggerd` 守护进程捕获该信号，将崩溃线程的寄存器状态、调用栈（backtrace）、内存映射等信息写入 `/data/tombstones/tombstone_XX` 文件，同时通过 `logcat` 输出简要信息。

**符号化流程**：
```
tombstone 中的地址（如 #00 pc 0000abcd  libnative.so）
        │
        ▼
计算偏移量：实际地址 - .so 基址 = 相对偏移
        │
        ▼
addr2line -f -e libnative.so（带符号表） 0000abcd
        │ 或者
ndk-stack -sym obj/local/arm64-v8a/ -dump tombstone.txt
        │
        ▼
得到：函数名 + 源文件:行号
```

### 2.4 OOM 三种类型及排查

| 类型 | 关键 Message | 本质原因 | 排查工具/指标 |
|------|-------------|----------|--------------|
| **Java Heap OOM** | `java.lang.OutOfMemoryError: Java heap space` | Dalvik/ART 堆内存超过上限 | `dumpsys meminfo`、Android Profiler、`Runtime.getRuntime().maxMemory()` |
| **线程 OOM** | `java.lang.OutOfMemoryError: pthread_create (1040KB stack) failed` | 进程内线程数达到上限（通常 ~500-1000） | `/proc/pid/status` 查看 `Threads:` 字段 |
| **FD 耗尽 OOM** | `java.lang.OutOfMemoryError: Could not allocate JNI Env` 或 `Too many open files` | 文件描述符达到上限（Android 通常 1024） | `/proc/pid/fd/` 目录数量、`/proc/pid/limits` 查看 `Max open files` |

---

## 三、核心原理深度解析

### 3.1 Java 崩溃处理链

Android App 主线程的崩溃处理链分为多层：

```
App 层异常发生
        │
        ▼
[1] 当前线程的 UncaughtExceptionHandler
        Thread.getUncaughtExceptionHandler()
        默认为 null，除非显式设置
        │
        ▼ (该线程未设置 handler)
[2] 当前线程 ThreadGroup 的 uncaughtException()
        ThreadGroup.uncaughtException(t, e)
        │
        ▼ (ThreadGroup 未重写)
[3] 全局默认 Handler
        Thread.getDefaultUncaughtExceptionHandler()
        如果有多个 SDK 设置，通常采用"保存前一个"的链式模式
        │
        ▼
[4] RuntimeInit.KillApplicationHandler（系统设置）
        RuntimeInit$KillApplicationHandler.uncaughtException()
        │
        ├──▶ Process.killProcess(Process.myPid())  // 杀死进程
        └──▶ System.exit(10)                        // 退出 JVM
```

### 3.2 Native 崩溃信号处理流程

```
Native 代码非法操作（空指针解引用、非法内存访问等）
        │
        ▼
Linux 内核 → 生成信号（SIGSEGV/SIGABRT/SIGBUS...）
        │
        ├──▶ 优先：本进程注册的信号处理器
        │    signal() / sigaction() 注册的 handler
        │    崩溃 SDK（Bugly/Crashlytics）会在这里注册自己的 handler
        │    通常做法：先保存原始 handler，在自己的 handler 中收集信息后，再调用原始 handler
        │
        ▼
debuggerd 守护进程介入
        │
        ├── [1] 接收信号
        │    debuggerd 作为系统的崩溃处理守护进程，通过 /dev/socket/debuggerd 监听
        │
        ├── [2] 暂停进程
        │    ptrace(PTRACE_ATTACH) 附加到崩溃进程，暂停所有线程
        │
        ├── [3] 收集信息
        │    ├── 读取 /proc/pid/maps → 内存映射（各 .so 段的基址）
        │    ├── ptrace(PTRACE_GETREGS) → CPU 寄存器状态
        │    ├── 根据 PC 寄存器和 FP 寄存器回溯调用栈 (unwind)
        │    ├── 读取 /proc/pid/cmdline → 进程命令行
        │    └── 读取接近崩溃地址的内存内容（附近内存 dump）
        │
        ├── [4] 生成 tombstone
        │    写入 /data/tombstones/tombstone_XX
        │    格式包含：
        │    - Build fingerprint
        │    - 崩溃信号和代码
        │    - 寄存器 dump
        │    - 各线程 backtrace
        │    - 内存映射
        │    - logcat 日志快照
        │
        └── [5] 恢复或终止
             SIGABRT → 发送 SIGKILL 终止进程
             其他信号 → 可选择恢复执行（通常也会终止）
```

### 3.3 OOM 底层机制

**Java Heap OOM**：
- `dalvik.vm.heapgrowthlimit`：标准应用堆上限（如 192MB/256MB/384MB，因设备而异）
- `dalvik.vm.heapsize`：在 AndroidManifest 中声明 `android:largeHeap="true"` 后的上限
- ART/Dalvik 在执行分配请求时，若 GC 后仍无法释放足够内存，则抛出 OOM

**线程数限制**：
- 每个线程默认栈大小约 1MB（`pthread_create` 默认）
- `/proc/sys/kernel/threads-max` 系统全局上限
- 进程实际可达线程数 ≈ 虚拟地址空间剩余 / 线程栈大小
- 32 位进程虚拟地址空间仅 ~3GB，更容易触发线程 OOM

**FD 限制**：
- `ulimit -n` 默认 1024，每个进程最多打开 1024 个文件描述符
- 常见泄漏场景：未关闭的 Cursor/InputStream/Socket/HandlerThread
- 耗尽后 `open()`/`socket()`/`pipe()` 全部失败，JNI 创建失败时抛 OOM

---

## 四、流程图

### 4.1 Java 崩溃处理链

```
┌──────────────────────────────────────────────────────────┐
│                    Java 崩溃处理全链路                      │
└──────────────────────────────────────────────────────────┘

  App 内 throw new NullPointerException()
             │
             ▼
  ┌──────────────────────────┐
  │ JVM 查找异常处理器        │
  │ 沿调用栈向上 unwind       │
  └──────────────────────────┘
             │
             ├─── 有 catch 块 ───▶ 正常捕获处理，不触发崩溃
             │
             └─── 无 catch 块 ───▶ "未捕获异常"
                                       │
                                       ▼
             ┌─────────────────────────────────────────────┐
             │ ① thread.getUncaughtExceptionHandler()      │
             │    每个线程可设置独立的 handler（默认为 null）  │
             └────────────────┬────────────────────────────┘
                              │ null → 进入下一层
                              ▼
             ┌─────────────────────────────────────────────┐
             │ ② ThreadGroup.uncaughtException(t, e)       │
             │    ThreadGroup 默认实现：                     │
             │    如果 parent != null → 委托给 parent       │
             │    否则 → 进入全局默认 handler                 │
             └────────────────┬────────────────────────────┘
                              │
                              ▼
             ┌─────────────────────────────────────────────┐
             │ ③ Thread.getDefaultUncaughtExceptionHandler │
             │    Bugly/Crashlytics SDK 在此层注册          │
             │    链式模式：保存旧的 → 执行自己的 → 交还旧的  │
             └────────────────┬────────────────────────────┘
                              │
                              ▼
             ┌─────────────────────────────────────────────┐
             │ ④ RuntimeInit$KillApplicationHandler        │
             │    ActivityThread.main() 中设置              │
             │    最终兜底：Process.killProcess() + exit(10)│
             └─────────────────────────────────────────────┘
```

### 4.2 Native 崩溃信号处理与 tombstone 生成

```
┌─────────────────────────────────────────────────────────────────┐
│                 Native 崩溃 → tombstone 全流程                    │
└─────────────────────────────────────────────────────────────────┘

  [Native 代码执行]
        │
        │  非法内存访问 / 空指针解引用 / 除零
        ▼
  ┌──────────────────────┐
  │  CPU 触发硬件异常      │
  │  → Linux Kernel       │
  │  发送对应 Signal       │
  └──────────┬───────────┘
             │
             ▼
  ┌─────────────────────────────────────────────────┐
  │  信号分发 (Kernel → 目标进程)                     │
  │                                                 │
  │  ┌──────────────┐     ┌──────────────────────┐  │
  │  │ sigaction()  │ OR  │ 默认行为 (SIG_DFL)    │  │
  │  │ 用户态 handler│     │ → coredump + 退出    │  │
  │  └──────┬───────┘     └──────────────────────┘  │
  └─────────┼───────────────────────────────────────┘
            │
            ▼
  ┌──────────────────────────────────────────────────┐
  │  crash SDK signal handler (用户态)                │
  │  ┌─────────────────────────────────────────────┐ │
  │  │ 1. 收集堆栈（libunwind / __builtin_return）  │ │
  │  │ 2. 写入 crash log 到磁盘                     │ │
  │  │ 3. 调用旧的 signal handler（链式调用）        │ │
  │  └─────────────────────────────────────────────┘ │
  └──────────────────┬───────────────────────────────┘
                     │
                     ▼
  ┌──────────────────────────────────────────────────┐
  │  debuggerd 守护进程介入                           │
  │  ┌─────────────────────────────────────────────┐ │
  │  │ socket: /dev/socket/debuggerd               │ │
  │  └─────────────────────────────────────────────┘ │
  │                                                 │
  │  debuggerd 收到通知 → ptrace attach 崩溃进程      │
  │                                                 │
  │  ┌─────────────────────────────────────────────┐ │
  │  │ Step 1: ptrace(PTRACE_ATTACH, pid)          │ │
  │  │ Step 2: 读取 /proc/pid/maps → 内存布局       │ │
  │  │ Step 3: ptrace(PTRACE_GETREGS) → 寄存器     │ │
  │  │ Step 4: unwind 回溯                         │ │
  │  │   - 32位: ARM 标准帧指针回溯                 │ │
  │  │   - 64位: ARM64 或 .eh_frame/.debug_frame   │ │
  │  │ Step 5: 读取 /proc/pid/cmdline, status...   │ │
  │  └─────────────────────────────────────────────┘ │
  └──────────────────┬───────────────────────────────┘
                     │
                     ▼
  ┌──────────────────────────────────────────────────┐
  │  生成 tombstone 文件                              │
  │  /data/tombstones/tombstone_XX                   │
  │                                                 │
  │  ┌─────────────────────────────────────────────┐ │
  │  │ *** *** *** *** *** *** *** *** *** *** *** │ │
  │  │ Build fingerprint: 'Xiaomi/...'             │ │
  │  │ Revision: '0'                               │ │
  │  │ ABI: 'arm64'                                │ │
  │  │ Timestamp: 2024-05-08 10:30:15              │ │
  │  │ pid: 12345, tid: 12346 >>> com.example <<<  │ │
  │  │ signal 11 (SIGSEGV), code 1 (SEGV_MAPERR)  │ │
  │  │     x0  x1  x2  x3 ... (寄存器 dump)        │ │
  │  │ backtrace:                                  │ │
  │  │     #00 pc 0000abcd  libnative.so           │ │
  │  │     #01 pc 0000ef01  libnative.so           │ │
  │  │     #02 pc 00012345  libart.so              │ │
  │  │ ...                                         │ │
  │  └─────────────────────────────────────────────┘ │
  └──────────────────────────────────────────────────┘
```

---

## 五、源码分析

### 5.1 RuntimeInit 的 KillApplicationHandler

源码位置：`frameworks/base/core/java/com/android/internal/os/RuntimeInit.java`

```java
// Android 系统源码关键逻辑（简化版）
public class RuntimeInit {

    // 这就是最终兜底的崩溃处理器
    private static class KillApplicationHandler
            implements Thread.UncaughtExceptionHandler {

        @Override
        public void uncaughtException(Thread t, Throwable e) {
            try {
                // 确保只处理一次，防止递归崩溃导致死循环
                if (mCrashing) return;
                mCrashing = true;

                // 1. 将崩溃信息写入 logcat
                // 使用 ActivityManager 的 ProcessRecord 上报
                if (ActivityThread.currentApplication() != null) {
                    Log.e(TAG, "FATAL EXCEPTION: " + t.getName(), e);
                    // 2. 通知 ActivityManagerService (AMS)
                    //    AMS 收到后会弹出 App Not Responding 对话框
                    ActivityThread.currentApplication().dispatchOnUnexpectedError(e);
                } else {
                    // 系统进程崩溃，直接输出到 System.err
                    e.printStackTrace();
                }
            } catch (Throwable ignored) {
                // 如果上报过程又崩溃了，直接忽略
            } finally {
                // 3. 无论如何都要杀死进程，保证崩溃 App 被及时清理
                Process.killProcess(Process.myPid());
                System.exit(10); // 10 是 Android 约定的崩溃退出码
            }
        }
    }

    // ActivityThread.main() 中调用
    public static final void main(String[] argv) {
        // ...
        // 设置兜底崩溃处理器
        Thread.setDefaultUncaughtExceptionHandler(
            new KillApplicationHandler()
        );
        // ...
    }
}
```

**设计要点**：
- `mCrashing` 标记防止递归：如果 KillApplicationHandler 自身在处理过程中又抛出异常（如 Log 写入失败），不会陷入无限循环；
- `dispatchOnUnexpectedError` 通知 AMS：AMS 记录崩溃日志，后续可能触发 ANR 对话框或自动重启；
- `Process.killProcess` + `System.exit(10)` 双保险：确保进程一定被终止；
- 退出码 10：Android 特有，区别于正常退出（0）和 ANR（exit(?)），方便问题分类。

### 5.2 debuggerd 的 tombstone 生成

源码位置：`system/core/debuggerd/`

```cpp
// debuggerd 核心处理逻辑（简化版）
// 文件：system/core/debuggerd/debuggerd_handler.cpp

static void debuggerd_signal_handler(int signal_number, siginfo_t* info, void* context) {
    // 1. 防止同一线程递归进入信号处理
    //    (如信号处理函数内部又访问了非法地址)
    if (pthread_getspecific(crash_dump_started_key)) {
        return; // 递归崩溃，放弃处理
    }

    // 2. 通过 socket 向 debuggerd daemon 发送崩溃信息
    //    fd 会预创建并缓存，因为崩在信号处理函数中不能执行复杂操作
    int fd = get_pseudothread_fd();

    // 3. 构造调试请求
    debugger_msg_t msg;
    msg.action = DEBUGGER_ACTION_CRASH;
    msg.tid = gettid();
    msg.abort_msg = get_abort_message(); // 读取 .note.android.ident section

    // 4. 发送请求到 debuggerd daemon
    send_fd(fd, &msg, sizeof(msg));

    // 5. debuggerd daemon 收到后:
    //    - ptrace(PTRACE_ATTACH, target_pid)
    //    - 读取 /proc/pid/maps 获取各 so 加载基址
    //    - ptrace(PTRACE_GETREGS) 读取 CPU 寄存器
    //    - unwind 获取调用栈
    //    - 生成 tombstone 文件
    //    - 通过 logcat 输出简要信息

    // 6. 等待 daemon 完成（同步等待，防止进程提前退出）
    read(fd, &response, sizeof(response));

    // 7. 恢复默认信号处理并重新发送信号
    //    让进程按照默认行为终止
    signal(signal_number, SIG_DFL);
    raise(signal_number);
}

// debuggerd daemon 端 - tombstone 写入
// 文件：system/core/debuggerd/tombstone.cpp
void engrave_tombstone(int tombstone_fd, const Tombstone& tombstone) {
    dprintf(tombstone_fd, "*** *** *** *** *** *** *** *** *** *** *** *** *** *** *** ***\n");
    dprintf(tombstone_fd, "Build fingerprint: '%s'\n", tombstone.build_fingerprint.c_str());
    dprintf(tombstone_fd, "ABI: '%s'\n", tombstone.abi.c_str());
    dprintf(tombstone_fd, "pid: %d, tid: %d, name: %s  >>> %s <<<\n",
            tombstone.pid, tombstone.tid,
            tombstone.thread_name.c_str(), tombstone.process_name.c_str());
    dprintf(tombstone_fd, "signal %d (%s), code %d (%s)\n",
            tombstone.signal, get_signame(tombstone.signal).c_str(),
            tombstone.si_code, get_sigcode(tombstone.signal, tombstone.si_code).c_str());

    // 输出寄存器内容
    dump_registers(tombstone_fd, tombstone.regs);

    // 输出每个线程的 backtrace
    for (const auto& thread : tombstone.threads) {
        dump_backtrace(tombstone_fd, thread);
    }

    // 输出内存映射
    dump_memory_map(tombstone_fd, tombstone.maps);
}
```

**关键设计**：
- `get_pseudothread_fd()` 预创建 socket：信号处理函数中不能分配内存或创建新 fd，所以 socket 必须预先创建好；
- `pthread_getspecific` 检测递归：避免信号处理函数自身崩溃导致无限递归（这会导致 kernel panic 的风险）；
- 同步等待 daemon 完成：通过 `read(fd)` 阻塞，确保 tombstone 完整写入后再允许进程退出；
- Build fingerprint：用于匹配对应版本的带符号表 .so 文件，实现精确符号化。

---

## 六、应用场景：Native 崩溃完整排查实战

### 场景描述

线上监控收到一条崩溃：

```
*** *** *** *** *** *** *** *** *** *** *** *** *** *** *** ***
Build fingerprint: 'google/sunfish/sunfish:12/SP1A.210812/7671067:user/release-keys'
ABI: 'arm64'
pid: 28734, tid: 28912, name: GLThread  >>> com.example.openglapp <<<
signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x0000000000000010
    x0  0000007123456789  x1  0000000000000000  x2  00000070abcdef01
    x3  0000000000000000  x4  0000000000000001  ...

backtrace:
    #00 pc 000000000012abcd  /data/app/~~xxx==/com.example.openglapp-xxx==/lib/arm64/libnativegl.so
    #01 pc 0000000000112233  /data/app/~~xxx==/com.example.openglapp-xxx==/lib/arm64/libnativegl.so
    #02 pc 0000000000345678  /system/lib64/libGLESv2.so
    #03 pc 0000000000234567  /system/lib64/libhwui.so
```

### 排查步骤

#### Step 1：获取带符号表的 .so

```bash
# 构建 App 时生成的带符号 .so 位于
# app/build/intermediates/cmake/release/obj/arm64-v8a/libnativegl.so

# 或者从 APK 中提取（需要保留 mapping + 符号表）
unzip app-release.apk -d apk_extract/
# 注意：APK 中的 .so 可能已被 strip，需要找到未 strip 的版本
```

#### Step 2：方法一 —— 使用 addr2line 逐帧还原

```bash
# NDK 自带的 addr2line 工具
$NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-addr2line \
    -f -e libnativegl.so 0x12abcd

# 输出：
# gl_render_frame()
# /path/to/project/src/main/cpp/gl_renderer.cpp:156
```

```bash
# 第二帧
$NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-addr2line \
    -f -e libnativegl.so 0x112233

# 输出：
# gl_draw_scene()
# /path/to/project/src/main/cpp/gl_renderer.cpp:89
```

#### Step 3：方法二 —— 使用 ndk-stack 批量还原（推荐）

```bash
# 将 tombstone 内容保存为 tombstone.txt
cat tombstone.txt | $NDK_HOME/ndk-stack \
    -sym app/build/intermediates/cmake/release/obj/arm64-v8a/ \
    -dump -

# 输出（已全部符号化）：
# ********** Crash dump: **********
# Build fingerprint: 'google/sunfish/sunfish:12/...'
# pid: 28734, tid: 28912, name: GLThread  >>> com.example.openglapp <<<
# signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x10
# Stack frame #00 pc 00012abcd  libnativegl.so:
#     Routine gl_render_frame in gl_renderer.cpp:156
# Stack frame #01 pc 000112233  libnativegl.so:
#     Routine gl_draw_scene in gl_renderer.cpp:89
```

#### Step 4：根据源码定位根因

还原后发现崩溃在 `gl_renderer.cpp:156`，查看源码：

```cpp
// gl_renderer.cpp 第 150-160 行
void gl_render_frame() {
    Scene* scene = get_current_scene();
    // 第 155 行
    glUseProgram(scene->shader_program);  // ← scene 可能为 nullptr!
    // 第 156 行：访问 scene->vertex_buffer 时 crash
    glBindBuffer(GL_ARRAY_BUFFER, scene->vertex_buffer);  // ← CRASH
    // ...
}
```

分析：
- `fault addr 0x0000000000000010` 是 `nullptr + offset(0x10)` 的典型特征，即 `scene` 为 null 时访问其成员 `vertex_buffer`（偏移 0x10）；
- `get_current_scene()` 在多线程场景下可能返回 null（Renderer 线程切换时还未初始化）；
- 修复：增加空指针校验，或在 Renderer 未就绪时跳过本帧渲染。

#### Step 5：使用 Android Studio 直接分析（最简单）

```
1. 打开 Android Studio → Analyze → Analyze Stacktrace
2. 粘贴 tombstone 中的 backtrace 部分
3. 确保项目已打开且符号表匹配
4. 点击 "OK"，AS 自动在源码中定位到崩溃行
```

### 完整排查清单总结

| 步骤 | 操作 | 工具 |
|------|------|------|
| 1 | 获取崩溃 tombstone / stacktrace | Bugly 后台 / logcat |
| 2 | 根据 Build fingerprint 找到匹配的符号表 .so | Gradle build output |
| 3 | 地址符号化 | `addr2line` / `ndk-stack` / AS Analyze Stacktrace |
| 4 | 根据源码定位根因并修复 | IDE + 代码审查 |
| 5 | 验证修复 → 灰度发布 → 全量 | 崩溃率监控 |

---

## 七、扩展知识

### 7.1 崩溃 SDK 的存活上报机制

- **运行时写入文件**：在 `uncaughtException()` 中，SDK 将崩溃堆栈序列化写入 App 私有目录（`files/crash_log/`），下次冷启动时读取并上报；
- **直接网络上报**：如果崩溃时网络可用，可以直接在信号处理函数中（Native）或 UEH 中（Java）发起一次轻量级 HTTP 请求。但风险很高——崩溃后的进程状态不稳定，可能二次崩溃；
- **mmap 缓冲区**：部分 SDK 使用 mmap 创建共享内存缓冲区，崩溃时只需写入内存（无需文件 I/O），下次启动时从 mmap 文件中恢复。

### 7.2 崩溃率定义与治理

```
UV 崩溃率 = 发生崩溃的设备数 / 启动 App 的设备数
PV 崩溃率 = 崩溃发生次数 / App 启动次数

业界标准：UV 崩溃率 ＜ 0.1% 为优秀，＜ 0.5% 为合格
```

- **为什么要区分 UV 和 PV**：同一台设备启动即崩可能产生大量 PV 崩溃，UV 能更真实反映用户影响面；
- **启动次数定义**：`onCreate` 被调用即计为一次启动（进程级别），非 Activity 级别；
- **崩溃治理阶梯**：解决 Top 1 崩溃（占总量 30-50%）→ 解决高频但不严重的崩溃 → 治理长尾崩溃。

### 7.3 ANR 与崩溃的区别

| 维度 | ANR | 崩溃 |
|------|-----|------|
| 本质 | 主线程超时未响应 | 未捕获异常/信号 |
| 触发方 | system_server 发送 SIGQUIT | JVM/Linux Kernel |
| 进程状态 | 进程存活（主线程阻塞） | 进程终止 |
| 收集方式 | `/data/anr/traces.txt` | `tombstone` + logcat |
| 是否可恢复 | 用户点"等待"可恢复 | 不可恢复，进程必死 |
| 根因常见原因 | 主线程 IO、死锁、耗时计算 | 空指针、内存越界、OOM |

---

> **总结**：崩溃分析是 Android 稳定性的基石。从 Java 层的 UncaughtExceptionHandler 链到 Native 层的 signal→debuggerd→tombstone 机制，再到 OOM 的多维度排查，掌握这套完整链路才能在面试和实际工作中游刃有余。记住：**符号化是桥梁，堆栈是地图，源码是终点。**
