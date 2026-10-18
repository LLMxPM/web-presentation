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
import {
  buildPlaybackPages,
  usePlaybackHost,
  type PlaybackHost,
  type PlaybackHostOptions,
} from './usePlaybackHost'

const { waitForAssets } = vi.hoisted(() => ({ waitForAssets: vi.fn() }))
vi.mock('@/core/utils/visual-assets', () => ({ waitForEditorVisualAssets: waitForAssets }))

const READY = { ok: true, timedOut: false, total: 0, loaded: 0, failed: [], pending: [], waitedMs: 0 }

function preloadPlaybackConfig(options: {
  supported?: boolean
  autoStart?: boolean
  loop?: boolean
  delays?: Record<string, number>
  advances?: Record<string, { mode: 'manual' | 'timer' | 'media_end'; delayMs: number; mediaTimeoutMs?: number }>
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
function addTestVideo(path: string, options: { blocked?: boolean } = {}) {
  const element = document.createElement('video')
  let paused = true
  let ended = false
  Object.defineProperty(element, 'paused', { configurable: true, get: () => paused })
  Object.defineProperty(element, 'ended', { configurable: true, get: () => ended })
  const play = vi.fn(() => {
    if (options.blocked) return Promise.reject(new DOMException('blocked', 'NotAllowedError'))
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
  }
}

/** 挂载放映宿主组合式函数并暴露其接口。 */
function mountPlaybackHost(router: ReturnType<typeof makeRouter>, options?: PlaybackHostOptions) {
  let host: PlaybackHost | undefined
  const Root = defineComponent({
    setup() {
      host = usePlaybackHost(options)
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
  document.body.innerHTML = ''
})

describe('buildPlaybackPages', () => {
  it('复用可见叶子目录并携带生效翻页配置', () => {
    const pages = buildPlaybackPages()
    expect(pages.map(page => page.path)).toEqual(['/a', '/b'])
    expect(pages[1].advance).toEqual({ mode: 'timer', delayMs: 2000, mediaTimeoutMs: 300000 })
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

  it('空格切换开始/暂停/继续并阻止布局层重复翻页', async () => {
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

    expect(pressSpace().defaultPrevented).toBe(true)
    expect(host.snapshot.value?.state).toBe('preparing')
    expect(layoutShortcuts).toBe(0)

    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()
    expect(host.snapshot.value?.state).toBe('playing')

    expect(pressSpace().defaultPrevented).toBe(true)
    expect(host.snapshot.value?.state).toBe('paused')
    expect(layoutShortcuts).toBe(0)

    expect(pressSpace().defaultPrevented).toBe(true)
    expect(host.snapshot.value?.state).toBe('playing')
    expect(layoutShortcuts).toBe(0)

    app.unmount()
    pressSpace()
    expect(layoutShortcuts).toBe(1)
    document.removeEventListener('keydown', layoutListener)
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
    expect(getRuntimeSession(router).autoStartAttempted.value).toBe(true)
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
