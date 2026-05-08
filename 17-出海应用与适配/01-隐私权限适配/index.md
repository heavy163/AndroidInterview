# 隐私权限适配 — 面试精讲（≥2200字）

> 从 Android 10 到 Android 14，Google 对隐私权限的管控逐年收紧。出海应用更需同时满足 GDPR 等国际合规要求。本文按六层递进结构组织，覆盖面试高频考点与实战完整路径。

---

## 第一层：核心机制面试必问

### 1.1 Android 10+ Scoped Storage（分区存储）

**共享存储（Shared Storage）**：Android 10 引入 Scoped Storage，应用不再能通过 `READ_EXTERNAL_STORAGE` / `WRITE_EXTERNAL_STORAGE` 随意访问外部存储上的所有文件。共享存储通过 MediaStore API 访问图片、音频、视频，应用只能看到自己贡献的媒体文件以及用户明确授权的文件。

- **`MediaStore.Images` / `Audio` / `Video` / `Downloads`**：四类集合，分别对应不同的媒体类型。查询时必须使用 `ContentResolver.query()`，返回的是经过过滤的游标。

**应用私有目录（App-specific Directory）**：路径为 `/Android/data/<package>/files/` 和 `/Android/data/<package>/cache/`，应用无需任何权限即可读写。Android 11 起，其他应用即使拥有 `MANAGE_EXTERNAL_STORAGE` 也无法访问你的私有目录（除非 Root/ADB）。

**SAF（Storage Access Framework）**：通过 `Intent.ACTION_OPEN_DOCUMENT` / `ACTION_CREATE_DOCUMENT` 启动系统文件选择器，用户主动选择文件后应用获得 URI 权限。这是 Scoped Storage 下访问非媒体文件（如 PDF、文档）的推荐方式。关键点：

- 获得的 `Uri` 通过 `takePersistableUriPermission()` 可跨重启保持。
- `DocumentsContract` 提供完整的增删改查能力。

**面试追问**：Android 10 提供了 `requestLegacyExternalStorage` 临时豁免标志；Android 11 强制开启 Scoped Storage，该标志失效。若 targetSdk=29 但运行在 Android 11 设备上，系统仍忽略豁免。

### 1.2 运行时权限最佳实践

**核心流程**：`checkSelfPermission()` → `requestPermissions()` → `onRequestPermissionsResult()`。

**`shouldShowRequestPermissionRationale` 的精准用法**：

- 用户**首次拒绝**（未勾选"不再询问"）→ 返回 `true`，此时应展示解释弹窗，说明权限的必要性。
- 用户**拒绝并勾选"不再询问"** → 返回 `false`，此时 `requestPermissions()` 会直接回调拒绝且不再弹系统对话框。应引导用户前往「设置」页面手动授予。
- 用户**首次请求**或**已授权** → 返回 `false`。

**最佳实践代码模式**：

```kotlin
fun requestPermission(activity: Activity, permission: String, requestCode: Int) {
    when {
        // 已授权
        ContextCompat.checkSelfPermission(activity, permission) == PackageManager.PERMISSION_GRANTED -> {
            onPermissionGranted()
        }
        // 被拒绝但可展示解释
        activity.shouldShowRequestPermissionRationale(permission) -> {
            showRationaleDialog {
                ActivityCompat.requestPermissions(activity, arrayOf(permission), requestCode)
            }
        }
        // 首次请求或"不再询问"——直接请求
        else -> {
            ActivityCompat.requestPermissions(activity, arrayOf(permission), requestCode)
        }
    }
}
```

### 1.3 GDPR 合规三大支柱

出海欧盟市场必须满足 GDPR（General Data Protection Regulation）：

1. **同意弹窗（Consent Dialog）**：必须在收集任何个人数据**之前**展示。需列出数据用途、第三方 SDK（如 Firebase、Adjust）、用户权利。使用 Google 的 UMP SDK（User Messaging Platform）实现标准化同意管理。

