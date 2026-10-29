/** 文件功能：验证视觉资源等待在离页、超时和正常完成后释放轮询、图片监听、字体观察与绘制帧。 */
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { waitForEditorVisualAssets } from './visual-assets'

beforeEach(() => { vi.useFakeTimers(); document.body.innerHTML = '' })
afterEach(() => {
  document.body.innerHTML = ''
  Reflect.deleteProperty(document, 'fonts')
  vi.unstubAllGlobals(); vi.useRealTimers()
})

/** 让探测到达当前资源等待，不通过推进时钟伪造资源已经完成。 */
async function flush(): Promise<void> { for (let i = 0; i < 30; i += 1) await Promise.resolve() }

/** 构造没有 load 结果的真实 img，避免依赖测试环境的网络行为。 */
function pendingImage(): HTMLImageElement {
  const image = document.createElement('img')
  image.src = 'https://assets.example/pending.png'
  Object.defineProperty(image, 'complete', { value: false, configurable: true })
  document.body.append(image)
  return image
}

it('已经取消的准备不探测页面，也不创建延时或绘制帧', async () => {
  const controller = new AbortController(); controller.abort()
  const query = vi.spyOn(document, 'querySelectorAll')
  await expect(waitForEditorVisualAssets({ signal: controller.signal })).rejects.toMatchObject({ name: 'AbortError' })
  expect(query).not.toHaveBeenCalled()
  expect(vi.getTimerCount()).toBe(0)
})

it.each(['view-preview', 'drawio', 'mermaid', 'model'])('%s 准备中的轮询在取消时立即释放', async kind => {
  document.body.innerHTML = `<div data-runtime-${kind}-state="loading"></div>`
  const controller = new AbortController()
  const waiting = waitForEditorVisualAssets({ signal: controller.signal })
  const cancelled = expect(waiting).rejects.toMatchObject({ name: 'AbortError' })
  await flush()
  expect(vi.getTimerCount()).toBeGreaterThan(0)
  controller.abort(); await cancelled
  expect(vi.getTimerCount()).toBe(0)
})

it('取消会移除 img 的 load/error 监听，迟到图片事件不产生解码', async () => {
  const image = pendingImage(), remove = vi.spyOn(image, 'removeEventListener')
  image.decode = vi.fn().mockResolvedValue(undefined)
  const controller = new AbortController()
  const waiting = waitForEditorVisualAssets({ signal: controller.signal })
  const cancelled = expect(waiting).rejects.toMatchObject({ name: 'AbortError' })
  await flush(); controller.abort(); await cancelled
  expect(remove.mock.calls.map(call => call[0])).toEqual(expect.arrayContaining(['load', 'error']))
  image.dispatchEvent(new Event('load'))
  expect(image.decode).not.toHaveBeenCalled()
  expect(vi.getTimerCount()).toBe(0)
})

it('取消背景图探测会移除临时 Image 的监听', async () => {
  const instances: EventTarget[] = []
  class ProbeImage extends EventTarget { src = ''; constructor() { super(); instances.push(this) } }
  vi.stubGlobal('Image', ProbeImage)
  document.body.innerHTML = '<div style="background-image: url(https://assets.example/background.png)"></div>'
  const controller = new AbortController()
  const waiting = waitForEditorVisualAssets({ signal: controller.signal })
  const cancelled = expect(waiting).rejects.toMatchObject({ name: 'AbortError' })
  await flush()
  expect(instances).toHaveLength(1)
  const remove = vi.spyOn(instances[0], 'removeEventListener')
  controller.abort(); await cancelled
  expect(remove.mock.calls.map(call => call[0])).toEqual(expect.arrayContaining(['load', 'error']))
  expect(vi.getTimerCount()).toBe(0)
})

it('不能取消的 decode 在退出后不阻塞，迟到拒绝被消费', async () => {
  const image = pendingImage()
  Object.defineProperties(image, { complete: { value: true }, naturalWidth: { value: 100 }, naturalHeight: { value: 100 } })
  let rejectDecode!: (error: unknown) => void
  image.decode = vi.fn(() => new Promise<void>((_, reject) => { rejectDecode = reject }))
  const controller = new AbortController()
  const waiting = waitForEditorVisualAssets({ signal: controller.signal })
  const cancelled = expect(waiting).rejects.toMatchObject({ name: 'AbortError' })
  await flush(); expect(image.decode).toHaveBeenCalledOnce()
  controller.abort(); await cancelled
  rejectDecode(new Error('迟到解码失败')); await flush()
  expect(vi.getTimerCount()).toBe(0)
})

it('字体准备中的取消不会等到 fonts.ready 或整体期限', async () => {
  Object.defineProperty(document, 'fonts', { configurable: true, value: { ready: new Promise(() => {}) } })
  const controller = new AbortController()
  const waiting = waitForEditorVisualAssets({ signal: controller.signal })
  const cancelled = expect(waiting).rejects.toMatchObject({ name: 'AbortError' })
  await flush(); controller.abort(); await cancelled
  expect(vi.getTimerCount()).toBe(0)
})

it('等待绘制帧时取消会撤销 RAF，后台窗口无需再获得一帧才能退出', async () => {
  const cancelFrame = vi.spyOn(globalThis, 'cancelAnimationFrame'), controller = new AbortController()
  const waiting = waitForEditorVisualAssets({ signal: controller.signal })
  const cancelled = expect(waiting).rejects.toMatchObject({ name: 'AbortError' })
  await flush(); controller.abort(); await cancelled
  expect(cancelFrame).toHaveBeenCalled()
  expect(vi.getTimerCount()).toBe(0)
})

it('资源提前成功后取消未胜出的长超时，不取消父信号', async () => {
  Object.defineProperty(document, 'fonts', { configurable: true, value: { ready: Promise.resolve() } })
  const controller = new AbortController(), waiting = waitForEditorVisualAssets({ signal: controller.signal })
  await vi.advanceTimersByTimeAsync(50)
  expect((await waiting).ok).toBe(true)
  expect(vi.getTimerCount()).toBe(0)
  expect(controller.signal.aborted).toBe(false)
})

it('图片超时保留 pending 语义，并在返回后释放加载监听', async () => {
  const image = pendingImage(), remove = vi.spyOn(image, 'removeEventListener')
  const waiting = waitForEditorVisualAssets({ timeoutMs: 100 })
  await vi.advanceTimersByTimeAsync(150)
  expect(await waiting).toMatchObject({ ok: false, timedOut: true, pending: [{ type: 'image' }] })
  expect(remove.mock.calls.map(call => call[0])).toEqual(expect.arrayContaining(['load', 'error']))
  expect(vi.getTimerCount()).toBe(0)
})
