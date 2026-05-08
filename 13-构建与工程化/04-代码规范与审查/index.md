# 代码规范与审查 — 面试深度内容

---

## 第一层：面试高频题（4+ 题）

### Q1: ktlint 与 detekt 的静态代码检查 — 区别、配置与适用场景

静态代码分析是 Android 工程化的第一道质量防线。Kotlin 生态中两个主流工具各有侧重：

**ktlint** — 风格警察

ktlint 是 Pinterest 开源的 Kotlin 代码格式化工具，核心理念是"零配置"（no configuration）。它严格遵循 [Kotlin Coding Conventions](https://kotlinlang.org/docs/coding-conventions.html)，内置规则覆盖缩进、空格、换行、命名、import 排序等风格问题。

```kotlin
// 违反 ktlint 规则的代码
fun foo (x:Int):String{return x.toString()}  // 多余空格、缺少空格、缺少换行

// ktlint 自动格式化后
fun foo(x: Int): String {
    return x.toString()
}
```

**关键特性**：
- 内置格式化（`ktlint --format`）可直接修复大多数风格问题
- `.editorconfig` 支持部分规则定制（如 `max_line_length`、`indent_size`）
- 与 Gradle 集成：`id("org.jlleitschuh.gradle.ktlint")` 插件，版本 12.x 支持 configuration 模式
- 规则集扩展能力有限（非设计目标），复杂逻辑检查应交给 detekt

**detekt** — 代码气味探测器

detekt 是专为 Kotlin 设计的静态分析工具，拥有 **200+ 规则**，覆盖六大类别：

| 类别 | 典型规则 | 示例 |
|------|---------|------|
| **complexity** | 圈复杂度、方法行数、嵌套深度 | `LongMethod`（默认 60 行）、`ComplexCondition`（Boolean 条件 > 3） |
| **style** | MagicNumber、命名规范、多余分号 | `MagicNumber`、`ForbiddenComment`（TODO/FIXME 不追踪） |
| **performance** | 不可变集合使用、冗余操作 | `SpreadOperator`（`*array` 性能损耗） |
| **exceptions** | 异常处理不当、泛型 catch | `TooGenericExceptionCaught`、`InstanceOfCheckForException` |
| **potential-bugs** | 相等性误用、空安全检查缺失 | `UnsafeCallOnNullableType`、`EqualsWithHashCodeExist` |
| **comments** | 注释规范、KDoc 完整性 | `UndocumentedPublicFunction`、`EndOfSentenceFormat` |

**面试要点 — ktlint vs detekt 的核心区别**：

| 维度 | ktlint | detekt |
|------|--------|--------|
| 定位 | 代码格式化/风格 | 代码质量/气味 |
| 规则数量 | ~100 条（风格） | 200+ 条（质量） |
| 可修复 | ✅ `--format` 自动修复 | ❌ 仅报告，需手动修复 |
| 自定义规则 | 困难（非设计目标） | ✅ 完整 DSL/Kotlin API |
| 配置方式 | `.editorconfig` | `detekt.yml`（规则开关+阈值） |
| 控制流分析 | ❌ | ✅ 支持类型解析 |
| IDE 集成 | IntelliJ 插件 | IntelliJ 插件 |

**真实项目配置示例**：

```kotlin
// build.gradle.kts — 同时集成 ktlint + detekt
plugins {
    id("org.jlleitschuh.gradle.ktlint") version "12.1.0"
    id("io.gitlab.arturbosch.detekt") version "1.23.6"
}

ktlint {
    version.set("1.2.1")
    android.set(true)
    ignoreErrors.set(false)   // CI 中设 true 会阻断构建
    reporters {
        reporter(org.jlleitschuh.gradle.ktlint.reporter.ReporterType.SARIF)
    }
}

detekt {
    config.setFrom(rootProject.files("config/detekt/detekt.yml"))
    buildUponDefaultConfig.set(true) // 在默认规则之上叠加
    parallel.set(true)
    baseline.set(rootProject.file("config/detekt/baseline.xml"))
}
```

**面试深度追问**：为什么要同时使用两个工具？

> ktlint 解决"代码看起来像一个人写的"，消除风格争论，降低 Code Review 心智负担；detekt 解决"代码里藏着潜在 bug"，发现人力难以及时发现的模式问题。两者互补：ktlint 管格式，detekt 管逻辑。格式问题是"确定性"问题（要么对要么错），逻辑问题是"概率性"问题（可能是 bug）。把它们分开处理，各司其职。

---

### Q2: Git 分支策略 — GitFlow vs TrunkBased，如何选择？

分支策略决定了团队的协作模式、发布节奏和合并冲突频率。面试中需要清晰阐述两种主流策略的**适用场景**和**利弊权衡**。

**GitFlow — 重型发布管理**

GitFlow 是 Vincent Driessen 在 2010 年提出的经典模型，定义了五种分支类型：

```
master (main)     ●────■───────────────●──────────■──→ 生产发布
                    \                 /          /
release/v1.0        ●──○──○──●     /          /
                              \   /          /
develop              ●──●──●──●──●──●──●──●──●──→ 开发主线
                       \     /      \     /
feature/login          ●──●        \   /
feature/payment         ●──●──●─────●─●
hotfix/urgent                                   ●──●──→ 紧急修复
```

- **master/main**：永远可发布，只接受 release 和 hotfix 合并
- **develop**：集成所有 feature，不稳定状态
- **feature/xxx**：从 develop 分出，完成后合并回 develop
- **release/x.y.z**：从 develop 分出，只修 bug、版本号递增、禁止新功能，完成后合并到 master 和 develop
- **hotfix/xxx**：从 master 分出，修复线上紧急问题，完成后合并到 master 和 develop

**GitFlow 适用场景**：
- 有明确发版周期（如双周/月度发布）
- 需要维护多个生产版本（如 v1.x 和 v2.x 并行）
- 团队规模较大（10+ 开发者），需要严格的合并控制
- 传统 App 发布模式（需要通过应用商店审核）

**TrunkBased — 主干开发，高频集成**

TrunkBased 要求所有开发者直接向 `main`（trunk）提交，或从 `main` 分出短生命周期分支（< 24 小时）：

```
main  ●──●──●──●──●──●──●──●──●──●──●──→ (始终可发布)
       \  /   \  /   \  /   \  /
        ●●     ●●     ●●     ●●         → 短分支 (≤ 1天)
```

**TrunkBased 核心实践**：
- **分支存活不超过 1 天**：迫使开发者拆小任务、频繁集成
- **Feature Flag（功能开关）**：未完成的功能隐藏在开关后，不影响主干可发布性
- **按需发布（Release on Demand）**：通过 Tag 标记发布点，支持每日多次发布
- **Pair Programming / 代码审查前置**：主干保护靠的是提交前的质量门禁

**面试要点 — 对比总结**：

| 维度 | GitFlow | TrunkBased |
|------|---------|------------|
| 分支数量 | 多（≥5 种类型） | 少（仅 main + 短分支） |
| 合并冲突 | 高（长生命周期分支易积压冲突） | 低（频繁集成，冲突小且分散） |
| 发布频率 | 低（周/月级） | 高（天/小时级） |
| CI/CD 要求 | 中等 | 极高（必须自动化质量门禁） |
| 团队要求 | 中 | 高（需要纪律性） |
| 回滚难度 | 中（需 hotfix 流程） | 低（revert 单次提交） |
| 典型使用者 | 传统企业 App、SDK | Google、Netflix、大部分互联网 App |

**面试追问：我们团队应该用哪个？**

> 移动端 App 的特殊性在于：应用商店审核周期决定了即使代码可以每天发布，用户端更新频率也受限。但 Beta/内部测试版本可以每天发布。**推荐策略**：使用 **Scaled TrunkBased**——日常开发在短分支上，通过 CI 自动构建 Beta 版；正式发布时从 main 拉出 release 分支进行商店提审。这样保留 TrunkBased 的高频集成优势，同时兼容商店审核的现实约束。

---

### Q3: Code Review 的检查要点 — 有效的审查应该看什么？

Code Review 不是"找茬"，而是**知识共享 + 质量兜底**。面试中要展示系统化的审查思维框架，而非泛泛"看看代码写得怎么样"。

**审查金字塔（从宏观到微观）**：

```
         ┌─────────────┐
         │  架构与设计   │  ← 最难修改，必须首先审视
         ├─────────────┤
         │  正确性与边界  │  ← 核心价值
         ├─────────────┤
         │  可维护性     │  ← 长期成本
         ├─────────────┤
         │  风格与格式   │  ← 交给 linter，人不该纠结
         └─────────────┘
```

**第一层：架构与设计（宏观）**

- **单一职责**：这个类/方法是否做了太多事情？能否拆分？
- **依赖方向**：是否符合分层架构？有没有反向依赖（底层依赖上层）？
- **抽象层级**：接口是否合理？抽象是否过度（YAGNI）或不足？
- **模块边界**：修改是否跨越了不该跨越的模块边界？

**第二层：正确性与边界条件（核心价值）**

- **空安全**：nullable 参数是否在每个调用点都做了处理？`!!` 的使用是否合理？
- **边界条件**：空列表、零值、极限值、网络异常、超时是否覆盖？
- **并发安全**：是否存在竞态条件？共享状态是否正确同步？Coroutine 作用域是否正确？
- **资源管理**：文件句柄、数据库连接、Bitmap、RecyclerView ViewHolder 是否正确释放/复用？
- **异常处理**：是否 catch 了过于宽泛的异常？是否有吞掉异常的 silent catch？

```kotlin
// Code Review 反例 — 容易被忽略的并发问题
class CounterViewModel : ViewModel() {
    var count = 0  // ⚠️ 可变状态，多线程不安全

    fun increment() {
        viewModelScope.launch(Dispatchers.Default) {
            count++  // ⚠️ count++ 不是原子操作，竞态条件
        }
    }
}

// 修正方案
class CounterViewModel : ViewModel() {
    private val _count = MutableStateFlow(0)
    val count: StateFlow<Int> = _count.asStateFlow()

    fun increment() {
        _count.update { it + 1 }  // 原子操作
    }
}
```

**第三层：可维护性（长期成本）**

- **命名是否自解释**：读一遍能否理解意图？是否需要注释来"翻译"？
- **重复代码**：是否存在可以通过抽象消除的重复？但也要警惕过度抽象的 DRY 陷阱
- **测试覆盖**：新增/修改的逻辑是否有对应测试？边界条件是否覆盖？
- **日志与监控**：关键路径是否有适当的日志（但不要过度）？

**第四层：风格与格式（交给工具）**

- 缩进、空格、换行 → **ktlint 自动处理**
- import 排序、通配符 → **IDE 自动优化 + ktlint**
- Magic Number、方法长度 → **detekt 自动报告**
- 注释格式、KDoc → **detekt comments 规则集**

**面试金句**：好的 Code Review 审查的是**逻辑和设计**，不是**格式和风格**。如果 Review 时间花在挑缩进和命名上，说明团队的自动化工具没有到位。人应该做机器做不了的事情。

**审查者的态度原则**：
- 区分"这是错的"（必须修改）和"我不喜欢"（可以讨论但不阻塞）
- 每个 Comment 都应附带**建议方案**或**参考链接**，而非只指出问题
- 优先使用"引导式提问"而非"命令式"："这里如果传入空列表会怎样？"而不是"你应该判断空列表"
- 正面反馈同样重要：好的设计选择值得明确认可

---

### Q4: 代码规范如何在团队落地 — 扫描 → CI 门禁 → 逐步收紧

这是面试中最考察工程化思维的问题。规范制定容易，落地执行难。**核心原则**：不要一次性追求完美，而要通过渐进式收紧让团队"平滑适应"。

**第一阶段：现状摸底与方案制定（1-2 周）**

```
1. 跑一次全量扫描（detekt + ktlint），生成基线报告
2. 分析 Top 20 高频违规，按修复成本分类：
   - 自动修复（ktlint --format 可解决）
   - 低风险手动修复（命名、MagicNumber）
   - 高风险修复（复杂度超标，需要重构）
3. 与团队讨论规则集：哪些规则立即开启，哪些暂缓
4. 产物：config/detekt/detekt.yml + config/ktlint/.editorconfig
```

**第二阶段：IDE 实时反馈（立即开始）**

在规范落地中最容易被忽略但效果最好的步骤——让开发者在编码时就能看到问题：

```kotlin
// 所有开发者 IDE 配置
// 1. 安装 detekt IntelliJ 插件 → 编码时红色波浪线提示
// 2. 安装 ktlint IntelliJ 插件 → 保存时自动格式化
// 3. .idea/codeStyles/ 提交到仓库 → 统一 IDE 代码风格设置
// 4. Save Actions 插件 → 保存时自动 optimize imports + reformat code
```

**关键认知**：IDE 层面消除问题的成本是秒级，CI 层面发现问题的成本是分钟级，Code Review 层面发现问题的成本是小时级。最佳策略是**把问题消灭在最前面的环节**。

**第三阶段：本地 Git Hook — Pre-commit 轻量检查（第 2-4 周）**

```bash
# .git/hooks/pre-commit（或通过 pre-commit 框架管理）
#!/bin/bash
# 仅检查 staged 的 Kotlin 文件

STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM | grep '\.kt$')

if [ -z "$STAGED_FILES" ]; then
    exit 0
fi

echo "Running ktlint on staged files..."
ktlint --relative $STAGED_FILES
KTLINT_EXIT=$?

if [ $KTLINT_EXIT -ne 0 ]; then
    echo "❌ ktlint found style violations. Run 'ktlint --format' to auto-fix."
    exit 1
fi

echo "✅ Pre-commit checks passed."
```

**初期策略**：Git Hook 只做 **Warning 提示**，不阻断提交。运行 2 周后切换为强制阻断。

**第四阶段：CI 门禁 — 强制阻断（第 3 周开始）**

在 CI Pipeline 中加入静态分析 Job：

```yaml
# .github/workflows/static-analysis.yml
name: Static Analysis

on:
  pull_request:
    branches: [main, develop]
  push:
    branches: [main, develop]

jobs:
  ktlint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          java-version: '17'
          distribution: 'temurin'
      - name: Run ktlint
        run: ./gradlew ktlintCheck

  detekt:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          java-version: '17'
          distribution: 'temurin'
      - name: Run detekt
        run: ./gradlew detekt
      - name: Upload detekt report
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: detekt-reports
          path: build/reports/detekt/
```

**第五阶段：逐步收紧规则（持续进行）**

```
初始基线（第1周）       第4周              第8周             第12周
──────────────────────────────────────────────────────────────→
规则开启率: 60%         80%                95%               100%
复杂度阈值: 20          15                 12                10
方法行数上限: 100       80                 60                40
允许的违规数: baseline  baseline-30%       baseline-60%      0
```

**收紧策略**：
- 每次收紧前 1 周通知团队，给出修复时间窗口
- 优先收紧"自动修复"类规则，减少人工成本
- 重大收紧在 Sprint 回顾会上同步，获得团队认同
- 使用 `baseline` 机制：存量违规记录在 `baseline.xml`，只对增量代码做严格检查

```xml
<!-- config/detekt/baseline.xml — 存量问题名单，CI 忽略已有违规 -->
<SmellBaseline>
  <ManuallySuppressedIssues/>
  <CurrentIssues>
    <ID>LongMethod:LoginViewModel.kt$...</ID>
    <ID>ComplexMethod:PaymentProcessor.kt$...</ID>
  </CurrentIssues>
</SmellBaseline>
```

**面试总结**：代码规范落地的本质是**行为改变管理**，不是工具部署。关键在于：
1. **低摩擦起步** — IDE 集成 > Git Hook > CI 门禁，从易到难
2. **增量收紧** — 存量宽容，增量严格，给团队适应期
3. **自动化优先** — 能自动修复的不要让人类去修
4. **数据驱动** — 用趋势图展示违规数量下降，用成就感而非负罪感推动改进

---

## 第二层：detekt 自定义规则开发

### 为什么要自定义规则？

detekt 内置 200+ 规则能覆盖 80% 的场景，但以下情况需要自定义规则：

- **团队特约惯例**：如"禁止直接使用 `System.currentTimeMillis()`，必须用团队的 `TimeProvider`"
- **架构约束**：如"ViewModel 不能持有 Context 引用"、"Repository 层不能引用 Android SDK"
- **API 规范**：如"所有 public 方法参数必须标注 `@NonNull` / `@Nullable`"（Java 互操作场景）
- **性能规则**：如"禁止在 RecyclerView.onBindViewHolder 中做耗时操作"

### 自定义规则开发三步走

**Step 1: 创建规则模块**

```kotlin
// detekt-rules/build.gradle.kts
plugins {
    kotlin("jvm") version "1.9.22"
}

dependencies {
    implementation("io.gitlab.arturbosch.detekt:detekt-api:1.23.6")
    testImplementation("io.gitlab.arturbosch.detekt:detekt-test:1.23.6")
}
```

**Step 2: 编写规则类**

detekt 规则基类提供了完整的访问基础设施，包括：
- **PSI (Program Structure Interface)**：Kotlin 编译器的 AST 表示
- **类型解析**：通过 `bindingContext` 获取完整的类型信息
- **配置参数**：通过 `@Configuration` 注解声明可配置项
- **债务计算**：通过 `Debt` 对象标记修复时间

```kotlin
package com.example.detekt.rules

import io.gitlab.arturbosch.detekt.api.*
import org.jetbrains.kotlin.psi.*
import org.jetbrains.kotlin.resolve.BindingContext
import org.jetbrains.kotlin.name.FqName

/**
 * 检测直接调用 System.currentTimeMillis() 的代码
 * 强制使用团队封装的 TimeProvider，便于测试时控制时间
 */
class ForbiddenSystemTimeCall(config: Config) : Rule(config) {

    // 通过 @Configuration 暴露可配置参数
    @Configuration("允许的替代 API 的完全限定名")
    private val allowedAlternative: String by config(
        "com.example.core.time.TimeProvider"
    )

    override val issue: Issue = Issue(
        javaClass.simpleName,
        Severity.CodeSmell,
        "直接调用 System.currentTimeMillis() 会使得时间相关逻辑难以测试。" +
            "请使用 $allowedAlternative 替代。",
        Debt.FIVE_MINS  // 修复预计 5 分钟
    )

    override fun visitReferenceExpression(expression: KtReferenceExpression) {
        super.visitReferenceExpression(expression)

        // 获取类型解析上下文
        val context = bindingContext ?: return

        // 检查是否为 System.currentTimeMillis() 调用
        if (expression is KtNameReferenceExpression &&
            expression.getReferencedName() == "currentTimeMillis"
        ) {
            val descriptor = context[BindingContext.REFERENCE_TARGET, expression]
            val fqName = descriptor?.containingDeclaration
                ?.let { it as? org.jetbrains.kotlin.descriptors.DeclarationDescriptor }
                ?.let { org.jetbrains.kotlin.resolve.descriptorUtil.fqNameOrNull(it) }

            if (fqName?.asString() == "kotlin.system.currentTimeMillis") {
                report(
                    CodeSmell(
                        issue = issue,
                        entity = Entity.atName(expression),
                        message = "禁止直接调用 System.currentTimeMillis()。" +
                            "请注入并使用 $allowedAlternative。"
                    )
                )
            }
        }
    }
}
```

**Step 3: 注册规则并提供给项目**

```kotlin
// detekt-rules/src/main/resources/META-INF/services/
//   io.gitlab.arturbosch.detekt.api.RuleSetProvider

class CustomRuleSetProvider : RuleSetProvider {
    override val ruleSetId: String = "team-custom"

    override fun instance(config: Config): RuleSet =
        RuleSet(
            id = ruleSetId,
            rules = listOf(
                ForbiddenSystemTimeCall(config),
                ViewModelNoContextRule(config),
                NoHardcodedColorRule(config)
            )
        )
}
```

```kotlin
// 项目 build.gradle.kts 引用
dependencies {
    detektPlugins(project(":detekt-rules"))
}
```

### 自定义规则的高级技巧

**使用类型解析做更深层检查**：

```kotlin
// 检测 ViewModel 是否持有 Context 引用
class ViewModelNoContextRule(config: Config) : Rule(config) {

    override val issue: Issue = Issue(
        "ViewModelNoContext",
        Severity.Defect,  // Defect > CodeSmell，表示更高严重度
        "ViewModel 不应持有 Context/Activity/Fragment/View 引用，会导致内存泄漏",
        Debt.TWENTY_MINS
    )

    override fun visitClass(klass: KtClass) {
        super.visitClass(klass)

        // 判断是否为 ViewModel 子类
        if (!klass.isSubtypeOf("androidx.lifecycle.ViewModel")) return

        // 检查属性类型
        klass.getProperties().forEach { property ->
            val typeRef = property.typeReference ?: return@forEach
            val typeText = typeRef.text

            val forbiddenTypes = listOf("Context", "Activity", "Fragment", "View", "Application")
            forbiddenTypes.forEach { forbidden ->
                if (typeText.contains(forbidden)) {
                    report(CodeSmell(
                        issue,
                        Entity.atName(property),
                        "ViewModel '${klass.name}' 的属性 '${property.name}' 类型为 '$typeText'，" +
                            "持有 $forbidden 引用将导致配置变更时内存泄漏。" +
                            "请使用 ApplicationProvider 或 SavedStateHandle 替代。"
                    ))
                }
            }
        }
    }

    // 辅助方法：判断类型继承关系
    private fun KtClass.isSubtypeOf(superFqName: String): Boolean {
        val superTypes = superTypeListEntries.map { it.typeReference?.text ?: "" }
        if (superTypes.any { it.contains("ViewModel") }) return true
        // 递归检查父类
        return superTypes.any { /* 通过 bindingContext 检查完整继承链 */ }
    }
}
```

---

## 第三层：Git Hooks 深度实践 — Pre-commit 检查的自动化防线

### Hooks 机制原理

Git 在 `.git/hooks/` 目录下提供了客户端钩子和服务端钩子。客户端钩子中最常用的是 **pre-commit**——在 `git commit` 执行前触发，返回非零退出码会**中止提交**。

```
开发者的操作流程：
  git add -A
  git commit -m "fix: login crash"
      │
      ▼
  .git/hooks/pre-commit 执行
      │
      ├── 退出码 0 → 提交成功
      └── 退出码 ≠ 0 → 提交被阻止，提示错误信息
```

### 企业级 Pre-commit 方案

裸用 `.git/hooks/` 存在致命缺陷：**`.git/` 目录不参与版本管理，无法团队同步**。必须借助框架：

**方案一：pre-commit 框架（推荐）**

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/pinterest/ktlint
    rev: "1.2.1"
    hooks:
      - id: ktlint
        args: ['--relative']
        stages: [commit]

  - repo: local
    hooks:
      - id: detekt
        name: detekt
        entry: ./gradlew detekt
        language: system
        pass_filenames: false
        stages: [commit]

  - id: commit-message-check
        name: 提交信息格式检查
        entry: bash -c '[[ "$(head -1 $1)" =~ ^(feat|fix|docs|style|refactor|perf|test|chore|ci|build)(\(.+\))?:\ .+ ]]'
        language: system
        stages: [commit-msg]

  - id: large-file-check
        name: 禁止提交大文件
        entry: bash -c 'find "$@" -size +5M | while read f; do echo "文件 $f 超过 5MB，禁止提交"; exit 1; done'
        language: system
```

```bash
# 团队初始化（每人一次）
brew install pre-commit       # macOS
pre-commit install            # 安装到 .git/hooks/
pre-commit install --hook-type commit-msg  # 安装 commit-msg hook
```

**方案二：Gradle 集成方案（纯 Kotlin 生态）**

```kotlin
// build.gradle.kts — 通过 Gradle Task 统一管理 Hook 安装
tasks.register("installGitHooks") {
    description = "安装 pre-commit Git hooks"
    group = "help"

    doLast {
        val hooksDir = rootProject.file(".git/hooks")
        hooksDir.mkdirs()

        val preCommitHook = hooksDir.resolve("pre-commit")
        preCommitHook.writeText("""
            |#!/bin/bash
            |# Auto-generated by Gradle. Do not edit directly.
            |
            |echo "🔍 Running pre-commit checks..."
            |
            |# 1. ktlint 检查（仅 staged 文件）
            |STAGED_FILES=$$(git diff --cached --name-only --diff-filter=ACM | grep '\.kt$$' || true)
            |if [ -n "$$STAGED_FILES" ]; then
            |    echo "  📏 ktlint..."
            |    ./gradlew ktlintCheck || {
            |        echo "❌ ktlint 检查未通过。运行 './gradlew ktlintFormat' 自动修复。"
            |        exit 1
            |    }
            |fi
            |
            |# 2. detekt 检查
            |echo "  🔎 detekt..."
            |./gradlew detekt || {
            |    echo "❌ detekt 检查未通过。请修复以上问题后重新提交。"
            |    exit 1
            |}
            |
            |echo "✅ 所有检查通过。"
            |""".trimMargin()
        )
        preCommitHook.setExecutable(true)

        println("✅ Git hooks installed successfully.")
    }
}
```

### 性能优化策略

Pre-commit 检查最致命的缺陷是**慢**——每次提交都跑 full detekt 会严重拖慢开发效率。针对性的优化策略：

```bash
#!/bin/bash
# 高性能 pre-commit hook

STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM | grep '\.kt$')

