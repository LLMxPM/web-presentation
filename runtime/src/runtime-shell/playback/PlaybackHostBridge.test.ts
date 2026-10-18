// @vitest-environment jsdom
/** 文件功能：验证全屏放映控制条的翻页、自动/手动切换、状态提示、演讲与退出入口。 */
import { createApp, nextTick } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { reloadAllConfigs } from '@/core/utils/config'
import { setRuntimePreloadedConfig } from '@/core/utils/path'
import { getRuntimeSession } from '@/core/router/runtime-session'
import { resetRuntimeExecutionForTests } from '@/core/execution/execution-scope'
import PlaybackHostBridge from './PlaybackHostBridge.vue'

const { waitForAssets } = vi.hoisted(() => ({ waitForAssets: vi.fn() }))
vi.mock('@/core/utils/visual-assets', () => ({ waitForEditorVisualAssets: waitForAssets }))

const READY = { ok: true, timedOut: false, total: 0, loaded: 0, failed: [], pending: [], waitedMs: 0 }

function preloadConfig(autoStart = true) {
  setRuntimePreloadedConfig({
    app: {
      app: {
        icon: 'slider',
        title: '控制条测试',
        description: '',
        page: { width: 1920, height: 1080, baseFontSize: '24px', iconDefaultStrokeWidth: 2 },
        features: { showPdfExportButton: false, menuMode: 'text' },
      },
    },
    routes: {
      playback: {
        autoStart,
        loop: false,
        advanceDefaults: { mode: 'manual', delayMs: 5000 },
      },
      transitionDefaults: { effect: 'none', durationMs: 0 },
      routes: [
        { route: 'a', component: '@/views/a.vue', meta: { title: 'A', order: 1, advance: { mode: 'timer', delayMs: 1000 } } },
        { route: 'b', component: '@/views/b.vue', meta: { title: 'B', order: 2, advance: { mode: 'timer', delayMs: 2000 } } },
      ],
    },
    icons: { static_icons: [] },
  } as never)
}

function makeRouter() {
  const component = { render: () => null }
  return createRouter({
    history: createMemoryHistory(),
    routes: ['/a', '/b'].map(path => ({ path, component })),
  })
}

function addPageElement(path: string): void {
  const element = document.createElement('div')
  element.className = 'runtime-page-print-source'
  element.dataset.runtimeRoutePath = path
  document.body.append(element)
}

async function flushAsync(): Promise<void> {
  await vi.advanceTimersByTimeAsync(0)
  for (let index = 0; index < 6; index += 1) {
    await nextTick()
    await Promise.resolve()
  }
}

function mountBridge(
  router: ReturnType<typeof makeRouter>,
  props: { initialAutoAdvance?: boolean; presenterAvailable?: boolean } = {},
) {
  const root = document.createElement('div')
  document.body.append(root)
  const app = createApp(PlaybackHostBridge, props)
  app.use(router)
  app.mount(root)
  return { root, app }
}

function text(root: HTMLElement): string {
  return root.querySelector<HTMLElement>('.runtime-playback-controls')?.textContent ?? ''
}

function buttonByLabel(root: HTMLElement, label: string): HTMLButtonElement {
  return root.querySelector<HTMLButtonElement>(`[aria-label="${label}"]`)!
}

