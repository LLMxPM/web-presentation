# 独立静态呈现

`useStaticPresentation.v1` 是与时间轴、播放进度无关的页面静态声明，公开路径为 `@runtime-kit/public/composables/static/useStaticPresentation.v1`。截图、缩略图、PDF/PPTX 与打印使用同一契约。当前完成开发接线与测试，真实像素、媒体禁播与产物验收由 Motion C3 执行。

## 页面声明

含受托管动画的页面必须在同一根节点声明一种模式：`default` 使用可读默认态，`poster` 由页面模板或准备函数提供海报，`unsupported` 明确不能静态呈现并附短原因。没有受托管动画的普通页面继续使用默认 DOM；Runtime 不猜测内容是否可读。

```vue
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useStaticPresentation } from '@runtime-kit/public/composables/static/useStaticPresentation.v1'

const root = ref<HTMLElement | null>(null)
const { isStatic } = useStaticPresentation({ root, mode: 'poster' })
onMounted(() => {
  if (isStatic.value) return
  // 在这里启动本页动态效果，并在卸载时释放。
})
</script>

<template>
  <section ref="root">
    <div v-if="isStatic">完整可读的内容或静态图表</div>
    <div v-else>动态内容</div>
  </section>
</template>
```

`isStatic` 在 `capture/export/thumbnail` 为真，交互预览和放映为假。可选 `prepare({ signal })` 只在静态上下文挂载后执行；用于准备图表等静态内容，必须响应取消信号。默认期限 25 秒，`timeoutMs` 只能缩短；卸载与超时都会中止信号。页面自己的 CSS、Canvas、计时器和异步写入须遵守静态分支与取消约束，Runtime 不会拦截任意 JavaScript 副作用。

`usePageScene.v1` 在静态上下文不执行 define、不创建 PageScene；模型保持初始姿态，不推进 Mixer，音频和 cue 不发声。静态声明不得调用 seek、sampleAt 或等待动画终点生成海报。旧 `usePageTimeline.v1` 的清零由 C2 负责，正式静态出口不消费旧采样链。

## 就绪与错误

目标画布的 `window.__RENDER_READY__.staticPresentation` 为 `{ status, code, message }`：

| status | 语义 |
| :--- | :--- |
| `ready` | 静态声明完成，继续等待字体、图片、视频 poster/有界首帧和模型初始静态帧；code/message 为 null |
| `unsupported` | 明确声明不可呈现，或受托管动画缺少同根静态声明；原因码 `STATIC_PRESENTATION_UNAVAILABLE`，不可重试 |
| `failed` | 声明、准备或期限失败；使用 `STATIC_PRESENTATION_FAILED` / `STATIC_PRESENTATION_TIMEOUT`，不伪装为内容不可呈现 |

消息最长 240 字符。同根重复声明失败，不同画布互不影响；导航先撤销旧回执，迟到准备不能覆盖下一页结果。

独立 PNG 对不可呈现返回不可重试错误；同 attempt 的诊断附图返回 `screenshot.status=unavailable`，保留成功布局。写入结果对应 `status=unavailable`，与 `pending/skipped` 分开。缩略图显示原因占位；批量导出默认整体失败并指出页码，不静默缺页。

捕获策略为 `page-static-capture.v3`，Backend 截图身份、调度请求和 Renderer 能力声明共享 `render_contracts.screenshot.CAPTURE_POLICY_VERSION`。v3 将各出口的视频静态准备统一到 Runtime 资源探针，修正前的图片不能命中新策略缓存。发布权限、候选版本、租约、取消围栏和默认截图指针保持现有契约。

PNG、缩略图和离屏导出共用 Runtime 资源探针：先完成静态声明，再等待字体、图片/背景图、视频 poster 解码或无 poster 的有界首帧、模型真实首帧。视频准备只暂停/加载，不调用 `play()`、不修改 `currentTime`；海报优先，视频源失败不否定已经可读的海报，坏海报也不能靠视频帧掩盖。图片、媒体监听和计时器随超时、取消或卸载释放。

PDF/PPTX 必须有可导航的页面路由，并经过离屏静态舞台；缺路由直接报错。模型静态 PNG 采集失败按资源/执行失败整体中断并给出页码和原因，不以空白 canvas 继续导出。缩略图对内容不可呈现或资源失败显示原因占位。

组件宿主继承 capture/thumbnail 等更严格策略。远程组件诊断使用 `capture`，场景切换后等待资源并返回对应 settled 回执；Editor 中的组件交互预览保持手势策略，首轮工作空间组件不使用 Scene。

截图阶段 `available` 不得带失败原因或重试标记；`STATIC_PRESENTATION_UNAVAILABLE` 只能对应不可重试的 `unavailable`，不能表达为 `skipped/failed`。跨端正反例维护在 `tests/fixtures/static-capture-cases.json`，同时验证 Runtime 回执、Renderer 映射、Python DTO 和两版 JSON Schema。

Renderer 关闭完成前只报告 `cleaning`，不披露成功图片描述符或下载产物。PNG 返回后再次复核期限、取消与图片阶段所有权；取消或图片阶段超时后的迟到结果不得落盘、注册或提升默认指针。成功结果的临时产物保留到消费/TTL，失败与取消清理目录和槽位。真实 Chromium 进程释放与跨产物像素一致性仍由 C3 实测。

指定时刻截图协议已在 B1 移除。截图请求不接受 `motion_snapshot`，结果不再返回 `applied_motion`，能力自省不再披露 `capture_snapshot`。Renderer 控制契约 v1/v2 和 Python DTO 均明确拒绝旧字段，离屏导出也拒绝旧 `motionSnapshot` 参数；旧播放内部 `sampleAt/seek/applyAt` 剩余文件由 C2 删除，不用于静态产物。
