# Gradle 构建系统 — 面试深度解析

---

## 一、面试层：核心必问 6 题

### Q1: Gradle 构建生命周期三阶段是什么？每个阶段做了什么？

Gradle 的构建过程严格分为三个阶段：

| 阶段 | 英文 | 核心职责 | 涉及文件 |
|------|------|----------|----------|
| 初始化 | **Initialization** | 确定哪些项目参与构建，创建 `Project` 对象体系 | `settings.gradle(.kts)` |
| 配置 | **Configuration** | 解析所有参与项目的 `build.gradle`，构建 Task 的有向无环图 (DAG) | 所有 `build.gradle(.kts)` |
| 执行 | **Execution** | 按照 DAG 依赖顺序执行用户指定的 Task | Task 实现类 |

**初始化阶段细节：**
- Gradle 首先查找 `settings.gradle`（或 `settings.gradle.kts`），确定是单项目还是多项目构建。
- 对于多项目构建，`include` 指令告诉 Gradle 哪些子项目参与构建。
- 每个参与的项目都会创建一个 `Project` 实例，形成树状结构（根项目 + 子项目）。
- 此阶段可监听 `settingsEvaluated` 和 `projectsLoaded` 回调。

**配置阶段细节：**
- Gradle 顺序执行每个 `build.gradle` 脚本（注意：此时 Task 只被"注册"和"配置"，不会被"执行"）。
- 构建 DAG：Gradle 根据 Task 的 `dependsOn` 关系建立有向无环图。
- 所有 `doFirst` / `doLast` 之外的代码都在此阶段执行。
- 配置阶段是单线程的（但可通过 `org.gradle.parallel=true` 实现多项目并行配置）。

**执行阶段细节：**
- 用户通过命令行指定的 Task（或默认 Task）及其所有依赖按 DAG 拓扑顺序执行。
- 只有需要执行的 Task 才会运行，已 `UP-TO-DATE` 的 Task 会被跳过。
- 支持 `--parallel` 并行执行独立的 Task。

**面试追问：如何在三个阶段插入自定义逻辑？**

```kotlin
// settings.gradle.kts — 初始化阶段
gradle.settingsEvaluated { println("Settings evaluated") }
gradle.projectsLoaded { println("Projects loaded: ${it.allprojects.size}") }

// build.gradle.kts — 配置阶段
gradle.beforeProject { println("Before: ${it.name}") }
gradle.afterProject { println("After: ${it.name}") }
gradle.projectsEvaluated { println("All projects evaluated") }

// build.gradle.kts — 执行阶段
gradle.taskGraph.whenReady { println("Task graph ready: ${it.allTasks.size} tasks") }
gradle.taskGraph.beforeTask { println("Before task: ${it.name}") }
gradle.taskGraph.afterTask { println("After task: ${it.name}") }
gradle.buildFinished { println("Build finished, success: ${it.failure == null}") }
```

---

### Q2: Task 的执行顺序和依赖关系如何控制？

Gradle 提供三级依赖控制：

**1. `dependsOn` — 强依赖（决定执行顺序和必要性）**
```kotlin
tasks.register("taskA") { doLast { println("A") } }
tasks.register("taskB") { dependsOn("taskA"); doLast { println("B") } }
tasks.register("taskC") { dependsOn("taskB"); doLast { println("C") } }
// 执行 taskC → 执行顺序: A → B → C
// 如果 taskA 失败，taskB 和 taskC 不会执行（默认行为）
```

**2. `mustRunAfter` — 顺序约束（仅排序，不创建依赖）**
```kotlin
tasks.register("compileKotlin") { /* ... */ }
tasks.register("lint") {
    mustRunAfter("compileKotlin")
    doLast { println("Linting...") }
}
// 执行 `gradle lint` → 只执行 lint，不强制执行 compileKotlin
// 执行 `gradle lint compileKotlin` → compileKotlin 先于 lint 执行
```

**3. `shouldRunAfter` — 软性顺序（可以被覆盖，用于优化）**
```kotlin
tasks.register("optimize") { shouldRunAfter("compile"); doLast { /* ... */ } }
```

**依赖解析的核心机制 — 拓扑排序：**

Gradle 将所有 Task 的依赖关系构建成 DAG，使用拓扑排序决定执行顺序。关键点：
- 多个无依赖关系的 Task 可以**并行执行**（`--parallel`）。
- 循环依赖会直接**报错**（因为必须是 DAG，不能有环）。
- `finalizedBy` 可以指定清理/收尾 Task，无论前置 Task 成功或失败都会执行。

```kotlin
tasks.register("build") { finalizedBy("cleanup") }
tasks.register("cleanup") { doLast { println("Always cleanup") } }
```

---

### Q3: 如何开发一个自定义 Gradle 插件？

完整的 Gradle 插件开发涉及三个核心组件：**Plugin** + **Extension** + **Task**。

