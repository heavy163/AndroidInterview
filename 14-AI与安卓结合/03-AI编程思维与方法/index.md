# 03 AI 编程思维与方法

> 面试内容：AI 辅助代码重构策略、自动化测试用例生成、异常日志模式识别、AST 级别理解、以及用 AI 重构老旧模块（从 MVP 到 MVVM）的完整实战

---

## 一、面试高频问题（3+）

### 1.1 AI 辅助代码重构的策略是什么？如何识别坏味道并审查 AI 的修改建议？

**参考答案：**

AI 辅助代码重构遵循一个三层循环：「**识别坏味道 → AI 生成重构建议 → 人工审查与验收**」。这个循环不是一次性的，而是迭代进行的——每轮重构后重新评估代码质量，直至满足团队标准。

#### 第一阶段：识别坏味道

坏味道（Code Smell）的识别来源有三类：

| 来源 | 工具/方法 | 示例 |
|------|----------|------|
| **静态分析工具** | detekt / ktlint / Android Lint / SonarQube | 过长方法（>80行）、过深嵌套（>4层）、God Class（>500行） |
| **AI 代码审查** | GitHub Copilot Chat / Cursor Review | 将整个文件或模块粘贴给 AI，让它列出潜在的坏味道和重构建议 |
| **人工敏锐度** | 开发者经验 | "这个类做了太多事情""这段逻辑重复了 3 次""命名完全看不出意图" |

```kotlin
// 典型坏味道示例：God Activity + 多重职责混合
class OldMainActivity : AppCompatActivity() {
    // ❌ 坏味道清单：
    // 1. God Object：承担了 UI 渲染 + 网络请求 + 数据解析 + 缓存管理
    // 2. 过长方法：onCreate() 超过 200 行
    // 3. 硬编码：URL、超时时间、缓存大小全部硬编码
    // 4. 主线程 IO：直接用 HttpURLConnection 在主线程请求
    // 5. 上帝依赖：直接 new 依赖，无 DI
    
    private val cache = HashMap<String, String>()
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        
        Thread {
            val url = URL("https://api.example.com/data")
            val json = url.readText()
            val items = Gson().fromJson(json, Array<Item>::class.java)
            runOnUiThread {
                recyclerView.adapter = ItemAdapter(items.toList())
            }
        }.start()
    }
}
```

#### 第二阶段：AI 生成重构建议

给 AI 的 Prompt 需要包含三个关键要素：

```
【重构 Prompt 模板】
1. 上下文：当前架构、目标架构、约束条件（如：不能改接口签名）
2. 坏味道清单：明确指出具体问题
3. 期望输出：具体的重构方案 + 修改前后对比 + 风险点

示例 Prompt：
"这是一个使用 MVP 模式的安卓老旧模块，请将其重构为 MVVM（ViewModel + StateFlow）。
约束：不能修改 Repository 层接口，需保持向后兼容。
请先列出当前代码的坏味道，然后给出逐步重构方案，每步标注风险等级。"
```

**AI 重构建议的常见模式：**

| 重构类型 | AI 能力 | 示例操作 |
|---------|:------:|---------|
| 方法提取 (Extract Method) | ★★★★★ | 自动识别可提取的代码块，生成有意义的方法名 |
| 类拆分 (Extract Class) | ★★★★☆ | 按职责将 God Class 拆分为多个单一职责类 |
| 引入设计模式 | ★★★☆☆ | 将 if-else 链替换为策略模式、将直接依赖替换为 DI |
| 架构迁移 | ★★★☆☆ | MVP → MVVM、RxJava → Coroutines+Flow |
| 命名优化 | ★★★★★ | 根据上下文生成符合团队规范的命名 |

#### 第三阶段：人工审查（核心不可跳过）

人工审查是 AI 辅助重构中最关键的一环。审查清单如下：

```
┌────────────────────────────────────────────────────────────────┐
│                   AI 重构代码人工审查清单                         │
├────────────┬───────────────────────────────────────────────────┤
│ 行为等价性 │ 重构前后行为是否完全一致？用单元测试验证             │
│ 边界条件   │ AI 是否遗漏了 null、空列表、网络异常等边界？         │
│ 副作用     │ 是否引入了不必要的异步、状态变更顺序是否改变？       │
│ 可读性     │ AI 的重构是否"过度设计"？简单逻辑是否有必要拆成 5 个类│
│ 性能       │ 是否引入了 N+1 查询、不必要的对象创建？              │
│ 惯用性     │ 是否符合 Kotlin 惯用法？（let/apply/also 的选择）    │
│ 安全性     │ 是否处理了 SSL 验证、数据脱敏、权限检查？            │
└────────────┴───────────────────────────────────────────────────┘
```

**追问：什么情况下不应该让 AI 参与重构？**

