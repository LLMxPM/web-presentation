// 文件功能：挂载四个原生 SFC 候选及两个独立实例，只暴露功能采样和局部修改操作。
import { createApp, h, nextTick, ref } from 'vue'
import GsapScene from './GsapScene.vue'
import AnimeScene from './AnimeScene.vue'
import MotionScene from './MotionScene.vue'
import WaapiScene from './WaapiScene.vue'
import PropsScene from './PropsScene.vue'
import { probeAdapters } from './adapters'
import './style.css'

const scenes = { gsap: GsapScene, anime: AnimeScene, motion: MotionScene, waapi: WaapiScene }
type Kind = keyof typeof scenes
interface SceneHandle { sample(ms: number): void; dispose(): void; play(): void; modelMs(): number; durationMs(): number }
const kind = ref<Kind>('gsap'), startMs = ref(900), revision = ref(0), visible = ref(true)
const left = ref<SceneHandle | null>(null), right = ref<SceneHandle | null>(null)

/** 两次绘制只用于等待 Vue 与动画库提交结果，不采集耗时或帧率。 */
async function settled() {
  await nextTick()
  await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())))
}
createApp({
  setup() {
    return () => h('main', [
      ...(visible.value ? [
        h(scenes[kind.value], { ref: left, key: `left-${revision.value}`, detailStartMs: startMs.value }),
        h(scenes[kind.value], { ref: right, key: `right-${revision.value}`, detailStartMs: 900 }),
        h(PropsScene),
      ] : []),
    ])
  },
}).mount('#app')

/** 读取用户可见样式与对象轨道，避免只以成功构建判断编排正确。 */
function snapshot() {
  const roots = document.querySelectorAll<HTMLElement>('.scene')
  const opacity = (element: Element) => +Number(getComputedStyle(element).opacity).toFixed(5)
  return {
    title: opacity(roots[0]!.querySelector('.title')!),
    cards: Array.from(roots[0]!.querySelectorAll('.card')).map(opacity),
    demo: opacity(roots[0]!.querySelector('.demo')!),
    modelMs: +left.value!.modelMs().toFixed(3), durationMs: +left.value!.durationMs().toFixed(3),
    untouchedRightModelMs: +right.value!.modelMs().toFixed(3),
    untouchedRightTitle: opacity(roots[1]!.querySelector('.title')!),
  }
}

Object.assign(window, { authoring: {
  probeAdapters,
  async mount(candidate: Kind, detailStartMs = 900) {
    kind.value = candidate; startMs.value = detailStartMs; revision.value++; visible.value = true
    await settled()
  },
  async sample(ms: number) { left.value!.sample(ms); await settled(); return snapshot() },
  async dispose() { left.value!.dispose(); right.value!.dispose(); await settled(); return document.getAnimations().length },
  async unmount() { visible.value = false; await settled(); return { scenes: document.querySelectorAll('.scene').length, nativeAnimations: document.getAnimations().length } },
} })