if [ -z "$STAGED_FILES" ]; then
    exit 0  # 没有 Kotlin 文件变更，跳过
fi

# 策略1：增量检查 — 只检查变更的文件
echo "Checking ${STAGED_FILES}..."
ktlint --relative $STAGED_FILES

# 策略2：detekt 增量 — 利用 Gradle 增量编译
# detekt 1.23+ 支持仅分析变更代码（配合 baseline）
./gradlew detekt -Pdetekt.incremental=true

# 策略3：缓存机制 — 未变更文件不重复检查
# Gradle build cache + detekt 内置缓存
```

**终极方案：服务器端 Hook + 客户端可选**

```
场景                          策略
─────────────────────────────────────────────
本地 pre-commit (客户端)       轻量检查：ktlint + commit message
                              允许 --no-verify 跳过（紧急情况）
CI pull_request (服务端)      完整检查：detekt full + ktlint
                              强制阻断，不可跳过
```

---

## 第四层：代码审查流程图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CODE REVIEW 完整流程                          │
└─────────────────────────────────────────────────────────────────────┘

开发者: 编写代码
    │
    ▼
┌──────────────────┐
│  1. 本地自检      │  ← IDE 实时 lint + pre-commit hook 自动检查
│  - ktlint format │
│  - detekt 扫描    │
│  - 自测通过       │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  2. 创建 PR       │  ← 填写 PR 模板：背景、变更说明、测试截图
│  - 关联 Issue     │
│  - 填写描述       │
│  - 指定 Reviewer  │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐     ┌─────────────────┐
│  3. CI 自动门禁   │────▶│ ❌ 阻断          │
│  - ktlintCheck   │     │ 开发者修复后     │
│  - detekt        │     │ 重新 push        │
│  - 单元测试       │     └────────┬────────┘
│  - 构建成功       │              │
└────────┬─────────┘              │
         │ ✅ 通过                 │
         ▼                        │
┌──────────────────┐              │
│  4. Reviewer 审查 │◄─────────────┘
│                   │
│  审查维度：        │
│  ├─ 架构与设计     │──── 宏观：是否符合架构？可扩展？
│  ├─ 正确性         │──── 核心：边界条件？并发？泄漏？
│  ├─ 可维护性       │──── 长期：命名？耦合度？可测试性？
│  └─ 风格与格式     │──── 自动：linter 已覆盖，不过分纠结
│                   │
│  审查决策树：      │
│  ┌─ 请求变更 ──────┤──── 发现必须修复的问题（标注 severity）
│  ├─ 评论/建议 ─────┤──── 可选优化建议，非阻塞
│  └─ 通过 ─────────┤──── 无问题或仅剩 nitpick
└────────┬──────────┘
         │
         ▼
    ┌────┴────┐
    │ 决定？   │
    └────┬────┘
         │
    ┌────┼────────────┐
    ▼    ▼            ▼
  请求  评论        ✅ 通过
  变更  (非阻塞)
    │    │            │
    ▼    │            ▼
 开发者   │     ┌──────────────┐
 修复并   │     │  5. 合并策略  │
 回复评论 │     │               │
    │    │     │  ├─ Squash    │  ← 单次提交合并，保持主干干净
    │    │     │  ├─ Rebase    │  ← 线性历史
    │    │     │  └─ Merge     │  ← 保留分支历史
    │    │     └──────┬────────┘
    │    │            │
    └────┴────────────┘
         │
         ▼
┌──────────────────┐
│  6. 合并后验证    │
│  - CI 主干构建    │
│  - 自动化回归测试  │
│  - (可选) 灰度发布 │
└──────────────────┘


═══════════════════════════════════════════════════════
  关键时间节点
═══════════════════════════════════════════════════════

  提交 PR 后:
  ├─ < 5 分钟:  CI 自动门禁完成
  ├─ < 4 小时:  Reviewer 首次反馈（工作日）
  ├─ < 24 小时: PR 合并或关闭
  └─ 紧急修复:  走 hotfix 通道，简化审查流程但保留 CI 门禁

═══════════════════════════════════════════════════════
  Review 大小的最佳实践
═══════════════════════════════════════════════════════

  PR 大小          审查时间    审查质量    建议
  ──────────────────────────────────────────────
  < 200 行         10-20 分钟   高          ✅ 理想
  200-500 行       20-40 分钟   中高        可接受
  500-1000 行      40-90 分钟   中          ⚠️ 需要拆分
  > 1000 行        > 90 分钟    低          ❌ 必须拆分
```

