/** 文件功能：验证原生 GSAP 标签、错峰、段落复用、资源依赖与静默采样生命周期。 */
import { afterEach, expect, it } from 'vitest'
import { compilePageTimeline } from './compile'
import { createNativeVisual, seconds, type NativeVisualTimeline } from './native-visual'
import { createMotionResourceBuilder } from './resource-builder'
import { createMotionTransport } from './transport'
import { createDefaultMotionAdapterFactory } from './default-adapters'

const cleanups: Array<() => void> = []
afterEach(() => { cleanups.splice(0).forEach(cleanup => cleanup()); document.body.innerHTML = '' })

/** 构造同结构的隔离页面，用于验证作用域和身份不依赖创建顺序。 */
function makeVisualRoot() {
  const root = document.createElement('section')
  root.innerHTML = '<h1 style="opacity:0.8">标题</h1><div class="card"></div><div class="card"></div>'
  document.body.append(root)
  return root
}

/** 段落直接向原生时间轴追加，位置、错峰、缓动均使用 GSAP 原生语法。 */
function appendCards(timeline: NativeVisualTimeline, at: string) {
  timeline.fromTo('.card', { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: seconds(300), stagger: seconds(100) }, at)
}

it('资源 builder 后继随动，原生视觉复用标签与段落，无第二播放时钟', async () => {
  const tracks = createMotionResourceBuilder()
    .voice('voice', { asset: 'voice', outMs: 1000 })
    .clip('model', { index: 0, durationMs: 1000, signature: 'queried' }, { asset: 'model', startMs: 1500 })
    .video('demo', { asset: 'demo', inMs: 1000, outMs: 3000, afterTrack: 'model', offsetMs: 200 }).build()
  const resources = compilePageTimeline({ schemaVersion: 1, timelineId: 'intro', tracks })
  expect(resources.labels.demo).toBe(2700)
  const root = makeVisualRoot()
  const visual = createNativeVisual(root, resources.labels, timeline => {
    timeline.fromTo('h1', { opacity: 0 }, { opacity: 1, duration: 0.4, immediateRender: false }, 0)
    appendCards(timeline, 'demo')
    timeline.fromTo('h1', { opacity: 1 }, { opacity: 0, duration: 0.3 }, 'demo+=0.5')
  })
  cleanups.push(() => visual.adapter.dispose())
  expect(visual.plan.labels.demo).toBe(2700)
  expect(visual.plan.durationMs).toBe(3500)
  await visual.adapter.applyAt({ positionMs: 200, visualMode: 'full' })
  expect(Number(root.querySelector('h1')!.style.opacity)).toBeCloseTo(0.5)
  expect(Number(root.querySelector<HTMLElement>('.card')!.style.opacity)).toBe(0)
  const middle = await visual.adapter.freeze!(200)
  await visual.adapter.applyAt({ positionMs: 3300, visualMode: 'full' })
  expect(Number(root.querySelector('h1')!.style.opacity)).toBeLessThan(1)
  await visual.adapter.applyAt({ positionMs: 200, visualMode: 'full' })
  expect((await visual.adapter.freeze!(200)).digest).toBe(middle.digest)
  visual.adapter.dispose()
  expect(root.querySelector('h1')!.style.opacity).toBe('0.8')
})

it('纯视觉编排通过统一 transport 完成采样，重复构造摘要一致', async () => {
  const build = (timeline: NativeVisualTimeline) => timeline.fromTo('h1', { opacity: 0 }, { opacity: 1, duration: 1 }, 0)
  const root = makeVisualRoot()
  const visual = createNativeVisual(root, {}, build)
  const otherRoot = makeVisualRoot()
  const other = createNativeVisual(otherRoot, {}, build)
  cleanups.push(() => other.adapter.dispose())
  expect(visual.plan.digest).toBe(other.plan.digest)
  const plan = compilePageTimeline({ schemaVersion: 1, timelineId: 'pure', tracks: [], poster: { atMs: 500 } }, { visual: visual.plan })
  const transport = createMotionTransport({ plan, root, generation: 1, pagePath: '/pure', visualMode: 'reduced',
    createAdapter: createDefaultMotionAdapterFactory(), visualAdapter: visual.adapter })
  cleanups.push(() => transport.dispose())
  await transport.sampleAt(500, 'full')
  expect(Number(root.querySelector('h1')!.style.opacity)).toBeCloseTo(0.5)
  expect(Number(otherRoot.querySelector('h1')!.style.opacity)).toBe(0)
  await transport.sampleAt(0, 'reduced')
  expect(Number(root.querySelector('h1')!.style.opacity)).toBe(1)
  expect(transport.getSnapshot().intent).toBe('stopped')
})

it('拒绝回调、外部目标、无限播放参数和同属性重叠，构造失败恢复样式', () => {
  const root = makeVisualRoot()
  const outside = document.createElement('h1')
  document.body.append(outside)
  expect(() => createNativeVisual(root, {}, timeline => {
    timeline.fromTo('h1', { opacity: 0 }, { opacity: 1, duration: 1, onComplete() {} })
  })).toThrow('onComplete')
  expect(() => createNativeVisual(root, {}, timeline => {
    timeline.fromTo(outside, { opacity: 0 }, { opacity: 1, duration: 1 })
  })).toThrow('当前页面')
  expect(() => createNativeVisual(root, {}, timeline => {
    timeline.fromTo('h1', { opacity: 0 }, { opacity: 1, duration: 1, repeat: -1 })
  })).toThrow('repeat')
  expect(() => createNativeVisual(root, {}, timeline => {
    timeline.fromTo('h1', { opacity: 0 }, { opacity: 1, duration: 1 }, 0)
    timeline.fromTo('h1', { opacity: 1 }, { opacity: 0, duration: 1 }, 0.5)
  })).toThrow('重叠属性')
  expect(root.querySelector('h1')!.style.opacity).toBe('0.8')
})
