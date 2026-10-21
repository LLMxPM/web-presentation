/* eslint-disable vue/one-component-per-file */
// @vitest-environment jsdom
/**
 * 文件用途：验证 Runtime 演讲模式页面列表转换、平铺默认尺寸与本地同步消息。
 */

import { createApp, defineComponent } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { reloadAllConfigs } from '@/core/utils/config'
import { setRuntimePreloadedConfig } from '@/core/utils/path'
import type { RouteConfig } from '@/core/types/navigation'
import {
  buildPresenterPages,
  buildPresenterStorageKey,
  parseStoredSyncMessage,
  usePresenterController,
  writePresenterInitialNavigateMessage,
} from '@/runtime-shell/presenter/usePresenterController'

afterEach(() => {
  setRuntimePreloadedConfig(undefined)
  localStorage.clear()
  document.body.innerHTML = ''
  vi.unstubAllGlobals()
  FakeBroadcastChannel.reset()
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

  it('应解析 schema 4 localStorage 兜底同步消息', () => {
    const storageKey = buildPresenterStorageKey('channel-a')
    const envelope = {
      protocol: 4,
      channelId: 'channel-a',
      artifactIdentity: 'artifact-1',
      sourceId: 'console-a',
      role: 'console',
      ownerEpoch: 5,
      revision: 1,
      eventId: 'console-a:1',
    }
    const parsed = parseStoredSyncMessage(JSON.stringify({
      sourceId: 'console-a',
      sentAt: 1,
      message: {
        ...envelope,
        type: 'state-sync',
        currentPath: '/second',
        viewMode: 'focus',
        tileSize: 240,
        playback: {
          state: 'playing',
          currentPath: '/second',
          remainingMs: 4000,
          delayMs: 5000,
          waitingForMedia: false,
          waitingForTimeline: false,
          autoAdvanceEnabled: true,
          timelineId: null,
          planDigest: null,
          positionMs: 0,
          timelineIntent: 'stopped',
          timelinePhase: 'idle',
          index: 1,
          total: 2,
        },
      },
    }))

    expect(storageKey).toBe('web-presentation.presenter.sync.channel-a')
    expect(parsed?.message).toMatchObject({
      type: 'state-sync',
      currentPath: '/second',
      viewMode: 'focus',
      tileSize: 240,
      playback: { state: 'playing', remainingMs: 4000 },
    })
    expect(parseStoredSyncMessage('not-json')).toBeNull()
    expect(parseStoredSyncMessage(JSON.stringify({ sourceId: 'x', message: { type: 'ready' } }))).toBeNull()
    expect(parseStoredSyncMessage(JSON.stringify({
      sourceId: 'console-a',
      sentAt: 1,
      message: { ...envelope, type: 'close' },
    }))?.message.type).toBe('close')
    expect(parseStoredSyncMessage(JSON.stringify({
      sourceId: 'display-a',
      sentAt: 2,
      message: {
        ...envelope,
        sourceId: 'display-a',
        eventId: 'display-a:1',
        type: 'display-status',
        status: { state: 'fullscreen', isFullscreen: true, updatedAt: 100 },
      },
    }))?.message).toMatchObject({
      type: 'display-status',
      status: { state: 'fullscreen', isFullscreen: true, updatedAt: 100 },
    })
    expect(parseStoredSyncMessage(JSON.stringify({
      sourceId: 'console-a',
      sentAt: 1,
      message: {
        type: 'state-sync',
        currentPath: '/legacy',
        viewMode: 'focus',
        tileSize: 240,
      },
    }))).toBeNull()
  })

  it('应写入演讲入口 schema 4 初始导航兜底消息', () => {
    writePresenterInitialNavigateMessage('channel-entry', 'intro', true, 'artifact-1')

    const parsed = parseStoredSyncMessage(localStorage.getItem(buildPresenterStorageKey('channel-entry')))

    expect(parsed?.sourceId).toBe('presenter-entry')
    expect(parsed?.message).toMatchObject({
      protocol: 4,
      channelId: 'channel-entry',
      artifactIdentity: 'artifact-1',
      sourceId: 'presenter-entry',
      role: 'console',
      ownerEpoch: 0,
      revision: 0,
      type: 'navigate',
      currentPath: '/intro',
      playback: { state: 'stopped', currentPath: '/intro', remainingMs: 0 },
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

describe('presenter playback commands', () => {
  it('控制台只向已就绪观众 owner 发送带目标 epoch 的命令', async () => {
    vi.stubGlobal('BroadcastChannel', FakeBroadcastChannel)
    let controller!: ReturnType<typeof usePresenterController>
    const app = createApp(defineComponent({
      setup() {
        controller = usePresenterController({
          role: 'console',
          channelId: 'channel-command',
          initialPath: '/first',
          ownerEpoch: 10,
        })
        return () => null
      },
    }))
    const host = document.createElement('div')
    document.body.appendChild(host)
    app.mount(host)
    const channel = FakeBroadcastChannel.active()

    expect(controller.sendPlaybackCommand('pause')).toBe(false)

    channel.dispatch(displayMessage({
      type: 'ready',
      revision: 1,
      eventId: 'display-1:1',
    }))
    channel.dispatch(displayMessage({
      type: 'display-status',
      revision: 2,
      eventId: 'display-1:2',
      status: { state: 'fullscreen', isFullscreen: true, updatedAt: 1 },
    }))
    expect(controller.displayAvailable.value).toBe(true)

    expect(controller.sendPlaybackCommand('pause')).toBe(true)
    expect(channel.posted.at(-1)).toMatchObject({
      type: 'playback-command',
      action: 'pause',
      targetOwnerEpoch: 77,
    })

    expect(controller.sendPlaybackCommand('set-auto-advance', false)).toBe(true)
    expect(channel.posted.at(-1)).toMatchObject({
      type: 'playback-command',
      action: 'set-auto-advance',
      autoAdvance: false,
      targetOwnerEpoch: 77,
    })

    expect(controller.sendSeek(1200)).toBe(true)
    expect(channel.posted.at(-1)).toMatchObject({
      type: 'playback-command',
      action: 'seek',
      positionMs: 1200,
      seekRevision: 1,
      targetOwnerEpoch: 77,
    })
    expect(controller.sendSeek(2400)).toBe(true)
    expect(channel.posted.at(-1)).toMatchObject({ action: 'seek', positionMs: 2400, seekRevision: 2 })
    expect(controller.sendSeek(-1)).toBe(false)

    app.unmount()
  })

  it('观众窗口忽略目标为其它 owner 的放映命令', async () => {
    vi.stubGlobal('BroadcastChannel', FakeBroadcastChannel)
    const received: string[] = []
    const app = createApp(defineComponent({
      setup() {
        usePresenterController({
          role: 'display',
          channelId: 'channel-command',
          initialPath: '/first',
          ownerEpoch: 77,
          onPlaybackCommand: action => received.push(action),
        })
        return () => null
      },
    }))
    const host = document.createElement('div')
    document.body.appendChild(host)
    app.mount(host)
    const channel = FakeBroadcastChannel.active()

    channel.dispatch(commandMessage('start', 1, 'console-1:1', 76))
    channel.dispatch(commandMessage('start', 2, 'console-1:2', 77))
    await Promise.resolve()

    expect(received).toEqual(['start'])
    app.unmount()
  })
  it('观众窗口先加载时，收到控制台状态后补发身份与播放回执且只补一次', async () => {
    vi.stubGlobal('BroadcastChannel', FakeBroadcastChannel)
    const app = createApp(defineComponent({
      setup() {
        usePresenterController({
          role: 'display',
          channelId: 'channel-command',
          initialPath: '/first',
          ownerEpoch: 77,
        })
        return () => null
      },
    }))
    const host = document.createElement('div')
    document.body.appendChild(host)
    app.mount(host)
    const channel = FakeBroadcastChannel.active()
    const before = channel.posted.length

    channel.dispatch(displayMessage({
      type: 'state-sync',
      sourceId: 'console-late',
      role: 'console',
      ownerEpoch: 10,
      revision: 1,
      eventId: 'console-late:1',
      currentPath: '/first',
      viewMode: 'focus',
      tileSize: 300,
      playback: {
        state: 'stopped',
        currentPath: '/first',
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
    }))
    await Promise.resolve()

    const acknowledgement = channel.posted.slice(before)
    expect(acknowledgement.map(message => (message as { type: string }).type))
      .toEqual(['display-status', 'playback-state'])
    expect(acknowledgement[0]).toMatchObject({ status: { state: 'connected' } })

    const afterFirstAcknowledgement = channel.posted.length
    channel.dispatch(displayMessage({
      type: 'state-sync',
      sourceId: 'console-late',
      role: 'console',
      ownerEpoch: 10,
      revision: 2,
      eventId: 'console-late:2',
      currentPath: '/first',
      viewMode: 'focus',
      tileSize: 300,
      playback: {
        state: 'stopped',
        currentPath: '/first',
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
    }))
    await Promise.resolve()
    expect(channel.posted.length).toBe(afterFirstAcknowledgement)

    app.unmount()
  })

  it('控制台忽略旧观众 owner 的非权威状态', async () => {
    vi.stubGlobal('BroadcastChannel', FakeBroadcastChannel)
    let controller!: ReturnType<typeof usePresenterController>
    const app = createApp(defineComponent({
      setup() {
        controller = usePresenterController({
          role: 'console',
          channelId: 'channel-command',
          initialPath: '/first',
          ownerEpoch: 10,
        })
        return () => null
      },
    }))
    const host = document.createElement('div')
    document.body.appendChild(host)
    app.mount(host)
    const channel = FakeBroadcastChannel.active()

    channel.dispatch(displayMessage({ type: 'ready', revision: 1, eventId: 'display-1:1' }))
    channel.dispatch(displayMessage({
      type: 'display-status',
      revision: 2,
      eventId: 'display-1:2',
      status: { state: 'fullscreen', isFullscreen: true, updatedAt: 1 },
    }))
    expect(controller.displayAvailable.value).toBe(true)

    channel.dispatch(displayMessage({
      type: 'display-status',
      sourceId: 'display-old',
      ownerEpoch: 70,
      revision: 1,
      eventId: 'display-old:1',
      status: { state: 'closed', isFullscreen: false, updatedAt: 2 },
    }))
    expect(controller.displayAvailable.value).toBe(true)
    expect(controller.displayStatus.value.state).toBe('fullscreen')

    app.unmount()
  })

  it('观众窗口忽略其它观众窗口的导航，只接受控制台来源', async () => {
    setRuntimePreloadedConfig({
      routes: {
        playback: { autoStart: false, loop: false, advanceDefaults: { mode: 'manual', delayMs: 0 } },
        transitionDefaults: { effect: 'none', durationMs: 0 },
        routes: [
          { route: 'first', component: '@/views/first.vue', meta: { title: '第一页', order: 0 } },
          { route: 'second', component: '@/views/second.vue', meta: { title: '第二页', order: 1 } },
        ],
      },
      icons: { static_icons: [] },
    } as never)
    await reloadAllConfigs()
    vi.stubGlobal('BroadcastChannel', FakeBroadcastChannel)
    let controller!: ReturnType<typeof usePresenterController>
    const app = createApp(defineComponent({
      setup() {
        controller = usePresenterController({
          role: 'display',
          channelId: 'channel-command',
          initialPath: '/first',
          ownerEpoch: 77,
        })
        return () => null
      },
    }))
    const host = document.createElement('div')
    document.body.appendChild(host)
    app.mount(host)
    const channel = FakeBroadcastChannel.active()
    const playback = {
      state: 'stopped',
      currentPath: '/second',
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
      index: 1,
      total: 2,
    }

    channel.dispatch(displayMessage({
      type: 'navigate',
      sourceId: 'display-old',
      ownerEpoch: 50,
      revision: 1,
      eventId: 'display-old:1',
      currentPath: '/second',
      playback,
    }))
    await Promise.resolve()
    expect(controller.currentPath.value).toBe('/first')

    channel.dispatch(displayMessage({
      type: 'navigate',
      sourceId: 'console-1',
      role: 'console',
      ownerEpoch: 10,
      revision: 1,
      eventId: 'console-1:1',
      currentPath: '/second',
      playback,
    }))
    await Promise.resolve()
    expect(controller.currentPath.value).toBe('/second')

    app.unmount()
  })
})

/** 构造观众窗口来源的协议消息。 */
function displayMessage(overrides: Record<string, unknown>) {
  return {
    protocol: 4,
    channelId: 'channel-command',
    artifactIdentity: '',
    sourceId: 'display-1',
    role: 'display',
    ownerEpoch: 77,
    ...overrides,
  }
}

/** 构造控制台放映命令消息。 */
function commandMessage(action: string, revision: number, eventId: string, targetOwnerEpoch: number) {
  return {
    protocol: 4,
    channelId: 'channel-command',
    artifactIdentity: '',
    sourceId: 'console-1',
    role: 'console',
    ownerEpoch: 10,
    revision,
    eventId,
    type: 'playback-command',
    action,
    targetOwnerEpoch,
  }
}

class FakeBroadcastChannel {
  static instances: FakeBroadcastChannel[] = []
  static posted: unknown[] = []
  readonly listeners = new Set<(event: MessageEvent) => void>()
  readonly name: string
  readonly posted: unknown[] = []

  constructor(name: string) {
    this.name = name
    FakeBroadcastChannel.instances.push(this)
  }

  addEventListener(_type: string, listener: EventListener): void {
    this.listeners.add(listener as (event: MessageEvent) => void)
  }

  removeEventListener(_type: string, listener: EventListener): void {
    this.listeners.delete(listener as (event: MessageEvent) => void)
  }

  postMessage(data: unknown): void {
    this.posted.push(data)
    FakeBroadcastChannel.posted.push(data)
  }

  close(): void {}

  dispatch(data: unknown): void {
    for (const listener of this.listeners) {
      listener({ data } as MessageEvent)
    }
  }

  static active(): FakeBroadcastChannel {
    return FakeBroadcastChannel.instances[0]
  }

  static reset(): void {
    FakeBroadcastChannel.instances = []
    FakeBroadcastChannel.posted = []
  }
}

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
