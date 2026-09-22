// @vitest-environment jsdom
/**
 * 文件用途：验证 Runtime 演讲模式页面列表转换、平铺默认尺寸与本地同步消息。
 */

import { createApp, defineComponent } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'

import type { RouteConfig } from '@/core/types/navigation'
import {
  buildPresenterPages,
  buildPresenterStorageKey,
  parseStoredSyncMessage,
  usePresenterController,
  writePresenterInitialNavigateMessage,
} from '@/runtime-shell/presenter/usePresenterController'

afterEach(() => {
  localStorage.clear()
  document.body.innerHTML = ''
})

describe('buildPresenterPages', () => {
  it('应按页码收集可演讲页面并保留演讲者备注', () => {
    const configs: RouteConfig[] = [
      buildRoute({
        path: 'chapter',
        title: '章节',
        pageNumber: undefined,
        componentPath: '',
        children: [
          buildRoute({
            path: 'second',
            title: '第二页',
            pageNumber: 2,
            componentPath: '@/views/second.vue',
            speakerNotes: '第二页备注',
          }),
          buildRoute({
            path: 'hidden',
            title: '隐藏页',
            pageNumber: 3,
            componentPath: '@/views/hidden.vue',
            hidden: true,
          }),
        ],
      }),
      buildRoute({
        path: 'first',
        title: '第一页',
        pageNumber: 1,
        componentPath: '@/views/first.vue',
        speakerNotes: '第一页备注',
      }),
    ]

    const pages = buildPresenterPages(configs)

    expect(pages).toEqual([
      {
        path: '/first',
        title: '第一页',
        pageNumber: 1,
        componentPath: '@/views/first.vue',
        speakerNotes: '第一页备注',
      },
      {
        path: '/chapter/second',
        title: '第二页',
        pageNumber: 2,
        componentPath: '@/views/second.vue',
        speakerNotes: '第二页备注',
      },
    ])
  })

  it('不应因缺失缩略预览组件路径而丢弃可导航页面', () => {
    const configs: RouteConfig[] = [
      buildRoute({
        path: 'summary',
        title: '总结页',
        pageNumber: 1,
        componentPath: '',
        speakerNotes: '总结页备注',
      }),
    ]

    const pages = buildPresenterPages(configs)

    expect(pages).toEqual([
      {
        path: '/summary',
        title: '总结页',
        pageNumber: 1,
        componentPath: '',
        speakerNotes: '总结页备注',
      },
    ])
  })

  it('应解析 localStorage 兜底同步消息', () => {
    const storageKey = buildPresenterStorageKey('channel-a')
    const parsed = parseStoredSyncMessage(JSON.stringify({
      sourceId: 'console-a',
      sentAt: 1,
      message: {
        type: 'state-sync',
        currentPath: '/second',
        viewMode: 'focus',
        tileSize: 240,
      },
    }))

    expect(storageKey).toBe('web-presentation.presenter.sync.channel-a')
    expect(parsed?.message).toEqual({
      type: 'state-sync',
      currentPath: '/second',
      viewMode: 'focus',
      tileSize: 240,
    })
    expect(parseStoredSyncMessage('not-json')).toBeNull()
    expect(parseStoredSyncMessage(JSON.stringify({ sourceId: 'x', message: { type: 'ready' } }))).toBeNull()
    expect(parseStoredSyncMessage(JSON.stringify({
      sourceId: 'console-a',
      sentAt: 1,
      message: {
        type: 'close',
      },
    }))?.message).toEqual({
      type: 'close',
    })
    expect(parseStoredSyncMessage(JSON.stringify({
      sourceId: 'display-a',
      sentAt: 2,
      message: {
        type: 'display-status',
        status: {
          state: 'fullscreen',
          isFullscreen: true,
          updatedAt: 100,
        },
      },
    }))?.message).toEqual({
      type: 'display-status',
      status: {
        state: 'fullscreen',
        isFullscreen: true,
        updatedAt: 100,
      },
    })
  })

  it('应写入演讲入口初始导航兜底消息', () => {
    writePresenterInitialNavigateMessage('channel-entry', 'intro')

    const parsed = parseStoredSyncMessage(localStorage.getItem(buildPresenterStorageKey('channel-entry')))

    expect(parsed?.sourceId).toBe('presenter-entry')
    expect(parsed?.message).toEqual({
      type: 'navigate',
      currentPath: '/intro',
    })
  })

  it('未持久化时默认平铺尺寸应为 300', () => {
    let tileSize = 0
    const host = document.createElement('div')
    document.body.appendChild(host)
    const app = createApp(defineComponent({
      setup() {
        const controller = usePresenterController({
          role: 'console',
          channelId: '',
        })
        tileSize = controller.tileSize.value
        return () => null
      },
    }))

    app.mount(host)

    expect(tileSize).toBe(300)
    app.unmount()
  })
})

interface RouteFixture {
  path: string
  title: string
  pageNumber?: number
  componentPath: string
  speakerNotes?: string
  hidden?: boolean
  children?: RouteConfig[]
}

/**
 * 构造最小 Runtime 路由配置。
 * @param fixture 路由测试数据
 * @returns 可传入页面列表转换函数的路由配置
 */
function buildRoute(fixture: RouteFixture): RouteConfig {
  return {
    path: fixture.path,
    name: fixture.title,
    title: fixture.title,
    order: fixture.pageNumber ?? 0,
    pageNumber: fixture.pageNumber,
    component: async () => ({}),
    meta: {
      title: fixture.title,
      order: fixture.pageNumber ?? 0,
      hidden: fixture.hidden ?? false,
      componentPath: fixture.componentPath,
      speakerNotes: fixture.speakerNotes,
    },
    children: fixture.children,
  }
}
