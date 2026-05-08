# 单元测试与自动化测试 — 面试深度内容

---

## 第一层：面试高频题（5+ 题）

### Q1: JUnit4 与 JUnit5 在 Android 开发中的对比

**JUnit4** 是 Android 单元测试的长期默认框架，核心注解包括 `@Test`、`@Before`、`@After`、`@BeforeClass`、`@AfterClass`、`@Ignore`、`@RunWith`。Android 早期通过 `AndroidJUnitRunner` 将其与 Instrumentation 测试桥接。JUnit4 的局限在于：所有 `@Before` 执行完毕后才能运行测试，且规则（Rule）机制虽然灵活但不够直观；参数化测试依赖 `Parameterized` Runner，导致一个类只能有一种参数化方式，扩展性差。

**JUnit5**（Jupiter）带来架构革新：`@BeforeEach` / `@AfterEach` 替代 lifecycle 注解，`@DisplayName` 提升可读性，`@Nested` 支持内嵌测试类以分组场景，`@ParameterizedTest` + `@ValueSource` / `@CsvSource` / `@MethodSource` 实现多种参数化方式并存，`@ExtendWith` 取代 `@RunWith`，扩展模型更灵活。Android 官方从 AGP 7.0 开始实验性支持 JUnit5，通过 `android-junit5` Gradle 插件可将 Jupiter 引擎注入 Instrumentation 测试。

**面试要点**：JUnit5 不是 JUnit4 的简单升级，而是完全重写的测试引擎；JUnit5 的 Launcher API 允许同时运行 JUnit4 和 JUnit5 测试，实现平滑迁移。

---

### Q2: Mockito 中 mock() 与 spy() 的核心区别

| 维度 | `mock()` | `spy()` |
|------|----------|---------|
| 创建方式 | `mock(Class)` 创建全虚假对象 | `spy(new RealObj())` 包裹真实对象 |
| 默认行为 | 所有方法返回默认值（null/0/false） | 调用真实实现 |
| 桩设置 | `when(mock.method()).thenReturn(...)` | `doReturn(...).when(spy).method()`（避免触发真实方法） |
| 使用场景 | 隔离外部依赖，不需要真实逻辑 | 部分 mock，验证真实对象的部分行为 |

**关键陷阱**：对 spy 使用 `when(spy.method())` 会先**真实调用** `method()`，可能导致 NPE 或副作用。必须用 `doReturn().when(spy).method()` 绕过真实调用。

**面试延伸**：`@Mock` vs `@Spy` 注解，`@InjectMocks` 自动注入依赖的原理（先通过构造器，再 setter，最后字段反射注入）。

---

### Q3: Espresso UI 测试原理 — onView + ViewMatcher + ViewAction 三剑客

Espresso 的核心流程是 **find → interact → assert**：

```kotlin
// 1. onView(ViewMatcher) — 定位控件
onView(withId(R.id.button))           // ID 匹配
onView(withText("提交"))               // 文本匹配
onView(allOf(withId(R.id.input), isDisplayed()))  // 组合匹配

// 2. perform(ViewAction) — 执行操作
.perform(click())
.perform(typeText("hello"), closeSoftKeyboard())
.perform(swipeLeft())

// 3. check(ViewAssertion) — 断言验证
.check(matches(isDisplayed()))
.check(matches(withText("hello")))
.check(matches(withEffectiveVisibility(Visibility.VISIBLE)))
```

**底层机制**：Espresso 在主线程空闲时（通过 `IdlingResource` 监控）才执行操作，避免测试与 UI 渲染竞态。`onView()` 返回 `ViewInteraction`，它内部维护一个 `ViewFinder` 在 View 树中递归查找匹配的 View；`perform()` 通过 `ViewAction` 接口的 `perform(UiController, View)` 方法在 UI 线程同步执行操作。

**Hierarchy 调试技巧**：当 `onView` 找不到控件时，使用 `onView(withId(R.id.root)).check(matches(isDisplayed()))` 验证根 View，或打印 View 层级树来排查。

