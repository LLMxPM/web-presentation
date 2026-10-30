/** 文件功能：验证正式预览只接受父窗口握手后的 Scene 命令，事件状态完整且退出释放任务。 */
import { createApp, defineComponent, h, ref } from 'vue'
import { gsap } from 'gsap'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { initializeRuntimeExecution, resetRuntimeExecutionForTests } from '@/core/execution/execution-scope'
import { usePageScene } from '@/runtime-kit/public/composables/motion/usePageScene.v1'
import { deferred } from './session-test-helpers'
import type { SceneTaskContext } from './types'
import { createPageScenePreview } from './page-scene-preview'
import { installPreviewSceneBridge } from './preview-bridge'
import { parsePreviewSceneCommand, PREVIEW_SCENE_REQUEST_TYPE, PREVIEW_SCENE_STATE_TYPE } from './preview-protocol'

const { assets } = vi.hoisted(() => ({ assets: vi.fn() }))
vi.mock('@/core/utils/visual-assets', () => ({ waitForEditorVisualAssets: assets }))
const cleanups: Array<() => void> = []
const originalParent = Object.getOwnPropertyDescriptor(window, 'parent')!
beforeEach(() => {
  gsap.ticker.sleep(); vi.useFakeTimers(); initializeRuntimeExecution('?runtimeExecution=interactive-preview')
  assets.mockReset(); assets.mockResolvedValue({ ok: true, failed: [], pending: [], total: 0, loaded: 0, timedOut: false, waitedMs: 0 })
})
afterEach(() => {
  cleanups.splice(0).reverse().forEach(cleanup => cleanup()); document.body.innerHTML = ''
  Reflect.deleteProperty(document, 'hidden')
  Object.defineProperty(window, 'parent', originalParent); gsap.ticker.sleep(); vi.useRealTimers(); resetRuntimeExecutionForTests()
})

/** 使用公开组合式声明，真实挂载根 ref 与任务释放域。 */
function page() {
  const pending = deferred(), cleanup = vi.fn(), run = vi.fn()
  let active!: SceneTaskContext
  const app = createApp(defineComponent({ setup() {
    const root = ref<HTMLElement | null>(null)
    usePageScene({ root, define(scene) { scene.task({ id: 'content', role: 'blocking', run(context) {
      active = context; context.onCleanup(cleanup); run(); return pending.promise
    } }) } })
    return () => h('section', { ref: root }, '默认可读内容')
  } }))
  const element = document.createElement('div'); document.body.append(element); app.mount(element)
  let mounted = true
  const unmount = () => { if (mounted) { mounted = false; app.unmount() } }
  cleanups.push(unmount)
  return { element, run, cleanup, pending, unmount, active: () => active }
}

/** 不推进时间，仅排空声明、准备与启动消息。 */
async function flush(): Promise<void> { for (let i = 0; i < 40; i += 1) await Promise.resolve() }

/** 使用真实 WindowProxy 构造父窗口消息，避免绕开来源判断。 */
function parent() {
  const frame = document.createElement('iframe'); document.body.append(frame)
  const source = frame.contentWindow!
  Object.defineProperty(window, 'parent', { configurable: true, value: source })
  const post = vi.spyOn(source, 'postMessage').mockImplementation(() => {})
  const send = (action: string, origin = 'https://editor.example', sender: Window | null = source, extra: Record<string, unknown> = {}) => {
    window.dispatchEvent(new MessageEvent('message', { source: sender, origin,
      data: { type: PREVIEW_SCENE_REQUEST_TYPE, version: 1, action, ...extra } }))
  }
  const dispose = installPreviewSceneBridge(); cleanups.push(dispose)
  return { source, post, send, dispose }
}

it('声明挂载可发现但不会自动运行，正式预览显式播放和停止', async () => {
  const preview = createPageScenePreview(), change = vi.fn(); cleanups.push(preview.dispose)
  preview.subscribe(change)
  const p = page()
  expect(preview.read()).toMatchObject({ hasScene: true, phase: 'idle', generation: null })
  expect(change).toHaveBeenCalled(); expect(p.run).not.toHaveBeenCalled()
  expect(await preview.play()).toBe(true)
  expect(preview.read()).toMatchObject({ hasScene: true, phase: 'running', hasBlocking: true })
  preview.stop(); expect(preview.read().phase).toBe('stopped')
  expect(p.active().signal.aborted).toBe(true); expect(p.cleanup).toHaveBeenCalledOnce()
  p.unmount(); expect(preview.read().hasScene).toBe(false)
})

it('隐藏时开始预览不运行任务，freeze 不被 visibility 提前解除，resume 才运行', async () => {
  Object.defineProperty(document, 'hidden', { configurable: true, value: true })
  const p = page(), preview = createPageScenePreview(); cleanups.push(preview.dispose)
  await preview.play(); expect(p.run).not.toHaveBeenCalled()
  document.dispatchEvent(new Event('freeze'))
  Object.defineProperty(document, 'hidden', { configurable: true, value: false })
  document.dispatchEvent(new Event('visibilitychange')); await flush()
  expect(p.run).not.toHaveBeenCalled()
  document.dispatchEvent(new Event('resume')); await flush()
  expect(p.run).toHaveBeenCalledOnce()
  preview.dispose(); document.dispatchEvent(new Event('freeze')); document.dispatchEvent(new Event('resume')); await flush()
  expect(p.cleanup).toHaveBeenCalledOnce()
})