2. **数据删除（Right to Erasure）**：用户有权要求删除全部个人数据。技术上需实现：
   - 服务端 API：`DELETE /v1/user/data`，级联删除关联数据。
   - 客户端清空本地数据库、SharedPreferences、缓存。
   - 第三方 SDK 的数据删除——如 Adjust 的 `gdprForgetMe()`。

3. **跨境传输（Cross-border Transfer）**：数据从欧盟传输到非欧盟地区需满足 SCC（标准合同条款）或确保接收国有充分性认定。技术层面：使用欧盟区域的数据中心（如 GCP europe-west 区域），对传输中的数据加密（TLS 1.3）。

### 1.4 Android 14 部分媒体权限分拆

Android 14（API 34）将 `READ_EXTERNAL_STORAGE` 细化为：

- `READ_MEDIA_IMAGES`：仅访问图片。
- `READ_MEDIA_VIDEO`：仅访问视频。
- `READ_MEDIA_AUDIO`：仅访问音频。

**迁移要点**：若 targetSdk=34，必须使用以上细化权限取代 `READ_EXTERNAL_STORAGE`。同时支持同时请求多个权限。若应用只访问图片，不应再请求 `READ_EXTERNAL_STORAGE` 全权限——这在审查中会被拒绝上架。

---

## 第二层：进阶机制与 MediaStore 查询变化

### 2.1 MediaStore 查询 URI 演变

Android 10 前：
```kotlin
// 旧的查询方式，Android 10+ 返回空结果
val uri = MediaStore.Images.Media.EXTERNAL_CONTENT_URI
val projection = arrayOf(MediaStore.Images.Media.DATA) // DATA 列 Android 10+ 废弃
```

Android 10+ 正确方式：
```kotlin
val uri = MediaStore.Images.Media.getContentUri(MediaStore.VOLUME_EXTERNAL)
val projection = arrayOf(
    MediaStore.Images.Media._ID,
    MediaStore.Images.Media.DISPLAY_NAME,
    MediaStore.Images.Media.RELATIVE_PATH,  // 替代 DATA 列
    MediaStore.Images.Media.SIZE
)
```

**关键变化**：
- `DATA` 列在 Android 10+ 返回 `null`，必须用 `RELATIVE_PATH` + `DISPLAY_NAME` 组合定位。
- `MediaStore.VOLUME_EXTERNAL` vs `VOLUME_EXTERNAL_PRIMARY`：多存储设备场景需注意卷 ID。
- Android 11 新增 `MediaStore.Images.Media.IS_FAVORITE` 等字段。

### 2.2 Android 13 通知权限（POST_NOTIFICATIONS）

Android 13（API 33）引入运行时通知权限 `POST_NOTIFICATIONS`。此前通知是默认开启的。**面试高频**：

- **权限级别**：`dangerous`，属于运行时权限。
- **targetSdk=32 且运行在 Android 13**：系统会代为弹出默认通知权限请求（兼容行为）。
- **targetSdk=33**：必须自行调用 `requestPermissions()` 请求 `android.permission.POST_NOTIFICATIONS`。
- **被拒绝后**：`NotificationManager.areNotificationsEnabled()` 返回 `false`。可引导用户前往设置。
- **豁免场景**：媒体播放、前台服务等特定用例即使无通知权限也可弹出通知（需 Android 14+ 调整）。

**最佳实践**：在合适上下文（如用户完成关键操作后）请求通知权限，而非冷启动直接弹窗——提升授予率。

### 2.3 前后台位置权限细粒度

Android 10 起位置权限分拆为：
- `ACCESS_FINE_LOCATION` / `ACCESS_COARSE_LOCATION`：前台位置（仅应用使用期间）。
- `ACCESS_BACKGROUND_LOCATION`：后台位置，必须**单独请求**。