**第一步：定义 Extension（扩展配置）**
```kotlin
// MethodCountExtension.kt
open class MethodCountExtension {
    var enabled: Boolean = true
    var threshold: Int = 5000          // 方法数阈值
    var outputFormat: String = "json"  // json | html | console
    var includeTestClasses: Boolean = false
}
```

**第二步：编写 Task（执行逻辑）**
```kotlin
// MethodCountTask.kt
import org.gradle.api.DefaultTask
import org.gradle.api.tasks.*

abstract class MethodCountTask : DefaultTask() {

    @Input
    val threshold: Int = 5000

    @InputFiles
    @Classpath
    val classFiles: FileCollection = project.files()

    @OutputFile
    val reportFile: File = project.buildDir.resolve("method-count/report.json")

    @TaskAction
    fun countMethods() {
        val dexFile = File.createTempFile("classes", ".dex")
        // 使用 d8 将 class 转为 dex（实际场景可用 ASM 直接读取 class）
        project.exec {
            it.commandLine("d8", classFiles.files.joinToString(":"), "--output", dexFile.absolutePath)
        }.assertNormalExitValue()

        // 解析 dex 文件头获取方法数
        val methodCount = parseDexMethodCount(dexFile)
        val report = """
            {
              "total_methods": $methodCount,
              "threshold": $threshold,
              "exceeded": ${methodCount > threshold}
            }
        """.trimIndent()

        reportFile.parentFile.mkdirs()
        reportFile.writeText(report)
        logger.lifecycle("📊 Total methods: $methodCount (threshold: $threshold)")
    }

    private fun parseDexMethodCount(dexFile: File): Int {
        // 简化实现：解析 dex 文件中所有 method_ids 的数量
        // 真实实现需要解析 dex 格式的 method_ids_size 字段
        return dexFile.readBytes().let { bytes ->
            // dex 文件头偏移 88 字节处是 method_ids_size (小端序)
            if (bytes.size > 92) {
                (bytes[88].toInt() and 0xFF) or
                ((bytes[89].toInt() and 0xFF) shl 8) or
                ((bytes[90].toInt() and 0xFF) shl 16) or
                ((bytes[91].toInt() and 0xFF) shl 24)
            } else 0
        }
    }
}
```

**第三步：编写 Plugin（注册入口）**
```kotlin
// MethodCountPlugin.kt
import org.gradle.api.Plugin
import org.gradle.api.Project

class MethodCountPlugin : Plugin<Project> {

    override fun apply(project: Project) {
        // 1. 创建 Extension
        val extension = project.extensions.create(
            "methodCount", MethodCountExtension::class.java
        )

        // 2. 注册 Task
        val methodCountTask = project.tasks.register("countMethods", MethodCountTask::class.java) { task ->
            // Task 配置延迟到执行前（避免配置阶段解析不必要的文件）
            task.threshold = extension.threshold
        }

        // 3. 在 AGP 任务完成后自动触发（Android 项目）
        project.afterEvaluate {
            if (extension.enabled) {
                project.tasks.matching { it.name.contains("compile") }.configureEach { compileTask ->
                    methodCountTask.configure {
                        // 将 compile 产出的 class 文件作为输入
                        classFiles = compileTask.outputs.files
                    }
                }
            }
        }

        project.logger.lifecycle("✅ MethodCountPlugin applied to ${project.name}")
    }
}
```

**第四步：注册插件（resources/META-INF）**
```
# src/main/resources/META-INF/gradle-plugins/method-count.properties
implementation-class=com.example.MethodCountPlugin
```

**使用方式：**
```kotlin
// 根项目 build.gradle.kts
plugins { id("method-count") version "1.0.0" }

// 配置
methodCount {
    enabled = true
    threshold = 60000  // 单 dex 65535 限制
}
```

---

### Q4: settings.gradle 的依赖解析和仓库配置

`settings.gradle` 承担两大职责：**项目结构定义** 和 **插件/依赖仓库管理**。

**依赖解析流程（四级缓存机制）：**

```
请求依赖 com.example:lib:1.0.0
          │
          ▼
  ┌───────────────┐
  │ 1. 本地缓存    │ ~/.gradle/caches/modules-2/files-2.1/
  │    (Gradle Cache)│ ← 命中则直接返回
  └───────┬───────┘
          │ 未命中
          ▼
  ┌───────────────┐
  │ 2. 本地 Maven  │ ~/.m2/repository/
  │    (mavenLocal) │ ← mavenLocal() 仓库
  └───────┬───────┘
          │ 未命中
          ▼
  ┌───────────────┐
  │ 3. 远程仓库    │ 按 declarationOrder 顺序查询
  │    (maven/google/jitpack) │ ← 找到即停止
  └───────┬───────┘
          │ 未命中
          ▼
  ┌───────────────┐
  │ 4. 构建失败    │ Could not resolve...
  └───────────────┘
```

**仓库配置策略（推荐）：**

