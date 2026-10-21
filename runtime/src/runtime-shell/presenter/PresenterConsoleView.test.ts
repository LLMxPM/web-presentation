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
  sendPlaybackCommand: vi.fn(),
  displayAvailable: true,
  remotePlayback: null as unknown,
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
      displayAvailable: computed(() => presenterFixture.displayAvailable),
      viewMode: ref(presenterFixture.viewMode),
      tileSize: ref(300),
      channelSupported: ref(true),
      remotePlayback: computed(() => presenterFixture.remotePlayback),
      navigateTo: presenterFixture.navigateTo,
      goPrevious: vi.fn(),
      goNext: vi.fn(),
      setTileSize: vi.fn(),
      postClose: vi.fn(),
      postState: vi.fn(),
      sendPlaybackCommand: presenterFixture.sendPlaybackCommand,
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
  presenterFixture.sendPlaybackCommand.mockReset()
  presenterFixture.displayAvailable = true
  presenterFixture.remotePlayback = null
})

afterEach(() => {
  document.body.innerHTML = ''
})

describe('PresenterConsoleView', () => {
  it('控制台根节点应声明 thumbnail 执行作用域并阻断媒体播放', async () => {
    const { app, host } = mountPresenterConsoleView()
    await nextTick()

    const root = host.querySelector<HTMLElement>('.presenter-console')
    expect(root?.dataset.runtimeExecution).toBe('thumbnail')
    expect(root?.dataset.runtimeMedia).toBe('block')

    app.unmount()
  })

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

  it('应从观众快照显示放映状态并发送控制台命令', async () => {
    presenterFixture.remotePlayback = {
      receivedAt: 1000,
      deadline: 6000,
      message: {
        type: 'playback-state',
        playback: {
          state: 'stopped',
          currentPath: '/intro',
          remainingMs: 0,
          delayMs: null,
          waitingForMedia: false,
          waitingForTimeline: false,
          autoAdvanceEnabled: true,
          timelineId: null,
          planDigest: null,
          positionMs: 0,
          timelineIntent: 'stopped',
          timelinePhase: 'idle',
          index: 0,
          total: 2,
        },
      },
    }

    const { app, host } = mountPresenterConsoleView()
    await nextTick()

    expect(host.querySelector('[data-testid="presenter-playback-state"]')?.textContent?.trim()).toBe('未开始')
    const primary = host.querySelector<HTMLButtonElement>('[data-testid="presenter-playback-primary"]')
    expect(primary?.textContent?.trim()).toBe('开始放映')
    primary?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await nextTick()

    expect(presenterFixture.sendPlaybackCommand).toHaveBeenCalledWith('start')

    app.unmount()
  })

  it('观众窗口关闭时应显示暂停且不提供开始按钮', async () => {
    presenterFixture.displayAvailable = false

    const { app, host } = mountPresenterConsoleView()
    await nextTick()

    expect(host.querySelector('[data-testid="presenter-playback-state"]')?.textContent?.trim())
      .toBe('等待观众窗口全屏')
    expect(host.querySelector('[data-testid="presenter-playback-primary"]')).toBeNull()

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
