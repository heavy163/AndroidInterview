# C++与安卓面试：核心原理、最佳实践与代码示例

---

## 一、面试问题（4+高频问题）

### Q1：C++智能指针（shared_ptr / unique_ptr / weak_ptr）在NDK开发中如何使用？各自适用什么场景？

**答案要点：**

- **`std::unique_ptr`**：独占所有权，不可拷贝，只能移动（move）。适用于JNI中管理独占的Native资源，如文件句柄、OpenGL纹理、SQLite数据库连接等。当unique_ptr离开作用域时，自动释放资源，无需手动`delete`。
- **`std::shared_ptr`**：共享所有权，内部维护引用计数。适用于多个Java对象共享同一Native对象场景——例如多个Surface引用同一个Native渲染器。典型用法是将shared_ptr存入Java对象的long型字段（nativeHandle）。
- **`std::weak_ptr`**：不增加引用计数，用于打破循环引用。最常见场景是观察者模式：Subject持有shared_ptr<Observer>，Observer持有weak_ptr<Subject>，防止互相持有导致永不释放。

**面试追问**：shared_ptr的引用计数是线程安全的吗？
> 答：引用计数的增减操作是线程安全的（原子操作），但shared_ptr本身指向的对象的并发访问需要额外加锁保护。也就是说，多个线程同时拷贝/销毁同一个shared_ptr是安全的，但多个线程同时读写`*ptr`是不安全的。

---

### Q2：NDK开发中如何选择STL？gnustl、libc++、stlport、system 各有什么差异？

**答案要点：**

| STL实现 | 特点 | 状态 |
|---------|------|------|
| `c++_shared`（libc++） | 现代C++，完整C++11/14/17支持；以.so形式链接，多个.so共享同一份STL，减少体积 | **推荐**，当前默认 |
| `c++_static`（libc++静态） | 同上但静态链接，每个.so各自包含STL，体积较大但避免STL版本冲突 | 适合单.so或避免依赖冲突 |
| `gnustl` | GNU STL，已废弃 | NDK r18起移除 |
| `stlport` | 早期STL实现，兼容老项目 | 已废弃 |
| `system` | 仅提供最基础C++头文件 | 几乎不用 |

**最佳实践：** 在`Application.mk`或`build.gradle`中配置：

```cmake
# CMakeLists.txt
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
# android.useLegacyPackaging = true 时 c++_shared 更优
```

```groovy
// build.gradle
android {
    defaultConfig {
        externalNativeBuild {
            cmake {
                arguments "-DANDROID_STL=c++_shared"
            }
        }
    }
}
```

**避坑要点：** 如果项目中多个.so都使用`c++_shared`，必须确保所有.so使用同一NDK版本编译，否则STL版本不一致导致ABI不兼容。

---

### Q3：C++中的线程安全和互斥锁在NDK中如何正确使用？

**答案要点：**

NDK中C++线程安全的核心工具是 `<mutex>`、`<atomic>`、`<condition_variable>`：

```cpp
#include <mutex>
#include <atomic>
#include <thread>

class NativeAudioEngine {
private:
    std::mutex mtx_;
    std::atomic<bool> isPlaying_{false};

public:
    // ✅ 正确：lock_guard RAII自动解锁
    void startPlayback() {
        std::lock_guard<std::mutex> lock(mtx_);
        // 临界区操作
        isPlaying_.store(true);
        // lock_guard离开作用域自动释放mutex
    }

    // ✅ 正确：unique_lock可手动解锁，配合condition_variable
    void waitForBuffer(std::condition_variable& cv) {
        std::unique_lock<std::mutex> lock(mtx_);
        cv.wait(lock, [this] { return !isPlaying_.load(); });
    }
};
```

**高频考点：**

| 工具 | 用途 | 注意 |
|------|------|------|
| `std::mutex` | 互斥锁 | 不可递归，不可拷贝 |
| `std::recursive_mutex` | 可递归互斥锁 | 同一线程可重复加锁 |
| `std::lock_guard` | RAII自动加锁/解锁 | 不可手动释放 |
| `std::unique_lock` | 灵活RAII锁 | 可配合condition_variable |
| `std::atomic<T>` | 原子操作 | 非阻塞，适合简单标志位 |