---

### Q4: 测试金字塔 — Unit / Integration / E2E 的权衡

**金字塔模型（自上而下）**：

- **E2E（端到端测试）**：最顶层，数量最少。模拟真实用户操作，覆盖完整业务流程。在 Android 中通常用 Espresso + UI Automator 实现。**优点**：最接近真实场景；**缺点**：慢（秒级）、脆弱（UI 变化即失效）、难维护。
- **Integration（集成测试）**：中间层，数量适中。验证模块间交互，如 Fragment + ViewModel + Repository + 真实数据库。Android 中通常用 Robolectric（JVM 上运行）或 Instrumentation 测试实现。
- **Unit（单元测试）**：最底层，数量最多。验证单个类/方法的纯逻辑，不依赖 Android 框架。用 JUnit + Mockito 在 JVM 上毫秒级运行。

**黄金法则**：越底层越稳定、越快；越上层越真实、越慢。投入比例应遵循 **70% Unit + 20% Integration + 10% E2E**。

**反模式（冰淇淋甜筒）**：过度依赖 E2E 或手动测试，缺乏底层自动化测试，导致 CI 反馈慢、维护成本爆炸。

---

### Q5: Robolectric 的 Shadow 机制 — 如何在 JVM 上运行 Android 测试

Robolectric 的核心思想是**在 JVM 上模拟 Android SDK**。它通过 **Shadow 类** 拦截 Android 框架类的调用并返回模拟行为：

```kotlin
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [33])
class MyActivityTest {
    @Test
    fun `click button updates text`() {
        val activity = Robolectric.buildActivity(MyActivity::class.java)
            .create().start().resume().visible().get()
        
        activity.findViewById<Button>(R.id.btn).performClick()
        
        val textView = activity.findViewById<TextView>(R.id.tv)
        assertThat(textView.text.toString(), `is`("Clicked"))
    }
}
```

**Shadow 原理**：Robolectric 在类加载时通过自定义 `ClassLoader` 拦截目标类（如 `android.os.Looper`），将其替换为对应的 Shadow 实现（如 `ShadowLooper`）。Shadow 对象通过 `Shadow.extract()` 获取，可进行细粒度控制：

```kotlin
val shadowLooper = Shadow.extract(Looper.getMainLooper())
shadowLooper.idle()  // 手动推进主线程消息队列
shadowLooper.runOneTask()  // 执行一条消息
```

**与 Instrumentation 测试对比**：Robolectric 在 JVM 上运行，毫秒级启动，适合 CI；Instrumentation 需要设备/模拟器，秒级启动，但结果更真实。通常用 Robolectric 做 ViewModel/Intent/Resource 相关的单元测试，用 Instrumentation + Espresso 做 UI 交互测试。

---

## 第二层：Mockito 代理原理 — cglib vs ByteBuddy

### 为什么需要代理？

Mockito 创建 mock/spy 对象时，需要动态生成一个目标类的子类（或接口实现），以拦截所有方法调用并返回桩值。这依赖**字节码操作库**。

### Mockito 1.x：cglib

早期 Mockito 依赖 **cglib**（Code Generation Library），它基于 ASM 字节码框架，通过 `Enhancer` 在运行时生成目标类的子类。所有非 final 方法被重写，转发到 Mockito 的 `MockHandler`。**缺陷**：无法 mock final 类/方法（cglib 无法覆盖 final），且 `Objenesis` 绕过构造器可能引发问题。

### Mockito 2.x+：ByteBuddy（Inline）

**ByteBuddy** 是 Mockito 2.x 以来的默认代理引擎，其 `mock-maker-inline` 模式通过 **Java Instrumentation API**（`java.lang.instrument`）直接在字节码层面修改类定义，而非生成子类：

```java
// ByteBuddy 代理最终类的原理示意
new ByteBuddy()
    .subclass(Target.class)              // 正常情况下无法 subclass final
    .method(ElementMatchers.any())
    .intercept(MethodDelegation.to(handler))
    .make()
```

