# 动画系统

---

## 1. 面试问题（≥5）

### Q1: View动画 vs 属性动画 vs 转场动画的区别和选型？

**面试场景**：这是高频考点，面试官考察对动画体系的整体认知，尤其在复杂交互场景下的选型能力。

**区别对照表**：

| 维度 | View动画（补间动画） | 属性动画 | 转场动画（Transition） |
|------|---------------------|----------|------------------------|
| **作用对象** | 仅限 View | 任意对象（Object） | ViewGroup 场景切换 |
| **实际属性** | 不改变，仅视觉效果 | 真实改变属性值 | 改变布局属性 |
| **点击区域** | 保持原始位置 | 跟随动画变化 | 跟随最终布局 |
| **自定义能力** | 受限（4种基本变换） | 极强（任意属性） | 中等（布局变化） |
| **引入版本** | API 1 | API 11 (Android 3.0) | API 19 (Android 4.4) |
| **硬件加速** | 支持 | 支持 | 支持 |
| **性能** | 高（仅 Canvas 变换） | 中（反射调用） | 中（Layout 计算） |

**选型指南**：
- **View动画**：简单进场/退场效果（Activity 切换）、无交互需求的纯视觉效果
- **属性动画**：需要交互反馈、动态改变 View 真实属性（如拖拽回弹）、自定义 View 动画
- **转场动画**：场景切换（Fragment/Activity 切换）、布局变化过渡

---

### Q2: ObjectAnimator 和 ValueAnimator 的原理和使用区别？

**ValueAnimator**：核心引擎，只负责数值变化。

```java
ValueAnimator animator = ValueAnimator.ofFloat(0f, 1f);
animator.addUpdateListener(new ValueAnimator.AnimatorUpdateListener() {
    @Override
    public void onAnimationUpdate(ValueAnimator animation) {
        float fraction = animation.getAnimatedFraction();
        float value = (float) animation.getAnimatedValue();
        view.setAlpha(value); // 手动设置属性
    }
});
animator.start();
```

**ObjectAnimator**：ValueAnimator 的子类，自动通过反射设置目标对象的属性。

```java
ObjectAnimator.ofFloat(view, "alpha", 0f, 1f).start();
```

**关键区别**：
1. ObjectAnimator 要求目标对象必须有对应的 getter/setter（如 `setAlpha(float)`），否则 Crash
2. ValueAnimator 更灵活，可在回调中做任意逻辑
3. ObjectAnimator 内部通过 PropertyValuesHolder 实现多属性并行动画
4. 性能：ObjectAnimator 有反射开销（Android 7.0+ 已优化为 JNI 直接调用）

---

### Q3: 插值器（Interpolator）和估值器（TypeEvaluator）的角色和自定义方式？

**插值器（Interpolator）**：控制动画「节奏」——输入 0~1 的线性时间流逝，输出 0~1 的进度偏移（可超出）。

```java
// 自定义：先快后慢再弹
public class BounceInterpolator implements Interpolator {
    @Override
    public float getInterpolation(float input) {
        // input: 线性时间 0→1，output: 偏移进度
        return (float) (1 - Math.pow(1 - input, 3) + Math.sin(input * Math.PI * 3) * 0.1);
    }
}
```

**估值器（TypeEvaluator）**：控制动画「数值」——根据 fraction(0~1) 计算具体值。

```java
// 自定义：颜色估值器
public class ColorEvaluator implements TypeEvaluator<Integer> {
    @Override
    public Integer evaluate(float fraction, Integer startValue, Integer endValue) {
        int startR = (startValue >> 16) & 0xFF;
        int startG = (startValue >> 8) & 0xFF;
        int startB = startValue & 0xFF;
        int endR = (endValue >> 16) & 0xFF;
        int endG = (endValue >> 8) & 0xFF;
        int endB = endValue & 0xFF;
        int r = (int) (startR + fraction * (endR - startR));
        int g = (int) (startG + fraction * (endG - startG));
        int b = (int) (startB + fraction * (endB - startB));
        return 0xFF000000 | (r << 16) | (g << 8) | b;
    }
}
```

**三者的协作流水线**：

```
VSYNC信号 → 当前时间 → 计算elapsed比率(t)
  → Interpolator.getInterpolation(t) → fraction(节奏偏移)
    → TypeEvaluator.evaluate(fraction, start, end) → value(实际数值)
      → 属性setter设置 / onAnimationUpdate回调
```

---

### Q4: 动画卡顿原因（GPU Overdraw + 主线程阻塞）与硬件层优化？

**卡顿原因**：

1. **GPU Overdraw（过度绘制）**：同一像素被绘制多次（>2.5x 会明显掉帧）
   - 检测：开发者选项 → 调试 GPU 过度绘制
   - 动画期间 View 不断重绘，Overdraw 叠加导致 pixel fill rate 瓶颈

2. **主线程阻塞**：
   - 动画帧回调在 Choreographer 的 `CALLBACK_ANIMATION` 阶段
   - 若 measure/layout/draw 超时（>16ms），掉帧
   - 属性动画的反射调用（setter）可能触发 requestLayout

