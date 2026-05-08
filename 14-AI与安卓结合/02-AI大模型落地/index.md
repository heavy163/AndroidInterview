# 02 AI 大模型落地

> 面试内容：安卓端 AI 大模型部署 —— 模型压缩（量化/蒸馏）、端侧推理框架（TFLite / ONNX Runtime / NCNN）、硬件加速（NNAPI）、离线运行与工程实战

---

## 一、面试高频问题（5+）

### 1.1 端侧大模型部署方案有哪些？量化（INT8/INT4）和蒸馏如何选型？

**参考答案：**

端侧部署面临三大核心约束：**算力有限、内存紧张、功耗敏感**。主流方案如下：

| 方案 | 原理 | 压缩率 | 精度损失 | 适用场景 |
|------|------|:------:|:--------:|---------|
| **INT8 量化** | 将 FP32 权重/激活映射到 8-bit 整数 | ~4× | <1% | 通用推理，首选项 |
| **INT4 量化** | 进一步压缩到 4-bit | ~8× | 1%~3% | 超低功耗设备、大语言模型 |
| **知识蒸馏** | 大模型（Teacher）指导小模型（Student）训练 | 不固定 | 可控 | 需要特定小模型架构时 |
| **剪枝** | 移除贡献小的神经元/通道 | 30%~90% | 视剪枝率 | 配合量化使用 |
| **混合精度** | 敏感层保留 FP16，其余 INT8 | ~3× | <0.5% | 精度要求极高的场景 |

**量化 vs 蒸馏 选型决策树：**

```
                    有现成小模型可用？
                    /            \
                  是              否
                  │               │
                  ▼               ▼
            直接用+量化      需要定制架构？
            （首选 INT8）      /         \
                           是           否
                           │            │
                           ▼            ▼
                      知识蒸馏       INT8 量化
                    + INT8 量化     + 剪枝配合
```

**追问题：INT4 量化在什么场景下值得使用？**

INT4 的精度损失在 NLP 大模型（如 LLaMA 7B→4-bit）上通常可接受（困惑度下降约 0.5~1.0），但在图像分类/检测等 CV 任务上精度下降更明显（Top-1 可能下降 2~5%），需在目标设备上实测验证。推荐优先尝试 INT8，内存仍超标再考虑 INT4。

---

### 1.2 TFLite / ONNX Runtime / NCNN 等推理框架如何对比选型？

**参考答案：**

| 维度 | TFLite | ONNX Runtime | NCNN |
|------|--------|-------------|------|
| **开发者** | Google | Microsoft | 腾讯 |
| **模型格式** | `.tflite` | `.onnx` | `.param` + `.bin` |
| **算子覆盖** | ★★★★☆ (150+) | ★★★★★ (180+) | ★★★☆☆ (100+) |
| **安卓适配** | ★★★★★ | ★★★★☆ | ★★★★★ |
| **硬件加速** | NNAPI / GPU / Hexagon | NNAPI / GPU / XNNPACK | Vulkan / OpenCL |
| **包体积增量** | ~800KB | ~3MB | ~500KB |
| **社区活跃度** | ★★★★★ | ★★★★★ | ★★★☆☆ |
| **Google Play 推荐** | ✅ 首选 | 备选 | 备选 |

**选型建议：**

```
┌─────────────────────────────────────────────────────┐
│                    框架选型决策矩阵                    │
├────────────┬──────────┬──────────┬──────────────────┤
│ 场景        │ 推荐框架  │ 原因      │ 备注             │
├────────────┼──────────┼──────────┼──────────────────┤
│ 通用 CV 任务 │ TFLite   │ 与安卓深度集成 │ NNAPI 委托零配置  │
│ 跨平台部署   │ ONNX RT  │ 一次导出到处跑 │ 需额外做算子兼容   │
│ 极致性能     │ NCNN     │ 无依赖纯 C++  │ 需手动优化计算图   │
│ 大语言模型   │ MLC-LLM  │ 专用 LLM 引擎 │ llama.cpp 安卓版  │
│ 原型验证     │ TFLite   │ 最快跑通      │ 配合 ML Kit      │
└────────────┴──────────┴──────────┴──────────────────┘
```

**追问题：TFLite 和 ONNX Runtime 在一个项目里能共存吗？**

可以共存，但不推荐。两个框架同时集成会导致包体积膨胀约 4MB（含各自依赖），且各自的 NNAPI 委托可能产生资源竞争。如果团队已有大量 ONNX 模型，建议统一到 ONNX Runtime；如果从零开始，优先 TFLite。

---

### 1.3 模型文件大小与推理性能如何平衡？

**参考答案：**

这是一个多目标优化问题，核心公式：

```
推理质量 = f(模型大小, 推理延迟, 内存峰值, 精度)  ← 帕累托最优
```

**实战平衡策略：**

| 技术手段 | 模型大小 | 推理延迟 | 精度 | 实施难度 |
|---------|:------:|:------:|:---:|:------:|
| INT8 量化 | ↓75% | ↓20%~40% | ~持平 | ★☆☆ |
| 深度可分离卷积 | ↓90% | ↓50% | ↓1~3% | ★★★ |
| 知识蒸馏 | 自定义 | ↓30% | 可控 | ★★★★ |
| 算子融合 | 不变 | ↓15%~25% | 不变 | ★★☆ |
| 模型剪枝 | ↓30~50% | ↓10% | ↓0.5~2% | ★★☆ |