对于 final 类/方法，ByteBuddy 使用 `Instrumentation.retransformClasses()` 在类加载后重新转换字节码，移除 final 修饰符并插入拦截逻辑。需要指定 Mockito 扩展文件：`src/test/resources/mockito-extensions/org.mockito.plugins.MockMaker` 内容为 `mock-maker-inline`。

### Android 的挑战

Android 运行在 ART/Dalvik 虚拟机上，其字节码格式是 **Dex**（而非 JVM 的 Class 文件），且不支持 `java.lang.instrument` API。因此 Android 上的 Mockito 使用 **dexmaker** 作为底层代理引擎，在运行时生成 Dex 字节码并加载到当前 ClassLoader。

---

## 第三层：Espresso IdlingResource — 异步等待的优雅解法

### 问题场景

Espresso 默认在主线程空闲时执行 View 操作。但如果应用在执行网络请求、数据库操作、动画等异步任务时，测试可能在结果返回前就执行断言，导致 **flaky test**（不稳定测试）。

```kotlin
// ❌ 可能失败的测试：网络请求尚未完成
onView(withId(R.id.result)).check(matches(withText("loaded")))  // 还显示 "loading..."
```

### IdlingResource 原理

`IdlingResource` 是一个接口，Espresso 在每次操作前会检查所有注册的 `IdlingResource` 是否空闲（`isIdleNow() == true`），只有当所有资源空闲时才继续执行：

```kotlin
interface IdlingResource {
    val name: String
    fun isIdleNow(): Boolean
    fun registerIdleTransitionCallback(callback: IdlingResource.ResourceCallback)
}
```

**常见实现**：

1. **CountingIdlingResource**：手动 increment/decrement 计数器，计数器归零时空闲。适合自定义异步任务。

```kotlin
val idlingResource = CountingIdlingResource("network-call")
// 网络开始时 increment
idlingResource.increment()
// 网络完成时 decrement
idlingResource.decrement()
// 注册到 Espresso
IdlingRegistry.getInstance().register(idlingResource)
```

2. **OkHttp IdlingResource**（官方提供）：自动监听 OkHttp Dispatcher 的 running calls 数量。

3. **RxJava/RxAndroid IdlingResource**：包装 RxJava 的 Scheduler，追踪未完成的订阅。

4. **协程 IdlingResource**：通过 `Dispatchers.Main` 的 `CoroutineContext` 检查是否有活跃协程。

### 最佳实践

- 在 `@Before` 中注册，`@After` 中注销，避免泄漏影响其他测试。
- 避免在生产代码中引入 IdlingResource——使用 debug build variant 条件编译。
- 对 ViewModel + LiveData/StateFlow 的异步场景，优先用 `InstantTaskExecutorRule` 和 `TestDispatcher` 在单元层处理，而非在 UI 测试层依赖 IdlingResource。

---

## 第四层：测试金字塔层级图

