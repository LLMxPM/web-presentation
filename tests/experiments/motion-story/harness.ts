// 文件功能：挂载六种完整故事组合，提供样式/资源采样及有限错误反馈探针。
import { createApp, h, nextTick, ref } from 'vue'
import GsapStory from './GsapStory.vue'
import AnimeStory from './AnimeStory.vue'
import BuilderStory from './BuilderStory.vue'
import JsonStory from './JsonStory.vue'
import { compile } from './plan'
import type { Draft, Engine, StoryProps } from './types'
import type { Session } from './session'
import './style.css'
type Kind = 'native' | 'builder' | 'json'
type Handle = Session & { ready: boolean; error: { code: string; fieldPath: string; message: string } | null }
const kind = ref<Kind>('native'), engine = ref<Engine>('gsap'), visible = ref(false), revision = ref(0)
const props = ref<StoryProps>({}), left = ref<Handle>()
createApp({ setup() { return () => {
  const component = kind.value === 'builder' ? BuilderStory : kind.value === 'json' ? JsonStory : engine.value === 'gsap' ? GsapStory : AnimeStory
  return visible.value ? h(component, { ...props.value, engine: engine.value, ref: left, key: revision.value }) : null
} } }).mount('#app')

/** 等待 Vue 与浏览器提交，不记录耗时。 */
async function settled() {
  await nextTick(); await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())))
}
/** 错误样本使用同一份真实资源元数据；错误对象保持稳定位置与轨道 id。 */
function errors() {
  const state = left.value!.state(), clip = state.clip
  const metadata = { clip, voiceDurationMs: 4000, videoDurationMs: 6000 }
  const cases: Record<string, Draft[]> = {
    target: [{ id: 'bad', type: 'enter', target: 'typo', durationMs: 400, start: { atMs: 0 } }],
    cycle: [
      { id: 'a', type: 'enter', target: 'title', durationMs: 400, start: { after: 'b' } },
      { id: 'b', type: 'enter', target: 'card1', durationMs: 400, start: { after: 'a' } },
    ],
    trim: [{ id: 'demo', type: 'video', target: 'video', inMs: 1000, outMs: 7000, start: { atMs: 0 } }],
  }
  return Object.fromEntries(Object.entries(cases).map(([name, drafts]) => {
    try { compile(metadata, drafts); return [name, { code: 'UNEXPECTED_SUCCESS' }] }
    catch (error) { const e = error as Error & { code: string; fieldPath: string; trackId: string }; return [name, { code: e.code, fieldPath: e.fieldPath, trackId: e.trackId }] }
  }))
}
Object.assign(window, { storyResearch: {
  async mount(route: Kind, candidate: Engine, options: StoryProps = {}) {
    kind.value = route; engine.value = candidate; props.value = options; revision.value++; visible.value = true
    await settled()
    for (let i = 0; i < 500; i++) {
      if (left.value?.error) return { ready: false, error: left.value.error }
      if (left.value?.ready) return { ready: true, state: left.value.state() }
      await new Promise(resolve => setTimeout(resolve, 20))
    }
    throw new Error('PREPARE_TIMEOUT')
  },
  async sample(ms: number) { await left.value!.sample(ms); await settled(); return left.value!.state() },
  play: () => left.value!.play(), state: () => left.value!.state(), errors,
  async freeze() { left.value!.freeze(); await settled(); return left.value!.state() },
  async dispose() { left.value!.dispose(); await settled(); return left.value!.state() },
  async unmount() { visible.value = false; await settled(); return { roots: document.querySelectorAll('.story').length, animations: document.getAnimations().length } },
} })