**面试加分点：提出"分级部署"策略**

```
设备等级         内存预算       可用模型             量化策略
───────────────────────────────────────────────────────
旗舰机 (>8GB)    ≤2GB          ResNet50 / ViT-B     FP16，GPU 委托
中端机 (4~6GB)   ≤500MB        MobileNetV3          INT8，NNAPI
低端机 (<4GB)    ≤200MB        MobileNetV3-Small    INT8，CPU + XNNPACK
```

**追问题：如何精准评估模型在目标设备上的性能？**

使用 Android 的 `benchmark_model` 工具（TFLite 自带）或 ONNX Runtime 的 `onnxruntime_perf_test`，在目标设备上跑 100 次 warmup + 1000 次推理，测量 P50/P95 延迟和内存峰值。**不要依赖模拟器数据**——模拟器的 CPU/GPU 行为与真机差异巨大。

---

### 1.4 离线运行时如何控制内存占用和功耗？

**参考答案：**

**内存控制策略：**

```
┌─────────────────────────────────────────────────────┐
│                端侧推理内存生命周期                     │
├──────────┬──────────────────────────────────────────┤
│ 加载阶段  │ 模型文件 → mmap 映射（避免完整读入内存）      │
│          │ 权重内存：sizeof(dtype) × 参数量            │
│ 推理阶段  │ 输入张量 + 中间激活 + 输出张量               │
│          │ 激活内存 = f(batch_size, input_size, layers)│
│ 峰值内存  │ ≈ 权重内存 + 最大层激活内存                  │
└──────────┴──────────────────────────────────────────┘
```

**具体措施：**

| 措施 | 效果 | 实现方式 |
|------|------|---------|
| **mmap 模型文件** | 减少 50% 加载内存 | `Interpreter(byteBuffer)` 或 `mmap` flags |
| **GPU/NPU 委托** | 权重留在 GPU 显存 | `interpreter.useNNAPI = true` |
| **推理后释放中间结果** | 降低峰值 | 框架自动管理（TFLite arena allocator） |
| **单批次推理** | 激活内存最小化 | batch_size = 1 |
| **动态形状避免** | 避免内存重分配 | 固定输入尺寸 |

**功耗控制三板斧：**

```
1. 委托（Delegate）优先：NPU > DSP > GPU > CPU 小核 > CPU 大核
2. 批量推理合并：N 次推理合并为 1 次，减少 CPU 唤醒次数
3. 帧率控制：预览 30fps，但推理只需 5~10fps，中间帧复用上一次结果
```

**追问题：安卓端推理导致发热如何处理？**

- 使用 `AndroidProfileTools` 或 `Perfetto` 监控 CPU/GPU 频率和温度
- GPU 委托在高负载下可能比 CPU 更热（频率拉升），需实测选择冷热平衡方案
- 实现"温度感知推理"：温度 > 40°C 时自动降频推理或切换到 INT4
- 利用 Android 12+ 的 `PerformanceHintManager` 提示系统合理分配 CPU 核心

---

### 1.5 安卓端 AI 应用有哪些典型场景？请分别说明技术方案。

**参考答案：**

| 场景 | 典型模型 | 推理框架 | 关键挑战 |
|------|---------|---------|---------|
| **图像分类** | MobileNetV3 / EfficientNet-Lite | TFLite + NNAPI | 实时性（≤50ms）、多分辨率适配 |
| **目标检测** | EfficientDet-Lite / YOLOv8-nano | TFLite / NCNN | 后处理 NMS 的性能优化 |
| **人脸识别** | FaceNet / ArcFace（轻量版） | TFLite | 活体检测、特征向量加密存储 |
| **图像分割** | DeepLabV3+ / MediaPipe Selfie | TFLite | 高分辨率输入的显存压力 |
| **OCR 文字识别** | CRNN / PaddleOCR-Mobile | ONNX RT | 中英文混合、竖排文字、多角度 |
| **语音唤醒** | KWS（Keyword Spotting） | TFLite Micro | 常驻后台功耗 ≤5mA |
| **语音识别** | Whisper.cpp / 端侧 ASR | GGML 系 | 流式识别、多语种 |
| **NLP/LLM** | Gemma 2B / Phi-3 / Qwen2 | MLC-LLM / llama.cpp | 内存（2B 模型 INT4 ≈ 1.5GB） |
| **图像生成** | Stable Diffusion（量化版） | ONNX RT / Qualcomm AI | 推理时间（>10s），仅限旗舰机 |

**场景一：实时相机图像分类**

```
CameraX → ImageProxy → Bitmap → TFLite Interpreter → Top-K 分类结果 → UI 渲染
                              ↓
                    预处理：resize(224,224), normalize([0,1]), toTensor
```

**场景二：端侧大语言模型对话**

```
用户输入 → Tokenizer → Embedding → Transformer Decoder (INT4, GPU)
                                      ↓
                              逐 Token 生成 → 流式输出到 UI
                                      ↓
                            KV Cache 管理（O(L×H×2) 内存）
```

**追问题：为什么端侧 LLM 难以普及？**

三大瓶颈：(1) 内存——2B 模型 INT4 约需 1.5GB，7B 模型约需 4GB，低端设备无法承受；(2) 推理速度——移动端 GPU Token/s 通常仅 5~15 t/s，远低于云端；(3) 生态系统——安卓端的 Tokenizer、Sampling、KV Cache 等基础设施远不如服务器端成熟。但随着硬件演进（骁龙 8 Gen4 支持 INT4 加速）和模型小型化，未来 2~3 年有望突破。

