# React Native 面试核心考点深度解析

> 本文档围绕 React Native 面试的高频考点，采用六层递进结构：从基础面试题 → 核心原理深入（JSI/Fabric）→ 图解架构 → 实战案例分析，帮助读者建立完整的 RN 知识体系。

---

## 第一层：高频面试题精讲（4+ 道核心题）

### 1. RN 的 JS Bridge 通信原理（异步队列 + JSON 序列化）

**面试官视角：** 这道题考察候选人是否理解 RN 架构的核心——JavaScript 与 Native 之间如何通信，这是理解 RN 性能瓶颈和 New Architecture 改进的基础。

**核心回答：**

React Native 的 JS-Native 通信基于 **Bridge** 架构，核心是一种**异步、批量、单向**的消息传递机制：

**Old Bridge 三层架构：**

```
┌─────────────────────────────────────────────────┐
│                   JS Thread                       │
│  React → Virtual DOM Diff → Bridge Message       │
├─────────────────────────────────────────────────┤
│               Bridge (Message Queue)              │
│  ┌───────────────────────────────────────────┐   │
│  │  Shadow Queue  │  UI Queue  │  Native Queue│   │
│  │  (布局计算)     │  (UI操作)   │  (模块调用)  │   │
│  └───────────────────────────────────────────┘   │
├─────────────────────────────────────────────────┤
│                Native Thread                      │
│  Yoga Layout → Native View → Android/iOS UI      │
└─────────────────────────────────────────────────┘
```

**通信流程详解：**

1. **JS 侧调用 Native：** React 在 JS 线程执行，将操作（创建 View、调用模块）序列化为 JSON 消息，放入 Message Queue
2. **Bridge 传输：** 消息队列定期批量传递到 Native 侧。**关键：所有消息必须先 JSON.stringify 序列化，跨线程传输后再 JSON.parse 反序列化**
3. **Native 侧执行：** Shadow Thread 处理布局（Yoga），Main Thread 创建/更新原生 View
4. **Native 回调 JS：** 回调同样走 JSON 序列化 → Bridge → JS 线程

**三个线程模型：**

| 线程 | 职责 | 关键点 |
|------|------|--------|
| **JS Thread** | 执行 React 代码、Diff 算法 | 单线程，卡住会阻塞全部 UI 更新 |
| **Shadow Thread** | Yoga 布局计算（Flexbox） | 将 CSS-layout 转为原生坐标 |
| **Main Thread** | 创建/更新原生 View | 等同于 Android/iOS 的 UI Thread |

**Bridge 的三大性能瓶颈：**

1. **JSON 序列化开销：** 每次跨线程通信都要 JSON.stringify + JSON.parse，大数据量时 CPU 消耗显著
2. **异步批处理延迟：** 消息批量传递，非实时同步，快速滚动时可能掉帧
3. **单通道拥塞：** 所有模块（UI、网络、存储）共享同一个 Bridge，模块间互相阻塞

---

### 2. RN 新旧架构对比：Old Bridge vs Fabric / TurboModule / JSI

**面试官视角：** 这是 RN 面试的"定级题"——区分候选人是否关注 RN 技术演进，以及对底层变革的理解深度。

**核心回答：**

React Native 在 0.68+ 版本引入了 **New Architecture**，包含三大核心组件：

| 组件 | 旧架构 | 新架构 | 核心改进 |
|------|--------|--------|---------|
| **通信层** | Bridge（JSON 异步） | **JSI**（C++ 同步调用） | 消除序列化，直接内存访问 |
| **渲染层** | UIManager（异步） | **Fabric**（同步渲染） | 优先级调度，Concurrent 模式 |
| **原生模块** | Native Modules（JSON） | **TurboModules**（JSI 绑定） | 按需加载，C++ 直接调用 |

**核心变化详解：**

**1. JSI（JavaScript Interface）—— 通信革命**

```
Old Bridge:
JS → JSON.stringify → Bridge Queue → JSON.parse → Native
                                    (异步, 有序列化开销)

New JSI:
JS ←→ C++ Host Object ←→ Native
         (同步, 零拷贝, 直接方法调用)
```

JSI 的核心创新：
- **C++ 作为中间层**：JS 引擎（Hermes）直接通过 JSI 调用 C++ 函数，C++ 再调用 Native（Java/ObjC）
- **同步调用可能**：不再强制异步，可以像调用普通 JS 函数一样调用 Native 方法
- **Host Object**：C++ 对象可以注册为 JS 可直接访问的对象，无需序列化
- **引擎无感**：JSI 是引擎无关的抽象层，理论上可以替换 Hermes/V8/JSC

**2. TurboModules —— 原生模块的按需加载**

```
Old Native Modules:
启动时全量注册 → 扫描所有 NativeModule → 初始化 → 占用内存

TurboModules:
首次调用时才加载 → JSI 绑定 → 仅初始化被使用的模块
```

**3. Fabric —— 新的渲染系统**

核心特性：基于优先级调度、支持 React Concurrent Mode、渲染可中断

---

### 3. RN 的渲染原理（Shadow Tree → Yoga 布局 → 原生 View）

**面试官视角：** 考察候选人是否理解 RN 如何将 React 组件树最终映射到原生 View 层级。

**核心回答：**

RN 的渲染流程分为两个阶段：

**阶段一：React 协调 + Shadow Tree 构建（JS + Shadow Thread）**

```
React Component Tree (JS)
        │
        ▼  Reconciliation (Virtual DOM Diff)
   ┌─────────────┐
   │  Shadow Tree │  ← Shadow Thread
   │  ┌─────────┐ │
   │  │  Node   │ │  每个 Shadow Node 存储：
   │  │  style  │ │  - CSS-layout 属性（flex, width, height...）
   │  │  layout │ │  - Yoga 计算后的绝对坐标 (x, y, width, height)
   │  └─────────┘ │
   └──────┬──────┘
          │
          ▼  Yoga Layout Engine (C++)
   ┌─────────────────────────┐
   │  Flexbox → Absolute Pos  │
   │  (递归计算每个节点的坐标) │
   └──────────┬──────────────┘
```

**阶段二：原生 View 创建/更新（Main Thread）**