---

## 第五层：detekt 自定义规则完整示例

### 实战规则：禁止在 RecyclerView.Adapter 中使用不安全的 notifyDataSetChanged()

```kotlin
package com.example.detekt.rules

import io.gitlab.arturbosch.detekt.api.*
import org.jetbrains.kotlin.psi.*
import org.jetbrains.kotlin.name.FqName
import org.jetbrains.kotlin.resolve.BindingContext
import org.jetbrains.kotlin.resolve.calls.callUtil.getResolvedCall

/**
 * 检测 RecyclerView.Adapter 子类中调用 notifyDataSetChanged()
 *
 * notifyDataSetChanged() 会触发整个列表重绘，丢失动画和滚动位置。
 * 应使用 ListAdapter + DiffUtil，或 notifyItemChanged/Inserted/Removed/Range 等精准通知方法。
 *
 * 配置项:
 * - allowedMethods: 允许列表，默认只允许精准通知方法
 * - ignoreAbstractClasses: 是否忽略抽象 Adapter（默认 true）
 */
class AvoidNotifyDataSetChanged(config: Config) : Rule(config) {

    @Configuration("允许使用的替代方法列表（逗号分隔）")
    private val allowedMethods: List<String> by config(
        listOf(
            "notifyItemChanged",
            "notifyItemInserted",
            "notifyItemRemoved",
            "notifyItemMoved",
            "notifyItemRangeChanged",
            "notifyItemRangeInserted",
            "notifyItemRangeRemoved"
        )
    )

    @Configuration("是否忽略抽象类")
    private val ignoreAbstractClasses: Boolean by config(true)

    override val issue: Issue = Issue(
        javaClass.simpleName,
        Severity.Performance,   // 性能问题严重度
        "RecyclerView.Adapter 中不应使用 notifyDataSetChanged()，它会触发全局刷新，" +
            "导致动画丢失、滚动位置重置、性能下降。请使用 ListAdapter + AsyncListDiffer " +
            "（自动 DiffUtil），或手动调用精准通知方法。",
        Debt.FIFTEEN_MINS  // 修复预计 15 分钟
    )

    override fun visitNamedFunction(function: KtNamedFunction) {
        super.visitNamedFunction(function)

        // 判断调用方法名是否为 notifyDataSetChanged
        if (function.name != "notifyDataSetChanged") return

        // 判断所在类是否为 RecyclerView.Adapter 子类
        val containingClass = function.parent as? KtClassOrObject ?: return
        if (!containingClass.isSubtypeOf("androidx.recyclerview.widget.RecyclerView.Adapter")) return

        // 是否忽略抽象类
        if (ignoreAbstractClasses && containingClass is KtClass && containingClass.isAbstract()) return

        report(
            CodeSmell(
                issue = issue,
                entity = Entity.atName(function),
                message = "${containingClass.name ?: "匿名 Adapter"} 中使用了 " +
                    "notifyDataSetChanged()。建议迁移到 ListAdapter<*, *> " +
                    "配合 AsyncListDiffer / DiffUtil，实现高效的增量更新。" +
                    "\n\n示例:\n" +
                    "class MyAdapter : ListAdapter<Item, MyAdapter.ViewHolder>(DiffCallback()) {\n" +
                    "    fun submitList(newItems: List<Item>) {\n" +
                    "        submitList(newItems.toList())  // DiffUtil 自动计算差异\n" +
                    "    }\n" +
                    "}"
            )
        )
    }

    // 通过 bindingContext 检查是否有对 notifyDataSetChanged 的调用表达式
    override fun visitCallExpression(expression: KtCallExpression) {
        super.visitCallExpression(expression)

        val context = bindingContext ?: return

        // 获取被调用的函数引用
        val callee = expression.calleeExpression as? KtNameReferenceExpression ?: return
        if (callee.getReferencedName() != "notifyDataSetChanged") return

        // 通过类型解析确认调用的是 RecyclerView.Adapter.notifyDataSetChanged()
        val resolvedCall = expression.getResolvedCall(context) ?: return
        val fqName = resolvedCall.candidateDescriptor
            .containingDeclaration
            .let {
                org.jetbrains.kotlin.resolve.descriptorUtil.fqNameOrNull(
                    it as org.jetbrains.kotlin.descriptors.DeclarationDescriptor
                )
            }

        if (fqName?.asString() == "androidx.recyclerview.widget.RecyclerView.Adapter.notifyDataSetChanged") {
            report(
                CodeSmell(
                    issue = issue,
                    entity = Entity.from(expression),
                    message = "检测到 notifyDataSetChanged() 调用，建议使用精准更新方法。"
                )
            )
        }
    }
}
```

