// @vitest-environment jsdom

/**
 * 文件用途：验证演讲者控制台的预览遮罩，避免页面内部交互误导演讲同步。
 */

import { createApp, nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import PresenterConsoleView from './PresenterConsoleView.vue'

const presenterFixture = vi.hoisted(() => ({
  viewMode: 'focus' as 'focus' | 'grid',
  navigateTo: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({
    query: {
      channel: 'channel-console',
      route: '/intro',
    },
  }),
  useRouter: () => ({
    push: vi.fn(),
  }),
}))

vi.mock('@/runtime-shell/presenter/presenter-window', () => ({
  openPresenterDisplayWindow: vi.fn(),
}))

vi.mock('@/runtime-shell/presenter/usePresenterController', async () => {
  const { computed, ref } = await import('vue')
  const pages = [
    {
      path: '/intro',
      title: '第一页',
      pageNumber: 1,
      componentPath: '@/views/intro.vue',
      speakerNotes: '第一页备注',
    },
    {
      path: '/summary',
      title: '第二页',
      pageNumber: 2,
      componentPath: '@/views/summary.vue',
      speakerNotes: '',
    },
  ]

  return {
    usePresenterController: () => ({
      pages: ref(pages),
      currentPath: ref('/intro'),
      currentPage: computed(() => pages[0]),
      nextPage: computed(() => pages[1]),
      canGoPrevious: ref(false),
      canGoNext: ref(true),
      displayStatus: ref({
        state: 'connected',
        isFullscreen: false,
        updatedAt: 1,
      }),
      viewMode: ref(presenterFixture.viewMode),
      tileSize: ref(300),
      channelSupported: ref(true),
      navigateTo: presenterFixture.navigateTo,
      goPrevious: vi.fn(),
      goNext: vi.fn(),
      setTileSize: vi.fn(),
      postClose: vi.fn(),
      postState: vi.fn(),
    }),
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
        return () => h('button', {
          'data-file-path': props.filePath,
          'data-testid': 'view-preview-inner-button',
          type: 'button',
        }, 'inner')
      },
    }),
  }
})

beforeEach(() => {
  presenterFixture.viewMode = 'focus'
  presenterFixture.navigateTo.mockReset()
})

afterEach(() => {
  document.body.innerHTML = ''
})

describe('PresenterConsoleView', () => {
  it('单页模式应为当前页和下一页预览添加不可交互遮罩', async () => {
    const { app, host } = mountPresenterConsoleView()
    await nextTick()

    expect(host.querySelector('[data-testid="presenter-timer-panel"]')).not.toBeNull()
    expect(host.querySelectorAll('.presenter-console__preview-shield')).toHaveLength(2)
    expect(host.querySelectorAll('.presenter-console__preview-content[inert][aria-hidden="true"]')).toHaveLength(2)
    expect(host.querySelectorAll('[data-testid="view-preview-inner-button"]')).toHaveLength(2)

    app.unmount()
  })

  it('平铺模式应为每个页卡预览添加不可交互遮罩', async () => {
    presenterFixture.viewMode = 'grid'

    const { app, host } = mountPresenterConsoleView()
    await nextTick()

    expect(host.querySelector<HTMLElement>('.presenter-console__grid')?.style.gridTemplateColumns)
      .toBe('repeat(auto-fill, minmax(300px, 1fr))')
    expect(host.querySelectorAll('.presenter-console__preview-shield')).toHaveLength(2)
    expect(host.querySelectorAll('.presenter-console__preview-content[inert][aria-hidden="true"]')).toHaveLength(2)

    app.unmount()
  })
})

/**
 * 挂载演讲者控制台组件。
 * @returns Vue 应用和宿主节点
 */
function mountPresenterConsoleView() {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const app = createApp(PresenterConsoleView)
  app.config.errorHandler = (error) => {
    throw error
  }
  app.mount(host)
  return { app, host }
}