3. **频繁 invalidate**：动画每一帧触发 View.invalidate() → 全树绘制遍历

**优化方案**：

```java
// 1. 启用硬件层（将 View 渲染到 FBO，减少重绘）
view.setLayerType(View.LAYER_TYPE_HARDWARE, null);
ObjectAnimator animator = ObjectAnimator.ofFloat(view, "scaleX", 1f, 1.5f);
animator.addListener(new AnimatorListenerAdapter() {
    @Override
    public void onAnimationEnd(Animator animation) {
        view.setLayerType(View.LAYER_TYPE_NONE, null); // 动画结束必须释放
    }
});
animator.start();
```

- **硬件层原理**：View 及其子 View 被光栅化到一块 FBO（Frame Buffer Object）纹理中，动画期间只做 GPU 矩阵变换（translate/scale/rotate/alpha），无需每帧执行 draw() 遍历
- **注意**：LAYER_TYPE_HARDWARE 占用 GPU 显存（View 尺寸 × 4 bytes RGBA），动画结束必须 `setLayerType(LAYER_TYPE_NONE)` 释放
- **软件层**（LAYER_TYPE_SOFTWARE）：用于不支持硬件加速的场景，原理类似但缓存到内存位图

---

### Q5: 共享元素转场（SharedElementTransition）的实现原理？

**三要素**：
1. `transitionName`：源和目标 View 绑定同一个唯一名称
2. `Transition`：定义动画行为（ChangeBounds, ChangeTransform, ChangeClipBounds 等）
3. `TransitionSet`：组合多个 Transition 同步执行

**源码原理流程**：

```
Activity A → Activity B (共享元素转场)
  │
  ├─ setExitSharedElementCallback()  // 源 Activity：收集共享元素信息
  │    ├─ ViewOverlay 中捕获源 View 的 Bitmap 快照
  │    └─ 记录源 View 的位置、大小、Matrix 状态
  │
  ├─ setEnterSharedElementCallback() // 目标 Activity：接收共享元素
  │    ├─ postponeEnterTransition()  // 延迟转场，等待 View 就绪
  │    ├─ 目标 View 通过 transitionName 匹配
  │    └─ 计算源位置→目标位置的变换矩阵
  │
  └─ Transition.TransitionListener
       ├─ onTransitionStart: 隐藏真实 View，只显示快照
       ├─ 动画执行中: 快照从源位置移动到目标位置
       └─ onTransitionEnd: 隐藏快照，显示真实 View
```

**关键类**：
- `TransitionValues`：记录 View 的 property 快照（位置、大小、可见性等）
- `ChangeBounds`：捕获 left/top/right/bottom → 动画位置变化
- `ChangeTransform`：捕获 scaleX/scaleY/rotation → 动画变换
- `ChangeImageTransform`：专门处理 ImageView 的 matrix 变换（如 scaleType）

---

### Q6: AnimatorSet 的 playSequentially / playTogether 执行机制？

```java
AnimatorSet set = new AnimatorSet();
set.playTogether(
    ObjectAnimator.ofFloat(view, "scaleX", 1f, 1.5f),
    ObjectAnimator.ofFloat(view, "scaleY", 1f, 1.5f),
    ObjectAnimator.ofFloat(view, "alpha", 1f, 0.5f)
);
set.playSequentially(
    ObjectAnimator.ofFloat(view, "translationX", 0, 200),
    ObjectAnimator.ofFloat(view, "rotation", 0, 360)
);
set.start();
```

**内部机制**：

- **playTogether**：所有子动画共享同一个 `startDelay` 基准，同时启动。内部通过 `AnimatorSet.Builder` 构建依赖图（实际上依赖同一个 dummy 节点）
- **playSequentially**：构建链式依赖——前一个动画的 `end` 事件触发下一个动画的 `start`
- **核心数据结构**：`Node` 类（链表节点）存储每个 animator 及其依赖关系（`dependencies` List）
- **执行引擎**：监听每个 child animator 的 `onAnimationEnd`，遍历 Node 链表找到下一个 `dependencies` 全部满足的节点启动

**进阶用法**：

```java
// play().with().before().after() 构建复杂依赖
AnimatorSet set = new AnimatorSet();
set.play(anim2).with(anim3).after(anim1).before(anim4);
// 等价于：anim1 → [anim2, anim3 并行] → anim4
```

---

### Q7: 帧动画（Frame Animation）的 OOM 风险和替代方案？

**OOM 原理**：

```xml
<!-- animation_list.xml — 每帧是一张完整 Bitmap -->
<animation-list>
    <item android:drawable="@drawable/frame_01" android:duration="50" />
    <item android:drawable="@drawable/frame_02" android:duration="50" />
    <!-- ... 30帧 1080p → 30 × 1920 × 1080 × 4 = 约237MB！-->
</animation-list>
```

- 所有帧在 AnimationDrawable.start() 时全部加载到内存
- 无分帧释放机制 → 序列帧越多 OOM 风险越大

