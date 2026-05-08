# CI/CD 流程 — Android 工程化核心

---

## 一、面试高频：Jenkins Pipeline / 增量构建 / AAB 发布 / 多环境

### Q1：Jenkins Pipeline 的 Groovy 脚本与 Jenkinsfile 怎么写？Declarative vs Scripted 怎么选？

**答案要点：**

Jenkins Pipeline 用 Groovy DSL 定义构建流程。两种风格：

**Declarative Pipeline（声明式）— 推荐：**
```groovy
pipeline {
    agent any
    environment {
        GRADLE_OPTS = '-Dorg.gradle.daemon=true'
    }
    stages {
        stage('Checkout') {
            steps { checkout scm }
        }
        stage('Build') {
            parallel {
                stage('Debug') {
                    steps { sh './gradlew assembleDebug' }
                }
                stage('UnitTest') {
                    steps { sh './gradlew testDebugUnitTest' }
                }
            }
        }
        stage('Publish') {
            when { branch 'release' }
            steps { sh './gradlew bundleRelease' }
        }
    }
    post {
        failure { emailext body: '${BUILD_URL} 构建失败', subject: 'FAIL', to: 'dev@team.com' }
        success { archiveArtifacts 'app/build/outputs/**/*.apk' }
    }
}
```

**Scripted Pipeline（脚本式）— 灵活但复杂：**
```groovy
node('android') {
    try {
        stage('Checkout') { checkout scm }
        stage('Build') { sh './gradlew assembleDebug' }
    } catch (e) {
        currentBuild.result = 'FAILURE'
        throw e
    } finally {
        junit '**/test-results/**/*.xml'
    }
}
```

**对比：** Declarative 有严格结构（pipeline/stages/steps/post），语法校验好，适合标准化团队；Scripted 更灵活适合复杂条件分支，但维护成本高。**实际选型：90% 场景用 Declarative，复杂动态 Pipeline 用 Shared Library + Scripted。**

**Jenkinsfile 最佳实践：**
- 放入项目根目录，随代码版本化
- 用 `Shared Library` 抽取公共逻辑（如签名、上传）
- 敏感信息用 `credentials()` 绑定，绝不硬编码
- `when` 条件控制阶段执行，减少不必要构建

---

### Q2：CI 中增量构建策略怎么做？如何实现变更检测 + 缓存？

**答案要点：**

Android 项目 CI 最耗时的两个环节：Gradle 构建和单测。增量策略三层：

**第一层：变更检测（Change Detection）— 决定「要不要构建」**

```bash
# 基于 git diff 检测模块变更
CHANGED_MODULES=$(git diff --name-only HEAD~1 | grep '^module_' | cut -d'/' -f1 | sort -u)

if echo "$CHANGED_MODULES" | grep -q "app"; then
    echo "app模块变更，触发完整构建"
    ./gradlew assembleDebug
else
    echo "仅构建变更模块: $CHANGED_MODULES"
    for mod in $CHANGED_MODULES; do
        ./gradlew :$mod:assembleDebug
    done
fi
```

进阶：用 Gradle `configure-on-demand` + 模块间依赖图自动推导受影响模块。

**第二层：Gradle 构建缓存（Build Cache）— 加速「怎么构建」**

```properties
# gradle.properties
org.gradle.caching=true
org.gradle.parallel=true
org.gradle.configure-on-demand=true
org.gradle.jvmargs=-Xmx4g -XX:MaxMetaspaceSize=512m
```

- **本地缓存**：CI 节点保留 `~/.gradle/caches`，同一节点反复构建命中率高
- **远程缓存**：用 Gradle Enterprise 或自建 HTTP 缓存节点，多 CI 节点共享缓存
- **关键**：`outputs.cacheIf { true }` 标记 Task 可缓存，确保 Task 输入输出声明准确

**第三层：测试分层执行 — 细化「构建什么」**

```bash
# 仅跑变更模块的单元测试
./gradlew $(echo $CHANGED_MODULES | sed 's/ /:testDebugUnitTest /g'):testDebugUnitTest

# UI 测试仅在 release 分支跑
if [ "$BRANCH" = "release" ]; then
    ./gradlew connectedAndroidTest
fi
```