---

### 1.6 端侧模型的安全性和知识产权保护如何考量？

**参考答案：**

端侧模型直接随 APK 分发，面临逆向提取风险：

| 防护手段 | 安全等级 | 性能影响 | 实施复杂度 |
|---------|:------:|:------:|:--------:|
| 模型文件存入 `assets/` | ★☆☆☆☆ | 无 | ★☆☆ |
| APK 签名校验 + 完整性检查 | ★★☆☆☆ | 无 | ★★☆ |
| 模型权重 AES-256 加密 | ★★★☆☆ | 加载时解密 1~3s | ★★★ |
| 白盒加密 + Native 层加载 | ★★★★☆ | 轻微 | ★★★★★ |
| TEE（Trusted Execution Environment） | ★★★★★ | 无 | ★★★★★ |

**推荐方案：**

```kotlin
// 模型加密加载流程
object ModelLoader {
    fun loadEncryptedModel(context: Context): ByteBuffer {
        // 1. 从 assets 读取加密模型
        val encrypted = context.assets.open("model.tflite.enc").readBytes()
        // 2. Native 层 AES-GCM 解密（密钥隐藏在 .so 中）
        val decrypted = NativeCrypto.decryptAesGcm(encrypted, getKeyFromNative())
        // 3. 返回 ByteBuffer 给 TFLite Interpreter
        return ByteBuffer.allocateDirect(decrypted.size).put(decrypted)
    }
}
```

**关键点：** 没有绝对的安全，目标是提高逆向成本使其超过模型价值。对于高价值模型，推荐结合 TEE（如 Android Keystore + StrongBox）存储解密密钥。

---

## 二、量化原理深度解析

### 2.1 量化基本概念

**核心思路：** 将浮点数（FP32）映射到低精度整数（INT8/INT4），用更少的比特表示近似相同的数值范围。

```
量化映射公式：
    q = round((r - zero_point) / scale)

反量化公式：
    r = scale × (q - zero_point)

其中：
    scale = (rmax - rmin) / (qmax - qmin)
    zero_point = qmin - round(rmin / scale)
```

**对称量化 vs 非对称量化：**

```
┌──────────────────────────────────────────────────────┐
│ 对称量化（Symmetric）:  zero_point = 0                │
│                                                        │
│  FP32:  -max ─────────── 0 ────────── +max           │
│           │                  │              │           │
│  INT8:  -127                0             127         │
│                                                        │
│  适用：权重（通常对称分布）                              │
├──────────────────────────────────────────────────────┤
│ 非对称量化（Asymmetric）: zero_point ≠ 0               │
│                                                        │
│  FP32:  0 ──────────────────────── +max               │
│           │                          │                  │
│  INT8:   0                        255                  │
│                                                        │
│  适用：ReLU 激活输出（非负分布）                         │
└──────────────────────────────────────────────────────┘
```

### 2.2 Post-Training Quantization vs Quantization-Aware Training

**这是面试必考核心题：**

```
┌─────────────────────────────────────────────────────┐
│                    PTQ 流程图                          │
│                                                        │
│  已训练 FP32 模型 ──▶ 校准数据集 ──▶ 统计各层数值范围    │
│                                        │               │
│                                        ▼               │
│                          计算 scale & zero_point       │
│                                        │               │
│                                        ▼               │
│                              INT8 量化模型              │
│                                   │                    │
│                                   ▼                    │
│                        精度验证（≤1000 样本校准）        │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│                    QAT 流程图                          │
│                                                        │
│  已训练 FP32 模型 ──▶ 插入 FakeQuant 节点               │
│                              │                         │
│                              ▼                         │
│                   继续训练（模拟量化误差）               │
│                   forward: FP32 → fakeQuant → INT8 → FP32│
│                   backward: STE (Straight-Through Estimator)│
│                              │                         │
│                              ▼                         │
│                    精度收敛后导出 INT8 模型               │
└─────────────────────────────────────────────────────┘
```

| 对比维度 | PTQ | QAT |
|---------|-----|-----|
| **数据需求** | 数百~数千张校准样本 | 完整训练数据集 |
| **训练时间** | 无需训练，仅校准（几分钟） | 需完整训练（几小时~几天） |
| **精度损失** | INT8: 0.5%~3%；INT4: 3%~10% | INT8: <0.5%；INT4: 1%~3% |
| **工程复杂度** | ★☆☆☆☆ | ★★★★☆ |
| **适用场景** | 绝大多数 CV/NLP 模型 | 对精度极敏感的任务、INT4 部署 |

**面试话术模板：**

> "在实际项目中，我们的策略是 **PTQ 优先，QAT 兜底**。先用 PTQ 做 INT8 量化并评估精度，如果精度损失在可接受范围内（通常 <1%），直接上线；如果精度不达标，再考虑 QAT。对于 INT4 部署，QAT 几乎是必须的。"

**追问题：为什么 PTQ 量化会带来精度损失？**

三个原因：(1) **量化误差**——连续的 FP32 值被映射到离散的 INT8 桶，引入了舍入误差；(2) **范围裁剪**——超出 `[rmin, rmax]` 的值被截断，丢失离群点信息；(3) **误差累积**——逐层传播中量化误差被放大。QAT 通过在训练中模拟这些误差，让模型学会适应量化后的数值分布。

### 2.3 安卓端的量化实践

