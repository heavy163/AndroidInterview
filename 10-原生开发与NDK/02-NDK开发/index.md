# 02 NDK 开发

> **面试权重：★★★★☆**  
> CMake 构建、so 库加载、ABI 兼容性 —— NDK 开发面试必考三大件

---

## 1. 面试问题集（6 道高频真题）

### Q1: CMake 与 ndk-build 有什么区别？Android 官方推荐哪个？为什么？

**标准答案：**

| 维度 | CMake | ndk-build (Android.mk) |
|:---|:---|:---|
| **配置文件** | `CMakeLists.txt` | `Android.mk` + `Application.mk` |
| **跨平台性** | 通用构建系统，Windows/Linux/macOS 都支持 | Android 专用，仅 NDK 环境可用 |
| **IDE 集成** | Android Studio 原生支持，Gradle 联动 | 需手动配置，IDE 支持较弱 |
| **依赖管理** | `find_package`、`add_subdirectory` 机制成熟 | 需手写 `PREBUILT_SHARED_LIBRARY` |
| **增量编译** | 良好支持 | 依赖 `LOCAL_SHORT_COMMANDS` 等手段 |
| **Google 立场** | **官方推荐**，2016 年起作为默认构建系统 | 遗留项目维护，新项目不推荐 |

**延伸要点：**
- CMake 通过 `build.gradle` 中的 `externalNativeBuild { cmake { path "CMakeLists.txt" } }` 声明。
- CMake 支持 `-DANDROID_ABI`、`-DANDROID_PLATFORM` 等 NDK 专用变量。
- 迁移建议：老项目可同时兼容两种构建方式，但新模块一律用 CMake。

---

### Q2: System.loadLibrary("xxx") 的 so 搜索路径是什么？为什么有时会报 UnsatisfiedLinkError？

**标准答案：**

`System.loadLibrary("native-lib")` 的搜索路径按优先级：

```
1. /data/app/<package>/lib/arm64/          ← 应用安装时解压的 so
2. /vendor/lib64/                           ← vendor 分区
3. /system/lib64/                           ← 系统分区
```

**UnsatisfiedLinkError 常见原因：**

| 原因 | 场景 | 解决 |
|:---|:---|:---|
| **ABI 不匹配** | 手机是 arm64-v8a，但 apk 中只打包了 armeabi-v7a 的 so | 在 `build.gradle` 中配置 `abiFilters` |
| **so 未打包进 apk** | CMakeLists.txt 未正确配置 `add_library` | 检查 CMake 输出和 `jniLibs` 目录 |
| **依赖 so 缺失** | libA.so 依赖 libB.so，但 libB.so 未加载 | 先 `System.loadLibrary("B")`，再加载 A |
| **Native 方法签名不匹配** | JNI 函数名与 Java 类路径不对应 | 使用 `javah` 或自动生成 |
| **STL 运行时缺失** | 使用了 C++ STL 但未链接 `c++_shared` | CMake 中设置 `-DANDROID_STL=c++_shared` |

---

### Q3: ABI 兼容性你是怎么处理的？armeabi-v7a、arm64-v8a、x86 之间有什么差异？

**标准答案：**

#### ABI 对照表

| 特性 | armeabi-v7a | arm64-v8a | x86 | x86_64 |
|:---|:---|:---|:---|:---|
| **指令集** | ARMv7 (32-bit) | AArch64 (64-bit) | x86 (32-bit) | x86_64 (64-bit) |
| **指针宽度** | 4 字节 | 8 字节 | 4 字节 | 8 字节 |
| **浮点运算** | VFPv3-D16（软浮点可选） | 硬件 NEON | SSE/SSE2 | SSE4.1+ |
| **强制要求** | 可选（armeabi 已废弃） | **Google Play 强制 64-bit** | 模拟器可用 | 模拟器可用 |
| **兼容模式** | arm64 设备兼容运行 v7a so | 原生 64 位，兼容 32 位 | x86_64 兼容 x86 | 原生 64 位 |
| **市场占比** | ~15%（老旧设备） | **~85%（主流设备）** | <1%（模拟器为主） | <1% |

**生产环境最佳实践：**

```groovy
// build.gradle (app)
android {
    defaultConfig {
        ndk {
            abiFilters 'arm64-v8a', 'armeabi-v7a'  // 仅保留两个主要 ABI
        }
    }
}
```

**核心原则：**
1. **首选 arm64-v8a**：Google Play 2019 年起强制要求 64 位，且性能提升 15%-20%。
2. **保留 armeabi-v7a**：覆盖存量低端设备（API 21+）。
3. **删除 x86/x86_64**：除非需要模拟器调试，否则增大 APK 体积无意义。
4. **App Bundle (aab)** 会自动按设备 ABI 分发，不用手动裁剪。