**替代方案**：

| 方案 | 适用场景 | 内存占用 | 灵活性 |
|------|---------|----------|--------|
| **Lottie** | 矢量动画（JSON 描述） | 极低（矢量 + 缓存池） | 高（可交互） |
| **属性动画组合** | 简单动效 | 无额外内存 | 中 |
| **AnimatedVectorDrawable** | 矢量路径变换 | 低 | 低 |
| **逐帧（手动管理）** | 必须使用位图帧 | 可控（手动 decode/recycle） | 高 |

**Lottie 工作原理**：
- 解析设计师导出的 JSON（来自 After Effects）+ 图片资源
- 将图层结构映射为 Android Canvas 绘制指令
- 每帧遍历图层树 → 应用 Transform（Matrix）→ 绘制到 Canvas
- 支持动态替换颜色/文字、进度控制、交互绑定

---

## 2. 标准答案（结构化 + 性能对比）

### 动画体系总览

Android 动画体系分三层：

1. **View 动画层**（AlphaAnimation / ScaleAnimation / TranslateAnimation / RotateAnimation）
2. **属性动画层**（ValueAnimator / ObjectAnimator / AnimatorSet）
3. **转场动画层**（Transition Framework：Scene + Transition + TransitionManager）

### 性能对比矩阵

| 性能维度 | View 动画 | 属性动画 | 帧动画 | Lottie | Transition |
|----------|----------|---------|--------|--------|-------------|
| **CPU 占用** | 低（Matrix 运算） | 中（反射 + invalidate） | 高（Bitmap decode+draw） | 中（Canvas draw） | 中（Layout + draw） |
| **GPU 占用** | 低（纹理变换） | 低~中 | 高（大纹理上传） | 中（矢量光栅化） | 低~中 |
| **内存增量** | ~0 | ~0 | **极高**（所有帧） | 低（矢量数据） | ~0 |
| **掉帧风险** | 低 | 中（复杂 View 树） | 高（大位图） | 低（缓存优化） | 中 |
| **启用硬件层后** | 已隐含 | **显著提升** | 无帮助 | 已内置 | 部分场景 |

### 面试标准回答模板

> "Android 动画选型核心看两点：是否需要改变 View 的真实属性、以及动画的复杂度。
>
> 如果只需视觉效果（如页面淡入），View 动画足够且性能最优，因为只做 Canvas Matrix 变换不触发 invalidate；
>
> 如果动画需要交互反馈（如按钮按下缩放后响应点击），必须使用属性动画，因为 View 动画不改变实际位置导致点击区域错位；
>
> 对于页面切换场景，Transition 框架是最好的选择，它自动捕获布局变化并生成过渡动画，配合 SharedElement 可以实现流畅的共享元素转场；
>
> 如果是复杂矢量动画（如 Lottie 图标），避免使用帧动画（容易 OOM），改用 Lottie 或 AnimatedVectorDrawable，后者内存占用降低 90% 以上。"

---

## 3. 核心原理

### 3.1 属性动画执行原理（VSYNC → 属性设置完整链路）

```
┌────────────────────── 属性动画完整执行链路 ──────────────────────┐

Display (硬件)
  │ 每 16.6ms (60Hz) 发出 VSYNC 信号
  ▼
Choreographer.doFrame(frameTimeNanos)
  │ FrameCallback 优先级顺序：
  │   1. CALLBACK_INPUT         (输入事件)
  │   2. CALLBACK_ANIMATION     (动画)         ← 动画在这里
  │   3. CALLBACK_INSETS_ANIMATION
  │   4. CALLBACK_TRAVERSAL     (measure/layout/draw)
  │   5. CALLBACK_COMMIT        (提交)
  ▼
ValueAnimator.doAnimationFrame(frameTime)
  │ 1. 计算 fraction：
  │    elapsed = frameTime - mStartTime
  │    fraction = elapsed / mDuration
  │    fraction = clamp(fraction, 0.0, 1.0)   // 限制范围
  │ 2. 插值器变换：
  │    interpolatedFraction = mInterpolator.getInterpolation(fraction)
  │ 3. 估值器计算：
  │    value = mEvaluator.evaluate(interpolatedFraction, startValue, endValue)
  │ 4. 通知监听器：
  │    onAnimationUpdate(animator) → mAnimatedValue = value
  ▼
ObjectAnimator (继承 ValueAnimator)
  │ 5. 属性设置（JNI 反射调用）：
  │    target.setPropertyName(value)          // 如 view.setScaleX(1.5)
  │    或通过 PropertyValuesHolder.setAnimatedValue(target)
  ▼
View 属性变更
  │ 6. View.invalidate() → 触发重绘
  │    (某些属性如 alpha/scale 触发 invalidate，
  │     translationX/Y 仅触发 invalidate 不触发 requestLayout)
  ▼
View.draw(canvas)  →  RenderNode.displayList  →  GPU 合成  → 显示
```

### 3.2 View 动画的 Matrix 变换原理