```kotlin
// settings.gradle.kts
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
        // 私有仓库应通过凭证管理注入，不硬编码
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    // FAIL_ON_PROJECT_REPOS：禁止子项目单独声明仓库（统一管理）
    // PREFER_SETTINGS：settings 优先，但允许子项目覆盖
    // PREFER_PROJECT：子项目优先（不推荐）
    
    repositories {
        google()
        mavenCentral()
        maven { url = uri("https://jitpack.io") }
        // 阿里巴巴镜像（国内加速）
        maven { url = uri("https://maven.aliyun.com/repository/public") }
    }
}

// 版本目录 (Version Catalog) — 统一依赖版本管理
// gradle/libs.versions.toml
// [versions]
// kotlin = "1.9.0"
// [libraries]
// kotlin-stdlib = { module = "org.jetbrains.kotlin:kotlin-stdlib", version.ref = "kotlin" }
```

---

### Q5: Gradle vs Maven 全面对比

| 维度 | Gradle | Maven |
|------|--------|-------|
| **构建模型** | 有向无环图 (DAG)，基于 Task | 固定生命周期阶段 (phases) |
| **构建脚本** | Groovy / Kotlin DSL（编程式） | XML（声明式） |
| **灵活性** | 极高 — 可编程、动态 Task、条件逻辑 | 较低 — 必须遵循生命周期和插件约定 |
| **性能** | 增量编译 + 构建缓存 + Daemon 复用 | 仅增量编译（3.x 引入） |
| **学习曲线** | 陡峭 — DSL、生命周期、Provider API | 平缓 — XML 约定 > 配置 |
| **依赖管理** | 动态版本、排除规则、变体感知 | 传递依赖、scope 机制 |
| **插件生态** | AGP、Kotlin、Spring Boot 等 | 丰富成熟，中央仓库插件 |
| **多模块** | 原生支持，跨项目 Task 依赖 | 通过 `<modules>` 聚合 |
| **配置时间** | 较慢（Groovy DSL 解析）但可优化 | 较快 |
| **IDE 集成** | Android Studio 深度集成 | IntelliJ / Eclipse 原生支持 |

**核心哲学差异：**
- Maven：「约定优于配置」— 你只需要告诉 Maven 你的项目类型，它会自动按标准流程构建。
- Gradle：「可编程的构建」— 构建本身是一门编程语言，可以表达任意复杂的构建逻辑。

**一个直观对比 — 条件逻辑：**
```xml
<!-- Maven: 需要 profile 和 activation -->
<profiles>
    <profile>
        <id>release</id>
        <activation><property><name>release</name></property></activation>
        <build><plugins><!-- ... --></plugins></build>
    </profile>
</profiles>
```
```kotlin
// Gradle: 原生 if/else
if (project.hasProperty("release")) {
    // release 构建逻辑
}
```

---

### Q6: 增量编译原理和 Build Cache 机制

**增量编译（Incremental Compilation）— 输入/输出快照比对：**

Gradle 的增量编译基于 **Task 的输入输出快照（Snapshot）** 机制：

```
执行 Task 前：
  1. 计算所有 @Input / @InputFiles 的哈希值
  2. 与上一次构建的快照对比
  3. 如果输入完全一致 → Task 标记为 UP-TO-DATE，跳过执行
  4. 如果 @OutputFile/Directory 不存在 → 必须执行
  5. 如果有任何输入变化 → 执行 Task，更新快照
```

**关键注解：**
| 注解 | 作用 | 示例 |
|------|------|------|
| `@Input` | 影响 Task 输出的配置值 | `minSdkVersion`、`isDebuggable` |
| `@InputFiles` | 输入文件集合 | 源代码 `.kt/.java` 文件 |
| `@OutputFile` | 输出文件 | APK、AAR |
| `@OutputDirectory` | 输出目录 | `build/intermediates/` |
| `@Classpath` | classpath 文件 | 依赖的 jar |
| `@Internal` | 不影响增量的字段 | 日志开关 |

**Build Cache — 跨构建复用：**

```kotlin
// gradle.properties
org.gradle.caching=true
org.gradle.caching.debug=false  // 开启后可查看缓存命中/未命中原因
```

Build Cache 分为两级：
1. **Local Build Cache**：`~/.gradle/caches/build-cache-1/`，本机跨项目复用。
2. **Remote Build Cache**（HTTP）：CI 环境共享，所有开发者共享缓存。

**缓存键（Cache Key）计算：**
```
cacheKey = hash(
    Task 实现类全限定名,
    所有 @Input 属性值,
    所有 @InputFiles 文件内容哈希,
    classpath 文件内容哈希,
    依赖 Task 的 outputs 哈希
)
```

**面试高频追问 — 为什么有时 UP-TO-DATE 不生效？**
1. Task 未声明 `@Input`/`@Output` 注解。
2. 使用了 `System.currentTimeMillis()` 等非确定性输入。
3. 文件路径中包含绝对路径（CI 环境变化）。
4. `@InputFiles` 中的文件时间戳变化但内容未变（Gradle 默认使用内容哈希）。
5. `doFirst`/`doLast` 中修改了输入或依赖。

