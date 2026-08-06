/**
 * 文件功能：验证页面 Runtime 预览生命周期的弱网、超时、迟到 ready 与重置行为。
 */
import { defineComponent, h, nextTick } from 'vue'
import { render, screen } from '@testing-library/vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useRuntimePreviewLifecycle } from '@/composables/useRuntimePreviewLifecycle'

afterEach(() => vi.useRealTimers())

describe('useRuntimePreviewLifecycle', () => {
  it('应按 8 秒和 30 秒阈值推进，并允许超时后的迟到 ready 恢复', async () => {
    vi.useFakeTimers()
    const lifecycle = mountLifecycle()
    lifecycle.start('loading')
    await nextTick()

    expect(screen.getByTestId('status')).toHaveTextContent('loading')
    vi.advanceTimersByTime(8000)
    await nextTick()
    expect(screen.getByTestId('status')).toHaveTextContent('slow')

    vi.advanceTimersByTime(22000)
    await nextTick()
    expect(screen.getByTestId('status')).toHaveTextContent('error')
    expect(screen.getByTestId('message')).toHaveTextContent('超过 30 秒')

    lifecycle.markReady()
    await nextTick()
    expect(screen.getByTestId('status')).toHaveTextContent('ready')
    expect(screen.getByTestId('message').textContent).toBe('')
  })

  it('新周期与重置应使旧计时器失效', async () => {
    vi.useFakeTimers()
    const lifecycle = mountLifecycle()
    lifecycle.start('loading')
    lifecycle.start('generating')
    lifecycle.reset()
    vi.advanceTimersByTime(30000)
    await nextTick()

    expect(screen.getByTestId('status')).toHaveTextContent('idle')
    expect(screen.getByTestId('message').textContent).toBe('')
  })
})

/** 挂载生命周期测试宿主并返回可调用接口。 */
function mountLifecycle() {
  let lifecycle!: ReturnType<typeof useRuntimePreviewLifecycle>
  render(defineComponent({
    name: 'RuntimePreviewLifecycleTestHost',
    setup() {
      lifecycle = useRuntimePreviewLifecycle()
      return () => h('div', [
        h('span', { 'data-testid': 'status' }, lifecycle.status.value),
        h('span', { 'data-testid': 'message' }, lifecycle.message.value),
      ])
    },
  }))
  return lifecycle
}