```
Yoga 布局结果 → UIManager → createView/updateView
        │
        ▼
┌────────────────────┐
│  Android View Tree │  ← Android: ViewGroup + View
│  ┌──────────────┐  │
│  │  FrameLayout │  │
│  │  ├─ TextView │  │
│  │  └─ ImageView│  │
│  └──────────────┘  │
│        OR           │
│  iOS UIView Tree    │  ← iOS: UIView + CALayer
│  ┌──────────────┐  │
│  │  RCTView     │  │
│  │  ├─ RCTText  │  │
│  │  └─ RCTImage │  │
│  └──────────────┘  │
└────────────────────┘
```

**Yoga 布局引擎核心原理：**

Yoga 是 Facebook 用 C++ 实现的 Flexbox 布局引擎，将 CSS Flexbox 属性计算为屏幕上的绝对坐标：

```javascript
// JS 侧样式声明
<View style={{
  flexDirection: 'row',
  justifyContent: 'space-between',
  padding: 16
}}>

// Yoga 内部计算：
// Node[0].layout = { x: 0, y: 0, width: 375, height: 100 }
// Node[0].children[0].layout = { x: 16, y: 16, width: 150, height: 68 }
// Node[0].children[1].layout = { x: 209, y: 16, width: 150, height: 68 }
```

**旧架构渲染的关键缺陷：**

- JS 线程计算 Diff → Shadow Thread 计算布局 → Main Thread 更新 View，三步都是**异步跳转**
- 用户快速滚动时，JS 线程可能来不及计算 Diff，导致空白帧（White Screen Flash）
- 布局计算和 View 更新之间存在时间差，可能导致"跳变"（jump）

---

### 4. RN 的性能瓶颈和优化（FlatList / 长列表 / 动画）

**面试官视角：** 这题区分"会用 RN"和"能优化 RN 项目"的候选人。

**核心回答：**

#### 性能瓶颈分析

| 瓶颈 | 根因 | 表现 |
|------|------|------|
| **Bridge 过载** | JSON 序列化 + 单通道 | 快速滚动时 UI 更新延迟 |
| **JS 线程阻塞** | 单线程执行 JS + Diff | 动画卡顿、响应延迟 |
| **过度渲染** | 不必要的组件重渲染 | 浪费 CPU/GPU 资源 |
| **原生 View 创建开销** | 每个 React 组件映射一个原生 View | 嵌套过深导致 View 层级爆炸 |
| **图片解码** | 主线程解码大图 | 掉帧明显 |

#### 核心优化方案

**1. FlatList 优化（长列表性能关键）**

```javascript
// ❌ 错误做法：ScrollView 一次性渲染所有 Item
<ScrollView>
  {data.map(item => <ItemComponent key={item.id} data={item} />)}
</ScrollView>

// ✅ 正确做法：FlatList 虚拟化 + 回收复用
<FlatList
  data={data}
  renderItem={renderItem}
  keyExtractor={item => item.id}
  // 核心优化参数
  windowSize={5}          // 预渲染可见区外的 5 屏（默认 21）
  maxToRenderPerBatch={10} // 每批次最多渲染 10 个
  initialNumToRender={10}  // 首屏只渲染 10 个
  removeClippedSubviews={true} // 移除屏幕外的原生 View
  getItemLayout={getItemLayout} // 固定高度时可跳过布局计算
/>
```

**FlatList 优化参数解读：**

| 参数 | 作用 | 建议值 |
|------|------|--------|
| `windowSize` | 渲染窗口 = 可见区域 × windowSize | 5-10（小屏设备用更小值） |
| `maxToRenderPerBatch` | 每帧最多渲染 item 数 | 5-10 |
| `initialNumToRender` | 首屏渲染数量 | 刚好覆盖一屏 |
| `removeClippedSubviews` | 移除屏幕外原生 View，节省内存 | true（Android 特别有效） |
| `getItemLayout` | 预知高度，跳过 Yoga 测量 | 固定高度列表必须设置 |

**2. 动画优化：useNativeDriver**

```javascript
// ❌ 错误：动画每帧走 Bridge（JS → Native）
Animated.timing(value, {
  toValue: 1,
  duration: 300,
  useNativeDriver: false, // 默认 false
}).start();

// ✅ 正确：动画在 Native 侧直接执行
Animated.timing(value, {
  toValue: 1,
  duration: 300,
  useNativeDriver: true,  // 动画在 Native 驱动，不经过 Bridge
}).start();
```

**useNativeDriver 原理：**

```
Native Driver OFF (JS 驱动):
每一帧：JS计算值 → JSON序列化 → Bridge → Native更新View
        (60fps → 每16ms一次Bridge往返, 严重拥塞)

Native Driver ON (Native 驱动):
JS只发送"动画配置"一次 → Native侧自主执行动画
        (Bridge完全不参与动画过程, 丝滑60fps)
```

**支持的属性：** `opacity`、`transform`（translate/scale/rotate）、`backgroundColor`（Android 不支持）

**3. React 层面的通用优化**

| 优化手段 | 原理 | 代码 |
|---------|------|------|
| `React.memo` | 浅比较 props 避免重渲染 | `export default React.memo(Component)` |
| `useMemo` | 缓存计算结果 | `const value = useMemo(() => heavyCalc(a), [a])` |
| `useCallback` | 缓存函数引用 | `const handler = useCallback(() => {}, [])` |
| `InteractionManager` | 延迟非关键任务 | `InteractionManager.runAfterInteractions(() => {})` |

**4. 图片优化**

```javascript
// 指定尺寸避免主线程解码后重新布局
<Image
  source={{ uri: '...' }}
  style={{ width: 200, height: 200 }}
  resizeMode="cover"
/>

// 使用 FastImage 替代默认 Image（更好的缓存 + 优先级）
import FastImage from 'react-native-fast-image';
<FastImage
  source={{ uri: '...', priority: FastImage.priority.normal }}
/>
```

---

## 第二层：核心原理深入 —— JSI（C++ 直接调用） vs Bridge（JSON 桥接）性能差异

### JSI 的本质：消灭序列化，打通 JS ↔ Native 的直接引用