**典型错误：**
```cpp
// ❌ 错误：忘记解锁，死锁风险
void badCode() {
    mtx_.lock();
    if (error_condition) return;   // 提前返回，未解锁！
    mtx_.unlock();
}

// ✅ 正确：使用RAII
void goodCode() {
    std::lock_guard<std::mutex> lock(mtx_);
    if (error_condition) return;   // 自动解锁
}
```

**JNI线程注意事项：**
- `FindClass` 在非主线程调用会导致问题——应在`JNI_OnLoad`中缓存Class引用。
- JNIEnv是线程局部的，不能在多线程间共享Native层的`JNIEnv*`，需通过`JavaVM::AttachCurrentThread`获取当前线程的JNIEnv。

---

### Q4：JNI中C++对象的生命周期如何管理？如何与Java垃圾回收协调？

**答案要点：**

C++对象的生命周期由开发者显式管理（无GC），而Java对象由Dalvik/ART的GC自动管理。两者协调的核心策略：

#### 策略一：Java对象持有Native指针（Handle模式）

```cpp
// Native端：在Java的long字段存储C++对象指针
extern "C" JNIEXPORT jlong JNICALL
Java_com_example_NativeObject_nativeCreate(JNIEnv* env, jobject thiz) {
    auto* obj = new NativeObject();
    return reinterpret_cast<jlong>(obj);
}

extern "C" JNIEXPORT void JNICALL
Java_com_example_NativeObject_nativeDestroy(JNIEnv* env, jobject thiz, jlong handle) {
    delete reinterpret_cast<NativeObject*>(handle);
}
```

```java
// Java端
public class NativeObject {
    private long nativeHandle;  // 存储C++对象指针

    public NativeObject() {
        nativeHandle = nativeCreate();
    }

    public void release() {
        if (nativeHandle != 0) {
            nativeDestroy(nativeHandle);
            nativeHandle = 0;
        }
    }

    @Override
    protected void finalize() throws Throwable {
        release();  // 兜底释放，但不可靠
        super.finalize();
    }
}
```

#### 策略二：全局引用绑定生命周期

```cpp
// C++对象持有Java对象的GlobalRef，确保Java对象不被GC
class NativeRenderer {
    jobject javaPeer_;  // GlobalRef
public:
    NativeRenderer(JNIEnv* env, jobject javaObj)
        : javaPeer_(env->NewGlobalRef(javaObj)) {}

    ~NativeRenderer() {
        // 需要JNIEnv来释放GlobalRef，通常在JNI调用上下文中执行
    }
};
```

#### 策略三：智能指针 + 引用计数（推荐高级场景）

```cpp
// 多个Java对象共享同一个C++对象
#include <memory>
#include <unordered_map>

class NativeObjectPool {
    std::unordered_map<jlong, std::shared_ptr<NativeObject>> pool_;
    std::mutex mtx_;
    jlong nextId_ = 1;

public:
    jlong acquire(std::shared_ptr<NativeObject> obj) {
        std::lock_guard<std::mutex> lock(mtx_);
        jlong id = nextId_++;
        pool_[id] = obj;
        return id;
    }

    void release(jlong id) {
        std::lock_guard<std::mutex> lock(mtx_);
        pool_.erase(id);
    }
};
```

---

## 二、核心原理深度解析

### 2.1 RAII在JNI资源管理中的应用

**RAII（Resource Acquisition Is Initialization）** 是C++最核心的设计理念之一。在JNI场景中，资源获取（如GetStringUTFChars、PushLocalFrame、获取mutex锁）与释放必须配对，RAII可自动保证即使在异常/提前返回时也能正确释放。