**实战指标：** 合理配置后增量构建可从 15 分钟降到 2-3 分钟。

---

### Q3：AAB（Android App Bundle）的发布流程和 Google Play 管理怎么做？

**答案要点：**

**AAB vs APK 核心差异：**
- APK：包含所有资源，用户下载完整包
- AAB：上传到 Google Play，由 Play 动态生成 Split APK，用户仅下载所需部分（按屏幕密度/CPU架构/语言拆分），体积平均减少 35%

**标准发布流水线：**

```mermaid
graph LR
    A[代码合入release分支] --> B[CI触发bundleRelease]
    B --> C[签名: jarsigner/apksigner]
    C --> D[生成 .aab 产物]
    D --> E[上传 Google Play Console]
    E --> F[内部测试轨道 Internal Test]
    F --> G[Alpha 封闭测试]
    G --> H[Beta 开放测试]
    H --> I[Production 分阶段发布]
```

**关键脚本：**

```bash
# 1. 构建 AAB
./gradlew bundleRelease

# 2. jarsigner 签名
jarsigner -verbose -sigalg SHA256withRSA -digestalg SHA-256 \
    -keystore release.keystore \
    app/build/outputs/bundle/release/app-release.aab \
    alias_name

# 3. 上传 Google Play（用 gradle-play-publisher 插件）
./gradlew publishBundle
```

**Google Play 管理要点：**

- **轨道管理**：Internal → Alpha → Beta → Production，递进式发布
- **分阶段发布（Staged Rollout）**：Production 先推 10% → 观察崩溃率 → 全量
- **紧急修复**：可以直接替换 AAB，versionCode 自增即可
- **签名管理**：推荐 Google Play App Signing（Play 保管签名密钥），也可以选择自管密钥

---

### Q4：多环境构建（dev / staging / release）如何做配置管理？

**答案要点：**

**方案一：Product Flavor（推荐）**

```groovy
// app/build.gradle
android {
    flavorDimensions "env"
    productFlavors {
        dev {
            dimension "env"
            applicationIdSuffix ".dev"
            versionNameSuffix "-dev"
            buildConfigField "String", "BASE_URL", '"https://dev-api.example.com"'
            resValue "string", "app_name", "MyApp Dev"
        }
        staging {
            dimension "env"
            applicationIdSuffix ".staging"
            buildConfigField "String", "BASE_URL", '"https://staging-api.example.com"'
        }
        release {
            dimension "env"
            buildConfigField "String", "BASE_URL", '"https://api.example.com"'
        }
    }
}
```

**方案二：BuildConfig 字段 + CI 注入**

```groovy
buildTypes {
    debug {
        buildConfigField "String", "API_URL", "\"${System.getenv('API_URL') ?: 'https://dev.example.com'}\""
    }
}
```

```bash
# CI 注入环境变量
export API_URL="https://staging.example.com"
./gradlew assembleDebug
```

**方案对比：**

| 维度 | Product Flavor | CI 注入 |
|------|---------------|---------|
| 类型安全 | 编译期确定 | 运行时可变 |
| 多 APK 共存 | 支持（不同 applicationId） | 不支持 |
| 配置版本化 | 代码内版本化 | 依赖 CI 变量 |
| 适用场景 | 需要同时安装多版本 | 简单环境切换 |

**最佳实践：** dev/staging 用 Flavor（需同时安装），release 环境用 BuildConfig + CI 注入（避免误提交生产配置）。

---

## 二、架构原理：Jenkins Master-Agent 分布式构建

### Master-Agent 架构详解

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│   Master    │────▶│  Agent 1     │     │  Agent 2     │
│  (调度中心)  │     │  (linux,     │     │  (macOS,     │
│             │     │  android_sdk) │     │  xcode+iOS)  │
│  任务队列   │     └──────────────┘     └──────────────┘
│  负载均衡   │     ┌──────────────┐
│  Web UI    │────▶│  Agent 3     │
└─────────────┘     │  (windows)   │
                    └──────────────┘