JSI（JavaScript Interface）是 New Architecture 中最底层的变革，它改变了 RN 根本的通信模型。

#### Bridge 模式的数据流（旧架构）

```
┌──────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────┐
│ JS Code  │──1──│ JSON.stringify│──2──│  Bridge Queue │──3──│ JSON.parse│──4──│ Native  │
│          │     │ (V8/Hermes)   │     │  (异步批量)    │     │ (JNI/ObjC) │     │          │
└──────────┘     └──────────────┘     └──────────────┘     └──────────────┘     └──────────┘

每一次跨语言调用（JS → Native）的开销：
  1. V8/Hermes 执行 JSON.stringify（CPU 密集）
  2. 消息入队，等待批次传输（延迟不可控）
  3. 消息出队，JNI/ObjC 回调
  4. Native 侧 JSON.parse（CPU 密集）
  5. 执行实际逻辑
  6. 返回结果重新走 1-4
  
  总耗时：毫秒级别，高并发时可达几十毫秒
```

#### JSI 模式的数据流（新架构）

```
┌──────────┐          ┌──────────────────┐          ┌──────────┐
│ JS Code  │──直接调用─│  C++ Host Object  │──直接调用─│ Native   │
│          │◄─────────│  (JSI Binding)    │◄─────────│          │
└──────────┘          └──────────────────┘          └──────────┘

JSI 调用流程：
  1. JS 引擎持有 C++ Host Object 的引用（指针）
  2. JS 调用 C++ 方法 → 通过 JSI API 直接进入 C++ 层
  3. C++ 层通过 JNI（Android）或直接调用（iOS Objective-C++）访问 Native API
  4. 返回值原路返回（C++ → JSI → JS）
  
  总耗时：微秒级别，接近原生方法调用
```

#### 性能对比实测

| 场景 | Bridge (旧) | JSI (新) | 提升倍数 |
|------|------------|----------|---------|
| 空方法调用（往返） | ~2-3ms | ~0.01ms | **200-300x** |
| 传递 1KB 数据 | ~4-6ms | ~0.05ms | **80-120x** |
| 传递 100KB 数据 | ~50-100ms | ~0.5ms | **100-200x** |
| 动画每帧更新（60fps） | 不可行 | 完全可以 | ∞ |

#### JSI 的核心能力

**1. Host Objects（宿主对象）**

```cpp
// C++ 侧：定义一个可以被 JS 直接调用的对象
class NativeStorage : public jsi::HostObject {
public:
    jsi::Value get(jsi::Runtime& runtime, const jsi::PropNameID& name) override {
        if (name.utf8(runtime) == "getItem") {
            return jsi::Function::createFromHostFunction(
                runtime, name, 1,
                [](jsi::Runtime& rt, const jsi::Value&, const jsi::Value* args, size_t count) {
                    std::string key = args[0].getString(rt).utf8(rt);
                    std::string value = androidStorageGet(key); // 直接调用 JNI
                    return jsi::String::createFromUtf8(rt, value);
                }
            );
        }
        return jsi::Value::undefined();
    }
};

// 注册到 JS 全局对象
runtime.global().setProperty(runtime, "NativeStorage",
    jsi::Object::createFromHostObject(runtime, 
        std::make_shared<NativeStorage>()));
```

```javascript
// JS 侧：像调用普通 JS 对象一样使用
const value = NativeStorage.getItem('user_token'); // 同步！无 await！
console.log(value); // 直接拿到 Native 返回值
```

**2. 同步调用能力**

```javascript
// Bridge 时代：必须异步
const value = await AsyncStorage.getItem('key'); // 返回 Promise

// JSI 时代：可以同步
const value = NativeStorage.getItem('key');       // 直接返回值
// 但注意：同步调用会阻塞 JS 线程，耗时操作仍需异步
```

**3. 共享内存（零拷贝）**

```cpp
// JSI 支持直接传递 ArrayBuffer，JS 和 C++ 共享同一块内存
// 不需要任何序列化/反序列化
uint8_t* buffer = new uint8_t[imageSize];
// JS 侧直接读写这个 buffer
```

---

## 第三层：核心原理深入 —— Fabric 渲染器的同步渲染

### Fabric 的革命：从三线程异步到同步可中断渲染

Fabric 是 New Architecture 的渲染引擎，核心目标是解决旧架构中 UI 更新"异步不可控"的问题。

#### 旧架构渲染的"三跳"问题

```
Frame 生命周期（16ms @ 60fps）:

[0ms]         [5ms]            [10ms]           [16ms]
  │             │                │                │
  │ JS Thread   │                │                │
  │ Diff计算    ├─→ Bridge ──→   │                │
  │             │  (JSON传递)    │                │
  │             │                │ Shadow Thread  │
  │             │                │ Yoga布局       ├─→ Bridge ──→ │
  │             │                │                │  (JSON传递)  │
  │             │                │                │              │ Main Thread
  │             │                │                │              │ 创建View
  │             │                │                │              │ (可能已超16ms!)
  
问题：跨线程跳转 3 次 + JSON 序列化 2 次，在 16ms 内完成非常困难
结果：掉帧、白屏闪现、列表滚动不跟手
```

#### Fabric 的同步渲染管线

```
Fabric 渲染流程:

[0ms]            [4ms]              [8ms]              [12ms]         [16ms]
  │                │                  │                  │               │
  │ JS Thread      │                  │                  │               │
  │ (Concurrent)   │                  │                  │               │
  │ ① React        │                  │                  │               │
  │ Element Tree   │                  │                  │               │
  │    │ C++ JSI    │                  │                  │               │
  │    ▼           │                  │                  │               │
  │ ② Fabric       │                  │                  │               │
  │ Shadow Tree    │                  │                  │               │
  │ (C++ 共享内存)  │                  │                  │               │
  │    │ 直接指针   │                  │                  │               │
  │    ▼           │                  │                  │               │
  │ ③ Yoga Layout  │                  │                  │               │
  │ (C++ 同进程)    │                  │                  │               │
  │    │ 直接指针   │                  │                  │               │
  │    ▼           │                  │                  │               │
  │ ④ Main Thread  │                  │                  │               │
  │   创建/更新View │                  │                  │               │
  │    (JNI调用)    │                  │                  │               │
  
关键变化：
  ✅ 全程无 JSON 序列化——数据通过 C++ 指针直接传递
  ✅ JS → Shadow → Yoga → Native 全在一个进程空间（C++）
  ✅ 渲染可以被高优先级事件（如手势）中断和恢复
```