```
View.draw(canvas) 流程：

  drawBackground(canvas)
  │
  ▼
  if (hasAnimation()) {
      final Animation anim = getAnimation();
      final Transformation transformation = mTransformation;
      
      // 1. 计算当前变换矩阵
      anim.getTransformation(drawTime, transformation);
      //    内部：interpolator.getInterpolation(fraction)
      //         → Transformation.getMatrix() 组装 Matrix
      
      // 2. canvas.concat(transformation.getMatrix())
      //    → 应用 translate/rotate/scale/alpha 到 Canvas
      
      alpha = transformation.getAlpha();  // 透传给 RenderNode
  }
  │
  ▼
  onDraw(canvas)  // ← View 自身 draw 不感知 Matrix 变化！
  │
  ▼
  dispatchDraw(canvas)
```

**关键结论**：
- View 动画只在 `draw()` 阶段修改 Canvas 的变换矩阵
- `getLeft()/getTop()/getRight()/getBottom()` 不变化
- `getWidth()/getHeight()` 不变化
- **点击热区不变** → 画面上的按钮移动了，但点击原始位置仍能触发

### 3.3 硬件层（Hardware Layer）原理

```
普通渲染流程（每帧）：
  VSYNC → dispatchDraw → onDraw → drawText → drawBitmap
                                   ↑ 每帧都执行完整绘制树！
  GPU:
    framebuffer ← 合成所有 RenderNode

启用 HARDWARE Layer 的渲染流程：
  第一帧（创建 FBO）：
    onDraw → 光栅化到 FBO 纹理 (offscreen buffer)
  
  后续帧（仅动画期间）：
    GPU 直接操作 FBO 纹理：
      - glTranslate → texture matrix
      - glScale     → texture matrix  
      - glRotate    → texture matrix
      - Alpha 混合
    完全跳过 onDraw() 调用！
  
  动画结束：
    glDeleteTextures → 释放 FBO
    setLayerType(LAYER_TYPE_NONE) → 回归正常渲染
```

**关键限制**：
- FBO 是静态快照，层内子 View 的动画不会更新（除非重新 invalidate 触发重绘）
- 适用于：整个 View 做平移/缩放/旋转/透明度的属性动画
- 不适用于：层内某子 View 独立动画、颜色渐变（需每帧重绘）

### 3.4 Transition 框架的 Scene + Transition + TransitionManager

```java
// Scene 1 → Scene 2 的自动过渡
Scene scene1 = Scene.getSceneForLayout(rootView, R.layout.scene1, context);
Scene scene2 = Scene.getSceneForLayout(rootView, R.layout.scene2, context);

Transition transition = new AutoTransition(); // Fade + ChangeBounds
TransitionManager.go(scene2, transition);
```

**内部机制**：
1. `Scene.enter()`：将新布局 inflate 到 rootView
2. `TransitionManager.go()`：
   - 捕获 `scene1` 中所有 View 的 `TransitionValues`（快照）
   - 执行 `scene2.enter()` 替换布局
   - 捕获 `scene2` 中对应 View 的 `TransitionValues`
   - 为每个变化的 View 创建动画：从 startValues → endValues
   - 通过 `Transition.playTransition()` 在 Animator 中执行

### 3.5 Choreographer 回调优先级和动画帧注册

```
Choreographer.FrameCallback 优先级（值越小越先执行）：

  CALLBACK_INPUT         = 0    → 处理触摸事件
  CALLBACK_ANIMATION     = 1    → ValueAnimator/ViewPropertyAnimator
  CALLBACK_INSETS_ANIMATION = 2 → 键盘/状态栏动画
  CALLBACK_TRAVERSAL     = 3    → ViewRootImpl.doTraversal() → performTraversals()
  CALLBACK_COMMIT        = 4    → 帧提交完成回调

动画在 CALLBACK_ANIMATION 阶段执行：
  - 先于 measure/layout/draw
  - 动画更新的属性值在当帧的 draw 中立即生效
  - 保证动画值是最新的

注册方式：
  Choreographer.getInstance()
      .postFrameCallback(Choreographer.CALLBACK_ANIMATION, 
          new Choreographer.FrameCallback() {
              @Override
              public void doFrame(long frameTimeNanos) { }
          }, null);
```

---

## 4. 流程图

### 4.1 属性动画执行时序图

```mermaid
sequenceDiagram
    participant Display as Display (硬件)
    participant Choreo as Choreographer
    participant VA as ValueAnimator
    participant OA as ObjectAnimator
    participant Interp as Interpolator
    participant Eval as TypeEvaluator
    participant View as View (target)

    Display->>Choreo: VSYNC (每16.6ms)
    Choreo->>Choreo: doFrame(frameTimeNanos)
    Choreo->>VA: doAnimationFrame(frameTime) ⚡CALLBACK_ANIMATION
    
    alt 动画已完成
        VA-->>Choreo: return (移除回调)
    end

    VA->>VA: fraction = elapsed / duration
    VA->>Interp: getInterpolation(fraction)
    Interp-->>VA: interpolatedFraction
    
    alt has mEvaluator && startValue/endValue set
        VA->>Eval: evaluate(interpolatedFraction, start, end)
        Eval-->>VA: animatedValue
    end

    VA->>VA: notifyUpdateListeners(onAnimationUpdate)
    
    VA-->>OA: animateValue(interpolatedFraction)
    OA->>OA: 遍历 PropertyValuesHolder[]
    OA->>View: target.setProperty(value) ⚡反射/JNI
    View->>View: mScaleX = value; invalidate()
    
    Note over Choreo,View: 后续 CALLBACK_TRAVERSAL 阶段
    Choreo->>View: performTraversals() → draw()
    View-->>Display: RenderNode → GPU → 上屏
```

