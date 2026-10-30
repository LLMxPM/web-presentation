# Scene 开发调试

`usePageScene.v1` 已进入 Runtime Kit manifest 和 Backend/Agent 能力目录，页面可以使用公开路径导入。正式全屏放映与 Editor 单页预览已使用 Scene，开发控制台复用同一套预览执行逻辑。B3 模型正向动作与 B4 显式媒体/AudioBus 已接入；持久配置、Presenter 和 AI/CLI 由 B5 继续收敛。开发分支暂保留旧时间轴供已有页面手动调试，旧入口清除与完整验收在合并 `main` 前完成。

已运行的 Backend 会缓存 manifest；首次拉取本批改动后需重启 Backend 才能刷新能力目录与导入白名单。页面源码改动继续使用 Vite HMR。启动与重启入口见[本地开发指南](../getting-started.md)。

## 声明页面

挂载只登记，define 在播放准备时执行。每页一个声明，内部登记多条 visual/task；静态呈现另用相同 root 声明。

```vue
<script setup lang="ts">
import { ref } from 'vue'
import { usePageScene } from '@runtime-kit/public/composables/motion/usePageScene.v1'
import { useStaticPresentation } from '@runtime-kit/public/composables/static/useStaticPresentation.v1'

const root = ref<HTMLElement | null>(null)
useStaticPresentation({ root, mode: 'default' })
usePageScene({ root, define(scene) {
  scene.visual({ id: 'intro', role: 'blocking', define(tl) {
    tl.fromTo('.title', { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.4 })
  } })
  const output = scene.root.querySelector<HTMLElement>('[data-counter]')!
  const counter = { value: 0 }
  scene.onCleanup(() => { output.textContent = '100' })
  scene.visual({ id: 'counter', role: 'blocking', define(tl) {
    tl.to(counter, { value: 100, duration: 1, onUpdate() {
      output.textContent = Math.round(counter.value).toString()
    } })
  } })
} })
</script>

<template>
  <section id="scene-page" ref="root" class="h-full w-full">
    <h1 class="title">Scene 开发样例</h1>
    <span data-counter>100</span>
  </section>
</template>
```

默认内容完整可读，截图和导出不执行 define。视觉参数 duration 使用秒，任务 startMs/offsetMs 使用毫秒。有限工作标 blocking；无限装饰标 ambient，不阻塞完成聚合。异步工作通过 task 返回 Promise，页面自建监听、计时器、RAF 等用 onCleanup 释放并响应 signal。当前不支持 GSAP 插件或任意时刻重建。

页面与工作空间组件只能通过 `scene.visual` 使用受管 GSAP，不直接导入 `gsap`、`gsap/*`、`gsap-trial/*` 或 `@gsap/*`。Backend 写入/CodeCheck、远程预览和构建/诊断编译均拒绝这些导入，返回 `SCENE_GSAP_IMPORT_FORBIDDEN`；平台内部实现仍可依赖 GSAP。此规则限定支持的创作方式，不构成任意 JavaScript 的安全沙箱。检查缓存指纹包含创作策略版本，修改规则时必须升级版本。

## 控制台播放

完整样例位于 `runtime/src/examples/local/views/feature-showcase/SceneShowcase.vue`。Runtime 独立运行时进入 `/feature-showcase/scene-showcase`；公开声明根为 `#scene-showcase`，可执行 `await window.__RUNTIME_SCENE_DEBUG__.play('#scene-showcase')`。本地路由 fixture 为该页设置 `scene_end`，有限数字、文字、描边与 Canvas 任务完成后停留 300ms 再推进，DOM/CSS 无限装饰不阻塞；它不修改平台项目的 Backend 配置。样例已通过类型、构建和真实 GSAP ticker 的假时钟开发回归，像素表现和实际浏览器生命周期待 C3。

复用已运行的 Vite 开发服务，打开页面或 Editor 预览，在浏览器开发者工具中选择 **Runtime 预览 iframe 的执行上下文**。全屏放映退出后执行：

```js
const debug = window.__RUNTIME_SCENE_DEBUG__
await debug.play('#scene-page')
debug.read()
debug.stop()
```

当前 frame 只有一个声明时可省略选择器：`await debug.play()`。多个画布时必须传入包含声明根的元素或选择器。read 返回当前 generation、phase、hasBlocking、blockedTaskIds 和 issue；准备/执行失败在 issue 中给出原因。每次 play 都先释放上一轮，再创建新的会话；stop 返回停止后的快照，随后 read 为 null。