---

## 二~三、深入原理

### Task 的有向无环图 (DAG) 调度机制

Gradle 内部的 Task 调度器基于 **拓扑排序 + 并行执行池** 实现：

```
               :app:assembleDebug
              /          |          \
     compileDebug     processDebug     mergeDebug
     Kotlin/Java      Resources        Assets
         |                |                |
    :lib1:jar       :lib2:jar              |
         \              /                  |
          \            /                   |
           dexBuilderDebug                 |
                |                          |
           mergeDexDebug ──────────────────┘
                |
           packageDebug
                |
           assembleDebug ✅
```

**调度算法：**

```
1. 从用户请求的 entryTask 出发，遍历 dependsOn 构建完整 DAG
2. 拓扑排序：计算每个 Task 的入度（被多少 Task 依赖）
3. 入度为 0 的 Task 加入就绪队列
4. 并行执行器从就绪队列取 Task，分配到线程池
5. Task 完成后，将其所有后继 Task 的入度减 1
6. 重复步骤 3-5 直到所有 Task 执行完毕
7. 如果存在 Task 未执行（循环依赖），抛出异常
```

**并行执行配置：**
```kotlin
// gradle.properties
org.gradle.parallel=true                // 多模块并行
org.gradle.workers.max=4                // Worker API 线程数
org.gradle.configureondemand=true       // 按需配置（仅配置需要的项目）
```

---

### Gradle 生命周期回调详解

```
settings.gradle 评估
    │
    ├── settingsEvaluated       ← Settings 对象创建完成
    │
    ├── projectsLoaded          ← 所有 Project 对象创建完成
    │
    ▼
build.gradle 评估（每个 Project）
    │
    ├── beforeProject           ← 每个 Project 配置前
    ├── afterProject            ← 每个 Project 配置后
    │
    ├── projectsEvaluated       ← 所有 Project 配置完成
    │
    ▼
Task DAG 构建
    │
    ├── taskGraph.whenReady     ← DAG 构建完毕，可修改 Task 依赖
    │
    ▼
执行阶段
    │
    ├── taskGraph.beforeTask    ← 每个 Task 执行前
    ├── taskGraph.afterTask     ← 每个 Task 执行后
    │
    ├── buildFinished           ← 构建结束（无论成功/失败）
```

**关键回调实战用途：**
- `projectsEvaluated`：在所有项目配置完成后修改 Task 属性（如动态修改 versionCode）。
- `taskGraph.whenReady`：根据用户请求的 Task 动态添加依赖。
- `buildFinished`：生成构建报告、发送通知、清理临时文件。

---

### Transform API vs Artifact Transform API

**Transform API（AGP 3.x — 已废弃）：**

Transform 是 AGP 提供的字节码插桩机制，在 `.class` → `.dex` 过程中注册自定义转换：

```groovy
// 旧版 — 已废弃
class MyTransform extends Transform {
    @Override String getName() { return "myTransform" }
    @Override Set<QualifiedContent.ContentType> getInputTypes() { return TransformManager.CONTENT_CLASS }
    @Override Set<? super QualifiedContent.Scope> getScopes() { return TransformManager.SCOPE_FULL_PROJECT }
    @Override boolean isIncremental() { return true }
    
    @Override
    void transform(TransformInvocation invocation) {
        // 对 class 文件做字节码操作（ASM/Javassist）
    }
}
```

**Artifact Transform API（AGP 7.0+ 推荐）：**

基于 Gradle 原生的 `TransformAction` + `ArtifactType`：

```kotlin
// 新版 — Artifact Transform
abstract class AsmTransform : TransformAction<TransformParameters.None> {
    
    @get:InputArtifact
    abstract val inputArtifact: Provider<FileSystemLocation>
    
    override fun transform(outputs: TransformOutputs) {
        val input = inputArtifact.get().asFile
        val output = outputs.file(input.name.replace(".jar", "-transformed.jar"))
        // ASM 字节码操作
        ClassReader(input.readBytes()).accept(ClassWriter(0), 0)
        output.writeBytes(/* transformed bytes */)
    }
}

// 注册
abstract class MyPlugin : Plugin<Project> {
    override fun apply(project: Project) {
        val artifactType = ArtifactType::class.java
        project.dependencies {
            registerTransform(AsmTransform::class.java) {
                from.attribute(artifactType, "jar")
                to.attribute(artifactType, "transformed-jar")
            }
        }
    }
}
```

**对比：**
| | Transform API | Artifact Transform API |
|---|---|---|
| 所属 | AGP 专属 | Gradle 原生 |
| 状态 | 已废弃 | 活跃维护 |
| 增量支持 | 需要实现 | 框架自动处理 |
| 缓存 | 需手动处理 | 自动集成 Build Cache |
| 性能 | 较差（全量处理） | 更好（按需转换） |

