// @vitest-environment jsdom
/** 文件功能：验证双页过渡的快速导航、方向、静态模式与清理边界。 */
import { createApp, h, nextTick, reactive } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import PageTransitionHost from './PageTransitionHost.vue'

afterEach(() => { vi.useRealTimers(); document.body.innerHTML = '' })

/** 挂载可更新页面参数的测试宿主。 */
function mountHost() {
  const state = reactive({ page: 'a', number: 1, disabled: false })
  const root = document.createElement('div')
  document.body.append(root)
  const app = createApp({ render: () => h(PageTransitionHost, {
    node: h('p', state.page), pageKey: state.page, pageNumber: state.number,
    config: { effect: 'push', durationMs: 400 }, disabled: state.disabled,
  }) })
  app.mount(root)
  return { state, root, app }
}

describe('PageTransitionHost', () => {
  it('初次显示静态，过渡至多两层，连续请求只留下最新目标', async () => {
    vi.useFakeTimers()
    const { state, root, app } = mountHost()
    expect(root.querySelectorAll('p')).toHaveLength(1)
    state.page = 'b'; state.number = 2
    await nextTick(); await nextTick()
    expect(root.querySelectorAll('p')).toHaveLength(2)
    state.page = 'c'; state.number = 3
    await nextTick()
    state.page = 'd'; state.number = 4
    await nextTick()
    expect(root.querySelectorAll('p')).toHaveLength(2)
    await vi.advanceTimersByTimeAsync(1100)
    expect(root.textContent).toBe('d')
    expect(root.querySelector('[data-transition-state]')?.getAttribute('data-transition-state')).toBe('idle')
    app.unmount()
  })

  it('后翻反向，切换静态模式立即完成并清除旧页', async () => {
    vi.useFakeTimers()
    const { state, root, app } = mountHost()
    state.page = 'previous'; state.number = 0
    await nextTick(); await nextTick()
    expect(root.querySelector<HTMLElement>('.page-transition-host')?.style.getPropertyValue('--transition-direction')).toBe('-1')
    state.disabled = true
    await nextTick(); await nextTick()
    expect(root.querySelectorAll('p')).toHaveLength(1)
    expect(root.textContent).toBe('previous')
    app.unmount()
    expect(vi.getTimerCount()).toBeLessThanOrEqual(1)
  })
})