#### Fabric 的三大核心特性

**1. 同步渲染（Synchronous Rendering）**

```cpp
// Fabric 中，JS 创建 View 的代码执行后，Native View 直接同步创建
// 而不是放入队列异步等待

// 旧架构：
UIManager.createView(tag, 'RCTView', { width: 100 });  
// → 消息入队 → 等待批处理 → Native 创建 （异步，不可预测）

// Fabric：
FabricUIManager.createNode(tag, 'RCTView', { width: 100 });
// → JSI 直接调用 C++ → C++ 调用 JNI → Native View 立即创建（同步）
```

**2. 优先级调度（不阻塞手势/动画）**

Fabric 借用了 React Fiber 的优先级概念：

```
事件优先级：
  ⬆ 最高：用户交互（点击、滑动）→ 立即处理，中断低优渲染
  ⬆ 高：  动画更新 → 每帧保证
  ⬇ 正常：UI 更新
  ⬇ 低：  数据预加载、后台计算
```

**3. 跨平台一致性**

Fabric 的 C++ 核心层在所有平台上共享同一套代码：

```
┌────────────────────────────────────┐
│       React (JavaScript/TS)        │
├────────────────────────────────────┤
│       JSI (C++ Binding Layer)      │
├────────────────────────────────────┤
│    Fabric Core (C++) — 跨平台共享  │
│  - Shadow Tree Management          │
│  - Yoga Layout                     │
│  - Event Dispatching               │
│  - State Management                │
├──────────────────┬─────────────────┤
│  Android Mount   │  iOS Mount      │
│  (JNI → Java)    │  (ObjC++)       │
├──────────────────┼─────────────────┤
│  Android View    │  iOS UIView     │
└──────────────────┴─────────────────┘
```

---

## 第四层：架构图解

### Old Bridge vs New Architecture 完整对比流程图

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                        OLD BRIDGE ARCHITECTURE (RN < 0.68)                   ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  ┌─────────────────┐          ┌─────────────────────────────────────────┐   ║
║  │   JS THREAD     │          │            BRIDGE (Message Queue)        │   ║
║  │                 │          │                                         │   ║
║  │ ┌─────────────┐ │  JSON   │  ┌──────────┐ ┌────────┐ ┌───────────┐  │   ║
║  │ │ React Recon │─┼────────►│  │ Shadow   │ │  UI    │ │  Native   │  │   ║
║  │ │ (Virtual DOM│ │ seq/    │  │ Messages │ │Messages│ │  Module   │  │   ║
║  │ │   Diff)     │ │ deseq   │  │ (Yoga)   │ │( View) │ │  Messages │  │   ║
║  │ └─────────────┘ │         │  └────┬─────┘ └───┬────┘ └─────┬─────┘  │   ║
║  │                 │         │       │            │            │        │   ║
║  │ ┌─────────────┐ │         │       │            │            │        │   ║
║  │ │ NativeModule│ │◄────────┼───────┴────────────┴────────────┘        │   ║
║  │ │  .call()    │ │  JSON   │        (回调走同一个 Bridge)              │   ║
║  │ └─────────────┘ │         │                                         │   ║
║  └─────────────────┘         └─────────────────────────────────────────┘   ║
║                                        │                                    ║
║                    ┌───────────────────┼───────────────────┐                ║
║                    ▼                   ▼                   ▼                ║
║  ┌─────────────────────┐ ┌─────────────────────┐ ┌─────────────────────┐   ║
║  │   SHADOW THREAD     │ │    MAIN THREAD      │ │   NATIVE MODULES    │   ║
║  │                     │ │                     │ │                     │   ║
║  │ ┌─────────────────┐ │ │ ┌─────────────────┐ │ │ ┌─────────────────┐ │   ║
║  │ │ Yoga Layout     │ │ │ │ RCTView(View)   │ │ │ │ CameraModule   │ │   ║
║  │ │ (Flexbox→绝对坐标)│ │ │ │ RCTText(TextV)  │ │ │ │ StorageModule  │ │   ║
║  │ │                 │ │ │ │ RCTImage(ImgV)  │ │ │ │ NetworkModule  │ │   ║
║  │ └─────────────────┘ │ │ └─────────────────┘ │ │ └─────────────────┘ │   ║
║  │                     │ │                     │ │                     │   ║
║  │ ⚠️ 独立线程          │ │ ⚠️ Android UI Thread│ │ ⚠️ 启动时全量注册    │   ║
║  │ ⚠️ 与JS异步通信      │ │ ⚠️ 收到消息后才更新  │ │ ⚠️ JSON序列化传参    │   ║
║  └─────────────────────┘ └─────────────────────┘ └─────────────────────┘   ║
║                                                                              ║
║  核心痛点：                                                                    ║
║  ❌ 全走 JSON 序列化/反序列化（CPU 密集型）                                      ║
║  ❌ 所有通信异步批处理（实时性差）                                                ║
║  ❌ 单 Bridge 通道拥塞（模块间互相影响）                                          ║
║  ❌ 启动时全量初始化所有 Native Module（内存浪费）                                  ║
║  ❌ 渲染三线程跳转不可控（无法保证 16ms 内完成一帧）                                  ║
╚══════════════════════════════════════════════════════════════════════════════╝