**TFLite 模型量化命令：**

```python
import tensorflow as tf

# 方式一：训练后整数量化（推荐，支持 NNAPI 全加速）
converter = tf.lite.TFLiteConverter.from_saved_model("saved_model")
converter.optimizations = [tf.lite.Optimize.DEFAULT]
converter.representative_dataset = representative_data_gen  # 校准数据集生成器
converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
converter.inference_input_type = tf.uint8
converter.inference_output_type = tf.uint8
tflite_model = converter.convert()

# 方式二：FP16 量化（GPU 友好，但 NNAPI 兼容性差）
converter.target_spec.supported_types = [tf.float16]

# 方式三：动态范围量化（仅权重量化，速度提升最小）
converter.optimizations = [tf.lite.Optimize.DEFAULT]
```

**PyTorch 模型量化（用于 ONNX 导出）：**

```python
import torch.quantization as quant

# PTQ（Eager Mode）
model_fp32.eval()
model_fp32.qconfig = quant.get_default_qconfig("qnnpack")
quant.prepare(model_fp32, inplace=True)
# ... 校准循环（喂入代表性数据）...
quant.convert(model_fp32, inplace=True)  # 转换为 INT8 模型

# 导出 ONNX 后，用 onnxruntime 的 quantize_static 做量化
from onnxruntime.quantization import quantize_static, QuantType
quantize_static("model.onnx", "model_int8.onnx", calibration_data_reader, 
                quant_format=QuantType.QOperator)
```

---

## 三、NNAPI 硬件加速

### 3.1 NNAPI 架构概览

NNAPI（Android Neural Networks API）是 Android 8.1+ 提供的系统级推理加速接口，自动将计算图下发到设备的专用 AI 硬件：

```
┌─────────────────────────────────────────────────────┐
│                   应用层                              │
│            TFLite / ONNX RT / 自定义框架               │
│                      │                                │
│                      ▼  NNAPI Delegate                │
│              ┌───────────────┐                        │
│              │    NNAPI      │  Android 系统服务       │
│              │  ANeuralNetworks│                       │
│              └───────┬───────┘                        │
│                      │                                │
│          ┌───────────┼───────────┐                    │
│          ▼           ▼           ▼                    │
│     ┌────────┐ ┌────────┐ ┌──────────┐               │
│     │  GPU   │ │  DSP   │ │   NPU    │  ← 硬件驱动    │
│     │(Adreno)│ │(Hexagon)│ │(Tensor等)│               │
│     └────────┘ └────────┘ └──────────┘               │
│          │           │           │                    │
│          ▼           ▼           ▼                    │
│     Qualcomm   Qualcomm   MediaTek / Google Tensor    │
│     Adreno     Hexagon    Samsung Exynos NPU          │
└─────────────────────────────────────────────────────┘
```

**NNAPI 的核心价值：**

1. **硬件透明**：开发者无需关心底层芯片是骁龙/天玑/Exynos/麒麟，NNAPI 自动选择最优加速器
2. **功耗优化**：专用 NPU/DSP 的能效比通常是 CPU 的 10~100 倍
3. **零拷贝**：NNAPI 支持 AHardwareBuffer，输入/输出无需 CPU→GPU 数据搬运

### 3.2 NNAPI 与推理框架的集成

**TFLite 启用 NNAPI：**

```kotlin
val interpreter = Interpreter(tfliteModel, Interpreter.Options().apply {
    // 基础 NNAPI 启用
    useNNAPI = true

    // 高级配置（API 29+）
    // 允许回退到 CPU（算子不支持时）
    nnapiAllowFp16PrecisionForFp32 = true

    // 为 NNAPI 委托设置加速器偏好
    // ACCELERATOR_PREFERENCE_SUSTAINED_SPEED：偏向 GPU/NPU（持续推理）
    // ACCELERATOR_PREFERENCE_FAST_SINGLE_ANSWER：偏向 CPU（单次推理，避免初始化开销）
    // ACCELERATOR_PREFERENCE_LOW_POWER：偏向 DSP（低功耗常驻任务）
})
```

**ONNX Runtime 启用 NNAPI：**

```kotlin
val sessionOptions = OrtSession.SessionOptions().apply {
    // 添加 NNAPI 执行提供器
    addNnapi(
        NnapiFlags.NNAPI_FLAG_CPU_DISABLED or
        NnapiFlags.NNAPI_FLAG_USE_FP16
    )
}
val session = ortEnv.createSession("model_int8.onnx", sessionOptions)
```

**NNAPI 不支持的算子如何处理？**

```
┌───────────────────────────────────────────┐
│      TFLite NNAPI 算子兼容性检查流程        │
│                                            │
│  模型加载                                    │
│     │                                       │
│     ▼                                       │
│  遍历所有算子                                │
│     │                                       │
│     ├── NNAPI 支持？ ── 是 ──▶ 映射到 NNAPI  │
│     │                           算子       │
│     │                                       │
│     └── 不支持 ──▶ 标记为 CPU 回退          │
│                       │                     │
│                       ▼                     │
│              生成 CPU/NNAPI 混合计算图       │
│                                            │
│  ⚠️ 注意：CPU↔NNAPI 切换有数据搬运开销      │
│     单图切换次数 >5 次时，推理延迟可能增加   │
│     建议尽量选用 NNAPI 覆盖率高的模型架构    │
└───────────────────────────────────────────┘
```

### 3.3 硬件加速选型决策树