**兼容模式的坑：**
- arm64 设备运行 32-bit so 时，`/proc/cpuinfo` 显示的是 armv8，但进程实际跑在 32-bit 模式。
- `sizeof(long)` 在 32 位下是 4 字节，64 位下是 8 字节，直接传递 `long` 给 Native 层会引发内存越界。

---

### Q4: Native 线程和 Java 线程是什么关系？pthread_create 创建的线程能回调 Java 吗？

**标准答案：**

三者关系递进：

```
pthread_create()  →  OS 原生线程
        ↓
Thread (Java)    →  ART 虚拟机管理的线程（内部封装了 pthread）
        ↓
JNIEnv*          →  线程的 JNI 上下文指针（**线程绑定**）
```

**关键机制：**

1. **默认情况**：`pthread_create` 创建的线程**没有绑定 JNIEnv**，不能直接调用 JNI 函数。
2. **绑定步骤**：
   ```cpp
   JavaVM* g_jvm;  // 在 JNI_OnLoad 中保存全局引用
   
   void* native_thread_func(void* args) {
       JNIEnv* env;
       // 关键：将当前 OS 线程附加到 JVM
       g_jvm->AttachCurrentThread(&env, nullptr);
       
       // 现在可以安全调用 JNI 函数了
       jclass clazz = env->FindClass("com/example/MainActivity");
       env->CallStaticVoidMethod(clazz, ...);
       
       // 用完后分离（可选，但线程结束时建议调用）
       g_jvm->DetachCurrentThread();
       return nullptr;
   }
   ```

3. **线程名对应关系**：
   - Java 线程名 `"main"` → Native 层 `prctl(PR_GET_NAME)` 得到 `"main"`。
   - ART 会给 Native-attached 线程命名格式 `"Thread-N"`。

**面试陷阱：**
- ❌ `JNIEnv*` 是**线程局部**的，不能跨线程传递。
- ❌ `FindClass` 在 Native 线程中调用时，如果类在 dex 中未加载会返回 NULL——需要用主线程提前 `FindClass` 并持有 `jclass` 全局引用。

---

### Q5: Native 崩溃如何调试？Crash 日志怎么看？

**标准答案：**

#### 调试工具链

| 工具 | 作用 | 命令示例 |
|:---|:---|:---|
| **ndk-stack** | 将崩溃地址翻译为源码行号 | `adb logcat \| ndk-stack -sym ./obj/local/arm64-v8a/` |
| **addr2line** | 根据地址定位源码行 | `aarch64-linux-android-addr2line -e libnative.so 0x12345` |
| **objdump** | 反编译 so，查看符号表 | `aarch64-linux-android-objdump -S libnative.so` |
| **readelf** | 查看 ELF 段信息 | `readelf -d libnative.so \| grep NEEDED` |
| **tombstone** | 系统自动生成的崩溃报告 | `/data/tombstones/tombstone_00` |

#### 崩溃日志解读流程

```
*** *** *** *** *** *** *** *** *** *** *** *** *** *** *** ***
Build fingerprint: 'google/taimen/taimen:12/...'
pid: 12345, tid: 12346, name: MyNativeThread  >>> com.example.app <<<
signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x00000000
    x0  0000000000000000  x1  00000072d0f8e400  x2  0000000000000005
    ...
backtrace:
    #00 pc 0000000000012345  /data/app/com.example.app-xxx/lib/arm64/libnative.so (my_function+20)
    #01 pc 0000000000015678  /data/app/com.example.app-xxx/lib/arm64/libnative.so (Java_com_example_app_MainActivity_processData+48)
```

**解析步骤：**
1. 读取 `signal 11 (SIGSEGV)` → 空指针/野指针访问。
2. 读取 `fault addr 0x00000000` → 确实是空指针解引用。
3. 读取 `#00 pc 0x12345` → 崩溃在 `my_function+20` 偏移处。
4. 用 `addr2line -e libnative.so 0x12345` 定位到具体 C/C++ 行。

#### Bugly / Firebase Crashlytics 集成

线上环境建议接入符号表上传：
```bash
# 将带符号的 so 上传到 Bugly 后台
java -jar buglySymbolAndroid.jar -appid xxx -appkey xxx -bundleid xxx \
     -version 1.0.0 -platform Android -inputSymbol ./obj/
```
这样线上崩溃堆栈会自动还原为带行号的源码。

---