以下场景不建议让 AI 主导重构：
- **涉及金融交易/支付逻辑的代码**：任何等价性偏差都可能造成资金损失
- **复杂的多线程/并发逻辑**：AI 对竞态条件的分析能力有限
- **加密/安全协议实现**：AI 可能在不知情的情况下削弱安全强度
- **团队尚未建立完善的测试覆盖**：没有安全网的重构极其危险

---

### 1.2 AI 如何辅助自动化测试用例生成？有哪些实战技巧？

**参考答案：**

AI 辅助测试生成不是"一键生成所有测试"，而是与人类开发者形成协作流水线：

```
开发者编写 Given-When-Then 骨架 → AI 填充断言与边界 → 人工审查与补充
```

#### 生成的五个层次

| 层次 | AI 能力 | 典型 Prompt |
|:---:|---------|------------|
| **L1: 样板填充** | ★★★★★ | "为这个 ViewModel 生成 JUnit5 + MockK 测试类骨架" |
| **L2: Happy Path** | ★★★★★ | "为 login() 方法生成正常登录流程的测试用例" |
| **L3: 异常路径** | ★★★★☆ | "补充网络超时、服务端 500、Token 过期的异常用例" |
| **L4: 边界条件** | ★★★☆☆ | "补充参数为空字符串、null、超长字符串的测试" |
| **L5: 业务规则** | ★★☆☆☆ | "当用户连续 3 次登录失败后，应锁定账户 15 分钟" |

**实战 Prompt 技巧：**

```
技巧 1：提供被测代码的完整上下文
❌ "给 login 方法写测试"
✅ "这是 LoginViewModel 的完整代码[粘贴代码]，依赖 UserRepository(接口)和 AuthManager(单例)，
   请用 MockK 生成单元测试，覆盖：成功登录、密码错误、网络异常、Token 过期四种场景"

技巧 2：指定测试框架和命名规范
"使用 JUnit5 + MockK + Turbine(用于 StateFlow 测试)，测试方法命名遵循:
 `方法名_场景_预期结果()` 格式，例如 `login_validCredentials_returnsSuccess()`

技巧 3：逐步迭代
第 1 轮：生成 Happy Path 测试
第 2 轮：补充异常场景测试
第 3 轮：审查并补充 AI 遗漏的边界条件
```

**追问：AI 生成的测试有哪些常见缺陷？**

| 缺陷 | 表现 | 修复方式 |
|------|------|---------|
| **假通过测试** | 断言永远为 true，如 `assertThat(result).isNotNull` 但没有验证具体值 | 要求 AI 对关键字段做精确断言 |
| **缺少 verify** | 只验证返回值未验证副作用（如未验证 saveToCache 是否被调用） | 补充 `verify { dependency.method() }` |
| **测试过于具体** | 断言引用了内部实现细节，重构即破裂 | 改为行为层面断言 |
| **忽略协程调度** | 在测试中直接调用 suspend 函数但未处理 Dispatcher | 使用 `StandardTestDispatcher` + `runTest` |
| **Mock 过度** | 每个依赖都 Mock，导致测试与实现强绑定 | 对值对象用真实实例，只 Mock 有副作用的外部依赖 |

---

### 1.3 AI 辅助异常日志分析如何进行模式识别？

**参考答案：**

异常日志分析是 AI 的强项——AI 擅长从海量日志中识别重复模式、关联分散信息、推断根因。典型工作流如下：

#### 三步工作流

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────┐
│  Step 1       │ ──► │  Step 2           │ ──► │  Step 3      │
│  日志清洗     │     │  AI 模式识别      │     │  根因推断    │
│  (去噪+结构化)│     │  (聚类+关联)      │     │  (定因+建议) │
└──────────────┘     └──────────────────┘     └──────────────┘
```

**Step 1：日志清洗与结构化**

给 AI 的日志必须经过预处理。原始 Crash 日志通常包含大量无关信息（时间戳、线程 ID、内存地址），应在提交给 AI 前做初步清洗：

```bash
# 过滤关键行
grep -E "(FATAL|ANR|OutOfMemory|NullPointer|Signal)" crash.log \
  | sed 's/[0-9a-f]\{8,\}/ADDR/g'   # 匿名化内存地址
```

**Step 2：AI 模式识别 Prompt**

```
【日志分析 Prompt 模板】
"以下是过去 7 天收集的 50 个 Crash 日志（已匿名化），请分析：
1. 按 Crash 类型聚类（同类问题归为一组），列出每组的关键特征签名
2. 找出高频 Crash 的时间分布规律（是否集中在某个版本/某个时间窗口）
3. 对于 Top 3 高频 Crash，推断可能的根因并给出修复方向
4. 标注哪些 Crash 之间存在因果关联（A Crash 可能触发了 B Crash）