### 测试自定义规则

```kotlin
package com.example.detekt.rules

import io.gitlab.arturbosch.detekt.test.compileAndLint
import org.junit.jupiter.api.Test
import kotlin.test.assertEquals

class AvoidNotifyDataSetChangedTest {

    private val rule = AvoidNotifyDataSetChanged(TestConfig.empty)

    @Test
    fun `detects notifyDataSetChanged in Adapter subclass`() {
        val code = """
            import androidx.recyclerview.widget.RecyclerView
            
            class MyAdapter : RecyclerView.Adapter<MyViewHolder>() {
                fun updateData() {
                    notifyDataSetChanged()
                }
            }
        """.trimIndent()

        val findings = rule.compileAndLint(code)
        assertEquals(1, findings.size)
        assertEquals("AvoidNotifyDataSetChanged", findings.first().id)
    }

    @Test
    fun `allows notifyItemInserted in Adapter subclass`() {
        val code = """
            import androidx.recyclerview.widget.RecyclerView
            
            class MyAdapter : RecyclerView.Adapter<MyViewHolder>() {
                fun addItem() {
                    notifyItemInserted(0)
                }
            }
        """.trimIndent()

        val findings = rule.compileAndLint(code)
        assertEquals(0, findings.size)
    }
}
```

---