```
                        ┌─────────────────────────────────────────┐
                        │                                         │
                        │            ☁️  E2E Tests  ☁️              │
                        │      (Espresso + UI Automator)          │
                        │     数量: ~5%  速度: 分钟级              │
                        │     验证: 完整用户流程                    │
                        │                                         │
                        │    ┌───────────────────────────────┐     │
                        │    │                               │     │
                        │    │    🔗 Integration Tests       │     │
                        │    │  (Robolectric / Instrumentation)│   │
                        │    │   数量: ~15%  速度: 秒级        │     │
                        │    │   验证: 模块间交互               │     │
                        │    │                               │     │
                        │    │  ┌─────────────────────────┐  │     │
                        │    │  │                         │  │     │
                        │    │  │   🧪 Unit Tests          │  │     │
                        │    │  │   (JUnit + Mockito)      │  │     │
                        │    │  │   数量: ~80%  速度: ms级  │  │     │
                        │    │  │   验证: 纯逻辑/单类行为    │  │     │
                        │    │  │                         │  │     │
                        │    │  └─────────────────────────┘  │     │
                        │    └───────────────────────────────┘     │
                        └─────────────────────────────────────────┘

         金字塔（正确）                         冰淇淋甜筒（错误）
     ╱                 ╲                    ┌─────────────────┐
    ╱   少量 E2E        ╲                   │   大量 E2E       │
   ╱                     ╲                  │   (缓慢、脆弱)    │
  ╱    适量集成测试       ╲                 ├─────────────────┤
 ╱                         ╲                │ 少量 Integration │
╱      大量单元测试          ╲               ├─────────────────┤
╲                            ╱              │ 极少 Unit        │
 ╲                          ╱               └─────────────────┘
  ╲                        ╱                  运维噩梦！
   ╲                      ╱
    ╲____________________╱

      测试金字塔的核心信条：
      "越快越稳定 → 越多写  |  越慢越脆弱 → 越少写"
```

### 各层级投入产出对比

| 层级 | 编写成本 | 运行时间 | 维护成本 | 置信度 | 定位能力 | 建议占比 |
|------|----------|----------|----------|--------|----------|----------|
| Unit | 低 | <100ms | 极低 | 低 | 精确 | 70-80% |
| Integration | 中 | 1-10s | 中 | 中 | 模块级 | 15-20% |
| E2E | 高 | 30s-5min | 高 | 高 | 模糊 | 5-10% |

---

## 第五层：ViewModel 单元测试 — 完整代码与架构拆解

### 被测对象：UserProfileViewModel

```kotlin
// UserProfileViewModel.kt
class UserProfileViewModel(
    private val userRepository: UserRepository
) : ViewModel() {

    private val _uiState = MutableStateFlow(UserProfileUiState())
    val uiState: StateFlow<UserProfileUiState> = _uiState.asStateFlow()

    fun loadUser(userId: String) {
        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, error = null) }
            try {
                val user = userRepository.getUser(userId)
                _uiState.update { it.copy(
                    isLoading = false,
                    user = user,
                    error = null
                )}
            } catch (e: Exception) {
                _uiState.update { it.copy(
                    isLoading = false,
                    error = e.message ?: "Unknown error"
                )}
            }
        }
    }

    fun refresh() {
        val currentUser = _uiState.value.user ?: return
        loadUser(currentUser.id)
    }
}

data class UserProfileUiState(
    val isLoading: Boolean = false,
    val user: User? = null,
    val error: String? = null
)

data class User(val id: String, val name: String, val email: String)

interface UserRepository {
    suspend fun getUser(userId: String): User
}
```

### 测试架构分析

ViewModel 单元测试的核心挑战：
1. **协程调度**：`viewModelScope.launch` 默认使用 `Dispatchers.Main`，单元测试环境无主线程。
2. **状态收集**：需要收集 `StateFlow` 的发射序列进行断言。
3. **依赖隔离**：`UserRepository` 是外部依赖，需要 mock。

对应解决策略：
- **MainDispatcherRule**：替换 `Dispatchers.Main` 为 `TestDispatcher`
- **turbine**（或手动 collect）：流式断言 StateFlow 发射
- **Mockito**：mock UserRepository，用 `coEvery` 处理 suspend 函数

---

## 第六层：ViewModel 完整单元测试实现