[粘贴日志]"
```

**AI 的四种模式识别能力：**

| 模式类型 | AI 示例 | 传统方式难度 |
|---------|--------|:----------:|
| **堆栈聚类** | 提取异常类型 + 关键帧（项目代码的第一帧）作为 Crash 指纹 | 中（需正则+去重逻辑） |
| **时序关联** | 识别"OOM 前 30 秒必有 Bitmap 分配失败"的关联模式 | 高（需人工交叉分析） |
| **版本归因** | 发现 v3.2.1 起某 Crash 数量暴涨 300%，与某次提交高度相关 | 中（需关联 Git+Crash 数据） |
| **设备/系统关联** | 发现 95% 的某 Crash 集中在 Android 12、特定芯片组上 | 低（统计即可发现） |

**Step 3：根因推断示例**

```kotlin
// 日志片段（堆栈关键帧）
// Caused by: java.lang.IllegalStateException:
//   Fragment already added: VideoPlayerFragment{abc123}
//     at FragmentManager.addFragment()

// AI 根因推断输出：
// 【根因】Fragment 重复添加的典型并发问题
// 【触发条件】用户快速点击导航按钮 → 两次 add 操作进入消息队列
//            → 第一次 add 尚未 commit → 第二次 add 检测到同一实例
// 【修复方案】
//   1. 在 add 前调用 findFragmentByTag 检查是否已存在
//   2. 对导航点击做防抖处理（300ms）
//   3. 使用 Fragment 事务的 commitNow() 确保同步执行
// 【风险】方案 3 可能引发 IllegalStateException(onSaveInstanceState 之后)，
//         推荐使用方案 1+2
```

**追问：AI 日志分析有哪些常见误判？**

- **误判根因**：AI 可能将"症状"误判为"病因"（如将 OOM 归因于图片加载，实际是内存泄漏累积导致）
- **忽略环境差异**：AI 分析的日志可能来自不同设备/系统版本，但 AI 不易区分
- **建议过于通用**：AI 给出的修复方案可能缺乏项目特定的上下文（如"检查权限"但未说明具体权限）

---

## 二、AI 代码重构的 AST 级别理解

### 2.1 什么是 AST？AI 如何在 AST 层面理解和重构代码？

**参考答案：**

AST（Abstract Syntax Tree，抽象语法树）是源代码的结构化表示，将代码从字符串转化为树形数据结构。AI 辅助重构之所以强大，核心就在于它能理解 AST 而不是仅做文本替换。

```
                         parse                    analyze
源代码（字符串）      ────────►    AST（树）     ────────►   语义理解
    ↓                                                          ↓
文本替换（sed/regex）             结构化变换               意图驱动的重构
（传统工具）                      （AI 工具）              （AI 高级能力）
```

#### Kotlin 代码 → AST 示例

```kotlin
val name: String = user.getName() ?: "unknown"
```

对应的 AST 结构（简化表示）：

```
PropertyDeclaration
├── ValKeyword
├── Identifier("name")
├── TypeReference("String")
├── Eq
└── Initializer
    └── ElvisExpression
        ├── LeftOperand
        │   └── DotExpression
        │       ├── Identifier("user")
        │       └── FunctionCall("getName")
        └── RightOperand
            └── StringLiteral("unknown")
```

#### AI 在 AST 层面的三种操作模式

| 操作 | AST 节点级别 | 示例 | 安全性 |
|------|------------|------|:-----:|
| **重命名** | 遍历所有 Identifier 节点，替换引用 | 变量/方法/类重命名 | ★★★★★ |
| **提取** | 选定子树 → 提取为新函数/新类 | Extract Method / Extract Class | ★★★★☆ |
| **迁移** | 识别模式子树 → 替换为等价新模式 | RxJava Observable → Kotlin Flow | ★★★☆☆ |

**追问：为什么 AI 在 AST 层面重构比文本替换更安全？**

文本替换（`sed`/正则）不理解代码结构，容易产生以下问题：

```kotlin
// 场景：要将变量 "user" 重命名为 "currentUser"
// 文本替换的陷阱：
// 1. 字符串内的 "user" 也会被误改："User not found" → "currentUser not found"
// 2. 注释中的 "user" 也被替换
// 3. 其他作用域的 "user" 变量也会受影响（如内部类的同名变量）

