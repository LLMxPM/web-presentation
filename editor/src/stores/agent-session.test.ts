/**
 * 文件功能：验证 Agent Store 的会话隔离、快照与事件收敛及单次刷新通知。
 */
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useAgentSessionStore } from '@/stores/agent-session'
import type {
  AgentActiveRunItem,
  AgentPendingRequirement,
  AgentRunEvent,
  AgentSessionItem,
  AgentSessionRuntimeSnapshot,
  AgentTimelineItem,
} from '@/types/api'

/** 创建指定会话的活跃 Run 夹具。 */
function run(sessionId: string, status: AgentActiveRunItem['status'], requirement: AgentPendingRequirement | null = null): AgentActiveRunItem {
  return {
    run_id: `run-${sessionId}`,
    session_id: sessionId,
    agent_id: 'agent-coordinator',
    status,
    focus: { scope_type: 'workspace', workspace_id: 1, source: 'test' },
    work_scope_mode: 'workspace',
    allowed_project_ids: [],
    focus_version: 0,
    pending_requirement: requirement,
    content: null,
    created_at: null,
    event_index: 4,
  }
}

/** 创建包含一条服务端消息的运行态快照。 */
function snapshot(sessionId: string, activeRun: AgentActiveRunItem): AgentSessionRuntimeSnapshot {
  return {
    session: { session_id: sessionId } as AgentSessionItem,
    timeline_items: [{
      id: `message-${sessionId}`,
      session_id: sessionId,
      run_id: activeRun.run_id,
      kind: 'message',
      role: 'user',
      event_index: 3,
      order_index: 3,
      content: `服务端-${sessionId}`,
      status: null,
      tool: null,
      source: 'message',
      created_at: null,
    } satisfies AgentTimelineItem],
    context_status: {} as AgentSessionRuntimeSnapshot['context_status'],
    active_run: activeRun,
    last_run: null,
    pending_requirement: activeRun.pending_requirement,
    event_index: 4,
    pending_attachments: [],
  }
}

/** 创建带服务端游标的 SSE 事件。 */
function event(sessionId: string, index: number, content: string): AgentRunEvent {
  return {
    event: 'message.delta',
    session_id: sessionId,
    run_id: `run-${sessionId}`,
    event_index: index,
    content,
    data: {},
  }
}

describe('agent-session store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('两个会话交错接收快照和 SSE 时仅修改目标会话，并忽略重复事件', () => {
    const store = useAgentSessionStore()
    const requirement: AgentPendingRequirement = {
      id: 'requirement-a',
      kind: 'confirmation',
      run_id: 'run-a',
      session_id: 'a',
      tool_name: 'update_entity',
      tool_execution: {},
      suggested_patch: null,
      user_feedback_schema: [],
      note: null,
    }
    store.applyRuntimeSnapshot('a', snapshot('a', run('a', 'paused', requirement)))
    store.applyRuntimeSnapshot('b', snapshot('b', run('b', 'running')))
    const options = { agentId: 'agent-coordinator', agentDisplayName: '内容助手' }

    expect(store.applyRunEvent('b', event('b', 5, '增量'), options).applied).toBe(true)
    expect(store.applyRunEvent('b', event('b', 5, '重复'), options).applied).toBe(false)
    expect(store.getSession('a')?.runtime.activeRun?.pending_requirement?.id).toBe('requirement-a')
    expect(store.getSession('a')?.runtime.timelineItems.map(item => item.content)).toContain('服务端-a')
    expect(store.getSession('b')?.runtime.timelineItems.some(item => item.content?.includes('增量'))).toBe(true)
    expect(store.getSession('b')?.runtime.timelineItems.some(item => item.content?.includes('重复'))).toBe(false)
  })

  it('显式清空 paused requirement 后，后续 running 状态不会恢复旧要求', () => {
    const store = useAgentSessionStore()
    const requirement: AgentPendingRequirement = {
      id: 'requirement-a',
      kind: 'user_feedback',
      run_id: 'run-a',
      session_id: 'a',
      tool_name: 'ask_user',
      tool_execution: {},
      suggested_patch: null,
      user_feedback_schema: [],
      note: null,
    }
    store.setActiveRun('a', run('a', 'paused', requirement))
    store.setPendingRequirement('a', null)
    expect(store.getSession('a')?.runtime.activeRun?.pending_requirement).toBeNull()

    store.setActiveRun('a', run('a', 'running', requirement))
    expect(store.getSession('a')?.runtime.activeRun?.pending_requirement).toBeNull()
    expect(store.getSession('b')).toBeNull()
  })

  it('非 paused 时拒绝挂载 requirement，paused 时才允许写入', () => {
    const store = useAgentSessionStore()
    const requirement: AgentPendingRequirement = {
      id: 'requirement-a',
      kind: 'confirmation',
      run_id: 'run-a',
      session_id: 'a',
      tool_name: 'update_entity',
      tool_execution: {},
      suggested_patch: null,
      user_feedback_schema: [],
      note: null,
    }

    store.setActiveRun('a', run('a', 'running'))
    store.setPendingRequirement('a', requirement)
    expect(store.getSession('a')?.runtime.activeRun?.pending_requirement).toBeNull()

    store.setActiveRun('a', run('a', 'paused'))
    store.setPendingRequirement('a', requirement)
    expect(store.getSession('a')?.runtime.activeRun?.pending_requirement?.id).toBe('requirement-a')
  })

  it('交互状态按会话隔离，领域刷新事件只取出一次', () => {
    const store = useAgentSessionStore()
    store.setImageUploading('a', true)
    store.setInterrupting('b', true)
    store.appendMutationRefreshEvents('a', [{
      kind: 'page',
      workspaceId: 1,
      projectId: 2,
      pageId: 3,
      componentId: null,
      toolName: 'update_entity',
      result: { success: true },
    }])
    expect(store.getSession('a')?.ui.imageUploading).toBe(true)
    expect(store.getSession('a')?.ui.interrupting).toBe(false)
    expect(store.getSession('b')?.ui.interrupting).toBe(true)
    expect(store.drainMutationRefreshEvents('a')).toHaveLength(1)
    expect(store.drainMutationRefreshEvents('a')).toEqual([])
  })
})
