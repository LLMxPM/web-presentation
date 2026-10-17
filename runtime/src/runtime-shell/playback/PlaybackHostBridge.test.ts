// @vitest-environment jsdom
/** 文件功能：验证放映控制条的开始/暂停/继续/停止、页码与剩余时间展示。 */
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

function preloadConfig() {
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
        autoStart: false,
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
  for (let index = 0; index < 6; index += 1) {
    await nextTick()
    await Promise.resolve()
  }
}

function mountBridge(router: ReturnType<typeof makeRouter>) {
  const root = document.createElement('div')
  document.body.append(root)
  const app = createApp(PlaybackHostBridge)
  app.use(router)
  app.mount(root)
  return { root, app }
}

function button(root: HTMLElement): HTMLButtonElement {
  return root.querySelector<HTMLButtonElement>('.runtime-playback-controls__button--primary')!
}

function text(root: HTMLElement): string {
  return root.querySelector<HTMLElement>('.runtime-playback-controls')?.textContent ?? ''
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
  it('展示页码与状态，完成开始、暂停、继续、停止和自动翻页', async () => {
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { root, app } = mountBridge(router)
    const session = getRuntimeSession(router)
    await flushAsync()

    expect(text(root)).toContain('开始放映')
    expect(text(root)).toContain('已停止')
    expect(text(root)).toContain('1 / 2')
    expect(text(root)).toContain('—')

    button(root).click()
    await flushAsync()
    expect(text(root)).toContain('暂停')
    expect(text(root)).toContain('准备中')
    expect(text(root)).toContain('0:01')

    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()
    expect(text(root)).toContain('放映中')
    expect(text(root)).toContain('0:01')

    await vi.advanceTimersByTimeAsync(1000)
    await flushAsync()
    expect(router.currentRoute.value.path).toBe('/b')
    expect(text(root)).toContain('准备中')

    button(root).click()
    await flushAsync()
    expect(text(root)).toContain('继续')
    expect(text(root)).toContain('已暂停')

    button(root).click()
    await flushAsync()
    expect(text(root)).toContain('暂停')
    expect(text(root)).toContain('准备中')

    session.transitionSettled.value = { path: '/b', generation: 2 }
    await flushAsync()
    expect(text(root)).toContain('放映中')

    const stopButton = root.querySelector<HTMLButtonElement>('[aria-label="停止放映"]')
    stopButton?.click()
    await flushAsync()
    expect(text(root)).toContain('开始放映')
    expect(text(root)).toContain('已停止')
    expect(router.currentRoute.value.path).toBe('/b')

    app.unmount()
  })

  it('资源失败显示错误提示并保持当前页', async () => {
    waitForAssets.mockResolvedValue({
      ...READY,
      ok: false,
      failed: [{ type: 'image', message: '图片资源加载失败：/cover.png' }],
    })
    const router = makeRouter()
    await router.push('/a')
    await router.isReady()
    const { root, app } = mountBridge(router)
    const session = getRuntimeSession(router)
    await flushAsync()
    button(root).click()
    session.transitionSettled.value = { path: '/a', generation: 1 }
    await flushAsync()

    expect(root.querySelector('.runtime-playback-error')?.textContent).toContain('图片资源加载失败')
    expect(text(root)).toContain('重试')
    expect(text(root)).toContain('错误')
    app.unmount()
  })
})