---

### Gradle Daemon 的 JVM 复用机制

**Daemon 工作原理：**

```
首次构建：
  gradle assemble ──→ 启动 Daemon 进程 (JVM 冷启动)
                         │
  Daemon 进程 (长时间存活)  ├── 加载 Gradle 核心类
  PID: 12345              ├── 加载 settings.gradle
                          ├── 加载 build.gradle
                          ├── 分析依赖、解析 DAG
                          └── 执行 Task → 构建完成（进程不退出）

第二次构建：
  gradle assemble ──→ 复用 Daemon PID 12345
                         │
                         ├── ✅ JVM 已预热（类已加载）
                         ├── ✅ 脚本已缓存（增量解析）
                         ├── ✅ 依赖图已分析（仅变更部分重新解析）
                         └── 快速进入执行阶段
```

**Daemon 带来的性能提升：**
- 冷启动：~5-10 秒（加载 JVM + Gradle 核心类 + 脚本解析）
- 热构建：~0.5-2 秒（复用已预热的 Daemon）
- **加速比：5-10x**

**Daemon 配置优化：**
```properties
# gradle.properties
org.gradle.daemon=true                    # 启用 Daemon（默认 true）
org.gradle.daemon.idletimeout=10800000    # 空闲超时 3 小时 (ms)
org.gradle.jvmargs=-Xmx4g -Xms1g         # Daemon JVM 内存
org.gradle.jvmargs=-XX:MaxMetaspaceSize=512m  # 元空间上限
```

**Daemon 故障排查：**
```bash
# 查看运行的 Daemon
gradle --status

# 停止所有 Daemon
gradle --stop

# 查看 Daemon 日志
cat ~/.gradle/daemon/<version>/daemon-<pid>.out.log
```

---

## 四、可视化

### Gradle 构建三阶段流程图

```
┌─────────────────────────────────────────────────────────────────┐
│                    GRADLE 构建生命周期                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────────────────────────────────────────┐      │
│  │           阶段 1: INITIALIZATION (初始化)              │      │
│  │                                                      │      │
│  │   settings.gradle(.kts)                              │      │
│  │         │                                            │      │
│  │         ├── 解析 include / includeFlat               │      │
│  │         ├── 创建 Settings 对象                       │      │
│  │         ├── 创建 RootProject + SubProjects           │      │
│  │         └── 回调: settingsEvaluated → projectsLoaded │      │
│  │                                                      │      │
│  │   产出: Project 对象层次结构                          │      │
│  └──────────────────────┬───────────────────────────────┘      │
│                         │                                      │
│                         ▼                                      │
│  ┌──────────────────────────────────────────────────────┐      │
│  │           阶段 2: CONFIGURATION (配置)                 │      │
│  │                                                      │      │
│  │   遍历每个 Project:                                   │      │
│  │   ┌─────────────────────────────────────────────┐   │      │
│  │   │  :app/build.gradle.kts                      │   │      │
│  │   │  ├── plugins { id("com.android.application")}│   │      │
│  │   │  ├── android { compileSdk = 34 }            │   │      │
│  │   │  ├── dependencies { ... }                   │   │      │
│  │   │  └── tasks.register("myTask") { ... }       │   │      │
│  │   └─────────────────────────────────────────────┘   │      │
│  │   ┌─────────────────────────────────────────────┐   │      │
│  │   │  :lib1/build.gradle.kts                     │   │      │
│  │   │  └── ...                                    │   │      │
│  │   └─────────────────────────────────────────────┘   │      │
│  │                                                      │      │
│  │   Task DAG 构建:                                     │      │
│  │   ┌─────────────────────────────────────────────┐   │      │
│  │   │ 注册所有 Task → 建立 dependsOn 关系          │   │      │
│  │   │ → 拓扑排序 → 验证无环 → Task DAG 就绪        │   │      │
│  │   └─────────────────────────────────────────────┘   │      │
│  │                                                      │      │
│  │   回调: beforeProject → afterProject →               │      │
│  │         projectsEvaluated → taskGraph.whenReady      │      │
│  │                                                      │      │
│  │   产出: 完整的 Task DAG                               │      │
│  └──────────────────────┬───────────────────────────────┘      │
│                         │                                      │
│                         ▼                                      │
│  ┌──────────────────────────────────────────────────────┐      │
│  │           阶段 3: EXECUTION (执行)                    │      │
│  │                                                      │      │
│  │   ┌───────────────────────────────────────────┐     │      │
│  │   │  输入快照检查                               │     │      │
│  │   │  ┌─────────┐   ┌─────────┐   ┌─────────┐  │     │      │
│  │   │  │ UP-TO-DATE│   │ CHANGED │   │ NO-SRC │  │     │      │
│  │   │  │  ⏭ 跳过  │   │  ▶ 执行  │   │  ▶ 执行 │  │     │      │
│  │   │  └─────────┘   └─────────┘   └─────────┘  │     │      │
│  │   └───────────────────────────────────────────┘     │      │
│  │                                                      │      │
│  │   按 DAG 拓扑顺序 + 并行策略执行 Task:                 │      │
│  │   ┌───────────────────────────────────────────┐     │      │
│  │   │  compileKotlin ──→ compileJava            │     │      │
│  │   │       │                 │                 │     │      │
│  │   │       └──→ dexBuilder ──→ mergeDex ──→    │     │      │
│  │   │                              │            │     │      │
│  │   │              packageDebug ───┘            │     │      │
│  │   │                  │                        │     │      │
│  │   │              assembleDebug ✅              │     │      │
│  │   └───────────────────────────────────────────┘     │      │
│  │                                                      │      │
│  │   回调: beforeTask → afterTask → buildFinished        │      │
│  │                                                      │      │
│  │   产出: 构建产物 (APK / AAR / JAR / 测试报告等)        │      │
│  └──────────────────────────────────────────────────────┘      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Task DAG 依赖关系图

```
                    ┌──────────────────┐
                    │  assembleDebug   │ ◄── entry task（入口）
                    │  (Lifecycle Task) │
                    └────────┬─────────┘
                             │ dependsOn
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
    ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
    │ packageDebug│  │  lintDebug  │  │testDebugUnit│
    │ (产出 APK)  │  │  (静态检查) │  │  (单元测试) │
    └──────┬──────┘  └─────────────┘  └──────┬──────┘
           │ dependsOn                        │ dependsOn
           ▼                                  ▼
    ┌─────────────┐                    ┌──────────────┐
    │ mergeDexDebug│                   │compileDebug  │
    │ (合并 DEX)  │                   │Java/Kotlin   │
    └──────┬──────┘                    │Sources       │
           │                           └──────┬───────┘
           │ dependsOn                        │
           ▼                                  │
    ┌─────────────┐                           │
    │ dexBuilder  │                           │
    │ Debug       │◄──────────────────────────┘
    │ (class→dex) │    dependsOn
    └──────┬──────┘
           │
           │ dependsOn (多源)
           │
    ┌──────┴──────────────────────────────┐
    │                                      │
    ▼                                      ▼
