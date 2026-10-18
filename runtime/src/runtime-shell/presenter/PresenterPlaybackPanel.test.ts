/* eslint-disable vue/one-component-per-file */
// @vitest-environment jsdom
/** 文件功能：验证控制台放映面板的状态回显、倒计时与命令按钮。 */

import { createApp, defineComponent, h, nextTick, ref } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import PresenterPlaybackPanel from './PresenterPlaybackPanel.vue'
import type {
  PresenterSyncPlaybackCommandAction,
  PresenterSyncPlaybackSnapshot,
  ReceivedPresenterSync,
} from './presenter-sync-protocol'

afterEach(() => {
  vi.useRealTimers()
  document.body.innerHTML = ''
})

describe('PresenterPlaybackPanel', () => {
  it('未开始时显示开始按钮并发送 start', async () => {
    const { host, commands } = mountPanel(received('stopped'))
    await nextTick()

    expect(host.querySelector('[data-testid="presenter-playback-state"]')?.textContent?.trim()).toBe('未开始')
    host.querySelector<HTMLButtonElement>('[data-testid="presenter-playback-primary"]')
      ?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await nextTick()

    expect(commands).toEqual(['start'])
  })

  it('播放中显示倒计时、暂停和停止，不提供下一页', async () => {
    const { host } = mountPanel(received('playing', { delayMs: 5000, remainingMs: 5000 }, Date.now() + 5000))
    await nextTick()

    expect(host.querySelector('[data-testid="presenter-playback-state"]')?.textContent?.trim()).toBe('放映中')
    expect(host.querySelector('[data-testid="presenter-playback-remaining"]')?.textContent?.trim()).toMatch(/^0:0[45]$/)
    expect(host.querySelector('[data-testid="presenter-playback-primary"]')?.textContent?.trim()).toBe('暂停')
    expect(host.querySelector('[data-testid="presenter-playback-stop"]')).not.toBeNull()
    expect(host.querySelector('[data-testid="presenter-playback-next"]')).toBeNull()
  })

  it('受阻时提供重试和下一页，观众未连接时保持暂停且不提供命令', async () => {
    const { host } = mountPanel(received('blocked', { index: 1, total: 3 }))
    await nextTick()

    expect(host.querySelector('[data-testid="presenter-playback-state"]')?.textContent?.trim()).toBe('受阻')
    expect(host.querySelector('[data-testid="presenter-playback-primary"]')?.textContent?.trim()).toBe('重试')
    expect(host.querySelector('[data-testid="presenter-playback-next"]')).not.toBeNull()

    document.body.innerHTML = ''
    const offline = mountPanel(received('playing'), false)
    await nextTick()

    expect(offline.host.querySelector('[data-testid="presenter-playback-state"]')?.textContent?.trim())
      .toBe('已暂停（观众窗口未连接）')
    expect(offline.host.querySelector('[data-testid="presenter-playback-primary"]')).toBeNull()
    expect(offline.host.querySelector('[data-testid="presenter-playback-stop"]')).toBeNull()
  })
  it('从暂停继续时按当前时刻重建倒计时，不累计暂停时长', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-18T00:00:00Z'))
    const playback = ref(received('paused', { remainingMs: 2500, delayMs: 4000 }))
    const host = document.createElement('div')
    document.body.appendChild(host)
    const app = createApp(defineComponent({
      setup: () => () => h(PresenterPlaybackPanel, { playback: playback.value, displayAvailable: true }),
    }))
    app.mount(host)
    await nextTick()
    expect(host.querySelector('[data-testid="presenter-playback-remaining"]')?.textContent?.trim()).toBe('0:03')

    vi.setSystemTime(Date.now() + 5000)
    playback.value = received('playing', { remainingMs: 2500, delayMs: 4000 }, Date.now() + 2500)
    await nextTick()
    expect(host.querySelector('[data-testid="presenter-playback-state"]')?.textContent?.trim()).toBe('放映中')
    expect(host.querySelector('[data-testid="presenter-playback-remaining"]')?.textContent?.trim()).toBe('0:03')

    app.unmount()
  })
})
function received(
  state: PresenterSyncPlaybackSnapshot['state'],
  overrides: Partial<PresenterSyncPlaybackSnapshot> = {},
  deadline: number | null = null,
): ReceivedPresenterSync {
  return {
    receivedAt: 1000,
    deadline,
    message: {
      type: 'playback-state',
      playback: {
        state,
        currentPath: '/a',
        remainingMs: 0,
        delayMs: null,
        waitingForMedia: false,
        index: 0,
        total: 2,
        ...overrides,
      },
    },
  } as ReceivedPresenterSync
}

/** 挂载放映面板并收集命令。 */
function mountPanel(playback: ReceivedPresenterSync, displayAvailable = true) {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const commands: PresenterSyncPlaybackCommandAction[] = []
  const app = createApp(PresenterPlaybackPanel, {
    playback,
    displayAvailable,
    onCommand: (action: PresenterSyncPlaybackCommandAction) => commands.push(action),
  })
  app.mount(host)
  return { app, host, commands }
}