### 4.2 View动画 vs 属性动画绘制流程对比

```mermaid
flowchart TD
    subgraph VA[View 动画流程]
        VA_VSYNC[VSYNC 信号]
        VA_ANIM[Animation.getTransformation<br/>计算 Matrix + Alpha]
        VA_CANVAS[canvas.concat(matrix)<br/>修改 Canvas 变换]
        VA_DRAW[onDraw / dispatchDraw<br/>View 内容绘制不变]
        VA_OUT[输出：视觉位置变化<br/>实际位置不变 ❌]
        
        VA_VSYNC --> VA_ANIM --> VA_CANVAS --> VA_DRAW --> VA_OUT
    end

    subgraph PA[属性动画流程]
        PA_VSYNC[VSYNC 信号]
        PA_INTERP[Interpolator.getInterpolation]
        PA_EVAL[TypeEvaluator.evaluate]
        PA_SETTER[target.setProperty(value)<br/>反射设置真实属性]
        PA_LAYOUT[requestLayout / invalidate<br/>触发测量和重绘]
        PA_OUT[输出：视觉 + 实际位置<br/>都改变 ✅]
        
        PA_VSYNC --> PA_INTERP --> PA_EVAL --> PA_SETTER --> PA_LAYOUT --> PA_OUT
    end

    VA_VSYNC -.->|同一 Choreographer| PA_VSYNC
    
    style VA fill:#ffe6e6,stroke:#cc0000
    style PA fill:#e6ffe6,stroke:#00cc00
```

---

## 5. 源码分析

### 5.1 ObjectAnimator.start() 完整调用链

```java
// ==================== 入口：ObjectAnimator.start() ====================
public class ObjectAnimator extends ValueAnimator {
    
    @Override
    public void start() {
        // 1. 先调用父类 ValueAnimator.start()
        super.start();
    }
}

// ==================== ValueAnimator.start() ====================
public class ValueAnimator extends Animator {
    
    @Override
    public void start() {
        start(false);
    }
    
    private void start(boolean playBackwards) {
        // 2. 检查 Looper（必须在线程有 Looper 的线程调用）
        if (Looper.myLooper() == null) {
            throw new AndroidRuntimeException("Animators may only be run on Looper threads");
        }
        
        mReversing = playBackwards;
        mSelfPulse = !mSuppressSelfPulseRequested;
        
        // 3. 重置相关状态
        mStarted = true;
        mPaused = false;
        mRunning = true;
        mAnimationEndRequested = false;
        
        // 4. 初始化动画参数
        mStartTime = -1; // 将在第一帧时设置为当前时间
        mDuration = mUnscaledDuration;
        
        // 5. 添加动画帧回调到 Choreographer
        addAnimationCallback(0); // delay = 0
        
        // 6. 如果有 startDelay，直接播放第一帧为起始值
        if (mStartDelay == 0 || mSeekFraction >= 0 || mReversing) {
            startAnimation();
            if (mSeekFraction == -1) {
                setCurrentPlayTime(0); // 立即设置初始值
            }
        }
    }
    
    // ==================== addAnimationCallback ====================
    private void addAnimationCallback(long delay) {
        if (!mSelfPulse) return;
        
        getAnimationHandler().addAnimationFrameCallback(this, delay);
        // AnimationHandler 内部：
        //   → Choreographer.postFrameCallback(CALLBACK_ANIMATION, mFrameCallback, null)
        //   → 或通过 AnimationHandler.mAnimationCallbacks 延迟回调
    }
}

// ==================== AnimationHandler (内部类) ====================
// packages/apps/...  →  frameworks/base/core/java/android/animation/AnimationHandler.java
class AnimationHandler {
    private final Choreographer.FrameCallback mFrameCallback = 
        new Choreographer.FrameCallback() {
            @Override
            public void doFrame(long frameTimeNanos) {
                doAnimationFrame(getProvider().getFrameTime());
            }
        };
    
    private void doAnimationFrame(long frameTime) {
        long currentTime = SystemClock.uptimeMillis();
        
        // 遍历 mAnimationCallbacks（即 ValueAnimator 实例）
        for (int i = mAnimationCallbacks.size() - 1; i >= 0; i--) {
            AnimationFrameCallback callback = mAnimationCallbacks.get(i);
            if (callback == null) continue;
            
            if (isCallbackDue(callback, currentTime)) {
                callback.doAnimationFrame(frameTime);
            }
        }
        cleanUpList();
    }
}

// ==================== ValueAnimator.doAnimationFrame() ====================
public final boolean doAnimationFrame(long frameTime) {
    // 1. 第一帧初始化起始时间
    if (mStartTime < 0) {
        mStartTime = mReversing ? frameTime : frameTime + (long) (mStartDelay * resolveDurationScale());
    }
    
    // 2. 计算当前时间（处理 pause 和 startDelay）
    // ...
    
    // 3. 计算 fraction
    float fraction = mDuration > 0 
        ? (float) (currentTime - mStartTime) / mDuration 
        : 1f;
    fraction = Math.min(fraction, 1.0f);
    fraction = Math.max(fraction, 0.0f);
    
    // 4. 应用插值器
    float interpolatedFraction = mInterpolator != null 
        ? mInterpolator.getInterpolation(fraction) 
        : fraction;
    
    // 5. 触发 animateValue（ObjectAnimator 覆写）
    animateValue(interpolatedFraction);
    
    return animateFinished;
}

// ==================== ObjectAnimator.animateValue() ====================
// 这是 ObjectAnimator 覆写父类的关键方法
@Override
void animateValue(float fraction) {
    // 应用 Interpolator（已在父类中处理）
    fraction = mInterpolator != null 
        ? mInterpolator.getInterpolation(fraction) 
        : fraction;
    
    super.animateValue(fraction); // 通知所有 onAnimationUpdate 监听器
    
    // 遍历 PropertyValuesHolder[]
    int numValues = mValues.length;
    for (int i = 0; i < numValues; i++) {
        mValues[i].setAnimatedValue(mTarget); // 通过反射/JNI 设置属性！
    }
}

// ==================== PropertyValuesHolder.setAnimatedValue() ====================
void setAnimatedValue(Object target) {
    if (mSetter != null) {
        try {
            // Android 7.0+ 使用 JNI 直接调用（避免反射）
            nCallFloatMethod(target, mJniSetter, mFloatAnimatedValue);
        } catch (Throwable t) {
            // fallback to Java reflection
            mSetter.invoke(target, mFloatAnimatedValue);
        }
    }
}
```

