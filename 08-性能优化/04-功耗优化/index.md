# Android 功耗优化 —— 面试深度指南

> 六层递进式学习：面试问题 → 标准答案 → 核心原理 → 流程图解 → 源码剖析 → 实战案例

---

## 层一：常见面试问题

### Q1: Android 功耗主要来自哪些硬件模块？各自耗电占比如何？
**考点：功耗类型认知 (CPU / WakeLock / 网络 / GPS / 屏幕)**

### Q2: 什么是 WakeLock？如果 acquire() 后忘记 release() 会造成什么后果？
**考点：WakeLock 原理与持锁不释放的危害**

### Q3: Doze 模式和 App Standby 分别是什么？对应用有什么限制？如何适配？
**考点：低电耗模式的进入条件、系统行为、适配策略**

### Q4: JobScheduler 和 WorkManager 在功耗优化中扮演什么角色？为什么比后台 Service 更省电？
**考点：延迟/合并调度、约束执行、Doze 兼容**

### Q5: 使用 Battery Historian 分析功耗时，关键指标有哪些？如何定位异常耗电？
**考点：耗电分析工具与核心指标解读**

### Q6: 后台定时任务如何省电？setExact() / set() / setAndAllowWhileIdle() 有什么区别？
**考点：精准闹钟 vs 模糊闹钟、Alarm 对齐与 Doze 适配**

---

## 层二：标准答案与要点解析

### Q1 标准答案：Android 五大功耗来源

| 功耗类型 | 典型占比 | 核心优化策略 |
|---------|---------|------------|
| **屏幕** | 40%-60% | 降低亮度、暗色主题、缩短超时、减少唤醒 |
| **CPU** | 15%-25% | 减少后台计算、降低频率、大小核调度优化 |
| **网络 Radio** | 10%-20% | 批量/延迟请求、减少心跳、RRC 状态感知 |
| **GPS / 传感器** | 5%-10% | Fused Location Provider、自适应频率、GeoFence |
| **WakeLock 持锁** | 不定(异常时极高) | 成对 acquire/release、超时锁、JobScheduler 替代 |

**关键数据补充：**
- 屏幕点亮一次(约 2s) ≈ 网络 Radio 维持 DCH 状态 30s 的电量
- GPS 冷启动定位一次 ≈ 3-5mA，网络定位 ≈ 0.5mA
- CPU 大核(A76/X2)满载 ≈ 500-800mW，小核(A55)满载 ≈ 80-150mW

### Q2 标准答案：WakeLock 原理与不释放的后果

**WakeLock 本质：**
- 应用通过 `PowerManager.WakeLock.acquire()` 向系统申请阻止 CPU(或屏幕)进入休眠
- 底层通过 `/sys/power/wake_lock` 写入内核 wakelock，阻止 Kernel 进入 suspend 状态
- 是一个**引用计数**机制：同一锁可多次 acquire，需等量 release

**不释放的后果（按严重程度递增）：**

1. **CPU 无法休眠(持 PARTIAL_WAKE_LOCK)**：手机即使在息屏后，CPU 仍保持唤醒。实测功耗从 5-10mA(深度休眠) 飙升至 50-150mA
2. **整夜耗电 30%-50%**：典型场景 —— 应用在后台持锁 8 小时，耗电约 400-1200mAh
3. **触发 Battery Historian 红色告警**：`wake_lock_in` 事件持续无对应的 `wake_lock_out`
4. **系统级后果**：可能导致 `SystemSuspend` 阻塞，影响整个设备的 Doze 进入

**答题要点（面试官想听的关键词）：**
> "引用计数、Kernel wakelock、阻止 CPU suspend、耗电数量级(mA)、BatHist 红色长条"

### Q3 标准答案：Doze 模式 & App Standby

**Doze 模式（Android 6.0+，API 23）：**

| 阶段 | 进入条件 | 系统行为 |
|------|---------|---------|
| **Stage 1 (Light Doze)** | 熄屏 + 静止 + 不充电 + 几分钟 | 网络访问暂停、WakeLock 忽略、Job/ Alarm 延迟到维护窗口 |
| **Stage 2 (Deep Doze)** | Light Doze + 持续更长时间 | 所有 Stage 1 限制 + Alarm 被限制为最多 1 次/15min、GPS 关闭 |
| **Maintenance Window** | 周期性短暂退出(几秒-30s) | 可执行 Job/Alarm/网络同步，窗口结束后立即回到 Doze |

**实测数据：进入 Deep Doze 后，整机功耗从 20-30mA 降至 3-5mA。**

**App Standby（Android 6.0+）：**
- 判定条件：应用**最近未与用户交互** + **没有前台进程** + **没有活跃通知**
- 系统行为：网络访问被限制(最松→最严 4 级)、Job 延迟、Alarm 频率受限
- 退出条件：用户手动启动应用 / 应用变为前台 / 收到高优先级 FCM 消息

**适配策略：**
1. 延时非紧急任务 → 使用 `JobScheduler` / `WorkManager`
2. 高优先级即时消息 → 使用**高优先级 FCM** (`priority: high`) 临时豁免 Doze
3. 闹钟类应用 → 使用 `setExactAndAllowWhileIdle()`
4. 避免使用 `AlarmManager.setExact()` + `WakeLock` 的旧模式

