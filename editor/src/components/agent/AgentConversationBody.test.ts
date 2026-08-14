/**
 * 文件功能：验证会话正文自动贴底跟随的滚动计算，防止流式签名、阈值与滚动意图判断回归。
 */
import { render } from '@testing-library/vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import AgentConversationBody from '@/components/agent/AgentConversationBody.vue'
import type { TimelineDisplayItem } from '@/components/agent/agent-conversation-panel'
import type { AgentMessageItem, AgentTimelineItem } from '@/types/api'

/**
 * 构造最小 assistant 消息展示项，仅内容随流式输出变化。
 */
function assistantMessageItem(content: string): TimelineDisplayItem {
  const timelineItem: AgentTimelineItem = {
    id: 'assistant-1',
    session_id: 'session-1',
    run_id: 'run-1',
    kind: 'message',
    role: 'assistant',
    event_index: null,
    order_index: 0,
    content,
    status: null,
    tool: null,
    source: 'event',
    created_at: null,
  }
  const message: AgentMessageItem = {
    id: 'assistant-1',
    run_id: 'run-1',
    role: 'assistant',
    content,
    created_at: null,
    tool_name: null,
    tool_call_id: null,
    tool_args: null,
    tool_call_error: null,
  }
  return { id: 'assistant-1', kind: 'message', item: timelineItem, message }
}

function baseProps(content: string, sessionId = 'session-1') {
  return {
    timelineDisplayItems: [assistantMessageItem(content)],
    draftPatches: [],
    loading: false,
    loadingText: '加载中',
    lastRunIssue: null,
    activeRun: null,
    cancellingRunForceAvailable: false,
    isStreaming: true,
    streamingTimelineItemId: 'assistant-1',
    sessionId,
  }
}

interface ScrollMetrics {
  scrollTop: number
  scrollHeight: number
  clientHeight: number
}

/**
 * jsdom 不做布局，用可控属性模拟滚动尺寸；scrollTop 存储原始赋值便于断言贴底写入。
 */
function installScrollMetrics(element: HTMLElement, metrics: ScrollMetrics) {
  Object.defineProperty(element, 'scrollTop', {
    configurable: true,
    get: () => metrics.scrollTop,
    set: value => {
      metrics.scrollTop = value
    },
  })
  Object.defineProperty(element, 'scrollHeight', {
    configurable: true,
    get: () => metrics.scrollHeight,
  })
  Object.defineProperty(element, 'clientHeight', {
    configurable: true,
    get: () => metrics.clientHeight,
  })
}

async function flushAutoScroll() {
  await nextTick()
  await nextTick()
  flushAnimationFrames()
  await nextTick()
}

let animationFrameId = 0
let pendingAnimationFrames = new Map<number, FrameRequestCallback>()
let resizeObserverCallbacks: ResizeObserverCallback[] = []

class ControlledResizeObserver implements ResizeObserver {
  constructor(callback: ResizeObserverCallback) {
    resizeObserverCallbacks.push(callback)
  }

  observe() {}
  unobserve() {}
  disconnect() {}
}

/** 模拟真实浏览器下一帧执行，避免同步 rAF 隐藏调度状态问题。 */
function flushAnimationFrames() {
  const callbacks = [...pendingAnimationFrames.values()]
  pendingAnimationFrames.clear()
  callbacks.forEach(callback => callback(performance.now()))
}

