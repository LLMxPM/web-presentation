/**
 * 文件功能：验证智能体 run 事件状态机的去重、旧 run 隔离与暂停/终态收敛。
 */
import { describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { applyAgentRunEvent, applyAgentRuntimeSnapshot, createAgentSessionRuntimeState } from '@/components/agent/agent-run-state'
import { useAgentSessionStore } from '@/stores/agent-session'
import type { AgentRunEvent } from '@/types/api'

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

describe('agent-run-state', () => {
  it('重复 sequence 不应重复追加 delta', () => {
    const state = createAgentSessionRuntimeState()
    const options = { agentId: 'agent-coordinator', agentDisplayName: '内容助手' }

    applyAgentRunEvent(state, event({ event: 'run.started', sequence: 1 }), options)
    applyAgentRunEvent(state, event({ event: 'message.delta', content: '你好', sequence: 2 }), options)
    applyAgentRunEvent(state, event({ event: 'message.delta', content: '你好', sequence: 2 }), options)

    expect(state.messages.at(-1)?.content).toBe('你好')
  })

  it('旧 run 事件不能污染当前 run', () => {
    const state = createAgentSessionRuntimeState()
    const options = { agentId: 'agent-coordinator', agentDisplayName: '内容助手' }

    applyAgentRunEvent(state, event({ event: 'run.started', run_id: 'run-1', sequence: 1 }), options)
    applyAgentRunEvent(state, event({ event: 'message.delta', run_id: 'run-2', content: '旧消息', sequence: 1 }), options)

    expect(state.messages).toHaveLength(0)
  })

  it('paused 应写入 requirement 并停止 streaming', () => {
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
  })

  it('cancelled 应清理 activeRun 并写入 lastRun', () => {
    const state = createAgentSessionRuntimeState()
    const options = { agentId: 'agent-coordinator', agentDisplayName: '内容助手' }

    applyAgentRunEvent(state, event({ event: 'run.started', sequence: 1 }), options)
    applyAgentRunEvent(state, event({ event: 'run.cancelled', sequence: 2 }), options)

    expect(state.activeRun).toBeNull()
    expect(state.lastRun?.status).toBe('cancelled')
    expect(state.stream.streaming).toBe(false)
  })

  it('cancelling 事件应进入停止中状态并保持订阅', () => {
    const state = createAgentSessionRuntimeState()
    const options = { agentId: 'agent-coordinator', agentDisplayName: '内容助手' }

    applyAgentRunEvent(state, event({ event: 'run.started', sequence: 1 }), options)
    applyAgentRunEvent(state, event({ event: 'run.cancelling', sequence: 2 }), options)

    expect(state.activeRun?.status).toBe('cancelling')
    expect(state.pendingRequirement).toBeNull()
    expect(state.stream.streaming).toBe(true)
  })

  it('工具调用前后的思考片段应分属不同助手消息块', () => {
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
      content: '',
      data: { reasoning_content: '再根据工具结果总结' },
      sequence: 4,
    }), options)

    const assistantMessages = state.messages.filter(message => message.role === 'assistant')
    expect(assistantMessages).toHaveLength(2)
    expect(assistantMessages[0].reasoning_content).toBe('先判断是否需要工具')
    expect(assistantMessages[1].reasoning_content).toBe('再根据工具结果总结')
    expect(state.toolCallDetails[0].assistantMessageId).toBe(assistantMessages[0].id)
  })

  it('run.completed 的聚合 reasoning 不应重复追加已流式展示的思考', () => {
    const state = createAgentSessionRuntimeState()
    const options = { agentId: 'agent-coordinator', agentDisplayName: '内容助手' }

    applyAgentRunEvent(state, event({ event: 'run.started', sequence: 1 }), options)
    applyAgentRunEvent(state, event({
      event: 'message.delta',
      content: '',
      data: { reasoning_content: '先判断用户意图' },
      sequence: 2,
    }), options)
    applyAgentRunEvent(state, event({
      event: 'run.completed',
      data: { reasoning_content: '先判断用户意图' },
      sequence: 3,
    }), options)

    expect(state.messages.at(-1)?.reasoning_content).toBe('先判断用户意图')
  })

  it('缺少 tool_call_id 时 started 和 completed 应合并为同一工具详情', () => {
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

    expect(state.toolCallDetails).toHaveLength(1)
    expect(state.toolCallDetails[0]).toEqual(expect.objectContaining({
      toolCallId: null,
      toolName: 'list_workspace_render_assets',
      status: 'completed',
      inputPayload: { workspace_id: 11 },
      outputPayload: { total: 2 },
    }))
  })

  it('运行中的 runtime 快照不应推进事件游标，避免恢复订阅时跳过回放事件', () => {
    const state = createAgentSessionRuntimeState()

    applyAgentRuntimeSnapshot(state, {
      messages: [
        {
          id: 'user-active',
          run_id: 'run-1',
          role: 'user',
          content: '开始运行',
          reasoning_content: null,
          created_at: '2026-04-18T10:00:00+08:00',
          tool_name: null,
          tool_call_id: null,
          tool_args: null,
          tool_call_error: null,
          attachments: [],
        },
        {
          id: 'assistant-active-stale',
          run_id: 'run-1',
          role: 'assistant',
          content: '运行中快照里的半截内容',
          reasoning_content: null,
          created_at: '2026-04-18T10:00:01+08:00',
          tool_name: null,
          tool_call_id: null,
          tool_args: null,
          tool_call_error: null,
          attachments: [],
        },
      ],
      activeRun: {
        run_id: 'run-1',
        session_id: 'session-1',
        agent_id: 'agent-coordinator',
        status: 'running',
        pending_requirement: null,
        content: null,
        created_at: '2026-04-18T10:00:00+08:00',
        event_sequence: 5,
      },
      lastRun: null,
      pendingRequirement: null,
      pendingImageAttachments: [],
      contextStatus: null,
      eventCursor: 5,
    })

    expect(state.stream.lastSequenceByRun['run-1']).toBeUndefined()
    expect(state.stream.streaming).toBe(true)
    expect(state.messages.map(message => message.id)).toEqual(['user-active'])
  })

  it('runtime 快照应恢复历史工具详情并锚定 assistant 消息', () => {
    const state = createAgentSessionRuntimeState()

    applyAgentRuntimeSnapshot(state, {
      messages: [{
        id: 'assistant-1',
        run_id: 'run-1',
        role: 'assistant',
        content: '',
        reasoning_content: null,
        created_at: '2026-04-18T10:00:00+08:00',
        tool_name: null,
        tool_call_id: null,
        tool_args: null,
        tool_call_error: null,
        attachments: [],
      }],
      activeRun: null,
      lastRun: {
        run_id: 'run-1',
        session_id: 'session-1',
        agent_id: 'agent-coordinator',
        status: 'cancelled',
        pending_requirement: null,
        content: null,
        created_at: '2026-04-18T10:00:00+08:00',
        event_sequence: 3,
      },
      pendingRequirement: null,
      pendingImageAttachments: [],
      contextStatus: null,
      eventCursor: 3,
      toolDetails: [{
        id: 'run-1:list_workspace_render_assets:2',
        run_id: 'run-1',
        tool_call_id: null,
        tool_name: 'list_workspace_render_assets',
        member_agent_id: null,
        member_agent_name: null,
        member_run_id: null,
        status: 'completed',
        assistant_message_id: 'assistant-1',
        input_payload: { workspace_id: 1 },
        output_payload: { total: 2 },
        message: '',
        created_at: '2026-04-18T10:00:01+08:00',
      }],
    })

    expect(state.toolCallDetails).toHaveLength(1)
    expect(state.toolCallDetails[0]).toEqual(expect.objectContaining({
      source: 'history',
      assistantMessageId: 'assistant-1',
      inputPayload: { workspace_id: 1 },
      outputPayload: { total: 2 },
    }))
  })

  it('终态 runtime 快照应使用后端工具详情替换同 run 实时工具详情', () => {
    const state = createAgentSessionRuntimeState()
    const options = { agentId: 'agent-coordinator', agentDisplayName: '内容助手' }

    applyAgentRunEvent(state, event({ event: 'run.started', sequence: 1 }), options)
    applyAgentRunEvent(state, event({
      event: 'tool.completed',
      data: { tool_name: 'list_workspace_render_assets', result: { total: 1 } },
      sequence: 2,
    }), options)

    applyAgentRuntimeSnapshot(state, {
      messages: [{
        id: 'assistant-1',
        run_id: 'run-1',
        role: 'assistant',
        content: '已完成。',
        reasoning_content: null,
        created_at: '2026-04-18T10:00:00+08:00',
        tool_name: null,
        tool_call_id: null,
        tool_args: null,
        tool_call_error: null,
        attachments: [],
      }],
      activeRun: null,
      lastRun: {
        run_id: 'run-1',
        session_id: 'session-1',
        agent_id: 'agent-coordinator',
        status: 'completed',
        pending_requirement: null,
        content: null,
        created_at: '2026-04-18T10:00:00+08:00',
        event_sequence: 3,
      },
      pendingRequirement: null,
      pendingImageAttachments: [],
      contextStatus: null,
      eventCursor: 3,
      toolDetails: [{
        id: 'run-1:list_workspace_render_assets:2',
        run_id: 'run-1',
        tool_call_id: null,
        tool_name: 'list_workspace_render_assets',
        member_agent_id: null,
        member_agent_name: null,
        member_run_id: null,
        status: 'completed',
        assistant_message_id: 'assistant-1',
        input_payload: null,
        output_payload: { total: 1 },
        message: '',
        created_at: '2026-04-18T10:00:01+08:00',
      }],
    })

    expect(state.toolCallDetails).toHaveLength(1)
    expect(state.toolCallDetails[0]).toEqual(expect.objectContaining({
      source: 'history',
      runId: 'run-1',
      assistantMessageId: 'assistant-1',
    }))
  })

  it('工具调用后 run.completed 携带纯文本时应创建最终助手消息块', () => {
    const state = createAgentSessionRuntimeState()
    const options = { agentId: 'agent-coordinator', agentDisplayName: '内容助手' }

    applyAgentRunEvent(state, event({ event: 'run.started', sequence: 1 }), options)
    applyAgentRunEvent(state, event({
      event: 'message.delta',
      content: '先检查资源。',
      sequence: 2,
    }), options)
    applyAgentRunEvent(state, event({
      event: 'tool.completed',
      data: { tool_name: 'list_workspace_render_assets', result: { total: 1 } },
      sequence: 3,
    }), options)
    applyAgentRunEvent(state, event({
      event: 'run.completed',
      content: '资源检查完成。',
      sequence: 4,
    }), options)

    const assistantMessages = state.messages.filter(message => message.role === 'assistant')
    expect(assistantMessages).toHaveLength(2)
    expect(assistantMessages[0].content).toBe('先检查资源。')
    expect(assistantMessages[1].content).toBe('资源检查完成。')
  })

  it('取消终态快照暂时为空时应保留本地消息兜底', () => {
    const state = createAgentSessionRuntimeState()
    state.activeRun = {
      run_id: 'run-1',
      session_id: 'session-1',
      agent_id: 'agent-coordinator',
      status: 'cancelling',
      pending_requirement: null,
      content: null,
      created_at: '2026-04-18T10:00:00+08:00',
      event_sequence: 2,
    }
    state.messages = [{
      id: 'local-assistant',
      run_id: null,
      role: 'assistant',
      content: '本地已流出内容',
      reasoning_content: null,
      created_at: '2026-04-18T10:00:01+08:00',
      tool_name: null,
      tool_call_id: null,
      tool_args: null,
      tool_call_error: null,
      attachments: [],
    }]

    applyAgentRuntimeSnapshot(state, {
      messages: [],
      activeRun: null,
      lastRun: {
        run_id: 'run-1',
        session_id: 'session-1',
        agent_id: 'agent-coordinator',
        status: 'cancelled',
        pending_requirement: null,
        content: null,
        created_at: '2026-04-18T10:00:00+08:00',
        event_sequence: 3,
      },
      pendingRequirement: null,
      pendingImageAttachments: [],
      contextStatus: null,
      eventCursor: 3,
      toolDetails: [],
    })

    expect(state.messages[0].content).toBe('本地已流出内容')
    expect(state.lastRun?.status).toBe('cancelled')
  })

  it('取消终态快照暂时为空且本地 run_id 已清理时仍应保留消息', () => {
    const state = createAgentSessionRuntimeState()
    state.messages = [{
      id: 'local-user',
      run_id: null,
      role: 'user',
      content: '刚发送的消息',
      reasoning_content: null,
      created_at: '2026-04-18T10:00:01+08:00',
      tool_name: null,
      tool_call_id: null,
      tool_args: null,
      tool_call_error: null,
      attachments: [],
    }]

    applyAgentRuntimeSnapshot(state, {
      messages: [],
      activeRun: null,
      lastRun: {
        run_id: 'run-unknown-locally',
        session_id: 'session-1',
        agent_id: 'agent-coordinator',
        status: 'cancelled',
        pending_requirement: null,
        content: null,
        created_at: '2026-04-18T10:00:00+08:00',
        event_sequence: 1,
      },
      pendingRequirement: null,
      pendingImageAttachments: [],
      contextStatus: null,
      eventCursor: 1,
      toolDetails: [],
    })

    expect(state.messages[0].content).toBe('刚发送的消息')
    expect(state.lastRun?.run_id).toBe('run-unknown-locally')
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
})