### Q4 标准答案：JobScheduler & WorkManager

**为什么比后台 Service 省电？**

| 对比维度 | 后台 Service | JobScheduler/WorkManager |
|---------|-------------|--------------------------|
| CPU 持有 | 持续运行，CPU 无法休眠 | 任务结束后释放 CPU，可休眠 |
| 网络请求 | 应用自行管理，易导致频繁唤醒 Radio | 系统级批量调度，合并网络请求 |
| Doze 适配 | 需自行处理 | 系统自动在 Maintenance Window 执行 |
| 约束感知 | 无 | 可设置网络类型/充电/空闲/存储/电池等约束 |
| 任务合并 | 不支持 | 支持任务链、周期性任务最小间隔 15min |

**WorkManager 省电量化：**
- 10 个应用各自 1 小时上传一次 → 若同时调度，Radio 唤醒 1 次 vs 10 次
- 一次 Cellular Radio 上电(DCH→FACH→IDLE) ≈ 20-30s tail time，功耗约 100-200mA
- 合并后省电比例：Radio 唤醒次数 / N 个应用

### Q5 标准答案：Battery Historian 关键指标

**核心分析流程：**

```
导出 bugreport → Battery Historian 可视化 → 定位异常耗电
```

| 关键指标 | 正常值 | 异常信号 |
|---------|-------|---------|
| **Device Idle Mode** | 深绿(Deep Doze)占比高 | 长时间处于 "Off" 状态 |
| **WakeLock** | 短促的蓝条，acquire 数秒内 release | 连续蓝色长条(小时级)，wake_lock_in 无对应 out |
| **CPU Running** | 与Job/WakeLock同步的窄脉冲 | 长时间的 CPU 运行与 Job 不匹配 |
| **Mobile Radio** | 窄条，与 Job/FCM 对应 | 持续活跃 / 高频率周期活跃 |
| **Battery Level** | 线性缓慢下降 | 陡峭下降段(每小时 >2-3%) |
| **Wifi / GPS** | 按需使用，运行时长短 | 长时间持续运行 |
| **Sync / Job** | 执行时间 < 5s | Job 时长 > 30s / 频繁调度 |
| **Top App** | 多为前台应用 | 后台应用占据 Top 位置 |

**定位公式：**
> **耗电大户 = Top App 柱状图 + WakeLock 长蓝条 + CPU Running 密集区 + 电池曲线陡坡**

### Q6 标准答案：Alarm 类型与省电策略

**AlarmManager 三种 TICK 模式比较：**

| 方法 | 精确度 | Doze 行为 | 适用场景 | 功耗影响 |
|------|-------|-----------|---------|---------|
| `setExact()` | **精准**，指定时间触发 | Doze 中**被推迟**到 Maintenance Window | 闹钟、日历提醒 | 高(阻止批量对齐) |
| `set()` | **模糊**，系统对齐批量触发 | Doze 中推迟 | 定期数据同步、缓存刷新 | 低(系统可对齐多个 App 的 Alarm) |
| `setAndAllowWhileIdle()` | **精准**，Doze 中也触发 | Doze 中允许(频率受限，1次/9min→15min) | 高优先级 FCM 兜底 | 中(破坏 Doze 休眠) |

**省电核心原则：**
1. **能用 `set()`（模糊）绝不用 `setExact()`** —— 系统会将多个临近 Alarm 对齐到同一时刻，减少 CPU 唤醒次数
2. **能用 `WorkManager` 周期任务绝不用 `AlarmManager` 周期** —— WorkManager 优先使用 JobScheduler，天然 Doze 兼容
3. **IM 心跳从 30s 精准 → 5min 自适应** —— 结合 FCM + 模糊 Alarm 兜底

---

## 层三：核心原理深度讲解

### 3.1 Android 电源管理框架：从 PowerManager 到 Kernel WakeLock

```
┌─────────────────────────────────────────────────┐
│  Application (Java/Kotlin)                       │
│  PowerManager.WakeLock.acquire(timeout)           │
└───────────────────┬─────────────────────────────┘
                    │ Binder IPC
┌───────────────────▼─────────────────────────────┐
│  System Server (PowerManagerService)              │
│  - 管理 WakeLock 引用计数                         │
│  - SuspendBlocker (Native 层)                    │
│  - 决策是否请求内核进入 suspend                   │
└───────────────────┬─────────────────────────────┘
                    │ JNI
┌───────────────────▼─────────────────────────────┐
│  Native Layer (com_android_server_power)          │
│  - acquire_wake_lock() → /sys/power/wake_lock    │
│  - release_wake_lock() → /sys/power/wake_unlock  │
└───────────────────┬─────────────────────────────┘
                    │ sysfs write
┌───────────────────▼─────────────────────────────┐
│  Linux Kernel (Power Management Subsystem)        │
│  - wakelock 机制                                  │
│  - wakeup source 框架                             │
│  - suspend/resume 决策                            │
│  - CPUFreq / CPUIdle 调控                         │
└─────────────────────────────────────────────────┘
```

