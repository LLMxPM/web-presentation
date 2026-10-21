// 文件功能：加载单个独立候选并读取双实例可见样式，避免失败候选的导入污染其他组。
import { createApp, h, nextTick, ref, type Component } from 'vue'
import type { StoryProps } from '../motion-story/types'
import type { Session } from '../motion-story/session'
import '../motion-story/style.css'
import './style.css'
type Handle = Session & { ready: boolean; error: { code: string; fieldPath: string; message: string } | null }
const component = ref<Component>(), shown = ref(false), revision = ref(0), options = ref<StoryProps>({})
const left = ref<Handle>(), right = ref<Handle>()
createApp({ setup() { return () => shown.value && component.value ? h('main', [
  h(component.value, { ...options.value, key: `left-${revision.value}`, ref: left }),
  h(component.value, { key: `right-${revision.value}`, ref: right }),
]) : null } }).mount('#app')

/** 等待页面提交，不统计执行耗时。 */
async function settled() { await nextTick(); await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))) }
/** 样式从真实 DOM 读取；透明度与位移都纳入检查。 */
function styles(index = 0) {
  const root = document.querySelectorAll('.story')[index]!
  const read = (element: Element) => {
    const style = getComputedStyle(element)
    return { opacity: +Number(style.opacity).toFixed(5), y: style.transform === 'none' ? 0 : +new DOMMatrixReadOnly(style.transform).m42.toFixed(4) }
  }
  return {
    title: read(root.querySelector('.title')!), cards: [...root.querySelectorAll('.card')].map(read),
    clipCaption: read(root.querySelector('.clip-caption')!), demoCaption: read(root.querySelector('.demo-caption')!),
    calloutModel: [...root.querySelectorAll('.callout-model .chip')].map(read), calloutDemo: [...root.querySelectorAll('.callout-demo .chip')].map(read),
  }
}
Object.assign(window, { lunaResearch: {
  async mount(id: string, props: StoryProps = {}) {
    const module: { default: Component } = await import(/* @vite-ignore */ `/candidates/${id}.vue`)
    component.value = module.default; options.value = props; shown.value = true; revision.value++
    await settled()
    for (let i = 0; i < 500; i++) {
      if (left.value?.error || right.value?.error) return { ready: false, error: left.value?.error ?? right.value?.error }
      if (left.value?.ready && right.value?.ready) return { ready: true, left: left.value.state(), right: right.value.state(), styles: styles() }
      await new Promise(resolve => setTimeout(resolve, 20))
    }
    throw new Error('PREPARE_TIMEOUT')
  },
  async sample(ms: number) { await left.value!.sample(ms); await settled(); return { state: left.value!.state(), styles: styles(), right: right.value!.state(), rightStyles: styles(1) } },
  async freeze() { left.value!.freeze(); await settled() },
  async dispose() { left.value!.dispose(); right.value!.dispose(); await settled(); return { left: left.value!.state(), right: right.value!.state() } },
  async unmount() { shown.value = false; await settled(); return document.querySelectorAll('.story').length },
} })