╔══════════════════════════════════════════════════════════════════════════════╗
║                    NEW ARCHITECTURE (RN ≥ 0.68, Fabric + TurboModule)        ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  ┌──────────────────────────────────────────────────────────────────────┐   ║
║  │                         JS THREAD (Hermes/V8)                        │   ║
║  │                                                                      │   ║
║  │  ┌────────────┐    ┌────────────────┐    ┌───────────────────────┐   │   ║
║  │  │ React       │    │ TurboModules   │    │ Fabric Components     │   │   ║
║  │  │ Concurrent  │    │ (JS侧存根)      │    │ (JS侧声明式组件)       │   │   ║
║  │  │ Renderer    │    │                │    │                       │   │   ║
║  │  └──────┬─────┘    └───────┬────────┘    └───────────┬───────────┘   │   ║
║  └─────────┼─────────────────┼───────────────────────────┼──────────────┘   ║
║            │                 │                           │                   ║
║     ═══════╪═════════════════╪═══════════════════════════╪═══════════       ║
║            │           JSI (C++ Binding Layer)           │                   ║
║            │           同步 · 零拷贝 · 直接调用            │                   ║
║     ═══════╪═════════════════╪═══════════════════════════╪═══════════       ║
║            │                 │                           │                   ║
║            ▼                 ▼                           ▼                   ║
║  ┌──────────────────────────────────────────────────────────────────────┐   ║
║  │                     C++ CORE (跨平台共享层)                            │   ║
║  │                                                                      │   ║
║  │  ┌──────────────────────┐  ┌──────────────────────────────────────┐  │   ║
║  │  │ TurboModule Manager  │  │        Fabric Renderer               │  │   ║
║  │  │                      │  │                                      │  │   ║
║  │  │ ┌──────────────────┐ │  │  ┌────────────────────────────────┐  │  │   ║
║  │  │ │ CameraTurboMod   │ │  │  │     Shadow Tree (C++ Objects)  │  │  │   ║
║  │  │ │ StorageTurboMod  │ │  │  │     ┌──────┐ ┌──────┐ ┌──────┐ │  │  │   ║
║  │  │ │ NetworkTurboMod  │ │  │  │     │View │ │Text  │ │Image │ │  │  │   ║
║  │  │ │ (按需懒加载)      │ │  │  │     └──┬───┘ └──┬───┘ └──┬───┘ │  │  │   ║
║  │  │ └──────────────────┘ │  │  │        │        │        │     │  │  │   ║
║  │  └──────────┬───────────┘  │  │        ▼        ▼        ▼     │  │  │   ║
║  │             │              │  │  ┌────────────────────────────┐ │  │  │   ║
║  │             │              │  │  │   Yoga Layout (C++ 同进程)  │ │  │  │   ║
║  │             │              │  │  │   计算出绝对坐标 (x,y,w,h)  │ │  │  │   ║
║  │             │              │  │  └────────────────────────────┘ │  │  │   ║
║  │             │              │  │               │                 │  │  │   ║
║  │             │              │  │               ▼                 │  │  │   ║
║  │             │              │  │  ┌────────────────────────────┐ │  │  │   ║
║  │             │              │  │  │     Mounting Layer         │ │  │  │   ║
║  │             │              │  │  │  (创建/更新原生 View)       │ │  │  │   ║
║  │             │              │  │  └────────────┬───────────────┘ │  │  │   ║
║  │             │              │  └────────────────┼────────────────┘  │  │   ║
║  └─────────────┼──────────────┘                   │                   │   ║
║                │                                  │                   │   ║
║     ═══════════╪══════════════════════════════════╪═══════════════       ║
║                │          JNI / ObjC++            │                   ║
║     ═══════════╪══════════════════════════════════╪═══════════════       ║
║                │                                  │                   ║
║  ┌─────────────┴──────────────┐  ┌────────────────┴──────────────────┐  ║
║  │     ANDROID NATIVE         │  │          ANDROID MAIN THREAD       │  ║
║  │                            │  │                                   │  ║
║  │  ┌──────────────────────┐  │  │  ┌─────────────────────────────┐  │  ║
║  │  │ TurboModule Impl     │  │  │  │ Android View Tree           │  │  ║
║  │  │ (Kotlin/Java)        │  │  │  │ ┌─────────┐ ┌────────────┐  │  │  ║
║  │  │                      │  │  │  │ │ViewGroup│ │TextView    │  │  │  ║
║  │  │ @ReactModule          │  │  │  │ │(FrameL) │ │(AppCompat) │  │  │  ║
║  │  │ class CameraModule    │  │  │  │ └─────────┘ └────────────┘  │  │  ║
║  │  └──────────────────────┘  │  │  └─────────────────────────────┘  │  ║
║  │                            │  │                                   │  ║
║  │  或 iOS (Swift/ObjC)       │  │  或 iOS Main Thread                │  ║
║  │  ┌──────────────────────┐  │  │  ┌─────────────────────────────┐  │  ║
║  │  │ RCTTurboModule       │  │  │  │ UIView Hierarchy            │  │  ║
║  │  │ (ObjC++)             │  │  │  │ ┌──────┐ ┌──────┐ ┌──────┐  │  │  ║
║  │  └──────────────────────┘  │  │  │ │UIView│ │UILabel│ │UIImg│  │  │  ║
║  │                            │  │  │ └──────┘ └──────┘ └──────┘  │  │  ║
║  └────────────────────────────┘  │  └─────────────────────────────┘  │  ║
║                                  └────────────────────────────────────┘  ║
║                                                                              ║
║  核心提升：                                                                    ║
║  ✅ JSI 同步调用，消除 JSON 序列化开销                                          ║
║  ✅ C++ 共享层，JS/Shadow/Yoga/Mount 同进程直接通信                              ║
║  ✅ TurboModules 按需懒加载（启动内存大幅降低）                                     ║
║  ✅ Fabric 同步渲染 + 优先级调度（保证 60fps）                                    ║
║  ✅ 支持 React Concurrent Mode（可中断渲染）                                      ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

### Old Bridge 通信时序 vs JSI 通信时序

```
Old Bridge (异步批处理):

JS Thread          Bridge Queue        Native Thread
   │                    │                    │
   │─invoke('getData')──►│                    │
   │                    │────[入队]──────────►│
   │                    │                    │──执行 getData()
   │                    │                    │──return "result"
   │                    │◄───[入队]──────────│
   │◄─────("result")────│                    │
   │                    │                    │
   时间：不可预测（取决于队列深度）


JSI (同步直接调用):

JS Thread          C++ (JSI)          Native Thread
   │                    │                    │
   │─NativeModule.getData()                 │
   │──────►│───────────►│───────────►│
   │       │  C++ HObj  │  JNI call  │
   │       │  直接调用   │            │──执行 getData()
   │◄──────│◄───────────│◄───────────│──return "result"
   │                    │                    │
   时间：微秒级（约 0.01ms）
```