**关键点：**
- `PowerManagerService` 维护所有应用的 WakeLock 列表，当所有锁释放后才允许 `autosuspend`
- 每个 WakeLock 对应一个 `SuspendBlocker`（Native 层），通过写入 `/sys/power/wake_lock` 创建内核 wakelock
- 内核 `wakeup_count` 机制防止 suspend 过程中产生的新事件丢失

### 3.2 WakeLock 类型详解

| WakeLock 类型 | Flag 值 | 屏幕 | 键盘 | CPU | 典型用途 |
|--------------|---------|------|------|-----|---------|
| `PARTIAL_WAKE_LOCK` | 0x00000001 | OFF | OFF | **ON** | 后台音乐播放、下载、IM心跳 |
| `FULL_WAKE_LOCK` (已废弃) | 0x0000001A | **ON** | **ON** | ON | (废弃，用 FLAG_KEEP_SCREEN_ON 替代) |
| `SCREEN_DIM_WAKE_LOCK` (已废弃) | 0x00000006 | DIM | ON | ON | (废弃) |
| `SCREEN_BRIGHT_WAKE_LOCK` (已废弃) | 0x0000000A | BRIGHT | ON | ON | (废弃) |
| `PROXIMITY_SCREEN_OFF_WAKE_LOCK` | 0x00000020 | 接近传感器控制 | — | ON | 电话通话中关闭屏幕 |

**最佳实践：**
- **只用 `PARTIAL_WAKE_LOCK`** —— 其他类型已在 API 17-20+ 废弃
- **始终使用 `acquire(timeout)` 代替无限 `acquire()`** —— 超时自动释放，防止应用 crash 后持锁
- **参考计数**：`acquire()` → `release()` 必须严格成对，用 `isHeld()` 防御

### 3.3 Doze 模式：状态机与系统行为

**进入条件（所有条件同时满足）：**
1. 设备**未充电**（USB/Wireless 均不可）
2. **屏幕关闭**（用户熄屏或超时熄屏）
3. 设备**静止不动**（加速度计/陀螺仪/Gyro 检测无运动）
4. 持续一段时间（Android 6: ~30min → Android 7+: ~数分钟即可进入 Light Doze）

**系统限制（Deep Doze 阶段）：**

| 被限制的功能 | 具体行为 |
|------------|---------|
| 网络访问 | 完全暂停，包括 Wi-Fi 和移动数据。唤醒广播的 `ConnectivityManager.CONNECTIVITY_ACTION` 不被发送 |
| WakeLock | **忽略** —— 即使应用持锁，系统仍然可以进入 suspend |
| Alarm | `setExact()` 推迟到 Maintenance Window；`setAndAllowWhileIdle()` 最多 1次/9min（API 23-25）或 1次/15min（API 26+） |
| JobScheduler | 推迟到 Maintenance Window 或下一个白名单窗口 |
| Sync Adapter | 推迟到 Maintenance Window |

**Doze 白名单（省电例外）：**
- 用户可在 设置 → 电池 → 电池优化 中手动添加
- 应用可通过 `ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS` 引导用户添加（Play Store 政策限制）
- 白名单应用：WakeLock 仍被忽略，但网络和 Alarm 限制放松

### 3.4 App Standby 判定规则（Android 6.0+）

**判定逻辑（所有条件需同时满足）：**

```
if (应用非前台 && 
    无前台Service && 
    无活跃Notification &&
    未被用户手动启动(近期) &&
    未通过省电白名单) {
    → 进入 App Standby
}
```

**四层限制递进（Android 9+ 更激进）：**

| 层级 | 触发条件 | 限制 |
|------|---------|------|
| **Active** | 用户使用中 | 无限制 |
| **Working Set** | 近期使用 / 有通知 | 基本无限制 |
| **Frequent** | 有一定使用频率 | Alarm 限速、网络延迟增加 |
| **Rare** | 极少使用 | Alarm 大幅限速、网络严重延迟 |
| **Restricted**（Android 12+） | 从未交互 | 几乎完全禁止后台工作 |

### 3.5 CPU 调度与功耗：big.LITTLE 架构

**大小核功耗差异（典型骁龙 888 数据）：**

| 核心类型 | 架构 | 频率范围 | 满载功耗(单核) | 能效比 |
|---------|------|---------|--------------|-------|
| Prime Core | Cortex-X1 | 2.84 GHz | ~1000mW | 低 |
| Big Core | Cortex-A78 ×3 | 2.42 GHz | ~500mW/核 | 中 |
| Little Core | Cortex-A55 ×4 | 1.80 GHz | ~80-120mW/核 | **高** |

**Governor 策略对功耗的影响：**
- `performance`：所有核满频运行 → 功耗极高，仅用于基准测试
- `schedutil`（默认）：负载驱动，感知 EAS（Energy Aware Scheduling）→ 优先用小核，大核仅在需要时上线
- `ondemand` / `interactive`（旧版）：响应式升频，不如 schedutil 高效
- EAS（Energy Aware Scheduling）通过**能耗模型**决定任务分配到哪个核心

**省电关键策略：**
- 后台任务尽量跑在小核上 → `Process.setThreadPriority(Process.THREAD_PRIORITY_BACKGROUND)`
- 避免高频周期唤醒 CPU → 合并任务使用 JobScheduler
- 使用 `sched_boost` 关闭不必要的 CPU Boost

