// @vitest-environment jsdom
/** 文件功能：验证双页过渡的快速导航、方向、静态模式与清理边界。 */
import { createApp, h, nextTick, reactive } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import PageTransitionHost from './PageTransitionHost.vue'

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); document.body.innerHTML = '' })

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

describe('PageTransitionHost settled 信号', () => {
  it('初次挂载在 DOM 提交后报告一次路径与 generation，动画结束只报告一次', async () => {
    vi.useFakeTimers()
    const settled: Array<{ path: string; generation: number }> = []
    const state = reactive({ page: 'a', number: 1 })
    const root = document.createElement('div')
    document.body.append(root)
    const app = createApp({ render: () => h(PageTransitionHost, {
      node: h('p', state.page), pageKey: state.page, pageNumber: state.number,
      config: { effect: 'fade', durationMs: 400 }, onSettled: (event: { path: string; generation: number }) => settled.push(event),
    }) })
    app.mount(root)

    await nextTick(); await nextTick()
    expect(settled).toHaveLength(1)
    expect(settled[0].path).toBe('a')
    expect(settled[0].generation).toBeGreaterThan(0)

    state.page = 'b'; state.number = 2
    await nextTick(); await nextTick()
    expect(root.querySelectorAll('p')).toHaveLength(2)
    const entering = root.querySelector<HTMLElement>('.page-transition-layer.entering')
    expect(entering).not.toBeNull()

    // 子元素冒泡的 transitionend 不得收尾。
    const childEvent = new Event('transitionend', { bubbles: true })
    Object.defineProperty(childEvent, 'propertyName', { value: 'opacity' })
    entering?.querySelector('p')?.dispatchEvent(childEvent)
    expect(settled).toHaveLength(1)

    const enterEvent = new Event('transitionend', { bubbles: false })
    Object.defineProperty(enterEvent, 'propertyName', { value: 'opacity' })
    entering?.dispatchEvent(enterEvent)
    await nextTick()
    expect(settled).toHaveLength(2)
    expect(settled[1].path).toBe('b')
    expect(settled[1].generation).toBeGreaterThan(settled[0].generation)

    // 兜底计时器不得重复报告。
    await vi.advanceTimersByTimeAsync(600)
    expect(settled).toHaveLength(2)
    app.unmount()
  })

  it('无动画导航在目标页提交后立即报告，且旧 generation 被过滤', async () => {
    const settled: Array<{ path: string; generation: number }> = []
    const state = reactive({ page: 'a', number: 1, effect: 'none' as const })
    const root = document.createElement('div')
    document.body.append(root)
    const app = createApp({ render: () => h(PageTransitionHost, {
      node: h('p', state.page), pageKey: state.page, pageNumber: state.number,
      config: { effect: state.effect, durationMs: 0 }, onSettled: (event: { path: string; generation: number }) => settled.push(event),
    }) })
    app.mount(root)
    await nextTick(); await nextTick()

    state.page = 'b'; state.number = 2
    await nextTick(); await nextTick()
    expect(root.querySelectorAll('p')).toHaveLength(1)
    expect(settled.at(-1)?.path).toBe('b')
    expect(new Set(settled.map(item => item.generation)).size).toBe(settled.length)
    app.unmount()
  })
})

describe('PageTransitionHost started 信号', () => {
  interface Started { generation: number; fromPath: string; toPath: string; direction: 1 | -1; effect: string }

  /** 挂载带 started 记录的最小宿主。 */
  function mountStarted(options: { effect?: 'none' | 'fade' | 'push'; disabled?: boolean } = {}) {
    const started: Started[] = []
    const state = reactive({
      page: 'a', number: 1, disabled: options.disabled ?? false,
      effect: (options.effect ?? 'push') as 'none' | 'fade' | 'push',
    })
    const root = document.createElement('div')
    document.body.append(root)
    const app = createApp({ render: () => h(PageTransitionHost, {
      node: h('p', state.page), pageKey: state.page, pageNumber: state.number,
      config: { effect: state.effect, durationMs: 400 }, disabled: state.disabled,
      onStarted: (event: Started) => started.push(event),
    }) })
    app.mount(root)
    return { state, root, app, started }
  }

  it('初次挂载与同路径刷新不发声', async () => {
    const { state, app, started } = mountStarted()
    await nextTick(); await nextTick()
    expect(started).toHaveLength(0)

    state.number = 9
    await nextTick(); await nextTick()
    expect(started).toHaveLength(0)
    app.unmount()
  })

  it('真实前进/后退报告方向并复用过渡 generation', async () => {
    vi.useFakeTimers()
    const { state, app, started } = mountStarted()
    await nextTick(); await nextTick()

    state.page = 'b'; state.number = 2
    await nextTick(); await nextTick()
    expect(started).toHaveLength(1)
    expect(started[0]).toMatchObject({ fromPath: 'a', toPath: 'b', direction: 1, effect: 'push' })

    await vi.advanceTimersByTimeAsync(600)
    state.page = 'previous'; state.number = 0
    await nextTick(); await nextTick()
    expect(started).toHaveLength(2)
    expect(started[1]).toMatchObject({ fromPath: 'b', toPath: 'previous', direction: -1 })
    expect(started[1].generation).toBeGreaterThan(started[0].generation)
    app.unmount()
  })

  it('effect=none 与减少动态效果仍视为真实翻页', async () => {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: false, media: query, onchange: null,
      addEventListener: () => undefined, removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }))
    const none = mountStarted({ effect: 'none' })
    await nextTick(); await nextTick()
    none.state.page = 'b'; none.state.number = 2
    await nextTick(); await nextTick()
    expect(none.started).toHaveLength(1)
    expect(none.started[0].effect).toBe('none')
    none.app.unmount()

    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: true, media: query, onchange: null,
      addEventListener: () => undefined, removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }))
    const reduced = mountStarted()
    await nextTick(); await nextTick()
    reduced.state.page = 'b'; reduced.state.number = 2
    await nextTick(); await nextTick()
    expect(reduced.started).toHaveLength(1)
    reduced.app.unmount()
  })

  it('快速连跳只为实际被接受的 generation 发声，被替换的中间页不发声', async () => {
    vi.useFakeTimers()
    const { state, app, started } = mountStarted()
    await nextTick(); await nextTick()

    state.page = 'b'; state.number = 2
    await nextTick(); await nextTick()
    state.page = 'c'; state.number = 3
    await nextTick()
    state.page = 'd'; state.number = 4
    await nextTick()
    expect(started.map(item => item.toPath)).toEqual(['b'])

    await vi.advanceTimersByTimeAsync(1200)
    expect(started.map(item => item.toPath)).toEqual(['b', 'd'])
    app.unmount()
  })

  it('卸载丢弃尚未开始的待切换页，不产生迟到信号', async () => {
    vi.useFakeTimers()
    const { state, app, started } = mountStarted()
    await nextTick(); await nextTick()

    state.page = 'b'; state.number = 2
    await nextTick(); await nextTick()
    expect(started.map(item => item.toPath)).toEqual(['b'])

    state.page = 'c'; state.number = 3
    await nextTick(); await nextTick()
    expect(started.map(item => item.toPath)).toEqual(['b'])

    app.unmount()
    await vi.advanceTimersByTimeAsync(1200)
    expect(started.map(item => item.toPath)).toEqual(['b'])
  })
})