## 第六层：CI 门禁完整配置

### GitHub Actions 完整静态分析 Pipeline

```yaml
# .github/workflows/code-quality-gate.yml
name: 🛡️ Code Quality Gate

on:
  pull_request:
    branches: [main, develop]
    types: [opened, synchronize, reopened]
  push:
    branches: [main, develop]

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  # ────────────────────────────────────────────
  # Job 1: ktlint 风格检查
  # ────────────────────────────────────────────
  ktlint:
    name: 📏 ktlint Style Check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up JDK 17
        uses: actions/setup-java@v4
        with:
          java-version: '17'
          distribution: 'temurin'
          cache: 'gradle'

      - name: Setup Gradle
        uses: gradle/actions/setup-gradle@v3

      - name: Run ktlint
        run: ./gradlew ktlintCheck --no-daemon

      - name: Upload ktlint SARIF Report
        if: failure()
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: build/reports/ktlint/ktlintMainSourceSetCheck.sarif

  # ────────────────────────────────────────────
  # Job 2: detekt 代码质量分析
  # ────────────────────────────────────────────
  detekt:
    name: 🔎 detekt Code Analysis
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up JDK 17
        uses: actions/setup-java@v4
        with:
          java-version: '17'
          distribution: 'temurin'
          cache: 'gradle'

      - name: Setup Gradle
        uses: gradle/actions/setup-gradle@v3

      - name: Run detekt
        run: ./gradlew detekt --no-daemon

      - name: Upload detekt HTML Report
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: detekt-html-report
          path: build/reports/detekt/detekt.html

      - name: Upload detekt SARIF Report
        if: failure()
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: build/reports/detekt/detekt.sarif

      - name: Comment PR with Violations
        if: failure() && github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const report = fs.readFileSync('build/reports/detekt/detekt.md', 'utf8');
            const summary = report.substring(0, 2000);  // GitHub comment 有长度限制

            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: `## ❌ detekt 检查未通过\n\n${summary}\n\n> 💡 完整报告请下载 Artifact: [detekt-html-report](${process.env.GITHUB_SERVER_URL}/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId})`
            });

  # ────────────────────────────────────────────
  # Job 3: Android Lint（Android 官方工具）
  # ────────────────────────────────────────────
  android-lint:
    name: 🤖 Android Lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up JDK 17
        uses: actions/setup-java@v4
        with:
          java-version: '17'
          distribution: 'temurin'
          cache: 'gradle'

      - name: Setup Gradle
        uses: gradle/actions/setup-gradle@v3

      - name: Run Android Lint
        run: ./gradlew lint --no-daemon

      - name: Upload Lint Report
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: lint-report
          path: |
            app/build/reports/lint-results*.html
            app/build/reports/lint-results*.xml

  # ────────────────────────────────────────────
  # Job 4: 汇总 — 必须在所有检查通过后才算成功
  # ────────────────────────────────────────────
  quality-gate-summary:
    name: ✅ Quality Gate Passed
    needs: [ktlint, detekt, android-lint]
    runs-on: ubuntu-latest
    if: always()
    steps:
      - name: Check Results
        run: |
          echo "### Quality Gate Results" >> $GITHUB_STEP_SUMMARY
          if [[ "${{ needs.ktlint.result }}" == "success" ]]; then
            echo "- 📏 ktlint: ✅ PASSED" >> $GITHUB_STEP_SUMMARY
          else
            echo "- 📏 ktlint: ❌ FAILED" >> $GITHUB_STEP_SUMMARY
          fi
          if [[ "${{ needs.detekt.result }}" == "success" ]]; then
            echo "- 🔎 detekt: ✅ PASSED" >> $GITHUB_STEP_SUMMARY
          else
            echo "- 🔎 detekt: ❌ FAILED" >> $GITHUB_STEP_SUMMARY
          fi
          if [[ "${{ needs.android-lint.result }}" == "success" ]]; then
            echo "- 🤖 Android Lint: ✅ PASSED" >> $GITHUB_STEP_SUMMARY
          else
            echo "- 🤖 Android Lint: ❌ FAILED" >> $GITHUB_STEP_SUMMARY
          fi

      - name: Fail if any check failed
        if: |
          needs.ktlint.result != 'success' ||
          needs.detekt.result != 'success' ||
          needs.android-lint.result != 'success'
        run: exit 1