### 3.6 网络耗电模型：RRC 状态机

蜂窝网络的功耗不是线性的——Radio 有一个 **tail time**（尾延时）。

**RRC（Radio Resource Control）三态模型（4G LTE）：**

```
    数据活跃期
  ┌──────────────┐
  │              ▼
DCH (专用信道) ──────► FACH (共享) ──► IDLE (休眠)
500-800mW            200-300mW       5-10mW
 ▲        | 无数据    ▲      |
 │        | 5-10s     │      | 8-12s
 │        ▼           │      ▼
 │    (tail timer)    │  (tail timer)
 │                    │
 └────── 发送数据时升级到 DCH ──────────┘
```

**典型一次 HTTP 请求的功耗分解（总耗时 15s，数据传输 0.5s）：**

| 阶段 | 耗时 | 功耗 | 耗电 |
|------|------|------|------|
| IDLE→DCH 建立 | 100ms | 800mW | ~0.02mWh |
| 数据传输(DCH) | 500ms | 800mW | ~0.11mWh |
| **DCH Tail** | **10s** | **500mW** | **~1.39mWh** ⚠️ |
| FACH Tail | 8s | 250mW | ~0.56mWh |
| IDLE | — | 8mW | — |

**核心结论：**
> **Tail time 耗电远超实际数据传输！** 一次 0.5s 的 HTTP 请求，实际 Radio 活跃 15-20s，78% 的耗电发生在 tail 阶段。

**优化策略（基于 RRC 状态机）：**
1. **批量发送 / 预取合并**：1 次发 10KB 比 10 次各发 1KB 省电 80%+
2. **Prefetch 策略**：在 DCH 活跃期趁 tail 还在，预取未来可能用的数据
3. **避免短周期心跳**：30s 心跳 → Radio 几乎持续 DCH，耗电如流水

---

## 层四：原理流程图（Mermaid.js）

### 4.1 Android 电源管理状态机

<div class="mermaid">
stateDiagram-v2
    [*] --> Normal: 设备使用中
    Normal --> LightDoze: 熄屏 + 静止 + 不充电 + 数分钟
    LightDoze --> DeepDoze: LightDoze持续+无用户交互+更长时间
    LightDoze --> Normal: 屏幕亮/运动/充电/闹钟
    DeepDoze --> MaintenanceWindow: 周期性窗口(15min)
    MaintenanceWindow --> DeepDoze: 窗口结束(数秒)
    MaintenanceWindow --> Normal: 用户唤醒/充电
    DeepDoze --> Normal: 屏幕亮/运动/充电

    note right of LightDoze
        网络暂停
        WakeLock忽略
        Alarm延迟
    end note

    note right of DeepDoze
        网络完全暂停
        Alarm ≤1次/15min
        GPS关闭
        Job调度暂停
    end note

    note right of MaintenanceWindow
        CPU唤醒(数秒)
        执行积压Job
        网络恢复
        Alarm触发
    end note
</div>

### 4.2 RRC 网络状态机功耗模型

<div class="mermaid">
stateDiagram-v2
    [*] --> IDLE: 无数据传输
    IDLE --> DCH: 发送/接收数据
    DCH --> DCH: 持续传输中
    DCH --> FACH: Tail Timer到期(无数据5-10s)
    FACH --> IDLE: Tail Timer到期(无数据8-12s)
    FACH --> DCH: 新数据传输
    IDLE --> IDLE: 功耗: 5-10mW

    note right of DCH
        功耗: 500-800mW
        带宽: 最高
        延迟: 最低
    end note

    note right of FACH
        功耗: 200-300mW
        带宽: 共享信道
    end note

    note right of IDLE
        功耗: 5-10mW
        仅监听寻呼
    end note
</div>

### 4.3 Battery Historian 分析流程

<div class="mermaid">
flowchart TD
    A[导出 bugreport] --> B[battery-historian 解析]
    B --> C{查看 System Stats 标签}

    C --> D1[Device Idle Mode 占比]
    C --> D2[WakeLock 时间线]
    C --> D3[CPU Running 区域]
    C --> D4[Top App 柱状图]
    C --> D5[Battery Level 曲线]
    C --> D6[Mobile Radio 时间线]

    D1 --> E1{Doze占比 < 50%?}
    E1 -- 是 --> F1[检查WakeLock长条]

    D2 --> E2{连续WakeLock > 1min?}
    E2 -- 是 --> F1[定位对应UID应用]

    D3 --> E3{CPU频繁唤醒?}
    E3 -- 是 --> F2[检查Alarm/Job频率]

    D4 --> E4{后台App在Top?}
    E4 -- 是 --> F3[检查后台行为]

    F1 --> G[输出报告: 列出异常应用UID+耗电占比+建议]
    F2 --> G
    F3 --> G
</div>

---

## 层五：核心源码分析

### 5.1 PowerManager.WakeLock.acquire() 调用链

**源码路径：**
```
frameworks/base/core/java/android/os/PowerManager.java          # WakeLock 定义
frameworks/base/services/core/java/com/android/server/power/    # PowerManagerService
  ├── PowerManagerService.java                                  # 核心服务
  └── Notifier.java                                             # 通知/亮度
```

