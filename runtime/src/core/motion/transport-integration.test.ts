/** 文件功能：跨真实适配器验证延后媒体、顺序视觉、捕获模式与主媒体重播。 */
import { afterEach, expect, it, vi } from 'vitest'
import { compilePageTimeline } from './compile'
import { createMotionTransport } from './transport'
import { createDefaultMotionAdapterFactory } from './default-adapters'
import type { MotionAdapterFactory } from './adapters'
import type { PageTimelineDefinition } from './types'

const cleanups: Array<() => void> = []
afterEach(() => { cleanups.splice(0).forEach(cleanup => cleanup()); document.body.innerHTML = '' })

/** 用受控墙钟驱动真实 transport 与适配器，媒体只替换浏览器原语。 */
function harness(definition: PageTimelineDefinition, factory = createDefaultMotionAdapterFactory(), mode: 'full' | 'reduced' = 'full') {
  const root = document.createElement('div')
  root.innerHTML = '<h1 class="title">标题</h1><video class="video"></video>'
  document.body.append(root)
  let wall = 0
  let callback: (() => void) | null = null
  const plan = compilePageTimeline(definition)
  const transport = createMotionTransport({ plan, root, pagePath: '/a', generation: 1, createAdapter: factory, visualMode: mode,
    now: () => wall, scheduler: { request(fn) { callback = fn; return 1 }, cancel() { callback = null } } })
  cleanups.push(() => transport.dispose())
  return { root, transport, async tick(time: number) { wall = time; const fn = callback; callback = null; fn?.(); await new Promise(resolve => setTimeout(resolve, 0)) } }
}

/** 模拟 currentTime/seeked 与 play/pause，测试本身不替换轨道调度。 */
function mockMedia(video: HTMLVideoElement) {
  let paused = true
  let time = 0
  Object.defineProperties(video, {
    paused: { get: () => paused }, duration: { value: 10 }, readyState: { value: 4 },
    currentTime: { get: () => time, set(value: number) { time = value; queueMicrotask(() => video.dispatchEvent(new Event('seeked'))) } },
  })
  video.play = vi.fn(async () => { paused = false })
  video.pause = vi.fn(() => { paused = true })
  return video
}

it('延后媒体在边界启动，暂停和定位不偷播，结束后停止', async () => {
  const { root, transport, tick } = harness({ schemaVersion: 1, timelineId: 'delayed', tracks: [
    { type: 'video', id: 'video', asset: 'demo', selector: '.video', startMs: 1000, outMs: 2000, muted: true },
  ] })
  const video = mockMedia(root.querySelector('video')!)
  await transport.play()
  expect(video.play).not.toHaveBeenCalled()
  await tick(100)
  expect(video.paused).toBe(true)
  await tick(1100)
  expect(video.paused).toBe(false)
  expect(video.play).toHaveBeenCalledTimes(1)
  transport.pause()
  await transport.seek(1050)
  expect(video.currentTime).toBeCloseTo(0.05)
  expect(video.paused).toBe(true)
  await transport.resume()
  expect(video.play).toHaveBeenCalledTimes(2)
  await tick(4000)
  expect(video.paused).toBe(true)
})

it('捕获模式覆盖宿主偏好，回执和实际像素状态一致且不改变偏好', async () => {
  const { root, transport } = harness({ schemaVersion: 1, timelineId: 'sample', tracks: [
    { type: 'dom', id: 'title', target: '.title', preset: 'fade', durationMs: 1000 },
  ] }, createDefaultMotionAdapterFactory(), 'reduced')
  const first = await transport.sampleAt(500, 'full')
  expect(first.visualMode).toBe('full')
  expect(Number(root.querySelector<HTMLElement>('.title')!.style.opacity)).toBeLessThan(1)
  expect(transport.visualMode).toBe('reduced')
  await transport.sampleAt(800, 'reduced')
  expect(Number(root.querySelector<HTMLElement>('.title')!.style.opacity)).toBe(1)
  expect((await transport.sampleAt(500, 'full')).stateDigest).toBe(first.stateDigest)
})

it('同属性非重叠段落可顺序及乱序采样，结束后恢复页面样式', async () => {
  const { root, transport } = harness({ schemaVersion: 1, timelineId: 'sequence', tracks: [
    { type: 'dom', id: 'enter', target: '.title', from: { opacity: 0 }, to: { opacity: 1 }, durationMs: 1000 },
    { type: 'dom', id: 'exit', target: '.title', from: { opacity: 1 }, to: { opacity: 0 }, durationMs: 1000, afterTrack: 'enter', offsetMs: 500 },
  ] })
  const element = root.querySelector<HTMLElement>('.title')!
  const first = await transport.sampleAt(500)
  expect(Number(element.style.opacity)).toBeGreaterThan(0)
  await transport.sampleAt(1200)
  expect(Number(element.style.opacity)).toBe(1)
  await transport.sampleAt(2000)
  expect(Number(element.style.opacity)).toBeLessThan(1)
  expect((await transport.sampleAt(500)).stateDigest).toBe(first.stateDigest)
  transport.dispose()
  expect(element.style.opacity).toBe('')
})

it('主媒体交接后重播或回拖，重新读取媒体进度及缓冲状态', async () => {
  const clock = { positionMs: 0, ended: false, buffering: false, blocked: false }
  const factory: MotionAdapterFactory = ({ track }) => ({ type: track.type, async prepare() {}, async applyAt({ positionMs }) {
    if (track.id === 'voice') { clock.positionMs = Math.min(positionMs, 1000); clock.ended = positionMs >= 1000 }
  }, async play() {}, pause() {}, getClock: track.id === 'voice' ? () => clock : undefined, dispose() {} })
  const { transport, tick } = harness({ schemaVersion: 1, timelineId: 'replay', tracks: [
    { type: 'audio', id: 'voice', asset: 'voice', role: 'primary', outMs: 1000 },
    { type: 'dom', id: 'title', target: '.title', preset: 'fade', durationMs: 3000 },
  ] }, factory)
  await transport.play()
  clock.positionMs = 1000; clock.ended = true
  await tick(1000)
  await transport.restart()
  clock.positionMs = 50
  await tick(1100)
  expect(transport.getSnapshot().positionMs).toBe(50)
  await transport.seek(1500)
  await transport.seek(200)
  clock.buffering = true
  await tick(1200)
  expect(transport.getSnapshot()).toMatchObject({ phase: 'buffering', positionMs: 200 })
})
