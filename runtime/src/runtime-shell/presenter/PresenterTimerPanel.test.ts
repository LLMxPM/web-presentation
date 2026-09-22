// @vitest-environment jsdom

/**
 * 文件用途：验证演讲计时面板的开始、暂停、重置与当前页切换计时行为。
 */

import { createApp, defineComponent, nextTick, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import PresenterTimerPanel from './PresenterTimerPanel.vue'

const currentPath = ref('/intro')

beforeEach(() => {
  currentPath.value = '/intro'
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-06-06T09:00:00.000Z'))
})

afterEach(() => {
  vi.clearAllTimers()
  vi.useRealTimers()
  document.body.innerHTML = ''
})

describe('PresenterTimerPanel', () => {
  it('开始计时后应同步刷新当前页与总计时，并在切页时重置当前页计时', async () => {
    const { app, host } = mountPresenterTimerPanel()
    await nextTick()

    clickByTestId(host, 'presenter-timer-toggle')
    vi.advanceTimersByTime(65_000)
    await nextTick()

    expect(readTextByTestId(host, 'presenter-timer-current')).toBe('00:01:05')
    expect(readTextByTestId(host, 'presenter-timer-total')).toBe('00:01:05')

    currentPath.value = '/summary'
    await nextTick()

    expect(readTextByTestId(host, 'presenter-timer-current')).toBe('00:00:00')
    expect(readTextByTestId(host, 'presenter-timer-total')).toBe('00:01:05')

    vi.advanceTimersByTime(5_000)
    await nextTick()

    expect(readTextByTestId(host, 'presenter-timer-current')).toBe('00:00:05')
    expect(readTextByTestId(host, 'presenter-timer-total')).toBe('00:01:10')

    app.unmount()
  })

  it('暂停后应停止累加，重置应清空当前页与总计时', async () => {
    const { app, host } = mountPresenterTimerPanel()
    await nextTick()

    clickByTestId(host, 'presenter-timer-toggle')
    vi.advanceTimersByTime(12_000)
    await nextTick()

    clickByTestId(host, 'presenter-timer-toggle')
    vi.advanceTimersByTime(8_000)
    await nextTick()

    expect(readTextByTestId(host, 'presenter-timer-current')).toBe('00:00:12')
    expect(readTextByTestId(host, 'presenter-timer-total')).toBe('00:00:12')

    clickByTestId(host, 'presenter-timer-reset')
    await nextTick()

    expect(readTextByTestId(host, 'presenter-timer-current')).toBe('00:00:00')
    expect(readTextByTestId(host, 'presenter-timer-total')).toBe('00:00:00')

    app.unmount()
  })
})

/**
 * 挂载计时面板测试宿主。
 * @returns 应用实例和宿主节点
 */
function mountPresenterTimerPanel() {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const RootComponent = defineComponent({
    components: {
      PresenterTimerPanel,
    },
    setup() {
      return {
        currentPath,
      }
    },
    template: '<PresenterTimerPanel :current-path="currentPath" />',
  })
  const app = createApp(RootComponent)
  app.config.errorHandler = (error) => {
    throw error
  }
  app.mount(host)
  return { app, host }
}

/**
 * 读取测试节点文本。
 * @param host 测试宿主节点
 * @param testId 目标测试标识
 * @returns 节点文本内容
 */
function readTextByTestId(host: HTMLElement, testId: string): string {
  const element = host.querySelector(`[data-testid="${testId}"]`)
  if (!(element instanceof HTMLElement)) {
    throw new Error(`未找到 test id: ${testId}`)
  }
  return element.textContent?.trim() || ''
}

/**
 * 触发指定测试节点的点击行为。
 * @param host 测试宿主节点
 * @param testId 目标测试标识
 */
function clickByTestId(host: HTMLElement, testId: string): void {
  const element = host.querySelector(`[data-testid="${testId}"]`)
  if (!(element instanceof HTMLButtonElement)) {
    throw new Error(`未找到按钮 test id: ${testId}`)
  }
  element.click()
}