```
                是否需要硬件加速？
                      │
              ┌───────┴───────┐
             否                是
              │                │
              ▼                ▼
         CPU + XNNPACK    需要常驻后台/低功耗？
         （简单可靠）          │
                      ┌───────┴───────┐
                     是                否
                      │                │
                      ▼                ▼
                 NNAPI（DSP）     需要极致性能？
                 ◀ 语音唤醒           │
                                  ┌───┴───┐
                                 是       否
                                  │        │
                                  ▼        ▼
                            GPU 委托    NNAPI（NPU）
                            ◀ 实时视频   ◀ 通用最优
```

**实战经验：**

- **NNAPI 的第一次推理通常很慢**（100~200ms 初始化），之后进入稳定状态。预热策略：在 `onResume` 时执行一次 dummy 推理
- **骁龙 Hexagon DSP** 对 INT8 量化模型有极好的支持，但 FP16 模型可能无法加速
- **Google Tensor 的 TPU** 需要特定版本的 TFLite 委托，普通 NNAPI 无法自动利用

---

## 四、端侧推理流程图

### 4.1 完整推理流水线

```
┌─────────────────────────────────────────────────────────────────────┐
│                        端侧推理完整流水线                              │
│                                                                      │
│  ┌──────────┐    ┌──────────┐    ┌────────────┐    ┌──────────────┐ │
│  │ 1. 输入   │───▶│ 2. 预处理 │───▶│ 3. 模型推理  │───▶│ 4. 后处理    │ │
│  │ 数据采集  │    │ 图像/音频 │    │ 委托分发     │    │ 结果解析     │ │
│  └──────────┘    └──────────┘    └────────────┘    └──────────────┘ │
│       │               │               │                    │         │
│       ▼               ▼               ▼                    ▼         │
│  · CameraX        · Resize        · NPU 委托          · Softmax     │
│  · AudioRecord    · Normalize     · GPU 委托          · NMS         │
│  · 用户输入       · ToTensor      · CPU 回退          · CTC 解码    │
│  · 传感器数据     · Tokenize      · 多线程并行        · 阈值过滤    │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                      5. 结果输出与交互                          │   │
│  │                                                               │   │
│  │  · UI 更新（主线程回调）    · 播放声音/振动     · 日志记录      │   │
│  │  · 通知栏推送（后台）      · 后续业务逻辑触发   · 性能监控      │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.2 各阶段详解

**阶段 1：输入数据采集**

```
数据源              采集 API                   格式             延迟要求
─────────────────────────────────────────────────────────────────
摄像头预览           CameraX ImageAnalysis    YUV_420_888      ≤33ms (30fps)
静态图片             ContentResolver           JPEG/PNG         不限
麦克风               AudioRecord              PCM 16-bit       ≤200ms（关键词检测）
传感器（IMU）        SensorManager            float[3]         ≤20ms
用户文本输入         EditText                 String           不限
```

**阶段 2：预处理 —— 以图像为例**

```kotlin
// 图像预处理管道
fun preprocess(image: ImageProxy): ByteBuffer {
    // Step 1: YUV → RGB 转换
    val bitmap = image.toBitmap() // 或使用 Renderscript/OpenCV 加速
    
    // Step 2: 缩放到模型输入尺寸
    val resized = Bitmap.createScaledBitmap(bitmap, 224, 224, true)
    
    // Step 3: 归一化 + 通道转换
    val input = ByteBuffer.allocateDirect(4 * 224 * 224 * 3)
    input.order(ByteOrder.nativeOrder())
    for (y in 0 until 224) {
        for (x in 0 until 224) {
            val pixel = resized.getPixel(x, y)
            // RGB → (R/255.0 - mean) / std → float
            input.putFloat(((pixel shr 16 and 0xFF) / 255.0f - 0.485f) / 0.229f)
            input.putFloat(((pixel shr 8 and 0xFF) / 255.0f - 0.456f) / 0.224f)
            input.putFloat(((pixel and 0xFF) / 255.0f - 0.406f) / 0.225f)
        }
    }
    return input
}
```

**阶段 3：模型推理——线程模型**

```kotlin
class InferenceEngine(private val interpreter: Interpreter) {
    // 推理必须在后台线程执行
    suspend fun infer(input: ByteBuffer): FloatArray = withContext(Dispatchers.Default) {
        val output = FloatArray(NUM_CLASSES)
        interpreter.run(input, output)
        output
    }
}
```

**阶段 4：后处理**

```kotlin
fun postprocess(logits: FloatArray, topK: Int = 5): List<Pair<String, Float>> {
    return logits.mapIndexed { idx, score ->
        LABELS[idx] to score
    }.sortedByDescending { it.second }
     .take(topK)
}
```

**阶段 5：结果输出**

```kotlin
lifecycleScope.launch {
    val results = inferenceEngine.infer(preprocessedInput)
    withContext(Dispatchers.Main) {
        updateUI(results)
    }
}
```

---

## 五、实战：在安卓端部署图像分类模型（上）

### 5.1 模型选型与准备

**场景设定：** 在安卓端实现一个实时花卉识别应用，需识别 102 种花卉，要求单次推理 ≤100ms、模型 ≤15MB。

**模型选型对比：**

| 模型 | Top-1 精度 | 模型大小 (FP32) | 推理延迟 (Pixel 6) | 选择 |
|------|:--------:|:------------:|:------------------:|:---:|
| ResNet50 | 76.1% | 98MB | 120ms | ❌ 太大 |
| EfficientNet-B0 | 77.1% | 21MB | 80ms | ❌ 偏大 |
| **MobileNetV3-Large** | **75.2%** | **17MB → 4.3MB (INT8)** | **60ms → 28ms** | ✅ |
| MobileNetV3-Small | 68.5% | 10MB → 2.5MB | 35ms → 16ms | 备选 |

**最终选择：MobileNetV3-Large，INT8 量化后 4.3MB，推理 28ms。**

### 5.2 模型训练与转换（Python 端）

```python
# ===========================================
# Step 1: 准备训练/微调（使用 TF Hub）
# ===========================================
import tensorflow as tf
import tensorflow_hub as hub

