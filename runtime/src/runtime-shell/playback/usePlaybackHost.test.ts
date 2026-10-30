/** 文件功能：真实 Router/Vue 宿主接入 Scene，验证全屏门槛、过渡准备、取消、推进与静态零播放。 */
import { createApp, defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { gsap } from 'gsap'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { reloadAllConfigs } from '@/core/utils/config'
import { setRuntimePreloadedConfig } from '@/core/utils/path'
import { initializeRuntimeExecution, resetRuntimeExecutionForTests } from '@/core/execution/execution-scope'
import { getRuntimeSession } from '@/core/router/runtime-session'
import { registerPageSceneDefinition } from '@/core/scene/page-scene-definition'
import { deferred } from '@/core/scene/session-test-helpers'
import type { SceneTaskContext } from '@/core/scene/types'
import { usePlaybackHost, type PlaybackHost } from './usePlaybackHost'
import PlaybackHostBridge from './PlaybackHostBridge.vue'

const { assets } = vi.hoisted(() => ({ assets: vi.fn() }))
vi.mock('@/core/utils/visual-assets', () => ({ waitForEditorVisualAssets: assets }))
const cleanups: Array<() => void> = []
const READY = { ok: true, timedOut: false, failed: [], pending: [], total: 0, loaded: 0, waitedMs: 0 }

beforeEach(async () => {
  gsap.ticker.sleep(); vi.useFakeTimers(); assets.mockReset(); assets.mockResolvedValue(READY)
  initializeRuntimeExecution('?runtimeExecution=presentation')
  Object.defineProperty(document, 'fullscreenElement', { configurable: true, value: document.documentElement })
  setRuntimePreloadedConfig({ routes: { playback: { autoStart: false, loop: false }, routes: ['/a', '/b'].map((path, index) => ({
    route: path.slice(1), component: `@/views/${path.slice(1)}.vue`, meta: { order: index + 1, title: path, advance: { mode: 'timer', delayMs: 1000 } },
  })) }, app: {}, icons: { static_icons: [] } } as never)
  await reloadAllConfigs()
})
afterEach(() => {
  cleanups.splice(0).reverse().forEach(cleanup => cleanup()); gsap.ticker.sleep()
  document.body.innerHTML = ''; Reflect.deleteProperty(document, 'fullscreenElement'); Reflect.deleteProperty(document, 'hidden')
  setRuntimePreloadedConfig(undefined); resetRuntimeExecutionForTests(); vi.useRealTimers()
})

/** 刷新 Router 和共享准备链路，保留真实任务完成边界。 */
async function flush(): Promise<void> { for (let i = 0; i < 45; i += 1) await Promise.resolve() }

/** 挂载实际放映宿主或控制条，画布由公开 Scene 登记器提供。 */
async function mount(bridge = false, startOnMount = false) {
  const router = createRouter({ history: createMemoryHistory(), routes: ['/a', '/b'].map(path => ({ path, component: { render: () => h('div') } })) })
  await router.push('/a'); await router.isReady()
  const pending = deferred(), run = vi.fn(), cleanup = vi.fn()
  let context!: SceneTaskContext
  for (const path of ['/a', '/b']) {
    const root = document.createElement('section'); root.className = 'runtime-page-print-source'; root.dataset.runtimeRoutePath = path; document.body.append(root)
    cleanups.push(registerPageSceneDefinition({ root: () => root, define(scene) {
      if (path === '/a') scene.task({ id: 'visual', role: 'blocking', run(value) { context = value; value.onCleanup(cleanup); run(); return pending.promise } })
    } }))
  }
  let host!: PlaybackHost
  const Root = bridge ? PlaybackHostBridge : defineComponent({ setup() { host = usePlaybackHost({ startOnMount }); return () => h('div') } })
  const element = document.createElement('div'); document.body.append(element)
  const app = createApp(Root); app.use(router); app.mount(element)
  let mounted = true
  const unmount = () => { if (mounted) { mounted = false; app.unmount() } }
  cleanups.push(unmount)
  const session = getRuntimeSession(router)
  return { host, router, session, element, run, cleanup, pending, context: () => context, unmount }
}

it('只有根元素全屏时才创建 Deck；原 auto_start=false 不改变页面推进配置', async () => {
  Object.defineProperty(document, 'fullscreenElement', { configurable: true, value: null })
  const f = await mount()
  expect(f.host.start()).toBe(false); expect(f.host.snapshot.value).toBeNull(); expect(assets).not.toHaveBeenCalled()
  Object.defineProperty(document, 'fullscreenElement', { configurable: true, value: document.documentElement })
  expect(f.host.start()).toBe(true); await flush(); expect(f.run).not.toHaveBeenCalled()
  f.session.transitionSettled.value = { path: '/a', generation: 1 }; await flush()
  expect(f.run).toHaveBeenCalledOnce()
  await vi.advanceTimersByTimeAsync(1000)
  expect(f.router.currentRoute.value.path).toBe('/b'); expect(f.context().signal.aborted).toBe(true)
})

it.each(['capture', 'export', 'thumbnail', 'interactive-preview'])('%s 不创建放映控制器或资源等待', async kind => {
  initializeRuntimeExecution(`?runtimeExecution=${kind}`)
  const f = await mount(false, true); await flush()
  expect(f.host.start()).toBe(false); expect(f.host.snapshot.value).toBeNull(); expect(assets).not.toHaveBeenCalled()
})

it('视频元素自身全屏不建立放映', async () => {
  Object.defineProperty(document, 'fullscreenElement', { configurable: true, value: document.createElement('video') })
  const f = await mount(); expect(f.host.start()).toBe(false)
})

it.each(['停止', '退出全屏', '卸载'])('%s 立即撤销正在准备的资源，迟到结果不执行 Scene', async action => {
  const f = await mount(), pending = deferred()
  assets.mockReturnValue(pending.promise)
  f.host.start(); f.session.transitionSettled.value = { path: '/a', generation: 1 }; await flush()
  const signal = assets.mock.calls[0][0].signal as AbortSignal
  if (action === '停止') f.host.stop()
  else if (action === '卸载') f.unmount()
  else {
    Object.defineProperty(document, 'fullscreenElement', { configurable: true, value: null })
    document.dispatchEvent(new Event('fullscreenchange'))
  }
  await flush(); expect(signal.aborted).toBe(true)
  pending.resolve(); await flush(); expect(f.run).not.toHaveBeenCalled()
})

it('手动路由切换释放旧 Scene，目标过渡完成才运行新页', async () => {
  const f = await mount(); f.host.start()
  f.session.transitionSettled.value = { path: '/a', generation: 1 }; await flush()
  await f.router.push('/b'); await flush()
  expect(f.context().signal.aborted).toBe(true); expect(f.cleanup).toHaveBeenCalledOnce()
  expect(f.host.snapshot.value?.state).toBe('preparing')
  f.session.transitionSettled.value = { path: '/b', generation: 2 }; await flush()
  expect(f.host.snapshot.value?.state).toBe('playing')
})

it('保持/释放只影响翻页，后台冻结按剩余预算恢复', async () => {
  const f = await mount(); f.host.start(); f.session.transitionSettled.value = { path: '/a', generation: 1 }; await flush()
  f.host.hold(); await vi.advanceTimersByTimeAsync(2000)
  expect(f.context().signal.aborted).toBe(false); expect(f.router.currentRoute.value.path).toBe('/a')
  f.host.release(); await vi.advanceTimersByTimeAsync(700)
  document.dispatchEvent(new Event('freeze')); await vi.advanceTimersByTimeAsync(5000)
  expect(f.router.currentRoute.value.path).toBe('/a')
  Object.defineProperty(document, 'hidden', { configurable: true, value: false })
  document.dispatchEvent(new Event('resume')); await vi.advanceTimersByTimeAsync(299)
  expect(f.router.currentRoute.value.path).toBe('/a')
  await vi.advanceTimersByTimeAsync(1); expect(f.router.currentRoute.value.path).toBe('/b')
})

it('控制条接入正式 Scene 并提供保持、静音、翻页和退出入口', async () => {
  const f = await mount(true)
  f.session.transitionSettled.value = { path: '/a', generation: 1 }; await flush()
  expect(f.run).toHaveBeenCalledOnce()
  const toggle = f.element.querySelector<HTMLButtonElement>('[data-testid="playback-hold-toggle"]')!
  toggle.click(); await flush(); expect(f.element.textContent).toContain('释放本页')
  await vi.advanceTimersByTimeAsync(2000); expect(f.context().signal.aborted).toBe(false)
  f.element.querySelector<HTMLButtonElement>('[data-testid="playback-mute-toggle"]')!.click(); await flush()
  expect(f.session.audioMuted.value).toBe(true)
  expect(f.element.querySelector('[aria-label="退出放映"]')).not.toBeNull()
  expect(f.session.stopPlayback).toBeTypeOf('function')
  f.unmount(); expect(f.session.stopPlayback).toBeNull(); expect(f.cleanup).toHaveBeenCalledOnce()
})