```

**核心概念：**

- **Master**：负责任务调度、管理 Agent 连接、展示构建结果。不直接执行构建任务（生产环境）。
- **Agent（原 Slave）**：实际执行构建任务的节点。通过 JNLP（Java Web Start）或 SSH 与 Master 通信。
- **Label**：给 Agent 打标签，Pipeline 中用 `agent { label 'android' }` 指定执行节点。

**连接方式：**

1. **SSH 方式**（推荐）：Master 通过 SSH 主动连接 Agent，需配置 SSH 密钥
2. **JNLP 方式**：Agent 主动连接 Master，适合动态 Agent（如 Docker 容器）
3. **Docker / K8s Agent**：每次构建启动新容器，构建完销毁，环境隔离极好

**Android 项目 Agent 配置：**

```groovy
pipeline {
    agent {
        docker {
            image 'android-sdk:33'
            args '-v /cache/gradle:/root/.gradle'  // 挂载缓存
        }
    }
    // ...
}
```

**常见问题：**
- **Agent 离线**：Master 心跳检测，超时自动标记 offline
- **环境不一致**：用 Docker 镜像或 Ansible 统一 Agent 环境
- **资源竞争**：设置 `executors` 数量限制并发任务，Android 构建建议 limit=2

---

## 三、GitLab CI：YAML 语法与 Runner 机制

### .gitlab-ci.yml 核心语法

```yaml
# .gitlab-ci.yml
stages:
  - build
  - test
  - deploy

variables:
  GRADLE_OPTS: "-Dorg.gradle.daemon=true"
  ANDROID_COMPILE_SDK: "33"

# 缓存：跨 Job 复用
cache:
  key: ${CI_COMMIT_REF_SLUG}
  paths:
    - .gradle/wrapper
    - .gradle/caches
  policy: pull-push          # 既拉取又上传缓存

before_script:
  - export GRADLE_USER_HOME=$(pwd)/.gradle
  - chmod +x ./gradlew

# 构建 Job
build_debug:
  stage: build
  tags:
    - android                   # 指定 Runner 标签
  script:
    - ./gradlew assembleDebug
  artifacts:
    paths:
      - app/build/outputs/apk/
    expire_in: 7 days
  only:
    - merge_requests
    - develop

# 单元测试 Job
unit_test:
  stage: test
  tags:
    - android
  script:
    - ./gradlew testDebugUnitTest
  artifacts:
    reports:
      junit: app/build/test-results/**/TEST-*.xml

# AAB 发布 Job
publish_bundle:
  stage: deploy
  tags:
    - android
  script:
    - ./gradlew bundleRelease
    - ./gradlew publishBundle      # gradle-play-publisher 插件
  only:
    - /^release\/.*$/
  when: manual                     # 手动触发
```

### GitLab Runner 三种类型

| 类型 | 说明 | 适用场景 |
|------|------|----------|
| **Shared Runner** | GitLab 实例共享，所有项目可用 | 团队小、构建量少 |
| **Group Runner** | 组内所有项目共享 | 部门级共享 |
| **Specific Runner** | 单个项目专用 | 特殊环境需求 |

**Runner Executor 选择：**

```bash
# Docker Executor（最常用）
gitlab-runner register \
  --executor docker \
  --docker-image android-sdk:33 \
  --docker-volumes /cache:/cache