**关键源码（基于 AOSP 12，行号近似）：**

```java
// PowerManager.java (L1250+)
public WakeLock newWakeLock(int levelAndFlags, String tag) {
    validateWakeLockParameters(levelAndFlags, tag);
    return new WakeLock(levelAndFlags, tag, ...);
}

// WakeLock.acquire() (L900+)
public void acquire(long timeout) {
    synchronized (mToken) {
        acquireLocked(timeout);  // 内部调用
    }
}

private void acquireLocked(long timeout) {
    mInternalCount++;            // 引用计数+1
    mExternalCount++;
    if (!mRefCounted || mInternalCount == 1) {
        // 首次 acquire：通知 PowerManagerService
        mHandler.removeCallbacks(mReleaser);
        try {
            mService.acquireWakeLock(mToken, mFlags, mTag,   // Binder IPC → PMS
                                     mPackageName, mWorkSource, mHistoryTag);
        } catch (RemoteException e) { ... }
        mHeld = true;
    }
    if (timeout > 0) {
        mHandler.postDelayed(mReleaser, timeout);  // 超时自动释放
    }
}
```

```java
// PowerManagerService.java (L3500+)
// acquireWakeLock() → acquireWakeLockInternal()
private void acquireWakeLockInternal(IBinder lock, int flags, String tag,
                                      String packageName, WorkSource ws, ...) {
    synchronized (mLock) {
        WakeLock wakeLock = mWakeLocks.get(lock);
        if (wakeLock == null) {
            wakeLock = new WakeLock(lock, flags, tag, ...);
            mWakeLocks.put(lock, wakeLock);
        }
        wakeLock.mWorkSource.add(ws);
        wakeLock.mActiveSince = SystemClock.uptimeMillis();
        mWakeLockSum += 1;  // 全局计数
        
        // 关键：通知 Native SuspendBlocker
        setWakeLockDisabledStateLocked(wakeLock);
        updatePowerStateLocked();  // 重新评估是否需要 suspend
    }
}

// updatePowerStateLocked() → updateSuspendBlockerLocked()
private void updateSuspendBlockerLocked() {
    // 如果任何 PARTIAL_WAKE_LOCK 被持有 → 阻止 suspend
    boolean needSuspendBlocker = (mWakeLockSummary & WAKE_LOCK_CPU) != 0;
    if (needSuspendBlocker && !mHoldingWakeLockSuspendBlocker) {
        mWakeLockSuspendBlocker.acquire();  // → JNI → /sys/power/wake_lock
    }
    if (!needSuspendBlocker && mHoldingWakeLockSuspendBlocker) {
        mWakeLockSuspendBlocker.release();  // → JNI → /sys/power/wake_unlock
    }
}
```

**关键设计要点：**
- **L900-924**：引用计数机制 + 超时自动释放
- **L3520+**：PMS 维护 WakeLock 列表，任何持锁阻止整个系统进入 suspend
- **updateSuspendBlockerLocked()**：决策点，其输出直连内核 wakelock

### 5.2 JobScheduler / JobService 调度源码

**源码路径：**
```
frameworks/base/services/core/java/com/android/server/job/
  ├── JobSchedulerService.java       # 核心调度服务
  ├── JobServiceContext.java         # Job 执行上下文
  └── controllers/                    # 各种约束控制器
      ├── BatteryController.java      # 电池约束
      ├── IdleController.java         # 空闲/Doze 约束
      └── ConnectivityController.java # 网络约束
```

**核心调度逻辑（JobSchedulerService.java，L2000+）：**

```java
// 周期性 Job 的最小间隔限制
static final int MIN_PERIOD = 15 * 60 * 1000;  // 15分钟
static final int MIN_FLEX = 5 * 60 * 1000;     // 最少5分钟弹性

// 判断 Job 是否就绪
private boolean isReadyToBeExecutedLocked(JobStatus job) {
    // 1. 检查时间约束
    if (!job.isReady()) return false;
    
    // 2. 检查 Doze 状态
    if (mDeviceIdleJobs && mDeviceIdleMode) {
        // Doze 期间只允许白名单 Job
        if (!job.isExemptedFromAppStandby()) return false;
    }
    
    // 3. 检查网络约束
    if (job.hasConnectivityConstraint() && !mConnectivityController.isSatisfied(job)) 
        return false;
    
    // 4. 检查电池约束
    if (job.hasBatteryNotLowConstraint() && mBatteryController.isBatteryLow())
        return false;
    
    // 5. 检查空闲约束
    if (job.hasIdleConstraint() && !mIdleController.isDeviceIdle())
        return false;
    
    return true;
}

// Maintenance Window 期间的批量执行
void onDeviceIdleModeChanged() {
    synchronized (mLock) {
        // Doze 进入后暂停所有普通 Job
        // 到达 Maintenance Window 时批量唤醒
        if (mDeviceIdleMode) {
            cancelAllNonExemptJobs();
        } else {
            // 退出 Doze → 批量调度积压 Job
            maybeQueueReadyJobsForExecutionLocked();
        }
    }
}
```

