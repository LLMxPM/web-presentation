/** 文件功能：验证开发调试能经公开声明播放 Scene，并覆盖生产禁装、静态零启动和调试所有权释放。 */
import { createApp, defineComponent, h, ref } from 'vue'
import { gsap } from 'gsap'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { initializeRuntimeExecution, resetRuntimeExecutionForTests } from '@/core/execution/execution-scope'
import { usePageScene } from '@/runtime-kit/public/composables/motion/usePageScene.v1'
import { installPageSceneDebug } from './dev-debug'
import { deferred } from './session-test-helpers'
import type { SceneTaskContext } from './types'

const { assets, legacy } = vi.hoisted(() => ({ assets: vi.fn(), legacy: vi.fn() }))
vi.mock('@/core/utils/visual-assets', () => ({ waitForEditorVisualAssets: assets }))
vi.mock('@/core/motion/page-motion-contract', () => ({ findPageMotionHandle: legacy }))
const READY = { ok: true, failed: [], pending: [], timedOut: false, loaded: 0, total: 0, waitedMs: 0 }
const cleanups: Array<() => void> = []
let sequence = 0

beforeEach(() => {
  gsap.ticker.sleep(); vi.useFakeTimers(); vi.stubEnv('DEV', true)
  initializeRuntimeExecution('?runtimeExecution=interactive-preview')
  assets.mockReset(); assets.mockResolvedValue(READY); legacy.mockReset(); legacy.mockReturnValue(null)
})
afterEach(() => {
  cleanups.splice(0).reverse().forEach(cleanup => cleanup())
  document.body.innerHTML = ''; Reflect.deleteProperty(document, 'fullscreenElement')
  gsap.ticker.sleep(); vi.useRealTimers(); vi.unstubAllEnvs(); resetRuntimeExecutionForTests()
})

/** 使用真实公开 setup 入口；DOM 挂载不执行定义，任务 Promise 可显式延迟。 */
function page(pending = false) {
  const host = document.createElement('div'), id = `scene-page-${++sequence}`; document.body.append(host)
  const completion = deferred(), cleanup = vi.fn()
  let active!: SceneTaskContext
  const run = vi.fn((context: SceneTaskContext) => {
    active = context; context.onCleanup(cleanup)
    if (pending) return completion.promise
  })
  const define = vi.fn(scene => scene.task({ id: 'task', role: 'blocking', run }))
  const app = createApp(defineComponent({ setup() {
    const root = ref<HTMLElement | null>(null)
    usePageScene({ root, define })
    return () => h('section', { id, ref: root }, '默认可读内容')
  } }))
  app.mount(host)
  let mounted = true
  const unmount = () => { if (mounted) { mounted = false; app.unmount() } }
  cleanups.push(unmount)
  return { host, root: host.firstElementChild as HTMLElement, id, run, define, cleanup, completion, unmount, active: () => active }
}

/** 刷新资源/准备/启动链路，不用时间推进替代真实完成。 */
async function flush(): Promise<void> { for (let i = 0; i < 35; i += 1) await Promise.resolve() }

/** 安装并登记清理，测试通过浏览器实际全局入口调用，不访问私有 slot。 */
function install() {
  cleanups.push(installPageSceneDebug())
  return window.__RUNTIME_SCENE_DEBUG__!
}

it('公开声明挂载不启动，开发入口可以播放、读状态和停止清理', async () => {
  const p = page(true), api = install()
  expect(p.define).not.toHaveBeenCalled()
  expect(api.read()).toBeNull()
  expect((await api.play())?.phase).toBe('running')
  expect(p.run).toHaveBeenCalledOnce()
  expect(api.read()?.hasBlocking).toBe(true)
  expect(api.stop()?.phase).toBe('stopped')
  expect(p.active().signal.aborted).toBe(true)
  expect(p.cleanup).toHaveBeenCalledOnce()
  expect(api.read()).toBeNull()
  p.completion.resolve(); await flush()
  expect(vi.getTimerCount()).toBe(0)
})

it('完成状态可读，重复播放创建新 generation 并先清理上一轮', async () => {
  const p = page(), api = install()
  await api.play(); await flush()
  const previous = api.read()!
  expect(previous.phase).toBe('completed')
  await api.play(); await flush()
  expect(api.read()!.generation).toBeGreaterThan(previous.generation)
  expect(p.cleanup).toHaveBeenCalledOnce()
  expect(p.run).toHaveBeenCalledTimes(2)
})

it('多画布必须选作用域，选择器只播放指定的公开声明', async () => {
  const a = page(), b = page(), api = install()
  await expect(api.play()).rejects.toMatchObject({ code: 'SCENE_DEFINITION_DUPLICATED' })
  await api.play(`#${b.id}`)
  expect(a.run).not.toHaveBeenCalled()
  expect(b.run).toHaveBeenCalledOnce()
})