---

## 第五层：RN 混合开发 —— 原生模块封装实战（上）

### 场景描述

**项目背景：** 一个社交 App 使用 React Native 开发主体，但需要集成以下原生能力：
1. **人脸识别 SDK**（原生 C++ 库，需要实时视频流处理）
2. **自定义视频播放器**（基于 Android ExoPlayer / iOS AVPlayer，需要精细控制）
3. **蓝牙通信**（需要原生 BLE API，频繁数据交换）

**技术目标：**
- 封装原生模块，使其在 JS 侧调用体验与普通 JS 模块无差异
- 保证高频数据传输（蓝牙数据流、视频帧）的性能
- 新旧架构双兼容（Bridge 方案 + TurboModule 方案）

### 方案架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     REACT NATIVE APP (JS/TS)                      │
│                                                                   │
│  ┌─────────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │ FaceDetector.ts │  │ VideoPlayer  │  │ BLEScanner.ts      │  │
│  │ (JS 业务封装)    │  │ .tsx (组件)   │  │ (JS 业务封装)       │  │
│  └────────┬────────┘  └──────┬───────┘  └─────────┬──────────┘  │
│           │                  │                     │              │
│           ▼                  ▼                     ▼              │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │              NativeModules / TurboModules Registry         │  │
│  │                                                            │  │
│  │  FaceDetectorModule  VideoPlayerModule  BLEManagerModule   │  │
│  └──────────────────────┬─────────────────────────────────────┘  │
│                         │                                        │
└─────────────────────────┼────────────────────────────────────────┘
                          │
        ══════════════════╪══════════════════
           Bridge / JSI   │  (根据架构选择)
        ══════════════════╪══════════════════
                          │
┌─────────────────────────┼────────────────────────────────────────┐
│            ANDROID NATIVE (Kotlin/Java)                           │
│                         │                                        │
│  ┌──────────────────────┴──────────────────────────────────────┐ │
│  │              Native Module Implementations                   │ │
│  │                                                              │ │
│  │  ┌────────────────┐  ┌───────────────┐  ┌────────────────┐  │ │
│  │  │FaceDetector    │  │VideoPlayer    │  │BLEManager      │  │ │
│  │  │Module.kt       │  │Module.kt      │  │Module.kt       │  │ │
│  │  │                │  │               │  │                │  │ │
│  │  │- detectFace()  │  │- play(url)    │  │- startScan()   │  │ │
│  │  │- processFrame()│  │- pause()      │  │- connect(addr) │  │ │
│  │  │- onFaceFound() │  │- seekTo(ms)   │  │- sendData()    │  │ │
│  │  │  (EventEmitter)│  │- onProgress() │  │- onDeviceFound │  │ │
│  │  └────────────────┘  └───────────────┘  └────────────────┘  │ │
│  │                                                              │ │
│  │  ┌────────────────────────────────────────────────────────┐  │ │
│  │  │           原生 SDK / 底层能力                            │  │ │
│  │  │  - ML Kit Face Detection (Google)                       │  │ │
│  │  │  - ExoPlayer (Google)                                   │  │ │
│  │  │  - Android BLE API (Android SDK)                        │  │ │
│  │  └────────────────────────────────────────────────────────┘  │ │
│  └──────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────┘
```

### 核心技术选型

| 通信方式 | 适用场景 | JS 侧 API 风格 | 性能 |
|---------|---------|---------------|------|
| **Native Modules (Bridge)** | 低频方法调用，兼容旧版本 | `NativeModules.Xxx.call()` (Promise) | 中 |
| **TurboModules (JSI)** | 高频调用，新架构首选 | `NativeModules.Xxx.call()` (同步/Promise) | 高 |
| **EventEmitter** | Native → JS 事件推送 | `NativeEventEmitter.addListener()` | 中-高 |
| **Native UI Component** | 嵌入原生 View | `<RCTXxxView />` 直接声明 | 高 |

---

## 第六层：RN 混合开发 —— 原生模块封装实战（下）完整实现

### Step 1：定义 TypeScript 接口（类型安全）

```typescript
// src/native/BLETypes.ts
export interface BLEDevice {
  id: string;
  name: string;
  rssi: number;
  services: string[];
}

export interface BLEConnectionState {
  deviceId: string;
  state: 'connecting' | 'connected' | 'disconnected';
}

// src/native/BLEManager.ts
import { NativeModules, NativeEventEmitter, Platform } from 'react-native';

const { BLEManagerModule } = NativeModules;

// 类型安全的封装
class BLEManager {
  private eventEmitter: NativeEventEmitter;
  
  constructor() {
    // NativeEventEmitter 从 NativeModule 读取 supportedEvents
    this.eventEmitter = new NativeEventEmitter(BLEManagerModule);
  }

  // ① 方法调用（返回 Promise）
  async startScan(serviceUUIDs: string[]): Promise<void> {
    if (Platform.OS === 'android') {
      // Android 需要位置权限
      await this.requestLocationPermission();
    }
    return BLEManagerModule.startScan(serviceUUIDs);
  }

  async connect(deviceId: string): Promise<void> {
    return BLEManagerModule.connect(deviceId);
  }

  async sendData(deviceId: string, data: number[]): Promise<void> {
    return BLEManagerModule.sendData(deviceId, data);
  }

  // ② 事件监听（Native → JS 推送）
  onDeviceFound(callback: (device: BLEDevice) => void) {
    return this.eventEmitter.addListener('onDeviceFound', callback);
  }

  onConnectionStateChanged(callback: (state: BLEConnectionState) => void) {
    return this.eventEmitter.addListener('onConnectionStateChanged', callback);
  }

  onDataReceived(callback: (data: { deviceId: string; data: number[] }) => void) {
    return this.eventEmitter.addListener('onDataReceived', callback);
  }
}

export default new BLEManager();
```

### Step 2：Android 侧实现（Bridge 模式 — 兼容旧架构）

```kotlin
// android/app/src/main/kotlin/com/yourapp/BLEManagerModule.kt
package com.yourapp

