// @vitest-environment jsdom

/**
 * 文件用途：验证演讲模式观众窗口内的屏幕授权、屏幕选择与全屏调用。
 */

import { createApp, nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import PresenterDisplayView from './PresenterDisplayView.vue'

vi.mock('./PresenterPageStage.vue', () => ({ default: { template: '<div />' } }))

vi.mock('vue-router', () => ({
  useRoute: () => ({
    query: {
      channel: 'channel-display',
      route: '/intro',
    },
  }),
}))

vi.mock('@/runtime-shell/presenter/usePresenterController', () => ({
  usePresenterController: () => ({
    currentPage: {
      path: '/intro',
      title: '第一页',
      pageNumber: 1,
      componentPath: '@/views/intro.vue',
      speakerNotes: '',
    },
    goPrevious: vi.fn(),
    goNext: vi.fn(),
    postDisplayStatus: vi.fn(),
  }),
}))

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

    const projectorButton = host.querySelector<HTMLButtonElement>('button[data-screen-index="1"]')
    expect(projectorButton).not.toBeNull()
    projectorButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flushVueUpdates()

    expect(requestFullscreen).toHaveBeenCalledWith({ screen: projectorScreen })

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