### Q6: NDK 开发常用哪些第三方 Native 库？

**标准答案：**

| 库 | 用途 | 典型面试说法 |
|:---|:---|:---|
| **OpenSL ES** | 低延迟音频播放/录制 | Android 原生音频 API，延迟 <20ms，比 AudioTrack 更适合实时音频 |
| **AAudio** | API 26+ 的高性能音频 | Google 推荐的新一代音频 API，比 OpenSL ES 更简洁 |
| **OpenCV** | 计算机视觉 | 人脸检测、图像滤镜；Android 上用 `OpenCV-android-sdk` 预编译 so |
| **FFmpeg** | 音视频编解码 | 交叉编译后封装为 so；视频播放器、推流 SDK 必用 |
| **libyuv** | YUV 格式转换 | 摄像头预览帧旋转、缩放，性能远优于 Java 层的 `YuvImage` |
| **TensorFlow Lite** | 端侧 AI 推理 | 通过 Native API 加载 `.tflite` 模型做图像分类 |
| **Protobuf (nanopb)** | 序列化 | 比 JSON 体积更小，适合 Native 和 Java 通信 |

---

## 2. 核心原理深度解析

### 2.1 CMake 构建全流程

```
Gradle 触发构建
      │
      ▼
externalNativeBuild { cmake { ... } }
      │
      ▼
CMake 读取 CMakeLists.txt
      │
      ├── cmake_minimum_required(VERSION 3.18.1)
      ├── project("native-lib")
      ├── add_library(native-lib SHARED native-lib.cpp)
      ├── target_include_directories(native-lib PRIVATE ${CMAKE_SOURCE_DIR}/include)
      ├── find_library(log-lib log)                     ← 查找系统库
      ├── target_link_libraries(native-lib ${log-lib})  ← 链接
      └── set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -std=c++17 -O2")
      │
      ▼
CMake 调用 NDK 工具链 (ninja/make)
      │
      ├── aarch64-linux-android21-clang++  编译 arm64-v8a
      ├── armv7a-linux-androideabi21-clang++  编译 armeabi-v7a
      └── (根据 abiFilters 决定编译几个 ABI)
      │
      ▼
生成 libnative-lib.so → 输出到 build/intermediates/cmake/
      │
      ▼
Gradle 将 .so 打包进 APK 的 lib/<ABI>/ 目录
```

**CMake 关键变量速查：**

| 变量 | 含义 |
|:---|:---|
| `${ANDROID_ABI}` | 当前编译的 ABI（如 arm64-v8a） |
| `${ANDROID_PLATFORM}` | 最小 API level（如 android-21） |
| `${ANDROID_STL}` | STL 运行时（c++_shared / c++_static / none） |
| `${CMAKE_SOURCE_DIR}` | CMakeLists.txt 所在目录 |
| `${CMAKE_LIBRARY_OUTPUT_DIRECTORY}` | so 输出目录 |

### 2.2 so 库加载流程（从 Java 到底层）

**流程图：**

```
System.loadLibrary("native-lib")
        │
        ▼
Runtime.loadLibrary0(ClassLoader, String)
        │
        ├── 获取 ClassLoader（通常是 PathClassLoader）
        │
        ▼
ClassLoader.findLibrary("native-lib")
        │
        ▼
DexPathList.findLibrary("native-lib")
        │
        ├── 遍历 nativeLibraryPathElements[] 
        │     ├── /data/app/<pkg>/lib/arm64/
        │     ├── /vendor/lib64/
        │     └── /system/lib64/
        │
        ▼
找到 /data/app/<pkg>/lib/arm64/libnative-lib.so
        │
        ▼
nativeLoad(path, classLoader, caller)
        │  (Runtime.nativeLoad → Native 方法)
        │
        ▼
dlopen("libnative-lib.so", RTLD_LAZY)
        │
        ├── Linux 动态链接器 ld.so 加载 ELF 文件
        ├── 解析 .dynamic 段 → 递归加载依赖 so（NEEDED 条目）
        ├── 执行 .init_array 中的构造函数
        │
        ▼
JNI_OnLoad(JavaVM* vm, void* reserved)
        │
        │  ← 这里可以缓存 JavaVM* 指针，做动态注册
        │
        ▼
dlsym(handle, "Java_com_example_...") → 找到 JNI 函数地址
        │
        ▼
ART 将 Java 方法和 Native 函数指针绑定 → 调用通路建立
```