```

### detekt 配置文件（与 CI 配合）

```yaml
# config/detekt/detekt.yml
build:
  maxIssues: 0                   # CI 模式下不允许任何新违规
  excludeCorrectable: false
  weights:
    complexity: 2
    style: 1
    comments: 0.5

style:
  MagicNumber:
    active: true
    ignoreNumbers: ['-1', '0', '1', '2']
    ignoreHashCodeFunction: true
    ignorePropertyDeclaration: true
    ignoreCompanionObjectPropertyDeclaration: true
    ignoreEnums: true
    ignoreRanges: true

  ForbiddenComment:
    active: true
    values: ['TODO:', 'FIXME:', 'HACK:']
    allowedPatterns: 'TODO\(ISSUE-\d+\)'  # 要求 TODO 关联 Issue 编号

complexity:
  LongParameterList:
    active: true
    functionThreshold: 6
    constructorThreshold: 7

  TooManyFunctions:
    active: true
    thresholdInFiles: 11
    thresholdInClasses: 11
    thresholdInInterfaces: 8

  ComplexMethod:
    active: true
    threshold: 12       # 圈复杂度上限

  LongMethod:
    active: true
    threshold: 60       # 方法行数上限

exceptions:
  TooGenericExceptionCaught:
    active: true
    exceptionNames:
      - Error
      - Exception
      - Throwable
      - RuntimeException

