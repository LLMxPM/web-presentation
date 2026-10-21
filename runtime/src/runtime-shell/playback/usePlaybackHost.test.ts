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
import { mediaPlaybackCoordinator } from '@/core/execution/media-playback-guard'
import { compilePageTimeline } from '@/core/motion/compile'
import type { PageMotionHandle } from '@/core/motion/page-motion-contract'
import type { MotionTransportSnapshot } from '@/core/motion/types'
import {
  buildPlaybackPages,
  usePlaybackHost,
  type PlaybackHost,
  type PlaybackHostOptions,
} from './usePlaybackHost'

const { waitForAssets } = vi.hoisted(() => ({ waitForAssets: vi.fn() }))
vi.mock('@/core/utils/visual-assets', () => ({ waitForEditorVisualAssets: waitForAssets }))

const READY = { ok: true, timedOut: false, total: 0, loaded: 0, failed: [], pending: [], waitedMs: 0 }

// 测试宿主默认沿用预载配置的 auto_start；显式传参优先，便于验证手动启动与初始模式。
let configuredAutoStart = false

interface FakeWakeLockSentinel {
  released: boolean
  release: ReturnType<typeof vi.fn>
  addEventListener: ReturnType<typeof vi.fn>
  removeEventListener: ReturnType<typeof vi.fn>
  emitRelease: () => void
}

interface FakeWakeLockApi {
  request: ReturnType<typeof vi.fn>
  sentinel: FakeWakeLockSentinel
}

/** 安装可控 Screen Wake Lock；拒绝时模拟浏览器权限失败。 */
function installWakeLock(options: { reject?: DOMException } = {}): FakeWakeLockApi {
  let releaseListener: (() => void) | null = null
  const sentinel: FakeWakeLockSentinel = {
    released: false,
    release: vi.fn(async () => { sentinel.released = true }),
    addEventListener: vi.fn((type: string, listener: () => void) => {
      if (type === 'release') releaseListener = listener
    }),
    removeEventListener: vi.fn((type: string, listener: () => void) => {
      if (type === 'release' && releaseListener === listener) releaseListener = null
    }),
    emitRelease: () => {
      sentinel.released = true
      releaseListener?.()
    },
  }
  const request = vi.fn(async () => {
    if (options.reject) throw options.reject
    sentinel.released = false
    return sentinel
  })
  Object.defineProperty(navigator, 'wakeLock', { configurable: true, value: { request } })
  return { request, sentinel }
}

function removeWakeLock(): void {
  delete (navigator as Navigator & { wakeLock?: unknown }).wakeLock
}