# 加载预训练 MobileNetV3-Large
model = tf.keras.Sequential([
    hub.KerasLayer(
        "https://tfhub.dev/google/imagenet/mobilenet_v3_large_100_224/classification/5",
        trainable=True
    )
])

# 在花卉数据集上微调
model.compile(optimizer=tf.keras.optimizers.Adam(1e-4),
              loss='sparse_categorical_crossentropy',
              metrics=['accuracy'])
model.fit(train_dataset, validation_data=val_dataset, epochs=10)

# 保存 SavedModel
tf.saved_model.save(model, "flower_model_fp32")

# ===========================================
# Step 2: PTQ INT8 量化
# ===========================================
def representative_dataset():
    """校准数据集生成器：从训练集取 200 张代表性图片"""
    for image_batch, _ in calibration_dataset.take(200):
        yield [image_batch]

converter = tf.lite.TFLiteConverter.from_saved_model("flower_model_fp32")

# 启用量化
converter.optimizations = [tf.lite.Optimize.DEFAULT]
converter.representative_dataset = representative_dataset

# 强制 INT8 算子（确保 NNAPI 全加速）
converter.target_spec.supported_ops = [
    tf.lite.OpsSet.TFLITE_BUILTINS_INT8
]
converter.inference_input_type = tf.uint8   # 输入也用 uint8
converter.inference_output_type = tf.uint8  # 输出也用 uint8

# 转换并保存
tflite_quant_model = converter.convert()
with open("flower_model_int8.tflite", "wb") as f:
    f.write(tflite_quant_model)

print(f"FP32 模型大小: {len(tf.saved_model.save(model, '/tmp/fp32'))} bytes")
print(f"INT8 模型大小: {len(tflite_quant_model)} bytes")

# ===========================================
# Step 3: 精度验证
# ===========================================
interpreter = tf.lite.Interpreter(
    model_content=tflite_quant_model,
    num_threads=4
)
interpreter.allocate_tensors()

correct = 0
total = 0
for images, labels in val_dataset.take(500):
    for i in range(images.shape[0]):
        input_data = tf.cast(images[i:i+1], tf.uint8)
        interpreter.set_tensor(input_index, input_data)
        interpreter.invoke()
        output = interpreter.get_tensor(output_index)
        predicted = np.argmax(output[0])
        if predicted == labels[i]:
            correct += 1
        total += 1

print(f"INT8 量化后 Top-1 精度: {correct/total*100:.2f}%")
```

---

## 六、实战：在安卓端部署图像分类模型（下）

### 6.1 Android 项目集成

**项目结构：**

```
app/
├── src/main/
│   ├── assets/
│   │   ├── flower_model_int8.tflite    # 量化模型（4.3MB）
│   │   └── flower_labels.txt           # 102 个类别名
│   ├── java/com/example/flowerai/
│   │   ├── MainActivity.kt
│   │   ├── inference/
│   │   │   ├── FlowerClassifier.kt     # 分类器封装
│   │   │   └── Preprocessor.kt         # 图像预处理
│   │   └── camera/
│   │       └── CameraAnalyzer.kt       # CameraX 分析器
│   └── res/
├── build.gradle.kts
```

**Gradle 依赖：**

```kotlin
// build.gradle.kts (Module: app)
dependencies {
    // TFLite 运行时（不含 Google Play Services）
    implementation("org.tensorflow:tensorflow-lite:2.16.1")
    // GPU 委托（可选，用于对比测试）
    implementation("org.tensorflow:tensorflow-lite-gpu:2.16.1")
    // Android 原生硬件加速（NNAPI 已内置，无需额外依赖）
    
    // CameraX
    implementation("androidx.camera:camera-core:1.3.4")
    implementation("androidx.camera:camera-camera2:1.3.4")
    implementation("androidx.camera:camera-lifecycle:1.3.4")
}
```

### 6.2 推理引擎实现

**FlowerClassifier.kt —— 核心分类器：**

```kotlin
package com.example.flowerai.inference

import android.content.Context
import android.content.res.AssetFileDescriptor
import org.tensorflow.lite.Interpreter
import java.io.FileInputStream
import java.nio.ByteBuffer
import java.nio.channels.FileChannel

class FlowerClassifier(context: Context) {

    private val interpreter: Interpreter
    private val labels: List<String>

    companion object {
        private const val MODEL_FILE = "flower_model_int8.tflite"
        private const val LABEL_FILE = "flower_labels.txt"
        private const val INPUT_SIZE = 224
        private const val NUM_CLASSES = 102
    }