it('声明缺失给出明确错误，不伪造已经启动', async () => {
  const api = install()
  await expect(api.play('#missing')).rejects.toMatchObject({ code: 'SCENE_DEBUG_SCOPE_MISSING' })
  await expect(api.play()).rejects.toMatchObject({ code: 'SCENE_DEBUG_DEFINITION_MISSING' })
  expect(assets).not.toHaveBeenCalled()
})

it.each(['capture', 'export', 'thumbnail'])('%s 全局策略禁止启动和资源等待', async kind => {
  const p = page(), api = install()
  initializeRuntimeExecution(`?runtimeExecution=${kind}`)
  expect(await api.play()).toBeNull()
  expect(p.define).not.toHaveBeenCalled()
  expect(assets).not.toHaveBeenCalled()
})

it('嵌套缩略图不能借交互预览全局策略启动', async () => {
  const p = page(), api = install()
  p.host.dataset.runtimeExecution = 'thumbnail'
  expect(await api.play(p.root)).toBeNull()
  expect(p.define).not.toHaveBeenCalled()
  expect(assets).not.toHaveBeenCalled()
})

it('生产模式不安装调试入口', () => {
  vi.stubEnv('DEV', false)
  const dispose = installPageSceneDebug()
  expect(window.__RUNTIME_SCENE_DEBUG__).toBeUndefined()
  dispose()
})

it('准备中停止立即返回，旧资源结果不能执行定义', async () => {
  const p = page(), api = install(), pending = deferred()
  assets.mockReturnValue(pending.promise)
  const preparing = api.play(); await flush()
  const signal = assets.mock.calls[0][0].signal as AbortSignal
  api.stop()
  expect(await preparing).toBeNull()
  expect(signal.aborted).toBe(true)
  pending.resolve(); await flush()
  expect(p.define).not.toHaveBeenCalled()
})

it('播放中页面卸载会取消任务，迟到完成不复活', async () => {
  const p = page(true), api = install()
  await api.play(); p.unmount(); await flush()
  expect(p.active().signal.aborted).toBe(true)
  expect(p.cleanup).toHaveBeenCalledOnce()
  p.completion.resolve(); await flush()
  expect(api.read()).toBeNull()
})

it('准备中 DOM 被移除也立即取消，尚未执行 define 时同样释放', async () => {
  const p = page(), api = install(), pending = deferred()
  assets.mockReturnValue(pending.promise)
  const preparing = api.play(); await flush()
  p.root.remove(); await flush()
  expect(await preparing).toBeNull()
  pending.resolve(); await flush()
  expect(p.define).not.toHaveBeenCalled()
})

it('开发入口重装先停止旧会话，旧 dispose 不删除新入口', async () => {
  const p = page(true), firstDispose = installPageSceneDebug(), old = window.__RUNTIME_SCENE_DEBUG__!
  await old.play()
  const current = install()
  expect(p.cleanup).toHaveBeenCalledOnce()
  firstDispose()
  expect(window.__RUNTIME_SCENE_DEBUG__).toBe(current)
  expect(await old.play()).toBeNull()
})

it('正式放映期间拒绝调试，进入全屏会释放已有调试任务', async () => {
  const p = page(true), api = install()
  await api.play()
  Object.defineProperty(document, 'fullscreenElement', { configurable: true, value: document.body })
  document.dispatchEvent(new Event('fullscreenchange'))
  expect(p.cleanup).toHaveBeenCalledOnce()
  await expect(api.play()).rejects.toMatchObject({ code: 'SCENE_DEBUG_PRESENTING' })
})

it('同页旧时间轴不会与开发 Scene 重复启动', async () => {
  const p = page(), api = install()
  legacy.mockReturnValue({})
  await expect(api.play()).rejects.toMatchObject({ code: 'SCENE_DEBUG_LEGACY_CONFLICT' })
  expect(p.define).not.toHaveBeenCalled()
})

it('导航提交前清理当前调试会话，即使旧 DOM 仍在过渡层中', async () => {
  const router = createRouter({ history: createMemoryHistory(), routes: ['/a', '/b'].map(path => ({ path, component: { render: () => h('div') } })) })
  await router.push('/a'); await router.isReady()
  const p = page(true)
  cleanups.push(installPageSceneDebug(router))
  await window.__RUNTIME_SCENE_DEBUG__!.play()
  await router.push('/b')
  expect(p.root.isConnected).toBe(true)
  expect(p.active().signal.aborted).toBe(true)
  expect(p.cleanup).toHaveBeenCalledOnce()
})

it('资源失败保留可读错误状态，不执行页面定义', async () => {
  const p = page(), api = install()
  assets.mockResolvedValue({ ...READY, ok: false, failed: [{ message: '私有地址 /secret' }] })
  expect(await api.play()).toMatchObject({ phase: 'failed', issue: { code: 'SCENE_PAGE_ASSETS_FAILED' } })
  expect(api.read()?.issue?.message).not.toContain('/secret')
  expect(p.define).not.toHaveBeenCalled()
})
