/* eslint-disable vue/one-component-per-file */
// @vitest-environment jsdom
/** 文件功能：验证 Router 绑定、就绪时序、旧事件过滤、导航失败与捕获禁推进。 */
import { createApp, defineComponent, h, nextTick } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { reloadAllConfigs } from '@/core/utils/config'
import { setRuntimePreloadedConfig } from '@/core/utils/path'
import { getRuntimeSession } from '@/core/router/runtime-session'
import { initializeRuntimeExecution, resetRuntimeExecutionForTests } from '@/core/execution/execution-scope'
import { buildPlaybackPages, usePlaybackHost, type PlaybackHost } from './usePlaybackHost'

const { waitForAssets } = vi.hoisted(() => ({ waitForAssets: vi.fn() }))
vi.mock('@/core/utils/visual-assets', () => ({ waitForEditorVisualAssets: waitForAssets }))

const READY = { ok: true, timedOut: false, total: 0, loaded: 0, failed: [], pending: [], waitedMs: 0 }

function preloadPlaybackConfig(options: {
  autoStart?: boolean
  loop?: boolean
  delays?: Record<string, number>
  advances?: Record<string, { mode: 'manual' | 'timer'; delayMs: number }>
} = {}) {
  const delays = options.delays ?? { '/a': 1000, '/b': 2000 }
  const route = (name: string, order: number, hidden = false) => ({
    route: name.slice(1),
    component: `@/views/${name.slice(1)}.vue`,
    meta: {
      title: name,
      order,
      hidden,
      advance: options.advances?.[name] ?? { mode: 'timer', delayMs: delays[name] ?? 1000 },
    },
  })
  setRuntimePreloadedConfig({
    app: {
      app: {
        icon: 'slider',
        title: '放映测试',
        description: '',
        page: { width: 1920, height: 1080, baseFontSize: '24px', iconDefaultStrokeWidth: 2 },
        features: { showPdfExportButton: false, menuMode: 'text' },
      },
    },
    routes: {
      playback: {
        autoStart: options.autoStart ?? false,
        loop: options.loop ?? false,
        advanceDefaults: { mode: 'manual', delayMs: 5000 },
      },
      transitionDefaults: { effect: 'none', durationMs: 0 },
      routes: [route('/a', 1), route('/b', 2), route('/hidden', 3, true)],
    },
    icons: { static_icons: [] },
  } as never)
}

function makeRouter() {
  const component = defineComponent({ render: () => h('div') })
  return createRouter({
    history: createMemoryHistory(),
    routes: ['/a', '/b', '/hidden'].map(path => ({ path, component })),
  })
}

function addPageElement(path: string): HTMLElement {
  const element = document.createElement('div')
  element.className = 'runtime-page-print-source'
  element.dataset.runtimeRoutePath = path
  document.body.append(element)
  return element
}

/** 挂载放映宿主组合式函数并暴露其接口。 */
function mountPlaybackHost(router: ReturnType<typeof makeRouter>) {
  let host: PlaybackHost | undefined
  const Root = defineComponent({
    setup() {
      host = usePlaybackHost()
      return () => h('div')
    },
  })
  const root = document.createElement('div')
  document.body.append(root)
  const app = createApp(Root)
  app.use(router)
  app.mount(root)
  expect(host).toBeDefined()
  return { app, host: host! }
}

/** 刷新 watcher、nextTick 与资源探测的 Promise 链。 */
async function flushAsync(): Promise<void> {
  for (let index = 0; index < 6; index += 1) {
    await nextTick()
    await Promise.resolve()
  }
}

beforeEach(async () => {
  vi.useFakeTimers()
  waitForAssets.mockReset()
  waitForAssets.mockResolvedValue(READY)
  resetRuntimeExecutionForTests()
  preloadPlaybackConfig()
  await reloadAllConfigs()
  addPageElement('/a')
  addPageElement('/b')
})

afterEach(() => {
  vi.useRealTimers()
  setRuntimePreloadedConfig(undefined)
  resetRuntimeExecutionForTests()
  document.body.innerHTML = ''
})

describe('buildPlaybackPages', () => {
  it('复用可见叶子目录并携带生效翻页配置', () => {
    const pages = buildPlaybackPages()
    expect(pages.map(page => page.path)).toEqual(['/a', '/b'])
    expect(pages[1].advance).toEqual({ mode: 'timer', delayMs: 2000 })
  })
})