describe('AgentConversationBody 滚动跟随', () => {
  beforeEach(() => {
    animationFrameId = 0
    pendingAnimationFrames = new Map()
    resizeObserverCallbacks = []
    vi.stubGlobal('ResizeObserver', ControlledResizeObserver)
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      animationFrameId += 1
      pendingAnimationFrames.set(animationFrameId, callback)
      return animationFrameId
    })
    vi.stubGlobal('cancelAnimationFrame', (id: number) => {
      pendingAnimationFrames.delete(id)
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  function setup(content: string, metrics: ScrollMetrics) {
    const utils = render(AgentConversationBody, { props: baseProps(content) })
    const container = utils.container.querySelector('.agent-conversation-body') as HTMLElement
    installScrollMetrics(container, metrics)
    return { ...utils, scrollBody: container, metrics }
  }

  it('流式 assistant 消息内容增长时应保持贴底', async () => {
    const metrics: ScrollMetrics = { scrollTop: 600, scrollHeight: 1000, clientHeight: 400 }
    const { rerender, metrics: state } = setup('第一段', metrics)

    state.scrollHeight = 1600
    await rerender(baseProps(`第一段${'内容'.repeat(200)}`))
    await flushAutoScroll()

    expect(state.scrollTop).toBe(1200)
  })

  it('用户上滑离开底部后，新内容不应把视口拉回底部', async () => {
    const metrics: ScrollMetrics = { scrollTop: 600, scrollHeight: 1000, clientHeight: 400 }
    const { rerender, scrollBody, metrics: state } = setup('第一段', metrics)

    scrollBody.dispatchEvent(new WheelEvent('wheel', { deltaY: -20 }))
    state.scrollTop = 580
    scrollBody.dispatchEvent(new Event('scroll'))

    state.scrollHeight = 1600
    await rerender(baseProps(`第一段${'内容'.repeat(200)}`))
    await flushAutoScroll()

    expect(state.scrollTop).toBe(580)
  })

  it('向上滚动后的布局 clamp 不恢复跟随，用户滚回底部后才恢复', async () => {
    const metrics: ScrollMetrics = { scrollTop: 600, scrollHeight: 1000, clientHeight: 400 }
    const { rerender, scrollBody, metrics: state } = setup('第一段', metrics)

    // 先上滑关闭跟随
    scrollBody.dispatchEvent(new WheelEvent('wheel', { deltaY: -20 }))
    state.scrollTop = 100
    scrollBody.dispatchEvent(new Event('scroll'))

    // 布局收缩等原因把 scrollTop clamp 到底部，但没有用户滚动意图
    state.scrollTop = 600
    scrollBody.dispatchEvent(new Event('scroll'))

    state.scrollHeight = 1600
    await rerender(baseProps(`第一段${'内容'.repeat(200)}`))
    await flushAutoScroll()
    expect(state.scrollTop).toBe(600)

    // 用户滚轮滚回底部，应重新开启跟随
    state.scrollTop = 1200
    scrollBody.dispatchEvent(new WheelEvent('wheel', { deltaY: 20 }))
    scrollBody.dispatchEvent(new Event('scroll'))

    state.scrollHeight = 2200
    await rerender(baseProps(`第一段${'内容'.repeat(400)}`))
    await flushAutoScroll()
    expect(state.scrollTop).toBe(1800)
  })

  it('多次内容尺寸变化应合并为同一动画帧的贴底写入', async () => {
    const metrics: ScrollMetrics = { scrollTop: 600, scrollHeight: 1000, clientHeight: 400 }
    const { metrics: state } = setup('第一段', metrics)
    await flushAutoScroll()

    state.scrollHeight = 1600
    resizeObserverCallbacks.forEach(callback => {
      callback([], {} as ResizeObserver)
      callback([], {} as ResizeObserver)
      callback([], {} as ResizeObserver)
    })
    await nextTick()

    expect(pendingAnimationFrames.size).toBe(1)
    flushAnimationFrames()
    expect(state.scrollTop).toBe(1200)
  })

  it('切换会话后应重新跟随新会话底部', async () => {
    const metrics: ScrollMetrics = { scrollTop: 600, scrollHeight: 1000, clientHeight: 400 }
    const { rerender, scrollBody, metrics: state } = setup('第一段', metrics)
    await flushAutoScroll()

    scrollBody.dispatchEvent(new WheelEvent('wheel', { deltaY: -20 }))
    state.scrollTop = 580
    scrollBody.dispatchEvent(new Event('scroll'))

    state.scrollHeight = 1600
    await rerender(baseProps('新会话消息', 'session-2'))
    await flushAutoScroll()

    expect(state.scrollTop).toBe(1200)
  })
})