┌───────────────┐                   ┌───────────────┐
│compileDebug   │                   │:lib1:compile  │
│Kotlin Sources │                   │DebugJava      │
│(app 模块)     │                   │(library 模块) │
└───────────────┘                   └───────┬───────┘
                                            │
                                   dependsOn│
                                            ▼
                                    ┌───────────────┐
                                    │:lib2:compile  │
                                    │DebugKotlin    │
                                    │(传递依赖)     │
                                    └───────────────┘

图例：
──▶  = dependsOn (强依赖，必须等前置完成)
 ⏭  = 被跳过 (UP-TO-DATE, 输入未变化)
 ✅  = 并行可执行 (无相互依赖)
```

---

## 五~六、实战 — 编写自定义 Gradle 插件（统计方法数）

### 完整项目结构

```
method-count-plugin/
├── build.gradle.kts
├── settings.gradle.kts
└── src/main/
    ├── kotlin/com/example/
    │   ├── MethodCountPlugin.kt
    │   ├── MethodCountExtension.kt
    │   └── MethodCountTask.kt
    └── resources/META-INF/gradle-plugins/
        └── method-count.properties
```

### build.gradle.kts（插件构建脚本）

```kotlin
plugins {
    `kotlin-dsl`
    `java-gradle-plugin`
    id("com.gradle.plugin-publish") version "1.2.0"
}

group = "com.example"
version = "1.0.0"

gradlePlugin {
    plugins {
        create("methodCount") {
            id = "com.example.method-count"
            implementationClass = "com.example.MethodCountPlugin"
            displayName = "Method Count Plugin"
            description = "统计 Android 项目的方法数，防止超过 65535 限制"
            tags.set(listOf("android", "method-count", "dex"))
        }
    }
}

dependencies {
    implementation("com.android.tools.build:gradle:8.2.0")
    implementation("org.ow2.asm:asm:9.6")           // 字节码操作
    implementation("org.ow2.asm:asm-commons:9.6")
}
```

### MethodCountExtension.kt

```kotlin
package com.example

import org.gradle.api.model.ObjectFactory
import org.gradle.api.provider.Property
import javax.inject.Inject

open class MethodCountExtension @Inject constructor(objects: ObjectFactory) {

    /** 是否启用方法数统计 */
    val enabled: Property<Boolean> = objects.property(Boolean::class.java).convention(true)

    /** 方法数警告阈值（默认 60000，留 5535 的缓冲） */
    val threshold: Property<Int> = objects.property(Int::class.java).convention(60000)

    /** 输出格式: console | json | html */
    val outputFormat: Property<String> = objects.property(String::class.java).convention("console")

    /** 是否包含测试代码 */
    val includeTests: Property<Boolean> = objects.property(Boolean::class.java).convention(false)