describe('usePlaybackHost 自动开始与就绪', () => {
  it('自动开始只尝试一次，过渡与资源就绪后才计时并自动翻页', async () => {
    preloadPlaybackConfig({ autoStart: true })
    await reloadAllConfigs()
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    const session = getRuntimeSession(router)

    await flushAsync()
    expect(host.snapshot.value).toMatchObject({ state: 'preparing', path: '/a' })
    expect(waitForAssets).not.toHaveBeenCalled()

    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()
    expect(waitForAssets).toHaveBeenCalledTimes(1)
    expect(waitForAssets.mock.calls[0][0].root.dataset.runtimeRoutePath).toBe('/a')
    expect(waitForAssets.mock.calls[0][0].includeAnimations).toBe(false)
    expect(host.snapshot.value?.state).toBe('playing')

    await vi.advanceTimersByTimeAsync(1000)
    await flushAsync()
    expect(router.currentRoute.value.path).toBe('/b')
    expect(host.snapshot.value).toMatchObject({ state: 'preparing', path: '/b' })

    session.transitionSettled.value = { path: '/b', generation: 2 }
    await flushAsync()
    expect(host.snapshot.value?.state).toBe('playing')

    app.unmount()
  })

  it('加载期间不计时，延迟就绪后才开始完整停留', async () => {
    preloadPlaybackConfig({ autoStart: true })
    await reloadAllConfigs()
    let resolveAssets: ((value: typeof READY) => void) | undefined
    waitForAssets.mockReturnValue(new Promise(resolve => { resolveAssets = resolve }))
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    const session = getRuntimeSession(router)

    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()
    expect(host.snapshot.value?.state).toBe('preparing')
    await vi.advanceTimersByTimeAsync(10_000)
    expect(router.currentRoute.value.path).toBe('/a')
    expect(host.snapshot.value?.state).toBe('preparing')

    resolveAssets?.(READY)
    await flushAsync()
    expect(host.snapshot.value?.state).toBe('playing')
    await vi.advanceTimersByTimeAsync(999)
    expect(router.currentRoute.value.path).toBe('/a')
    await vi.advanceTimersByTimeAsync(1)
    await flushAsync()
    expect(router.currentRoute.value.path).toBe('/b')
    app.unmount()
  })

  it('忽略旧页面 settled，只接受当前路由的新事件', async () => {
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    const session = getRuntimeSession(router)
    expect(host.start()).toBe(true)
    await flushAsync()

    session.transitionSettled.value = { path: '/b', generation: 1 }
    await flushAsync()
    expect(waitForAssets).not.toHaveBeenCalled()
    expect(host.snapshot.value?.state).toBe('preparing')

    session.transitionSettled.value = { path: '/a', generation: 2 }
    await flushAsync()
    expect(host.snapshot.value?.state).toBe('playing')

    await router.push('/b')
    await flushAsync()
    expect(host.snapshot.value?.state).toBe('preparing')
    session.transitionSettled.value = { path: '/a', generation: 3 }
    await flushAsync()
    expect(waitForAssets).toHaveBeenCalledTimes(1)
    session.transitionSettled.value = { path: '/b', generation: 4 }
    await flushAsync()
    expect(waitForAssets).toHaveBeenCalledTimes(2)
    expect(host.snapshot.value).toMatchObject({ state: 'playing', path: '/b' })
    app.unmount()
  })

  it('资源失败进入可见错误态且不创建推进计时', async () => {
    waitForAssets.mockResolvedValue({
      ...READY,
      ok: false,
      failed: [{ type: 'image', message: '图片资源加载失败：/cover.png' }],
    })
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    const session = getRuntimeSession(router)
    expect(host.start()).toBe(true)
    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()

    expect(host.snapshot.value?.state).toBe('error')
    expect(host.errorMessage.value).toContain('图片资源加载失败')
    await vi.advanceTimersByTimeAsync(10_000)
    expect(router.currentRoute.value.path).toBe('/a')
    app.unmount()
  })

  it('稳定页面节点缺失时进入错误态', async () => {
    document.querySelectorAll('.runtime-page-print-source').forEach(element => element.remove())
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    const session = getRuntimeSession(router)
    expect(host.start()).toBe(true)
    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()

    expect(host.snapshot.value?.state).toBe('error')
    expect(host.errorMessage.value).toContain('页面节点未就绪')
    app.unmount()
  })

  it('导航错误使等待中的放映进入错误态', async () => {
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    const session = getRuntimeSession(router)
    expect(host.start()).toBe(true)
    session.navigationError.value = '页面加载失败，请重试或选择其他页面。'
    await flushAsync()
    expect(host.snapshot.value?.state).toBe('error')
    expect(host.errorMessage.value).toContain('页面加载失败')
    app.unmount()
  })

  it('同一 Router 会话重新挂载不会再次自动开始', async () => {
    preloadPlaybackConfig({ autoStart: true })
    await reloadAllConfigs()
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const first = mountPlaybackHost(router)
    await flushAsync()
    first.app.unmount()

    const second = mountPlaybackHost(router)
    await flushAsync()
    expect(second.host.snapshot.value?.state).toBe('stopped')
    expect(waitForAssets).not.toHaveBeenCalled()
    second.app.unmount()
  })
})

describe('usePlaybackHost 禁用上下文', () => {
  it('捕获上下文不创建控制器、计时或资源探测', async () => {
    initializeRuntimeExecution('?runtimeCapture=1')
    preloadPlaybackConfig({ autoStart: true })
    await reloadAllConfigs()
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    await flushAsync()
    await vi.advanceTimersByTimeAsync(60_000)

    expect(host.snapshot.value).toBeNull()
    expect(host.errorMessage.value).toBe('')
    expect(waitForAssets).not.toHaveBeenCalled()
    expect(router.currentRoute.value.path).toBe('/a')
    app.unmount()
  })
})
