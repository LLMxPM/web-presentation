/* eslint-disable vue/one-component-per-file */
// @vitest-environment jsdom
/** 文件功能：验证控制台传输栏的状态回显、倒计时、自动/手动切换与翻页命令。 */

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

  it('播放中显示倒计时、页码、暂停和停止，并允许传输栏翻页', async () => {
    const { host } = mountPanel(received('playing', { delayMs: 5000, remainingMs: 5000 }, Date.now() + 5000))
    await nextTick()

    expect(host.querySelector('[data-testid="presenter-playback-state"]')?.textContent?.trim()).toBe('放映中')
    expect(host.querySelector('[data-testid="presenter-playback-page"]')?.textContent?.trim()).toBe('2 / 3')
    expect(host.querySelector('[data-testid="presenter-playback-remaining"]')?.textContent?.trim()).toMatch(/^0:0[45]$/)
    expect(host.querySelector('[data-testid="presenter-playback-primary"]')?.textContent?.trim()).toBe('暂停')
    expect(host.querySelector('[data-testid="presenter-playback-stop"]')).not.toBeNull()
    expect(host.querySelector('[aria-label="下一页"]')).not.toBeNull()
  })

  it('受阻时提供重试和下一页并发送 next 命令', async () => {
    const { host, commands } = mountPanel(received('blocked', { index: 1, total: 3 }))
    await nextTick()

    expect(host.querySelector('[data-testid="presenter-playback-state"]')?.textContent?.trim()).toBe('受阻')
    expect(host.querySelector('[data-testid="presenter-playback-primary"]')?.textContent?.trim()).toBe('重试')
    host.querySelector<HTMLButtonElement>('[aria-label="下一页"]')
      ?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await nextTick()
    expect(commands).toEqual(['next'])
  })

  it('观众窗口未全屏时保持等待且不提供命令', async () => {
    const { host } = mountPanel(received('playing'), false)
    await nextTick()

    expect(host.querySelector('[data-testid="presenter-playback-state"]')?.textContent?.trim())
      .toBe('等待观众窗口全屏')
    expect(host.querySelector('[data-testid="presenter-playback-primary"]')).toBeNull()
    expect(host.querySelector('[data-testid="presenter-playback-stop"]')).toBeNull()
    expect(host.querySelector<HTMLButtonElement>('[data-testid="presenter-playback-auto"]')?.disabled).toBe(true)
    expect(host.querySelector<HTMLButtonElement>('[aria-label="下一页"]')?.disabled).toBe(true)
  })

  it('自动/手动切换发送目标状态并显示当前模式', async () => {
    const host = document.createElement('div')
    document.body.appendChild(host)
    const autoEvents: boolean[] = []
    const app = createApp(PresenterPlaybackPanel, {
      playback: received('playing', { autoAdvanceEnabled: true }),
      displayAvailable: true,
      canGoPrevious: false,
      canGoNext: true,
      pageLabel: '1 / 2',
      onAuto: (enabled: boolean) => autoEvents.push(enabled),
    })
    app.mount(host)
    await nextTick()

    const toggle = host.querySelector<HTMLButtonElement>('[data-testid="presenter-playback-auto"]')!
    expect(toggle.textContent?.trim()).toBe('自动')
    toggle.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await nextTick()
    expect(autoEvents).toEqual([false])

    app.unmount()

    const manual = mountPanel(received('playing', { autoAdvanceEnabled: false }))
    await nextTick()
    expect(manual.host.querySelector('[data-testid="presenter-playback-auto"]')?.textContent?.trim()).toBe('手动')
    expect(manual.host.querySelector('[data-testid="presenter-playback-remaining"]')?.textContent?.trim()).toBe('手动')
  })

  it('等待页内时间轴时显示时间轴状态，不误报为本页手动', async () => {
    const playing = mountPanel(received('playing', {
      waitingForTimeline: true,
      timelineId: 'intro',
      planDigest: '0123456789abcdef',
      positionMs: 1200,
      timelineIntent: 'playing',
      timelinePhase: 'ready',
    }))
    await nextTick()
    expect(playing.host.querySelector('[data-testid="presenter-playback-state"]')?.textContent?.trim()).toBe('时间轴播放中')
    expect(playing.host.querySelector('[data-testid="presenter-playback-remaining"]')?.textContent?.trim()).toBe('等待时间轴')
    playing.app.unmount()

    const buffering = mountPanel(received('playing', {
      waitingForTimeline: true,
      timelinePhase: 'buffering',
    }))
    await nextTick()
    expect(buffering.host.querySelector('[data-testid="presenter-playback-state"]')?.textContent?.trim()).toBe('时间轴缓冲')
    buffering.app.unmount()
  })

  it('从暂停继续时按当前时刻重建倒计时，不累计暂停时长', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-18T00:00:00Z'))
    const playback = ref(received('paused', { remainingMs: 2500, delayMs: 4000 }))
    const host = document.createElement('div')
    document.body.appendChild(host)
    const app = createApp(defineComponent({
      setup: () => () => h(PresenterPlaybackPanel, {
        playback: playback.value,
        displayAvailable: true,
        canGoPrevious: false,
        canGoNext: true,
        pageLabel: '1 / 2',
      }),
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
        currentPath: '/b',
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
        total: 3,
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
    canGoPrevious: true,
    canGoNext: true,
    pageLabel: '2 / 3',
    onCommand: (action: PresenterSyncPlaybackCommandAction) => commands.push(action),
    onNext: () => commands.push('next'),
  })
  app.mount(host)
  return { app, host, commands }
}
