/**
 * 文件功能：验证智能体 HITL 动作组合逻辑的状态迁移、接口调用和流中断恢复。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAgentHitlActions } from '@/components/agent/agent-hitl-actions'
import type {
  AgentActiveRunItem,
  AgentPendingRequirement,
  AgentRunEvent,
  AgentScopeContext,
} from '@/types/api'

const mocks = vi.hoisted(() => {
  class AgentStreamInterruptedError extends Error {
    constructor() {
      super('智能体流式传输已中断。')
      this.name = 'AgentStreamInterruptedError'
    }
  }
  return {
    AgentStreamInterruptedError,
    continueAgentSessionActiveRun: vi.fn(),
    cancelAgentSessionActiveRun: vi.fn(),
    createConfirm: vi.fn(),
    messageInfo: vi.fn(),
    messageError: vi.fn(),
    logClientWarning: vi.fn(),
  }
})

vi.mock('@/api/ai', () => ({
  AgentStreamInterruptedError: mocks.AgentStreamInterruptedError,
  continueAgentSessionActiveRun: (...args: unknown[]) => mocks.continueAgentSessionActiveRun(...args),
  cancelAgentSessionActiveRun: (...args: unknown[]) => mocks.cancelAgentSessionActiveRun(...args),
}))

vi.mock('@/utils/message', () => ({
  createConfirm: (...args: unknown[]) => mocks.createConfirm(...args),
  Message: {
    info: (...args: unknown[]) => mocks.messageInfo(...args),
    error: (...args: unknown[]) => mocks.messageError(...args),
  },
}))

vi.mock('@/utils/client-logger', () => ({
  logClientWarning: (...args: unknown[]) => mocks.logClientWarning(...args),
}))

const scope: AgentScopeContext = {
  scope_type: 'page',
  workspace_id: 11,
  project_id: 21,
  page_id: 31,
  component_id: null,
  workspace_name: null,
  project_name: null,
  page_title: 'AI 页面',
  component_name: null,
  source: 'editor-page-detail',
}

describe('useAgentHitlActions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('确认继续应清理当前 session 的 requirement，并通过 SSE 继续 paused run', async () => {
    const { actions, calls, controller, requirement } = createHitlFixture()
    const runEvent: AgentRunEvent = {
      event: 'RunCompleted',
      run_id: 'run-1',
      session_id: 'session-1',
      content: '完成',
      data: {},
    }
    mocks.continueAgentSessionActiveRun.mockImplementation(async (...args: unknown[]) => {
      const options = args[3] as { onEvent?: (event: AgentRunEvent) => void }
      options.onEvent?.(runEvent)
    })

    await actions.handleContinueRun('confirm')

    expect(calls.setPendingRequirementForSession).toHaveBeenCalledWith('session-1', null)
    expect(calls.syncActiveRun).toHaveBeenCalledWith('session-1', expect.objectContaining({
      status: 'running',
      pending_requirement: null,
    }))
    expect(mocks.continueAgentSessionActiveRun).toHaveBeenCalledWith(
      'session-1',
      scope,
      expect.objectContaining({
        agent_id: 'agent-coordinator',
        decision: 'confirm',
        tool_execution: requirement.tool_execution,
        feedback_selections: [],
      }),
      expect.objectContaining({ signal: controller.signal }),
    )
    expect(calls.handleRunEvent).toHaveBeenCalledWith(runEvent, 'session-1')
    expect(calls.finalizeRun).toHaveBeenCalledWith('session-1')
    expect(calls.setSessionStreaming).toHaveBeenNthCalledWith(1, 'session-1', true)
    expect(calls.setSessionStreaming).toHaveBeenLastCalledWith('session-1', false)
    expect(calls.setHitlActionInFlight).toHaveBeenLastCalledWith('session-1', false)
  })

  it('结构化提问提交应携带 feedback selections', async () => {
    const { actions } = createHitlFixture({
      requirement: createRequirement({
        kind: 'user_feedback',
        tool_name: 'ask_user',
        tool_execution: {
          tool_name: 'ask_user',
          tool_call_id: 'tool-ask-1',
          requires_user_input: true,
        },
      }),
    })
    mocks.continueAgentSessionActiveRun.mockResolvedValue(undefined)

    await actions.handleSubmitFeedbackRun([
      {
        question: '选择风格？',
        selected_label: '简洁',
        custom_text: null,
      },
    ])

    expect(mocks.continueAgentSessionActiveRun).toHaveBeenCalledWith(
      'session-1',
      scope,
      expect.objectContaining({
        decision: null,
        feedback_selections: [
          {
            question: '选择风格？',
            selected_label: '简洁',
            custom_text: null,
          },
        ],
      }),
      expect.any(Object),
    )
  })

  it('流式中断时应刷新运行状态，不按执行失败展示', async () => {
    const { actions, calls } = createHitlFixture()
    mocks.continueAgentSessionActiveRun.mockRejectedValue(new mocks.AgentStreamInterruptedError())

    await actions.handleContinueRun('confirm')

    expect(calls.refreshAfterStreamInterrupted).toHaveBeenCalledWith('session-1')
    expect(calls.finalizeRun).not.toHaveBeenCalled()
    expect(mocks.messageError).not.toHaveBeenCalled()
    expect(calls.setSessionStreaming).toHaveBeenLastCalledWith('session-1', false)
  })

  it('强制释放应提交当前 requirement 的 tool_call_id 并收敛本地 run', async () => {
    const { actions, calls } = createHitlFixture()
    mocks.createConfirm.mockResolvedValue(true)
    mocks.cancelAgentSessionActiveRun.mockResolvedValue({
      run_id: 'run-1',
      session_id: 'session-1',
      cancel_requested: true,
    })

    await actions.handleForceReleaseHitl()

    expect(mocks.cancelAgentSessionActiveRun).toHaveBeenCalledWith('session-1', scope, {
      agent_id: 'agent-coordinator',
      force: true,
      tool_call_id: 'tool-confirm-1',
    })
    expect(calls.setPendingRequirementForSession).toHaveBeenCalledWith('session-1', null)
    expect(calls.syncActiveRun).toHaveBeenCalledWith('session-1', expect.objectContaining({
      status: 'cancelled',
      pending_requirement: null,
    }))
    expect(calls.finalizeRun).toHaveBeenCalledWith('session-1', { preserveLocalCancelled: true })
    expect(mocks.messageInfo).toHaveBeenCalledWith('已释放当前待处理动作。')
  })
})

function createHitlFixture(options: { requirement?: AgentPendingRequirement } = {}) {
  const requirement = options.requirement ?? createRequirement()
  const pausedRun: AgentActiveRunItem = {
    run_id: requirement.run_id,
    session_id: requirement.session_id,
    agent_id: 'agent-coordinator',
    status: 'paused',
    pending_requirement: requirement,
    content: null,
    created_at: '2026-06-19T08:00:00+08:00',
    updated_at: null,
    cancel_requested_at: null,
    event_index: 3,
  }
  const controller = new AbortController()
  const calls = {
    setHitlActionInFlight: vi.fn(),
    setSessionStreaming: vi.fn(),
    syncActiveRun: vi.fn(),
    setPendingRequirementForSession: vi.fn(),
    markPendingRequirementResolved: vi.fn(),
    createStreamAbortController: vi.fn(() => controller),
    clearStreamAbortController: vi.fn(),
    handleRunEvent: vi.fn(),
    finalizeRun: vi.fn().mockResolvedValue(undefined),
    refreshAfterStreamInterrupted: vi.fn(),
  }
  const actions = useAgentHitlActions({
    getActiveSessionId: () => 'session-1',
    getPendingRequirement: () => requirement,
    getActiveRun: () => pausedRun,
    getScope: () => scope,
    getAgentId: () => 'agent-coordinator',
    isDisposed: () => false,
    ...calls,
  })
  return {
    actions,
    calls,
    controller,
    requirement,
  }
}

function createRequirement(overrides: Partial<AgentPendingRequirement> = {}): AgentPendingRequirement {
  return {
    id: 'req-1',
    kind: 'confirmation',
    run_id: 'run-1',
    session_id: 'session-1',
    member_agent_id: null,
    member_agent_name: null,
    member_run_id: null,
    tool_name: 'apply_page_edits',
    tool_execution: {
      tool_name: 'apply_page_edits',
      tool_call_id: 'tool-confirm-1',
      tool_args: { page_id: 31 },
    },
    suggested_patch: null,
    user_feedback_schema: [],
    note: null,
    ...overrides,
  }
}