**与 WorkManager 的关系：**
- `WorkManager` 内部优先使用 `JobScheduler`（API 23+），兜底用 `AlarmManager` + `BroadcastReceiver`
- `WorkManager 2.7+` 支持 `Expedited Work`（Android 12 的前台服务快速路径）

### 5.3 AlarmManager 三种 set 方法的行为差异

**源码路径：**
```
frameworks/base/core/java/android/app/AlarmManager.java
frameworks/base/services/core/java/com/android/server/AlarmManagerService.java
```

**关键源码（AlarmManagerService.java，L800+）：**

```java
// ======== setExact() ========
// 精准闹钟，Doze 中被推迟
public void setExact(int type, long triggerAtMillis, PendingIntent operation) {
    setImpl(type, triggerAtMillis, WINDOW_EXACT, 0, 0, operation, 
            null, null, 0, null, null, callingPid, callingUid);
}

// ======== set() ========
// 模糊闹钟，WINDOW_EXACT 标志允许系统对齐
// 系统会将同一时段内多个 App 的 Alarm 对齐到同一时刻
public void set(int type, long triggerAtMillis, PendingIntent operation) {
    setImpl(type, triggerAtMillis, WINDOW_HEURISTIC, 0, 0, operation, ...);
}

// ======== setAndAllowWhileIdle() ========
// Doze 中也允许触发，但有频率限制
// API 26+: 最小间隔 15分钟   API 23-25: 最小间隔 9分钟
static final int MIN_INTERVAL_ALLOW_WHILE_IDLE = 9 * 60 * 1000; // 9min (API<26)

public void setAndAllowWhileIdle(int type, long triggerAtMillis, 
                                  PendingIntent operation) {
    setImpl(type, triggerAtMillis, WINDOW_EXACT, 
            ALLOW_WHILE_IDLE,        // ← Doze 豁免标志
            0, operation, ...);
}

// ======== 内部实现判断 Doze 行为 ========
private void setImpl(..., int flags) {
    final boolean allowWhileIdle = (flags & ALLOW_WHILE_IDLE) != 0;
    
    synchronized (mLock) {
        // 关键判断：Doze 期间是否允许此 Alarm
        if (!allowWhileIdle && mDeviceIdleUserWhitelistOnly) {
            // Doze 中且非白名单 → 延迟到下一个 Maintenance Window
            mPendingIdleUntil = mNextWakeFromIdle;
            // 推迟执行
        }
        
        // 频率限制（即使 allowWhileIdle = true）
        if (allowWhileIdle) {
            long minInterval = mAllowWhileIdleMinInterval; // 9min or 15min
            if (triggerAtMillis - lastTrigger < minInterval) {
                // 过于频繁 → 强制延迟
                triggerAtMillis = lastTrigger + minInterval;
            }
        }
    }
}
```

**三种方法行为总结表：**

| 方法 | 精准 | Doze行为 | 最小间隔 | Android 12+ 前台App限制 |
|------|------|---------|---------|------------------------|
| `set()` | ❌ 模糊 | 推迟 | 无强限制 | `SCHEDULE_EXACT_ALARM` 权限不需要 |
| `setExact()` | ✅ 精准 | 推迟 | 无强限制 | 需 `SCHEDULE_EXACT_ALARM` |
| `setAndAllowWhileIdle()` | ✅ 精准 | 允许(受限) | 15min | 需 `SCHEDULE_EXACT_ALARM` |

---

## 层六：应用场景举例

### 场景 1：IM 心跳优化 —— 从 30s 到 5min，省电 40%

**背景：** 某 IM 应用使用 `AlarmManager.setExact(30s)` + `WakeLock` 保活，导致大量后台耗电。

**问题分析：**
```
30s 心跳周期分析：
┌─ 每次心跳流程：
│  WakeLock.acquire() → CPU唤醒(50ms) → Radio DCH建立(100ms) 
│  → TCP心跳包(1 round-trip 50ms) → DCH Tail(10s!) → IDLE
│  
│  30s周期中，Radio实际活跃时间 ≈ 10.2s
│  活跃占比 = 10.2s / 30s = 34%！！！
│  每小时唤醒 120 次 × 每次耗电 ~0.15mAh = 18mAh/小时
└────────────────────────────────
```

**优化方案：**

```java
// ============ 优化前 ============
AlarmManager am = (AlarmManager) getSystemService(ALARM_SERVICE);
PowerManager.WakeLock wl = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "Heartbeat");
PendingIntent pi = PendingIntent.getBroadcast(this, 0, intent, FLAG_UPDATE_CURRENT);

// 每30秒精准唤醒+持锁→心跳
am.setExact(AlarmManager.ELAPSED_REALTIME_WAKEUP, 
            SystemClock.elapsedRealtime() + 30_000, pi);

// ============ 优化后 ============
// Step 1: 接入 FCM 推送代替轮询心跳
// 高优先级 FCM 消息直接推送，无需应用轮询

// Step 2: 兜底心跳 → 模糊 Alarm + 自适应间隔
// 使用 WorkManager 周期任务
PeriodicWorkRequest heartbeatWork = new PeriodicWorkRequest.Builder(
    HeartbeatWorker.class,
    15, TimeUnit.MINUTES,   // 最小间隔15分钟(系统限制)
    5, TimeUnit.MINUTES     // flex interval
)
.setConstraints(new Constraints.Builder()
    .setRequiredNetworkType(NetworkType.CONNECTED)
    .build())
.addTag("heartbeat")
.build();
WorkManager.getInstance(context)
    .enqueueUniquePeriodicWork("heartbeat", KEEP, heartbeatWork);

// Step 3: 自适应心跳算法
class HeartbeatWorker extends Worker {
    @Override
    public Result doWork() {
        long now = System.currentTimeMillis();
        // 如果最近5分钟收到过FCM推送，说明连接存活，跳过心跳
        if (now - lastFcmReceived < 5 * 60_000) {
            return Result.success();
        }
        // 否则发送长连接心跳
        sendTcpHeartbeat();
        return Result.success();
    }
}
```

