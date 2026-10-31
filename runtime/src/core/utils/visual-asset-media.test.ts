// @vitest-environment jsdom
/** 文件功能：验证静态视频海报、首帧、资源失败、取消和零播放，供所有捕获出口共用。 */
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { initializeRuntimeExecution, resetRuntimeExecutionForTests } from '@/core/execution/execution-scope'
import { waitForEditorVisualAssets } from './visual-assets'

beforeEach(() => {
  vi.useFakeTimers()
  initializeRuntimeExecution('?runtimeCapture=1')
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {})
  vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => {})
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue()
})
afterEach(() => {
  document.body.innerHTML = ''
  vi.restoreAllMocks()
  vi.useRealTimers()
  resetRuntimeExecutionForTests()
})

/** 可控解码状态的视频，不引入真实媒体或浏览器网络。 */
function video(poster = '') {
  document.body.innerHTML = '<video src="/demo.mp4" autoplay></video>'
  const target = document.querySelector('video')!
  if (poster) target.poster = poster
  let frame = false
  Object.defineProperties(target, {
    readyState: { get: () => frame ? 2 : 0 },
    videoWidth: { get: () => frame ? 320 : 0 },
    videoHeight: { get: () => frame ? 180 : 0 },
  })
  return { target, ready() { frame = true; target.dispatchEvent(new Event('loadeddata')) } }
}

/** 海报独立于视频源，通过真实 img 事件与 decode Promise 驱动。 */
function posterImage() {
  const image = document.createElement('img')
  Object.defineProperty(image, 'complete', { value: false })
  image.decode = vi.fn().mockResolvedValue(undefined)
  const create = document.createElement.bind(document)
  vi.spyOn(document, 'createElement').mockImplementation(((tag: string, options?: ElementCreationOptions) => tag === 'img' ? image : create(tag, options)) as typeof document.createElement)
  return image
}

it('无海报等待真实首帧，始终不调用 play 或推进 currentTime', async () => {
  const { target, ready } = video()
  const pending = waitForEditorVisualAssets({ timeoutMs: 500 })
  await vi.advanceTimersByTimeAsync(20)
  let settled = false
  void pending.then(() => { settled = true })
  expect(settled).toBe(false)
  ready()
  await vi.advanceTimersByTimeAsync(50)
  expect(await pending).toMatchObject({ ok: true, total: 1, loaded: 1 })
  expect(target.play).not.toHaveBeenCalled()
  expect(target.currentTime).toBe(0)
  expect(target.hasAttribute('autoplay')).toBe(false)
})

it('海报解码后恢复 poster，不等待失败的视频；重复探测只重置一次', async () => {
  const { target } = video('/poster.png')
  Object.defineProperty(target, 'error', { value: { code: 4 } })
  const image = posterImage()
  for (let index = 0; index < 2; index += 1) {
    const pending = waitForEditorVisualAssets({ timeoutMs: 500 })
    await vi.advanceTimersByTimeAsync(1)
    image.dispatchEvent(new Event('load'))
    await vi.advanceTimersByTimeAsync(50)
    expect((await pending).ok).toBe(true)
  }
  expect(image.decode).toHaveBeenCalledTimes(2)
  expect(target.load).toHaveBeenCalledTimes(1)
  expect(target.play).not.toHaveBeenCalled()
  expect(target.preload).toBe('none')
})

it('海报失败属于资源失败，即使视频已有首帧也不能忽略坏海报', async () => {
  const { ready } = video('/broken.png')
  ready()
  const image = posterImage()
  const pending = waitForEditorVisualAssets({ timeoutMs: 500 })
  await vi.advanceTimersByTimeAsync(1)
  image.dispatchEvent(new Event('error'))
  await vi.advanceTimersByTimeAsync(50)
  expect(await pending).toMatchObject({ ok: false, timedOut: false, failed: [{ type: 'video', message: '视频海报加载失败。' }] })
})

it('无海报解码失败与超时分别记为 failed 与 pending', async () => {
  const { target } = video()
  let pending = waitForEditorVisualAssets({ timeoutMs: 100 })
  await vi.advanceTimersByTimeAsync(1)
  Object.defineProperty(target, 'error', { value: { code: 3 }, configurable: true })
  target.dispatchEvent(new Event('error'))
  await vi.advanceTimersByTimeAsync(50)
  expect(await pending).toMatchObject({ ok: false, timedOut: false, failed: [{ type: 'video' }] })
  Object.defineProperty(target, 'error', { value: null })
  pending = waitForEditorVisualAssets({ timeoutMs: 100 })
  await vi.advanceTimersByTimeAsync(150)
  expect(await pending).toMatchObject({ ok: false, timedOut: true, pending: [{ type: 'video' }] })
})

it.each(['frame', 'poster'])('%s 等待取消后撤销媒体或海报监听，不遗留计时器', async mode => {
  const { target } = video(mode === 'poster' ? '/poster.png' : '')
  const image = mode === 'poster' ? posterImage() : null
  const remove = vi.spyOn(image || target, 'removeEventListener')
  const controller = new AbortController()
  const pending = waitForEditorVisualAssets({ timeoutMs: 500, signal: controller.signal })
  const rejection = expect(pending).rejects.toMatchObject({ name: 'AbortError' })
  await vi.advanceTimersByTimeAsync(1)
  controller.abort()
  await rejection
  expect(remove).toHaveBeenCalled()
  expect(vi.getTimerCount()).toBe(0)
})

it('交互预览不准备静态视频，不改变用户媒体状态', async () => {
  initializeRuntimeExecution('?runtimeMode=presenter')
  const { target } = video()
  const pending = waitForEditorVisualAssets({ timeoutMs: 100, includeAnimations: false })
  await vi.advanceTimersByTimeAsync(50)
  expect((await pending).ok).toBe(true)
  expect(target.pause).not.toHaveBeenCalled()
  expect(target.load).not.toHaveBeenCalled()
})