**Android 11+ 变化**：后台位置权限不能与前台权限一同请求，必须分步引导。用户先在设置中授予"仅在使用应用时允许"，然后应用在需要后台位置时显示额外弹窗引导用户改为"始终允许"。

**面试陷阱**：若 targetSdk=29 且 `ACCESS_BACKGROUND_LOCATION` 已在清单声明，可同时请求两个权限。targetSdk=30+ 则必须分步。

---

## 第三层：权限策略与用户信任

### 3.1 最小权限原则（Principle of Least Privilege）

Google Play 审核强制要求：
- 只声明**实际使用**的权限。
- 后台位置权限需提交使用说明，且必须在应用中显著展示位置访问的 UI 指示器。
- 敏感权限组（通话记录、短信）需通过 Google Play 敏感权限声明流程。

### 3.2 权限归组与声明策略

Android 将权限划分为多个权限组（Permission Groups）。同一组内的权限，用户授予一个后组内其他权限自动授予（如 Calendar 组包含 READ_CALENDAR 和 WRITE_CALENDAR）。但**不应依赖此行为**——始终显式检查和请求每一个需要的权限。

### 3.3 用户信任构建

- **运行时解释 UI**：在权限弹窗出现前展示半透明引导遮罩，解释权限用途。
- **增量授权**：按功能模块逐步请求，而非启动时一次性请求七八个权限。
- **设置中心的权限管理入口**：应用内提供聚合的权限状态面板，一目了然。

---

## 第四层：Android 权限演进时间线

```
┌─────────────────────────────────────────────────────────────────┐
│                 Android 隐私权限演进时间线                        │
├────────────┬────────────────────────────────────────────────────┤
│ Android 6  │ 运行时权限模型首次引入                                │
│   (API 23) │ · 危险权限必须动态请求                                │
│            │ · 用户可逐条授予/撤销                                 │
├────────────┼────────────────────────────────────────────────────┤
│ Android 10 │ Scoped Storage 首次引入                              │
│   (API 29) │ · requestLegacyExternalStorage 过渡标志              │
│            │ · 后台位置权限独立声明                                │
│            │ · 限制访问不可重置的设备标识符                         │
├────────────┼────────────────────────────────────────────────────┤
│ Android 11 │ Scoped Storage 强制执行                              │
│   (API 30) │ · MANAGE_EXTERNAL_STORAGE 需特殊审核                 │
│            │ · 权限自动重置（数月未使用自动撤销）                    │
│            │ · 后台位置权限分步请求                                │
│            │ · 包可见性限制（需 <queries> 声明）                    │
├────────────┼────────────────────────────────────────────────────┤
│ Android 12 │ 隐私仪表板 + 麦克风/相机指示器                        │
│   (API 31) │ · 近似位置选项（用户可授予模糊位置）                   │
│            │ · 剪贴板访问提示                                     │
│            │ · 休眠模式对权限的影响                                │
├────────────┼────────────────────────────────────────────────────┤
│ Android 13 │ 通知权限 + 细粒度媒体权限                             │
│   (API 33) │ · POST_NOTIFICATIONS 成为运行时权限                  │
│            │ · READ_MEDIA_IMAGES/VIDEO/AUDIO 分拆                │
│            │ · 后台使用身体传感器需新权限                          │
│            │ · 附近 Wi-Fi 设备权限独立                             │
├────────────┼────────────────────────────────────────────────────┤
│ Android 14 │ 部分媒体访问 + 照片选择器增强                         │
│   (API 34) │ · READ_MEDIA_IMAGES/VIDEO/AUDIO 替代                 │
│            │   READ_EXTERNAL_STORAGE                             │
│            │ · 照片选择器原生集成（无需权限即可选照片）              │
│            │ · 每应用数据使用量展示                                │
│            │ · 安全的全屏 Intent 通知限制                          │
└────────────┴────────────────────────────────────────────────────┘
```

---