```cpp
// ❌ 传统写法：极易漏释放
extern "C" JNIEXPORT jstring JNICALL
Java_com_example_Helper_process(JNIEnv* env, jobject, jstring input) {
    const char* str = env->GetStringUTFChars(input, nullptr);
    // ... 100行逻辑，某处可能return ...
    env->ReleaseStringUTFChars(input, str);
    return result;
}

// ✅ RAII包装器
class JStringUTF {
    JNIEnv* env_;
    jstring jstr_;
    const char* cstr_;
public:
    JStringUTF(JNIEnv* env, jstring jstr)
        : env_(env), jstr_(jstr), cstr_(env->GetStringUTFChars(jstr, nullptr)) {}

    ~JStringUTF() {
        if (cstr_) env_->ReleaseStringUTFChars(jstr_, cstr_);
    }

    const char* c_str() const { return cstr_; }
};

// ✅ 使用RAII后无需手动释放
extern "C" JNIEXPORT jstring JNICALL
Java_com_example_Helper_process(JNIEnv* env, jobject, jstring input) {
    JStringUTF utf(env, input);
    // 任何return路径都会自动调用析构函数释放
    if (utf.c_str()[0] == '\0') return nullptr;
    return env->NewStringUTF(utf.c_str());
}
```

**更多JNI RAII场景：**

```cpp
// LocalFrame RAII
class ScopedLocalFrame {
    JNIEnv* env_;
    int capacity_;
public:
    ScopedLocalFrame(JNIEnv* env, int capacity = 16)
        : env_(env), capacity_(capacity) {
        env_->PushLocalFrame(capacity);
    }
    ~ScopedLocalFrame() { env_->PopLocalFrame(nullptr); }
};

// GlobalRef RAII
class ScopedGlobalRef {
    JNIEnv* env_;
    jobject ref_;
public:
    ScopedGlobalRef(JNIEnv* env, jobject obj)
        : env_(env), ref_(env->NewGlobalRef(obj)) {}
    ~ScopedGlobalRef() { env_->DeleteGlobalRef(ref_); }
    jobject get() const { return ref_; }
};
```

### 2.2 std::mutex + lock_guard 原理

`std::mutex` 在Android底层调用的是Linux futex（Fast Userspace Mutex），轻量且高效。`std::lock_guard` 是纯RAII包装：

```cpp
template<typename Mutex>
class lock_guard {
    Mutex& mtx_;
public:
    explicit lock_guard(Mutex& m) : mtx_(m) { mtx_.lock(); }
    ~lock_guard() { mtx_.unlock(); }
    lock_guard(const lock_guard&) = delete;      // 不可拷贝
    lock_guard& operator=(const lock_guard&) = delete;
};
```

**原理要点：**
1. 构造时加锁，析构时解锁——利用C++的确定性析构语义
2. 不可拷贝（deleted copy constructor）——防止锁被意外复制导致双重释放
3. 栈上创建，函数返回或异常抛出时自动析构

**`std::unique_lock` vs `std::lock_guard`**：

| 特性 | lock_guard | unique_lock |
|------|-----------|-------------|
| 大小 | 最小（1个引用） | 较大（包含状态标志） |
| 灵活性 | 最低（无法手动解锁） | 高（可手动lock/unlock） |
| 与condition_variable配合 | ❌ | ✅ |
| 开销 | 几乎为零 | 略高 |

### 2.3 C++对象与Java对象的生命周期绑定

```
┌─────────────────────────────────────────────────────────────┐
│                    Java Layer (ART/Dalvik)                   │
│                                                              │
│   NativeObject.java              NativePeer.java            │
│   ┌──────────────────┐          ┌──────────────────┐       │
│   │ long nativeHandle │────────▶│ Native Peer (JNI) │       │
│   │ nativeCreate()    │          │ nativeInit()     │       │
│   │ nativeDestroy()   │          └────────┬─────────┘       │
│   └──────────────────┘                    │                 │
│           │                               │ jlong handle    │
│           │ finalize() / release()        │                 │
└───────────┼───────────────────────────────┼─────────────────┘
            │                               │
            ▼                               ▼
┌─────────────────────────────────────────────────────────────┐
│                    Native Layer (C++)                        │
│                                                              │
│   ┌──────────────────┐          ┌──────────────────┐       │
│   │  NativeObject*    │          │  NativePeer*     │       │
│   │  (unique_ptr)     │          │  (shared_ptr)    │       │
│   │                   │          │                  │       │
│   │  - data_          │◀────────│  - weak_ptr ─────┼───┐   │
│   │  - mutex_         │  shared  │  - observers_    │   │   │
│   └──────────────────┘          └──────────────────┘   │   │
│            │                              │              │   │
│            ▼                              ▼              │   │
│   ┌──────────────────┐          ┌──────────────────┐   │   │
│   │  Resource Pool   │          │  RenderContext   │   │   │
│   │  (static)        │          │  (per-instance)  │   │   │
│   └──────────────────┘          └──────────────────┘   │   │
│                                                          │   │
│   生命周期规则：                                           │   │
│   1. Java finalize ➔ nativeDestroy ➔ delete C++对象      │   │
│   2. GlobalRef持有Java对象 ➔ 阻止Java GC                  │   │
│   3. weak_ptr持有NativePeer ➔ 不阻止释放，可检测存活       │   │
└─────────────────────────────────────────────────────────────┘
```

