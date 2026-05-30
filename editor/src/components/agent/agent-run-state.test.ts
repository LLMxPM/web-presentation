/**
 * 文件功能：验证智能体 run-first 时间线状态机的去重、工具配对与快照恢复。
 */
import { describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { applyAgentRunEvent, applyAgentRuntimeSnapshot, createAgentSessionRuntimeState } from '@/components/agent/agent-run-state'
import { useAgentSessionStore } from '@/stores/agent-session'
import type { AgentRunEvent, AgentTimelineItem } from '@/types/api'

function event(payload: Partial<AgentRunEvent>): AgentRunEvent {
  return {
    event: 'message.delta',
    run_id: 'run-1',
    session_id: 'session-1',
    content: null,
    data: {},
    sequence: 1,
    ...payload,
  }
}

function timelineItem(overrides: Partial<AgentTimelineItem>): AgentTimelineItem {
  return {
    id: overrides.id ?? `item-${overrides.order_index ?? 0}`,
    session_id: 'session-1',
    run_id: 'run-1',
    kind: 'message',
    role: 'assistant',
    event_index: null,
    order_index: 0,
    content: null,
    status: null,
    tool: null,
    source: 'event',
    created_at: null,
    ...overrides,
  }
}

describe('agent-run-state timeline', () => {
  it('重复 sequence 不应重复追加 delta', () => {
    const state = createAgentSessionRuntimeState()
    const options = { agentId: 'agent-coordinator', agentDisplayName: '内容助手' }

    applyAgentRunEvent(state, event({ event: 'run.started', sequence: 1 }), options)
    applyAgentRunEvent(state, event({ event: 'message.delta', content: '你好', sequence: 2 }), options)
    applyAgentRunEvent(state, event({ event: 'message.delta', content: '你好', sequence: 2 }), options)

    const assistantItems = state.timelineItems.filter(item => item.kind === 'message' && item.role === 'assistant')
    expect(assistantItems).toHaveLength(1)
    expect(assistantItems[0].content).toBe('你好')
  })

  it('旧 run 事件不能污染当前 run', () => {
    const state = createAgentSessionRuntimeState()
    const options = { agentId: 'agent-coordinator', agentDisplayName: '内容助手' }

    applyAgentRunEvent(state, event({ event: 'run.started', run_id: 'run-1', sequence: 1 }), options)
    applyAgentRunEvent(state, event({ event: 'message.delta', run_id: 'run-2', content: '旧消息', sequence: 1 }), options)

    expect(state.timelineItems).toHaveLength(0)
  })

  it('paused 应写入 requirement 时间线并停止 streaming', () => {
    const state = createAgentSessionRuntimeState()
    const options = { agentId: 'agent-coordinator', agentDisplayName: '内容助手' }

    applyAgentRunEvent(state, event({ event: 'run.started', sequence: 1 }), options)
    applyAgentRunEvent(state, event({
      event: 'run.paused',
      sequence: 2,
      data: {
        requirement: {
          id: 'req-1',
          kind: 'confirmation',
          run_id: 'run-1',
          session_id: 'session-1',
          tool_name: 'apply_page_edits',
          tool_execution: {},
          suggested_patch: null,
          user_feedback_schema: [],
          note: null,
        },
      },
    }), options)

    expect(state.activeRun?.status).toBe('paused')
    expect(state.pendingRequirement?.id).toBe('req-1')
    expect(state.stream.streaming).toBe(false)
    expect(state.timelineItems.some(item => item.kind === 'requirement')).toBe(true)
  })

  it('ask_user paused requirement 时间线应显示问题文案', () => {
    const state = createAgentSessionRuntimeState()
    const options = { agentId: 'agent-coordinator', agentDisplayName: '内容助手' }

    applyAgentRunEvent(state, event({ event: 'run.started', sequence: 1 }), options)
    applyAgentRunEvent(state, event({
      event: 'run.paused',
      sequence: 2,
      data: {
        requirement: {
          id: 'req-ask-1',
          kind: 'user_feedback',
          run_id: 'run-1',
          session_id: 'session-1',
          tool_name: 'ask_user',
          tool_execution: { tool_name: 'ask_user', tool_call_id: 'tool-ask-1', requires_user_input: true },
          suggested_patch: null,
          user_feedback_schema: [
            {
              question: '是否继续整理资源？',
              header: '继续',
              options: [{ label: '继续', description: '继续整理资源。' }],
              multi_select: false,
              selected_options: null,
            },
          ],
          note: null,
        },
      },
    }), options)

    const requirementItem = state.timelineItems.find(item => item.kind === 'requirement')
    expect(requirementItem?.content).toBe('是否继续整理资源？')
  })

  it('cancelled 应清理 activeRun 并写入 run_status', () => {
    const state = createAgentSessionRuntimeState()
    const options = { agentId: 'agent-coordinator', agentDisplayName: '内容助手' }

    applyAgentRunEvent(state, event({ event: 'run.started', sequence: 1 }), options)
    applyAgentRunEvent(state, event({ event: 'run.cancelled', sequence: 2 }), options)

    expect(state.activeRun).toBeNull()
    expect(state.lastRun?.status).toBe('cancelled')
    expect(state.stream.streaming).toBe(false)
    expect(state.timelineItems.at(-1)).toEqual(expect.objectContaining({ kind: 'run_status', status: 'cancelled' }))
  })

  it('thinking、tool、assistant 应作为独立时间线项', () => {
    const state = createAgentSessionRuntimeState()
    const options = { agentId: 'agent-coordinator', agentDisplayName: '内容助手' }

    applyAgentRunEvent(state, event({ event: 'run.started', sequence: 1 }), options)
    applyAgentRunEvent(state, event({
      event: 'message.delta',
      content: '',
      data: { reasoning_content: '先判断是否需要工具' },
      sequence: 2,
    }), options)
    applyAgentRunEvent(state, event({
      event: 'tool.completed',
      data: { tool_name: 'list_workspace_render_assets', result: { total: 1 } },
      sequence: 3,
    }), options)
    applyAgentRunEvent(state, event({
      event: 'message.delta',
      content: '资源检查完成。',
      sequence: 4,
    }), options)

    expect(state.timelineItems.map(item => item.kind)).toEqual(['reasoning', 'tool', 'message'])
    expect(state.timelineItems[1].tool?.tool_name).toBe('list_workspace_render_assets')
    expect(state.timelineItems[2].content).toBe('资源检查完成。')
  })

  it('缺少 tool_call_id 时 started 和 completed 应合并为同一工具时间线项', () => {
    const state = createAgentSessionRuntimeState()
    const options = { agentId: 'agent-coordinator', agentDisplayName: '内容助手' }

    applyAgentRunEvent(state, event({ event: 'run.started', sequence: 1 }), options)
    applyAgentRunEvent(state, event({
      event: 'tool.started',
      data: {
        tool_name: 'list_workspace_render_assets',
        tool_args: { workspace_id: 11 },
      },
      sequence: 2,
    }), options)
    applyAgentRunEvent(state, event({
      event: 'tool.completed',
      data: {
        tool_name: 'list_workspace_render_assets',
        result: { total: 2 },
      },
      sequence: 3,
    }), options)

    const tools = state.timelineItems.filter(item => item.kind === 'tool')
    expect(tools).toHaveLength(1)
    expect(tools[0].tool).toEqual(expect.objectContaining({
      tool_call_id: null,
      tool_name: 'list_workspace_render_assets',
      status: 'completed',
      input_payload: { workspace_id: 11 },
      output_payload: { total: 2 },
    }))
  })

  it('runtime snapshot 应直接恢复完整 timeline', () => {
    const state = createAgentSessionRuntimeState()

    applyAgentRuntimeSnapshot(state, {
      timelineItems: [
        timelineItem({ id: 'user-1', kind: 'message', role: 'user', order_index: 0, content: '检查资源' }),
        timelineItem({ id: 'tool-1', kind: 'tool', role: null, order_index: 1, status: 'completed', tool: {
          tool_call_id: null,
          tool_name: 'list_workspace_render_assets',
          status: 'completed',
          input_payload: { workspace_id: 1 },
          output_payload: { total: 2 },
          message: '',
        } }),
      ],
      activeRun: null,
      lastRun: {
        run_id: 'run-1',
        session_id: 'session-1',
        agent_id: 'agent-coordinator',
        status: 'cancelled',
        pending_requirement: null,
        content: null,
        created_at: '2026-04-18T10:00:00+08:00',
        event_index: 3,
      },
      pendingRequirement: null,
      pendingImageAttachments: [],
      contextStatus: null,
      eventIndex: 3,
    })

    expect(state.timelineItems.map(item => item.id)).toEqual(['user-1', 'tool-1'])
    expect(state.timelineItems[1].tool?.output_payload).toEqual({ total: 2 })
    expect(state.stream.lastSequenceByRun['run-1']).toBe(3)
  })

  it('取消终态快照缺少当前 run 进度时应保留本地 timeline', () => {
    const state = createAgentSessionRuntimeState()
    state.activeRun = {
      run_id: 'run-1',
      session_id: 'session-1',
      agent_id: 'agent-coordinator',
      status: 'cancelling',
      pending_requirement: null,
      content: null,
      created_at: '2026-04-18T10:00:00+08:00',
      event_index: 2,
    }
    state.timelineItems = [
      timelineItem({ id: 'local-assistant', run_id: 'run-1', kind: 'message', role: 'assistant', order_index: 0, content: '本地已流出内容' }),
      timelineItem({ id: 'local-tool', run_id: 'run-1', kind: 'tool', role: null, order_index: 1, status: 'completed', tool: {
        tool_call_id: null,
        tool_name: 'list_workspace_render_assets',
        status: 'completed',
        input_payload: null,
        output_payload: { total: 1 },
        message: '',
      } }),
    ]

    applyAgentRuntimeSnapshot(state, {
      timelineItems: [],
      activeRun: null,
      lastRun: {
        run_id: 'run-1',
        session_id: 'session-1',
        agent_id: 'agent-coordinator',
        status: 'cancelled',
        pending_requirement: null,
        content: null,
        created_at: '2026-04-18T10:00:00+08:00',
        event_index: 3,
      },
      pendingRequirement: null,
      pendingImageAttachments: [],
      contextStatus: null,
      eventIndex: 3,
    })

    expect(state.timelineItems.map(item => item.id)).toEqual(['local-assistant', 'local-tool'])
    expect(state.lastRun?.status).toBe('cancelled')
  })

  it('store 扁平缓存中的 null 应能清理嵌套 paused requirement', () => {
    setActivePinia(createPinia())
    const store = useAgentSessionStore()
    const sessionId = 'session-1'

    store.setPendingRequirement(sessionId, {
      id: 'req-1',
      kind: 'confirmation',
      run_id: 'run-1',
      session_id: sessionId,
      tool_name: 'apply_page_edits',
      tool_execution: {},
      suggested_patch: null,
      user_feedback_schema: [],
      note: null,
    })
    store.pendingRequirementBySession[sessionId] = null
    store.applyRunEvent(sessionId, event({ event: 'run.cancelling', sequence: 1 }), {
      agentId: 'agent-coordinator',
      agentDisplayName: '内容助手',
    })

    expect(store.sessions[sessionId].pendingRequirement).toBeNull()
  })

  it('Agno raw event 应投影成运行中、消息增量和 HITL 暂停状态', () => {
    const state = createAgentSessionRuntimeState()
    const options = { agentId: 'agent-coordinator', agentDisplayName: '内容助手' }

    applyAgentRunEvent(state, event({ event: 'RunStarted', event_index: 0, sequence: null }), options)
    applyAgentRunEvent(state, event({ event: 'RunContent', content: '半截输出', event_index: 1, sequence: null }), options)
    applyAgentRunEvent(state, event({
      event: 'RunPaused',
      event_index: 2,
      sequence: null,
      requirements: [{
        id: 'req-1',
        tool_execution: {
          tool_name: 'apply_page_edits',
          tool_call_id: 'call-1',
          requires_confirmation: true,
          confirmed: null,
          tool_args: { note: '写入页面' },
        },
      }],
    }), options)

    expect(state.timelineItems.find(item => item.kind === 'message')?.content).toBe('半截输出')
    expect(state.activeRun?.status).toBe('paused')
    expect(state.activeRun?.event_index).toBe(2)
    expect(state.pendingRequirement).toEqual(expect.objectContaining({
      id: 'req-1',
      tool_name: 'apply_page_edits',
    }))
  })
})
