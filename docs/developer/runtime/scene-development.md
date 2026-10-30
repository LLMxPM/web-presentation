# Scene 开发调试

`usePageScene.v1` 已进入 Runtime Kit manifest 和 Backend/Agent 能力目录，页面可以使用公开路径导入。开发分支暂与旧时间轴并存，同一页选一种编排。正式放映宿主、三维和音频接线仍按工作包推进；旧入口清除与完整验收是合并 `main` 前的门槛，不阻止开发过程中公开和调试新入口。

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

## 控制台播放

复用已运行的 Vite 开发服务，打开页面或 Editor 预览，在浏览器开发者工具中选择 **Runtime 预览 iframe 的执行上下文**。全屏放映退出后执行：

```js
const debug = window.__RUNTIME_SCENE_DEBUG__
await debug.play('#scene-page')
debug.read()
debug.stop()
```

当前 frame 只有一个声明时可省略选择器：`await debug.play()`。多个画布时必须传入包含声明根的元素或选择器。read 返回当前 generation、phase、hasBlocking、blockedTaskIds 和 issue；准备/执行失败在 issue 中给出原因。每次 play 都先释放上一轮，再创建新的会话；stop 返回停止后的快照，随后 read 为 null。

该调试入口只在 Vite `DEV` 模式安装，生产构建不包含它。导航、页面卸载、HMR 或进入正式全屏放映会取消调试任务；capture/export/thumbnail 及嵌套静态画布不播放。同页同时登记旧时间轴时会报冲突，避免两个所有者一起启动。开发调试没有自动翻页，也不代表完整放映、实际媒体、Renderer 或产物验收已经通过。

## 合并前收口

完整责任和实机清单见[工作包清单](../runtime-integration/playback-redesign/work-packages/README.md)。合并 main 前必须完成正式宿主切换、旧时间轴/Transport/采样与旧 manifest 清除、各调用端及生成物收敛，并通过 C3 的全量与集中实机验收。开发阶段保持版本化公开路径、最小充分测试、静态截图和导出开发回归；不再用“尚未删除旧入口”阻止新能力调试。
