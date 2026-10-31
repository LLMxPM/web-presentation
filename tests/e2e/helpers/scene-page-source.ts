/**
 * 文件功能：提供跨 E2E 场景共用的正式 Runtime Kit Scene 页面源码。
 */

/**
 * 构造默认可读的 Scene 页面：红色标题淡入，计数器由 0 走向 100，停止后恢复初值。
 * 静态上下文只渲染模板，不执行 define，因此截图与导出始终看到完整可读内容。
 */
export function buildScenePage(title = 'Scene 第一页'): string {
  return `<template>
  <main ref="root" class="scene-e2e-page">
    <h1 class="scene-e2e-title">${title}</h1>
    <p class="scene-e2e-counter" data-counter>0</p>
  </main>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import { usePageScene } from '@runtime-kit/public/composables/motion/usePageScene.v1'
import { useStaticPresentation } from '@runtime-kit/public/composables/static/useStaticPresentation.v1'
const root = ref<HTMLElement | null>(null)
useStaticPresentation({ root, mode: 'default' })
usePageScene({ root, define(scene) {
  const output = scene.root.querySelector<HTMLElement>('[data-counter]')!
  const counter = { value: 0 }
  scene.onCleanup(() => { output.textContent = '0' })
  scene.visual({ id: 'title', role: 'blocking', define(timeline) {
    timeline.fromTo('.scene-e2e-title', { opacity: 0 }, { opacity: 1, duration: 1.2, ease: 'none' })
    timeline.to(counter, { value: 100, duration: 1.2, ease: 'none',
      onUpdate() { output.textContent = String(Math.round(counter.value)) } })
  } })
} })
</script>
<style scoped>
.scene-e2e-page { width: 100%; height: 100%; display: grid; place-content: center; justify-items: center; gap: 12px; background: #f8fafc; }
.scene-e2e-title { font-size: 64px; color: #b91c1c; }
.scene-e2e-counter { font-size: 28px; color: #0f172a; font-variant-numeric: tabular-nums; }
</style>`
}

/**
 * 构造「有限 blocking + 无限 ambient」的 Scene 页面：scene_end 只等待有限任务，装饰不阻塞推进。
 */
export function buildSceneAmbientPage(title = 'Scene 装饰页'): string {
  return `<template>
  <main ref="root" class="scene-e2e-page">
    <h1 class="scene-e2e-title">${title}</h1>
    <p class="scene-e2e-counter" data-counter>0</p>
    <i v-for="index in 6" :key="index" class="scene-e2e-spark" aria-hidden="true"></i>
  </main>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import { usePageScene } from '@runtime-kit/public/composables/motion/usePageScene.v1'
import { useStaticPresentation } from '@runtime-kit/public/composables/static/useStaticPresentation.v1'
const root = ref<HTMLElement | null>(null)
useStaticPresentation({ root, mode: 'default' })
usePageScene({ root, define(scene) {
  const output = scene.root.querySelector<HTMLElement>('[data-counter]')!
  const counter = { value: 0 }
  scene.onCleanup(() => { output.textContent = '0' })
  scene.visual({ id: 'finite', role: 'blocking', define(timeline) {
    timeline.to(counter, { value: 100, duration: 1, ease: 'none',
      onUpdate() { output.textContent = String(Math.round(counter.value)) } })
  } })
  scene.visual({ id: 'decor', role: 'ambient', repeat: -1, yoyo: true, define(timeline) {
    timeline.to('.scene-e2e-spark', { opacity: 0.3, duration: 0.6, stagger: 0.05 })
  } })
} })
</script>
<style scoped>
.scene-e2e-page { width: 100%; height: 100%; display: grid; place-content: center; justify-items: center; gap: 12px; background: #f8fafc; }
.scene-e2e-title { font-size: 64px; color: #b91c1c; }
.scene-e2e-counter { font-size: 28px; color: #0f172a; font-variant-numeric: tabular-nums; }
.scene-e2e-spark { width: 10px; height: 10px; border-radius: 50%; background: #38bdf8; opacity: 0.9; }
</style>`
}

/**
 * 构造带显式旁白任务的 Scene 页面；旁白实际 ended 才完成，播放失败按真实失败处理。
 * 资源名必须来自真实上传，否则页面依赖校验会拒绝源码。
 * @param narrationName 已上传音频资源的逻辑名
 */
export function buildSceneNarrationPage(narrationName: string, title = 'Scene 旁白页'): string {
  return `<template>
  <main ref="root" class="scene-e2e-page">
    <h1 class="scene-e2e-title">${title}</h1>
    <AssetAudio name="${narrationName}" purpose="narration" @media-ready="target = $event" @media-unmounted="target = null" />
  </main>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import AssetAudio from '@runtime-kit/public/components/assets/AssetAudio.v1.vue'
import { createSceneMediaTask } from '@runtime-kit/public/composables/media/createSceneMediaTask.v1'
import { usePageScene } from '@runtime-kit/public/composables/motion/usePageScene.v1'
import { useStaticPresentation } from '@runtime-kit/public/composables/static/useStaticPresentation.v1'
const root = ref<HTMLElement | null>(null)
const target = ref<HTMLMediaElement | null>(null)
useStaticPresentation({ root, mode: 'default' })
usePageScene({ root, define(scene) {
  scene.task(createSceneMediaTask({ id: 'narration', role: 'blocking', target: () => target.value }))
} })
</script>
<style scoped>
.scene-e2e-page { width: 100%; height: 100%; display: grid; place-content: center; justify-items: center; background: #f8fafc; }
.scene-e2e-title { font-size: 64px; color: #b91c1c; }
</style>`
}