```kotlin
// MainDispatcherRule.kt — 将 Dispatchers.Main 替换为测试调度器
@OptIn(ExperimentalCoroutinesApi::class)
class MainDispatcherRule(
    val testDispatcher: TestDispatcher = UnconfinedTestDispatcher()
) : TestWatcher() {

    override fun starting(description: Description) {
        Dispatchers.setMain(testDispatcher)
    }

    override fun finished(description: Description) {
        Dispatchers.resetMain()
    }
}

// UserProfileViewModelTest.kt
@OptIn(ExperimentalCoroutinesApi::class)
class UserProfileViewModelTest {

    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    // Mock Repository
    private val userRepository: UserRepository = mock()

    // 被测对象
    private lateinit var viewModel: UserProfileViewModel

    // StateFlow 收集器
    private val results = mutableListOf<UserProfileUiState>()

    @Before
    fun setUp() {
        viewModel = UserProfileViewModel(userRepository)
        results.clear()
    }

    // ============================
    // 测试 1：首次加载，初始状态正确
    // ============================
    @Test
    fun `initial state shows no loading, no user, no error`() = runTest {
        // then
        assertThat(viewModel.uiState.value).isEqualTo(UserProfileUiState())
    }

    // ============================
    // 测试 2：成功加载用户数据
    // ============================
    @Test
    fun `loadUser success updates uiState with user`() = runTest {
        // given
        val expectedUser = User(id = "1", name = "Alice", email = "alice@example.com")
        coEvery { userRepository.getUser("1") } returns expectedUser

        // 收集 StateFlow 发射的历史
        val collector = viewModel.uiState.testIn(backgroundScope)

        // when
        viewModel.loadUser("1")

        // then — 断言完整的发射序列
        assertThat(collector.awaitItem()).isEqualTo(
            UserProfileUiState(isLoading = false)  // 初始值
        )
        assertThat(collector.awaitItem()).isEqualTo(
            UserProfileUiState(isLoading = true, error = null)  // loading 开始
        )
        assertThat(collector.awaitItem()).isEqualTo(
            UserProfileUiState(isLoading = false, user = expectedUser, error = null)  // 加载完成
        )

        collector.cancelAndIgnoreRemainingEvents()
    }

    // ============================
    // 测试 3：加载失败，错误信息更新
    // ============================
    @Test
    fun `loadUser failure sets error in uiState`() = runTest {
        // given
        coEvery { userRepository.getUser("99") } throws RuntimeException("Network error")

        val collector = viewModel.uiState.testIn(backgroundScope)

        // when
        viewModel.loadUser("99")

        // then
        assertThat(collector.awaitItem()).isEqualTo(UserProfileUiState())           // 初始
        assertThat(collector.awaitItem()).isEqualTo(
            UserProfileUiState(isLoading = true, error = null)                      // loading
        )
        assertThat(collector.awaitItem()).isEqualTo(
            UserProfileUiState(isLoading = false, user = null, error = "Network error") // error
        )

        collector.cancelAndIgnoreRemainingEvents()
    }

    // ============================
    // 测试 4：refresh 无当前用户时不应调用 repository
    // ============================
    @Test
    fun `refresh with no current user does nothing`() = runTest {
        // when
        viewModel.refresh()

        // then — repository 完全未被调用
        coVerify(exactly = 0) { userRepository.getUser(any()) }
    }

    // ============================
    // 测试 5：refresh 有当前用户时重新加载
    // ============================
    @Test
    fun `refresh after successful load calls repository again`() = runTest {
        // given — 先加载一个用户，建立状态
        val user1 = User("1", "Alice", "alice@example.com")
        coEvery { userRepository.getUser("1") } returns user1
        viewModel.loadUser("1")

        val user2 = User("1", "Alice Updated", "alice_new@example.com")
        coEvery { userRepository.getUser("1") } returns user2

        val collector = viewModel.uiState.testIn(backgroundScope)

        // when
        viewModel.refresh()

        // then — refresh 触发 loading → 新数据
        assertThat(collector.awaitItem()).isEqualTo(UserProfileUiState())                    // 0: 初始
        assertThat(collector.awaitItem()).isEqualTo(
            UserProfileUiState(isLoading = true, error = null)                               // 1: loading
        )
        assertThat(collector.awaitItem()).isEqualTo(
            UserProfileUiState(isLoading = false, user = user1, error = null)                // 2: 首次加载完成
        )
        assertThat(collector.awaitItem()).isEqualTo(
            UserProfileUiState(isLoading = true, user = user1, error = null)                 // 3: refresh 触发 loading
        )
        assertThat(collector.awaitItem()).isEqualTo(
            UserProfileUiState(isLoading = false, user = user2, error = null)                // 4: refresh 完成
        )

        collector.cancelAndIgnoreRemainingEvents()
    }

    // ============================
    // 测试 6：快速连续调用 loadUser，只取最后一次结果
    // ============================
    @Test
    fun `rapid successive loadUser calls cancel prior requests`() = runTest {
        // given — 使用 delay 模拟慢速请求
        coEvery { userRepository.getUser("1") } coAnswers {
            delay(100) // 模拟慢速网络
            User("1", "Alice", "alice@example.com")
        }
        coEvery { userRepository.getUser("2") } coAnswers {
            User("2", "Bob", "bob@example.com")
        }

        val collector = viewModel.uiState.testIn(backgroundScope)

        // when — 快速连续调用
        viewModel.loadUser("1")
        viewModel.loadUser("2") // 第二个调用应在第一个完成前发出

        // then — 第一个请求被取消，只有第二个成功
        // 注意：这里需要 advanceUntilIdle 或合适的 TestDispatcher
        // 用 UnconfinedTestDispatcher 时，行为取决于协程调度
        // 这里验证最终状态只包含第二个用户
        val finalState = collector.expectMostRecentItem()
        assertThat(finalState.user?.id).isEqualTo("2")
        assertThat(finalState.isLoading).isFalse()
        assertThat(finalState.error).isNull()

        collector.cancelAndIgnoreRemainingEvents()
    }
}
```