## 第五层：targetSdk 28 → 34 完整适配路径

### 5.0 起点：targetSdk 28（Android 9）

现状反思：
- 全量 `READ/WRITE_EXTERNAL_STORAGE` 无限制读写。
- 无 Scoped Storage、无通知权限、无位置权限细粒度。
- 所有权限一次性在启动页请求。

### 5.1 Step 1：targetSdk 28 → 29（Android 10）

| 适配项 | 具体操作 |
|-------|---------|
| Scoped Storage 过渡 | 清单设置 `requestLegacyExternalStorage="true"`；评估所有文件 IO 路径，将非媒体文件迁移至 SAF 或应用私有目录 |
| 后台位置 | 清单新增 `<uses-permission android:name="android.permission.ACCESS_BACKGROUND_LOCATION"/>` |
| 设备 ID | 用 `MediaDrm` API 或 `AdvertisingIdClient` 替代 `Build.getSerial()` |
| 后台 Activity 启动限制 | 移除后台直接 `startActivity()`，改用 Notification 触发 |

### 5.2 Step 2：targetSdk 29 → 30（Android 11）

| 适配项 | 具体操作 |
|-------|---------|
| 强制执行 Scoped Storage | 移除 `requestLegacyExternalStorage` 或标记 false；所有文件访问改为 MediaStore/SAF/私有目录三选一 |
| 权限自动重置 | 在应用冷启动时重新检查关键权限，缺失则引导授权 |
| 包可见性 | 在 `AndroidManifest.xml` 中添加 `<queries>` 声明所有需要交互的包（如支付 SDK、地图 SDK） |
| 后台位置分步 | 实现两步引导：先请求前台位置 → 使用时再引导改为始终允许 |

### 5.3 Step 3：targetSdk 30 → 33（Android 13）

| 适配项 | 具体操作 |
|-------|---------|
| 通知权限 | 集成 `POST_NOTIFICATIONS` 请求，选择合适时机展示弹窗；处理拒绝后的降级逻辑 |
| 细化媒体权限 | 在清单中**同时**保留 `READ_EXTERNAL_STORAGE`（maxSdkVersion=32）和新增三个独立权限 |
| 附近 Wi-Fi 权限 | 若扫描 Wi-Fi，新增 `NEARBY_WIFI_DEVICES` 替代 `ACCESS_FINE_LOCATION` |
| 身体传感器后台 | 若需后台访问身体传感器，新增 `BODY_SENSORS_BACKGROUND` |

**关键代码适配**：

```kotlin
// 请求通知权限（Android 13+）
if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
    requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQ_NOTIFICATION)
}

// 请求媒体权限（Android 13+）
if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
    requestPermissions(arrayOf(
        Manifest.permission.READ_MEDIA_IMAGES,
        Manifest.permission.READ_MEDIA_VIDEO
    ), REQ_MEDIA)
} else {
    requestPermissions(arrayOf(
        Manifest.permission.READ_EXTERNAL_STORAGE
    ), REQ_STORAGE)
}
```

### 5.4 Step 4：targetSdk 33 → 34（Android 14）

| 适配项 | 具体操作 |
|-------|---------|
| 移除 READ_EXTERNAL_STORAGE | 清单中删除或限制 `maxSdkVersion="32"`，仅使用 `READ_MEDIA_*` |
| 照片选择器 | 优先使用 `PickVisualMedia` / `PhotoPicker`（无需权限），作为权限降级方案 |
| 前台服务类型声明 | 每种前台服务必须指定 `foregroundServiceType`（如 `camera`、`location`） |
| 动态广播接收器导出标志 | 注册 `BroadcastReceiver` 时必须显式设置 `RECEIVER_EXPORTED` 或 `RECEIVER_NOT_EXPORTED` |

### 5.5 Step 5：GDPR 合规贯穿全路径

无论 targetSdk 级别，GDPR 合规需贯穿始终：

