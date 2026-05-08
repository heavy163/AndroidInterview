# 03-PMS详解 — PackageManagerService 面试全攻略

---

## 目录

1. [面试高频问题](#1-面试高频问题)
2. [标准答案](#2-标准答案)
3. [核心原理深度剖析](#3-核心原理深度剖析)
4. [APK安装全流程（流程图）](#4-apk安装全流程图)
5. [源码分析：PMS构造函数](#5-源码分析pms构造函数)
6. [应用场景：Android 10+ Scoped Storage](#6-应用场景android-10-scoped-storage)

---

## 1. 面试高频问题

以下是PMS模块面试中最常被问到的6个核心问题：

### Q1: APK的完整安装流程是怎样的？

从用户点击安装到应用可启动，经历了 **拷贝→解析AndroidManifest→dex优化→权限授予→完成注册** 五个阶段。每个阶段涉及不同系统服务的协同工作，是整个PMS最核心的流程。面试官通常期望你画出流程图并描述每个阶段的关键操作。

### Q2: PMS中的PackageManager和PackageInstaller有什么区别和联系？

这是一个经典的对比题。`PackageManager` 是面向开发者的 **查询API**（只读），提供 `getPackageInfo()`、`queryIntentActivities()` 等方法；而 `PackageInstaller` 是面向应用的 **安装API**（写入），提供 `createSession()` 实现分包安装。两者都是PMS对外的Binder接口，底层都调用PMS内部方法。

### Q3: AndroidManifest.xml的解析过程是怎样的？PackageParser做了哪些事？

PackageParser 使用 **SAX/XMLPullParser** 解析 APK 中的 AndroidManifest.xml（二进制AXML格式），生成 `Package` 对象。解析内容包括四大组件声明、权限声明、`<uses-sdk>` 版本信息、`<uses-feature>` 硬件特性等。解析结果缓存在 `/data/system/package_cache/` 目录。

### Q4: Android的权限管理机制是怎样的？运行时权限的grant/revoke流程？

Android 6.0+ 将权限分为 **正常权限**（安装时授予）和 **危险权限**（运行时动态请求）。grant流程：App调用 `requestPermissions()` → AMS → PMS 检查权限保护级别 → 弹出系统对话框 → 用户确认后PMS将授权写入 `/data/system/packages.xml`。revoke可在"设置"中手动操作或通过 `revokeRuntimePermission()` API。

### Q5: APK签名校验机制是怎样的？V1/V2/V3 Scheme的核心区别？

- **V1 (JAR签名)**：基于 `META-INF/MANIFEST.MF` → `CERT.SF` → `CERT.RSA` 链式签名，逐文件校验
- **V2 (APK Signature Scheme v2)**：对整个APK ZIP文件进行签名，签名信息写入APK Signing Block（位于ZIP Central Directory之前），校验速度快且安全性更高
- **V3 (APK Signature Scheme v3)**：在V2基础上支持 **密钥轮转**（Key Rotation），允许应用更新签名证书而不丢失身份

### Q6: 应用的data目录和code目录结构是怎样的？分别存放什么内容？

- **code目录**（`/data/app/<包名>-<随机后缀>/`）：存放APK文件本身（base.apk）和拆分APK（split_*.apk），以及 `oat/` 目录下的优化产物
- **data目录**（`/data/data/<包名>/`）：应用私有数据，包括 `databases/`（SQLite数据库）、`shared_prefs/`（SharedPreferences）、`files/`（内部存储）、`cache/`（缓存）等

---

## 2. 标准答案（含安装流程图）

### 2.1 APK安装流程详解

APK安装是Android系统最复杂的跨进程协作流程之一，涉及 **PackageInstaller**（前端）、**PackageManagerService**（核心逻辑）、**installd**（文件操作守护进程）、**dex2oat**（DEX编译器）等多个组件的协同。

#### 第一阶段：拷贝APK到目标目录

```
用户点击安装
    │
    ▼
PackageInstallerActivity（安装确认界面）
    │
    ▼
PackageInstaller.Session::commit()
    │  └─ 通过Binder调用PMS
    ▼
PMS::commitPackageInternal()
    │
    ▼
installd::copyApk()
    └─ 将APK从源路径拷贝到 /data/app/<pkg>-<hash>/
       如果是从应用商店下载，可能从 /data/local/tmp/ 拷贝
```

**关键点**：installd 是运行在 root 权限下的native守护进程，负责所有文件I/O操作，PMS本身不直接操作文件系统（权限隔离）。

#### 第二阶段：解析AndroidManifest.xml

```
PMS::scanPackageTracedLI()
    │
    ▼
PackageParser::parsePackage()
    │
    ├── 1. 解析AndroidManifest.xml（二进制AXML）
    │      └─ 使用 AssetManager 读取，内部用 XmlBlock
    ├── 2. 提取 <manifest> 标签：package属性、sharedUserId、versionCode/versionName
    ├── 3. 提取 <application> 标签：主题、图标、进程名、allowBackup等
    ├── 4. 遍历四大组件：
    │      ├── <activity>   → PackageParser.ActivityIntentInfo
    │      ├── <service>    → PackageParser.ServiceIntentInfo
    │      ├── <receiver>   → PackageParser.ActivityIntentInfo（继承自同样的基类）
    │      └── <provider>   → PackageParser.ProviderIntentInfo
    ├── 5. 解析 <uses-permission> → 记录请求的权限列表
    ├── 6. 解析 <permission>     → 应用自定义权限
    ├── 7. 解析 <uses-feature>   → 硬件特性需求（如摄像头、GPS）
    ├── 8. 解析 <uses-library>   → 共享库依赖（如org.apache.http.legacy）
    └── 9. 构建 IntentFilter 映射表 → 用于后续 Intent 解析
    │
    ▼
生成 PackageParser.Package 对象
    └─ 包含上述所有解析信息的Java对象
    └─ 缓存在 mPackages 和 Settings 中
```

**重要细节**：
- AndroidManifest 在APK内是编译后的 **二进制AXML格式**，不是纯文本XML。这是为了节省空间和加快解析速度。
- 解析结果会被序列化缓存到 `/data/system/package_cache/<pkg>-<version>.cache`，下次开机直接反序列化，避免重复解析。

#### 第三阶段：DEX优化（dex2oat）

```
PMS::performDexOpt()
    │
    ▼
通过 installd 调用 dex2oat
    │
    ├── 输入：APK中的 classes.dex / classes2.dex / ...
    ├── 输出：/data/app/<pkg>/oat/<arch>/base.odex / base.vdex / base.art
    │
    ├── AOT编译模式：
    │   ├── speed-profile    (推荐)：基于云配置文件，热点函数完全编译
    │   ├── speed            (不推荐)：全量AOT，占用空间大
    │   ├── verify           (默认)：仅验证，运行时JIT编译
    │   └── everything       (废弃)：全量编译所有代码
    │
    └── Android 7.0+ JIT/AOT混合模式：
        ├── 首次安装：仅verify模式，快速完成
        ├── 运行时：JIT编译热点代码
        └── 充电+空闲时：根据JIT profile重新AOT编译（BackgroundDexOptService）
```

**.odex / .vdex / .art 的区别**：
- `.vdex`：包含验证后的DEX文件（未压缩），加速类加载
- `.odex`：AOT编译后的native代码（.so格式），包含已编译方法
- `.art`：ART内部使用的辅助数据（如类初始化信息、image）

#### 第四阶段：权限授予与设置写入

```
PMS::grantPermissionsLPw()
    │
    ├── 正常权限（Normal）：直接授予，无需用户确认
    ├── 危险权限（Dangerous）：
    │   ├── targetSdkVersion < 23：安装时一次性授予（兼容模式）
    │   └── targetSdkVersion ≥ 23：安装时不授予，等待运行时请求
    ├── 签名权限（Signature）：只有当请求方与声明方签名相同时才授予
    └── 签名或系统权限（SignatureOrSystem）：签名相同或系统应用均可授予
    │
    ▼
Settings::writeLPr()
    └─ 将应用信息写入 /data/system/packages.xml
    └─ 内容包括：包名、路径、权限、组件、签名指纹等
```

#### 第五阶段：安装完成与广播发送

```
PMS::commitPackageInternal() 完成
    │
    ├── 更新 mPackages 内存映射
    ├── 更新 mSettings（标记 Dirty）
    ├── 写入 packages.xml
    ├── 发送 Intent.ACTION_PACKAGE_ADDED 广播
    └── 通知 launcher 刷新图标（如有 <intent-filter> 包含 LAUNCHER 的 Activity）
```

### 2.2 安装流程总览（ASCII流程图）

```
┌─────────────────────────────────────────────────────────────────────┐
│                        APK 安装全流程                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  [用户点击APK]                                                       │
│       │                                                              │
│       ▼                                                              │
│  ┌──────────────────┐                                                │
│  │ ① 拷贝阶段        │  installd: 拷贝APK到 /data/app/<pkg>-hash/   │
│  │   copyApk()      │  校验磁盘空间，设置SELinux上下文               │
│  └────────┬─────────┘                                                │
│           ▼                                                          │
│  ┌──────────────────┐                                                │
│  │ ② 解析阶段        │  PackageParser: 解析AndroidManifest.xml       │
│  │   parsePackage() │  提取四大组件/权限/IntentFilter等 → Package    │
│  └────────┬─────────┘                                                │
│           ▼                                                          │
│  ┌──────────────────┐                                                │
│  │ ③ 签名校验        │  verifySignatures():                          │
│  │   verifySig()    │  V1(META-INF链) → V2(Signing Block) → V3      │
│  └────────┬─────────┘                                                │
│           ▼                                                          │
│  ┌──────────────────┐                                                │
│  │ ④ DEX优化         │  dex2oat: classes.dex → .odex/.vdex          │
│  │   dex2oat        │  speed-profile / verify 模式可选              │
│  └────────┬─────────┘                                                │
│           ▼                                                          │
│  ┌──────────────────┐                                                │
│  │ ⑤ 权限授予        │  grantPermissionsLPw():                       │
│  │   grantPerm()    │  Normal直接给 / Dangerous等运行时              │
│  └────────┬─────────┘                                                │
│           ▼                                                          │
│  ┌──────────────────┐                                                │
│  │ ⑥ 注册完成        │  Settings.writeLPr() → packages.xml           │
│  │   commit()       │  发送ACTION_PACKAGE_ADDED广播                  │
│  └──────────────────┘                                                │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. 核心原理深度剖析

### 3.1 PackageManagerService — 扫描与初始化

PMS是系统启动过程中最早初始化的核心服务之一，在 `SystemServer.main()` → `startBootstrapServices()` 阶段启动。

**扫描目录体系**（按优先级）：

| 扫描目录 | 用途 | 优先级 |
|---------|------|--------|
| `/system/app/` | 系统应用（不可卸载） | 高（先扫描） |
| `/system/priv-app/` | 特权系统应用（有signatureOrSystem权限） | 高 |
| `/vendor/app/` | 厂商定制应用 | 中 |
| `/product/app/` | 产品分区应用（Android 9+） | 中 |
| `/data/app/` | 用户安装的第三方应用 | 低（后扫描） |
| `/data/priv-app/` | 用户安装的特权应用 | 低 |

**扫描流程**（`PMS::scanDirTracedLI`）：

```java
// 简化版扫描逻辑
private void scanDirTracedLI(File scanDir, int parseFlags, int scanFlags, long currentTime) {
    // 1. 列出目录下所有APK文件和子目录
    File[] files = scanDir.listFiles();
    
    for (File file : files) {
        // 2. 每个APK调用 scanPackageTracedLI
        PackageParser.Package pkg = scanPackageTracedLI(file, parseFlags, scanFlags, currentTime);
        
        // 3. 添加到内存映射
        mPackages.put(pkg.packageName, pkg);
        
        // 4. 记录Settings
        mSettings.insertPackageSettingLPw(pkg, null);
    }
}
```

**关键数据结构**：

- `mPackages`（HashMap）：包名 → Package 对象，内存中的核心索引
- `mSettings`（Settings）：持久化存储，对应 `/data/system/packages.xml`
- `mActivities` / `mServices` / `mReceivers` / `mProviders`：组件级别的IntentFilter索引，用于快速Intent解析
- `mInstaller`（Installer）：与 installd 通信的代理对象

### 3.2 PackageParser — AndroidManifest解析引擎

PackageParser 是PMS内部最复杂的解析器之一，负责将APK中的二进制AXML转换为结构化的 `Package` 对象。

**解析核心流程**：

```
PackageParser::parseMonolithicPackage(File apkFile, int flags)
    │
    ├── 1. 获取 AssetManager 实例，指向APK的ZIP内部
    │      AssetManager am = new AssetManager();
    │      am.addAssetPath(apkFile.getAbsolutePath());
    │
    ├── 2. 读取 AndroidManifest.xml（二进制AXML）
    │      XmlResourceParser parser = am.openXmlResourceParser("AndroidManifest.xml");
    │
    ├── 3. 解析各标签（switch-case遍历XML事件流）
    │      ├── TAG_MANIFEST      → parseBaseApplication()
    │      ├── TAG_APPLICATION   → parseBaseApplication()
    │      │   ├── TAG_ACTIVITY      → parseActivity()
    │      │   ├── TAG_SERVICE       → parseService()
    │      │   ├── TAG_RECEIVER      → parseActivity()  // 共享基类
    │      │   └── TAG_PROVIDER      → parseProvider()
    │      ├── TAG_USES_PERMISSION   → 记录到 Package.requestedPermissions
    │      ├── TAG_USES_FEATURE      → 记录到 Package.reqFeatures
    │      └── TAG_USES_SDK          → 记录 minSdkVersion / targetSdkVersion
    │
    ├── 4. 构建 Package 对象
    │      Package pkg = new Package(packageName);
    │      pkg.applicationInfo = ...;
    │      pkg.activities = ...;
    │      pkg.services = ...;
    │      pkg.receivers = ...;
    │      pkg.providers = ...;
    │      pkg.permissions = ...;
    │      pkg.mSharedUserId = ...;
    │
    └── 5. 返回 Package 对象
```

**缓存机制**：解析后的 Package 对象会被序列化写入 `/data/system/package_cache/`，下次扫描时如果APK未更新且缓存有效，直接从缓存反序列化，跳过XML解析。

### 3.3 dex2oat — DEX到OAT的AOT编译

dex2oat 是ART运行时的核心编译工具，将DEX字节码转换为native机器码。

**编译模式对比**：

| 模式 | 编译时机 | 产物 | 启动速度 | 空间占用 |
|------|---------|------|---------|---------|
| verify | 安装时（默认） | .vdex | 慢（需运行时JIT） | 最小 |
| speed-profile | 安装时（推荐） | .odex(部分) + .vdex | 快（热点已编译） | 适中 |
| speed | 安装时 | .odex(全部) | 最快 | 很大 |
| JIT Profile Guided | 充电空闲时 | .odex(补充) | 逐步优化 | 动态增长 |

**编译流程**：

```
dex2oat --dex-file=base.apk        \
        --oat-file=base.odex       \
        --compiler-filter=speed-profile \
        --profile-file=primary.prof  \    ← 云端下发的Profile
        --class-loader-context=PCL   \    ← 类加载器上下文（Android N+）
        --boot-image=/system/framework/boot.art  ← Boot Image
```

**关键概念 — Profile Guided Optimization (PGO)**：
- Google Play 收集用户运行时的热点方法信息
- 生成 `primary.prof` 配置文件随APK下发
- dex2oat 根据 Profile 只编译真正热点的代码
- 相比全量编译（speed），空间节省60%+，性能损失<5%

### 3.4 签名校验 — V1 / V2 / V3 Scheme

APK签名校验是安全保障的核心，确保APK未被篡改且来源可信。

#### V1 — JAR签名（基于文件）

```
APK内部结构（V1签名后）：
├── META-INF/
│   ├── MANIFEST.MF      ← 列出所有文件的SHA-256摘要（Base64编码）
│   ├── CERT.SF          ← 对MANIFEST.MF整体的SHA-256摘要 + 各条目摘要
│   └── CERT.RSA         ← 对CERT.SF的签名（PKCS#7格式，含证书链）
├── classes.dex
├── res/
├── resources.arsc
└── AndroidManifest.xml
```

**校验链**：逐文件计算SHA-256 → 比对MANIFEST.MF条目 → MANIFEST.MF整体摘要比对CERT.SF → CERT.SF签名验证CERT.RSA

**缺陷**：校验慢（需遍历所有文件），APK内某些文件（如ZIP注释）不受保护。

#### V2 — APK Signature Scheme v2（整包签名）

```
APK结构（V2签名后）：
┌────────────────────────────────────┐
│  ZIP File Content                  │  ← 偏移 0 开始
│  (classes.dex, res/, etc.)         │
├────────────────────────────────────┤
│  APK Signing Block                │  ← 新增：包含签名信息
│  ├── ID: 0x7109871a (V2签名块)     │
│  │   └── 对ZIP Content的摘要+签名   │
│  └── 其他ID块（填充/第三方）        │
├────────────────────────────────────┤
│  ZIP Central Directory             │  ← 末尾
├────────────────────────────────────┤
│  ZIP End of Central Directory      │  ← 最后
│  (包含Signing Block的偏移和大小)     │
└────────────────────────────────────┘
```

**优势**：只需一次计算（对ZIP Content的整体摘要），校验极快；整个APK除Signing Block外都受保护。

#### V3 — APK Signature Scheme v3（密钥轮转）

```
V3签名块结构（在APK Signing Block中）：
┌──────────────────────────────────────┐
│  Signer Block (当前签名证书)          │
│  ├── signed-data: 对APK的哈希         │
│  ├── signatures: 当前证书签名         │
│  └── public-key: 当前证书公钥         │
├──────────────────────────────────────┤
│  Proof-of-Rotation Block（轮转证明）  │  ← V3新增
│  ├── previous-signer: 旧证书信息      │
│  ├── signature: 新证书对旧证书的签名   │
│  └── ... (可链式追溯到原始签名证书)    │
└──────────────────────────────────────┘
```

**核心能力**：应用发布者可以在保留应用身份的前提下更换签名证书。旧证书签名新证书，形成信任链。用户在Play商店更新应用时无需卸载重装。

### 3.5 Settings类 — 持久化存储

Settings 是PMS的持久化存储单元，管理所有已安装应用信息的读写。

**核心文件**：

| 文件 | 路径 | 内容 |
|------|------|------|
| packages.xml | `/data/system/packages.xml` | 所有已安装应用的完整信息 |
| packages-backup.xml | `/data/system/packages-backup.xml` | packages.xml的备份 |
| packages.list | `/data/system/packages.list` | 包名 → UID → data目录 的映射（纯文本，格式简单，用于installd快速查找） |
| runtime-permissions.xml | `/data/system/users/<userId>/runtime-permissions.xml` | 每个用户的运行时权限授权状态 |

**packages.xml 条目示例**（简化）：

```xml
<package name="com.example.app"
         codePath="/data/app/com.example.app-xxxx/base.apk"
         nativeLibraryPath="/data/app/com.example.app-xxxx/lib"
         userId="10123"
         flags="0"
         ft="16b9a3c0000"
         it="16b9a3c0000"
         ut="16b9a3c0000"
         version="1">
    <sigs count="1">
        <cert index="0" key="308204a8..."/>  ← 签名证书的DER编码
    </sigs>
    <perms>
        <item name="android.permission.INTERNET" granted="true" flags="0"/>
        <item name="android.permission.CAMERA" granted="false" flags="0"/>
    </perms>
    <proper-signing-keyset identifier="10"/>
</package>
```

**Settings 内存结构**：

```java
final class Settings {
    // 包名 → PackageSetting（内存中的包信息，对应packages.xml中的<package>）
    final ArrayMap<String, PackageSetting> mPackages;
    
    // SharedUserId → SharedUserSetting（共享UID的应用，如system UID）
    final ArrayMap<String, SharedUserSetting> mSharedUsers;
    
    // UserHandle → 该用户下已安装的应用列表
    final SparseArray<...> mUserStates;
    
    // 标记是否有未写入磁盘的更改
    boolean mPackagesDirty;
}
```

---

## 4. APK安装全流程（详细流程图）

```
                            ┌─────────────────────┐
                            │   用户点击安装APK     │
                            └──────────┬──────────┘
                                       │
                                       ▼
                            ┌─────────────────────┐
                            │ PackageInstaller    │  系统安装器UI
                            │ Activity (前端)      │  - 权限提示
                            │                     │  - 确认安装/取消
                            └──────────┬──────────┘
                                       │ Intent / Binder
                                       ▼
                   ┌───────────────────────────────────────┐
                   │        PackageManagerService          │
                   │                                       │
                   │  ① commitPackageInternal()            │
                   │     ├── 参数校验（包名合法性、重复等）    │
                   │     └── 调用 installd.copyApk()       │
                   │                                       │
                   │  ② scanPackageTracedLI()              │
                   │     ├── PackageParser.parsePackage()  │
                   │     │   ├── 解析 AndroidManifest.xml  │
                   │     │   ├── 提取组件/权限/IntentFilter │
                   │     │   └── 生成 Package 对象         │
                   │     │                                 │
                   │     ├── verifySignaturesLP()          │
                   │     │   ├── V1: META-INF/* 链式校验   │
                   │     │   ├── V2: APK Signing Block校验 │
                   │     │   └── V3: Key Rotation验证      │
                   │     │                                 │
                   │     ├── 收集native库                   │
                   │     │   └── 拷贝 .so 到 /data/app/    │
                   │     │                                 │
                   │     ├── performDexOpt()               │
                   │     │   └── dex2oat: DEX→OAT         │
                   │     │       ├── 模式: speed-profile   │
                   │     │       └── 产物: .odex/.vdex     │
                   │     │                                 │
                   │     ├── grantPermissionsLPw()         │
                   │     │   ├── Normal → 直接授予         │
                   │     │   ├── Dangerous + targetSdk<23  │
                   │     │   │   └── 安装时授予            │
                   │     │   └── Dangerous + targetSdk≥23  │
                   │     │       └── 仅记录，等待运行时     │
                   │     │                                 │
                   │     └── Settings.writeLPr()           │
                   │         ├── 写入 packages.xml         │
                   │         └── 写入 packages.list        │
                   │                                       │
                   │  ③ 更新内存索引                       │
                   │     ├── mPackages.put(pkgName, pkg)   │
                   │     ├── 更新组件IntentFilter索引       │
                   │     └── 通知其他系统服务（如Launcher）  │
                   │                                       │
                   │  ④ 发送广播                           │
                   │     └── ACTION_PACKAGE_ADDED          │
                   │         ├── Launcher→添加桌面图标     │
                   │         └── 其他应用→收到安装通知      │
                   └───────────────────────────────────────┘
                                       │
                                       ▼
                            ┌─────────────────────┐
                            │      安装完成        │
                            │  应用可正常启动       │
                            └─────────────────────┘


═══════════════════════════════════════════════════════
             权限运行时授予流程（补充）
═══════════════════════════════════════════════════════

  [App调用 requestPermissions()]
              │
              ▼
  [AMS → PMS: grantRuntimePermission()]
              │
              ├── 检查权限保护级别是否为 "dangerous"
              ├── 检查用户是否已授权
              ├── 弹出系统权限对话框（用户可见）
              │
              ▼
  ┌─────[用户选择]─────┐
  │                    │
  [允许]              [拒绝]
  │                    │
  ▼                    ▼
  PMS记录授权        PMS记录拒绝
  │                    │
  ▼                    ▼
  写入                  写入
  runtime-             runtime-
  permissions.xml      permissions.xml
  │                    │
  ▼                    ▼
  返回                  返回
  PERMISSION_GRANTED   PERMISSION_DENIED
```

---

## 5. 源码分析：PMS构造函数与scanDirTracedLI

### 5.1 PMS构造函数的关键初始化

PMS构造函数位于 `frameworks/base/services/core/java/com/android/server/pm/PackageManagerService.java`（Android 9+ 细分为多个文件，核心逻辑在 `PackageManagerService.java` 和 `ScanPackageUtils.java`）。

**构造函数核心步骤**（简化）：

```java
public PackageManagerService(Context context, Installer installer, ...) {
    // ========== 第一阶段：基础设施初始化 ==========
    
    // 1. 初始化Settings（读取已有的packages.xml）
    mSettings = new Settings(Environment.getDataDirectory());
    mSettings.addSharedUserLPw("android.uid.system", Process.SYSTEM_UID, ...);
    mSettings.addSharedUserLPw("android.uid.phone", Process.PHONE_UID, ...);
    // ... 添加其他系统 SharedUser
    
    // 2. 读取已安装应用列表
    mFirstBoot = !mSettings.readLPw(this, ...);  // 首次启动
    
    // 3. 初始化各种缓存和数据结构
    mPackages = new ArrayMap<>();
    mActivities = new ActivityIntentResolver();
    mServices = new ServiceIntentResolver();
    mReceivers = new ActivityIntentResolver();
    mProviders = new ProviderIntentResolver();
    
    // ========== 第二阶段：扫描APK目录 ==========
    
    // 4. 扫描系统分区（优先级从高到低）
    File systemAppDir = new File(Environment.getRootDirectory(), "app");
    File systemPrivAppDir = new File(Environment.getRootDirectory(), "priv-app");
    File vendorAppDir = new File("/vendor/app");
    File oemAppDir = new File("/oem/app");
    
    scanDirTracedLI(systemAppDir, ...);
    scanDirTracedLI(systemPrivAppDir, ...);
    scanDirTracedLI(vendorAppDir, ...);
    scanDirTracedLI(oemAppDir, ...);
    
    // 5. 扫描数据分区（用户安装的应用和更新）
    File dataAppDir = new File(Environment.getDataDirectory(), "app");
    scanDirTracedLI(dataAppDir, ...);
    
    // ========== 第三阶段：收尾工作 ==========
    
    // 6. 更新权限
    updatePermissionsLPw(null, null, UPDATE_PERMISSIONS_ALL);
    
    // 7. 写入最终状态
    mSettings.writeLPr();
    
    // 8. 启动后台DexOpt
    mHandler.post(() -> {
        performBootDexOpt();  // 检查是否有未优化的APK
    });
}
```

### 5.2 scanDirTracedLI 详解

这是PMS最核心的扫描函数，负责遍历一个目录下的所有APK并解析注册。

```java
// 源码位置：frameworks/base/services/core/java/com/android/server/pm/PackageManagerService.java
private void scanDirTracedLI(File scanDir, int parseFlags, int scanFlags, long currentTime) {
    Trace.traceBegin(TRACE_TAG_PACKAGE_MANAGER, "scanDir [" + scanDir.getAbsolutePath() + "]");
    try {
        scanDirLI(scanDir, parseFlags, scanFlags, currentTime);
    } finally {
        Trace.traceEnd(TRACE_TAG_PACKAGE_MANAGER);
    }
}

private void scanDirLI(File scanDir, int parseFlags, int scanFlags, long currentTime) {
    // 1. 获取目录下的所有文件（APK文件或子目录）
    final File[] files = scanDir.listFiles();
    if (files == null) {
        Log.w(TAG, "No files in app dir " + scanDir);
        return;
    }
    
    // 2. 并行扫描优化（Android 8.0+）
    //    使用线程池并行解析多个APK，加速开机
    ParallelPackageParser parallelParser = new ParallelPackageParser(
        mSeparateProcesses, mOnlyCore, mMetrics, mCacheDir, 
        mParallelPackageParserCallback);
    
    // 3. 提交所有文件到解析队列
    for (File file : files) {
        final boolean isPackage = (parseFlags & ...) != 0 
            && isPackageFilename(file);
        if (!isPackage) {
            continue;  // 跳过非APK文件
        }
        parallelParser.submit(file, parseFlags);
    }
    
    // 4. 逐个处理解析结果
    for (int i = 0; i < fileCount; i++) {
        ParallelPackageParser.ParseResult parseResult = parallelParser.take();
        
        // 4.1 错误处理（损坏的APK、解析失败等）
        if (parseResult.throwable != null) {
            Log.w(TAG, "Failed to parse " + parseResult.scanFile, 
                  parseResult.throwable);
            // 删除损坏的APK
            mInstaller.rmPackageDir(parseResult.scanFile.getAbsolutePath());
            continue;
        }
        
        // 4.2 将解析出的 Package 对象注册到PMS
        if (parseResult.pkg != null) {
            scanPackageChildLI(parseResult.pkg, parseFlags, scanFlags, 
                              currentTime, null);
        }
    }
    
    parallelParser.close();
}

private PackageParser.Package scanPackageChildLI(PackageParser.Package pkg,
        int parseFlags, int scanFlags, long currentTime, UserHandle user) {
    
    // 1. 检查是否已存在（新旧版本比较）
    PackageSetting ps = mSettings.getPackageLPr(pkg.packageName);
    PackageSetting updatedPkg;
    
    if (ps != null) {
        // 已经安装过 → 这是更新！
        // 比较版本号，决定是否覆盖
        if (ps.versionCode <= pkg.mVersionCode) {
            updatedPkg = ps;
        } else {
            // 新版本号更低，不覆盖（降级安装）
            return null;
        }
    }
    
    // 2. 签名校验
    if (!verifySignaturesLP(...)) {
        Log.w(TAG, "Signature mismatch for " + pkg.packageName);
        return null;
    }
    
    // 3. 收集native库并拷贝
    NativeLibraryHelper.Handle handle = NativeLibraryHelper.Handle.create(pkg);
    int copyRet = NativeLibraryHelper.copyNativeBinaries(handle, ...);
    
    // 4. DEX优化
    performDexOpt(pkg, ...);
    
    // 5. 权限授予
    grantPermissionsLPw(pkg, ...);
    
    // 6. 注册到内存索引
    mPackages.put(pkg.packageName, pkg);
    mSettings.insertPackageSettingLPw(...);
    
    // 7. 注册组件IntentFilter
    for (PackageParser.Activity a : pkg.activities) {
        mActivities.addActivity(a, "activity");
    }
    // ... services, receivers, providers 同理
    
    return pkg;
}
```

**并行解析优化**（ParallelPackageParser）：

Android 8.0 引入了并行解析机制。在开机扫描大量APK时，使用线程池（通常4线程）并行调用 `PackageParser`，解析完的 `Package` 对象放入阻塞队列，主线程按序取出并执行后续的签名校验、DEX优化等必须串行的步骤。这种方式在典型设备（200+APK）上可将扫描时间缩短40%~50%。

---

## 6. 应用场景：Android 10+ Scoped Storage

### 6.1 Scoped Storage 概述

Android 10 (API 29) 引入了 **Scoped Storage（分区存储）**，从根本上改变了应用访问外部存储的方式。Android 11 (API 30) 强制所有应用适配。

**核心变化**：

```
Android 9 及之前                     Android 10+
─────────────────────────           ─────────────────────────
READ_EXTERNAL_STORAGE               READ_EXTERNAL_STORAGE
  └── 可访问整个 /sdcard/              └── 只能访问 MediaStore 中
      包括其他应用的私有文件               本应用创建的媒体文件
                                    └── 访问其他应用的文件需要
                                       MANAGE_EXTERNAL_STORAGE
                                       （Android 11+，需要特殊审批）
```

### 6.2 对应用私有目录的影响

PMS在管理应用目录时需要与Scoped Storage策略协调：

| 目录类型 | 路径 | 是否需要权限 | 特点 |
|---------|------|-------------|------|
| 应用私有目录 | `/data/data/<pkg>/` | 不需要 | 完全隔离，其他应用无法访问 |
| 应用外部私有目录 | `/sdcard/Android/data/<pkg>/` | 不需要（Android 10+） | 卸载时自动删除 |
| 应用外部媒体目录 | `/sdcard/Android/media/<pkg>/` | 不需要（Android 10+） | 存放媒体文件 |
| 共享媒体目录 | `/sdcard/Pictures/`, `/sdcard/Music/` | 需要READ/WRITE权限 | 所有应用共享 |
| 共享下载目录 | `/sdcard/Download/` | 需要权限 | 系统下载管理器使用 |

### 6.3 PMS与Scoped Storage的交互

**1. 应用数据清理**：

```
PMS::clearApplicationUserData(packageName)
    │
    ├── 清除 /data/data/<pkg>/     ← 传统私有目录
    └── 清除 /sdcard/Android/data/<pkg>/  ← Scoped Storage下也自动清除
    └── （媒体目录中的文件不会被清除，因为它们是共享资源）
```

**2. 权限授予与Scoped Storage**：

```java
// PMS 在 grantPermissionsLPw() 中的处理
if (perm.name.equals(Manifest.permission.READ_EXTERNAL_STORAGE)) {
    if (targetSdkVersion >= Build.VERSION_CODES.Q) {
        // Android 10+：READ_EXTERNAL_STORAGE 变为受限权限
        // 应用默认只能访问自己的媒体文件
        // 需要 MANAGE_EXTERNAL_STORAGE 才能访问所有文件
    }
}
```

**3. 应用私有目录权限调整**：

Android 10+ 中，PMS在创建应用目录时自动设置更严格的SELinux上下文和文件权限：

```
# Android 9: 其他应用可以遍历 /data/data/ 下的目录
drwx------  u0_a123  u0_a123  com.example.app

# Android 10+: 权限更严格，SELinux 策略增强
drwx------  u0_a123  u0_a123  com.example.app
# SELinux: app_data_file 类型，跨应用访问默认deny
```

### 6.4 实战建议

**面试时的满分回答**：

> "Android 10引入Scoped Storage后，PMS管理的应用私有目录（`/data/data/<pkg>/`和外部私有目录`/sdcard/Android/data/<pkg>/`）仍然是完全隔离的，不需要任何权限即可访问。但在分配`READ_EXTERNAL_STORAGE`权限时，PMS会根据`targetSdkVersion`判断：如果≥29，该权限实际上只授予了对MediaStore的访问能力，而非整个外部存储。应用卸载时，PMS通过`installd`自动清理私有目录，但共享媒体目录中的文件不会被清理，这是为了避免误删用户数据。"

---

## 总结

PMS 是Android Framework中最庞大、最复杂的系统服务之一，掌握它需要理解以下知识链路：

```
APK文件
  → PackageParser（解析Manifest）
    → Settings（持久化）
      → dex2oat（编译优化）
        → 签名校验（安全保障）
          → 权限管理（访问控制）
            → 目录结构（存储管理）
```

在面试中，除了要能清晰描述每个环节的实现细节，更要能将这些知识点串联起来，展现你对Android系统架构的完整理解。建议重点掌握APK安装流程、签名机制演进、DEX编译模式以及权限管理这四个核心方向。

---

> **参考源码路径**（AOSP）：
> - PMS主文件：`frameworks/base/services/core/java/com/android/server/pm/PackageManagerService.java`
> - PackageParser：`frameworks/base/core/java/android/content/pm/PackageParser.java`
> - Settings：`frameworks/base/services/core/java/com/android/server/pm/Settings.java`
> - installd：`frameworks/native/cmds/installd/`
> - dex2oat：`art/dex2oat/`
> - 签名校验：`frameworks/base/core/java/android/util/apk/ApkSignatureSchemeV2Verifier.java` / `V3Verifier`

---

*文档生成时间：2026年5月 | 适用版本：Android 8.0 ~ Android 14*