    /** 是否在超过阈值时让构建失败 */
    val failOnExceed: Property<Boolean> = objects.property(Boolean::class.java).convention(false)
}
```

### MethodCountTask.kt（核心逻辑 — ASM 实现）

```kotlin
package com.example

import org.gradle.api.DefaultTask
import org.gradle.api.file.ConfigurableFileCollection
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.*
import org.objectweb.asm.ClassReader
import java.io.BufferedInputStream
import java.util.jar.JarFile

abstract class MethodCountTask : DefaultTask() {

    @get:Input
    abstract val threshold: Property<Int>

    @get:Input
    abstract val outputFormat: Property<String>

    @get:Input
    abstract val failOnExceed: Property<Boolean>

    @get:InputFiles
    @get:Classpath
    abstract val classFiles: ConfigurableFileCollection

    @get:OutputFile
    abstract val reportFile: RegularFileProperty

    @TaskAction
    fun execute() {
        val methodCounts = mutableMapOf<String, Int>()
        var totalMethods = 0

        classFiles.forEach { file ->
            if (file.isDirectory) {
                // 处理目录中的 .class 文件
                file.walkTopDown()
                    .filter { it.extension == "class" }
                    .forEach { classFile ->
                        val count = countMethodsInClass(classFile)
                        val className = classFile.relativeTo(file).path
                        methodCounts[className] = count
                        totalMethods += count
                    }
            } else if (file.extension == "jar") {
                // 处理 jar 包（依赖库）
                JarFile(file).use { jar ->
                    jar.entries().asIterator().forEach { entry ->
                        if (!entry.isDirectory && entry.name.endsWith(".class")) {
                            val count = jar.getInputStream(entry).use { input ->
                                countMethodsInStream(input)
                            }
                            methodCounts[entry.name] = count
                            totalMethods += count
                        }
                    }
                }
            }
        }

        // 排序输出
        val sortedMethods = methodCounts.entries
            .sortedByDescending { it.value }
            .take(30) // Top 30

        generateReport(totalMethods, sortedMethods)

        // 检查阈值
        if (totalMethods > threshold.get() && failOnExceed.get()) {
            throw GradleException(
                "❌ 方法数 $totalMethods 超过阈值 ${threshold.get()}！请启用 Multidex 或优化依赖。"
            )
        }
    }

    /** 使用 ASM 精确统计单个 class 文件的方法数 */
    private fun countMethodsInClass(classFile: java.io.File): Int {
        return classFile.inputStream().buffered().use { countMethodsInStream(it) }
    }

    private fun countMethodsInStream(input: java.io.InputStream): Int {
        val reader = ClassReader(BufferedInputStream(input))
        val counter = MethodCounter()
        reader.accept(counter, ClassReader.SKIP_DEBUG or ClassReader.SKIP_FRAMES)
        return counter.count
    }

    /** 生成报告 */
    private fun generateReport(total: Int, topMethods: List<Map.Entry<String, Int>>) {
        val threshold = threshold.get()
        val exceeded = total > threshold
        val status = if (exceeded) "⚠️ 已超过" else "✅ 正常"

        when (outputFormat.get().lowercase()) {
            "json" -> {
                val json = buildString {
                    appendLine("{")
                    appendLine("  \"total_methods\": $total,")
                    appendLine("  \"threshold\": $threshold,")
                    appendLine("  \"exceeded\": $exceeded,")
                    appendLine("  \"top_classes\": [")
                    topMethods.forEachIndexed { i, (name, count) ->
                        append("    {\"class\": \"${name}\", \"methods\": $count}")
                        if (i < topMethods.size - 1) append(",")
                        appendLine()
                    }
                    appendLine("  ]")
                    appendLine("}")
                }
                reportFile.get().asFile.apply {
                    parentFile.mkdirs()
                    writeText(json)
                }
            }
            "html" -> {
                val html = buildString {
                    appendLine("<html><head><style>")
                    appendLine("body{font-family:monospace;margin:20px}")
                    appendLine(".exceeded{color:red}.normal{color:green}")
                    appendLine("table{border-collapse:collapse;width:100%}")
                    appendLine("th,td{border:1px solid #ddd;padding:8px;text-align:left}")
                    appendLine("th{background:#4CAF50;color:white}")
                    appendLine("</style></head><body>")
                    appendLine("<h1>方法数统计报告</h1>")
                    appendLine("<p>总计: <b class='${if (exceeded) "exceeded" else "normal"}'>$total</b> / $threshold</p>")
                    appendLine("<p>状态: <b>$status</b></p>")
                    appendLine("<table><tr><th>类名</th><th>方法数</th></tr>")
                    topMethods.forEach { (name, count) ->
                        appendLine("<tr><td>$name</td><td>$count</td></tr>")
                    }
                    appendLine("</table></body></html>")
                }
                reportFile.get().asFile.apply {
                    parentFile.mkdirs()
                    writeText(html)
                }
            }
            else -> {
                // console 输出（默认）
                val divider = "=".repeat(60)
                logger.lifecycle(divider)
                logger.lifecycle("  📊 方法数统计报告")
                logger.lifecycle(divider)
                logger.lifecycle("  总方法数: $total / $threshold  $status")
                logger.lifecycle("  剩余空间: ${65535 - total}")
                logger.lifecycle(divider)
                logger.lifecycle("  Top 30 类 (按方法数):")
                topMethods.forEachIndexed { i, (name, count) ->
                    val bar = "█".repeat((count.toFloat() / topMethods.first().value * 30).toInt().coerceAtLeast(1))
                    logger.lifecycle("  ${(i+1).toString().padStart(2)}. ${name.takeLast(50).padEnd(50)} $count $bar")
                }
                logger.lifecycle(divider)
            }
        }
    }
}