| 环节 | 技术方案 |
|------|---------|
| 同意管理 | 集成 UMP SDK / 自建 Consent Manager；Tcf 2.2 框架支持 |
| 数据映射 | 建立 Data Map：记录每条个人数据的来源、用途、存储位置、第三方共享 |
| 删除机制 | REST API + 客户端级联清除 |
| 隐私政策 | 应用内可访问的详细隐私政策页面，更新时弹窗提示 |
| DPO 对接 | 提供 `privacy@domain.com` 联系入口 |

---

## 第六层：完整适配 CheckList 与实战经验

### 6.1 权限清单自查表

| 序号 | 检查项 | 通过标准 |
|:---:|------|---------|
| 1 | 不在清单中声明未使用权限 | `aapt d permissions app.apk` 无多余权限 |
| 2 | 运行时权限均有 `checkSelfPermission` 前置检查 | Code Review 确认 |
| 3 | 拒绝后回调处理（Rationale 弹窗 / 设置引导） | 测试覆盖"拒绝+不再询问"路径 |
| 4 | targetSdk=34 不使用 `READ_EXTERNAL_STORAGE` | 清单审查 |
| 5 | 包可见性 `<queries>` 覆盖所有第三方交互 | 支付、分享、地图功能正常 |
| 6 | 后台位置单独请求且有使用声明 | Google Play Console 提交 |
| 7 | GDPR 同意弹窗在数据收集前展示 | 冷启动流程截屏验证 |
| 8 | 有用户数据删除能力（应用内+服务端） | 功能测试 |
| 9 | 通知权限有降级策略 | 被拒绝后核心功能不受阻 |
| 10 | 前台服务类型声明完整 | API 34 设备无 crash |

### 6.2 常见坑与面试回答

**Q1：升级 targetSdk 到 34 后图片加载 crash？**
A：原因可能有三——① 仍使用 `DATA` 列拼接路径；② 使用了 `MediaStore.Images.Media.EXTERNAL_CONTENT_URI` 而非 `getContentUri(VOLUME_EXTERNAL)`；③ 清单中 `READ_EXTERNAL_STORAGE` 的 maxSdkVersion 未设置导致 Android 14 无权限。解决：全部迁移到 `READ_MEDIA_IMAGES` + `RELATIVE_PATH` + `ContentResolver.loadThumbnail()`。

**Q2：用户拒绝通知权限后如何不影响核心体验？**
A：根据业务场景降级——① 即时通讯类用静默通知 + 后台拉取替代；② 工具类通过应用内红点/横幅展示；③ 在关键操作前（如"下单成功"）再次用 Contextual Rationale 引导授权。

**Q3：如何确保 GDPR 合规在代码层面可验证？**
A：建立自动化合规测试：① CI 中集成 `aapt d permissions` 检查权限声明；② 单元测试覆盖同意状态机（未同意→已同意→已撤销）；③ E2E 测试验证数据传输加密（Charles 抓包确认无明文个人信息）；④ 定期审计第三方 SDK 的数据收集行为（用 AppSweep 或 DataDog 的 RUM）。

### 6.3 适配收益

完成以上适配路径后，应用将具备：
- **Google Play 合规**：通过审核要求，避免下架风险。
- **用户信任**：透明的权限请求提升授予率和留存。
- **GDPR 合规**：可在欧盟市场合法运营，避免最高 2000 万欧元或年营收 4% 的罚款。
- **架构健壮性**：Scoped Storage 迁移迫使代码解耦文件系统依赖，长期收益显著。

---

> **总结**：Android 隐私权限适配是一个**持续跟踪 + 渐进迁移**的工程。面试中既要展示对每个 API Level 变化的准确理解，又要能给出完整升级路径的技术方案。把握"Scoped Storage → 运行时权限 → GDPR → Android 14 分拆"这条主线，辅以 targetSdk 升级实战经验，即可从容应对。