**量化效果：**

| 指标 | 优化前(30s) | 优化后(5-15min自适应) | 改善 |
|------|-----------|---------------------|------|
| 每小时唤醒次数 | 120次 | 4-12次 | **减少90%+** |
| Radio 活跃率 | 34% | 2-5% | 减少30%+ |
| 每小时耗电 | 18mAh | 3-5mAh | **省电72%** |
| 24小时后台耗电 | 约432mAh(约15%) | 约96mAh(约3%) | **省电78%** |
| 整体省电(含其他模块) | — | — | **约40%** |

### 场景 2：WorkManager 替代后台 Service 执行数据同步

**背景：** 新闻类应用原使用 `Service` + `AlarmManager.setExact(1h)` 定时同步，即使没有网络也唤醒 CPU。

**优化前代码：**

```java
// 旧方案 —— 后台 Service 定时轮询
public class SyncService extends Service {
    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        new Thread(() -> {
            PowerManager.WakeLock wl = pm.newWakeLock(
                PowerManager.PARTIAL_WAKE_LOCK, "SyncWL");
            wl.acquire(60_000);  // 最多持锁1分钟
            try {
                syncArticles();  // HTTP请求下载新闻
            } finally {
                wl.release();
                stopSelf();
            }
        }).start();
        return START_NOT_STICKY;
    }
}
// Alarm 每1小时触发 → 不管有没有网络都唤醒
am.setExact(AlarmManager.RTC_WAKEUP, nextHourMs, syncPendingIntent);
```

**优化后代码：**

```java
// 新方案 —— WorkManager + 约束条件
Constraints syncConstraints = new Constraints.Builder()
    .setRequiredNetworkType(NetworkType.CONNECTED)   // 只在有网络时执行
    .setRequiresBatteryNotLow(true)                   // 低电量不执行
    .setRequiresDeviceIdle(true)                      // 设备空闲时执行
    .build();

PeriodicWorkRequest syncWork = new PeriodicWorkRequest.Builder(
    SyncWorker.class,
    1, TimeUnit.HOURS,        // 周期1小时
    15, TimeUnit.MINUTES       // flex 15分钟
)
.setConstraints(syncConstraints)
.setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
.setInitialDelay(30, TimeUnit.SECONDS)
.build();

WorkManager.getInstance(context)
    .enqueueUniquePeriodicWork(
        "news_sync",
        ExistingPeriodicWorkPolicy.KEEP,   // 已有则不重复创建
        syncWork
    );

// Worker 实现
class SyncWorker extends Worker {
    @Override
    public Result doWork() {
        // WorkManager 自动处理 WakeLock，无需手动管理！
        // 框架在 doWork() 期间持有 WakeLock
        try {
            List<Article> articles = api.syncArticles();
            database.insertAll(articles);
            return Result.success();
        } catch (IOException e) {
            // 无网络 → 自动重试(按 Backoff 策略)
            return Result.retry();
        }
    }
}
```

**对比效果：**

| 指标 | Service + Alarm | WorkManager | 改善 |
|------|----------------|-------------|------|
| 无网络时是否唤醒 | ✅ 唤醒，无用功 | ❌ 跳过 | 避免无效耗电 |
| 低电量执行 | ✅ 执行 | ❌ 延迟 | 10-15%电池节省 |
| Doze 中执行 | ❌ 失败/被限制 | ✅ 在 Maintenance Window | 可靠 |
| WakeLock 泄漏风险 | 中等(手动管理) | 极低(框架管理) | 安全性↑ |
| 任务合并 | 不支持 | 支持(与系统其他Job合并) | Radio 省电 |

### 场景 3：GPS 定位功耗优化 —— 从持续高精度到自适应

**问题：** 某跑步应用使用 `GPS_PROVIDER` + `5s` 定时间隔，持续后台定位导致耗电严重（1小时耗电 35-40%）。

**定位技术功耗对比：**

| 定位方式 | 典型精度 | 典型功耗 | 冷启动时间 | 适用场景 |
|---------|---------|---------|-----------|---------|
| GPS 芯片 | 3-5m | **50-80mW (持续)** | 30-120s | 导航、跑步 |
| Network (Cell/WiFi) | 20-100m | 5-15mW | <5s | 城市定位 |
| Fused (GPS+Network) | 3-30m | 可变(10-60mW) | <5s | **推荐** |