    init {
        // 1. 加载标签
        labels = context.assets.open(LABEL_FILE)
            .bufferedReader()
            .readLines()
            .filter { it.isNotBlank() }

        // 2. 使用 mmap 加载模型（减少内存占用）
        val modelBuffer = context.assets.openFd(MODEL_FILE).use { afd ->
            FileInputStream(afd.fileDescriptor).channel.use { channel ->
                channel.map(
                    FileChannel.MapMode.READ_ONLY,
                    afd.startOffset,
                    afd.declaredLength
                )
            }
        }

        // 3. 创建解释器，启用 NNAPI
        interpreter = Interpreter(modelBuffer, Interpreter.Options().apply {
            useNNAPI = true
            // 设置线程数（NNAPI 运行时 CPU 线程数影响有限）
            setNumThreads(4)
        })

        // 4. 预热：执行一次 dummy 推理，初始化 NNAPI 委托
        val dummyInput = ByteBuffer.allocateDirect(INPUT_SIZE * INPUT_SIZE * 3)
        val dummyOutput = Array(NUM_CLASSES) { ByteArray(1) }
        interpreter.run(dummyInput, dummyOutput)
    }

    /**
     * 执行推理
     * @param input 已预处理的 uint8 ByteBuffer (224×224×3)
     * @return 按置信度降序排列的 Top-5 分类结果
     */
    fun classify(input: ByteBuffer): List<Classification> {
        val output = Array(NUM_CLASSES) { ByteArray(1) }
        interpreter.run(input, output)

        return output.mapIndexed { idx, byteArray ->
            Classification(
                label = labels.getOrElse(idx) { "unknown_$idx" },
                confidence = (byteArray[0].toInt() and 0xFF) / 255.0f
            )
        }.sortedByDescending { it.confidence }
         .take(5)
    }

    fun close() {
        interpreter.close()
    }
}

data class Classification(
    val label: String,
    val confidence: Float
)
```

**Preprocessor.kt —— 图像预处理：**

```kotlin
package com.example.flowerai.inference

import android.graphics.Bitmap
import android.graphics.ImageFormat
import androidx.camera.core.ImageProxy
import java.nio.ByteBuffer

object Preprocessor {

    private const val INPUT_SIZE = 224

    /**
     * 将 CameraX ImageProxy 转换为模型输入的 ByteBuffer
     * 输入模型为 uint8 量化，因此输出 uint8 ByteBuffer（非 float）
     */
    fun imageProxyToBuffer(image: ImageProxy): ByteBuffer {
        val bitmap = imageProxyToBitmap(image)
        val scaled = Bitmap.createScaledBitmap(bitmap, INPUT_SIZE, INPUT_SIZE, true)

        val buffer = ByteBuffer.allocateDirect(INPUT_SIZE * INPUT_SIZE * 3)
        val pixels = IntArray(INPUT_SIZE * INPUT_SIZE)
        scaled.getPixels(pixels, 0, INPUT_SIZE, 0, 0, INPUT_SIZE, INPUT_SIZE)

        for (pixel in pixels) {
            // uint8 量化模型：直接写入 [0, 255] RGB 值
            buffer.put((pixel shr 16 and 0xFF).toByte())  // R
            buffer.put((pixel shr 8 and 0xFF).toByte())   // G
            buffer.put((pixel and 0xFF).toByte())          // B
        }

        // 注意：某些量化模型要求 buffer.rewind()
        // 这里 ByteBuffer.allocateDirect 已归零，无需额外操作
        return buffer
    }

    private fun imageProxyToBitmap(image: ImageProxy): Bitmap {
        val planes = image.planes
        val yPlane = planes[0]
        val uPlane = planes[1]
        val vPlane = planes[2]

        val yBuffer = yPlane.buffer
        val uBuffer = uPlane.buffer
        val vBuffer = vPlane.buffer

        val ySize = yBuffer.remaining()
        val uSize = uBuffer.remaining()
        val vSize = vBuffer.remaining()

        val nv21 = ByteArray(ySize + uSize + vSize)
        yBuffer.get(nv21, 0, ySize)
        vBuffer.get(nv21, ySize, vSize)
        uBuffer.get(nv21, ySize + vSize, uSize)

        val yuvImage = android.graphics.YuvImage(
            nv21, ImageFormat.NV21,
            image.width, image.height, null
        )

        val out = java.io.ByteArrayOutputStream()
        yuvImage.compressToJpeg(
            android.graphics.Rect(0, 0, image.width, image.height),
            100, out
        )

        val jpegData = out.toByteArray()
        return android.graphics.BitmapFactory.decodeByteArray(
            jpegData, 0, jpegData.size
        )
    }
}
```

**CameraAnalyzer.kt —— CameraX 集成：**

```kotlin
package com.example.flowerai.camera

import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import com.example.flowerai.inference.FlowerClassifier
import com.example.flowerai.inference.Preprocessor
import kotlinx.coroutines.*

