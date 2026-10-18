// @vitest-environment jsdom

/**
 * 文件用途：验证演讲模式观众窗口内的屏幕授权、屏幕选择与全屏调用。
 */

import { createApp, nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import PresenterDisplayView from './PresenterDisplayView.vue'

const presenterFixture = vi.hoisted(() => ({
  commandHandler: null as null | ((action: string, autoAdvance?: boolean) => void),
  postPlaybackState: vi.fn(),
  updatePlayback: vi.fn(),
}))

const playbackFixture = vi.hoisted(() => ({
  options: null as null | { autoStart?: boolean; initialAutoAdvance?: boolean },
  start: vi.fn(),
  pause: vi.fn(),
  resume: vi.fn(),
  stop: vi.fn(),
  retry: vi.fn(),
  next: vi.fn(),
  setAutoAdvance: vi.fn(),
}))

const routeFixture = vi.hoisted(() => ({
  query: { channel: 'channel-display', route: '/intro' } as Record<string, unknown>,
}))

vi.mock('./PresenterPageStage.vue', () => ({ default: { template: '<div />' } }))

vi.mock('vue-router', () => ({
  useRoute: () => ({
    query: routeFixture.query,
  }),
}))

vi.mock('@/runtime-shell/presenter/usePresenterController', () => ({
  usePresenterController: (options: { onPlaybackCommand?: (action: string, autoAdvance?: boolean) => void }) => {
    presenterFixture.commandHandler = options.onPlaybackCommand ?? null
    return {
      currentPage: {
        path: '/intro',
        title: '第一页',
        pageNumber: 1,
        componentPath: '@/views/intro.vue',
        speakerNotes: '',
      },
      postDisplayStatus: vi.fn(),
      postPlaybackState: presenterFixture.postPlaybackState,
      updatePlayback: presenterFixture.updatePlayback,
    }
  },
}))

vi.mock('@/runtime-shell/playback/usePlaybackHost', async () => {
  const { ref } = await import('vue')
  return {
    usePlaybackHost: (options: { autoStart?: boolean; initialAutoAdvance?: boolean }) => {
      playbackFixture.options = options
      return {
        snapshot: ref(null),
        errorMessage: ref(''),
        start: playbackFixture.start,
        pause: playbackFixture.pause,
        resume: playbackFixture.resume,
        stop: playbackFixture.stop,
        retry: playbackFixture.retry,
        next: playbackFixture.next,
        setAutoAdvance: playbackFixture.setAutoAdvance,
        refresh: vi.fn(),
      }
    },
  }
})

vi.mock('@/runtime-shell/preview/ViewPreview.vue', async () => {
  const { defineComponent, h } = await import('vue')

  return {
    default: defineComponent({
      name: 'ViewPreviewStub',
      props: {
        filePath: {
          type: String,
          required: true,
        },
      },
      setup(props) {
        return () => h('div', {
          'data-file-path': props.filePath,
          'data-testid': 'view-preview-stub',
        })
      },
    }),
  }
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.clearAllMocks()
  presenterFixture.commandHandler = null
  routeFixture.query = { channel: 'channel-display', route: '/intro' }
  Reflect.deleteProperty(window, 'getScreenDetails')
  Reflect.deleteProperty(document.documentElement, 'requestFullscreen')
  Object.defineProperty(document, 'fullscreenElement', {
    configurable: true,
    value: null,
  })
  document.body.innerHTML = ''
})

describe('PresenterDisplayView', () => {
  it('应在观众窗口内授权检测屏幕后按用户选择的屏幕全屏', async () => {
    const currentScreen = buildScreen({
      availLeft: 0,
      availTop: 0,
      availWidth: 1920,
      availHeight: 1040,
      isPrimary: true,
      label: '内置屏幕',
    })
    const projectorScreen = buildScreen({
      availLeft: 1920,
      availTop: 0,
      availWidth: 1600,
      availHeight: 900,
      label: '投影屏幕',
    })
    const getScreenDetails = vi.fn().mockResolvedValue({
      currentScreen,
      screens: [currentScreen, projectorScreen],
    })
    const requestFullscreen = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(window, 'getScreenDetails', {
      configurable: true,
      value: getScreenDetails,
    })
    Object.defineProperty(document.documentElement, 'requestFullscreen', {
      configurable: true,
      value: requestFullscreen,
    })

    const { app, host } = mountPresenterDisplayView()

    const detectButton = host.querySelector<HTMLButtonElement>('[data-testid="presenter-display-detect-screens"]')
    expect(detectButton).not.toBeNull()
    detectButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flushVueUpdates()

    expect(getScreenDetails).toHaveBeenCalledTimes(1)
    expect(host.textContent).toContain('内置屏幕')
    expect(host.textContent).toContain('投影屏幕')

    const fallbackButton = host.querySelector<HTMLButtonElement>('.presenter-display-screen__fallback-action')
    expect(fallbackButton).not.toBeNull()
    fallbackButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flushVueUpdates()
    expect(requestFullscreen).toHaveBeenCalledWith()

    const projectorButton = host.querySelector<HTMLButtonElement>('button[data-screen-index="1"]')
    expect(projectorButton).not.toBeNull()
    projectorButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flushVueUpdates()

    expect(requestFullscreen).toHaveBeenCalledWith({ screen: projectorScreen })

    app.unmount()
  })

  it('屏幕检测未授权时提供当前窗口全屏回退', async () => {
    const getScreenDetails = vi.fn().mockRejectedValue(new Error('denied'))
    const requestFullscreen = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(window, 'getScreenDetails', {
      configurable: true,
      value: getScreenDetails,
    })
    Object.defineProperty(document.documentElement, 'requestFullscreen', {
      configurable: true,
      value: requestFullscreen,
    })

    const { app, host } = mountPresenterDisplayView()
    host.querySelector<HTMLButtonElement>('[data-testid="presenter-display-detect-screens"]')
      ?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flushVueUpdates()

    expect(host.textContent).toContain('未获得屏幕检测授权')
    const fallbackButton = host.querySelector<HTMLButtonElement>('.presenter-display-screen__fallback-action')
    expect(fallbackButton).not.toBeNull()
    fallbackButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flushVueUpdates()
    expect(requestFullscreen).toHaveBeenCalledWith()

    app.unmount()
  })

  it('继承进入演讲时 URL 携带的自动/手动模式', async () => {
    routeFixture.query = { channel: 'channel-display', route: '/intro', auto: '1' }
    const { app } = mountPresenterDisplayView()
    await flushVueUpdates()

    expect(playbackFixture.options).toMatchObject({ autoStart: false, initialAutoAdvance: true })
    app.unmount()
  })

  it('观众窗口应由控制台命令驱动播放宿主，并在全屏后才开始放映', async () => {
    const { app, host } = mountPresenterDisplayView()
    await flushVueUpdates()

    expect(playbackFixture.options).toMatchObject({ autoStart: false, initialAutoAdvance: false })
    expect(presenterFixture.postPlaybackState).toHaveBeenCalled()
    expect(presenterFixture.updatePlayback).toHaveBeenCalledWith(expect.objectContaining({ state: 'stopped' }))

    presenterFixture.commandHandler?.('start')
    await flushVueUpdates()
    expect(playbackFixture.start).not.toHaveBeenCalled()
    expect(host.textContent).toContain('请先在观众窗口进入全屏')

    Object.defineProperty(document, 'fullscreenElement', {
      configurable: true,
      value: document.documentElement,
    })
    document.dispatchEvent(new Event('fullscreenchange'))
    await flushVueUpdates()
    expect(playbackFixture.start).toHaveBeenCalledTimes(1)

    presenterFixture.commandHandler?.('pause')
    presenterFixture.commandHandler?.('resume')
    presenterFixture.commandHandler?.('next')
    presenterFixture.commandHandler?.('stop')
    presenterFixture.commandHandler?.('set-auto-advance', false)

    expect(playbackFixture.pause).toHaveBeenCalledTimes(1)
    expect(playbackFixture.resume).toHaveBeenCalledTimes(1)
    expect(playbackFixture.next).toHaveBeenCalledTimes(1)
    expect(playbackFixture.stop).toHaveBeenCalledTimes(1)
    expect(playbackFixture.setAutoAdvance).toHaveBeenCalledWith(false)

    app.unmount()
  })
})

interface ScreenFixture {
  availLeft: number
  availTop: number
  availWidth: number
  availHeight: number
  isPrimary?: boolean
  label?: string
}

/**
 * 挂载观众窗口组件。
 * @returns Vue 应用和宿主节点
 */
function mountPresenterDisplayView() {
  Object.defineProperty(document, 'fullscreenElement', {
    configurable: true,
    value: null,
  })
  const host = document.createElement('div')
  document.body.appendChild(host)
  const app = createApp(PresenterDisplayView)
  app.config.errorHandler = (error) => {
    throw error
  }
  app.mount(host)
  return { app, host }
}

/**
 * 构造屏幕详情测试数据。
 * @param fixture 屏幕参数
 * @returns 屏幕详情
 */
function buildScreen(fixture: ScreenFixture) {
  return fixture
}

/**
 * 等待异步回调和 Vue DOM 更新完成。
 */
async function flushVueUpdates(): Promise<void> {
  await Promise.resolve()
  await Promise.resolve()
  await nextTick()
}