// AI 基于 AST 的重命名：
// 精确遍历 AST 的 Identifier 节点 → 仅替换指向该符号的引用
// → 安全、精确、零副作用
```

#### AST 级别重构的边界与局限

AI 的 AST 理解能力并非完美。以下场景容易出错：

1. **宏/注解处理器生成的代码**：编译期生成的代码不在源码 AST 中，AI 无法感知
2. **反射调用**：AST 中无法追踪 `Class.forName("com.xxx.Foo")` 的依赖关系
3. **跨语言边界**：Kotlin ↔ C++（JNI）的调用关系无法通过单语言 AST 追踪
4. **动态特性**：Kotlin 的 `by` 委托、属性代理在 AST 层面有特殊表示，AI 可能误判

---

## 三、测试生成的边界条件覆盖

### 3.1 AI 在测试生成中如何系统性地覆盖边界条件？

**参考答案：**

边界条件是 AI 测试生成中最容易遗漏的部分。以下是系统化的边界条件覆盖策略。

#### 边界条件分类框架

```
┌───────────────────────────────────────────────────────────────────┐
│                      边界条件分类体系                               │
├──────────────┬────────────────────────────────────────────────────┤
│ 空值边界     │ null、空字符串""、空列表[]、空 Map、Optional.empty  │
│ 数值边界     │ Int.MIN_VALUE、0、-0、Float.NaN、Float.Infinity     │
│ 集合边界     │ 空集合、单元素、极大集合（OOM 风险）、重复元素       │
│ 状态边界     │ 未初始化、已释放、已关闭、正在加载中                  │
│ 并发边界     │ 多线程同时写、读时被修改（ConcurrentModification）   │
│ 资源边界     │ 磁盘满、网络断开、内存不足、文件权限被拒绝           │
│ 输入边界     │ 超长字符串(>1MB)、特殊Unicode、SQL注入字符、XSS向量  │
│ 时间边界     │ 时间戳为0、负值、2038年溢出、时区边界(DST切换)      │
└──────────────┴────────────────────────────────────────────────────┘
```

#### AI 补充边界条件的 Prompt 策略

```
【边界条件 Prompt 模板】
"这是 UserProfileViewModel 的测试（已覆盖 Happy Path），
请补充以下类别的边界条件测试：

1. 空值边界：所有可为 null 的参数传入 null 的行为
2. 集合边界：返回列表为空的 UI 状态
3. 状态边界：Loading → Success → 再次触发加载时的状态
4. 输入边界：用户名超过 100 字符、包含 emoji、包含 SQL 注入字符

对每个边界条件，明确标注：
- 当前代码是否已处理（如否则标记为潜在 Bug）
- 预期行为是什么
- 是否需要修改生产代码"
```

#### 实战：边界条件驱动的 Bug 发现

```kotlin
// 被测代码
fun formatFileSize(bytes: Long): String {
    return when {
        bytes < 1024 -> "$bytes B"
        bytes < 1024 * 1024 -> "${bytes / 1024} KB"
        else -> "${bytes / (1024 * 1024)} MB"
    }
}

// AI 生成的边界条件测试（部分）
@Test
fun `formatFileSize negative value returns meaningful string`() {
    val result = formatFileSize(-1)
    // AI 发现：对于 -1，when 的 bytes < 1024 分支返回 "-1 B"
    // 这可能是预期行为（表示未知大小），也可能需要特殊处理
    // 建议：明确需求，如果 -1 是特殊值应提前处理
}

@Test
fun `formatFileSize very large value does not overflow`() {
    val result = formatFileSize(Long.MAX_VALUE)
    // AI 发现：bytes / (1024 * 1024) 不会溢出因为结果是 Long
    // 但如果是 Int.MAX_VALUE / 1024 * 1024 这样的中间计算可能溢出
    // 建议：使用 bytes / 1_048_576 直接除，避免中间值溢出风险
}

@Test
fun `formatFileSize zero bytes returns 0 B`() {
    assertThat(formatFileSize(0)).isEqualTo("0 B")
}
```

**追问：什么边界条件 AI 最容易遗漏？**

- **多字段组合边界**：AI 擅长单字段边界，但 `用户名非空 + 密码为空 + 验证码过期` 的组合边界极易遗漏
- **时序边界**：`onStart 回调 → 立刻 onStop → 立刻 onStart` 这种快速切换，AI 通常不会自动生成
- **跨模块联动边界**：模块 A 抛异常 → 模块 B 收到异常后的状态转换 → 模块 C 的 UI 表现

---

## 四、AI 辅助编程工作流

### 4.1 如何构建高效的 AI 辅助编程工作流？

**参考答案：**

AI 辅助编程不是"想到什么问什么"，而是需要建立系统化的工作流。以下是经过实战验证的四阶段流程：

```
┌─────────────────────────────────────────────────────────────────────┐
│                    AI 辅助编程四阶段工作流                             │
│                                                                     │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐        │
│  │ Phase 1  │──►│ Phase 2  │──►│ Phase 3  │──►│ Phase 4  │        │
│  │ 需求拆解 │   │ AI 生成   │   │ 审查验证  │   │ 迭代优化  │        │
│  │          │   │          │   │          │   │          │        │
│  │ 人工主导 │   │ AI 主导   │   │ 人工主导  │   │ 人机协作  │        │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘        │
│       ↓              ↓              ↓              ↓               │
│  用户故事分解    代码/测试生成   Review+测试   反馈修正循环            │
│  技术方案设计    PRD → Code    CI 通过确认   持续改进质量             │
└─────────────────────────────────────────────────────────────────────┘
```

#### Phase 1：需求拆解（人工主导，30% 时间）

这一阶段 AI 辅助有限。核心工作是：

```
1. 将用户故事拆解为可独立实现的子任务
2. 每个子任务需明确：输入/输出、边界条件、依赖关系
3. 确定哪些子任务适合 AI 生成（模板代码、CRUD、转换逻辑）
   哪些必须手写（核心算法、安全关键代码、架构决策）