it('有限完成保持 completed 状态直到显式停止，不生成位置或进度字段', async () => {
  const p = page(), preview = createPageScenePreview(); cleanups.push(preview.dispose)
  await preview.play(); p.pending.resolve(); await flush()
  expect(preview.read()).toMatchObject({ phase: 'completed', hasBlocking: true })
  expect(preview.read()).not.toHaveProperty('positionMs')
  expect(preview.read()).not.toHaveProperty('durationMs')
  expect(p.cleanup).not.toHaveBeenCalled()
  preview.stop(); expect(p.cleanup).toHaveBeenCalledOnce()
})

it('同一窗口中的缩略图声明不会被正式预览误认成第二个播放者', async () => {
  const thumbnail = page(); thumbnail.element.dataset.runtimeExecution = 'thumbnail'
  const content = page(), preview = createPageScenePreview(); cleanups.push(preview.dispose)
  expect(preview.read().hasScene).toBe(true)
  await preview.play()
  expect(content.run).toHaveBeenCalledOnce(); expect(thumbnail.run).not.toHaveBeenCalled()
})

it('父窗口握手、来源与 origin 一起校验，未授权消息不启动', async () => {
  const p = page(), bridge = parent()
  bridge.send('play'); bridge.send('sync', 'null'); bridge.send('sync', 'https://editor.example', window)
  await flush(); expect(p.run).not.toHaveBeenCalled(); expect(bridge.post).not.toHaveBeenCalled()
  bridge.send('sync')
  expect(bridge.post).toHaveBeenLastCalledWith(expect.objectContaining({ type: PREVIEW_SCENE_STATE_TYPE, state: expect.objectContaining({ phase: 'idle', hasScene: true }) }), 'https://editor.example')
  bridge.send('sync', 'https://wrong.example'); bridge.send('play', 'https://wrong.example'); await flush()
  expect(p.run).not.toHaveBeenCalled()
  bridge.send('play'); await flush()
  expect(p.run).toHaveBeenCalledOnce()
  expect(bridge.post.mock.calls.some(([message]) => (message as { state?: { phase?: string } }).state?.phase === 'running')).toBe(true)
})

it('stop/unsync/卸载都取消任务，迟到播放结果不会重新推送旧状态', async () => {
  const p = page(), bridge = parent()
  bridge.send('sync'); bridge.send('play'); await flush()
  bridge.send('stop', 'https://editor.example', bridge.source, { requestId: 'stop-current' })
  expect(p.active().signal.aborted).toBe(true)
  expect(bridge.post).toHaveBeenLastCalledWith(expect.objectContaining({ requestId: 'stop-current', state: expect.objectContaining({ phase: 'stopped' }) }), 'https://editor.example')
  bridge.send('play'); await flush(); bridge.send('unsync')
  expect(p.cleanup).toHaveBeenCalledTimes(2)
  const count = bridge.post.mock.calls.length
  p.pending.resolve(); await flush(); bridge.send('play'); await flush()
  expect(bridge.post).toHaveBeenCalledTimes(count)
  bridge.dispose(); bridge.send('sync'); expect(bridge.post).toHaveBeenCalledTimes(count)
})

it.each(['capture', 'export', 'thumbnail'])('%s 不安装可执行的跨窗口预览', async kind => {
  const p = page(); initializeRuntimeExecution(`?runtimeExecution=${kind}`)
  const bridge = parent(); bridge.send('sync'); bridge.send('play'); await flush()
  expect(p.run).not.toHaveBeenCalled(); expect(assets).not.toHaveBeenCalled(); expect(bridge.post).not.toHaveBeenCalled()
})

it.each(['pause', 'restart', 'seek', 'set-visual-mode'])('旧动作 %s 明确拒绝', action => {
  expect(parsePreviewSceneCommand({ type: PREVIEW_SCENE_REQUEST_TYPE, version: 1, action })).toBeNull()
})

it('协议拒绝旧消息、旧字段、错误版本与过长 requestId', () => {
  const command = { type: PREVIEW_SCENE_REQUEST_TYPE, version: 1, action: 'play' }
  expect(parsePreviewSceneCommand(command)).toMatchObject({ action: 'play' })
  expect(parsePreviewSceneCommand({ ...command, type: 'runtime-preview-motion' })).toBeNull()
  expect(parsePreviewSceneCommand({ ...command, version: 2 })).toBeNull()
  expect(parsePreviewSceneCommand({ ...command, positionMs: 100 })).toBeNull()
  expect(parsePreviewSceneCommand({ ...command, requestId: 'x'.repeat(129) })).toBeNull()
})