### 5.2 ValueAnimator.doAnimationFrame() fraction 计算源码

```java
// frameworks/base/core/java/android/animation/ValueAnimator.java

public final boolean doAnimationFrame(long frameTime) {
    if (mStartTime < 0) {
        mStartTime = frameTime; // 起始时间锚定
    }
    
    // ====== 核心：fraction 计算 ======
    final long elapsed = frameTime - mStartTime;
    final long duration = mDuration;
    
    float fraction = duration > 0 
        ? (float) elapsed / duration   // ← 线性分数
        : 1f;
    
    // clamp [0, 1] - 但 mInterpolator 可能输出超出范围的值（如 OvershootInterpolator）
    boolean complete = elapsed >= duration;
    
    if (mInterpolator != null) {
        fraction = mInterpolator.getInterpolation(fraction); // ← 插值器变换
    }
    
    // ====== 估值器计算 ======
    if (mValues != null && mValues.length > 0) {
        // PropertyValuesHolder.calculateValue(fraction);
        // 内部调用 mEvaluator.evaluate(fraction, mKeyframes.getStartValue(), mKeyframes.getEndValue())
    }
    
    animateValue(fraction); // 触发 ObjectAnimator.setAnimatedValue()
    
    return !complete; // 返回 false 时自动 removeCallback
}
```

### 5.3 Choreographer 的 FrameCallback 注册

