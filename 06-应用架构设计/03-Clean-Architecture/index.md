# Clean Architecture 面试深度解析

> **六层递进体系**：面试问题 → 标准答案 → 核心原理 → 流程图 → 源码分析 → 应用场景
> 适用岗位：高级/资深 Android 工程师、架构师

---

## 目录

1. [常见面试问题（8 题）](#1-常见面试问题)
2. [标准答案与要点解析](#2-标准答案与要点解析)
3. [核心原理深度讲解](#3-核心原理深度讲解)
4. [原理流程图](#4-原理流程图)
5. [核心源码分析](#5-核心源码分析)
6. [应用场景举例](#6-应用场景举例)

---

## 1. 常见面试问题

### Q1: Clean Architecture 的四层分层结构（Entity / UseCase / InterfaceAdapter / Framework）分别是什么？各层职责和依赖规则是什么？
### Q2: UseCase 的设计原则有哪些？（单一职责、无状态、可组合）如何界定一个 UseCase 的粒度？
### Q3: 领域层（domain）与数据层（data）的边界如何划分？DTO（Data Transfer Object）与 Domain Model 的映射在什么时机执行？
### Q4: Clean Architecture + MVVM 在 Android 项目中如何融合实践？ViewModel 在这一架构中处于什么位置？
### Q5: 依赖反转原则（DIP）在 Android 中的具体实现方式？为何 Repository 接口要定义在 domain 层？
### Q6: Clean Architecture 的测试优势体现在哪些方面？如何针对各层编写单元测试？
### Q7: 多数据源场景下（本地 Room + 远程 Retrofit），Repository 如何统一数据获取策略？
### Q8: Clean Architecture 在实际项目中的常见反模式有哪些？（过度工程、贫血 UseCase、层间泄漏）

---

## 2. 标准答案与要点解析

### Q1: Clean Architecture 四层分层结构与依赖规则

**核心答案**：Clean Architecture 由 Robert C. Martin（Uncle Bob）于 2012 年提出，核心思想是**通过分层和依赖规则将业务逻辑与外部框架彻底解耦**，使系统核心不依赖于任何外部细节。Android 社区普遍采用四层变体：

```
┌──────────────────────────────────────────────────────────┐
│                    Framework Layer                        │
│  (Activity/Fragment, Room DAO, Retrofit, Hilt/Koin)      │
│                    ↑ 依赖方向                              │
│  ┌────────────────────────────────────────────────────┐  │
│  │              Interface Adapter Layer                │  │
│  │     (ViewModel, RepositoryImpl, DTO Mapper)         │  │
│  │                    ↑ 依赖方向                        │  │
│  │  ┌──────────────────────────────────────────────┐  │  │
│  │  │            UseCase / Application Layer        │  │  │
│  │  │       (GetUserUseCase, LoginUseCase...)       │  │  │
│  │  │                    ↑ 依赖方向                  │  │  │
│  │  │  ┌────────────────────────────────────────┐  │  │  │
│  │  │  │          Entity / Domain Layer          │  │  │  │
│  │  │  │   (User, Order, Repository Interface)   │  │  │  │
│  │  │  └────────────────────────────────────────┘  │  │  │
│  │  └──────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

#### 各层职责明细

| 层 | 原名 | 核心职责 | 包含内容 | 依赖方向 |
|----|------|---------|---------|---------|
| **领域层** | Entities / Domain | 封装企业级业务规则和实体 | Domain Model（Entity）、Repository 接口、UseCase | **不依赖任何外层** |
| **用例层** | Use Cases / Application | 编排业务逻辑，协调领域实体 | 具体 UseCase 类（每个一个公共方法） | 仅依赖领域层 |
| **接口适配层** | Interface Adapters | 数据格式转换，连接内外层 | ViewModel、RepositoryImpl、DTO → Domain Mapper | 依赖领域层和用例层 |
| **框架与驱动层** | Frameworks & Drivers | 外部工具和框架的具体实现 | Activity / Fragment、Room / Retrofit / Hilt | 依赖所有内层 |

#### 依赖规则（Dependency Rule）

> **源代码依赖方向只能从外向内。内层对"外层"一无所知。**

具体而言：
- domain 层**零 Android 依赖**——不导入 `android.*`，不依赖 Context
- 内层声明接口（如 `UserRepository`），外层提供实现（如 `UserRepositoryImpl`）
- 任何外层变更（如换 ORM 框架）不触及内层代码

---

### Q2: UseCase 的设计原则

**核心答案**：UseCase 是 Clean Architecture 中**承载单一业务动作的最小逻辑单元**，遵循三大设计原则：

#### 2.1 单一职责（Single Responsibility）

> 一个 UseCase 只做一件事，只有一个 `public` 方法。

```kotlin
// ✅ 正确：单一职责
class GetUserProfileUseCase(
    private val userRepository: UserRepository
) {
    suspend operator fun invoke(userId: String): Result<User> {
        return userRepository.getUserById(userId)
    }
}

// ❌ 错误：一个 UseCase 做了太多事
class UserUseCase(...) {
    fun getUser() { ... }
    fun updateUser() { ... }
    fun deleteUser() { ... }
    fun syncUsers() { ... }
}
```

#### 2.2 无状态（Stateless）

UseCase **不应持有可变状态**，每次调用独立执行，返回值只取决于输入参数和依赖注入的 Repository。这意味着：
- 不持有缓存（缓存属于 Repository 层的职责）
- 不持有上一次请求的结果
- 线程安全，可在多个协程中并发调用

```kotlin
// ✅ 无状态 UseCase
class CalculateDiscountUseCase {
    // 纯函数式：输出仅由输入决定
    operator fun invoke(price: Double, discountRate: Double): Double {
        return price * (1 - discountRate)
    }
}
```

#### 2.3 可组合（Composable）

多个 UseCase 可以**组合**成更复杂的业务流程：

```kotlin
class CheckoutUseCase(
    private val validateCartUseCase: ValidateCartUseCase,
    private val calculateTotalUseCase: CalculateTotalUseCase,
    private val createOrderUseCase: CreateOrderUseCase
) {
    suspend operator fun invoke(cart: Cart): Result<Order> {
        // 1. 校验购物车
        if (!validateCartUseCase(cart)) return Result.failure(CartInvalidException())
        // 2. 计算总价
        val total = calculateTotalUseCase(cart)
        // 3. 创建订单
        return createOrderUseCase(cart, total)
    }
}
```

#### UseCase 粒度判断标准

| 场景 | 是否独立 UseCase | 理由 |
|------|:---:|------|
| 获取用户列表 | ✅ 是 | 独立的业务动作 |
| 格式化用户名为全大写 | ❌ 否 | 纯 UI 逻辑，放在 ViewModel 或 Mapper |
| 用户登录（含校验+网络请求+缓存Token） | ✅ 是 | 完整业务流程 |
| 根据语言环境拼接问候语 | ❌ 否 | UI 展示逻辑 |

**面试金句**：*"UseCase 是业务逻辑的编排者，不是数据转换的工具。如果 UseCase 里只有一行 `repository.xxx()`，那这个 UseCase 就是贫血的——应该思考是否有必要单独抽取。"*

---

### Q3: Domain 层与 Data 层的边界划分与 DTO 映射

**核心答案**：Domain 层和 Data 层之间的边界是 Clean Architecture 最重要的分界线。

#### 边界定义

```
┌──────────────────────────────────────────┐
│  domain 层（纯 Kotlin/Java，零依赖）       │
│  ├── model/User.kt           领域模型     │
│  ├── repository/UserRepository.kt  接口   │
│  └── usecase/GetUserUseCase.kt 用例       │
└─────────── 边界（接口）──────────────────────┘
│           ↑ 依赖反转：data 实现 domain 接口
┌──────────────────────────────────────────┐
│  data 层（依赖 Android / 第三方库）         │
│  ├── remote/dto/UserDto.kt    网络传输对象 │
│  ├── local/entity/UserEntity.kt Room实体  │
│  ├── mapper/UserMapper.kt     映射器       │
│  └── repository/UserRepositoryImpl.kt 实现│
└──────────────────────────────────────────┘
```

#### DTO → Domain → UI Model 三级映射

```
API Response (JSON)
       │
       ▼
  RemoteDTO (data/remote/dto)     ← 网络层实体，带 @SerializedName
       │  Mapper
       ▼
  Domain Model (domain/model)     ← 业务实体，纯 Kotlin data class
       │  Mapper (在 ViewModel 或 Adapter 层)
       ▼
  UI Model (presentation/model)   ← 界面展示实体，只含 UI 需要的字段
```

```kotlin
// ===== data 层：API 返回的 DTO =====
@Serializable
data class UserDto(
    @SerialName("user_id") val userId: Long,
    @SerialName("full_name") val fullName: String,
    @SerialName("avatar_url") val avatarUrl: String,
    @SerialName("created_at") val createdAt: String  // ISO 8601 字符串
)

// ===== domain 层：领域模型 =====
data class User(
    val id: Long,
    val name: String,
    val avatar: String,
    val registrationDate: LocalDate  // 已解析的类型安全日期
)

// ===== data 层：Mapper（扩展函数方式）=====
fun UserDto.toDomain(): User = User(
    id = userId,
    name = fullName,
    avatar = avatarUrl,
    registrationDate = LocalDate.parse(createdAt.substring(0, 10))
)

// ===== presentation 层：UI 模型 =====
data class UserUiModel(
    val id: Long,
    val displayName: String,        // 格式化后的名称
    val avatarUrl: String,
    val memberSince: String         // 格式化为 "2023年5月加入"
)

fun User.toUiModel(): UserUiModel = UserUiModel(
    id = id,
    displayName = name,
    avatarUrl = avatar,
    memberSince = "${registrationDate.year}年${registrationDate.monthValue}月加入"
)
```

**面试关键点**：
- DTO 永远不泄漏到 domain 层——Repository 的返回类型是 `User`（Domain Model），不是 `UserDto`
- domain 层不应知道 `@SerializedName`、`@Entity` 等注解
- 如果数据源切换（如 Retrofit → Ktor），只需修改 data 层的 DTO 和 Mapper，domain 层完全不受影响

---

### Q4: Clean Architecture + MVVM 的融合实践

**核心答案**：Clean Architecture 和 MVVM 在 Android 项目中是**互补关系**而非替代关系。Clean Architecture 解决的是"业务逻辑如何分层"（纵向），MVVM 解决的是"UI 层如何组织"（横向）。

#### 融合架构图

```
┌─────────────────────────────────────────────────────────────┐
│  Presentation Layer (MVVM)                                   │
│  ┌──────────┐     ┌──────────────┐     ┌─────────────────┐  │
│  │  View     │ ←── │  ViewModel   │ ──→ │  UiState        │  │
│  │(Activity/ │     │(持有 UiState) │     │  (data class)   │  │
│  │ Fragment/ │     └──────┬───────┘     └─────────────────┘  │
│  │ Compose)  │            │                                   │
│  └──────────┘            │ 调用                             │
├──────────────────────────┼──────────────────────────────────┤
│  Domain Layer             ▼                                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  UseCases (GetUserUseCase, LoginUseCase...)          │   │
│  │  Domain Models (User, Order...)                      │   │
│  │  Repository Interfaces                               │   │
│  └──────────────────────────┬───────────────────────────┘   │
├─────────────────────────────┼───────────────────────────────┤
│  Data Layer                 ▼                                │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  RepositoryImpl → RemoteDataSource / LocalDataSource │   │
│  │  DTOs, Mappers, Room DAO, Retrofit API               │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

#### ViewModel 在 Clean Architecture 中的定位

ViewModel **属于 Interface Adapter 层**（或 Presentation 层），职责是：
1. 调用 UseCase 执行业务逻辑
2. 将 Domain Model 映射为 UiState / UiModel
3. 管理 UI 相关的状态（加载中、错误、成功）
4. **不做业务判断**——业务逻辑全部在 UseCase 中

```kotlin
@HiltViewModel
class UserProfileViewModel @Inject constructor(
    private val getUserUseCase: GetUserUseCase,
    private val updateProfileUseCase: UpdateProfileUseCase
) : ViewModel() {

    private val _uiState = MutableStateFlow<UserProfileUiState>(UserProfileUiState.Loading)
    val uiState: StateFlow<UserProfileUiState> = _uiState.asStateFlow()

    fun loadProfile(userId: String) {
        viewModelScope.launch {
            _uiState.value = UserProfileUiState.Loading
            getUserUseCase(userId)
                .map { user -> user.toUiModel() }  // Domain → UI 映射
                .onSuccess { _uiState.value = UserProfileUiState.Success(it) }
                .onFailure { _uiState.value = UserProfileUiState.Error(it.message) }
        }
    }
}
```

**面试金句**：*"MVVM 解决 UI 层问题，Clean Architecture 解决整体分层问题。二者融合时，ViewModel 是 UseCase 的消费者，不做业务判断——业务逻辑在 UseCase 中，ViewModel 只做状态映射。"*

---

### Q5: 依赖反转原则（DIP）在 Android 中的实现

**核心答案**：依赖反转原则（Dependency Inversion Principle）是 Clean Architecture 的**基石**。其核心表述为：

> 高层模块不应依赖低层模块，二者都应依赖抽象。抽象不应依赖细节，细节应依赖抽象。

#### 在 Android 中的具体体现

```
 高层模块（Domain Layer）
    │
    │  定义接口（抽象）
    ▼
  interface UserRepository {           ← 抽象在 domain 层
      suspend fun getUser(id: String): User
  }
    ▲
    │  实现接口（细节依赖抽象）
    │
 低层模块（Data Layer）
  class UserRepositoryImpl(            ← 实现在 data 层
      private val api: UserApi,
      private val dao: UserDao
  ) : UserRepository {
      override suspend fun getUser(id: String): User {
          // 具体实现：先查缓存，再调网络
      }
  }
```

#### 为什么 Repository 接口必须定义在 domain 层？

| 如果定义在 data 层（❌ 错误） | 如果定义在 domain 层（✅ 正确） |
|---|---|
| domain 层需要依赖 data 层才能使用 `UserRepository` | domain 层完全自包含，data 层反向依赖 domain 层 |
| 违反依赖规则——内层依赖了外层 | 依赖方向正确——外层依赖内层 |
| 更换网络层框架需要改 domain 层代码 | 更换 Retrofit → Ktor，domain 层零改动 |
| UseCase 无法独立进行单元测试 | UseCase 可以轻松 Mock Repository 接口 |

#### Hilt 中的依赖注入实现

```kotlin
// ===== domain 层：定义接口 =====
interface AuthRepository {
    suspend fun login(username: String, password: String): Result<User>
    suspend fun getCachedUser(): User?
}

// ===== data 层：实现接口 =====
class AuthRepositoryImpl @Inject constructor(
    private val authApi: AuthApi,
    private val userDao: UserDao,
    private val tokenManager: TokenManager
) : AuthRepository {
    override suspend fun login(username: String, password: String): Result<User> {
        val response = authApi.login(LoginRequest(username, password))
        return if (response.isSuccessful) {
            tokenManager.saveToken(response.body()!!.token)
            val user = response.body()!!.user.toDomain()
            userDao.insertUser(user.toEntity())
            Result.success(user)
        } else {
            Result.failure(AuthException(response.errorBody()?.string()))
        }
    }
    // ...
}

// ===== DI 模块：绑定接口与实现（Hilt）=====
@Module
@InstallIn(SingletonComponent::class)
abstract class RepositoryModule {
    @Binds
    abstract fun bindAuthRepository(impl: AuthRepositoryImpl): AuthRepository
}
```

**面试金句**：*"依赖反转的本质是'谁拥有接口，谁就掌握了话语权'。Domain 层拥有 Repository 接口，就能强制 data 层按自己的契约来实现——这就是控制反转（IoC）在架构层面的体现。"*

---

### Q6: Clean Architecture 的测试优势

**核心答案**：Clean Architecture 的**分层解耦**天然带来了卓越的可测试性，每一层都可以独立进行单元测试。

#### 分层测试策略

| 测试层级 | 测试目标 | 依赖处理 | 特点 |
|---------|---------|---------|------|
| **Domain 层** | UseCase 逻辑、Domain Model 行为 | Mock Repository 接口 | 最快，纯 Kotlin 单元测试 |
| **Data 层** | RepositoryImpl、Mapper 逻辑 | Mock API / DAO | 验证数据转换正确性 |
| **Presentation 层** | ViewModel 状态转换 | Mock UseCase | 验证 UI 状态机 |
| **集成测试** | 完整数据流 | Fake / In-Memory 实现 | 端到端验证 |

#### Domain 层单元测试示例

```kotlin
class GetUserUseCaseTest {

    private lateinit var repository: UserRepository
    private lateinit var useCase: GetUserUseCase

    @Before
    fun setUp() {
        repository = mock()  // Mock 接口，无需任何 Android 依赖
        useCase = GetUserUseCase(repository)
    }

    @Test
    fun `invoke should return user when repository succeeds`() = runTest {
        val expectedUser = User(id = 1, name = "Test", avatar = "url", registrationDate = LocalDate.now())
        whenever(repository.getUserById("1")).thenReturn(Result.success(expectedUser))

        val result = useCase("1")

        assertTrue(result.isSuccess)
        assertEquals(expectedUser, result.getOrNull())
    }

    @Test
    fun `invoke should return failure when repository throws`() = runTest {
        whenever(repository.getUserById("1")).thenReturn(Result.failure(RuntimeException("Network error")))

        val result = useCase("1")

        assertTrue(result.isFailure)
        assertEquals("Network error", result.exceptionOrNull()?.message)
    }
}
```

#### ViewModel 测试示例

```kotlin
class UserProfileViewModelTest {

    @Test
    fun `loadProfile should emit Success state when use case succeeds`() = runTest {
        val mockUseCase: GetUserUseCase = mock()
        val user = User(1, "Name", "avatar", LocalDate.now())
        whenever(mockUseCase.invoke("1")).thenReturn(Result.success(user))

        val viewModel = UserProfileViewModel(mockUseCase)
        val states = viewModel.uiState.drop(1).take(2).toList()

        viewModel.loadProfile("1")

        assertEquals(UserProfileUiState.Loading, states[0])
        assertTrue(states[1] is UserProfileUiState.Success)
    }
}
```

**面试金句**：*"Clean Architecture 让单元测试从'奢侈品'变成'日用品'——Domain 层不需要 Robolectric，不需要 Android 设备，纯 JVM 测试毫秒级执行。完整的测试金字塔中，Domain 层单元测试占比应超过 60%。"*

---

### Q7: 多数据源 Repository 的统一实现

见 [第 6 节应用场景](#6-应用场景举例)。

---

### Q8: 常见反模式

| 反模式 | 表现 | 危害 | 正确做法 |
|--------|------|------|---------|
| **贫血 UseCase** | UseCase 只包含一行 `repository.xxx()` | 增加代码复杂度却无实际价值 | 如果无需编排逻辑，ViewModel 可直接调用 Repository |
| **DTO 泄漏** | Domain Model 字段名与 API 字段名一致（如 `user_id`） | 失去数据隔离，API 变更影响业务层 | 始终通过 Mapper 转换 |
| **Domain 层有 Android 依赖** | `import android.content.Context` 出现在 domain 模块 | 违反依赖规则，无法在 JVM 上测试 | 使用接口抽象，如 `DateTimeProvider` 替代 `Calendar` |
| **过度工程** | 一个简单列表页创建了 5 层 UseCase 链 | 维护成本远超收益 | 根据业务复杂度按需使用，简单 CRUD 不需要 UseCase |
| **跨层调用** | Fragment 直接调用 Repository | 层间边界模糊，测试困难 | 严格遵守 ViewModel → UseCase → Repository |

---

## 3. 核心原理深度讲解

### 3.1 依赖规则（Dependency Rule）的本质

Clean Architecture 的依赖规则是**源代码编译时依赖**的约束：

```
外层代码可以 import 内层代码
内层代码绝不 import 外层代码
```

**为什么这个规则如此重要？**

1. **独立可测试性**：domain 层作为纯 Kotlin/Java 模块，可在 JVM 上直接运行测试，无需模拟器
2. **框架无关性**：核心业务逻辑不绑定任何框架（Android、Retrofit、Room），未来迁移成本极低
3. **变更隔离**：UI 框架、数据库、网络库的变化不会传播到业务逻辑层
4. **团队并行开发**：domain 层定义好接口后，UI 层和数据层可并行开发

#### 依赖反转的实现机制

```
传统依赖（❌）:       依赖反转（✅）:
                     
Domain                Domain
  │                     │ (定义接口)
  ▼                     ▼
Data                interface Repository  ← 接口在 Domain
                     ▲
                       │ (实现接口)
                     Data
```

**控制流与依赖流的关系**：

- **运行时控制流**：View → ViewModel → UseCase → Repository（从外向内）
- **编译时依赖流**：Data → Domain（从外向内），Data 依赖 Domain 接口

这就是"反转"的含义——运行时调用方向与编译时依赖方向在边界处发生了反转。

### 3.2 UseCase 封装业务逻辑的深层原理

UseCase 不是简单的"方法提取"，而是**业务意图的语义封装**。

#### UseCase 的三种标准形态

```kotlin
// 形态1：无参数，返回结果
class GetCurrentUserUseCase @Inject constructor(
    private val authRepository: AuthRepository
) {
    suspend operator fun invoke(): User? = authRepository.getCachedUser()
}

// 形态2：有参数，返回结果
class SearchProductsUseCase @Inject constructor(
    private val productRepository: ProductRepository
) {
    suspend operator fun invoke(query: String, page: Int): Result<List<Product>> {
        require(query.isNotBlank()) { "Search query must not be blank" }
        require(page > 0) { "Page must be positive" }
        return productRepository.search(query, page)
    }
}

// 形态3：参数封装为 Request 对象（推荐用于复杂参数）
data class LoginRequest(val username: String, val password: String)

class LoginUseCase @Inject constructor(
    private val authRepository: AuthRepository,
    private val validateCredentialsUseCase: ValidateCredentialsUseCase
) {
    suspend operator fun invoke(request: LoginRequest): Result<User> {
        // 前置校验
        validateCredentialsUseCase(request)
        // 执行登录
        return authRepository.login(request.username, request.password)
    }
}
```

#### `operator fun invoke()` 的妙用

使用 Kotlin 的 `invoke` 操作符使得 UseCase 可以像函数一样调用：

```kotlin
// 注入
@Inject lateinit var getUserUseCase: GetUserUseCase

// 调用——就像调用一个函数
val user = getUserUseCase("user_id_123")

// 等价于
val user = getUserUseCase.invoke("user_id_123")
```

这种设计让 UseCase 的调用方式与普通函数一致，降低了认知负担，同时保留了类的可注入性。

### 3.3 Repository 接口定义在 Domain 层——IoC 的架构体现

这是 Clean Architecture 中**最核心的设计决策**，体现了控制反转（Inversion of Control）原则。

```
┌───────────────────┐
│   Domain Layer     │  ← 定义契约（我想要什么数据）
│   UserRepository   │  ← 接口：声明我需要的方法签名
│   (interface)      │
└────────┬──────────┘
         │ 实现
┌────────▼──────────┐
│   Data Layer       │  ← 提供实现（我怎么拿到数据）
│   UserRepoImpl     │  ← 实现类：具体的数据获取逻辑
│   (class)          │
└───────────────────┘
```

**这种设计将"数据从哪里来"变成了可替换的细节**：

- 开发阶段：使用 FakeRepository 返回模拟数据，UI 和 UseCase 开发不受阻塞
- 测试阶段：使用 Mock 或 InMemoryRepository，秒级执行
- 生产阶段：使用真实的 RepositoryImpl，连接 Retrofit + Room

### 3.4 数据映射的三层模型原理

```
RemoteDTO ──(data层Mapper)──→ DomainModel ──(presentation层Mapper)──→ UiModel
   │                              │                                    │
   │ 与API结构强耦合               │ 纯业务语义                          │ 与UI展示耦合
   │ @SerialName("user_id")       │ val id: Long                       │ "欢迎, 张三"
   │ 不可变，但可增删               │ 不可变，稳定                        │ 可变，可增删
```

**为什么不能跳过 Domain Model？**

1. **API 字段变更频繁**：后端可能改字段名（`user_id` → `uid`），如果直接对接到 UI，所有 UI 代码都需要改
2. **多数据源聚合**：Domain Model 可能是多个 DTO 的组合（用户信息 + 订单信息 → `UserProfile`）
3. **业务语义**：`LocalDate`（Domain）比 `String`（DTO）更能表达"日期"的业务含义
4. **UI 展示灵活**：UiModel 可以添加 `displayName`、`formattedDate` 等纯展示字段，不影响业务层

---

## 4. 原理流程图

### 4.1 Clean Architecture 分层环图

```
                    ┌──────────────────────────────┐
                    │       Frameworks & Drivers    │
                    │  ┌────────────────────────┐   │
                    │  │   Interface Adapters    │   │
                    │  │  ┌──────────────────┐   │   │
                    │  │  │   Application     │   │   │
                    │  │  │   (UseCases)      │   │   │
                    │  │  │  ┌────────────┐   │   │   │
                    │  │  │  │  Domain    │   │   │   │
                    │  │  │  │  Entities  │   │   │   │
                    │  │  │  └────────────┘   │   │   │
                    │  │  └──────────────────┘   │   │
                    │  └────────────────────────┘   │
                    └──────────────────────────────┘

    依赖方向：外层 ──→ 内层（箭头指向被依赖方）
    运行方向：外层 ←── 内层（控制流由外向内调用）
```

### 4.2 数据流：从 API 到 UI 的完整链路

```
                          ┌──────────────┐
                          │  REST API    │
                          │  (Server)    │
                          └──────┬───────┘
                                 │ HTTP Response (JSON)
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│  Data Layer                                                        │
│                                                                     │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────┐   │
│  │  Retrofit    │ ──→ │  UserDto     │ ──→ │  UserMapper      │   │
│  │  UserApi     │     │  (remote/dto)│     │  .toDomain()     │   │
│  └──────────────┘     └──────────────┘     └────────┬─────────┘   │
│                                                      │              │
│  ┌──────────────┐     ┌──────────────┐              │              │
│  │  Room DB     │ ──→ │  UserEntity  │ ──→ UserMapper.toDomain()  │
│  │  UserDao     │     │  (local/ent) │                             │
│  └──────────────┘     └──────────────┘                             │
│                                                      │              │
│  ┌───────────────────────────────────────────────────┘              │
│  │                                                                  │
│  │  UserRepositoryImpl                                              │
│  │  ┌──────────────────────────────────────────────────────┐       │
│  │  │  suspend fun getUser(id: String): Result<User> {     │       │
│  │  │    // 1. 先尝试本地                                    │       │
│  │  │    val cached = userDao.get(id)?.toDomain()           │       │
│  │  │    // 2. 网络获取                                      │       │
│  │  │    val remote = userApi.fetch(id).toDomain()          │       │
│  │  │    // 3. 缓存                                         │       │
│  │  │    userDao.insert(remote.toEntity())                  │       │
│  │  │    return Result.success(remote)                      │       │
│  │  │  }                                                    │       │
│  │  └──────────────────────────────────────────────────────┘       │
│  └────────────────────────┬─────────────────────────────────────── │
└───────────────────────────┼───────────────────────────────────────┘
                            │ Result<User> (Domain Model)
                            ▼
┌────────────────────────────────────────────────────────────────────┐
│  Domain Layer                                                       │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────┐      │
│  │  GetUserUseCase                                           │      │
│  │  suspend operator fun invoke(id: String): Result<User>    │      │
│  │      = userRepository.getUser(id)                         │      │
│  └──────────────────────────┬───────────────────────────────┘      │
└─────────────────────────────┼─────────────────────────────────────┘
                              │ Result<User>
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  Presentation Layer (Interface Adapter)                             │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────┐      │
│  │  UserViewModel                                            │      │
│  │  fun loadUser(id: String) {                               │      │
│  │    getUserUseCase(id)                                     │      │
│  │      .map { it.toUiModel() }  // Domain → UI Model        │      │
│  │      .onSuccess { _state.value = Success(it) }            │      │
│  │      .onFailure { _state.value = Error(it) }              │      │
│  │  }                                                        │      │
│  └──────────────────────────┬───────────────────────────────┘      │
│                             │ StateFlow<UserProfileUiState>         │
│                             ▼                                       │
│  ┌──────────────────────────────────────────────────────────┐      │
│  │  UserProfileFragment / @Composable                        │      │
│  │  collectAsState() → 渲染 UI                               │      │
│  └──────────────────────────────────────────────────────────┘      │
└────────────────────────────────────────────────────────────────────┘
```

### 4.3 依赖注入装配流程图

```
@HiltAndroidApp
Application
    │
    ├── @Module @InstallIn(SingletonComponent::class)
    │   ├── @Provides Retrofit (okhttp, gson, baseUrl)
    │   ├── @Provides RoomDatabase
    │   ├── @Binds UserApi → Retrofit 生成的实现
    │   └── @Binds UserDao → Room 生成的实现
    │
    ├── @Module @InstallIn(SingletonComponent::class)
    │   └── @Binds UserRepository → UserRepositoryImpl
    │
    └── @HiltViewModel UserViewModel
        └── @Inject constructor(GetUserUseCase)  ← Hilt 自动装配
```

---

## 5. 核心源码分析

### 5.1 UseCase 的 `invoke` 操作符设计

`operator fun invoke()` 是 Kotlin 为 Clean Architecture UseCase 量身定做的语言特性。

#### 源码解剖

```kotlin
// ===== 基础抽象（可选，推荐） =====
abstract class BaseUseCase<in Params, out Result> {
    abstract suspend fun execute(params: Params): Result

    suspend operator fun invoke(params: Params): Result = execute(params)
}

// 无参数变体
abstract class BaseNoParamUseCase<out Result> {
    abstract suspend fun execute(): Result

    suspend operator fun invoke(): Result = execute()
}

// ===== 具体 UseCase =====
class GetOrderDetailUseCase @Inject constructor(
    private val orderRepository: OrderRepository,
    private val dispatchers: AppDispatchers  // 可注入的调度器
) : BaseUseCase<GetOrderDetailUseCase.Params, Result<Order>>() {

    data class Params(val orderId: String, val includeHistory: Boolean = false)

    override suspend fun execute(params: Params): Result<Order> {
        // 参数校验（业务逻辑的一部分）
        require(params.orderId.isNotBlank()) { "Order ID must not be blank" }

        return try {
            val order = orderRepository.getOrderById(params.orderId)
            if (params.includeHistory) {
                // 可以在这里组合多个 Repository 调用
                order.copy(history = orderRepository.getOrderHistory(params.orderId))
            }
            Result.success(order)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}

// ===== ViewModel 中的调用 =====
@HiltViewModel
class OrderDetailViewModel @Inject constructor(
    private val getOrderDetailUseCase: GetOrderDetailUseCase
) : ViewModel() {

    fun loadOrder(orderId: String) {
        viewModelScope.launch {
            _uiState.value = OrderDetailUiState.Loading
            // UseCase 像普通函数一样被调用
            getOrderDetailUseCase(GetOrderDetailUseCase.Params(orderId, includeHistory = true))
                .onSuccess { order -> _uiState.value = OrderDetailUiState.Success(order.toUiModel()) }
                .onFailure { e -> _uiState.value = OrderDetailUiState.Error(e.message) }
        }
    }
}
```

**设计要点解析**：

1. **`Params` 封装**：使用内部 `data class` 封装参数，避免参数列表过长，同时保持类型安全
2. **`require()` 前置校验**：参数校验是业务规则的一部分，放在 UseCase 而非 ViewModel
3. **`invoke` 作为语法糖**：让调用者感受到 UseCase 即函数的语义
4. **可注入的调度器**：`AppDispatchers` 允许在测试中替换为 `TestDispatcher`

### 5.2 Repository 的依赖反转源码分析

这是 Clean Architecture 在 Android 中**最值得深入理解的代码模式**。

#### 完整源码示例

```kotlin
// ==========================================
// 文件位置：domain/src/main/java/.../repository/ProductRepository.kt
// 依赖：仅有 kotlin-stdlib, kotlinx-coroutines-core
// ==========================================
package com.example.domain.repository

import com.example.domain.model.Product

interface ProductRepository {
    suspend fun getProducts(category: String): Result<List<Product>>
    suspend fun getProductById(id: String): Result<Product>
    suspend fun searchProducts(query: String): Result<List<Product>>
}

// ==========================================
// 文件位置：data/src/main/java/.../repository/ProductRepositoryImpl.kt
// 依赖：domain 模块、Retrofit、Room、kotlinx-serialization
// ==========================================
package com.example.data.repository

import com.example.data.local.dao.ProductDao
import com.example.data.mapper.toDomain
import com.example.data.mapper.toEntity
import com.example.data.remote.api.ProductApi
import com.example.domain.model.Product
import com.example.domain.repository.ProductRepository
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class ProductRepositoryImpl @Inject constructor(
    private val productApi: ProductApi,
    private val productDao: ProductDao
) : ProductRepository {

    override suspend fun getProducts(category: String): Result<List<Product>> {
        return try {
            // 策略1：从 API 获取
            val dtos = productApi.fetchProducts(category)
            val products = dtos.map { it.toDomain() }

            // 策略2：缓存到本地
            productDao.insertAll(products.map { it.toEntity() })

            Result.success(products)
        } catch (e: Exception) {
            // 策略3：网络失败时使用缓存兜底
            val cached = productDao.getByCategory(category).map { it.toDomain() }
            if (cached.isNotEmpty()) {
                Result.success(cached)
            } else {
                Result.failure(e)
            }
        }
    }

    override suspend fun getProductById(id: String): Result<Product> {
        // 先查本地，再调网络（Cache-First 策略）
        val cached = productDao.getById(id)?.toDomain()
        if (cached != null) return Result.success(cached)

        return try {
            val dto = productApi.fetchProduct(id)
            val product = dto.toDomain()
            productDao.insert(product.toEntity())
            Result.success(product)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override suspend fun searchProducts(query: String): Result<List<Product>> {
        return try {
            val dtos = productApi.searchProducts(query)
            Result.success(dtos.map { it.toDomain() })
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}

// ==========================================
// Hilt 绑定模块
// ==========================================
@Module
@InstallIn(SingletonComponent::class)
abstract class RepositoryModule {
    @Binds
    @Singleton
    abstract fun bindProductRepository(
        impl: ProductRepositoryImpl
    ): ProductRepository
}
```

**关键设计分析**：

1. **接口归属**：`ProductRepository` 是 `domain` 模块的公共 API，data 模块通过 `implementation project(':domain')` 依赖它
2. **返回类型**：永远返回 Domain Model（`Product`），绝不返回 DTO——这是边界的硬件约束
3. **数据源策略封装**：本地缓存、网络降级等策略全部封装在 `Impl` 内部，对外表现为统一的接口
4. **Hilt @Binds**：将接口与实现绑定，消费方（UseCase）只需声明接口依赖，无需知道具体实现

### 5.3 Mapper 扩展函数的设计模式

```kotlin
// ===== data/src/main/java/.../mapper/ProductMapper.kt =====
package com.example.data.mapper

import com.example.data.local.entity.ProductEntity
import com.example.data.remote.dto.ProductDto
import com.example.domain.model.Product

// DTO → Domain
fun ProductDto.toDomain(): Product = Product(
    id = productId,
    name = productName,
    price = Price(amount = priceInCents / 100.0, currency = currencyCode),
    category = Category.fromString(category),
    imageUrl = images.firstOrNull() ?: "",
    isAvailable = stock > 0
)

// Entity → Domain
fun ProductEntity.toDomain(): Product = Product(
    id = id,
    name = name,
    price = Price(amount = priceAmount, currency = priceCurrency),
    category = Category.fromString(category),
    imageUrl = imageUrl,
    isAvailable = isAvailable
)

// Domain → Entity
fun Product.toEntity(): ProductEntity = ProductEntity(
    id = id,
    name = name,
    priceAmount = price.amount,
    priceCurrency = price.currency,
    category = category.name,
    imageUrl = imageUrl,
    isAvailable = isAvailable,
    lastUpdated = System.currentTimeMillis()
)
```

**设计要点**：
- 使用 Kotlin 扩展函数而非独立的 Mapper 类，减少样板代码
- 每个映射方向单一职责：`toDomain()` / `toEntity()` / `toDto()` 语义清晰
- 类型安全：`Price(amount, currency)` 替代原始 `Double + String` 组合
- 业务规则封装在映射过程中（如 `priceInCents / 100.0`、`images.firstOrNull()`）

---

## 6. 应用场景举例

### 6.1 场景：多数据源（本地 + 远程）统一的 Repository 实现

这是 Android 开发中**最高频的 Clean Architecture 实践场景**。以新闻客户端为例：

#### 需求描述

- 用户打开 App 时，立即展示缓存的新闻列表（离线可读）
- 同时在后台拉取最新新闻
- 网络请求成功后，更新缓存并刷新 UI
- 网络失败时，如有缓存则展示缓存 + 提示"无法刷新"

#### 架构设计

```
                    ┌────────────────────┐
                    │   NewsViewModel     │
                    │   (Presentation)    │
                    └──────────┬─────────┘
                               │ 调用
                    ┌──────────▼─────────┐
                    │  GetNewsUseCase     │
                    │  (Domain)           │
                    └──────────┬─────────┘
                               │ 调用接口
                    ┌──────────▼─────────┐
                    │  NewsRepository     │  ← domain 层接口
                    │  (interface)        │
                    └──────────┬─────────┘
                               │ 实现
               ┌───────────────┼───────────────┐
               ▼                               ▼
     ┌─────────────────┐             ┌─────────────────┐
     │ NewsRemoteSource│             │ NewsLocalSource  │
     │ (Retrofit API)  │             │ (Room Database)  │
     └─────────────────┘             └─────────────────┘
```

#### 完整实现代码

```kotlin
// ==================== Domain Layer ====================
// domain/src/main/java/.../repository/NewsRepository.kt
interface NewsRepository {
    fun getNewsFeed(category: String): Flow<Result<List<Article>>>
}

// domain/src/main/java/.../usecase/GetNewsUseCase.kt
class GetNewsUseCase @Inject constructor(
    private val newsRepository: NewsRepository
) {
    operator fun invoke(category: String): Flow<Result<List<Article>>> {
        return newsRepository.getNewsFeed(category)
    }
}

// ==================== Data Layer ====================
// data/src/main/java/.../repository/NewsRepositoryImpl.kt
@Singleton
class NewsRepositoryImpl @Inject constructor(
    private val remoteSource: NewsRemoteSource,
    private val localSource: NewsLocalSource
) : NewsRepository {

    override fun getNewsFeed(category: String): Flow<Result<List<Article>>> = flow {
        // ======= 阶段1：立即发射本地缓存 =======
        val cachedArticles = localSource.getArticles(category).map { it.toDomain() }
        if (cachedArticles.isNotEmpty()) {
            emit(Result.success(cachedArticles))
        }

        // ======= 阶段2：尝试网络刷新 =======
        try {
            val remoteArticles = remoteSource.fetchNews(category).map { it.toDomain() }

            // 写缓存（使用 Room 的冲突替换策略）
            localSource.replaceArticles(category, remoteArticles.map { it.toEntity() })

            // 发射最新数据
            emit(Result.success(remoteArticles))
        } catch (e: Exception) {
            // 如果没有任何缓存，才抛出错误
            if (cachedArticles.isEmpty()) {
                emit(Result.failure(e))
            }
            // 如果有缓存，静默处理网络错误（UI 可选择性展示 Snackbar）
        }
    }.flowOn(Dispatchers.IO)  // 在 IO 线程执行
}

// ==================== Framework Layer ====================
// data/src/main/java/.../remote/NewsRemoteSource.kt
class NewsRemoteSource @Inject constructor(
    private val newsApi: NewsApi
) {
    suspend fun fetchNews(category: String): List<ArticleDto> {
        return newsApi.getTopHeadlines(category = category, country = "cn")
            .articles
            .filter { it.title.isNotBlank() }  // 过滤无效数据
    }
}

// data/src/main/java/.../local/NewsLocalSource.kt
class NewsLocalSource @Inject constructor(
    private val newsDao: NewsDao
) {
    suspend fun getArticles(category: String): List<ArticleEntity> {
        return newsDao.getArticlesByCategory(category)
    }

    @Transaction
    suspend fun replaceArticles(category: String, articles: List<ArticleEntity>) {
        newsDao.deleteByCategory(category)
        newsDao.insertAll(articles)
    }
}

// ==================== Presentation Layer ====================
@HiltViewModel
class NewsViewModel @Inject constructor(
    private val getNewsUseCase: GetNewsUseCase
) : ViewModel() {

    private val _uiState = MutableStateFlow(NewsUiState())
    val uiState: StateFlow<NewsUiState> = _uiState.asStateFlow()

    init {
        loadNews("technology")
    }

    fun loadNews(category: String) {
        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true) }

            getNewsUseCase(category).collect { result ->
                _uiState.update { state ->
                    when {
                        result.isSuccess -> state.copy(
                            isLoading = false,
                            articles = result.getOrDefault(emptyList()).map { it.toUiModel() },
                            error = null,
                            isFromCache = false  // 由 Flow 的第二次 emit 设为 false
                        )
                        result.isFailure -> state.copy(
                            isLoading = false,
                            error = result.exceptionOrNull()?.message ?: "Unknown error"
                        )
                        else -> state
                    }
                }
            }
        }
    }
}

// 缓存感知的 UI 状态
data class NewsUiState(
    val isLoading: Boolean = true,
    val articles: List<ArticleUiModel> = emptyList(),
    val error: String? = null,
    val isFromCache: Boolean = true  // 标识当前数据是否来自缓存
)
```

#### 多数据源策略对比

| 策略 | 实现方式 | 适用场景 | 用户体验 |
|------|---------|---------|---------|
| **Cache-First** | 先返回缓存，后台刷新 | 新闻、社交动态 | 秒开，可能看到旧数据 |
| **Network-First** | 先请求网络，失败用缓存 | 金融行情、实时数据 | 等待网络，保证数据最新 |
| **Cache-Only** | 仅用本地数据 | 离线笔记、草稿箱 | 即时，无网络要求 |
| **Network-Only** | 不用缓存 | 支付、验证码 | 保证数据一致性 |
| **Cache-then-Network** | Flow 多次 emit | 资讯类应用（推荐） | 秒开 + 自动更新 |

### 6.2 场景：模块化工程中的 Clean Architecture

在大型项目中，Clean Architecture 通常与**多模块工程**结合：

```
Project
├── :app                          ← 壳工程，依赖所有 feature 模块
├── :core
│   ├── :core:common              ← 通用工具类
│   ├── :core:network             ← Retrofit 配置、拦截器
│   ├── :core:database            ← Room 配置、迁移
│   └── :core:ui                  ← 通用 UI 组件
├── :feature
│   ├── :feature:auth
│   │   ├── :feature:auth:domain  ← 仅依赖 kotlin-stdlib, coroutines
│   │   ├── :feature:auth:data    ← 依赖 :core:network, :core:database, domain
│   │   └── :feature:auth:presentation ← 依赖 domain, :core:ui
│   └── :feature:news
│       ├── :feature:news:domain
│       ├── :feature:news:data
│       └── :feature:news:presentation
```

**每个 feature 模块内部也遵循 Clean Architecture 三层**：
- `:domain` — 纯 Kotlin，零 Android 依赖
- `:data` — 依赖 network/database 核心模块
- `:presentation` — 依赖 domain，包含 ViewModel 和 UI

---

## 总结：Clean Architecture 面试 Checklist

| 维度 | 必须掌握的关键点 |
|------|----------------|
| **分层结构** | Entity / UseCase / InterfaceAdapter / Framework 四层 + 依赖方向从外向内 |
| **依赖规则** | Domain 层零 Android 依赖；内层定义接口、外层实现 |
| **UseCase** | 单一职责、无状态、可组合、`operator fun invoke()` 语法糖 |
| **Repository** | 接口在 domain、实现在 data、多数据源策略封装在 Impl 中 |
| **数据映射** | DTO → Domain → UiModel 三级映射，每层隔离变更 |
| **MVVM 融合** | ViewModel 属于 Interface Adapter 层，是 UseCase 的消费者 |
| **DIP 实现** | Hilt @Binds 绑定接口与实现，消费方只依赖接口 |
| **测试优势** | Domain 层纯 JVM 测试，无需 Android 环境 |
| **反模式** | 贫血 UseCase、DTO 泄漏、Domain 有 Android 依赖、过度工程 |

---

> **最后的话**：Clean Architecture 不是银弹，它的核心价值在于**将"变化"隔离在系统边缘**。面试中展现你对"为什么这样分层"的深层理解——比背诵架构图重要得多。真正的高手，不是能画出最复杂的架构图，而是知道什么时候该用 Clean Architecture，什么时候该保持简单。