**关键设计点：**
- `findLibrary` 只追加 `lib` 前缀和 `.so` 后缀，不会递归搜索子目录。
- 加载顺序是**应用目录 → vendor → system**，意味着你可以用同名 so 覆盖系统库。
- `dlopen` 的 `RTLD_LAZY` 表示延迟符号解析——只有首次调用时才解析函数地址。

### 2.3 NDK 的 STL 支持详解

| 运行时 | 状态 | 特点 |
|:---|:---|:---|
| **libc++_shared.so** | ✅ 官方推荐 | C++11/14/17 完整支持；动态链接，多个 so 可共享；需随 APK 打包 |
| **libc++_static.a** | ✅ 可用 | 静态链接进 so，无外部依赖，但多个 so 会导致 STL 代码重复、全局状态不共享 |
| **gnustl** | ❌ NDK r18 已移除 | 曾用于 `armeabi-v7a`，现在不可用 |
| **stlport** | ❌ 已废弃 | 早期版本使用，现已完全移除 |
| **system** | ⚠️ 仅用于 C | 无 C++ 标准库支持，链接 `stdc++` 最小库 |

**选择建议：**
```cmake
# 单个 so 场景：静态链接最简单
set(CMAKE_ANDROID_STL_TYPE c++_static)

# 多个 so 互相依赖场景：必须用动态链接
set(CMAKE_ANDROID_STL_TYPE c++_shared)
# 且 build.gradle 中要声明：
android {
    defaultConfig {
        ndk {
            stl "c++_shared"
        }
    }
}
```

---

## 3. 源码分析：Runtime.loadLibrary0()

以下基于 **AOSP Android 12** 源码的简化分析：

```java
// frameworks/base/core/java/java/lang/Runtime.java

// System.loadLibrary 最终调用这里
synchronized void loadLibrary0(ClassLoader loader, String libName) {
    // 1. 安全检查：防止加载非公开库
    //    如果调用者是系统类且库名不在白名单 → 拒绝
    String librarySearchPath = null;
    if (loader != null) {
        // 2. 通过 ClassLoader 查找 so 文件路径
        librarySearchPath = loader.findLibrary(libName);
        //    → PathClassLoader → DexPathList.findLibrary()
        if (librarySearchPath != null) {
            // 3. 找到路径，直接加载
            String error = doLoad(librarySearchPath, loader);
            if (error != null) {
                throw new UnsatisfiedLinkError(error);
            }
            return;
        }
    }
    
    // 4. ClassLoader 找不到，尝试 java.library.path 系统路径
    //    （Android 上该路径通常为空/不可用）
    String[] paths = System.getProperty("java.library.path", "").split(":");
    for (String path : paths) {
        String candidate = path + "/lib" + libName + ".so";
        if (IoUtils.canOpenReadOnly(candidate)) {
            String error = doLoad(candidate, loader);
            if (error == null) return;
        }
    }
    
    // 5. 所有路径都找不到 → 抛出 UnsatisfiedLinkError
    throw new UnsatisfiedLinkError(
        "Couldn't load " + libName + ": findLibrary returned null");
}
```

**关键设计要点：**

1. **ClassLoader 优先**：`findLibrary` 返回应用私有目录路径，避免加载恶意替换的 so。
2. **系统路径降级**：仅在 ClassLoader 查找失败后才回退 `java.library.path`。
3. **doLoad → nativeLoad**：最终通过 JNI 调用 `Runtime_nativeLoad`，该 Native 方法调用 `dlopen(3)`。
4. **线程安全**：整个方法用 `synchronized` 修饰，同一时间只有一个线程能加载 so。

---

## 4. 应用场景实战：FFmpeg 的 Android 交叉编译

### 4.1 场景描述

在视频播放器/直播推流 SDK 中，需要集成 FFmpeg 实现 H.264/H.265 解码。FFmpeg 是 C 语言编写的跨平台音视频库，在 Android 上需要**交叉编译**生成各 ABI 的 `.so` 文件。

### 4.2 交叉编译完整流程