import com.facebook.react.bridge.*
import com.facebook.react.modules.core.DeviceEventManagerModule
import android.bluetooth.*
import android.bluetooth.le.*

class BLEManagerModule(reactContext: ReactApplicationContext) 
    : ReactContextBaseJavaModule(reactContext) {

    // --- BuildConfig 配置：是否启用新架构 ---
    companion object {
        const val NAME = "BLEManagerModule"
    }

    private val bluetoothAdapter: BluetoothAdapter? 
        = BluetoothAdapter.getDefaultAdapter()
    private var bluetoothGatt: BluetoothGatt? = null
    private val leScanner: BluetoothLeScanner? 
        = bluetoothAdapter?.bluetoothLeScanner

    // ① 模块名称（JS 侧通过 NativeModules.BLEManagerModule 访问）
    override fun getName(): String = NAME

    // ② 声明支持的事件类型（JS 侧 NativeEventEmitter 读取）
    override fun getSupportedEvents(): List<String> = listOf(
        "onDeviceFound",
        "onConnectionStateChanged",
        "onDataReceived"
    )

    // ③ 发送事件到 JS
    private fun sendEvent(eventName: String, params: WritableMap?) {
        reactApplicationContext
            .getJSModule(DeviceEventManagerModule.RCTDeviceEventEmitter::class.java)
            .emit(eventName, params)
    }

    // ④ 扫描 BLE 设备
    @ReactMethod
    fun startScan(serviceUUIDs: ReadableArray?, promise: Promise) {
        try {
            if (bluetoothAdapter?.isEnabled != true) {
                promise.reject("BLE_DISABLED", "蓝牙未开启")
                return
            }

            val scanCallback = object : ScanCallback() {
                override fun onScanResult(callbackType: Int, result: ScanResult) {
                    val device = Arguments.createMap().apply {
                        putString("id", result.device.address)
                        putString("name", result.device.name ?: "Unknown")
                        putInt("rssi", result.rssi)
                        // services...
                    }
                    sendEvent("onDeviceFound", device)
                }

                override fun onScanFailed(errorCode: Int) {
                    promise.reject("SCAN_FAILED", "扫描失败: $errorCode")
                }
            }

            leScanner?.startScan(scanCallback)
            promise.resolve(null)
        } catch (e: Exception) {
            promise.reject("SCAN_ERROR", e.message)
        }
    }

    // ⑤ 连接设备
    @ReactMethod
    fun connect(deviceId: String, promise: Promise) {
        try {
            val device = bluetoothAdapter?.getRemoteDevice(deviceId)
            if (device == null) {
                promise.reject("DEVICE_NOT_FOUND", "设备不存在")
                return
            }

            bluetoothGatt = device.connectGatt(
                reactApplicationContext, 
                false, 
                gattCallback
            )
            promise.resolve(null)
        } catch (e: Exception) {
            promise.reject("CONNECT_ERROR", e.message)
        }
    }

    // ⑥ GATT 回调（处理 BLE 连接和数据）
    private val gattCallback = object : BluetoothGattCallback() {
        override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
            val params = Arguments.createMap().apply {
                putString("deviceId", gatt.device.address)
                putString("state", when (newState) {
                    BluetoothProfile.STATE_CONNECTED -> "connected"
                    BluetoothProfile.STATE_DISCONNECTED -> "disconnected"
                    else -> "connecting"
                })
            }
            sendEvent("onConnectionStateChanged", params)
        }

        override fun onCharacteristicChanged(
            gatt: BluetoothGatt, 
            characteristic: BluetoothGattCharacteristic
        ) {
            val params = Arguments.createMap().apply {
                putString("deviceId", gatt.device.address)
                putArray("data", Arguments.fromList(
                    characteristic.value.toList()
                ))
            }
            sendEvent("onDataReceived", params)
        }
    }

    // ⑦ 发送数据到 BLE 设备
    @ReactMethod
    fun sendData(deviceId: String, data: ReadableArray, promise: Promise) {
        try {
            val service = bluetoothGatt?.getService(UUID.fromString(SERVICE_UUID))
            val characteristic = service?.getCharacteristic(UUID.fromString(CHAR_UUID))
            
            val byteArray = ByteArray(data.size()) { i -> data.getInt(i).toByte() }
            characteristic?.value = byteArray
            val success = bluetoothGatt?.writeCharacteristic(characteristic) ?: false
            
            if (success) promise.resolve(null)
            else promise.reject("WRITE_FAILED", "写入失败")
        } catch (e: Exception) {
            promise.reject("SEND_ERROR", e.message)
        }
    }

    @ReactMethod
    fun addListener(eventName: String) {
        // RN 0.65+ 需要此方法支持 NativeEventEmitter
    }

    @ReactMethod
    fun removeListeners(count: Int) {
        // RN 0.65+ 需要此方法支持 NativeEventEmitter
    }
}
```

### Step 3：Android 侧注册模块

```kotlin
// android/app/src/main/kotlin/com/yourapp/BLEManagerPackage.kt
package com.yourapp

import com.facebook.react.ReactPackage
import com.facebook.react.bridge.NativeModule
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.uimanager.ViewManager

class BLEManagerPackage : ReactPackage {
    override fun createNativeModules(
        reactContext: ReactApplicationContext
    ): List<NativeModule> {
        return listOf(BLEManagerModule(reactContext))
    }

    override fun createViewManagers(
        reactContext: ReactApplicationContext
    ): List<ViewManager<*, *>> {
        return emptyList()
    }
}
```

```kotlin
// android/app/src/main/kotlin/com/yourapp/MainApplication.kt
// 在 getPackages() 中添加：
override fun getPackages(): List<ReactPackage> {
    return PackageList(this).packages.apply {
        add(BLEManagerPackage())  // ← 注册自定义模块
    }
}
```

### Step 4：JS 侧使用示例

```typescript
// src/screens/BLEScreen.tsx
import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, FlatList, TouchableOpacity, StyleSheet } from 'react-native';
import BLEManager, { BLEDevice } from '../native/BLEManager';