# Shell Executor（直接使用宿主机环境）
gitlab-runner register --executor shell
```

**Runner 配置最佳实践：**
- Android 构建用 Docker Executor，镜像预装 SDK
- 挂载 Gradle 缓存卷，避免重复下载依赖
- 设置 `concurrent` 控制并行任务数
- 为 release 构建设置单独的 Protected Runner

### Jenkins vs GitLab CI 对比

| 维度 | Jenkins | GitLab CI |
|------|---------|-----------|
| 配置方式 | Jenkinsfile（Groovy） | .gitlab-ci.yml（YAML） |
| 可视化 | 插件丰富但老旧 | 原生简洁 |
| 插件生态 | 极丰富（1500+） | 有限 |
| 部署复杂度 | 需要额外部署 Master | GitLab 内置 |
| 代码仓库集成 | 需额外配置 Webhook | 原生深度集成 |
| 适合团队 | 复杂定制需求 | 简单标准化流程 |

---

## 四、CI/CD 完整流水线图

### 端到端 Android CI/CD 流程

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          CI/CD 完整流水线                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────┐   ┌─────────┐   ┌──────────┐   ┌──────────┐   ┌─────────┐ │
│  │  代码   │   │  持续   │   │  自动化  │   │  制品    │   │ 持续    │ │
│  │  提交   │──▶│  集成   │──▶│  测试    │──▶│  管理    │──▶│ 部署    │ │
│  └─────────┘   └─────────┘   └──────────┘   └──────────┘   └─────────┘ │
│       │             │              │               │              │      │
│       ▼             ▼              ▼               ▼              ▼      │
│  ┌─────────┐   ┌─────────┐   ┌──────────┐   ┌──────────┐   ┌─────────┐ │
│  │ Merge   │   │ 静态    │   │ 单元测试  │   │ APK/AAB  │   │ Internal│ │
│  │Request  │   │ 检查    │   │ UI 测试  │   │ 归档     │   │ Track   │ │
│  │ │       │   │ Lint    │   │ 覆盖率   │   │ 版本标   │   │    │    │ │
│  │ ▼       │   │ Detekt  │   │ Monkey   │   │ mapping  │   │    ▼    │ │
│  │分支     │   │ ktlint  │   │          │   │          │   │ Alpha   │ │
│  │保护     │   │ 安全扫  │   │          │   │          │   │    │    │ │
│  │         │   │         │   │          │   │          │   │    ▼    │ │
│  │         │   │         │   │          │   │          │   │ Beta    │ │
│  │         │   │         │   │          │   │          │   │    │    │ │
│  │         │   │         │   │          │   │          │   │    ▼    │ │
│  │         │   │         │   │          │   │          │   │Product  │ │
│  └─────────┘   └─────────┘   └──────────┘   └──────────┘   └─────────┘ │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                       质量门禁 (Quality Gate)                     │  │
│  │   ✓ 静态分析通过   ✓ 单测覆盖率 > 80%   ✓ 崩溃率 < 0.1%         │  │
│  │   ✓ APK 体积增量 < 500KB              ✓ 无高危安全漏洞          │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

### 分支策略与流水线映射

| 分支 | 触发条件 | 流水线阶段 | 产物 |
|------|---------|-----------|------|
| `feature/*` | MR 创建 → 触发 | Lint + 编译 + 单元测试 | 仅构建验证 |
| `develop` | Merge 后触发 | 完整检查 + 生成 dev Apk | dev 包上内部分发 |
| `release/*` | 手动或定时触发 | 全量测试 + 生成 AAB | 上传 Internal Track |
| `hotfix/*` | MR 创建 → 触发 | 加速流水线（跳过部分测试） | 紧急修复包 |
| `main/master` | Merge + Tag | 仅生成 Release AAB | 正式发布包 |

---

## 五、组件化工程的 CI Pipeline 设计（上）：架构与策略

### 组件化 CI 的核心挑战

在一个 50+ 模块的组件化 Android 工程中，全量构建可能需要 30-60 分钟。CI 的核心挑战是：**只构建和测试受影响的模块**。

### 模块依赖拓扑感知

```
         ┌──────┐
         │ app  │ (壳工程)
         └──┬───┘
    ┌───────┼───────┐
    ▼       ▼       ▼
┌──────┐ ┌──────┐ ┌──────┐
│login │ │home  │ │user  │ (业务模块)
└──┬───┘ └──┬───┘ └──┬───┘
    │       │       │
    └───────┼───────┘
            ▼
    ┌─────────────┐
    │ common_base  │ (基础库)
    └──────┬───────┘
           ▼
    ┌─────────────┐
    │ net_framework│ (网络层)
    └─────────────┘
```

**核心问题：** 如果 `net_framework` 变更，所有上层模块都需要重新测试；但如果 `login` 变更，只影响 `app` 和自身。

### 变更影响分析算法

```python
# 伪代码：基于 git diff + 依赖图的影响分析
def get_affected_modules(changed_files, dependency_graph):
    """
    changed_files: git diff 变更文件列表
    dependency_graph: {module: [dependent_modules]}
    返回需要重新构建和测试的模块集合
    """
    # 1. 定位直接变更的模块
    directly_changed = set()
    for f in changed_files:
        module = extract_module_from_path(f)  # e.g., "login/" → "login"
        if module:
            directly_changed.add(module)

    # 2. 沿依赖图 BFS 传播影响
    affected = set(directly_changed)
    queue = list(directly_changed)
    while queue:
        current = queue.pop(0)
        for dependent in dependency_graph.get(current, []):
            if dependent not in affected:
                affected.add(dependent)
                queue.append(dependent)

    return affected
```

### CI 配置中的模块选择

```groovy
// Jenkinsfile 中的模块选择逻辑
def changedModules = getChangedModules()  // 调用 git diff 脚本
def affectedModules = resolveDependencyGraph(changedModules) // 依赖图分析

stage('Build Affected Modules') {
    steps {
        script {
            def gradleTasks = affectedModules.collect { ":${it}:assembleDebug" }
            sh "./gradlew ${gradleTasks.join(' ')}"
        }
    }
}

stage('Test Affected Modules') {
    steps {
        script {
            def testTasks = affectedModules.collect { ":${it}:testDebugUnitTest" }
            sh "./gradlew ${testTasks.join(' ')}"
        }
    }
}

stage('Assemble App') {
    when {
        // 仅当 app 模块或传递给 app 的模块变更时才组装
        expression { affectedModules.contains('app') }
    }
    steps {
        sh './gradlew :app:assembleDebug'
    }
}
```

---

## 六、组件化工程的 CI Pipeline 设计（下）：实战与优化

### 完整的组件化 CI 流水线

```yaml
# .gitlab-ci.yml — 组件化项目实战

stages:
  - detect_change    # 变更检测
  - static_check     # 静态检查（并行）
  - build            # 增量构建
  - test             # 分层测试
  - assemble         # 组装 APK（条件执行）
  - report           # 报告聚合

variables:
  GRADLE_OPTS: "-Dorg.gradle.daemon=true"

# ===== Stage 1: 变更检测 =====
change_detection:
  stage: detect_change
  script:
    - |
      CHANGED=$(git diff --name-only $CI_MERGE_REQUEST_DIFF_BASE_SHA...$CI_COMMIT_SHA)
      echo "$CHANGED" > changed_files.txt

      # 提取变更模块
      MODULES=$(echo "$CHANGED" | grep "^modules/" | cut -d'/' -f2 | sort -u)
      echo "CHANGED_MODULES=$MODULES" > changed_modules.env

      # 判断基础库是否变更（影响全局）
      if echo "$MODULES" | grep -qE "common_base|net_framework"; then
        echo "FULL_BUILD=true" >> changed_modules.env
      else
        echo "FULL_BUILD=false" >> changed_modules.env
      fi
  artifacts:
    reports:
      dotenv: changed_modules.env
    paths:
      - changed_files.txt
  only:
    - merge_requests

# ===== Stage 2: 静态检查（并行，仅变更模块）=====
lint:
  stage: static_check
  needs: [change_detection]
  parallel:
    matrix:
      - MODULE: $CHANGED_MODULES
  script:
    - echo "Run lint on $MODULE"
    - ./gradlew :modules:$MODULE:lint
  allow_failure: true

detekt:
  stage: static_check
  needs: [change_detection]
  script:
    - ./gradlew detekt
  allow_failure: true

# ===== Stage 3: 增量构建 =====
incremental_build:
  stage: build
  needs: [change_detection, lint, detekt]
  cache:
    key: ${CI_COMMIT_REF_SLUG}
    paths:
      - .gradle
    policy: pull-push
  script:
    - |
      if [ "$FULL_BUILD" = "true" ]; then
        echo "基础库变更，触发全量构建"
        ./gradlew assembleDebug
      else
        echo "增量构建模块: $CHANGED_MODULES"
        for mod in $CHANGED_MODULES; do
          ./gradlew :modules:$mod:assembleDebug
        done
      fi

# ===== Stage 4: 分层测试 =====
unit_test:
  stage: test
  needs: [incremental_build]
  parallel:
    matrix:
      - MODULE: $CHANGED_MODULES
  script:
    - ./gradlew :modules:$MODULE:testDebugUnitTest
  artifacts:
    reports:
      junit: modules/$MODULE/build/test-results/**/TEST-*.xml

