# 04 UI 与 View 体系

## 概览
安卓 UI 渲染的核心机制，从 View 的测量、布局、绘制到事件分发和自定义控件。

## 子模块

| 序号 | 技术点 | 核心内容 | 考察权重 |
|:---:|-------|---------|:-------:|
| 4.1 | [View 绘制流程](./01-View绘制流程/) | Measure/Layout/Draw 三阶段、MeasureSpec、ViewTree | ★★★★★ |
| 4.2 | [事件分发机制](./02-事件分发机制/) | dispatchTouchEvent/onInterceptTouchEvent/onTouchEvent 流程 | ★★★★★ |
| 4.3 | [自定义 View](./03-自定义View/) | 自定义属性、Canvas 绘制、Path 操作、贝塞尔曲线 | ★★★★★ |
| 4.4 | [动画系统](./04-动画系统/) | View 动画、属性动画、转场动画、物理动画 | ★★★★☆ |

## 面试高频考点
- requestLayout / invalidate / postInvalidate 的区别
- 滑动冲突的解决方案（内部拦截法 / 外部拦截法）
- 自定义 View 的三个关键回调（onMeasure / onLayout / onDraw）