performance:
  SpreadOperator:
    active: true       # 数组展开操作符 * 的性能问题

naming:
  FunctionNaming:
    active: true
    ignoreAnnotated: ['Composable']  # Compose 函数允许大写开头
```

### Gradle 整合：将所有检查串联为单一 Task

```kotlin
// build.gradle.kts — 根项目
tasks.register("codeQualityCheck") {
    description = "运行所有静态代码检查（ktlint + detekt + lint）"
    group = "verification"
    dependsOn(
        "ktlintCheck",
        "detekt",
        if (project.hasProperty("android")) "lint" else null
    )
}
```

```bash
# 开发者在本地提交前运行
./gradlew codeQualityCheck

# CI 中使用（与 GitHub Actions 等效）
./gradlew codeQualityCheck --no-daemon --continue
```

### 分支保护规则（GitHub Branch Protection）

```
Branch: main
├─ ✅ Require a pull request before merging
│   ├─ ✅ Require approvals: 1
│   └─ ✅ Dismiss stale pull request approvals when new commits are pushed
├─ ✅ Require status checks to pass before merging
│   ├─ ✅ ktlint
│   ├─ ✅ detekt
│   ├─ ✅ android-lint
│   ├─ ✅ unit-tests
│   └─ ✅ quality-gate-summary
├─ ✅ Require conversation resolution before merging
├─ ✅ Require linear history (禁止 merge commits)
└─ ✅ Do not allow bypassing the above settings
```

---

> **总结**：代码规范与审查是工程质量的基石。工具自动化（ktlint + detekt）解决 80% 的风格和质量问题，Git 分支策略决定团队的协作效率和风险控制能力，Code Review 流程确保知识和质量在团队中流动。三者的正确落地顺序是：**先让机器做机器擅长的事（自动检查），再让人做人擅长的事（设计与逻辑审查）。**