ui_test:
  stage: test
  needs: [incremental_build]
  script:
    - ./gradlew :app:connectedAndroidTest
  only:
    - merge_requests
  when: manual
  allow_failure: true

# ===== Stage 5: APK 组装（条件执行）=====
assemble_app:
  stage: assemble
  needs: [unit_test]
  script:
    - |
      # 仅当 app 模块或依赖链上模块变更时
      if echo "$CHANGED_MODULES" | grep -qv "base_only"; then
        ./gradlew :app:assembleDebug
      fi
  artifacts:
    paths:
      - app/build/outputs/apk/
    expire_in: 7 days

# ===== Stage 6: 报告聚合 =====
coverage_report:
  stage: report
  needs: [unit_test]
  script:
    - ./gradlew jacocoTestReport
    - ./gradlew sonarqube \
        -Dsonar.projectKey=myapp \
        -Dsonar.host.url=$SONAR_URL
  coverage: '/Total.*?([0-9]{1,3})%/'
  only:
    - develop
    - merge_requests
```

### 七个实战优化策略

**1. 远程 Build Cache + 模块级缓存**

```properties
# gradle.properties
org.gradle.caching=true
org.gradle.cache.remote.enabled=true
org.gradle.cache.remote.server=https://build-cache.internal.company.com
```

**2. Gradle Configuration Cache（Gradle 7.5+）**

```bash
./gradlew assembleDebug --configuration-cache
```

首次慢，后续 Task 图配置阶段（Configuration Phase）跳过，提速 30-60%。

**3. 动态依赖版本管理**

```toml
# libs.versions.toml（Gradle Version Catalog）
[versions]
kotlin = "1.9.0"
compose = "1.5.0"