```

#### Phase 2：AI 生成（AI 主导，20% 时间）

高效 Prompt 的四个要素：

| 要素 | 说明 | 示例 |
|------|------|------|
| **Role** | 定义 AI 的角色 | "你是一位资深 Android 架构师，精通 Kotlin 和 MVVM" |
| **Context** | 提供项目上下文 | "项目使用 Hilt DI、Retrofit、Room，最低 SDK 26" |
| **Constraint** | 明确约束 | "不能引入新依赖、需兼容现有 API 接口、遵循 Clean Architecture" |
| **Format** | 指定输出格式 | "先输出设计思路（<100 字），再输出完整代码，最后标注注意事项" |

#### Phase 3：审查验证（人工主导，30% 时间）

审查流水线：

```bash
# Step 1: 静态分析
./gradlew detekt lint ktlintCheck

# Step 2: AI 自查（让 AI 审查自己的代码）
# Prompt: "请审查这段代码[粘贴]，找出：潜在的空指针、线程安全问题、资源泄漏、性能隐患"

# Step 3: 运行测试
./gradlew test

# Step 4: 人工 Code Review（关注架构、安全、业务逻辑正确性）
```

#### Phase 4：迭代优化（人机协作，20% 时间）

这是 AI 辅助编程中最体现效率提升的阶段：

```
迭代 1: "生成的代码用了 !! 操作符，请改为安全调用 ?.let"
迭代 2: "StateFlow 的初始值应该用 Loading 而不是 null"
迭代 3: "提取这个重复的 try-catch 为扩展函数"
迭代 4: "给公共方法添加 KDoc 注释"
```

**追问：AI 辅助工作流中最大的效率陷阱是什么？**

最大的陷阱是**过度信任——跳过 Phase 3 审查验证**。开发者将 AI 代码直接合入，未经测试和审查，导致：
- 边界条件遗漏导致的线上 Crash
- 不符合团队规范的代码风格，增加维护成本
- AI 引入的不必要的抽象层次，降低可读性

黄金法则：**AI 写的每一行代码，都必须经过与手写代码同等严格的审查流程。**

---

## 五、实战：用 AI 重构老旧模块 —— 从 MVP 到 MVVM（上）

### 5.1 背景与目标

**场景设定**：一个电商 App 的商品详情模块，使用传统 MVP 架构，代码已有 3 年历史，多次打补丁后变得难以维护。现在需要用 AI 辅助将其重构为 MVVM 架构。

#### 重构前的代码画像

```
┌──────────────────────────────────────────────────────────────┐
│  重构对象：商品详情模块（ProductDetail）                        │
├──────────┬───────────────────────────────────────────────────┤
│ 文件数    │ 12 个（3 Activity + 4 Presenter + 3 Model + 2 Util│
│ 总行数    │ ~2800 行                                          │
│ 测试覆盖  │ ~15%（仅 2 个 Presenter 方法有测试）                │
│ 最大类    │ ProductDetailActivity: 847 行                     │
│ 最深层级  │ 6 层嵌套（if-for-if-when-if-try）                 │
├──────────┼───────────────────────────────────────────────────┤
│ 坏味道清单 │                                                   │
│ ● God Activity: 承担 UI + 网络 + 缓存 + 埋点                  │
│ ● Presenter 持有 Activity 引用 → 内存泄漏风险                  │
│ ● 多处手写 JSON 解析而非用 Gson/Moshi                          │
│ ● 散落各处的 SharedPreferences 读写（无统一管理）              │
│ ● 图片加载逻辑直接写在 Activity 中（Glide 调用散落 7 处）      │
│ ● 埋点代码与业务逻辑耦合                                       │
└──────────────────────────────────────────────────────────────────────┘
```

#### 重构目标架构

```
表示层（Presentation）
├── ProductDetailFragment         ← 负责 UI 渲染和用户交互
├── ProductDetailViewModel        ← 持有 UI 状态（StateFlow）
│
领域层（Domain）
├── GetProductDetailUseCase       ← 单一职责的业务逻辑
├── AddToCartUseCase
├── TrackProductViewUseCase       ← 埋点逻辑独立
│
数据层（Data）
├── ProductRepository             ← 统一数据源（网络 + 缓存策略）
├── ProductCache                  ← 内存缓存 + 磁盘缓存
└── ProductApi                    ← Retrofit 接口
```

### 5.2 Phase 1 & 2：理解现状与逐步重构

#### Step 1：让 AI 分析现有代码

```
【Prompt】
"以下是 ProductDetail 模块的全部代码[粘贴 12 个文件]，
请做以下分析：
1. 画出各文件之间的依赖关系图（谁依赖谁）
2. 标记每个类的职责数量（单一职责原则检查）
3. 列出可以安全删除的死代码（如未使用的 import、私有方法、注释掉的代码）
4. 按优先级排序重构步骤（高→低风险）"
```

**AI 输出示例（依赖关系分析）：**

```
ProductDetailActivity
├──→ ProductDetailPresenter（紧耦合，持有引用）
│   ├──→ ProductApi（直接调用，无 Repository 抽象）
│   ├──→ SharedPreferences（散落 4 处）
│   └──→ ProductDetailActivity（反向引用！← 内存泄漏源）
├──→ Glide（散落 7 处直接调用）
├──→ Gson（3 处手写解析，2 处在 Activity，1 处在 Presenter）
└──→ AnalyticsUtil（埋点调用散落 11 处）