export default function BLEScreen() {
  const [devices, setDevices] = useState<BLEDevice[]>([]);
  const [scanning, setScanning] = useState(false);

  useEffect(() => {
    // 监听设备发现
    const deviceSub = BLEManager.onDeviceFound((device: BLEDevice) => {
      setDevices(prev => {
        const exists = prev.find(d => d.id === device.id);
        if (exists) {
          return prev.map(d => d.id === device.id ? device : d);
        }
        return [...prev, device];
      });
    });

    // 监听连接状态
    const connSub = BLEManager.onConnectionStateChanged((state) => {
      console.log(`设备 ${state.deviceId}: ${state.state}`);
    });

    return () => {
      deviceSub.remove();
      connSub.remove();
    };
  }, []);

  const handleStartScan = useCallback(async () => {
    try {
      setScanning(true);
      await BLEManager.startScan([]);
    } catch (err) {
      console.error('扫描失败:', err);
    } finally {
      setScanning(false);
    }
  }, []);

  const handleConnect = useCallback(async (deviceId: string) => {
    try {
      await BLEManager.connect(deviceId);
    } catch (err) {
      console.error('连接失败:', err);
    }
  }, []);

  const renderDevice = ({ item }: { item: BLEDevice }) => (
    <TouchableOpacity 
      style={styles.deviceItem}
      onPress={() => handleConnect(item.id)}
    >
      <Text style={styles.deviceName}>{item.name}</Text>
      <Text style={styles.deviceId}>{item.id}</Text>
      <Text style={styles.rssi}>RSSI: {item.rssi}</Text>
    </TouchableOpacity>
  );

  return (
    <View style={styles.container}>
      <TouchableOpacity 
        style={[styles.scanButton, scanning && styles.scanning]}
        onPress={handleStartScan}
        disabled={scanning}
      >
        <Text>{scanning ? '扫描中...' : '开始扫描'}</Text>
      </TouchableOpacity>
      
      <FlatList
        data={devices}
        keyExtractor={d => d.id}
        renderItem={renderDevice}
        windowSize={5}
      />
    </View>
  );
}
```

### Step 5：线程安全与性能优化总结

```
┌──────────────────────────────────────────────────────────────────┐
│                    原生模块封装最佳实践                             │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  1. 线程模型：                                                     │
│     - Native Module 方法默认在 JS Native Modules Thread 执行       │
│     - 耗时操作（蓝牙扫描、网络请求）必须切到后台线程                 │
│     - UI 操作必须通过 runOnUiThread 切换到主线程                    │
│     - 回调 JS 时注意线程安全（ReactContext.getJSModule() 已处理）    │
│                                                                   │
│  2. 性能优化要点：                                                 │
│     - 高频数据传输（蓝牙、传感器）：使用 EventEmitter 批量发送       │
│     - 避免在 Bridge 上传输大量数据，改用文件路径或共享内存           │
│     - 对于巨量数据（图片、视频帧），优先使用 Native UI Component     │
│     - 按需监听事件，组件卸载时 remove() 监听器（防止内存泄漏）       │
│                                                                   │
│  3. TurboModule 迁移准备：                                         │
│     - 使用 @ReactModule 注解（Java）/ RCT_EXPORT_MODULE（ObjC）     │
│     - 方法签名统一使用 Promise/Callback 返回                       │
│     - 避免使用 ReadableMap/WritableMap 以外的非标准类型             │
│     - 创建 TurboModule 接口（C++ spec 文件）实现 JSI 绑定           │
│                                                                   │
│  4. 错误处理：                                                     │
│     - 所有 @ReactMethod 必须 try-catch 并 reject promise           │
│     - 统一错误码规范（ERR_NO_BLE、ERR_PERMISSION 等）               │
│     - Native 侧 crash 不应导致 JS 侧白屏                           │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 附录：面试常见追问与回答要点

| 追问 | 回答要点 |
|------|---------|
| "为什么 RN 的 Bridge 要设计成异步的？" | JS 是单线程，同步调用会阻塞 UI 响应；异步批处理可以减少通信开销，但代价是实时性差 |
| "JSI 的同步调用会不会阻塞 JS 线程？" | 会！所以 JSI 虽支持同步，但耗时操作仍应异步。同步适用于 getter/简单属性访问 |
| "Hermes 引擎相比 JSC/V8 有什么优势？" | 预编译（AOT）减小 APK 体积，启动速度更快，内存占用更低（专为移动端优化），支持 JSI |
| "Fabric 和 React Fiber 是什么关系？" | Fabric 是 RN 的渲染器，Fiber 是 React 的协调器。Fabric 支持 Fiber 的优先级调度，使 Concurrent Mode 成为可能 |
| "如何在现有项目中逐步迁移到 New Architecture？" | 1) 升级 RN 0.68+ 2) 安装 react-native-codegen 3) 启用 newArchEnabled 4) 逐个迁移 Native Module 为 TurboModule |
| "FlatList 和 FlashList 的区别？" | FlashList 由 Shopify 开发，使用回收复用 + 预估高度 + 更少的内存占用，性能比 FlatList 提升 5-10x |
| "RN 动画如何做到 60fps？" | useNativeDriver 让动画在 Native 侧执行（不经过 Bridge）+ LayoutAnimation 用于布局动画 + Reanimated 库（JSI 线程执行动画逻辑） |
| "RN 和 Flutter 的性能差异根源是什么？" | RN 桥接原生 View 通信有开销；Flutter 自绘引擎直接操作 GPU，不经过平台控件。但 RN New Architecture 正在缩小这个差距 |
| "原生模块如何处理 Android 的 Activity 生命周期？" | 通过 `LifecycleEventListener` 在 `onHostResume/onHostPause/onHostDestroy` 中管理资源 |

---

> **本文档涵盖了 React Native 面试中从 Bridge 通信原理 → JSI/Fabric 新架构 → 原生模块封装的完整知识链。重点理解：旧架构的 JSON Bridge 瓶颈、JSI 如何实现同步零拷贝通信、Fabric 的同步渲染管线，以及原生模块从 Bridge 到 TurboModule 的封装演进。建议结合 RN 0.68+ 项目实际操作以加深理解。**
