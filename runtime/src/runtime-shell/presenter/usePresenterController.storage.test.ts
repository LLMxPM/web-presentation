// @vitest-environment jsdom
/** 文件功能：验证无 BroadcastChannel 时演讲双窗口的首次握手、放映命令和状态回传。 */

import { createApp, defineComponent, nextTick, type App } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { reloadAllConfigs } from '@/core/utils/config'
import { setRuntimePreloadedConfig } from '@/core/utils/path'
import {
  buildPresenterStorageKey,
  parseStoredSyncMessage,
  usePresenterController,
} from './usePresenterController'
import type { PresenterSyncPlaybackCommandAction, PresenterSyncRole } from './presenter-sync-protocol'

const apps: App[] = []
const pendingStorageEvents: StorageEvent[] = []

beforeEach(async () => {
  vi.stubGlobal('BroadcastChannel', undefined)
  vi.spyOn(window, 'close').mockImplementation(() => {})
  const setItem = Storage.prototype.setItem
  // 同一 jsdom Window 承载两个控制器，手动投递跨窗口 storage 事件并保留异步顺序。
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(function (this: Storage, key, value) {
    const oldValue = this.getItem(key)
    setItem.call(this, key, value)
    if (oldValue !== value) {
      pendingStorageEvents.push(new StorageEvent('storage', { key, oldValue, newValue: value }))
    }
  })
  setRuntimePreloadedConfig({
    app: {},
    routes: {
      routes: [
        { route: 'first', component: '@/views/first.vue', meta: { title: '第一页', order: 0 } },
        { route: 'second', component: '@/views/second.vue', meta: { title: '第二页', order: 1 } },
      ],
    },
    icons: { static_icons: [] },
  } as never)
  await reloadAllConfigs()
})

afterEach(() => {
  for (const app of apps.splice(0).reverse()) app.unmount()
  pendingStorageEvents.length = 0
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  localStorage.clear()
  setRuntimePreloadedConfig(undefined)
  document.body.innerHTML = ''
})

describe('presenter localStorage fallback', () => {
  it.each<PresenterSyncRole>(['console', 'display'])('%s 先加载时无需操作即可握手并完成放映控制', async (firstRole) => {
    const actions: PresenterSyncPlaybackCommandAction[] = []
    const first = mountController(firstRole, actions)
    await flushStorageMessages()
    const secondRole = firstRole === 'console' ? 'display' : 'console'
    const second = mountController(secondRole, actions)
    await flushStorageMessages()
    const consoleController = firstRole === 'console' ? first : second
    const displayController = firstRole === 'display' ? first : second

    expect(consoleController.channelSupported.value).toBe(true)
    expect(consoleController.displayAvailable.value).toBe(true)
    for (const action of ['start', 'pause', 'resume', 'stop', 'retry', 'next'] as const) {
      expect(consoleController.sendPlaybackCommand(action)).toBe(true)
      await flushStorageMessages()
    }
    expect(actions).toEqual(['start', 'pause', 'resume', 'stop', 'retry', 'next'])

    consoleController.navigateTo('/second')
    await flushStorageMessages()
    expect(displayController.currentPath.value).toBe('/second')
    displayController.updatePlayback({ state: 'paused', remainingMs: 1200, delayMs: 5000 })
    displayController.postPlaybackState()
    await flushStorageMessages()
    expect(consoleController.remotePlayback.value?.message).toMatchObject({
      type: 'playback-state',
      playback: { state: 'paused', currentPath: '/second', remainingMs: 1200 },
    })
    // 实时命令与回执不能覆盖新窗口用于恢复页面的持久化导航快照。
    expect(parseStoredSyncMessage(localStorage.getItem(buildPresenterStorageKey('storage-test')))?.message)
      .toMatchObject({ type: 'navigate', currentPath: '/second' })

    consoleController.postClose()
    await flushStorageMessages()
    expect(window.close).toHaveBeenCalledOnce()
  })
})

/** 挂载固定频道的角色控制器，使用不同 owner 验证命令确实到达观众窗口。 */
function mountController(role: PresenterSyncRole, actions: PresenterSyncPlaybackCommandAction[]) {
  let controller!: ReturnType<typeof usePresenterController>
  const app = createApp(defineComponent({
    setup() {
      controller = usePresenterController({
        role,
        channelId: 'storage-test',
        artifactIdentity: 'artifact-test',
        initialPath: '/first',
        ownerEpoch: role === 'console' ? 10 : 77,
        onPlaybackCommand: action => actions.push(action),
      })
      return () => null
    },
  }))
  apps.push(app)
  const host = document.createElement('div')
  document.body.appendChild(host)
  app.mount(host)
  return controller
}

/** 清空模拟的跨窗口事件队列，包含处理握手后产生的异步回执。 */
async function flushStorageMessages(): Promise<void> {
  let delivered = 0
  while (pendingStorageEvents.length) {
    if (++delivered > 100) throw new Error('演讲同步出现消息循环')
    window.dispatchEvent(pendingStorageEvents.shift()!)
    await nextTick()
  }
}