死代码发现：
✗ Presenter 中未使用的 loadSimilarProducts() 方法（调了但结果未使用）
✗ Activity 中注释掉的旧版布局切换逻辑（28 行注释代码）
✗ 3 个未使用的 import
```

#### Step 2：按优先级逐步重构

**重构步骤规划：**

| 优先级 | 步骤 | 风险 | AI 依赖度 |
|:---:|------|:---:|:---:|
| P0 | 补充测试（确保重构安全网） | 低 | ★★★★☆ |
| P1 | 提取 Repository 层（数据源统一） | 中 | ★★★★★ |
| P2 | 创建 ViewModel + StateFlow | 中 | ★★★★☆ |
| P3 | 改造 UI 层为 Fragment + 观察 StateFlow | 高 | ★★☆☆☆ |
| P4 | 提取 UseCase（业务逻辑下沉） | 低 | ★★★★☆ |
| P5 | 引入 Hilt DI | 中 | ★★★☆☆ |
| P6 | 清理死代码 + 统一代码风格 | 低 | ★★★★★ |

**P1 实战：提取 Repository**

```kotlin
// === 重构前（Present 中的代码片段）===
class ProductDetailPresenter(
    private val activity: ProductDetailActivity  // ❌ 持有 Activity 引用
) {
    fun loadProduct(productId: String) {
        activity.showLoading()
        Thread {
            try {
                val url = URL("https://api.example.com/product/$productId")
                val json = url.readText()
                val product = Gson().fromJson(json, Product::class.java)
                // 缓存到 SP
                activity.getSharedPreferences("cache", Context.MODE_PRIVATE)
                    .edit().putString("product_$productId", json).apply()
                activity.runOnUiThread { activity.showProduct(product) }
            } catch (e: Exception) {
                // 尝试从 SP 读缓存
                val cached = activity.getSharedPreferences("cache", Context.MODE_PRIVATE)
                    .getString("product_$productId", null)
                if (cached != null) {
                    val product = Gson().fromJson(cached, Product::class.java)
                    activity.runOnUiThread { activity.showProduct(product) }
                } else {
                    activity.runOnUiThread { activity.showError(e.message) }
                }
            }
        }.start()
    }
}
```

```kotlin
// === AI 生成的重构代码（经人工审查修改后）===

// 数据模型
data class Product(
    val id: String,
    val name: String,
    val price: Double,
    val description: String
)

// Repository 接口
interface ProductRepository {
    suspend fun getProduct(productId: String): Result<Product>
}

// Repository 实现（网络优先 + 磁盘缓存降级）
class ProductRepositoryImpl(
    private val api: ProductApi,
    private val cache: ProductCache
) : ProductRepository {
    
    override suspend fun getProduct(productId: String): Result<Product> {
        return try {
            val product = api.getProduct(productId)
            cache.put(productId, product)  // 更新缓存
            Result.success(product)
        } catch (e: Exception) {
            val cached = cache.get(productId)
            if (cached != null) {
                Result.success(cached)
            } else {
                Result.failure(e)
            }
        }
    }
}

// ProductApi（Retrofit）
interface ProductApi {
    @GET("product/{id}")
    suspend fun getProduct(@Path("id") productId: String): Product
}

// Cache
class ProductCache {
    private val memoryCache = LruCache<String, Product>(50)
    private val prefs: SharedPreferences by lazy { ... }
    
    fun put(id: String, product: Product) {
        memoryCache.put(id, product)
        prefs.edit().putString("product_$id", Gson().toJson(product)).apply()
    }
    
