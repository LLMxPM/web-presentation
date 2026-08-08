/**
 * 文件功能：验证悬浮 AI 形象入口的点击展开、Y 轴拖拽、边界约束与位置持久化。
 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { beforeEach, describe, expect, it } from 'vitest'

import AgentFloatingTrigger from '@/components/agent/AgentFloatingTrigger.vue'

const STORAGE_KEY = 'web-presentation:agent-floating-trigger-top'
/** jsdom 默认视口高度。 */
const VIEWPORT_HEIGHT = 768
/** 与组件常量保持一致：顶栏 56px + 上下间距 16px。 */
const MIN_TOP = 72
const MAX_TOP = VIEWPORT_HEIGHT - 48 - 16

describe('AgentFloatingTrigger', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('渲染可访问的形象入口按钮', () => {
    render(AgentFloatingTrigger, { props: { expanded: false } })

    const trigger = screen.getByTestId('agent-floating-trigger')
    expect(trigger).toHaveAttribute('aria-label', '打开内容助手')
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
  })

  it('面板展开期间隐藏形象入口', () => {
    const { container } = render(AgentFloatingTrigger, { props: { expanded: true } })

    expect(container.querySelector('[data-testid="agent-floating-trigger"]')).toBeNull()
  })

  it('点击形象应上报展开', async () => {
    const view = render(AgentFloatingTrigger, { props: { expanded: false } })

    await fireEvent.click(screen.getByTestId('agent-floating-trigger'))

    expect(view.emitted()['update:expanded']).toEqual([[true]])
  })

  it('Y 轴拖拽应移动形象、不触发展开并持久化位置', async () => {
    const view = render(AgentFloatingTrigger, { props: { expanded: false } })
    const trigger = screen.getByTestId('agent-floating-trigger')

    await fireEvent.pointerDown(trigger, { clientY: 200, button: 0 })
    await fireEvent.pointerMove(trigger, { clientY: 300 })
    await fireEvent.pointerUp(trigger)
    await fireEvent.click(trigger)

    expect(Number.parseFloat(trigger.style.top)).toBe(330.4)
    expect(view.emitted()['update:expanded']).toBeUndefined()
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe('330')
  })

  it('拖拽位移低于阈值时视为点击', async () => {
    const view = render(AgentFloatingTrigger, { props: { expanded: false } })
    const trigger = screen.getByTestId('agent-floating-trigger')

    await fireEvent.pointerDown(trigger, { clientY: 200, button: 0 })
    await fireEvent.pointerMove(trigger, { clientY: 202 })
    await fireEvent.pointerUp(trigger)
    await fireEvent.click(trigger)

    expect(view.emitted()['update:expanded']).toEqual([[true]])
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it('拖拽超出视口边界时应收敛在可移动范围内', async () => {
    render(AgentFloatingTrigger, { props: { expanded: false } })
    const trigger = screen.getByTestId('agent-floating-trigger')

    await fireEvent.pointerDown(trigger, { clientY: 200, button: 0 })
    await fireEvent.pointerMove(trigger, { clientY: 8000 })
    await fireEvent.pointerUp(trigger)

    expect(Number.parseFloat(trigger.style.top)).toBe(MAX_TOP)
  })

  it('拖拽到顶部时应收敛在最小边界', async () => {
    render(AgentFloatingTrigger, { props: { expanded: false } })
    const trigger = screen.getByTestId('agent-floating-trigger')

    await fireEvent.pointerDown(trigger, { clientY: 200, button: 0 })
    await fireEvent.pointerMove(trigger, { clientY: 0 })
    await fireEvent.pointerUp(trigger)

    expect(Number.parseFloat(trigger.style.top)).toBe(MIN_TOP)
  })

  it('渲染时应恢复上次持久化的位置', () => {
    window.localStorage.setItem(STORAGE_KEY, '500')
    render(AgentFloatingTrigger, { props: { expanded: false } })

    expect(screen.getByTestId('agent-floating-trigger').style.top).toBe('500px')
  })

  it('持久化位置超出当前视口时按边界收敛', () => {
    window.localStorage.setItem(STORAGE_KEY, '9999')
    render(AgentFloatingTrigger, { props: { expanded: false } })

    expect(Number.parseFloat(screen.getByTestId('agent-floating-trigger').style.top)).toBe(MAX_TOP)
  })
})