**生命周期绑定规则总结：**

| 方向 | 持有方式 | GC影响 |
|------|---------|--------|
| Java → C++ | `long nativeHandle` 存储指针 | C++对象不受Java GC影响，需手动delete |
| C++ → Java | `NewGlobalRef()` 持有jobject | Java对象不会被GC，直到DeleteGlobalRef |
| 弱引用 C++ → Java | `NewWeakGlobalRef()` | Java对象可被GC回收 |
| C++内部共享 | `shared_ptr<T>` | 引用计数归零时delete |
| 打破循环引用 | `weak_ptr<T>` | 不阻止shared_ptr释放 |

---

## 三、NDK项目中C++最佳实践案例

### 案例一：音频引擎的RAII资源管理

```cpp
// AudioEngine.h - 完整RAII音频引擎
#pragma once
#include <memory>
#include <mutex>
#include <vector>
#include <jni.h>
#include <SLES/OpenSLES.h>
#include <SLES/OpenSLES_Android.h>

class AudioEngine {
public:
    AudioEngine();
    ~AudioEngine();
    AudioEngine(const AudioEngine&) = delete;
    AudioEngine& operator=(const AudioEngine&) = delete;

    bool init(int sampleRate, int channels);
    void play();
    void stop();
    void writeSamples(const int16_t* data, size_t count);

private:
    // SLEngine RAII包装
    struct SLEngineDeleter {
        void operator()(SLObjectItf obj) {
            if (obj) (*obj)->Destroy(obj);
        }
    };
    using SLEnginePtr = std::unique_ptr<std::remove_pointer_t<SLObjectItf>,
                                         SLEngineDeleter>;

    SLEnginePtr engineObj_;
    SLEngineItf engine_ = nullptr;
    SLObjectItf outputMixObj_ = nullptr;
    SLObjectItf playerObj_ = nullptr;
    SLPlayItf player_ = nullptr;
    SLAndroidSimpleBufferQueueItf bufferQueue_ = nullptr;

    std::mutex stateMutex_;
    bool initialized_ = false;
    bool playing_ = false;

    std::vector<int16_t> audioBuffer_;
    static constexpr size_t kBufferSize = 4096;
};

// AudioEngine.cpp
AudioEngine::AudioEngine() : audioBuffer_(kBufferSize, 0) {}

AudioEngine::~AudioEngine() {
    stop();
    // SLEnginePtr自动Destroy，无需手动清理
}

bool AudioEngine::init(int sampleRate, int channels) {
    std::lock_guard<std::mutex> lock(stateMutex_);

    // 使用unique_ptr管理OpenSL ES对象生命周期
    SLObjectItf engineObj;
    slCreateEngine(&engineObj, 0, nullptr, 0, nullptr, nullptr);
    engineObj_.reset(engineObj);  // 转移所有权给RAII

    (*engineObj)->Realize(engineObj, SL_BOOLEAN_FALSE);
    (*engineObj)->GetInterface(engineObj, SL_IID_ENGINE, &engine_);

    // 创建OutputMix（生命周期由成员管理）
    (*engine_)->CreateOutputMix(engine_, &outputMixObj_, 0, nullptr, nullptr);
    (*outputMixObj_)->Realize(outputMixObj_, SL_BOOLEAN_FALSE);

    initialized_ = true;
    return true;
}

void AudioEngine::play() {
    std::lock_guard<std::mutex> lock(stateMutex_);
    if (!initialized_ || playing_) return;

    // 配置BufferQueue音频源
    SLDataLocator_AndroidSimpleBufferQueue locBufQ = {
        SL_DATALOCATOR_ANDROIDSIMPLEBUFFERQUEUE, 2
    };
    SLDataFormat_PCM formatPCM = {
        SL_DATAFORMAT_PCM, 1, SL_SAMPLINGRATE_44_1,
        SL_PCMSAMPLEFORMAT_FIXED_16, SL_PCMSAMPLEFORMAT_FIXED_16,
        SL_SPEAKER_FRONT_CENTER, SL_BYTEORDER_LITTLEENDIAN
    };
    SLDataSource audioSrc = {&locBufQ, &formatPCM};

    SLDataLocator_OutputMix locOutMix = {
        SL_DATALOCATOR_OUTPUTMIX, outputMixObj_
    };
    SLDataSink audioSnk = {&locOutMix, nullptr};

    (*engine_)->CreateAudioPlayer(engine_, &playerObj_,
                                   &audioSrc, &audioSnk,
                                   0, nullptr, nullptr);
    (*playerObj_)->Realize(playerObj_, SL_BOOLEAN_FALSE);
    (*playerObj_)->GetInterface(playerObj_, SL_IID_PLAY, &player_);
    (*playerObj_)->GetInterface(playerObj_, SL_IID_BUFFERQUEUE, &bufferQueue_);

    (*player_)->SetPlayState(player_, SL_PLAYSTATE_PLAYING);
    playing_ = true;
    // 所有SL对象在析构函数中统一清理
}

void AudioEngine::stop() {
    std::lock_guard<std::mutex> lock(stateMutex_);
    if (playerObj_) {
        (*playerObj_)->Destroy(playerObj_);
        playerObj_ = nullptr;
        player_ = nullptr;
        bufferQueue_ = nullptr;
    }
    playing_ = false;
}

// JNI接口
extern "C" JNIEXPORT jlong JNICALL
Java_com_example_AudioEngine_nativeInit(JNIEnv*, jobject) {
    auto engine = std::make_unique<AudioEngine>();
    if (engine->init(44100, 1)) {
        return reinterpret_cast<jlong>(engine.release());
    }
    return 0;
}

extern "C" JNIEXPORT void JNICALL
Java_com_example_AudioEngine_nativeDestroy(JNIEnv*, jobject, jlong handle) {
    delete reinterpret_cast<AudioEngine*>(handle);
}
```