class CameraAnalyzer(
    private val classifier: FlowerClassifier,
    private val onResult: (String) -> Unit
) : ImageAnalysis.Analyzer {

    private val analysisScope = CoroutineScope(Dispatchers.Default + SupervisorJob())
    private var lastAnalyzedTimestamp = 0L
    private val minIntervalMs = 200L  // 每秒最多推理 5 次，控制功耗

    override fun analyze(imageProxy: ImageProxy) {
        val currentTimestamp = System.currentTimeMillis()
        if (currentTimestamp - lastAnalyzedTimestamp < minIntervalMs) {
            imageProxy.close()
            return
        }
        lastAnalyzedTimestamp = currentTimestamp

        analysisScope.launch {
            try {
                // 预处理（在后台线程）
                val input = Preprocessor.imageProxyToBuffer(imageProxy)

                // 推理
                val results = classifier.classify(input)

                // 构建结果文本
                val resultText = results.joinToString("\n") { result ->
                    "${result.label}: ${"%.1f".format(result.confidence * 100)}%"
                }

                // 切回主线程更新 UI
                withContext(Dispatchers.Main) {
                    onResult(resultText)
                }
            } catch (e: Exception) {
                // 推理失败时静默处理，不阻塞相机预览
            } finally {
                imageProxy.close()
            }
        }
    }
}
```

### 6.3 性能优化与验证清单

**上线前检查清单：**

```
┌─────────────────────────────────────────────────────────────┐
│                  性能优化验证 Checklist                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ □ 1. 模型大小：4.3MB ≤ 15MB 上限 ✓                           │
│                                                              │
│ □ 2. 推理延迟（Pixel 6, NNAPI）：                            │
│      - 均值 28ms ✓   P95 35ms ✓   P99 48ms ✓               │
│                                                              │
│ □ 3. 内存峰值：模型加载后 +60MB，推理中 +15MB                 │
│      合计 ~120MB（含应用基础），4GB 设备安全 ✓                 │
│                                                              │
│ □ 4. 功耗测试（30 分钟持续推理）：                            │
│      - 电池温度：32°C → 39°C（未触发降频）✓                  │
│      - 耗电：每分钟约 1.2%（Pixel 6, 4000mAh）              │
│                                                              │
│ □ 5. 多设备兼容性测试：                                       │
│      - 骁龙 8 Gen 2 (NNAPI NPU): 22ms ✓                     │
│      - 骁龙 778G (NNAPI DSP):  35ms ✓                       │
│      - 天玑 8200 (NNAPI APU):  31ms ✓                       │
│      - 低端 MTK G85 (CPU 回退): 95ms（勉强达标）△            │
│                                                              │
│ □ 6. 精度验证（测试集 500 张）：                              │
│      - FP32 原始模型：Top-1 75.2%                             │
│      - INT8 量化模型：Top-1 74.8%（损失 0.4%）✓              │
│                                                              │
│ □ 7. 降级策略：NNAPI 不可用时自动回退 CPU + XNNPACK          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**常见坑与解决：**

| 问题 | 现象 | 解决 |
|------|------|------|
| **NNAPI 初始化慢** | 第一次推理 ~200ms | 预热：`onResume` 时执行 dummy 推理 |
| **uint8 输入归一化错误** | 所有图片识别为同一类 | 确认量化参数与预处理一致（uint8 直接传 [0,255]） |
| **内存泄漏** | 长时间运行后 OOM | 确保每次 `imageProxy.close()`；监控 `ByteBuffer` 复用 |
| **相机预览卡顿** | UI 不流畅 | 推理限制帧率 + `ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST` |
| **某些设备 NNAPI 崩溃** | UnsatisfiedLinkError | 用 `try-catch` 包裹，回退 CPU；上报设备型号 |

---

## 总结

安卓端 AI 大模型落地的核心能力栈：

```
┌─────────────────────────────────────────────────────────────┐
│           安卓端 AI 大模型落地 —— 六层能力模型                │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  第六层：工程落地                                             │
│  ├─ CameraX 集成、协程调度、降级策略、CI/CD                    │
│  └─ 性能监控（Perfetto/Systrace）、线上崩溃分析               │
│                                                              │
│  第五层：端侧推理引擎                                         │
│  ├─ TFLite Interpreter、ONNX Runtime Session                 │
│  └─ mmap 加载、ByteBuffer 管理、多线程调度                    │
│                                                              │
│  第四层：预处理 & 后处理                                       │
│  ├─ 图像：YUV→RGB、Resize、Normalize                         │
│  └─ 输出：Softmax、NMS、Beam Search、CTC 解码                │
│                                                              │
│  第三层：硬件加速                                             │
│  ├─ NNAPI、GPU Delegate、Hexagon DSP、XNNPACK               │
│  └─ 加速器选型、回退策略、算子兼容性检查                      │
│                                                              │
│  第二层：模型压缩                                             │
│  ├─ PTQ (Post-Training Quantization)                         │
│  ├─ QAT (Quantization-Aware Training)                        │
│  ├─ 知识蒸馏、剪枝、混合精度                                  │
│  └─ 对称/非对称量化、Per-channel/Per-tensor                  │
│                                                              │
│  第一层：场景分析 & 模型选型                                   │
│  ├─ 任务类型（CV/NLP/Speech）→ 模型架构                      │
│  ├─ 目标设备 → 内存预算、算力上限                             │
│  └─ 精度/速度/体积的帕累托最优                                │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**面试核心考察点：**

1. **能否独立完成从模型训练到安卓端部署的完整链路？** —— 考察工程全栈能力
2. **理解量化原理，知道 PTQ 和 QAT 的区别和适用场景** —— 考察理论深度
3. **了解 NNAPI 的工作机制，能合理选择硬件加速方案** —— 考察系统知识
4. **具备内存和功耗的管控意识，能分析端侧推理的性能瓶颈** —— 考察优化能力
5. **能处理真实设备上的兼容性问题，有降级和兜底方案** —— 考察工程素养

> 一个优秀的安卓 AI 工程师 = 扎实的模型优化能力 + 深入的安卓系统知识 + 严谨的工程落地实践 + 对端侧硬件生态的敏锐判断
