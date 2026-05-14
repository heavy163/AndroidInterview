# AI 技能面试高频 QA

> 对应简历【核心技能 → AI / 数据智能 + AI Agent 工程化】板块的逐条面试题

## 目录

- [🧠 AI / 机器学习与数据智能](#-ai--机器学习与数据智能)
  - [Q1：TensorFlow Lite 的模型部署流程是怎样的？量化是什么？](#q1tensorflow-lite-的模型部署流程是怎样的量化是什么)
  - [Q2：NNAPI 和 GPU Delegate 分别解决什么问题？什么时候用哪个？](#q2nnapi-和-gpu-delegate-分别解决什么问题什么时候用哪个)
  - [Q3：MediaPipe 和 ML Kit 的架构区别？各自适用场景？](#q3mediapipe-和-ml-kit-的架构区别各自适用场景)
  - [Q4：Python 数据处理中，Pandas 和 NumPy 的核心区别？](#q4python-数据处理中pandas-和-numpy-的核心区别)
  - [Q5：Scikit-learn 做回归拟合（如光谱→浓度）的完整 pipeline 是怎样的？](#q5scikit-learn-做回归拟合如光谱浓度的完整-pipeline-是怎样的)
  - [Q6：RAG 检索增强生成的原理是什么？和 Fine-tuning 的区别？](#q6rag-检索增强生成的原理是什么和-fine-tuning-的区别)
  - [Q7：LangChain 的核心抽象有哪些？Chain / Agent / Tool 分别是什么？](#q7langchain-的核心抽象有哪些chain--agent--tool-分别是什么)
  - [Q8：Prompt Engineering 的核心技巧有哪些？Few-shot / Chain-of-Thought 怎么用？](#q8prompt-engineering-的核心技巧有哪些few-shot--chain-of-thought-怎么用)
- [🤖 AI Agent 工程化与研发提效](#-ai-agent-工程化与研发提效)
  - [Q9：AI Agent 和传统 Chatbot 的核心区别是什么？](#q9ai-agent-和传统-chatbot-的核心区别是什么)
  - [Q10：Tool Calling 的工作原理是怎样的？函数签名如何被 LLM 理解？](#q10tool-calling-的工作原理是怎样的函数签名如何被-llm-理解)
  - [Q11：Agent 的 Skill 管理和复用机制是怎样的？和微服务有什么区别？](#q11agent-的-skill-管理和复用机制是怎样的和微服务有什么区别)
  - [Q12：Cron Job 异步任务在 Agent 系统中如何实现上下文注入？](#q12cron-job-异步任务在-agent-系统中如何实现上下文注入)
  - [Q13：用 Gemini in Android Studio 辅助性能诊断的具体工作流是怎样的？](#q13用-gemini-in-android-studio-辅助性能诊断的具体工作流是怎样的)
  - [Q14：AI Agent 如何嵌入日常 Android 研发闭环？](#q14ai-agent-如何嵌入日常-android-研发闭环)

---

## 🧠 AI / 机器学习与数据智能

### Q1：TensorFlow Lite 的模型部署流程是怎样的？量化是什么？

**标准回答：**

TensorFlow Lite 是 Google 的端侧推理引擎，将训练好的模型（通常 `.h5` / SavedModel）转换为 `.tflite` 格式在移动设备上运行。完整流程分四步：

```
① 训练/获取模型（TF/Keras/PyTorch → SavedModel）
        ↓
② 转换（TFLiteConverter → .tflite）
        ↓  可选：量化（quantization）
③ 集成到 Android（添加 .tflite 到 assets/，依赖 tflite-runtime）
        ↓
④ 推理（Interpreter.run()）
```

**量化（Quantization）详解：**

| 量化方式 | 精度 | 体积缩减 | 速度提升 | 硬件要求 |
|---------|:---:|:------:|:------:|---------|
| **Float32（无量化）** | 最高 | 基准 | 基准 | 通用 |
| **Float16 量化** | 略降 | ~50% | GPU 上加速 | GPU Delegate |
| **Dynamic Range 量化** | 微降 | ~75% | CPU 上 2-3x | 通用（最推荐入门） |
| **Full Integer 量化** | 小幅下降 | ~75% | CPU 上 3-4x | 需要代表性数据集做校准 |
| **Int8 + Float fallback** | 可控 | ~75% | 混合 | 部分 op 支持 Int8 |

**核心代码链路（Android）：**

```kotlin
// 1. 加载模型
val interpreter = Interpreter(loadModelFile("model.tflite"))

// 2. 准备输入/输出 Buffer
val inputBuffer = ByteBuffer.allocateDirect(INPUT_SIZE * 4)
    .order(ByteOrder.nativeOrder())
// ... 填充像素数据 ...

val outputBuffer = Array(1) { FloatArray(NUM_CLASSES) }

// 3. 推理
interpreter.run(inputBuffer, outputBuffer)
```

**面试加分点**：
- 使用 TensorFlow Lite Task Library（更高层 API，一行代码做图像分类/目标检测）
- 使用 TFLite Support Library 做预处理（图像缩放/归一化）
- 了解 NNAPI Delegate 的 fallback 机制（不支持的操作自动回退 CPU）

---

### Q2：NNAPI 和 GPU Delegate 分别解决什么问题？什么时候用哪个？

**标准回答：**

两者都是 TFLite 的**硬件加速委托（Delegate）**，让推理在专用硬件上执行，而非纯 CPU。

| 维度 | NNAPI Delegate | GPU Delegate |
|------|---------------|--------------|
| **硬件** | 调用系统 NNAPI HAL → 底层可以是 DSP / NPU / GPU / 专用 AI 芯片 | 直接使用 OpenGL ES 3.1 / OpenCL / Vulkan Compute |
| **厂商适配** | 由 SoC 厂商实现 HAL（高通 Hexagon NN / 联发科 APU / 三星 NPU） | Google 维护，跨厂商一致 |
| **延迟** | 极低（特别是 NPU/DSP 场景） | 低（但可能有 GPU 上下文切换开销） |
| **功耗** | 最低（DSP/NPU 专为低功耗推理设计） | 中等 |
| **算子覆盖** | 取决于厂商 HAL 实现，部分 op 会 fallback CPU | 较完整，但对 LSTM/RNN 等时序模型支持弱 |
| **适合场景** | 持续推理（摄像头实时分析）、低功耗场景 | 批量推理、大模型、图像/视频处理 |

**选择建议（面试标准答案）：**

```
实时摄像头 → NNAPI（利用 DSP 低功耗持续运行）
大图像模型 → GPU Delegate（并行计算优势）
不确定     → NNAPI（自动 fallback，兼容性最好）
极小模型   → CPU（Delegate 本身有调度开销，模型太小反而不划算）
```

**"混合推理"是面试亮点**：TFLite 2.3+ 支持多 Delegate 组合——例如用 NNAPI 跑主干网络、GPU 跑后处理，但实际工程复杂度高，较少使用。

---

### Q3：MediaPipe 和 ML Kit 的架构区别？各自适用场景？

**标准回答：**

两者都是 Google 的移动端 AI 框架，但定位完全不同：

| 维度 | MediaPipe | ML Kit |
|------|----------|--------|
| **定位** | 开源 **ML Pipeline 框架**（自定义 pipeline） | Google 托管的 **ML 解决方案 SDK**（开箱即用） |
| **自定义能力** | 💚 极高——可自定义模型、预处理、后处理、多模型串联 | 🔴 有限——只能使用 Google 预置模型或自定义 TFLite |
| **开箱能力** | 需自行搭建 pipeline | 🟢 一行代码做人脸/文字/条码/姿态/自拍分割 |
| **跨平台** | Android / iOS / Web / Python / C++ | Android / iOS |
| **学习曲线** | 陡（需理解 Calculator / Graph / Packet 概念） | 平缓（API 极简） |
| **适用场景** | 研究、自定义 AI 产品（如自研手势识别、自定义健身追踪） | 快速集成通用 ML 能力（扫码/OCR/人脸检测） |

**架构对比（面试重点）：**

```
MediaPipe:
  [Camera] → [Calculator A] → [Calculator B] → [Calculator C] → [Renderer]
                ↑                                 ↑
           [TFLite Model]                   [TFLite Model]
  —— 本质是有向图计算框架，每个 Calculator 是一个节点

ML Kit:
  FaceDetector.detect(image) → List<Face>
  —— 本质是封装好的 SDK，内部可能用 MediaPipe 实现
```

**关键面试洞察**：ML Kit 的底层实现已迁移到 MediaPipe。如果你说"ML Kit 本质上是对 MediaPipe 的薄封装 + 云端模型托管"，面试官会点头。

---

### Q4：Python 数据处理中，Pandas 和 NumPy 的核心区别？

**标准回答：**

| 维度 | NumPy | Pandas |
|------|-------|--------|
| **数据类型** | 同质多维数组 `ndarray`（所有元素同类型） | 异质二维表 `DataFrame`（每列可不同类型） |
| **轴标签** | 无（纯索引） | 有（行索引 + 列名） |
| **缺失值** | 不原生支持（需 masked array 或 NaN） | 原生 `NaN` / `None`，有 `dropna()` / `fillna()` |
| **面向场景** | 数值计算、矩阵运算、科学计算 | 数据分析、清洗、探索、时间序列 |
| **底层实现** | C/Fortran，内存连续 | 底层依赖 NumPy，但对异构数据有 Python 层开销 |

**实战场景对比：**

```python
# NumPy 擅长：纯数值矩阵运算
import numpy as np
data = np.array([[1.2, 3.4], [5.6, 7.8]])
result = np.dot(data.T, data)    # 矩阵乘法 → O(1) 表达，C 级速度

# Pandas 擅长：带标签的异构数据操作
import pandas as pd
df = pd.read_csv("sensor_data.csv")
df = df[df["temperature"] > 25]            # 条件过滤
df.groupby("sensor_id")["value"].mean()    # 分组聚合
df["datetime"] = pd.to_datetime(df["ts"])  # 时间序列解析
```

**光谱标定场景的最佳实践**：NumPy 做数学核心（多项式拟合 `np.polyfit`、矩阵运算），Pandas 管理实验数据（多个传感器的多次采样、时间对齐、异常值清洗），Scikit-learn 做模型拟合和交叉验证。

---

### Q5：Scikit-learn 做回归拟合（如光谱→浓度）的完整 pipeline 是怎样的？

**标准回答：**

这是一个典型的**工业 AI 落地场景**——给定光谱仪采集的数百帧光谱数据（特征），输出各金属元素的浓度值（目标）。

```
① 数据采集与清洗（Pandas）
   ├─ 读取 N 个标准样品的多次测量数据
   ├─ 异常值检测（IQR / Z-score）
   └─ 数据对齐（每个样品的光谱波长对齐）

② 特征工程（NumPy + Scikit-learn）
   ├─ 峰面积计算（指定波长区间积分 → 特征列）
   ├─ 基线校正（扣除暗电流基线）
   ├─ 标准化 StandardScaler / 归一化 MinMaxScaler
   └─ 可选：PCA 降维（数百帧光谱 → 几十个主成分）

③ 模型选择与训练
   ├─ 数据划分 train_test_split(80/20)
   ├─ 模型：
   │   ├─ LinearRegression（线性关系）
   │   ├─ Ridge / Lasso（带正则化，防过拟合）
   │   ├─ SVR（支持向量回归，小样本效果好）
   │   └─ RandomForestRegressor / GradientBoosting（非线性拟合）
   └─ 交叉验证 cross_val_score (k=5)

④ 评估与调优
   ├─ 指标：R² / MAE / RMSE / MAPE
   ├─ 调参：GridSearchCV / RandomizedSearchCV
   └─ 学习曲线诊断过拟合/欠拟合

⑤ 部署
   ├─ joblib.dump(model, "calibration.pkl")
   ├─ 生产环境加载 model.predict(new_spectrum)
   └─ 精密度/准确度回测验证
```

**面试加分代码示例：**

```python
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import cross_val_score

pipeline = Pipeline([
    ("scaler", StandardScaler()),
    ("regressor", GradientBoostingRegressor(n_estimators=100, max_depth=5))
])

scores = cross_val_score(pipeline, X_spectrum, y_concentration, cv=5, scoring="r2")
print(f"R²: {scores.mean():.4f} (±{scores.std():.4f})")
```

**为什么不用深度学习？** 光谱-浓度关系通常是可解释的物理规律（朗伯-比尔定律），几百个样本用小模型（GBDT/SVR）通常优于大模型，且推理极快、无需 GPU。

---

### Q6：RAG 检索增强生成的原理是什么？和 Fine-tuning 的区别？

**标准回答：**

**RAG（Retrieval-Augmented Generation）** 是一种"让 LLM 查阅外部知识库再回答"的模式，核心三阶段：

```
① 索引阶段（离线）
   文档 → 分块（Chunking）→ 嵌入（Embedding）→ 向量数据库（Vector DB）
   例：团队内部技术文档 → text-embedding-3-small → ChromaDB

② 检索阶段（在线）
   用户提问 → 同样生成 Embedding → 向量相似度检索 Top-K 文档块

③ 生成阶段
   Prompt = "根据以下资料回答问题：{Top-K 文档块}\n\n问题：{用户提问}"
   LLM 基于注入的上下文生成回答（带来源引用）
```

**RAG vs Fine-tuning 核心区别：**

| 维度 | RAG | Fine-tuning |
|------|-----|-------------|
| **知识注入方式** | 运行时动态检索 → Prompt 注入 | 训练时修改模型权重 |
| **知识更新** | 💚 即时（更新向量 DB 即可） | 🔴 需重新训练 |
| **可解释性** | 💚 可追溯到具体文档片段 | 🔴 模型是黑盒 |
| **幻觉控制** | 💚 被检索文档约束，幻觉减少 | 🔴 仍可能编造 |
| **成本** | Embedding + 向量库 + LLM API | GPU 训练集群（贵） |
| **适用场景** | 知识库问答、文档助手、客服 | 风格迁移、领域术语、特定格式输出 |

**组合使用（面试亮点）**：RAG + Fine-tuning 可以互补——Fine-tune 让模型学会"如何利用检索到的资料"，RAG 提供最新知识。这就是"RAFT"（Retrieval Augmented Fine-Tuning）范式。

---

### Q7：LangChain 的核心抽象有哪些？Chain / Agent / Tool 分别是什么？

**标准回答：**

LangChain 是 LLM 应用开发框架，核心抽象分层如下：

```
┌──────────────────────────────────────────┐
│  Agent （决策层）                          │
│  "用户要查订单状态 → 我该调 OrderTool"      │
├──────────────────────────────────────────┤
│  Chain （编排层）                          │
│  "先翻译 → 再总结 → 最后分类"               │
├──────────────────────────────────────────┤
│  Tool （能力层）                           │
│  "查数据库 / 调 API / 执行 Python 代码"     │
├──────────────────────────────────────────┤
│  Model + Memory + Retriever（基础层）       │
│  LLM 调用 / 历史对话 / 向量检索             │
└──────────────────────────────────────────┘
```

| 抽象 | 是什么 | 类比 | 示例 |
|------|-------|------|------|
| **Tool** | LLM 可调用的外部函数 | 螺丝刀、锤子 | `OrderLookupTool`、`PythonREPLTool` |
| **Chain** | 固定的多步操作序列 | 装配流水线 | `translate_chain → summarize_chain → classify_chain` |
| **Agent** | 自主决策"用哪个 Tool、什么顺序" | 工人（会自己选工具干活） | 给定用户问题 → Agent 自己决定先查数据库、再算价格、最后格式化输出 |

**核心面试代码模式**：

```python
from langchain.agents import initialize_agent, Tool
from langchain.llms import ChatOpenAI

# 定义工具
tools = [
    Tool(name="OrderLookup", func=lookup_order, description="查询订单状态"),
    Tool(name="RefundCalc", func=calc_refund, description="计算退款金额"),
]

# 初始化 Agent
agent = initialize_agent(
    tools=tools,
    llm=ChatOpenAI(model="gpt-4"),
    agent="zero-shot-react-description"  # ReAct 范式
)

# Agent 自主决策
agent.run("用户 ID 12345 的订单退款多少钱？")
# → Agent 推理: "需要先查订单状态 → 再根据状态计算退款"
# → 自动调用 OrderLookup → RefundCalc → 生成回答
```

**关键洞察**：Agent 的本质是 **LLM 作为路由器**——它不干活，只负责决定"下一步该调哪个 Tool，用什么参数"。真正的执行在 Tool 层。

---

### Q8：Prompt Engineering 的核心技巧有哪些？Few-shot / Chain-of-Thought 怎么用？

**标准回答：**

Prompt Engineering 是"用自然语言编程"——通过精心设计的提示词引导 LLM 输出期望的结果。

**六大核心技巧：**

| 技巧 | 原理 | 示例 |
|------|------|------|
| **Zero-shot** | 不给示例，直接提问 | "将下面的代码从 Java 转成 Kotlin：`{code}`" |
| **Few-shot** | 给 2-5 个输入→输出示例 | "输入：`数据采集` → 英文：`data acquisition`\n输入：`精度回测` → 英文：`accuracy retest`\n输入：`传感器标定` → 英文：" |
| **Chain-of-Thought** | 要求逐步推理 | "分析这段 Systrace 的性能瓶颈。先列出所有耗时任务，再分析依赖关系，最后给出优化建议" |
| **Role Prompting** | 指定角色 | "你是一位资深 Android 性能优化专家，拥有 10 年 Systrace 分析经验..." |
| **Structured Output** | 指定输出格式 | "以 JSON 格式输出：`{"bottleneck": "...", "duration_ms": ..., "fix": "..."}`" |
| **Self-Consistency** | 多次采样取多数 | 同一问题问 5 次，取最一致的答案 |

**实战：用 CoT 做 Perfetto 报告诊断（简历场景）**

```
Prompt:
你是 Android 性能专家。分析以下 Perfetto trace 摘要。
请按照以下步骤推理：
1. 首先，列出主线程上所有耗时超过 16ms 的帧
2. 然后，对每一帧，找出占用时间最长的 3 个调用
3. 接着，分析这些调用之间的依赖关系
4. 最后，给出按优先级排序的优化建议

Perfetto 摘要：
- Frame 1 (73ms): Choreographer#doFrame 68ms → RecyclerView#onBindViewHolder 45ms → Glide#load 18ms
- Frame 2 (42ms): Choreographer#doFrame 38ms → JSON.parse 22ms
- Frame 3 (18ms): OK

请开始分析：
```

**面试加分**：提到 Prompt 也需"版本管理"和"A/B 测试"——不同 prompt 对同一批问题的准确率对比，选最优的进生产。

---

## 🤖 AI Agent 工程化与研发提效

### Q9：AI Agent 和传统 Chatbot 的核心区别是什么？

**标准回答：**

| 维度 | 传统 Chatbot | AI Agent |
|------|-------------|----------|
| **交互模式** | 一问一答（stateless） | 多轮自主行动（goal-driven） |
| **能力边界** | 只能生成文本 | 可以调用工具（查数据库/执行代码/操作文件） |
| **决策能力** | 无——回复由规则或单次 LLM 调用决定 | 有——自主规划步骤、选择工具、处理失败重试 |
| **上下文** | 对话历史 | 对话历史 + 工具调用结果 + 任务状态 |
| **典型架构** | LLM API 直接调用 | LLM + Tool Registry + Memory + Planner |
| **示例** | "今天天气怎么样？" | "帮我分析最近一周的 ANR 日志，找出根因并生成修复建议" |

**Agent 的核心循环（ReAct 范式）：**

```
Observation → Thought → Action → Observation → Thought → Action → ... → Final Answer
  (看到什么)  (该怎么想)  (调什么工具)  (结果如何)  (下一步)    (调工具)        (完成任务)
```

**具体到 Hermes Agent：**

```
用户: "分析当前项目的编译速度瓶颈"
  ↓
Agent Thought: "我需要先拿到 gradle-profile 报告，然后分析耗时任务"
  ↓
Action: terminal("cd project && ./gradlew assembleDebug --profile")  ← Tool Calling
  ↓
Observation: 得到 profile 报告文本
  ↓
Agent Thought: "报告中有 3 个任务超过 30 秒，需要深入分析依赖关系"
  ↓
Action: read_file("build/reports/profile/...")                       ← 文件工具
  ↓
... 多轮推理 ...
  ↓
Final Answer: "瓶颈在 :app:mergeDebugResources (45s)，建议开启 build-cache 并使用资源优化"
```

**一句话总结**：Chatbot 是"嘴巴"，Agent 是"有手有脑"。Agent 能操作外部世界（文件系统、网络、API、数据库），Chatbot 只能说话。

---

### Q10：Tool Calling 的工作原理是怎样的？函数签名如何被 LLM 理解？

**标准回答：**

Tool Calling（Function Calling）是 LLM 调用外部工具的核心机制。整个流程分三步：

```
① 系统告知 LLM "有哪些工具可用"
   将工具的 JSON Schema（名称/描述/参数类型）注入 System Prompt

② LLM 决策是否需要调用工具
   LLM 输出不是自然语言，而是结构化的 tool_call 指令
   {"name": "read_file", "parameters": {"path": "/app/config.json"}}

③ 宿主程序执行工具并返回结果给 LLM
   工具执行 → 结果注入为新的上下文 → LLM 继续推理
```

**函数签名的 JSON Schema 示例：**

```json
{
  "name": "analyze_systrace",
  "description": "分析 Systrace 文件，提取耗时超过 16ms 的帧及其调用栈",
  "parameters": {
    "type": "object",
    "properties": {
      "trace_path": {
        "type": "string",
        "description": "Systrace HTML 文件的绝对路径"
      },
      "threshold_ms": {
        "type": "integer",
        "description": "耗时阈值，默认 16ms",
        "default": 16
      }
    },
    "required": ["trace_path"]
  }
}
```

**LLM 为什么能"理解"这些 Schema 并正确调用？**

- LLM 在预训练阶段见过大量 API 文档和技术规范，已经学会了"函数签名→功能"的映射
- `description` 字段是自然语言，LLM 天然理解
- 现代模型（GPT-4、Gemini）经过专门的 Function Calling 微调，输出格式稳定

**Hermes Agent 的 Tool Calling 特点**：工具注册表包含 `terminal`（执行 shell 命令）、`read_file`（读文件）、`search_files`（搜索代码）、`delegate_task`（委派子任务）、`cronjob`（定时调度）等。Agent 根据用户意图自动选择工具组合，而非人工编排。

**面试加分**：提到"工具选择的容错设计"——LLM 选错工具时，系统可以通过工具返回的错误信息让 LLM 自我纠正（self-correction），无需人工介入。

---

### Q11：Agent 的 Skill 管理和复用机制是怎样的？和微服务有什么区别？

**标准回答：**

**Skill 是 Agent 的"可复用能力单元"**——将完成某类任务的方法论（步骤、命令、脚本）封装为 Skill，供 Agent 在不同场景下加载使用。

**Skill 的结构（以 Hermes Agent 为例）：**

```
skill: compile-diagnosis
├── SKILL.md          ← 核心：触发条件 + 分步流程 + 常见陷阱
├── scripts/
│   └── analyze_profile.py  ← Python 脚本（编译 profile 解析）
├── templates/
│   └── report.md           ← 诊断报告模板
└── references/
    └── gradle_flags.md     ← 参考文档（优化 flags 速查）
```

**Skill 复用的三个阶段：**

```
创建阶段：完成一次复杂任务后 → 沉淀为 Skill
    "解决了编译慢的问题 → 把分析流程写成 compile-diagnosis skill"

加载阶段：新对话中 Agent 根据任务自动判断 → 加载相关 Skill
    "用户问编译问题 → skill_view('compile-diagnosis') → Agent 遵循 Skill 中的步骤"

共享阶段：Skill 在团队/社区间共享
    "团队成员都可以用 compile-diagnosis skill，无需重复探索"
```

**Skill vs 微服务：**

| 维度 | Skill | 微服务 |
|------|-------|--------|
| **存在形式** | Markdown 文档 + 脚本 | 独立进程 + API |
| **执行方式** | LLM 读完 Skill → 自己按步骤调用工具 | HTTP/RPC 调用 |
| **"智能"程度** | LLM 理解 Skill 后灵活变通 | 固定逻辑，不灵活 |
| **更新方式** | 改 Markdown 即时生效 | 重新部署 |
| **适用场景** | 需要推理的复杂任务 | 确定性计算/存储 |

**关键面试洞察**：Skill 不是自动化脚本——脚本是固定流程，Skill 是"给 Agent 装上一个领域专家的知识"；Agent 拿到 Skill 后可以灵活组合、判断例外、调整方案，这是微服务做不到的。

---

### Q12：Cron Job 异步任务在 Agent 系统中如何实现上下文注入？

**标准回答：**

Agent 的 Cron Job 是一个"定时唤醒 → 注入上下文 → 执行任务 → 返回结果"的闭环。

**Hermes Agent Cron Job 的工作机制：**

```
┌─────────────────────────────────────────────────────┐
│  Cron Scheduler                                       │
│  "每天 9:00 触发 build-health-check job"              │
├─────────────────────────────────────────────────────┤
│  ① 唤醒 → 新 Agent Session                            │
│  ② 加载 Skill（可选）→ 注入 Skill 知识               │
│  ③ 执行 Script（可选）→ 收集数据为上下文              │
│     │  例：script 拉取昨晚的 CI 构建结果              │
│     │  stdout 自动注入为 Agent 的 context              │
│  ④ 注入 context_from（可选）→ 上游 Job 的输出        │
│     │  例：job-A 收集 ANR 数据 → job-B 分析          │
│  ⑤ Agent 处理 prompt → 生成报告                      │
│  ⑥ deliver → 推送到 Discord/Telegram/当前对话        │
└─────────────────────────────────────────────────────┘
```

**上下文注入的三种方式：**

| 方式 | 配置字段 | 原理 | 场景 |
|------|---------|------|------|
| **Script 输出** | `script` | Script stdout 注入为 Agent 上下文 | 数据采集（拉 CI 报告、监控磁盘） |
| **上游 Job 输出** | `context_from` | 引用其他 Job 的最后一次输出 | Job 链（采集→分析→报告） |
| **Skill 内容** | `skills` | Skill 的 SKILL.md 注入为系统知识 | 领域方法（编译诊断、性能分析） |

**实际 Job 链示例（简历场景）：**

```
Job A: anr-collector (script + no_agent=true)
  → 每天 8:00 运行 Python 脚本，拉取昨日 ANR 统计
  → stdout: "ANR 总数: 12, 应用无响应: 8, 广播超时: 4"

Job B: anr-analyzer (context_from=["job-A-id"], skills=["anr-diagnosis"])
  → 每天 8:15 运行，拿到 Job A 的输出作为上下文
  → Prompt: "基于以下 ANR 数据，分析趋势和根因"
  → Agent 按 anr-diagnosis skill 的步骤分析
  → 结果自动推送到团队 Discord 频道
```

**为什么上下文注入比"Agent 自己获取"更好？**
- **确定性**：Script 的输出是固定的，不依赖 LLM 的"猜测"
- **效率**：避免 Agent 浪费 Token 去"尝试获取数据"
- **解耦**：采集和分析分离，各 Job 独立维护

---

### Q13：用 Gemini in Android Studio 辅助性能诊断的具体工作流是怎样的？

**标准回答：**

这是 AI + Android 研发的**实战交叉点**——利用 Gemini 的代码理解能力做性能诊断，而非让它"写代码"。

**完整工作流：**

```
① 采集性能数据（工具层）
   ├─ Systrace / Perfetto → 得到 trace 文件
   ├─ Android Studio Profiler → CPU/Memory/Energy 火焰图
   └─ LeakCanary → 内存泄漏堆栈

② 提取关键信息（人工 + 工具辅助）
   ├─ 从 Systrace 中提取：耗时 >16ms 的帧列表 + 对应线程调用栈
   ├─ 从 Profiler 中提取：热点方法 Top 10
   └─ 整理为结构化文本

③ 与 Gemini 对话诊断（核心 AI 环节）
   ├─ 粘贴 trace 摘要 + 相关代码片段
   ├─ 使用 CoT Prompt 引导分步推理
   └─ Gemini 分析依赖关系、识别根因

④ 验证 AI 建议
   ├─ Gemini 提出优化方案 → 人工评估可行性
   ├─ 实施修改 → 重新采集性能数据验证
   └─ 形成闭环
```

**具体示例对话：**

```
开发者: （粘贴 Perfetto 片段 + RecyclerView Adapter 代码）
  这段 trace 显示 onBindViewHolder 耗时 45ms，但我的 onBind 只做了简单
  的文本设置。分析可能原因并按优先级给出修复建议。

Gemini: 基于你提供的 trace 和代码，我注意到以下问题：

  优先级 1（高） - 嵌套布局
  onBindViewHolder 中 inflate 的 item_layout.xml 有 3 层嵌套 LinearLayout。
  即使你的 onBind 只是 setText，layout measure/layout 过程会递归遍历整棵
  视图树。 → 建议：用 ConstraintLayout 扁平化为 1 层

  优先级 2（中） - 不必要的对象分配
  trace 显示 GC 暂停了 8ms。你的 onBind 中每次调用 DateFormat.format()
  都创建了新的 Calendar 实例。 → 建议：复用 DateFormat 实例

  优先级 3（低） - 图片解码
  虽然你用的是 Glide，但 trace 中 BitmapFactory.decodeStream 占了 12ms。
  → 建议：检查是否缺少 override(size) 导致解码了原图大小
```

**Gemini in AS 的 4 种日常使用模式：**

| 模式 | 快捷键/操作 | 场景 |
|------|-----------|------|
| **代码补全** | 敲代码自动触发 | 减少样板代码 |
| **选中解释** | 选中代码 → 右键 → Explain Code | 理解陌生代码 |
| **对话诊断** | Gemini 侧边栏 | 粘贴 trace/bug 报告 → 诊断 |
| **生成测试** | 选中方法 → 右键 → Generate Unit Tests | 自动生成测试骨架 |

---

### Q14：AI Agent 如何嵌入日常 Android 研发闭环？

**标准回答：**

这是简历中 **"AI 开发工具全栈：Hermes Agent + Gemini in AS + Copilot"** 的具体落地，形成覆盖开发全流程的 AI 增强闭环：

```
┌─────────────────────────────────────────────────────────┐
│                    AI 增强研发闭环                        │
│                                                         │
│  ① 架构/方案设计                                        │
│     ↓ Hermes Agent: "分析我的需求, 对比 3 种方案优劣"    │
│  ② 编码实现                                             │
│     ↓ Gemini + Copilot: 智能补全 + Bug 修复 + 重构建议   │
│  ③ 编译/构建                                            │
│     ↓ Hermes Cron Job: 定时检查编译时间趋势, 异常告警    │
│  ④ 测试验证                                             │
│     ↓ Hermes Agent: 分析失败用例日志, 推断根因           │
│  ⑤ 性能诊断                                             │
│     ↓ Gemini: Perfetto/Systrace 语义分析                 │
│  ⑥ 文档/总结                                            │
│     ↓ Hermes Agent: "根据本次迭代的 commit log, 生成     │
│        周报和变更摘要"                                    │
└─────────────────────────────────────────────────────────┘
```

**三个工具的分工（面试标准答案）：**

| 工具 | 擅长的 | 不擅长的 |
|------|--------|---------|
| **Hermes Agent** | 异步编排、多步骤推理、文件操作、定时任务、跨会话上下文 | 代码补全（太慢） |
| **Gemini in AS** | 代码级智能（补全/重构/诊断）、IDE 深度集成 | 跨文件任务编排、定时调度 |
| **Copilot** | 极速代码补全、模式识别 | 复杂推理、上下文理解 |

**面试加分**：强调"AI 不是替代开发者，而是扩展开发者的能力带宽"——Agent 处理重复性分析工作（编译诊断、日志分析、报告生成），开发者聚焦架构决策和创造性编码。

---

## 面试应答总结

| 能力板块 | 面试关键词 | 一句话总结 |
|---------|-----------|-----------|
| 端侧 AI | TFLite / NNAPI / Delegate / 量化 | "我能在 Android 设备上部署 AI 模型，并选最优推理后端" |
| 数据处理 | Pandas / NumPy / Scikit-learn Pipeline | "我能用 Python 做完整的数据→特征→模型→部署闭环" |
| LLM 应用 | RAG / LangChain / Prompt Engineering | "我理解 LLM 的能力边界，会用 RAG 解决幻觉问题" |
| AI Agent | Tool Calling / Skill / Cron Job / ReAct | "我能把日常研发工作拆解为 Agent 可编排的技能链" |
| AI + Android | Gemini in AS / Systrace 诊断 / 研发闭环 | "我有一整套 AI 辅助 Android 研发的实战方法论" |