[libraries]
kotlin-stdlib = { module = "org.jetbrains.kotlin:kotlin-stdlib", version.ref = "kotlin"}

# CI 中可以用环境变量覆盖：
# export KOTLIN_VERSION=1.9.10 && ./gradlew build
```

**4. 条件跳过模块发布**

```groovy
// 仅对变更模块执行发布（Maven/Nexus）
afterEvaluate { project ->
    project.tasks.matching { it.name.startsWith("publish") }.configureEach {
        onlyIf {
            project.name in System.getenv("CHANGED_MODULES")?.split(",") ?: []
        }
    }
}
```

**5. CI 资源调度优化**

- 开发分支：使用低配 Agent（2C4G），超时 30 分钟
- Release 分支：高配 Agent（8C16G），禁用并行任务避免资源竞争
- 夜间定时全量构建 + 代码质量报告

**6. 构建失败快速定位**

```bash
# 收集构建上下文
mkdir -p build-info
cp gradle.properties build-info/
cp local.properties build-info/
./gradlew build --scan  # 生成 Gradle Build Scan 链接
```

**7. 自定义 Gradle Task 做构建分析**

```groovy
tasks.register("ciBuildReport") {
    doLast {
        println "=== Build Time Report ==="
        gradle.taskGraph.allTasks.each { task ->
            if (task.state.didWork) {
                println "${task.path}: ${task.state.duration}"
            }
        }
    }
}
```

### 关键指标与监控

| 指标 | 目标值 | 监控方式 |
|------|--------|---------|
| MR 流水线耗时 | < 15 分钟 | CI 内置 duration 统计 |
| 构建成功率 | > 95% | Prometheus + Grafana |
| 增量构建命中率 | > 70% | 自定义日志收集 |
| 缓存命中率 | > 80% | Gradle Build Scan |
| Flaky Test 比例 | < 2% | 重跑标记 + JUnit 报告分析 |

---

## 总结

CI/CD 在 Android 工程化中不是一次性搭建完成的，而是持续演进的：

- **Level 1**：能编译、能打包（手工 Jenkins Job）
- **Level 2**：MR 自动触发、单测（Jenkinsfile 版本化）
- **Level 3**：增量构建、远程缓存、多环境（15 分钟内反馈）
- **Level 4**：组件化智能构建、自动化发布、质量门禁（零人工干预发布）

面试中展现你对从「能用」到「好用」再到「智能化」的演进理解，远比背命令更有说服力。