/** ASM ClassVisitor — 统计方法数 */
class MethodCounter : org.objectweb.asm.ClassVisitor(org.objectweb.asm.Opcodes.ASM9) {
    var count = 0

    override fun visitMethod(
        access: Int, name: String?, descriptor: String?,
        signature: String?, exceptions: Array<out String>?
    ): org.objectweb.asm.MethodVisitor? {
        count++
        return null // 不深入方法体，性能更高
    }
}
```

### MethodCountPlugin.kt（插件入口 — 完整版）

```kotlin
package com.example

import org.gradle.api.Plugin
import org.gradle.api.Project
import org.gradle.api.plugins.JavaPluginExtension
import org.gradle.api.tasks.SourceSetContainer
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.api.tasks.bundling.Jar
import org.gradle.kotlin.dsl.*

class MethodCountPlugin : Plugin<Project> {

    override fun apply(project: Project) {
        // 1. 注册扩展
        val extension = project.extensions.create(
            "methodCount", MethodCountExtension::class.java
        )

        // 2. 注册 Task
        val countTask = project.tasks.register<MethodCountTask>("countMethods") {
            group = "verification"
            description = "统计项目方法数，防止超过 65535 限制"

            // 延迟绑定配置值
            threshold.set(extension.threshold)
            outputFormat.set(extension.outputFormat)
            failOnExceed.set(extension.failOnExceed)
            reportFile.set(project.layout.buildDirectory.file("reports/method-count/report.json"))
        }

        // 3. 自动关联编译产物
        project.afterEvaluate {
            if (!extension.enabled.get()) return@afterEvaluate

            // Android 项目：关联 compileDebugJavaWithJavac 等 Task 的输出
            project.tasks.matching { 
                it.name.matches(Regex("compile.*(Java|Kotlin)")) 
            }.configureEach { compileTask ->
                countTask.configure {
                    classFiles.from(compileTask.outputs.files)
                }
            }

            // 如果是纯 Java/Kotlin 项目
            project.plugins.withId("java") {
                val sourceSets = project.extensions.getByType(SourceSetContainer::class.java)
                countTask.configure {
                    classFiles.from(
                        sourceSets.named("main").get().output
                    )
                }
            }

            // 将 countMethods 挂接到 check 生命周期
            project.tasks.findByName("check")?.dependsOn(countTask)
        }
        
        project.logger.lifecycle("🔌 MethodCountPlugin applied to project '${project.name}'")
    }
}
```

### 使用方式

```kotlin
// 根项目 build.gradle.kts
plugins {
    id("com.example.method-count") version "1.0.0"
}

// 配置插件
methodCount {
    enabled.set(true)
    threshold.set(60000)
    outputFormat.set("console")  // console | json | html
    failOnExceed.set(false)      // 设为 true 可在 CI 中阻断构建
}
```

**命令行执行：**
```bash
# 手动执行方法数统计
./gradlew countMethods

# 挂靠到 check 后，执行 check 时自动运行
./gradlew check

# CI 环境严格模式
./gradlew countMethods -PmethodCount.failOnExceed=true
```

---

## 补充面试要点速查

| 考察点 | 核心知识点 |
|--------|-----------|
| **Provider API** | `Property<T>` 延迟求值，避免配置阶段解析不必要的值 |
| **Configuration Cache** | Gradle 8.x 新特性，缓存配置阶段结果，跳过脚本解析 |
| **Variant Awareness** | 依赖变体感知 — debug/release、api/implementation 自动匹配 |
| **Composite Builds** | `includeBuild` 引入外部项目，替代 `mavenLocal` |
| **Worker API** | `WorkerExecutor` 并行执行独立工作单元，复用 JVM |
| **Task Configuration Avoidance** | `tasks.register` 而非 `tasks.create`，延迟 Task 实例化 |

---

> **文档版本**: v1.0  
> **适用场景**: Android 面试 — Gradle 构建系统深度考察  
> **建议配合**: 实际项目中的 `build.gradle.kts` 阅读 + 动手编写一个 Task 或 Plugin