**优化方案（Fused Location Provider + 自适应策略）：**

```java
public class OptimizedLocationManager {
    private FusedLocationProviderClient fusedClient;
    private LocationRequest locationRequest;
    private long lastKnownLocationTime;
    private Location lastKnownLocation;
    
    public void startAdaptiveLocation() {
        fusedClient = LocationServices.getFusedLocationProviderClient(context);
        
        // ===== 自适应定位请求配置 =====
        locationRequest = LocationRequest.create()
            .setPriority(LocationRequest.PRIORITY_HIGH_ACCURACY)
            // 最快更新间隔（运动中）
            .setFastestInterval(10_000)       // 最快10s
            // 默认更新间隔（静止时自动延长）
            .setInterval(30_000)              // 默认30s
            // 最小位移触发（不移动不更新）
            .setSmallestDisplacement(10)       // 10米位移才触发
            // 最大等待时间（超过此时间强制返回，即使无新位置）
            .setMaxWaitTime(60_000);
    }
    
    // 动态调整定位频率
    private void adaptFrequency(float speedMps) {
        LocationRequest newRequest = LocationRequest.create()
            .setPriority(LocationRequest.PRIORITY_HIGH_ACCURACY);
        
        if (speedMps < 0.5) {
            // 静止/步行 → 60s间隔 + 50m位移
            newRequest.setInterval(60_000)
                      .setSmallestDisplacement(50);    // 省电模式
        } else if (speedMps < 5) {
            // 跑步 → 15s间隔 + 20m位移
            newRequest.setInterval(15_000)
                      .setSmallestDisplacement(20);    // 平衡模式
        } else {
            // 骑行/驾驶 → 5s间隔 + 30m位移
            newRequest.setInterval(5_000)
                      .setSmallestDisplacement(30);    // 高精度模式
        }
        fusedClient.removeLocationUpdates(callback)
                   .addOnSuccessListener(v -> 
                       fusedClient.requestLocationUpdates(newRequest, callback, null));
    }
    
    // 使用 GeoFence 代替持续定位
    private void addGeoFence() {
        GeofencingRequest geoRequest = new GeofencingRequest.Builder()
            .setInitialTrigger(GeofencingRequest.INITIAL_TRIGGER_ENTER)
            .addGeofence(new Geofence.Builder()
                .setRequestId("home_100m")
                .setCircularRegion(homeLat, homeLng, 100) // 半径100米
                .setExpirationDuration(Geofence.NEVER_EXPIRE)
                .setTransitionTypes(Geofence.GEOFENCE_TRANSITION_ENTER |
                                    Geofence.GEOFENCE_TRANSITION_EXIT)
                .build())
            .build();
        
        geofencingClient.addGeofences(geoRequest, geofencePendingIntent);
        // GeoFence 基于芯片级Sensor Hub，功耗极低(<2mW)
    }
}
```

**量化效果（1小时持续运行）：**

| 指标 | 优化前(纯GPS 5s) | 优化后(自适应) | 改善 |
|------|-----------------|---------------|------|
| GPS 芯片活跃时间 | 3600s(100%) | ~900s(25%) | **减少75%** |
| Network 定位辅助 | 0% | ~40% | 大幅减少 GPS 冷启动 |
| 1小时定位功耗 | ~270mAh | ~55mAh | **省电80%** |
| 精度 | 3-5m | 3-30m(自适应) | 可接受 |

---

## 总结：功耗优化面试核心框架

```
面试回答万能框架（STAR + 量化）：

1. 现象(20字)：XXX App 后台耗电 XXX mAh/小时，占比 XX%

2. 定位工具(3个)：
   - Battery Historian → 找异常长 WakeLock / Radio / CPU
   - Profiler Energy → 查看方法级耗电
   - dumpsys batterystats → 命令行快速查看

3. 根本原因(核心指标)：
   - CPU：WakeLock 忘记 release / 死循环 / 频繁定时器
   - Radio：短周期心跳 / 无批量合并 / 忽略 tail time
   - GPS：持续高精度 / 未使用 Fused Provider
   - UI：屏幕常亮 / 白色主题 / 动画过频

4. 优化手段(对应方案)：
   - WakeLock → 超时 acquire / try-finally / 用 WorkManager 替代
   - 网络 → 批量/延迟/预取 / 长连接替代短轮询 / FCM 替代自定义推送
   - 定时 → set() 替代 setExact() / JobScheduler 替代 Alarm
   - GPS → FusedLocationProvider / GeoFence / 自适应频率
   - Doze → 遵守系统规则 / 不强行抵抗 / 高优消息用 FCM high priority

5. 优化效果(必须量化)：
   - 功耗从 XX mAh/h → YY mAh/h (降低 ZZ%)
   - 后台 CPU 时间从 A 分钟/小时 → B 分钟/小时
   - Doze 占比从 C% → D%
```

---

> **参考资源：**
> - AOSP 源码：`frameworks/base/services/core/java/com/android/server/power/`
> - Battery Historian：https://github.com/google/battery-historian
> - Android 开发者文档：Optimize for Doze and App Standby
> - WorkManager 官方指南：https://developer.android.com/topic/libraries/architecture/workmanager