beforeEach(async () => {
  vi.useFakeTimers()
  waitForAssets.mockReset()
  waitForAssets.mockResolvedValue(READY)
  resetRuntimeExecutionForTests()
  preloadConfig()
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

describe('PlaybackHostBridge 控制条', () => {
  it('自动推进、自动切手动后停留，再切回自动并在末页结束', async () => {
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { root, app } = mountBridge(router)
    const session = getRuntimeSession(router)
    await flushAsync()

    expect(text(root)).toContain('准备中')
    expect(text(root)).toContain('1 / 2')
    expect(text(root)).toContain('自动')
    expect(text(root)).toContain('0:01')

    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()
    expect(text(root)).toContain('放映中')
    await vi.advanceTimersByTimeAsync(1_000)
    await flushAsync()
    expect(router.currentRoute.value.path).toBe('/b')

    session.transitionSettled.value = { path: '/b', generation: 2 }
    await flushAsync()
    expect(text(root)).toContain('放映中')
    expect(text(root)).toContain('0:02')

    const toggle = root.querySelector<HTMLButtonElement>('[data-testid="playback-auto-toggle"]')!
    toggle.click()
    await flushAsync()
    expect(text(root)).toContain('手动')
    await vi.advanceTimersByTimeAsync(10_000)
    expect(router.currentRoute.value.path).toBe('/b')

    toggle.click()
    await flushAsync()
    expect(text(root)).toContain('自动')
    await vi.advanceTimersByTimeAsync(2_000)
    await flushAsync()
    expect(text(root)).toContain('已结束')
    expect(text(root)).toContain('重新开始')

    app.unmount()
  })

  it('静音按钮与 M 快捷键切换，不改变放映状态', async () => {
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { root, app } = mountBridge(router)
    const session = getRuntimeSession(router)
    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()
    expect(text(root)).toContain('放映中')

    const mute = root.querySelector<HTMLButtonElement>('[data-testid="playback-mute-toggle"]')!
    expect(mute.getAttribute('aria-pressed')).toBe('false')
    expect(text(root)).toContain('静音')

    mute.click()
    await flushAsync()
    expect(mute.getAttribute('aria-pressed')).toBe('true')
    expect(text(root)).toContain('已静音')
    expect(text(root)).toContain('放映中')

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'm', bubbles: true, cancelable: true }))
    await flushAsync()
    expect(mute.getAttribute('aria-pressed')).toBe('false')
    expect(text(root)).toContain('放映中')
    app.unmount()
  })

  it('控制条随指针进入底部区域显示，移出后隐藏，键盘聚焦时保持可见', async () => {
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { root, app } = mountBridge(router)
    await flushAsync()

    const controls = root.querySelector<HTMLElement>('.runtime-playback-controls')!
    const isHidden = (): boolean => controls.classList.contains('runtime-playback-controls--hidden')
    expect(isHidden()).toBe(false)

    window.dispatchEvent(new MouseEvent('pointermove', { clientY: 40 }))
    await nextTick()
    expect(isHidden()).toBe(true)

    window.dispatchEvent(new MouseEvent('pointermove', { clientY: window.innerHeight - 8 }))
    await nextTick()
    expect(isHidden()).toBe(false)

    window.dispatchEvent(new MouseEvent('pointermove', { clientY: 40 }))
    await nextTick()
    expect(isHidden()).toBe(true)

    const exitButton = buttonByLabel(root, '退出放映')
    exitButton.focus()
    await nextTick()
    expect(isHidden()).toBe(false)

    exitButton.blur()
    await nextTick()
    expect(isHidden()).toBe(true)

    app.unmount()
  })

  it('使用上一页/下一页翻页且边界不绕回', async () => {
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { root, app } = mountBridge(router, { initialAutoAdvance: false })
    const session = getRuntimeSession(router)
    await flushAsync()
    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()

    expect(text(root)).toContain('手动')
    expect(buttonByLabel(root, '上一页').disabled).toBe(true)
    expect(buttonByLabel(root, '下一页').disabled).toBe(false)

    buttonByLabel(root, '下一页').click()
    await flushAsync()
    expect(router.currentRoute.value.path).toBe('/b')
    session.transitionSettled.value = { path: '/b', generation: 2 }
    await flushAsync()
    expect(buttonByLabel(root, '上一页').disabled).toBe(false)
    expect(buttonByLabel(root, '下一页').disabled).toBe(true)

    buttonByLabel(root, '上一页').click()
    await flushAsync()
    expect(router.currentRoute.value.path).toBe('/a')
    app.unmount()
  })

  it('资源失败显示错误与重试，并触发演讲和退出事件', async () => {
    waitForAssets.mockResolvedValue({
      ...READY,
      ok: false,
      failed: [{ type: 'image', message: '图片资源加载失败：/cover.png' }],
    })
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { root, app } = mountBridge(router, { presenterAvailable: true })
    const session = getRuntimeSession(router)
    await flushAsync()
    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()

    expect(root.querySelector('.runtime-playback-error')?.textContent).toContain('图片资源加载失败')
    expect(text(root)).toContain('重试')
    expect(text(root)).toContain('错误')

    const onExit = vi.fn()
    const onPresenter = vi.fn()
    app.unmount()

    const second = createApp(PlaybackHostBridge, {
      initialAutoAdvance: true,
      presenterAvailable: true,
      onExit,
      onPresenter,
    })
    const secondRoot = document.createElement('div')
    document.body.append(secondRoot)
    second.use(router)
    second.mount(secondRoot)
    await flushAsync()
    secondRoot.querySelector<HTMLButtonElement>('[aria-label="进入演讲模式"]')!.click()
    secondRoot.querySelector<HTMLButtonElement>('[aria-label="退出放映"]')!.click()
    expect(onPresenter).toHaveBeenCalledTimes(1)
    expect(onExit).toHaveBeenCalledTimes(1)
    second.unmount()
  })

  it('旧产物没有放映配置时仍提供演讲与退出入口', async () => {
    setRuntimePreloadedConfig({
      app: { app: { icon: 'slider', title: '旧产物', description: '', page: { width: 1920, height: 1080, baseFontSize: '24px', iconDefaultStrokeWidth: 2 }, features: { showPdfExportButton: false, menuMode: 'text' } } },
      routes: { routes: [{ route: 'a', component: '@/views/a.vue', meta: { title: 'A', order: 1 } }] },
      icons: { static_icons: [] },
    } as never)
    await reloadAllConfigs()
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { root, app } = mountBridge(router, { presenterAvailable: true })
    await flushAsync()

    expect(text(root)).toContain('当前项目未启用放映配置')
    expect(root.querySelector('[aria-label="进入演讲模式"]')).not.toBeNull()
    expect(root.querySelector('[aria-label="退出放映"]')).not.toBeNull()
    app.unmount()
  })
})