    fun get(id: String): Product? {
        memoryCache.get(id)?.let { return it }
        val json = prefs.getString("product_$id", null) ?: return null
        return Gson().fromJson(json, Product::class.java)
    }
}
```

**P2 实战：创建 ViewModel**

```kotlin
// ViewModel（AI 生成 + 人工优化）
@HiltViewModel
class ProductDetailViewModel @Inject constructor(
    private val getProductUseCase: GetProductDetailUseCase,
    private val addToCartUseCase: AddToCartUseCase,
    private val trackViewUseCase: TrackProductViewUseCase
) : ViewModel() {

    // UI 状态
    data class UiState(
        val isLoading: Boolean = false,
        val product: Product? = null,
        val error: String? = null,
        val isInCart: Boolean = false,
        val addToCartSuccess: Boolean = false
    )

    private val _uiState = MutableStateFlow(UiState())
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()

    fun loadProduct(productId: String) {
        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, error = null) }
            
            getProductUseCase(productId)
                .onSuccess { product ->
                    _uiState.update { 
                        it.copy(isLoading = false, product = product) 
                    }
                    trackViewUseCase(productId)  // 埋点独立
                }
                .onFailure { e ->
                    _uiState.update { 
                        it.copy(isLoading = false, error = e.message) 
                    }
                }
        }
    }

    fun addToCart() {
        val product = _uiState.value.product ?: return
        viewModelScope.launch {
            addToCartUseCase(product)
                .onSuccess { _uiState.update { it.copy(addToCartSuccess = true, isInCart = true) } }
                .onFailure { _uiState.update { it.copy(error = "加入购物车失败") } }
        }
    }
}
```

---

## 六、实战：用 AI 重构老旧模块 —— 从 MVP 到 MVVM（下）

### 6.1 P3 改造 UI 层（Fragment）

这是风险最高的一步。Presenter → ViewModel 的接口迁移需要逐方法对比，确保行为等价。

```kotlin
// === 重构后的 Fragment ===
@AndroidEntryPoint
class ProductDetailFragment : Fragment() {
    
    private val viewModel: ProductDetailViewModel by viewModels()
    private var binding: FragmentProductDetailBinding by autoCleared()
    
    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?
    ): View {
        binding = FragmentProductDetailBinding.inflate(inflater, container, false)
        return binding.root
    }
    
    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        
        // 观察 UI 状态（单向数据流）
        viewLifecycleOwner.lifecycleScope.launch {
            viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
                viewModel.uiState.collect { state ->
                    render(state)
                }
            }
        }
        
        // 用户操作 → ViewModel
        binding.btnAddToCart.setOnClickListener { viewModel.addToCart() }
        
        // 从 Navigation Args 获取参数
        val productId = ProductDetailFragmentArgs.fromBundle(requireArguments()).productId
        viewModel.loadProduct(productId)
    }
    
    private fun render(state: ProductDetailViewModel.UiState) {
        binding.progressBar.isVisible = state.isLoading
        state.error?.let { showError(it) }
        state.product?.let { bindProduct(it) }
        if (state.addToCartSuccess) {
            Snackbar.make(binding.root, "已添加到购物车", Snackbar.LENGTH_SHORT).show()
            viewModel.onAddToCartShown()  // 事件消费
        }
    }
    
    private fun bindProduct(product: Product) {
        binding.apply {
            tvName.text = product.name
            tvPrice.text = "¥${product.price}"
            tvDescription.text = product.description
            Glide.with(root)
                .load(product.imageUrl)
                .placeholder(R.drawable.placeholder)
                .error(R.drawable.error)
                .into(ivProduct)
        }
    }
}
```

### 6.2 P5 引入 Hilt DI

DI 是 AI 辅助的强项——模块配置代码模式固定、重复性高。

```kotlin
// AI 生成的 Hilt Module
@Module
@InstallIn(SingletonComponent::class)
object DataModule {
    
    @Provides
    @Singleton
    fun provideProductApi(retrofit: Retrofit): ProductApi {
        return retrofit.create(ProductApi::class.java)
    }
    
    @Provides
    @Singleton
    fun provideProductCache(@ApplicationContext context: Context): ProductCache {
        return ProductCache(context)
    }
    
    @Provides
    @Singleton
    fun provideProductRepository(
        api: ProductApi,
        cache: ProductCache
    ): ProductRepository {
        return ProductRepositoryImpl(api, cache)
    }
}

@Module
@InstallIn(SingletonComponent::class)
object UseCaseModule {
    
    @Provides
    @Singleton
    fun provideGetProductDetailUseCase(
        repository: ProductRepository
    ): GetProductDetailUseCase {
        return GetProductDetailUseCase(repository)
    }
    