```bash
# ===== 第一步：准备 NDK 工具链 =====
export NDK_ROOT=$ANDROID_HOME/ndk/25.1.8937393
export HOST_TAG=linux-x86_64

# 构建独立工具链（或直接用 NDK 内置的）
TOOLCHAIN=$NDK_ROOT/toolchains/llvm/prebuilt/$HOST_TAG

# ===== 第二步：FFmpeg 配置脚本 =====
#!/bin/bash
# build_ffmpeg_android.sh

API=21  # 最小 SDK 版本

build_one() {
    ABI=$1
    case $ABI in
        arm64-v8a)
            ARCH=aarch64
            CPU=armv8-a
            CROSS_PREFIX=$TOOLCHAIN/bin/aarch64-linux-android-
            CC=$TOOLCHAIN/bin/aarch64-linux-android$API-clang
            ;;
        armeabi-v7a)
            ARCH=arm
            CPU=armv7-a
            CROSS_PREFIX=$TOOLCHAIN/bin/arm-linux-androideabi-
            CC=$TOOLCHAIN/bin/armv7a-linux-androideabi$API-clang
            ;;
        *)
            echo "Unknown ABI: $ABI"
            exit 1
            ;;
    esac

    ./configure \
        --prefix=./android/$ABI \
        --target-os=android \
        --arch=$ARCH \
        --cpu=$CPU \
        --cross-prefix=$CROSS_PREFIX \
        --cc=$CC \
        --enable-cross-compile \
        --enable-shared \                        # 生成 .so
        --disable-static \                       # 不生成 .a
        --disable-doc \                          # 去掉文档，减少体积
        --disable-ffmpeg \                       # 不需要命令行工具
        --disable-ffplay \
        --disable-ffprobe \
        --enable-neon \                          # arm 平台启用 NEON 加速
        --enable-hwaccels \
        --enable-jni \                           # 启用 JNI 支持
        --enable-mediacodec \                    # 启用 MediaCodec 硬解码
        --enable-decoder=h264 \
        --enable-decoder=hevc \
        --enable-decoder=aac \
        --enable-demuxer=flv \
        --enable-muxer=mp4 \
        --enable-protocol=file \
        --enable-protocol=http \
        --enable-protocol=rtmp

    make -j$(nproc)
    make install
}

# 编译多个 ABI
build_one arm64-v8a
build_one armeabi-v7a
```

### 4.3 集成到 Android 项目

```
app/
└── src/main/
    └── jniLibs/
        ├── arm64-v8a/
        │   ├── libavcodec.so
        │   ├── libavformat.so
        │   ├── libavutil.so
        │   ├── libswresample.so
        │   └── libswscale.so
        └── armeabi-v7a/
            ├── libavcodec.so
            ├── libavformat.so
            ├── libavutil.so
            ├── libswresample.so
            └── libswscale.so
```

**加载顺序注意：** FFmpeg 各库之间有依赖关系，必须按正确顺序加载：

```kotlin
object FFmpegLoader {
    fun init() {
        System.loadLibrary("avutil")       // 基础工具库，无依赖
        System.loadLibrary("swresample")   // 依赖 avutil
        System.loadLibrary("swscale")      // 依赖 avutil
        System.loadLibrary("avcodec")      // 依赖 avutil
        System.loadLibrary("avformat")     // 依赖 avcodec、avutil
    }
}
```

### 4.4 常见踩坑

| 问题 | 原因 | 解决 |
|:---|:---|:---|
| `libavcodec.so: has text relocations` | 旧版 NDK 对 arm 的 text relocation 更严格 | 启用 `-fPIC` 编译选项 |
| FFmpeg so 体积 40MB+ | 编译了所有编解码器 | 只启用业务需要的 `--enable-decoder` |
| 某些设备硬解码失败 | MediaCodec 的 color format 不匹配 | 添加 CSC（色彩空间转换）检查 |
| `dlopen failed: cannot locate symbol` | 加载顺序不对或缺少依赖 | 用 `readelf -d` 检查 NEEDED 依赖链 |

---

## 5. 面试速记卡

| 考点 | 一句话回答 |
|:---|:---|
| **CMake 优势** | 跨平台、IDE 集成好、Google 官方推荐 |
| **so 搜索路径** | 先 ClassLoader 的应用目录，再 vendor→system |
| **ABI 选择** | arm64-v8a 必选（Google Play 强制），armeabi-v7a 做兼容 |
| **Native 线程 JNI** | `AttachCurrentThread` 绑定后获取 JNIEnv，线程隔离不可跨线程传递 |
| **崩溃分析三板斧** | ndk-stack 还原堆栈 → addr2line 定位行号 → tombstone 分析信号 |
| **STL 选择** | 单 so 用 c++_static，多 so 一定要 c++_shared |
| **FFmpeg 集成** | 交叉编译 → jniLibs → 按依赖顺序 loadLibrary |

---

## 6. 延伸阅读

- [Android NDK 官方文档](https://developer.android.com/ndk)
- [CMake NDK 构建指南](https://developer.android.com/studio/projects/configure-cmake)
- [Android ABI 管理官方说明](https://developer.android.com/ndk/guides/abis)
- [FFmpeg Android 交叉编译 Wiki](https://trac.ffmpeg.org/wiki/CompilationGuide/Android)