```java
// frameworks/base/core/java/android/view/Choreographer.java

public class Choreographer {
    
    // ====== 回调类型常量 ======
    public static final int CALLBACK_INPUT = 0;
    public static final int CALLBACK_ANIMATION = 1;
    public static final int CALLBACK_INSETS_ANIMATION = 2;
    public static final int CALLBACK_TRAVERSAL = 3;
    public static final int CALLBACK_COMMIT = 4;
    
    // ====== CallbackQueue 数组 ======
    private final CallbackQueue[] mCallbackQueues;
    
    // ====== 公开注册方法 ======
    public void postFrameCallback(int callbackType, FrameCallback callback, Object token) {
        postCallbackDelayedInternal(
            callbackType,           // CALLBACK_ANIMATION
            callback,               // 用户实现的 FrameCallback 接口
            token,                  // FRAME_CALLBACK_TOKEN
            0                       // delayMillis
        );
    }
    
    private void postCallbackDelayedInternal(int callbackType, 
            Object action, Object token, long delayMillis) {
        synchronized (mLock) {
            final long now = SystemClock.uptimeMillis();
            final long dueTime = now + delayMillis;
            
            // 将 callback 添加到对应类型的 CallbackQueue
            mCallbackQueues[callbackType].addCallbackLocked(dueTime, action, token);
            
            if (dueTime <= now) {
                scheduleFrameLocked(now); // 立即请求下一帧
            } else {
                // 延迟到 dueTime 再请求帧
                Message msg = mHandler.obtainMessage(MSG_DO_SCHEDULE_CALLBACK, action);
                mHandler.sendMessageAtTime(msg, dueTime);
            }
        }
    }
    
    // ====== doFrame — 每帧主循环 ======
    void doFrame(long frameTimeNanos, int frame,
            DisplayEventReceiver.VsyncEventData vsyncEventData) {
        
        final long frameIntervalNanos = getFrameIntervalNanos(); // 16.6ms @ 60Hz
        
        // ====== 按优先级顺序执行 4 种回调 ======
        
        // 1. CALLBACK_INPUT
        doCallbacks(CALLBACK_INPUT, frameData);
        
        // 2. CALLBACK_ANIMATION        ← 动画在这里执行！
        doCallbacks(CALLBACK_ANIMATION, frameData);
        
        // 3. CALLBACK_INSETS_ANIMATION
        doCallbacks(CALLBACK_INSETS_ANIMATION, frameData);
        
        // 4. CALLBACK_TRAVERSAL         ← measure/layout/draw 在这里
        doCallbacks(CALLBACK_TRAVERSAL, frameData);
        
        // 5. CALLBACK_COMMIT
        doCallbacks(CALLBACK_COMMIT, frameData);
    }
    
    void doCallbacks(int callbackType, long frameTimeNanos) {
        CallbackQueue queue = mCallbackQueues[callbackType];
        
        // 提取到临时 ArrayList（减少锁持有时间）
        ArrayList<CallbackRecord> callbacks = queue.extractDueCallbacksLocked(now);
        
        for (CallbackRecord c : callbacks) {
            // 执行 FrameCallback.doFrame(long frameTimeNanos)
            c.run(frameTimeNanos);
        }
    }
}

// ====== 单例获取 ======
public static Choreographer getInstance() {
    return sThreadInstance.get(); // ThreadLocal 线程单例
}
```

---

## 6. 应用场景

### 6.1 列表 Item 滑入动画（属性动画 + LayoutAnimation）

```java
// ========= 方案一：RecyclerView ItemAnimator =========
public class SlideInItemAnimator extends DefaultItemAnimator {
    
    @Override
    public boolean animateAdd(RecyclerView.ViewHolder holder) {
        View view = holder.itemView;
        view.setTranslationY(-view.getHeight());    // 初始偏移
        view.setAlpha(0f);
        
        AnimatorSet set = new AnimatorSet();
        set.playTogether(
            ObjectAnimator.ofFloat(view, "translationY", -view.getHeight(), 0f),
            ObjectAnimator.ofFloat(view, "alpha", 0f, 1f)
        );
        set.setInterpolator(new DecelerateInterpolator(1.5f));
        set.setDuration(350);
        set.setStartDelay(holder.getLayoutPosition() * 30L); // 错峰延迟
        set.start();
        
        return true;
    }
}

// ========= 方案二：LayoutAnimation（旧但简单）=========
// res/anim/item_slide_up.xml
<set xmlns:android="http://schemas.android.com/apk/res/android"
     android:duration="350"
     android:interpolator="@android:anim/decelerate_interpolator">
    <translate android:fromYDelta="100%" android:toYDelta="0%" />
    <alpha android:fromAlpha="0" android:toAlpha="1" />
</set>

// 在 RecyclerView/ListView 设置
LayoutAnimationController controller = AnimationUtils
    .loadLayoutAnimation(context, R.anim.item_slide_up);
controller.setDelay(0.15f); // 每项延迟 15%
recyclerView.setLayoutAnimation(controller);
```

### 6.2 页面转场动画（TransitionManager.beginDelayedTransition）

```java
public class DetailActivity extends AppCompatActivity {
    
    private ViewGroup rootView;
    private TextView titleText;
    private ImageView imageView;
    private boolean isExpanded = false;
    
    private void toggleLayout() {
        // ===== 核心：一句代码实现平滑过渡 =====
        TransitionManager.beginDelayedTransition(rootView, 
            new TransitionSet()
                .addTransition(new ChangeBounds())       // 位置/大小变化
                .addTransition(new ChangeTransform())     // scale/rotation 变化
                .addTransition(new ChangeImageTransform())// ImageView 变换
                .setDuration(400)
                .setInterpolator(new FastOutSlowInInterpolator())
        );
        
        // ===== 直接修改布局参数，Transition 自动生成动画 =====
        ViewGroup.LayoutParams params = titleText.getLayoutParams();
        if (isExpanded) {
            params.width = ViewGroup.LayoutParams.MATCH_PARENT;
            imageView.setVisibility(View.VISIBLE);
        } else {
            params.width = 200;
            imageView.setVisibility(View.GONE);
        }
        titleText.setLayoutParams(params);
        isExpanded = !isExpanded;
    }
}

// ===== Activity 转场 =====
public void openDetail(View sharedView) {
    Intent intent = new Intent(this, DetailActivity.class);
    
    ActivityOptions options = ActivityOptions.makeSceneTransitionAnimation(
        this,
        sharedView,                                // 共享元素 View
        ViewCompat.getTransitionName(sharedView)   // "shared_image"
    );
    
    startActivity(intent, options.toBundle());
}

// ===== 目标 Activity =====
public class DetailActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        
        // 延迟转场，等图片加载完成
        ActivityCompat.postponeEnterTransition(this);
        
        imageView.setTransitionName("shared_image");
        
        Glide.with(this)
            .load(imageUrl)
            .listener(new RequestListener<Drawable>() {
                @Override
                public boolean onResourceReady(...) {
                    // 图片就绪，启动转场
                    ActivityCompat.startPostponedEnterTransition(DetailActivity.this);
                    return false;
                }
            })
            .into(imageView);
    }
}
```