**案例价值：**
- OpenSL ES的`SLObjectItf`生命周期完全由`unique_ptr`+自定义Deleter管理
- `std::lock_guard`保证多线程安全的播放/停止切换
- JNI层通过Handle模式传递C++对象，Java端完全无感知

---

### 案例二：线程池 + 任务队列的NDK加解密实践

```cpp
// ThreadPool.h - 多线程加解密引擎
#pragma once
#include <vector>
#include <queue>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <functional>
#include <future>
#include <jni.h>

class ThreadPool {
public:
    explicit ThreadPool(size_t numThreads);
    ~ThreadPool();

    template<typename Func, typename... Args>
    auto enqueue(Func&& func, Args&&... args)
        -> std::future<typename std::result_of_t<Func(Args...)>>;

private:
    std::vector<std::thread> workers_;
    std::queue<std::function<void()>> tasks_;
    std::mutex queueMutex_;
    std::condition_variable condition_;
    std::atomic<bool> stop_{false};
};

// 实现
ThreadPool::ThreadPool(size_t numThreads) {
    for (size_t i = 0; i < numThreads; ++i) {
        workers_.emplace_back([this] {
            while (true) {
                std::function<void()> task;
                {
                    std::unique_lock<std::mutex> lock(queueMutex_);
                    condition_.wait(lock, [this] {
                        return stop_.load() || !tasks_.empty();
                    });
                    if (stop_.load() && tasks_.empty()) return;
                    task = std::move(tasks_.front());
                    tasks_.pop();
                }
                task();  // 执行任务（锁已释放）
            }
        });
    }
}

ThreadPool::~ThreadPool() {
    stop_.store(true);
    condition_.notify_all();
    for (auto& worker : workers_) {
        if (worker.joinable()) worker.join();
    }
}

template<typename Func, typename... Args>
auto ThreadPool::enqueue(Func&& func, Args&&... args)
    -> std::future<typename std::result_of_t<Func(Args...)>> {
    using ReturnType = typename std::result_of_t<Func(Args...)>;

    auto task = std::make_shared<std::packaged_task<ReturnType()>>(
        std::bind(std::forward<Func>(func), std::forward<Args>(args)...)
    );

    std::future<ReturnType> result = task->get_future();
    {
        std::unique_lock<std::mutex> lock(queueMutex_);
        if (stop_.load()) {
            throw std::runtime_error("ThreadPool已停止");
        }
        tasks_.emplace([task]() { (*task)(); });
    }
    condition_.notify_one();
    return result;
}

// JNI层：文件并行AES加密
extern "C" JNIEXPORT jboolean JNICALL
Java_com_example_CryptoHelper_nativeParallelEncrypt(
    JNIEnv* env, jobject, jstring inputPath, jstring outputPath, jstring key) {

    const char* inPath = env->GetStringUTFChars(inputPath, nullptr);
    const char* outPath = env->GetStringUTFChars(outputPath, nullptr);
    const char* keyStr = env->GetStringUTFChars(key, nullptr);

    // 使用RAII释放JNI字符串
    struct StringReleaser {
        JNIEnv* env; jstring jstr; const char* cstr;
        ~StringReleaser() { env->ReleaseStringUTFChars(jstr, cstr); }
    };
    StringReleaser r1{env, inputPath, inPath};
    StringReleaser r2{env, outputPath, outPath};
    StringReleaser r3{env, key, keyStr};

    // 硬件并发线程数（Android设备适配）
    size_t numCores = std::thread::hardware_concurrency();
    if (numCores == 0) numCores = 4;  // 兜底

    ThreadPool pool(std::min(numCores, size_t(8)));

    // 分块并行加密
    constexpr size_t kChunkSize = 1024 * 1024;  // 1MB块
    std::vector<std::future<bool>> futures;
    // ... 分块读取、提交到线程池、加密写入 ...

    return JNI_TRUE;
}
```