function preloadPlaybackConfig(options: {
  supported?: boolean
  autoStart?: boolean
  loop?: boolean
  delays?: Record<string, number>
  advances?: Record<string, {
    mode: 'manual' | 'timer' | 'media_end' | 'timeline_end'
    delayMs: number
    mediaTimeoutMs?: number
    timelineTimeoutMs?: number
  }>
} = {}) {
  configuredAutoStart = options.autoStart ?? false
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
      ...(options.supported === false ? {} : {
        playback: {
          autoStart: options.autoStart ?? false,
          loop: options.loop ?? false,
          advanceDefaults: { mode: 'manual', delayMs: 5000 },
        },
      }),
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

/** 在指定放映页内放置可控视频，供 media_end 宿主链路测试。 */
function addTestVideo(path: string, options: { blocked?: boolean; error?: boolean; loop?: boolean } = {}) {
  const element = document.createElement('video')
  let paused = true
  let ended = false
  let blocked = options.blocked ?? false
  Object.defineProperty(element, 'paused', { configurable: true, get: () => paused })
  Object.defineProperty(element, 'ended', { configurable: true, get: () => ended })
  element.loop = options.loop ?? false
  const play = vi.fn(() => {
    if (blocked) return Promise.reject(new DOMException('blocked', 'NotAllowedError'))
    if (options.error) return Promise.reject(new Error('媒体播放失败。'))
    paused = false
    ended = false
    return Promise.resolve()
  })
  const pause = vi.fn(() => { paused = true })
  Object.assign(element, { play, pause })
  const page = document.querySelector(`[data-runtime-route-path="${path}"]`)
  if (!page) throw new Error(`页面 ${path} 不存在`)
  page.append(element)
  return {
    element,
    play,
    pause,
    /** 派发实际元素 ended，模拟播放自然结束。 */
    end: () => {
      ended = true
      paused = true
      element.dispatchEvent(new Event('ended'))
    },
    /** 派发原生 error，模拟浏览器解码或网络失败。 */
    fail: () => {
      paused = true
      element.dispatchEvent(new Event('error'))
    },
    /** 模拟用户手势后浏览器解除自动播放限制。 */
    allowPlayback: () => {
      blocked = false
    },
  }
}

/** 在指定放映页内放置可控音频，供旁白与内容音频测试使用。 */
function addTestAudio(
  path: string,
  options: { purpose?: 'content' | 'narration'; blocked?: boolean; error?: boolean; loop?: boolean } = {},
) {
  const element = document.createElement('audio')
  let paused = true
  let ended = false
  Object.defineProperty(element, 'paused', { configurable: true, get: () => paused })
  Object.defineProperty(element, 'ended', { configurable: true, get: () => ended })
  if (options.purpose) element.dataset.runtimeMediaPurpose = options.purpose
  element.loop = options.loop ?? false
  const play = vi.fn(() => {
    if (options.blocked) return Promise.reject(new DOMException('blocked', 'NotAllowedError'))
    if (options.error) return Promise.reject(new Error('媒体播放失败。'))
    paused = false
    ended = false
    return Promise.resolve()
  })
  const pause = vi.fn(() => { paused = true })
  Object.assign(element, { play, pause })
  const page = document.querySelector(`[data-runtime-route-path="${path}"]`)
  if (!page) throw new Error(`页面 ${path} 不存在`)
  page.append(element)
  return {
    element,
    play,
    pause,
    /** 派发实际元素 ended，模拟旁白自然结束。 */
    end: () => {
      ended = true
      paused = true
      element.dispatchEvent(new Event('ended'))
    },
    /** 派发原生 error，模拟浏览器解码或网络失败。 */
    fail: () => {
      paused = true
      element.dispatchEvent(new Event('error'))
    },
  }
}

/** 挂载放映宿主组合式函数并暴露其接口。 */
function mountPlaybackHost(router: ReturnType<typeof makeRouter>, options?: PlaybackHostOptions) {
  let host: PlaybackHost | undefined
  const Root = defineComponent({
    setup() {
      host = usePlaybackHost(options ?? { autoStart: configuredAutoStart })
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
  mediaPlaybackCoordinator.dispose()
  preloadPlaybackConfig()
  await reloadAllConfigs()
  addPageElement('/a')
  addPageElement('/b')
})

afterEach(() => {
  vi.useRealTimers()
  setRuntimePreloadedConfig(undefined)
  resetRuntimeExecutionForTests()
  Object.defineProperty(document, 'hidden', { configurable: true, get: () => false })
  removeWakeLock()
  document.body.innerHTML = ''
})

describe('buildPlaybackPages', () => {
  it('复用可见叶子目录并携带生效翻页配置', () => {
    const pages = buildPlaybackPages()
    expect(pages.map(page => page.path)).toEqual(['/a', '/b'])
    expect(pages[1].advance).toEqual({ mode: 'timer', delayMs: 2000, mediaTimeoutMs: 300000, timelineTimeoutMs: 300000 })
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

  it('autoStart:false 时不自动放映，只在显式开始后进入准备', async () => {
    preloadPlaybackConfig({ autoStart: true })
    await reloadAllConfigs()
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router, { autoStart: false })
    const session = getRuntimeSession(router)

    await flushAsync()
    expect(host.snapshot.value?.state).toBe('stopped')
    expect(waitForAssets).not.toHaveBeenCalled()

    expect(host.start()).toBe(true)
    await flushAsync()
    expect(host.snapshot.value?.state).toBe('preparing')
    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()
    expect(host.snapshot.value?.state).toBe('playing')
    app.unmount()
  })

  it('手动会话切换自动后按当前页重新计时', async () => {
    preloadPlaybackConfig({ autoStart: true })
    await reloadAllConfigs()
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router, { autoStart: true, initialAutoAdvance: false })
    const session = getRuntimeSession(router)

    await flushAsync()
    expect(host.snapshot.value).toMatchObject({ state: 'preparing', autoAdvanceEnabled: false })
    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()
    expect(host.snapshot.value).toMatchObject({
      state: 'playing',
      autoAdvanceEnabled: false,
      effectiveAdvanceMode: 'manual',
      remainingMs: 0,
    })
    await vi.advanceTimersByTimeAsync(5_000)
    expect(router.currentRoute.value.path).toBe('/a')

    expect(host.setAutoAdvance(true)).toBe(true)
    expect(host.setAutoAdvance(true)).toBe(false)
    await vi.advanceTimersByTimeAsync(999)
    expect(router.currentRoute.value.path).toBe('/a')
    await vi.advanceTimersByTimeAsync(1)
    await flushAsync()
    expect(router.currentRoute.value.path).toBe('/b')
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

  it('同一 Router 会话重新挂载会开始新一轮放映', async () => {
    preloadPlaybackConfig({ autoStart: true })
    await reloadAllConfigs()
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const first = mountPlaybackHost(router)
    await flushAsync()
    expect(first.host.snapshot.value?.state).toBe('preparing')
    first.app.unmount()

    const second = mountPlaybackHost(router)
    await flushAsync()
    expect(second.host.snapshot.value).toMatchObject({ state: 'preparing', path: '/a' })
    second.app.unmount()
  })
})


/** 在放映页注册可控时间轴句柄，模拟页面组件持有的 transport；仅实现宿主实际读取的接口。 */
function attachTestMotion(path: string) {
  const wrapper = document.querySelector(`[data-runtime-route-path="${path}"]`)
  if (!wrapper) throw new Error(`页面 ${path} 不存在`)
  // 与 RuntimePageStage 一致：宿主包装层内才是 SFC 自己的根。
  const page = document.createElement('section')
  wrapper.append(page)
  const plan = compilePageTimeline({
    schemaVersion: 1,
    timelineId: `timeline-${path.slice(1)}`,
    tracks: [
      {
        id: 'fade',
        type: 'dom',
        target: 'h1',
        durationMs: 1000,
        from: { opacity: 0 },
        to: { opacity: 1 },
      },
    ],
  })
  let snapshot: MotionTransportSnapshot = {
    timelineId: plan.timelineId,
    planDigest: plan.planDigest,
    pagePath: path,
    generation: 1,
    intent: 'stopped',
    phase: 'idle',
    positionMs: 0,
    durationMs: plan.durationMs,
    revision: 0,
    completedTrackIds: [],
    errorCode: null,
    errorMessage: '',
  }
  let claimed: Element | null = null
  const listeners = new Set<(value: MotionTransportSnapshot) => void>()
  const emit = () => {
    for (const listener of listeners) listener(snapshot)
  }
  const advanceSnapshot = (patch: Partial<MotionTransportSnapshot>) => {
    snapshot = { ...snapshot, ...patch, revision: snapshot.revision + 1 }
    emit()
  }
  const play = vi.fn(async () => {
    advanceSnapshot({ intent: 'playing', phase: 'ready' })
    return true
  })
  const pause = vi.fn(() => {
    advanceSnapshot({ intent: 'paused' })
    return true
  })
  const seek = vi.fn(async (positionMs: number) => {
    advanceSnapshot({ positionMs: Math.max(0, Math.min(plan.durationMs, positionMs)), phase: 'ready' })
  })
  const handle = {
    plan,
    ownership: { isElementClaimed: (element: Element) => element === claimed },
    isElementClaimed: (element: Element) => element === claimed,
    getSnapshot: () => snapshot,
    prepare: vi.fn(async () => {
      advanceSnapshot({ phase: 'ready' })
    }),
    play,
    pause,
    resume: vi.fn(async () => play()),
    seek,
    restart: vi.fn(async () => play()),
    setMuted: vi.fn(),
    sampleAt: vi.fn(async () => ({ proofs: [], positionMs: snapshot.positionMs })),
    subscribe: (listener: (value: MotionTransportSnapshot) => void) => {
      listeners.add(listener)
      listener(snapshot)
      return () => listeners.delete(listener)
    },
    dispose: vi.fn(),
  } as unknown as PageMotionHandle
  ;(page as unknown as Record<string, unknown>).__runtimePageMotionV1 = handle
  page.setAttribute('data-runtime-page-motion', 'v1')
  return {
    plan,
    play,
    pause,
    seek,
    claim: (element: Element) => { claimed = element },
    buffering: () => advanceSnapshot({ phase: 'buffering' }),
    ready: () => advanceSnapshot({ phase: 'ready' }),
    complete: () => advanceSnapshot({
      intent: 'stopped',
      phase: 'completed',
      positionMs: plan.durationMs,
      completedTrackIds: plan.requiredTrackIds,
    }),
    getSnapshot: () => snapshot,
  }
}

describe('usePlaybackHost media_end 媒体调度', () => {
  it('等待实际媒体结束后翻页，超时前不提前推进', async () => {
    preloadPlaybackConfig({ advances: { '/a': { mode: 'media_end', delayMs: 1000, mediaTimeoutMs: 5000 } } })
    await reloadAllConfigs()
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    const session = getRuntimeSession(router)
    const video = addTestVideo('/a')
    expect(host.start()).toBe(true)
    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()

    expect(host.snapshot.value).toMatchObject({ state: 'playing', waitingForMedia: true, advanceMode: 'media_end' })
    expect(video.play).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(4_999)
    expect(router.currentRoute.value.path).toBe('/a')

    video.end()
    await vi.advanceTimersByTimeAsync(0)
    await flushAsync()
    expect(router.currentRoute.value.path).toBe('/b')
    expect(host.snapshot.value).toMatchObject({ state: 'preparing', path: '/b' })
    app.unmount()
  })

  it('页面没有参与媒体时按停留时间翻页', async () => {
    preloadPlaybackConfig({ advances: { '/a': { mode: 'media_end', delayMs: 1000, mediaTimeoutMs: 5000 } } })
    await reloadAllConfigs()
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    const session = getRuntimeSession(router)
    expect(host.start()).toBe(true)
    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()

    expect(host.snapshot.value).toMatchObject({ state: 'playing', waitingForMedia: false, delayMs: 1000 })
    await vi.advanceTimersByTimeAsync(1000)
    await flushAsync()
    expect(router.currentRoute.value.path).toBe('/b')
    app.unmount()
  })

  it('只有循环媒体时不进入媒体等待，按停留时间翻页', async () => {
    preloadPlaybackConfig({ advances: { '/a': { mode: 'media_end', delayMs: 1000, mediaTimeoutMs: 5000 } } })
    await reloadAllConfigs()
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    const session = getRuntimeSession(router)
    const loop = addTestAudio('/a', { purpose: 'content', loop: true })
    expect(host.start()).toBe(true)
    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()

    expect(host.snapshot.value).toMatchObject({ state: 'playing', waitingForMedia: false, delayMs: 1000 })
    expect(loop.play).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1000)
    await flushAsync()
    expect(router.currentRoute.value.path).toBe('/b')
    app.unmount()
  })

  it('媒体播放受阻进入受阻态，下一页可继续放映', async () => {
    preloadPlaybackConfig({ advances: { '/a': { mode: 'media_end', delayMs: 1000, mediaTimeoutMs: 5000 } } })
    await reloadAllConfigs()
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    const session = getRuntimeSession(router)
    addTestVideo('/a', { blocked: true })
    expect(host.start()).toBe(true)
    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()

    expect(host.snapshot.value?.state).toBe('blocked')
    expect(host.errorMessage.value).toContain('阻止')
    expect(host.next()).toBe(true)
    await vi.advanceTimersByTimeAsync(0)
    await flushAsync()
    expect(router.currentRoute.value.path).toBe('/b')
    expect(host.snapshot.value).toMatchObject({ state: 'preparing', path: '/b' })
    app.unmount()
  })

  it('媒体受阻后用户重试恢复播放并最终翻页', async () => {
    preloadPlaybackConfig({ advances: { '/a': { mode: 'media_end', delayMs: 1000, mediaTimeoutMs: 5000 } } })
    await reloadAllConfigs()
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    const session = getRuntimeSession(router)
    const video = addTestVideo('/a', { blocked: true })
    expect(host.start()).toBe(true)
    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()
    expect(host.snapshot.value?.state).toBe('blocked')

    video.allowPlayback()
    expect(host.retry()).toBe(true)
    await flushAsync()
    expect(host.snapshot.value).toMatchObject({ state: 'playing', waitingForMedia: true })
    expect(video.play).toHaveBeenCalledTimes(2)

    video.end()
    await vi.advanceTimersByTimeAsync(0)
    await flushAsync()
    expect(router.currentRoute.value.path).toBe('/b')
    app.unmount()
  })

  it('媒体未结束超时进入错误暂停态', async () => {
    preloadPlaybackConfig({ advances: { '/a': { mode: 'media_end', delayMs: 1000, mediaTimeoutMs: 5000 } } })
    await reloadAllConfigs()
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    const session = getRuntimeSession(router)
    addTestVideo('/a')
    expect(host.start()).toBe(true)
    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()

    await vi.advanceTimersByTimeAsync(5_000)
    await flushAsync()
    expect(host.snapshot.value?.state).toBe('error')
    expect(host.errorMessage.value).toContain('超时')
    expect(router.currentRoute.value.path).toBe('/a')
    app.unmount()
  })

  it('暂停停播并保留媒体时限，恢复后继续播放再按结束翻页', async () => {
    preloadPlaybackConfig({ advances: { '/a': { mode: 'media_end', delayMs: 1000, mediaTimeoutMs: 5000 } } })
    await reloadAllConfigs()
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    const session = getRuntimeSession(router)
    const video = addTestVideo('/a')
    expect(host.start()).toBe(true)
    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()
    await vi.advanceTimersByTimeAsync(1_000)

    expect(host.pause()).toBe(true)
    expect(video.pause).toHaveBeenCalled()
    expect(host.snapshot.value).toMatchObject({ state: 'paused', waitingForMedia: true })
    await vi.advanceTimersByTimeAsync(10_000)
    expect(host.snapshot.value?.state).toBe('paused')

    expect(host.resume()).toBe(true)
    expect(host.snapshot.value).toMatchObject({ state: 'playing', waitingForMedia: true })
    expect(video.play).toHaveBeenCalledTimes(2)
    video.end()
    await vi.advanceTimersByTimeAsync(0)
    await flushAsync()
    expect(router.currentRoute.value.path).toBe('/b')
    app.unmount()
  })
})

describe('usePlaybackHost 页面旁白', () => {
  it('manual 页面自动播放旁白，内容音频保持用户手动播放', async () => {
    preloadPlaybackConfig({ advances: { '/a': { mode: 'manual', delayMs: 1000 } } })
    await reloadAllConfigs()
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    const session = getRuntimeSession(router)
    const narration = addTestAudio('/a', { purpose: 'narration' })
    const content = addTestAudio('/a', { purpose: 'content' })
    expect(host.start()).toBe(true)
    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()

    expect(host.snapshot.value).toMatchObject({ state: 'playing', advanceMode: 'manual' })
    expect(narration.play).toHaveBeenCalledTimes(1)
    expect(content.play).not.toHaveBeenCalled()
    narration.end()
    await flushAsync()
    expect(router.currentRoute.value.path).toBe('/a')
    app.unmount()
  })

  it('旁白与视频共同参与 media_end，全部结束后翻页', async () => {
    preloadPlaybackConfig({ advances: { '/a': { mode: 'media_end', delayMs: 1000, mediaTimeoutMs: 5000 } } })
    await reloadAllConfigs()
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    const session = getRuntimeSession(router)
    const narration = addTestAudio('/a', { purpose: 'narration' })
    const video = addTestVideo('/a')
    expect(host.start()).toBe(true)
    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()

    expect(host.snapshot.value).toMatchObject({ state: 'playing', waitingForMedia: true })
    expect(narration.play).toHaveBeenCalledTimes(1)
    expect(video.play).toHaveBeenCalledTimes(1)

    video.end()
    await flushAsync()
    expect(router.currentRoute.value.path).toBe('/a')

    narration.end()
    await vi.advanceTimersByTimeAsync(0)
    await flushAsync()
    expect(router.currentRoute.value.path).toBe('/b')
    app.unmount()
  })

  it('manual 页内容音频报错不改变放映状态，旁白报错进入错误态', async () => {
    preloadPlaybackConfig({ advances: { '/a': { mode: 'manual', delayMs: 1000 } } })
    await reloadAllConfigs()
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    const session = getRuntimeSession(router)
    const narration = addTestAudio('/a', { purpose: 'narration' })
    const content = addTestAudio('/a', { purpose: 'content' })
    expect(host.start()).toBe(true)
    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()

    content.fail()
    await flushAsync()
    expect(host.snapshot.value?.state).toBe('playing')
    expect(host.errorMessage.value).toBe('')

    narration.fail()
    await flushAsync()
    expect(host.snapshot.value?.state).toBe('error')
    expect(host.errorMessage.value).toContain('媒体播放失败')
    app.unmount()
  })

  it('旁白自动播放被浏览器阻止时进入受阻态', async () => {
    preloadPlaybackConfig({ advances: { '/a': { mode: 'manual', delayMs: 1000 } } })
    await reloadAllConfigs()
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    const session = getRuntimeSession(router)
    addTestAudio('/a', { purpose: 'narration', blocked: true })
    expect(host.start()).toBe(true)
    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()

    expect(host.snapshot.value?.state).toBe('blocked')
    expect(host.errorMessage.value).toContain('阻止')
    app.unmount()
  })

  it('会话静音对当前和后续加入的媒体生效，且不改变暂停状态', async () => {
    preloadPlaybackConfig({ advances: { '/a': { mode: 'manual', delayMs: 1000 } } })
    await reloadAllConfigs()
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    const session = getRuntimeSession(router)
    const narration = addTestAudio('/a', { purpose: 'narration' })
    expect(host.start()).toBe(true)
    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()

    expect(host.muted.value).toBe(false)
    expect(host.toggleMute()).toBe(true)
    expect(host.muted.value).toBe(true)
    expect(narration.element.muted).toBe(true)
    expect(host.snapshot.value?.state).toBe('playing')

    const late = addTestAudio('/a', { purpose: 'content' })
    await flushAsync()
    expect(late.element.muted).toBe(true)
    expect(host.toggleMute()).toBe(true)
    expect(narration.element.muted).toBe(false)
    expect(late.element.muted).toBe(false)
    app.unmount()
  })
})

describe('usePlaybackHost 可见性与快捷键', () => {
  it('窗口隐藏时暂停并保留剩余时间，回前台不自动继续', async () => {
    preloadPlaybackConfig({ autoStart: true })
    await reloadAllConfigs()
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    const session = getRuntimeSession(router)
    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()
    expect(host.snapshot.value?.state).toBe('playing')

    await vi.advanceTimersByTimeAsync(400)
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => true })
    document.dispatchEvent(new Event('visibilitychange'))
    await flushAsync()
    expect(host.snapshot.value?.state).toBe('paused')
    const remaining = host.snapshot.value?.remainingMs ?? 0
    expect(remaining).toBeGreaterThan(0)

    await vi.advanceTimersByTimeAsync(10_000)
    expect(router.currentRoute.value.path).toBe('/a')

    Object.defineProperty(document, 'hidden', { configurable: true, get: () => false })
    document.dispatchEvent(new Event('visibilitychange'))
    await flushAsync()
    expect(host.snapshot.value?.state).toBe('paused')

    expect(host.resume()).toBe(true)
    expect(host.snapshot.value?.state).toBe('playing')
    await vi.advanceTimersByTimeAsync(remaining)
    await flushAsync()
    expect(router.currentRoute.value.path).toBe('/b')
    app.unmount()
  })

  it('页面冻结与 bfcache 恢复时暂停，唤醒后不连跳', async () => {
    preloadPlaybackConfig({ autoStart: true })
    await reloadAllConfigs()
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    const session = getRuntimeSession(router)
    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()
    await vi.advanceTimersByTimeAsync(400)

    document.dispatchEvent(new Event('freeze'))
    await flushAsync()
    expect(host.snapshot.value?.state).toBe('paused')
    const remaining = host.snapshot.value?.remainingMs ?? 0
    expect(remaining).toBeGreaterThan(0)
    await vi.advanceTimersByTimeAsync(10_000)
    expect(router.currentRoute.value.path).toBe('/a')

    const pageShow = new Event('pageshow') as PageTransitionEvent
    Object.defineProperty(pageShow, 'persisted', { value: true })
    window.dispatchEvent(pageShow)
    await flushAsync()
    expect(host.snapshot.value?.state).toBe('paused')

    expect(host.resume()).toBe(true)
    await vi.advanceTimersByTimeAsync(remaining)
    await flushAsync()
    expect(router.currentRoute.value.path).toBe('/b')
    app.unmount()
  })

  it('暂停暂停当前页媒体，继续只恢复此前播放的媒体，停止清理记录', async () => {
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    const session = getRuntimeSession(router)
    expect(host.start()).toBe(true)
    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()
    expect(host.snapshot.value?.state).toBe('playing')

    const page = document.querySelector<HTMLElement>('[data-runtime-route-path="/a"]')
    expect(page).not.toBeNull()
    const playing = document.createElement('video')
    const idle = document.createElement('audio')
    page!.append(playing, idle)
    let playingPaused = false
    const idlePaused = true
    Object.defineProperty(playing, 'paused', { configurable: true, get: () => playingPaused })
    Object.defineProperty(idle, 'paused', { configurable: true, get: () => idlePaused })
    const pauseSpy = vi.fn(() => { playingPaused = true })
    const playSpy = vi.fn(() => {
      playingPaused = false
      return Promise.resolve()
    })
    Object.assign(playing, { pause: pauseSpy, play: playSpy })

    expect(host.pause()).toBe(true)
    expect(pauseSpy).toHaveBeenCalledTimes(1)
    expect(playingPaused).toBe(true)
    expect(idlePaused).toBe(true)

    expect(host.resume()).toBe(true)
    expect(playSpy).toHaveBeenCalledTimes(1)
    expect(playingPaused).toBe(false)

    expect(host.stop()).toBe(true)
    expect(pauseSpy).toHaveBeenCalledTimes(2)
    expect(host.resume()).toBe(false)
    app.unmount()
  })

  it('不再拦截空格：放映态翻页交由布局层统一处理', async () => {
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    const session = getRuntimeSession(router)
    let layoutShortcuts = 0
    const layoutListener = () => { layoutShortcuts += 1 }
    document.addEventListener('keydown', layoutListener)
    const pressSpace = () => {
      const event = new KeyboardEvent('keydown', { key: ' ', bubbles: true, cancelable: true })
      document.dispatchEvent(event)
      return event
    }

    session.transitionSettled.value = { path: '/a', generation: 1 }
    expect(host.start()).toBe(true)
    await flushAsync()
    expect(host.snapshot.value?.state).toBe('playing')

    const event = pressSpace()
    expect(event.defaultPrevented).toBe(false)
    // 播放状态与自动推进模式都不再被键盘改变，空格只作为翻页输入向上冒泡。
    expect(host.snapshot.value).toMatchObject({ state: 'playing', autoAdvanceEnabled: true })
    expect(layoutShortcuts).toBe(1)

    app.unmount()
    document.removeEventListener('keydown', layoutListener)
  })

  it('放映期间持有 Screen Wake Lock，隐藏暂停和卸载时释放', async () => {
    const lock = installWakeLock()
    preloadPlaybackConfig({ autoStart: true })
    await reloadAllConfigs()
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    const session = getRuntimeSession(router)
    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()
    expect(host.snapshot.value?.state).toBe('playing')
    expect(lock.request).toHaveBeenCalledTimes(1)
    expect(host.wakeLockState.value).toBe('active')

    Object.defineProperty(document, 'hidden', { configurable: true, get: () => true })
    document.dispatchEvent(new Event('visibilitychange'))
    await flushAsync()
    expect(host.snapshot.value?.state).toBe('paused')
    expect(lock.sentinel.release).toHaveBeenCalledTimes(1)
    expect(host.wakeLockState.value).toBe('idle')

    Object.defineProperty(document, 'hidden', { configurable: true, get: () => false })
    document.dispatchEvent(new Event('visibilitychange'))
    await flushAsync()
    expect(host.snapshot.value?.state).toBe('paused')
    expect(lock.request).toHaveBeenCalledTimes(1)

    expect(host.resume()).toBe(true)
    await flushAsync()
    expect(lock.request).toHaveBeenCalledTimes(2)
    expect(host.wakeLockState.value).toBe('active')
    app.unmount()
    expect(lock.sentinel.release).toHaveBeenCalledTimes(2)
  })

  it('浏览器回收屏幕锁后在可见的放映中重新申请', async () => {
    const lock = installWakeLock()
    preloadPlaybackConfig({ autoStart: true })
    await reloadAllConfigs()
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    const session = getRuntimeSession(router)
    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()
    expect(host.wakeLockState.value).toBe('active')

    lock.sentinel.emitRelease()
    await flushAsync()
    expect(lock.request).toHaveBeenCalledTimes(2)
    expect(host.wakeLockState.value).toBe('active')
    app.unmount()
  })

  it('防休眠权限拒绝时正常放映，只在显式重新开始时重试', async () => {
    const lock = installWakeLock({ reject: new DOMException('denied', 'NotAllowedError') })
    preloadPlaybackConfig({ autoStart: true })
    await reloadAllConfigs()
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    const session = getRuntimeSession(router)
    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()
    expect(host.snapshot.value?.state).toBe('playing')
    expect(host.wakeLockState.value).toBe('denied')
    expect(lock.request).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(1000)
    await flushAsync()
    expect(router.currentRoute.value.path).toBe('/b')
    session.transitionSettled.value = { path: '/b', generation: 2 }
    await flushAsync()
    expect(host.snapshot.value?.state).toBe('playing')
    expect(lock.request).toHaveBeenCalledTimes(1)

    expect(host.pause()).toBe(true)
    expect(host.resume()).toBe(true)
    await flushAsync()
    expect(lock.request).toHaveBeenCalledTimes(2)
    app.unmount()
  })

  it('旧产物缺少 playback 配置时不创建控制器与入口', async () => {
    preloadPlaybackConfig({ supported: false, autoStart: true })
    await reloadAllConfigs()
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    await flushAsync()

    expect(host.snapshot.value).toBeNull()
    expect(host.start()).toBe(false)
    expect(waitForAssets).not.toHaveBeenCalled()
    app.unmount()
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

describe('usePlaybackHost timeline_end 页内时间轴调度', () => {
  it('等待时间轴完成后翻页，不按停留时间提前推进', async () => {
    preloadPlaybackConfig({
      advances: { '/a': { mode: 'timeline_end', delayMs: 1000, timelineTimeoutMs: 5000 } },
    })
    await reloadAllConfigs()
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    const session = getRuntimeSession(router)
    const motion = attachTestMotion('/a')
    expect(host.start()).toBe(true)
    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()

    expect(host.snapshot.value).toMatchObject({
      state: 'playing',
      waitingForTimeline: true,
      advanceMode: 'timeline_end',
    })
    expect(motion.play).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(4_999)
    expect(router.currentRoute.value.path).toBe('/a')

    motion.complete()
    await vi.advanceTimersByTimeAsync(0)
    await flushAsync()
    expect(router.currentRoute.value.path).toBe('/b')
    app.unmount()
  })

  it('timeline_end 页没有时间轴时进入错误态，不退回停留计时', async () => {
    preloadPlaybackConfig({
      advances: { '/a': { mode: 'timeline_end', delayMs: 1000, timelineTimeoutMs: 5000 } },
    })
    await reloadAllConfigs()
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    const session = getRuntimeSession(router)
    expect(host.start()).toBe(true)
    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()

    expect(host.snapshot.value?.state).toBe('error')
    expect(host.errorMessage.value).toContain('时间轴')
    await vi.advanceTimersByTimeAsync(5_000)
    expect(router.currentRoute.value.path).toBe('/a')
    app.unmount()
  })

  it('暂停时间轴后保留预算，恢复时重新启动同一时间轴', async () => {
    preloadPlaybackConfig({
      advances: { '/a': { mode: 'timeline_end', delayMs: 1000, timelineTimeoutMs: 5000 } },
    })
    await reloadAllConfigs()
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    const session = getRuntimeSession(router)
    const motion = attachTestMotion('/a')
    expect(host.start()).toBe(true)
    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()
    await vi.advanceTimersByTimeAsync(1000)

    expect(host.pause()).toBe(true)
    expect(motion.pause).toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(10000)
    expect(host.snapshot.value?.state).toBe('paused')

    expect(host.resume()).toBe(true)
    expect(motion.play).toHaveBeenCalledTimes(2)
    motion.complete()
    await vi.advanceTimersByTimeAsync(0)
    await flushAsync()
    expect(router.currentRoute.value.path).toBe('/b')
    app.unmount()
  })

  it('时间轴认领的媒体不进入页面媒体自动播放', async () => {
    preloadPlaybackConfig({
      advances: { '/a': { mode: 'timeline_end', delayMs: 1000, timelineTimeoutMs: 5000 } },
    })
    await reloadAllConfigs()
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    const session = getRuntimeSession(router)
    const video = addTestVideo('/a')
    const motion = attachTestMotion('/a')
    motion.claim(video.element)
    expect(host.start()).toBe(true)
    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()

    expect(video.play).not.toHaveBeenCalled()
    expect(host.snapshot.value).toMatchObject({ state: 'playing', waitingForTimeline: true })
    app.unmount()
  })

  it('时间轴缓冲冻结超时预算，恢复后按剩余预算超时', async () => {
    preloadPlaybackConfig({
      advances: { '/a': { mode: 'timeline_end', delayMs: 1000, timelineTimeoutMs: 5000 } },
    })
    await reloadAllConfigs()
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    const session = getRuntimeSession(router)
    const motion = attachTestMotion('/a')
    expect(host.start()).toBe(true)
    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()
    await vi.advanceTimersByTimeAsync(2000)

    motion.buffering()
    await flushAsync()
    await vi.advanceTimersByTimeAsync(10000)
    expect(host.snapshot.value?.state).toBe('playing')

    motion.ready()
    await flushAsync()
    await vi.advanceTimersByTimeAsync(2999)
    expect(host.snapshot.value?.state).toBe('playing')
    await vi.advanceTimersByTimeAsync(1)
    expect(host.snapshot.value).toMatchObject({ state: 'error' })
    expect(host.errorMessage.value).toContain('超时')
    app.unmount()
  })

  it('定位命令转发到当前页时间轴并更新快照', async () => {
    preloadPlaybackConfig({
      advances: { '/a': { mode: 'timeline_end', delayMs: 1000, timelineTimeoutMs: 5000 } },
    })
    await reloadAllConfigs()
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { app, host } = mountPlaybackHost(router)
    const session = getRuntimeSession(router)
    const motion = attachTestMotion('/a')
    expect(host.start()).toBe(true)
    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()

    await expect(host.seekMotion(500)).resolves.toBe(true)
    expect(motion.seek).toHaveBeenCalledWith(500)
    expect(host.motion.value?.positionMs).toBe(500)
    app.unmount()
  })
})