### 6.3 Lottie 替代帧动画

```gradle
// build.gradle
dependencies {
    implementation "com.airbnb.android:lottie:6.1.0"
}
```

```xml
<!-- layout.xml -->
<com.airbnb.lottie.LottieAnimationView
    android:id="@+id/lottieView"
    android:layout_width="200dp"
    android:layout_height="200dp"
    app:lottie_fileName="loading.json"
    app:lottie_autoPlay="true"
    app:lottie_loop="true"
    app:lottie_renderMode="hardware" />
```

```java
LottieAnimationView lottieView = findViewById(R.id.lottieView);

// 播放控制
lottieView.playAnimation();
lottieView.pauseAnimation();
lottieView.setProgress(0.5f);          // 跳转到 50%
lottieView.setMinAndMaxProgress(0f, 0.6f); // 播放范围

// 动态换色（无需设计师重新导出）
lottieView.addValueCallback(
    new KeyPath("**", "Fill Color", KeyPath.CONTENT),
    LottieProperty.COLOR,
    new LottieValueCallback<>(Color.parseColor("#FF5722"))
);

// 监听动画事件
lottieView.addAnimatorListener(new Animator.AnimatorListener() {
    @Override
    public void onAnimationEnd(Animator animation) {
        // 动画结束，导航到主页面等
    }
});

// 性能对比
// 帧动画 30 帧 @1080p 内存: 30 × 1920 × 1080 × 4 = ~237MB → OOM
// Lottie 同效果: JSON 文件 ~50KB + 纹理缓存池 < 5MB
```

### 6.4 性能最佳实践总结

```java
/**
 * 动画性能优化清单
 */
public class AnimationPerformanceGuide {
    
    // ✅ 1. 使用硬件层缓存
    void animateWithLayer(View view) {
        view.setLayerType(View.LAYER_TYPE_HARDWARE, null);
        view.animate()
            .scaleX(1.5f)
            .scaleY(1.5f)
            .withLayer()  // 等价于上面的手动设置
            .start();
    }
    
    // ✅ 2. 避免动画期间触发 requestLayout
    // translationX/Y、scaleX/Y、rotation、alpha 只 invalidate，不触发 layout
    // left/right/top/bottom、margin、padding 会触发 requestLayout（开销大！）
    
    // ✅ 3. 在 onDetachedFromWindow 时取消动画
    @Override
    protected void onDetachedFromWindow() {
        super.onDetachedFromWindow();
        animator.cancel();
        view.animate().cancel();
        view.setLayerType(View.LAYER_TYPE_NONE, null); // 释放 FBO
    }
    
    // ✅ 4. 使用 ViewPropertyAnimator 提高效率
    // 比 ObjectAnimator 好：内部批量提交到 RenderNode，减少 JNI 调用
    view.animate()
        .x(200f)
        .y(300f)
        .alpha(0.5f)
        .setDuration(300)
        .setInterpolator(new DecelerateInterpolator())
        .start();
    
    // ✅ 5. 动画复用
    AnimatorSet reusableSet = new AnimatorSet();
    // ...配置一次
    reusableSet.setTarget(view1);
    reusableSet.start();
    // 换个 target 再用
    reusableSet.setTarget(view2);
    reusableSet.start();
}
```

---

## 总结

| 知识点 | 面试权重 | 核心要点 |
|--------|---------|---------|
| 动画分类与选型 | ⭐⭐⭐⭐⭐ | View动画不改变属性，属性动画改变真实值，Transition 布局切换 |
| 插值器 vs 估值器 | ⭐⭐⭐⭐ | 插值器控制节奏（时间→进度），估值器计算数值（进度→值） |
| 硬件层优化 | ⭐⭐⭐⭐ | FBO 缓存跳过 draw() 遍历，结束必须释放 |
| 源码调用链 | ⭐⭐⭐ | start()→addAnimationCallback→doAnimationFrame→animateValue |
| Choreographer | ⭐⭐⭐ | CALLBACK_ANIMATION 优先级在 traversal 之前 |
| 共享元素转场 | ⭐⭐⭐ | 快照 → 位置计算 → 动画过渡 → 显示真实 View |
| Lottie vs 帧动画 | ⭐⭐⭐ | Lottie 内存占用量为帧动画的 2~5%，抗锯齿更好 |