**案例价值：**
- `std::condition_variable` + `std::unique_lock` 实现生产者-消费者模型
- `std::atomic<bool>` 无锁标记线程池停止状态
- `std::future` 获取异步任务结果
- 硬件并发数适配：Android设备核心数差异巨大（从2核到8核+），使用`hardware_concurrency()`动态适配

---

### 案例三：全局JNI引用缓存与JNI_OnLoad模式

```cpp
// JNIBridge.cpp — JNI_OnLoad 全局缓存标准模式
#include <jni.h>
#include <mutex>

namespace {
    JavaVM* gVM = nullptr;

    // 全局缓存的Class引用
    jclass gClass_ArrayList = nullptr;
    jclass gClass_StringBuilder = nullptr;

    // 方法ID缓存
    jmethodID gMethod_ArrayList_add = nullptr;
    jmethodID gMethod_ArrayList_get = nullptr;

    std::once_flag gInitFlag;
}

jint JNI_OnLoad(JavaVM* vm, void* /*reserved*/) {
    gVM = vm;

    JNIEnv* env = nullptr;
    if (vm->GetEnv(reinterpret_cast<void**>(&env), JNI_VERSION_1_6) != JNI_OK) {
        return JNI_ERR;
    }

    // 缓存全局Class引用（用GlobalRef防止后续被GC后FindClass失效）
    jclass localArrayList = env->FindClass("java/util/ArrayList");
    gClass_ArrayList = static_cast<jclass>(env->NewGlobalRef(localArrayList));
    env->DeleteLocalRef(localArrayList);

    jclass localSB = env->FindClass("java/lang/StringBuilder");
    gClass_StringBuilder = static_cast<jclass>(env->NewGlobalRef(localSB));
    env->DeleteLocalRef(localSB);

    // 缓存方法ID
    gMethod_ArrayList_add = env->GetMethodID(gClass_ArrayList, "add", "(Ljava/lang/Object;)Z");
    gMethod_ArrayList_get = env->GetMethodID(gClass_ArrayList, "get", "(I)Ljava/lang/Object;");

    return JNI_VERSION_1_6;
}

void JNI_OnUnload(JavaVM* /*vm*/, void* /*reserved*/) {
    // 注意：卸载时JNIEnv可能不可用，需通过AttachCurrentThread获取
    JNIEnv* env = nullptr;
    if (gVM->AttachCurrentThread(&env, nullptr) == JNI_OK) {
        if (gClass_ArrayList) env->DeleteGlobalRef(gClass_ArrayList);
        if (gClass_StringBuilder) env->DeleteGlobalRef(gClass_StringBuilder);
        gVM->DetachCurrentThread();
    }
}

// 跨线程安全获取JNIEnv
JNIEnv* getJNIEnv() {
    JNIEnv* env = nullptr;
    if (gVM->GetEnv(reinterpret_cast<void**>(&env), JNI_VERSION_1_6) == JNI_OK) {
        return env;
    }
    // 非Java线程需Attach
    if (gVM->AttachCurrentThread(&env, nullptr) == JNI_OK) {
        return env;
    }
    return nullptr;
}
```