    @Provides
    @Singleton
    fun provideAddToCartUseCase(
        cartManager: CartManager
    ): AddToCartUseCase {
        return AddToCartUseCase(cartManager)
    }
}
```

### 6.3 重构前后对比

| 维度 | 重构前（MVP） | 重构后（MVVM） | 改进 |
|------|-------------|---------------|:---:|
| 文件数 | 12 个 | 18 个（职责更清晰） | +6 (合理的拆分) |
| 最大类行数 | 847 行 | 210 行 | ↓ 75% |
| 测试覆盖 | 15% | 72% | ↑ 57% |
| 主线程 IO | 存在（Thread + runOnUiThread） | 消除（协程 + suspend） | ✅ |
| 内存泄漏源 | Presenter 持有 Activity | Hilt 管理生命周期 | ✅ |
| 循环依赖 | Presenter ↔ Activity | 单向数据流 | ✅ |
| 新需求响应速度 | 需改动 3~4 个类 | 通常只改 ViewModel + UseCase | ↑ 60% |

### 6.4 重构中的关键教训

#### 教训 1：AI 容易"过度架构"

```
AI 第一次生成的重构方案包含了 UseCase → Repository → DataSource 三层抽象，
但实际上 Repository 已经足够——两层即可。过度分层增加了 4 个不必要的接口文件。
```

**原则**：让 AI 先生成方案，人工做"减法"——砍掉不必要的抽象层。

#### 教训 2：AI 对"事件型"和"状态型"的混淆

```
StateFlow 应该持有状态（持久值），而"加入购物车成功"是一次性事件。
AI 最初把 addToCartSuccess 放在 UiState 中，导致：
- 屏幕旋转后 Snackbar 再次弹出
- 从后台切回前台后又弹出一次

修复：使用 Channel + receiveAsFlow 处理一次性事件，或用 SharedFlow。
```

#### 教训 3：AI 生成的测试需要"反向审查"

```kotlin
// AI 生成的测试——看起来正确，实际有缺陷
@Test
fun `loadProduct success updates uiState`() = runTest {
    val product = Product("1", "Test", 9.99, "desc")
    // ❌ 问题：只在 setUp 中 mock 了一次，多个测试共享 mock 状态
    coEvery { repository.getProduct("1") } returns Result.success(product)
    
    viewModel.loadProduct("1")
    
    // ❌ 问题：未使用 Turbine 或 advanceUntilIdle，可能遗漏中间状态
    assertThat(viewModel.uiState.value.product).isEqualTo(product)
}
```

**审查修正**：每个测试独立 setup mock；用 `testScheduler.advanceUntilIdle()` 确保异步操作完成；验证 Loading → Success 的状态转换序列。

### 6.5 总结：AI 辅助重构的黄金法则

```
┌─────────────────────────────────────────────────────────────────┐
│                AI 辅助重构十大黄金法则                             │
├───┬─────────────────────────────────────────────────────────────┤
│ 1 │ 先补测试，再重构——没有安全网，不要动架构                       │
│ 2 │ 小步提交，每步可回滚——一次改 3 个文件的 PR 远比一次改 15 个安全│
│ 3 │ AI 生成架构方案，人工做减法——砍掉不必要的抽象                  │
│ 4 │ 每个 AI 建议都要问"为什么"——不理解的不合入                    │
│ 5 │ 行为等价性用测试证明——不是用肉眼判断                          │
│ 6 │ 区分状态和事件——AI 容易混淆 StateFlow 和 Channel              │
│ 7 │ DI 和模板代码放心交给 AI——核心业务逻辑保留人工                 │
│ 8 │ 重构前后做性能对比——避免引入协程调度开销                      │
│ 9 │ 团队对齐重构规范——每个人的 AI 使用方式应该统一                 │
│10 │ 定期 Code Review AI 的使用方式——持续优化人机协作流程           │
└───┴─────────────────────────────────────────────────────────────┘
```

---

## 附录：面试追问集锦

### Q1: AI 重构后的代码如何保证与原代码行为完全一致？

**答**：三重保证机制——
1. **单元测试**：重构前后的测试用例完全相同，确保回归通过
2. **Diff 测试**：对同一输入分别调用旧模块和新模块，对比输出
3. **灰度验证**：通过 Feature Flag 逐步放量，线上对比新旧实现的业务指标（转化率、Crash 率、加载时间）

### Q2: 团队中有人过度依赖 AI 怎么办？

**答**：设定"AI 使用红线"——
- AI 生成的代码必须在 PR 中标注 `🤖 AI-Generated`
- 核心业务逻辑（支付、认证、权限）禁止 AI 生成
- 每月统计 AI 生成代码的 Bug 率，与手写代码对比，数据驱动决策

### Q3: AI 辅助编程对初中高级开发者的价值有何不同？

| 级别 | AI 的核心价值 | 注意事项 |
|:---:|-------------|---------|
| **初级** | 学习最佳实践、减少语法错误、快速理解 API | 容易全盘接受 AI 建议而不理解原理 |
| **中级** | 提升编码速度、自动化重复劳动、探索技术方案 | 需要在质量和效率间找平衡 |
| **高级** | 架构方案 brainstorm、代码审查加速、技术债务识别 | AI 是副驾驶，架构决策权永远在开发者手中 |

---

*本文档持续更新，欢迎补充实战案例与面试经验。*
