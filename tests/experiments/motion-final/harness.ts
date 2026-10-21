// 文件功能：统一挂载最终适配模板的独立候选，提供双实例与实际时间轴回调探针。
import { createApp, h, nextTick, markRaw, ref, type Component } from 'vue'
import { gsap } from 'gsap'
import Reference from './reference.vue'
import type { Session } from '../motion-story/session'
import type { StoryProps } from './api-types'
import { inspectVisual } from './visual'
import '../motion-story/style.css'
import '../motion-luna/style.css'
type Handle = Session & { ready: boolean; error: { code: string; fieldPath: string; message: string } | null }
const loaders = import.meta.glob<{ default: Component }>('./candidates/*.vue')
const component = ref<Component>(), shown = ref(false), revision = ref(0), options = ref<StoryProps>({})
const left = ref<Handle>(), right = ref<Handle>(), probe = { parent: 0, child: 0 }
createApp({ setup() { return () => shown.value && component.value ? h('main', [
  h(component.value, { ...options.value, ref: left, key: `l-${revision.value}` }),
  h(component.value, { ref: right, key: `r-${revision.value}` }),
]) : null } }).mount('#app')

/** 等待 Vue 与样式提交；不采集耗时。 */
async function settled() { await nextTick(); await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))) }
/** 从实际元素读取透明度与位移，不以计划结构代替视觉校验。 */
function styles(index = 0) {
  const root = document.querySelectorAll('.story')[index]!
  const read = (element: Element) => {
    const style = getComputedStyle(element)
    return { opacity: +Number(style.opacity).toFixed(5), y: style.transform === 'none' ? 0 : +new DOMMatrixReadOnly(style.transform).m42.toFixed(4) }
  }
  return { title: read(root.querySelector('.title')!), cards: [...root.querySelectorAll('.card')].map(read),
    clipCaption: read(root.querySelector('.clip-caption')!), demoCaption: read(root.querySelector('.demo-caption')!),
    calloutModel: [...root.querySelectorAll('.callout-model .chip')].map(read), calloutDemo: [...root.querySelectorAll('.callout-demo .chip')].map(read) }
}
Object.assign(window, { finalResearch: {
  async mount(id: string, props: StoryProps = {}) {
    component.value = markRaw(id === 'reference' ? Reference : (await loaders[`./candidates/${id}.vue`]!()).default)
    options.value = props; shown.value = true; revision.value++; probe.parent = 0; probe.child = 0
    await settled()
    for (let i = 0; i < 500; i++) {
      if (left.value?.error || right.value?.error) return { ready: false, error: left.value?.error ?? right.value?.error }
      if (left.value?.ready && right.value?.ready) return { ready: true, left: left.value.state(), styles: styles() }
      await new Promise(resolve => setTimeout(resolve, 20))
    }
    throw new Error('PREPARE_TIMEOUT')
  },
  addProbe() {
    const root = document.querySelector<HTMLElement>('.story')!, record = inspectVisual(root)!
    const child = gsap.timeline().call(() => probe.child++, [], 0.1)
    record.timeline.add(child, 0).call(() => probe.parent++, [], 0.1)
  },
  async sample(ms: number) { await left.value!.sample(ms); await settled(); return { state: left.value!.state(), styles: styles(), right: right.value!.state(), rightStyles: styles(1), probe: { ...probe } } },
  play: () => left.value!.play(), state: () => left.value!.state(),
  async freeze() { left.value!.freeze(); await settled(); return { probe: { ...probe }, frozen: inspectVisual(document.querySelector('.story')!)!.frozen } },
  async dispose() {
    left.value!.dispose(); right.value!.dispose(); await settled()
    return { state: left.value!.state(), visualDisposed: [...document.querySelectorAll<HTMLElement>('.story')].every(root => inspectVisual(root)?.disposed) }
  },
  async unmount() { shown.value = false; await settled(); return document.querySelectorAll('.story').length },
} })
