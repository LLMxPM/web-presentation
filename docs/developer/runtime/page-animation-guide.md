# 页内动画与减少动态效果

页面与工作空间组件可以通过 Vue 和浏览器原生能力实现页内动效。动画创作、排查和交付需同时考虑正常播放、减少动态效果与静态捕获三个场景。

## 能力与边界

| 类型 | 当前实现方式与约束 |
| :--- | :--- |
| 入场、强调、退场、错峰、循环 | CSS `transition`、`@keyframes`；有限入场保留结束状态，循环按内容需要选择 |
| 点击展开、内容切换、列表过渡 | Vue 状态与 `Transition` / `TransitionGroup`；首次挂载过渡需设置 `appear` |
| 数字变化、SVG 路径、自定义动画 | 页面或组件局部 JavaScript、浏览器原生动画 API；卸载时清理计时、动画帧、动画实例和监听 |
| 图表动效 | `AssetChart` 的真实图表配置契约 |
| 三维模型 | 以 `AssetModel` 当前契约为准，当前只显示静态姿态 |
| 翻页过渡 | 项目或逐页配置的 `none` / `fade` / `push`，与页内动画分别控制 |

当前没有统一的页内步骤时间轴、“下一步逐项出现”或任意页内动画的全局暂停契约。页面自行实现的播放、暂停和重播，只能按自身实际行为说明，不能宣称 Runtime 放映控制条会自动接管。

不要假设 GSAP、Motion、Lottie 等依赖或未登记的 Runtime Kit 动画组件可用；依赖与公开 import path 以真实运行环境和能力契约为准。

## 减少动态效果是偏好信号

`prefers-reduced-motion: reduce` 表示系统或浏览器向网页报告减少动态效果的偏好。它不会自动停止任意网页动画；页面需要通过 CSS 或 JavaScript 响应这个信号。

因此，同一浏览器里两页表现不同可能来自源码处理不同：

- 页面 A 在 `reduce` 分支设置 `animation: none`，呈现静态状态。
- 页面 B 没有相应适配，动画仍继续运行。

这种差异本身不能证明浏览器或 Runtime 兼容性不同。Windows 动画效果设置、开发者工具模拟都可能影响这个偏好；仅凭媒体查询结果不能确定具体来源，更不能追溯是谁修改了设置。

## 推荐写法：静态可读，按偏好叠加动效

先让基础样式完整呈现核心内容，再在 `no-preference` 分支启用动画。对循环效果也应保留静态可读状态，不依赖动画结束事件才显示正文。

下面的 class 应放在独立的内层包裹元素上；外层负责定位，避免动画的 `transform` 覆盖居中等布局变换：

```vue
<template>
  <div class="absolute left-1/2 top-24 -translate-x-1/2">
    <h1 class="entry-motion">页面标题</h1>
  </div>
</template>

<style scoped>
/* 无动画时直接呈现可读标题。 */
.entry-motion { opacity: 1; }

@media (prefers-reduced-motion: no-preference) {
  .entry-motion { animation: entry-rise 0.5s ease-out both; }
}

@keyframes entry-rise {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
```

也可在 `reduce` 分支减弱或关闭已有动效，但只处理本页或本组件的动效元素，并恢复正确的静态状态。不要把所有元素统一设为 `opacity: 1`：闪光层、遮罩等装饰通常需要在静态状态保持透明或隐藏。原本用于布局的变换也需要保留。

## 实时预览没有动画时如何排查

1. 确认用户查看的是实时 iframe、截图/缩略图还是导出文件。
2. 在实际渲染页面的 iframe 中检查：

   ```js
   window.matchMedia('(prefers-reduced-motion: reduce)').matches
   ```

3. 检查目标元素的计算样式与实际代码：`animationName`、`animationDuration`、`animationPlayState`、关键帧加载、触发时机、延迟和循环间隔；使用 `transition` 时同时检查过渡属性和前后状态。
4. 如果 `reduce` 为真、页面也有相应规则，且计算样式是 `animation: none`，说明页面按偏好执行了降动效。不要直接判断为 scoped CSS、Runtime 或浏览器不兼容，也不要默认删除这项适配。
5. 用用户实际的实时预览验收正常动效和静态降级。可在开发者工具临时模拟两种偏好；不要擅自修改系统或浏览器设置。模型没有实际环境访问能力时，应说明待核实项，不能声称已检测到用户系统关闭动画。

## 截图、诊断与导出

[Renderer](../../../renderer/wp_renderer/engine/executor.py) 在截图和诊断的独立 Chromium 上下文中主动设置 `reduced_motion="reduce"`，截图还使用 `animations="disabled"`。这些设置属于捕获链路，不能推断 Editor 实时预览也被强制禁用动画。

静态导出对有限原生动画有等待和收尾处理，无限循环不会一直等待；任意 JavaScript/Canvas 动画不保证自动冻结。PPTX 呈现静态结果，不保留网页动画时间轴。正文、标题、关键数据在禁用动画、减少动态效果、截图和打印中都应可读。

截图成功只能作为静态结果证据；验收播放、触发、循环、暂停或重播需要实时验证。未实测时应在交付回复说明，必要的实现解释放源码注释或助手回复，不主动添加到成品画布。

## 模型提示入口

[动画共用规范](../../../backend/app/ai/animation_authoring_standard.py) 拼入页面和组件的系统默认代码规范，由以下入口共同提供：

- 内置内容助手：`get_code_standards(standard_type="page")` 或 `get_code_standards(standard_type="component")`。
- External API：`GET /api/v1/standards/page`、`GET /api/v1/standards/component`。
- CLI：`wp standards page`、`wp standards component`。

主提示只保留查询入口，详细规则不在多个提示中重复维护。用户已自定义整类型代码规范时，仍按原有覆盖规则生效；本次默认规则更新不会覆写自定义内容，需由用户合并新章节或恢复默认。

## 后续编排规划

[页内动画三维动作与媒体编排首期规划](../runtime-integration/motion/README.md) 定义统一播放控制、音视频同步、模型动作和指定状态取帧的后续契约与工作包。该专题尚未实施，本文上方的当前能力边界不因此改变。