该调试入口只在 Vite `DEV` 模式安装，生产构建不包含它。导航、页面卸载、HMR 或进入正式全屏放映会取消调试任务；capture/export/thumbnail 及嵌套静态画布不播放。同页同时登记旧时间轴时会报冲突，避免两个所有者一起启动。开发调试没有自动翻页，也不代表实际媒体、Renderer 或产物验收已经通过。

## 正式预览与放映

Editor 单页预览与放大预览提供播放、停止和完整 Scene 状态，不再提供时间轴位置、暂停或重播控件。有限任务 completed 后仍可停止，以清理继续运行的 ambient；停止后可以显式创建下一轮播放。放大时先停止原 iframe，关闭时释放弹窗预览；状态消息只接受当前 iframe 和已验证的 origin。

Runtime 根元素全屏后由唯一 Deck 启动当前页，过渡与资源就绪前不运行任务。manual 等待手动翻页，timer 到点取消未完成任务，scene_end 等全部 blocking 实际完成后再停留；保持/释放只阻止自动翻页，不暂停动画。冻结恢复按剩余预算继续，计时严重迟到时保持当前页等待释放。Runtime 内部配置已识别 scene_end 与 completionDelayMs；Backend DTO 和 Editor 配置表单升级由 B5 同批完成，旧 media_end/timeline_end 在正式宿主明确报错。

## 模型与实例数值

模型使用 `AssetModel.v3.vue`，通过组件 ref 的 `getHandle()` 在首帧就绪后取得句柄。`handle.animations()` 读取当前真实片段摘要；将资源查询确认的 `clipIndex/signature` 传入 `handle.animation({ id, role, clipIndex, signature, repeat?, rate? })`，再交给 `scene.task(...)`。有限动作可 blocking；repeat=-1 只能 ambient，同一实例同时仅允许一个动作，连续动作可用 afterTrack；多实例各自独立播放。资源替换后旧句柄失效，不能按名称猜测新片段。

`handle.transform` 提供 x/y/z/scale/rotationY（角度），`handle.camera` 提供位置、targetX/Y/Z 与 fov 数值副本；可用 scene.visual 驱动，并在 onUpdate 调用 handle.invalidate()。在 define 中登记 `scene.onCleanup(handle.reset)` 恢复初始视角与整体变换。材质、几何、骨骼与动作混合不通过此句柄开放。静态/可交互展示继续使用 AssetModel.v1；v2 已删除。实际 WebGL 和多模型资源曲线待 C3。

## 显式媒体与 cue

音频使用 AssetAudio.v1 的 `purpose="narration"`，自动视频使用 AssetVideo.v1 的 `purpose="automatic"`；普通 content 保留用户手动播放。组件的 media-ready 事件提供原生目标，页级 define 才登记播放任务：

```ts
import { createSceneMediaTask } from '@runtime-kit/public/composables/media/createSceneMediaTask.v1'

// voice 是由 <AssetAudio @media-ready="voice = $event" /> 填充的 shallowRef。
usePageScene({ root, define(scene) {
  scene.task(createSceneMediaTask({ id: 'voice', role: 'blocking', target: () => voice.value }))
} })
```

一页最多一个自动发声主媒体，其余自动视频显式 muted；循环只允许 ambient。prepare 不播放，run 才请求许可，ended 才实际完成。播放受阻时在当前 Runtime frame 出现“允许播放”按钮，必须当前窗口的点击恢复；Editor 父窗口和演讲者控制台不能代理用户手势。内容、Scene 媒体与 Deck cue 共用窗口 AudioBus 的静音与分组音量，离页清除重试和旧回执；静态上下文零通道与零播放。

交互 cue 使用 `@runtime-kit/public/composables/audio/useAudioCue.v2`；playCue 返回 Promise，等待真实许可回执后得到 played/skipped/unavailable，不等待 cue 结束，不参与 Scene 完成聚合。旧同步 v1 与 AssetAudio/Video.v2 已删除，旁白/cue 功能门也已删除，默认开放不代表 C3 实机发声通过。完整字段见[音频契约](../runtime-integration/audio/contract.md)。

## 合并前收口

完整责任和实机清单见[工作包清单](../runtime-integration/playback-redesign/work-packages/README.md)。合并 main 前必须完成正式宿主切换、旧时间轴/Transport/采样与旧 manifest 清除、各调用端及生成物收敛，并通过 C3 的全量与集中实机验收。开发阶段保持版本化公开路径、最小充分测试、静态截图和导出开发回归；不再用“尚未删除旧入口”阻止新能力调试。