**案例价值：**
- `JNI_OnLoad`中做一次性初始化，缓存Class和MethodID
- `NewGlobalRef`防止Class对象被GC导致悬垂引用
- `getJNIEnv()`封装`AttachCurrentThread`逻辑，统一多线程场景

---

## 四、常见踩坑与优化建议

### 4.1 C++异常与JNI边界

```cpp
// ❌ 错误：C++异常不能跨越JNI边界
extern "C" JNIEXPORT void JNICALL
Java_com_example_Helper_process(JNIEnv* env, jobject) {
    try {
        throw std::runtime_error("C++ error"); // 未捕获会崩溃
    } catch (const std::exception& e) {
        // ✅ 必须在JNI层catch所有C++异常
        jclass exClass = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(exClass, e.what());
    }
}
```

### 4.2 局部引用溢出

JNI局部引用表默认只有512个槽位。长时间循环创建大量对象会导致`LocalRef overflow`。

```cpp
// ✅ 解决方案：PushLocalFrame / PopLocalFrame
for (int i = 0; i < 10000; i++) {
    env->PushLocalFrame(16);  // 创建新的局部帧
    jobject obj = env->NewObject(someClass, someMethod);
    // obj只在这个frame内有效
    env->PopLocalFrame(nullptr);  // 释放整个frame的所有引用
}
```

### 4.3 编译优化建议

```cmake
# CMakeLists.txt — NDK C++最佳编译配置
cmake_minimum_required(VERSION 3.10)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 重点优化项
set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} -O2 -flto=thin -fvisibility=hidden")
set(CMAKE_SHARED_LINKER_FLAGS_RELEASE "${CMAKE_SHARED_LINKER_FLAGS_RELEASE} -flto=thin -Wl,--gc-sections")

# 异常和RTTI：体积敏感可关闭
# set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fno-exceptions -fno-rtti")
```

---

## 总结：C++在NDK中的核心优势

| 特性 | 优势 | 典型场景 |
|------|------|---------|
| RAII | 自动资源管理，消除内存泄漏 | JNI字符串/文件/锁管理 |
| 智能指针 | 明确所有权语义 | Native对象与Java对象生命周期绑定 |
| `<atomic>` / `<mutex>` | 零开销线程安全 | 音频/视频处理，多线程渲染 |
| `<thread>` / `<future>` | 跨平台多线程 | 并行计算、加解密 |
| 零成本抽象 | 性能接近C，代码可读性远超C | 游戏引擎、图像处理 |
| 确定性析构 | 无GC暂停，实时性有保障 | 音频实时播放、传感器数据处理 |

掌握这些C++与NDK结合的核心技术，你就能在面试中从容回答关于C++在Android中应用的几乎所有关键问题。