### 测试要点总结

| 测试用例 | 覆盖场景 | 关键断言 |
|---------|---------|---------|
| 初始状态 | 创建 ViewModel 后默认状态 | `isLoading=false, user=null, error=null` |
| 加载成功 | 正常数据流 | StateFlow 发射序列：初始 → loading → 有数据 |
| 加载失败 | 异常处理 | 发射序列：初始 → loading → error 非空 |
| 空 refresh | 边界条件 | `coVerify(exactly=0)` 验证无调用 |
| 正常 refresh | 重新加载 | 保留原有 user 且触发 loading → 新数据 |
| 竞态条件 | 快速连续请求 | 最终状态只反映最后一次成功请求 |

### 必备的测试依赖（build.gradle）

```kotlin
// 单元测试依赖
testImplementation("junit:junit:4.13.2")
testImplementation("org.mockito:mockito-core:5.8.0")
testImplementation("org.mockito.kotlin:mockito-kotlin:5.2.1")
testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.7.3")
testImplementation("app.cash.turbine:turbine:1.0.0")
testImplementation("com.google.truth:truth:1.1.5")
```

---

## 附录：测试常见反模式与改进

### 反模式 1：测试实现细节而非行为

```kotlin
// ❌ 测试内部方法调用
verify(viewModel).parseData(anyString())

// ✅ 测试可观测的行为
assertThat(viewModel.uiState.value.error).isNotNull()
```

### 反模式 2：过度使用 Instrumentation 测试

所有测试都在设备上跑 → CI 耗时 30 分钟+。改进：将纯逻辑移到 JVM 单元测试，设备上只跑关键的 UI 集成测试。

### 反模式 3：共享测试状态

多个测试方法共享 mutable 变量 → 测试顺序耦合。改进：每个 `@Test` 前通过 `@Before` 重新初始化，保持测试独立性。

### 反模式 4：忽略 flaky test

"这测试偶尔失败，重跑就好了" → 掩盖真实缺陷。改进：使用 IdlingResource 解决异步竞态，使用 `TestDispatcher` 控制协程调度，永远不忽略不稳定的测试。

---

> **一句话总结**：单元测试追求「快」和「稳定」，用 Mock 隔离外部世界；集成测试验证「连接」是否正确；E2E 确认「用户能做最关键的事」。三层分工明确，比例得当，才是健康的测试策略。
