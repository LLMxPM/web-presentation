/**
 * 文件功能：验证智能体 run-first 时间线状态机的去重、工具配对与快照恢复。
 */
import { describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import {
  applyAgentRunEvent,
  applyAgentRuntimeSnapshot,
  createAgentSessionRuntimeState,
} from '@/components/agent/agent-run-state'
import { useAgentSessionStore } from '@/stores/agent-session'
import type { AgentPendingRequirement, AgentRunEvent, AgentTimelineItem } from '@/types/api'

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

  it('reasoning.delta 应作为独立思考时间线项', () => {
    const state = createAgentSessionRuntimeState()
    const options = { agentId: 'agent-coordinator', agentDisplayName: '内容助手' }

    applyAgentRunEvent(state, event({ event: 'run.started', sequence: 1 }), options)
    applyAgentRunEvent(state, event({
      event: 'reasoning.delta',
      content: '先分析需求。',
      sequence: 2,
    }), options)

    expect(state.timelineItems).toEqual([
      expect.objectContaining({
        kind: 'reasoning',
        content: '先分析需求。',
        status: 'running',
      }),
    ])
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

  it('运行中 runtime snapshot 应推进回放游标避免旧事件重复插入', () => {
    const state = createAgentSessionRuntimeState()
    const options = { agentId: 'agent-coordinator', agentDisplayName: '内容助手' }

    applyAgentRuntimeSnapshot(state, {
      timelineItems: [
        timelineItem({ id: 'reasoning-1', kind: 'reasoning', role: null, order_index: 0, event_index: 1, content: '先分析。' }),
        timelineItem({ id: 'tool-1', kind: 'tool', role: null, order_index: 1, event_index: 2, status: 'completed', tool: {
          tool_call_id: 'call-1',
          tool_name: 'list_workspace_render_assets',
          status: 'completed',
          input_payload: { workspace_id: 1 },
          output_payload: { total: 2 },
          message: '',
        } }),
      ],
      activeRun: {
        run_id: 'run-1',
        session_id: 'session-1',
        agent_id: 'agent-coordinator',
        status: 'running',
        pending_requirement: null,
        content: null,
        created_at: '2026-04-18T10:00:00+08:00',
        event_index: 2,
      },
      lastRun: null,
      pendingRequirement: null,
      pendingImageAttachments: [],
      contextStatus: null,
      eventIndex: 2,
    })

    const replayed = applyAgentRunEvent(state, event({
      event: 'message.delta',
      content: '旧片段不应重复出现。',
      event_index: 1,
      sequence: null,
    }), options)
    const next = applyAgentRunEvent(state, event({
      event: 'message.delta',
      content: '新片段。',
      event_index: 3,
      sequence: null,
    }), options)

    expect(state.stream.lastSequenceByRun['run-1']).toBe(3)
    expect(replayed.applied).toBe(false)
    expect(next.applied).toBe(true)
    expect(state.timelineItems.map(item => item.content)).toEqual(['先分析。', null, '新片段。'])
  })

  it('取消终态快照缺少当前 run 进度时应以快照 timeline 为准', () => {
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

    expect(state.timelineItems).toEqual([])
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

  it('store 设置 running activeRun 时应清理旧 pending requirement', () => {
    setActivePinia(createPinia())
    const store = useAgentSessionStore()
    const sessionId = 'session-1'
    const requirement: AgentPendingRequirement = {
      id: 'req-1',
      kind: 'user_feedback',
      run_id: 'run-1',
      session_id: sessionId,
      tool_name: 'ask_user',
      tool_execution: { tool_name: 'ask_user', tool_call_id: 'tool-ask-1' },
      suggested_patch: null,
      user_feedback_schema: [],
      note: null,
    }

    store.setActiveRun(sessionId, {
      run_id: 'run-1',
      session_id: sessionId,
      agent_id: 'agent-coordinator',
      status: 'paused',
      pending_requirement: requirement,
      content: null,
      created_at: null,
    })
    store.setActiveRun(sessionId, {
      run_id: 'run-1',
      session_id: sessionId,
      agent_id: 'agent-coordinator',
      status: 'running',
      pending_requirement: requirement,
      content: null,
      created_at: null,
    })

    expect(store.activeRunBySession[sessionId]?.pending_requirement).toBeNull()
    expect(store.pendingRequirementBySession[sessionId]).toBeNull()
  })

  it('平台事件应投影成运行中、消息增量和 HITL 暂停状态', () => {
    const state = createAgentSessionRuntimeState()
    const options = { agentId: 'agent-coordinator', agentDisplayName: '内容助手' }

    applyAgentRunEvent(state, event({ event: 'run.started', event_index: 0, sequence: null }), options)
    applyAgentRunEvent(state, event({ event: 'message.delta', content: '半截输出', event_index: 1, sequence: null }), options)
    applyAgentRunEvent(state, event({
      event: 'run.paused',
      event_index: 2,
      sequence: null,
      data: {
        requirement: {
          id: 'req-1',
          kind: 'confirmation',
          run_id: 'run-1',
          session_id: 'session-1',
          tool_name: 'apply_page_edits',
          tool_execution: {
            tool_name: 'apply_page_edits',
            tool_call_id: 'call-1',
            requires_confirmation: true,
            tool_args: { note: '写入页面' },
          },
          suggested_patch: null,
          user_feedback_schema: [],
          note: null,
        },
      },
    }), options)

    expect(state.timelineItems.find(item => item.kind === 'message')?.content).toBe('半截输出')
    expect(state.activeRun?.status).toBe('paused')
    expect(state.activeRun?.event_index).toBe(2)
    expect(state.pendingRequirement).toEqual(expect.objectContaining({
      id: 'req-1',
      tool_name: 'apply_page_edits',
    }))
  })

  it('平台 model.request.started 应显示等待智能体输出提示并在工具开始后清理', () => {
    const state = createAgentSessionRuntimeState()
    const options = { agentId: 'agent-coordinator', agentDisplayName: '内容助手' }

    applyAgentRunEvent(state, event({ event: 'run.started', event_index: 0, sequence: null }), options)
    applyAgentRunEvent(state, event({ event: 'model.request.started', event_index: 1, sequence: null }), options)

    const requestStatus = state.timelineItems.find(item => item.kind === 'run_status')
    expect(requestStatus).toEqual(expect.objectContaining({
      status: 'model_request',
      content: '等待智能体输出中',
    }))
    expect(state.activeRun?.status).toBe('running')

    applyAgentRunEvent(state, event({ event: 'model.request.completed', event_index: 2, sequence: null }), options)
    expect(state.timelineItems.some(item => item.status === 'model_request')).toBe(true)

    applyAgentRunEvent(state, event({
      event: 'tool.started',
      event_index: 3,
      sequence: null,
      data: {
        tool_call_id: 'tool-call-1',
        tool_name: 'list_workspace_render_assets',
        tool_args: { workspace_id: 11 },
      },
    }), options)

    const tools = state.timelineItems.filter(item => item.kind === 'tool')
    expect(state.timelineItems.some(item => item.status === 'model_request')).toBe(false)
    expect(tools).toHaveLength(1)
    expect(tools[0].tool).toEqual(expect.objectContaining({
      tool_call_id: 'tool-call-1',
      tool_name: 'list_workspace_render_assets',
      status: 'running',
      input_payload: { workspace_id: 11 },
    }))
  })

  it('平台 model.request.started 后出现普通文本时应清理等待智能体输出提示', () => {
    const state = createAgentSessionRuntimeState()
    const options = { agentId: 'agent-coordinator', agentDisplayName: '内容助手' }

    applyAgentRunEvent(state, event({ event: 'run.started', event_index: 0, sequence: null }), options)
    applyAgentRunEvent(state, event({ event: 'model.request.started', event_index: 1, sequence: null }), options)
    applyAgentRunEvent(state, event({ event: 'message.delta', content: '先说明当前处理思路。', event_index: 2, sequence: null }), options)

    expect(state.timelineItems.some(item => item.status === 'model_request')).toBe(false)
    expect(state.timelineItems.find(item => item.kind === 'message')?.content).toBe('先说明当前处理思路。')
  })

  it('平台事件在工具参数阶段应显示等待输出并结束思考中状态', () => {
    const state = createAgentSessionRuntimeState()
    const options = { agentId: 'agent-coordinator', agentDisplayName: '内容助手' }

    applyAgentRunEvent(state, event({ event: 'run.started', event_index: 0, sequence: null }), options)
    applyAgentRunEvent(state, event({
      event: 'message.delta',
      content: '',
      data: { reasoning_content: '先判断需要读取资源。' },
      event_index: 1,
      sequence: null,
    }), options)

    expect(state.timelineItems.find(item => item.kind === 'reasoning')).toEqual(expect.objectContaining({
      content: '先判断需要读取资源。',
      status: 'running',
    }))

    applyAgentRunEvent(state, event({
      event: 'model.request.started',
      event_index: 2,
      sequence: null,
    }), options)

    expect(state.timelineItems.find(item => item.kind === 'reasoning')).toEqual(expect.objectContaining({
      content: '先判断需要读取资源。',
      status: null,
    }))
    expect(state.timelineItems.find(item => item.kind === 'run_status')).toEqual(expect.objectContaining({
      status: 'model_request',
      content: '等待智能体输出中',
    }))
    expect(state.timelineItems.some(item => item.kind === 'tool')).toBe(false)

    applyAgentRunEvent(state, event({
      event: 'tool.started',
      event_index: 3,
      sequence: null,
      data: {
        tool_call_id: 'tool-call-args-1',
        tool_name: 'list_workspace_render_assets',
        tool_args: { workspace_id: 11 },
      },
    }), options)

    expect(state.timelineItems.some(item => item.status === 'model_request')).toBe(false)
    expect(state.timelineItems.find(item => item.kind === 'tool')?.tool).toEqual(expect.objectContaining({
      tool_call_id: 'tool-call-args-1',
      tool_name: 'list_workspace_render_assets',
      status: 'running',
      input_payload: { workspace_id: 11 },
    }))
  })

  it('平台 model.request.started 应结束同一 run 内已流出的 reasoning 和正文运行态', () => {
    const state = createAgentSessionRuntimeState()
    const options = { agentId: 'agent-coordinator', agentDisplayName: '内容助手' }

    applyAgentRunEvent(state, event({ event: 'run.started', event_index: 0, sequence: null }), options)
    applyAgentRunEvent(state, event({
      event: 'message.delta',
      content: '',
      data: { reasoning_content: '先判断需要读取资源。' },
      event_index: 1,
      sequence: null,
    }), options)
    applyAgentRunEvent(state, event({
      event: 'message.delta',
      content: '我先检查现有资源。',
      event_index: 2,
      sequence: null,
    }), options)

    expect(state.timelineItems.find(item => item.kind === 'reasoning')).toEqual(expect.objectContaining({
      status: 'running',
    }))
    expect(state.timelineItems.find(item => item.kind === 'message')).toEqual(expect.objectContaining({
      content: '我先检查现有资源。',
      status: 'running',
    }))

    applyAgentRunEvent(state, event({ event: 'model.request.started', event_index: 3, sequence: null }), options)

    expect(state.timelineItems.find(item => item.kind === 'reasoning')).toEqual(expect.objectContaining({
      status: null,
    }))
    expect(state.timelineItems.find(item => item.kind === 'message')).toEqual(expect.objectContaining({
      status: null,
    }))
    expect(state.timelineItems.find(item => item.kind === 'run_status')).toEqual(expect.objectContaining({
      status: 'model_request',
      content: '等待智能体输出中',
    }))
  })

  it('平台 model.request.started 缺少 run/session 时应绑定当前 run 并显示等待提示', () => {
    const state = createAgentSessionRuntimeState()
    const options = { agentId: 'agent-coordinator', agentDisplayName: '内容助手' }

    state.stream.runId = 'run-1'
    state.stream.streaming = true

    applyAgentRunEvent(state, event({
      event: 'model.request.started',
      run_id: null,
      session_id: null,
      event_index: 1,
      sequence: null,
    }), options)

    expect(state.timelineItems).toEqual([
      expect.objectContaining({
        run_id: 'run-1',
        kind: 'run_status',
        status: 'model_request',
        content: '等待智能体输出中',
      }),
    ])
  })

  it('平台 member 事件应进入独立成员运行，不污染父 run 时间线', () => {
    const state = createAgentSessionRuntimeState()
    const options = { agentId: 'agent-coordinator', agentDisplayName: '内容助手' }

    applyAgentRunEvent(state, event({ event: 'run.started', run_id: 'parent-run-1', event_index: 0, sequence: null }), options)
    applyAgentRunEvent(state, event({
      event: 'tool.started',
      run_id: 'parent-run-1',
      event_index: 1,
      sequence: null,
      data: {
        tool_call_id: 'delegate-call-resource',
        tool_name: 'delegate_task_to_member',
        tool_args: { member_id: 'resource-manager', task: '整理资源' },
      },
    }), options)
    applyAgentRunEvent(state, event({
      event: 'member.run.started',
      run_id: 'parent-run-1',
      event_index: 2,
      sequence: null,
      data: {
        member_run_id: 'member-run-1',
        member_agent_id: 'resource-manager',
        member_agent_name: '资源助手',
      },
    }), options)
    applyAgentRunEvent(state, event({
      event: 'member.tool.started',
      run_id: 'parent-run-1',
      event_index: 3,
      sequence: null,
      data: {
        member_run_id: 'member-run-1',
        member_agent_id: 'resource-manager',
        member_agent_name: '资源助手',
        tool_call_id: 'child-tool-list-assets',
        tool_name: 'list_workspace_render_assets',
        tool_args: { workspace_id: 11 },
      },
    }), options)
    applyAgentRunEvent(state, event({
      event: 'member.tool.completed',
      run_id: 'parent-run-1',
      event_index: 4,
      sequence: null,
      data: {
        member_run_id: 'member-run-1',
        member_agent_id: 'resource-manager',
        member_agent_name: '资源助手',
        tool_call_id: 'child-tool-list-assets',
        tool_name: 'list_workspace_render_assets',
        result: { total: 2 },
      },
    }), options)
    applyAgentRunEvent(state, event({
      event: 'member.run.completed',
      run_id: 'parent-run-1',
      content: '资源整理完成。',
      event_index: 5,
      sequence: null,
      data: {
        member_run_id: 'member-run-1',
        member_agent_id: 'resource-manager',
        member_agent_name: '资源助手',
      },
    }), options)

    expect(state.timelineItems.filter(item => item.kind === 'tool').map(item => item.tool?.tool_name)).toEqual([
      'delegate_task_to_member',
    ])
    expect(state.memberRuns).toHaveLength(1)
    expect(state.memberRuns[0]).toEqual(expect.objectContaining({
      parent_run_id: 'parent-run-1',
      run_id: 'member-run-1',
      agent_id: 'resource-manager',
      agent_name: '资源助手',
      status: 'completed',
      delegate_tool_call_id: 'delegate-call-resource',
    }))
    expect(state.memberRuns[0].timeline_items.filter(item => item.kind === 'tool').map(item => item.tool)).toEqual([
      expect.objectContaining({
        tool_call_id: 'child-tool-list-assets',
        tool_name: 'list_workspace_render_assets',
        input_payload: { workspace_id: 11 },
        output_payload: { total: 2 },
      }),
    ])
  })

  it('平台 member model.request.started 应进入成员运行并在子工具开始后清理', () => {
    const state = createAgentSessionRuntimeState()
    const options = { agentId: 'agent-coordinator', agentDisplayName: '内容助手' }

    applyAgentRunEvent(state, event({ event: 'run.started', run_id: 'parent-run-1', event_index: 0, sequence: null }), options)
    applyAgentRunEvent(state, event({
      event: 'member.run.started',
      run_id: 'parent-run-1',
      event_index: 1,
      sequence: null,
      data: {
        member_run_id: 'member-run-1',
        member_agent_id: 'resource-manager',
        member_agent_name: '资源助手',
      },
    }), options)
    applyAgentRunEvent(state, event({
      event: 'member.model.request.started',
      run_id: 'parent-run-1',
      event_index: 2,
      sequence: null,
      data: {
        member_run_id: 'member-run-1',
        member_agent_id: 'resource-manager',
        member_agent_name: '资源助手',
      },
    }), options)

    expect(state.memberRuns).toHaveLength(1)
    expect(state.memberRuns[0].timeline_items.find(item => item.kind === 'run_status')).toEqual(expect.objectContaining({
      status: 'model_request',
      content: '等待智能体输出中',
    }))

    applyAgentRunEvent(state, event({
      event: 'member.tool.started',
      run_id: 'parent-run-1',
      event_index: 3,
      sequence: null,
      data: {
        member_run_id: 'member-run-1',
        member_agent_id: 'resource-manager',
        member_agent_name: '资源助手',
        tool_call_id: 'child-tool-list-assets',
        tool_name: 'list_workspace_render_assets',
        tool_args: { workspace_id: 11 },
      },
    }), options)

    const memberTimeline = state.memberRuns[0].timeline_items
    expect(memberTimeline.some(item => item.status === 'model_request')).toBe(false)
    expect(memberTimeline.filter(item => item.kind === 'tool').map(item => item.tool)).toEqual([
      expect.objectContaining({
        tool_call_id: 'child-tool-list-assets',
        tool_name: 'list_workspace_render_assets',
        status: 'running',
        input_payload: { workspace_id: 11 },
      }),
    ])
  })
})
