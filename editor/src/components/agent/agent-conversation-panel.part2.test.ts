/**
 * 文件功能：验证内容助手面板的流式消息渲染、工具详情与页面写回联动。
 */
import { render, fireEvent, screen, waitFor } from '@testing-library/vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AgentConversationPanel from '@/components/agent/AgentConversationPanel.vue'
import { useAgentSessionStore } from '@/stores/agent-session'
import type { AgentPendingRequirement } from '@/types/api'

const routerPushMock = vi.fn()
const routeMock = {
  fullPath: '/workspaces/11/projects/21/pages/31',
  path: '/workspaces/11/projects/21/pages/31',
}
const listAgentsMock = vi.fn()
const listAgentSessionsMock = vi.fn()
const createAgentSessionMock = vi.fn()
const getAgentSessionMessagesMock = vi.fn()
const getAgentSessionRuntimeMock = vi.fn()
const renameAgentSessionMock = vi.fn()
const getAgentSessionActiveRunMock = vi.fn()
const getAgentSessionContextStatusMock = vi.fn()
const startAgentRunMock = vi.fn()
const streamAgentRunMock = vi.fn()
const streamAgentRunEventsMock = vi.fn()
const streamAgentRunEventsByRunIdMock = vi.fn()
const continueAgentRunMock = vi.fn()
const continueAgentSessionActiveRunMock = vi.fn()
const cancelAgentRunMock = vi.fn()
const cancelAgentSessionActiveRunMock = vi.fn()
const messageSuccessMock = vi.fn()
const messageErrorMock = vi.fn()
const messageInfoMock = vi.fn()
const messageWarningMock = vi.fn()
const createConfirmMock = vi.fn()
const clipboardWriteTextMock = vi.fn()
const DEFAULT_AGENT_ID = 'agent-coordinator'
const DEFAULT_PLACEHOLDER = '描述目标；内容助手会处理页面/项目任务，并按需调用组件或资源助手。'

const { AgentStreamInterruptedErrorMock, AgentRequestErrorMock } = vi.hoisted(() => {
  class AgentStreamInterruptedError extends Error {
    constructor() {
      super('智能体流式传输已中断。')
      this.name = 'AgentStreamInterruptedError'
    }
  }
  class AgentRequestError extends Error {
    code?: string

    constructor(message: string, code?: string) {
      super(message)
      this.name = 'AgentRequestError'
      this.code = code
    }
  }
  return {
    AgentStreamInterruptedErrorMock: AgentStreamInterruptedError,
    AgentRequestErrorMock: AgentRequestError,
  }
})

vi.mock('vue-router', () => ({
  useRoute: () => routeMock,
  useRouter: () => ({
    push: routerPushMock,
  }),
}))

vi.mock('@/api/ai', () => ({
  AgentStreamInterruptedError: AgentStreamInterruptedErrorMock,
  AgentRequestError: AgentRequestErrorMock,
  listAgents: (...args: unknown[]) => listAgentsMock(...args),
  listAgentSessions: (...args: unknown[]) => listAgentSessionsMock(...args),
  createAgentSession: (...args: unknown[]) => createAgentSessionMock(...args),
  getAgentSessionMessages: (...args: unknown[]) => getAgentSessionMessagesMock(...args),
  getAgentSessionRuntime: (...args: unknown[]) => getAgentSessionRuntimeMock(...args),
  renameAgentSession: (...args: unknown[]) => renameAgentSessionMock(...args),
  getAgentSessionActiveRun: (...args: unknown[]) => getAgentSessionActiveRunMock(...args),
  getAgentSessionContextStatus: (...args: unknown[]) => getAgentSessionContextStatusMock(...args),
  startAgentRun: (...args: unknown[]) => startAgentRunMock(...args),
  streamAgentRun: (...args: unknown[]) => streamAgentRunMock(...args),
  streamAgentRunEvents: (...args: unknown[]) => streamAgentRunEventsMock(...args),
  streamAgentRunEventsByRunId: (...args: unknown[]) => streamAgentRunEventsByRunIdMock(...args),
  continueAgentRun: (...args: unknown[]) => continueAgentRunMock(...args),
  continueAgentSessionActiveRun: (...args: unknown[]) => continueAgentSessionActiveRunMock(...args),
  cancelAgentRun: (...args: unknown[]) => cancelAgentRunMock(...args),
  cancelAgentSessionActiveRun: (...args: unknown[]) => cancelAgentSessionActiveRunMock(...args),
}))

vi.mock('@/utils/message', () => ({
  createConfirm: (...args: unknown[]) => createConfirmMock(...args),
  Message: {
    success: (...args: unknown[]) => messageSuccessMock(...args),
    error: (...args: unknown[]) => messageErrorMock(...args),
    info: (...args: unknown[]) => messageInfoMock(...args),
    warning: (...args: unknown[]) => messageWarningMock(...args),
  },
}))

function createTestingRenderOptions(props?: Record<string, unknown>, pinia: Pinia = createPinia()) {
  const resolvedProps = {
    workspaceId: 11,
    projectId: 21,
    pageId: 31,
    pageTitle: 'AI 页面',
    ...props,
  }
  routeMock.fullPath = buildTestingRoutePath(resolvedProps)
  routeMock.path = routeMock.fullPath.split('?')[0]

  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return {
    props: resolvedProps,
    global: {
      plugins: [
        pinia,
        [VueQueryPlugin, { queryClient }] as [typeof VueQueryPlugin, { queryClient: QueryClient }],
      ],
      stubs: {
        teleport: true,
      },
    },
  }
}

function buildTestingRoutePath(props: Record<string, unknown>) {
  const workspaceId = Number(props.workspaceId ?? 11)
  const projectId = props.projectId === null ? null : Number(props.projectId ?? 21)
  const pageId = props.pageId === null ? null : Number(props.pageId ?? 31)
  if (projectId && pageId) {
    return `/workspaces/${workspaceId}/projects/${projectId}/pages/${pageId}`
  }
  if (projectId) {
    return `/workspaces/${workspaceId}/projects/${projectId}/pages`
  }
  return `/workspaces/${workspaceId}/home`
}

/**
 * 构造 runtime 快照，组件刷新和切换会话时只依赖该快照恢复运行态。
 */
function createRuntimeSnapshot(overrides: Record<string, unknown> = {}) {
  const { messages, timeline_items: timelineItems, ...restOverrides } = overrides
  return {
    session: {
      session_id: 'session-1',
      agent_id: DEFAULT_AGENT_ID,
      session_name: 'AI 页面 会话',
      created_at: '2026-04-18T10:00:00+08:00',
      updated_at: '2026-04-18T10:00:00+08:00',
      metadata: {
        scope_type: 'page',
        workspace_id: 11,
        project_id: 21,
        page_id: 31,
        page_title: 'AI 页面',
        source: 'editor-page-detail',
      },
    },
    timeline_items: Array.isArray(timelineItems)
      ? timelineItems
      : Array.isArray(messages)
        ? timelineFromMessages(messages)
        : [],
    member_runs: [],
    context_status: createContextStatus(),
    active_run: null,
    last_run: null,
    pending_requirement: null,
    event_index: -1,
    pending_attachments: [],
    ...restOverrides,
  }
}

/**
 * 兼容旧测试数据写法，把消息数组转换成 runtime timeline 响应。
 */
function timelineFromMessages(messages: any[]) {
  return messages.map((message, index) => {
    if (message.role === 'tool') {
      return {
        id: message.id,
        session_id: 'session-1',
        run_id: message.run_id ?? 'run-1',
        kind: 'tool',
        role: null,
        event_index: null,
        order_index: index,
        content: null,
        status: message.tool_call_error ? 'error' : 'completed',
        tool: {
          tool_call_id: message.tool_call_id ?? null,
          tool_name: message.tool_name || '工具调用',
          status: message.tool_call_error ? 'error' : 'completed',
          input_payload: message.tool_args ?? null,
          output_payload: parseMaybeJson(message.content),
          message: message.tool_call_error || '',
        },
        source: 'message',
        created_at: message.created_at ?? null,
      }
    }
    return {
      id: message.id,
      session_id: 'session-1',
      run_id: message.run_id ?? 'run-1',
      kind: message.reasoning_content ? 'reasoning' : 'message',
      role: message.reasoning_content ? null : message.role,
      event_index: null,
      order_index: index,
      content: message.reasoning_content || message.content || '',
      status: null,
      tool: null,
      source: 'message',
      created_at: message.created_at ?? null,
    }
  })
}

function parseMaybeJson(value: unknown) {
  if (typeof value !== 'string') {
    return value
  }
  try {
    return JSON.parse(value)
  } catch {
    return value
  }
}

/**
 * 返回测试使用的默认上下文预算状态。
 */
function createContextStatus(overrides: Record<string, unknown> = {}) {
  return {
    session_id: 'session-1',
    agent_id: DEFAULT_AGENT_ID,
    compression_enabled: true,
    compression_required: false,
    summary_available: false,
    summary: null,
    topics: [],
    summary_updated_at: null,
    context_window_tokens: 128000,
    max_output_tokens: 32000,
    history_token_ratio: 0.5,
    compression_target_ratio: 0.1,
    safety_margin_tokens: 10240,
    current_input_tokens: 0,
    fixed_context_tokens: 1000,
    history_budget_tokens: 64000,
    compression_target_tokens: 12800,
    estimated_history_tokens: 0,
    retained_recent_history_tokens: 0,
    retained_recent_message_count: 0,
    ...overrides,
  }
}

/**
 * 模拟内容助手在当前路由只是不允许启动，而不是模型绑定异常。
 */
function mockContentAgentRouteUnavailable() {
  listAgentsMock.mockResolvedValueOnce([
    {
      id: DEFAULT_AGENT_ID,
      name: '内容助手',
      icon: 'content-spark',
      summary: '按当前上下文申请并使用可用工具。',
      default_session_name: '内容助手会话',
      capabilities: ['组件依赖分析'],
      available: false,
      unavailable_reason: '内容助手需要进入具体项目后才能启动。',
      llm_slot: 'agent_coordinator',
      llm_binding_ready: true,
      bound_llm_name: '页面编辑模型',
      bound_provider_label: 'OpenAI',
      scope: {
        workspace_id: 11,
        project_id: null,
        page_id: null,
        source: 'editor-agent-sidebar',
      },
    },
  ])
}

/**
 * 构造可手动释放的 Promise，方便测试工具完成和 run 完成之间的即时刷新时机。
 */
function createDeferred<T = void>() {
  let resolve!: (value: T | PromiseLike<T>) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((nextResolve, nextReject) => {
    resolve = nextResolve
    reject = nextReject
  })
  return { promise, resolve, reject }
}

describe('AgentConversationPanel', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    localStorage.clear()
    routerPushMock.mockReset()
    createConfirmMock.mockResolvedValue(true)
    clipboardWriteTextMock.mockResolvedValue(undefined)
    Object.defineProperty(window.navigator, 'clipboard', {
      value: {
        writeText: clipboardWriteTextMock,
      },
      configurable: true,
    })
    listAgentsMock.mockResolvedValue([
      {
        id: DEFAULT_AGENT_ID,
        name: '内容助手',
        icon: 'content-spark',
        summary: '按当前上下文申请并使用可用工具。',
        default_session_name: '内容助手会话',
        capabilities: ['组件依赖分析'],
        llm_slot: 'agent_coordinator',
        llm_binding_ready: true,
        bound_llm_name: '页面编辑模型',
        bound_provider_label: 'OpenAI',
        scope: {
          workspace_id: 11,
          project_id: 21,
          page_id: 31,
          source: 'editor-page-detail',
        },
      },
    ])
    listAgentSessionsMock.mockResolvedValue([])
    createAgentSessionMock.mockResolvedValue({
      session_id: 'session-1',
      agent_id: DEFAULT_AGENT_ID,
      session_name: 'AI 页面 会话',
      created_at: '2026-04-18T10:00:00+08:00',
      updated_at: '2026-04-18T10:00:00+08:00',
      metadata: {
        workspace_id: 11,
        project_id: 21,
        page_id: 31,
        source: 'editor-page-detail',
      },
    })
    getAgentSessionMessagesMock.mockResolvedValue([])
    getAgentSessionActiveRunMock.mockResolvedValue(null)
    getAgentSessionContextStatusMock.mockResolvedValue({
      session_id: 'session-1',
      agent_id: DEFAULT_AGENT_ID,
      compression_enabled: true,
      compression_required: false,
      summary_available: false,
      summary: null,
      topics: [],
      summary_updated_at: null,
      context_window_tokens: 128000,
      max_output_tokens: 32000,
      history_token_ratio: 0.5,
      compression_target_ratio: 0.1,
      safety_margin_tokens: 10240,
      current_input_tokens: 0,
      fixed_context_tokens: 1000,
      history_budget_tokens: 64000,
      compression_target_tokens: 12800,
      estimated_history_tokens: 0,
      retained_recent_history_tokens: 0,
      retained_recent_message_count: 0,
    })
    getAgentSessionRuntimeMock.mockResolvedValue({
      session: {
        session_id: 'session-1',
        agent_id: DEFAULT_AGENT_ID,
        session_name: 'AI 页面 会话',
        created_at: '2026-04-18T10:00:00+08:00',
        updated_at: '2026-04-18T10:00:00+08:00',
        metadata: {
          workspace_id: 11,
          project_id: 21,
          page_id: 31,
          source: 'editor-page-detail',
        },
      },
      timeline_items: [],
      member_runs: [],
      context_status: {
        session_id: 'session-1',
        agent_id: DEFAULT_AGENT_ID,
        compression_enabled: true,
        compression_required: false,
        summary_available: false,
        summary: null,
        topics: [],
        summary_updated_at: null,
        context_window_tokens: 128000,
        max_output_tokens: 32000,
        history_token_ratio: 0.5,
        compression_target_ratio: 0.1,
        safety_margin_tokens: 10240,
        current_input_tokens: 0,
        fixed_context_tokens: 1000,
        history_budget_tokens: 64000,
        compression_target_tokens: 12800,
        estimated_history_tokens: 0,
        retained_recent_history_tokens: 0,
        retained_recent_message_count: 0,
      },
      active_run: null,
      last_run: null,
      pending_requirement: null,
      event_index: -1,
      pending_attachments: [],
    })
    renameAgentSessionMock.mockResolvedValue({
      session_id: 'session-1',
      agent_id: DEFAULT_AGENT_ID,
      session_name: '自动命名后的会话',
      created_at: '2026-04-18T10:00:00+08:00',
      updated_at: '2026-04-18T10:05:00+08:00',
      metadata: {
        workspace_id: 11,
        project_id: 21,
        page_id: 31,
        source: 'editor-page-detail',
      },
    })
    continueAgentSessionActiveRunMock.mockResolvedValue(undefined)
    continueAgentRunMock.mockResolvedValue({
      run_id: 'run-1',
      session_id: 'session-1',
      status: 'pending',
      event_index: -1,
    })
    cancelAgentSessionActiveRunMock.mockResolvedValue({
      run_id: 'run-1',
      session_id: 'session-1',
      cancel_requested: true,
    })
    cancelAgentRunMock.mockResolvedValue({
      run_id: 'run-1',
      session_id: 'session-1',
      cancel_requested: true,
    })
    startAgentRunMock.mockResolvedValue({
      run_id: 'run-1',
      session_id: 'session-1',
      status: 'pending',
      event_index: -1,
    })
    streamAgentRunEventsByRunIdMock.mockImplementation(async (_runId: string, _payload: unknown, options?: { onEvent?: (event: any) => void }) => {
      options?.onEvent?.({ event: 'run.started', run_id: 'run-1', session_id: 'session-1', content: null, data: {} })
      options?.onEvent?.({ event: 'message.delta', run_id: 'run-1', session_id: 'session-1', content: '先读取页面依赖。', data: {} })
      options?.onEvent?.({
        event: 'tool.completed',
        run_id: 'run-1',
        session_id: 'session-1',
        content: null,
        data: {
          tool_call_id: 'tool-1',
          tool_name: 'apply_page_edits',
          result: {
            success: true,
            message: '页面代码已更新并生成新版本。',
            page_code: 'PG001',
            version_no: 2,
            edits_applied: 1,
          },
        },
      })
      options?.onEvent?.({
        event: 'run.completed',
        run_id: 'run-1',
        session_id: 'session-1',
        content: '页面已按要求完成改写。',
        data: {},
      })
    })
    streamAgentRunEventsByRunIdMock.mockImplementation(async (_runId: string, _payload: unknown, options?: { onEvent?: (event: any) => void }) => {
      options?.onEvent?.({ event: 'run.started', run_id: 'run-1', session_id: 'session-1', content: null, data: {}, sequence: 1 })
      options?.onEvent?.({ event: 'message.delta', run_id: 'run-1', session_id: 'session-1', content: '先读取页面依赖。', data: {}, sequence: 2 })
      options?.onEvent?.({
        event: 'tool.completed',
        run_id: 'run-1',
        session_id: 'session-1',
        content: null,
        sequence: 3,
        data: {
          tool_call_id: 'tool-1',
          tool_name: 'apply_page_edits',
          result: {
            success: true,
            message: '页面代码已更新并生成新版本。',
            page_code: 'PG001',
            version_no: 2,
            edits_applied: 1,
          },
        },
      })
      options?.onEvent?.({
        event: 'run.completed',
        run_id: 'run-1',
        session_id: 'session-1',
        content: '页面已按要求完成改写。',
        data: {},
        sequence: 4,
      })
    })
    streamAgentRunMock.mockImplementation(async (sessionId: string, scope: unknown, payload: { run_id?: string }, options?: { onEvent?: (event: any) => void, signal?: AbortSignal }) => {
      startAgentRunMock(sessionId, scope, payload)
      await streamAgentRunEventsByRunIdMock(payload?.run_id ?? 'run-1', { after_sequence: -1 }, options)
    })
    streamAgentRunEventsMock.mockImplementation(async (_sessionId: string, runId: string, _scope: unknown, payload: { event_index?: number }, options?: { onEvent?: (event: any) => void, signal?: AbortSignal }) => {
      await streamAgentRunEventsByRunIdMock(runId, { after_sequence: payload?.event_index ?? -1 }, options)
    })
  })

  it('应通过新会话按钮旁的下拉菜单切换历史会话', async () => {
    localStorage.setItem('agent-session:agent-coordinator:11', 'session-1')
    listAgentSessionsMock.mockResolvedValueOnce([
      {
        session_id: 'session-1',
        agent_id: DEFAULT_AGENT_ID,
        session_name: '视觉优化讨论',
        created_at: '2026-04-18T10:00:00+08:00',
        updated_at: '2026-04-18T10:30:00+08:00',
        metadata: {
          scope_type: 'page',
          workspace_id: 11,
          project_id: 21,
          page_id: 31,
          page_title: 'AI 页面',
          source: 'editor-page-detail',
        },
      },
      {
        session_id: 'session-2',
        agent_id: DEFAULT_AGENT_ID,
        session_name: '素材排查记录',
        created_at: '2026-04-18T09:00:00+08:00',
        updated_at: '2026-04-18T09:10:00+08:00',
        metadata: {
          scope_type: 'page',
          workspace_id: 11,
          project_id: 21,
          page_id: 41,
          page_title: '素材页面',
          source: 'editor-page-detail',
        },
      },
    ])
    const currentSessionMessages = [
      {
        id: 'message-session-1',
        role: 'assistant',
        content: '这是当前会话的摘要。',
        created_at: '2026-04-18T10:30:00+08:00',
        tool_name: null,
        tool_call_id: null,
        tool_args: null,
        tool_call_error: null,
      },
    ]
    getAgentSessionMessagesMock.mockResolvedValue(currentSessionMessages)
    getAgentSessionRuntimeMock.mockResolvedValue(createRuntimeSnapshot({
      messages: currentSessionMessages,
    }))

    render(AgentConversationPanel, createTestingRenderOptions())

    await waitFor(() => {
      expect(screen.getByText('这是当前会话的摘要。')).toBeTruthy()
    })

    expect(screen.queryByText('会话列表')).toBeNull()
    await fireEvent.click(screen.getByRole('button', { name: '切换会话' }))

    await waitFor(() => {
      expect(screen.getByText(/素材排查记录/)).toBeTruthy()
    })

    await fireEvent.click(screen.getByRole('button', { name: /素材排查记录/ }))

    expect(localStorage.getItem('agent-session:v2:agent-coordinator:page:11:21:41::editor-page-detail')).toBe('session-2')
    expect(routerPushMock).toHaveBeenCalledWith('/workspaces/11/projects/21/pages/41')
  })

  it('手动新会话应先进入虚拟空白态，首条消息再实际创建', async () => {
    localStorage.setItem('agent-session:agent-coordinator:11', 'session-1')
    listAgentSessionsMock.mockResolvedValueOnce([
      {
        session_id: 'session-1',
        agent_id: DEFAULT_AGENT_ID,
        session_name: '旧会话',
        created_at: '2026-04-18T10:00:00+08:00',
        updated_at: '2026-04-18T10:30:00+08:00',
        metadata: {
          scope_type: 'page',
          workspace_id: 11,
          project_id: 21,
          page_id: 31,
          page_title: 'AI 页面',
          source: 'editor-page-detail',
        },
      },
    ])
    const oldSessionMessages = [
      {
        id: 'old-message',
        role: 'assistant',
        content: '旧会话内容',
        created_at: '2026-04-18T10:30:00+08:00',
        tool_name: null,
        tool_call_id: null,
        tool_args: null,
        tool_call_error: null,
      },
    ]
    getAgentSessionMessagesMock.mockResolvedValueOnce(oldSessionMessages)
    getAgentSessionRuntimeMock.mockResolvedValueOnce(createRuntimeSnapshot({
      messages: oldSessionMessages,
    }))
    createAgentSessionMock.mockResolvedValueOnce({
      session_id: 'manual-session',
      agent_id: DEFAULT_AGENT_ID,
      session_name: 'AI 页面 会话',
      created_at: '2026-04-18T10:40:00+08:00',
      updated_at: '2026-04-18T10:40:00+08:00',
      metadata: {
        scope_type: 'page',
        workspace_id: 11,
        project_id: 21,
        page_id: 31,
        page_title: 'AI 页面',
        source: 'editor-page-detail',
      },
    })

    render(AgentConversationPanel, createTestingRenderOptions())

    await waitFor(() => {
      expect(screen.getByText('旧会话内容')).toBeTruthy()
    })
    await fireEvent.click(screen.getByRole('button', { name: '新会话' }))

    expect(createAgentSessionMock).not.toHaveBeenCalled()
    expect(screen.queryByText('旧会话内容')).toBeNull()

    await fireEvent.update(screen.getByPlaceholderText(DEFAULT_PLACEHOLDER), '开启新讨论')
    await fireEvent.click(screen.getByRole('button', { name: /发送/ }))

    await waitFor(() => {
      expect(createAgentSessionMock).toHaveBeenCalledWith({
        agent_id: DEFAULT_AGENT_ID,
        scope: expect.objectContaining({
          scope_type: 'page',
          workspace_id: 11,
          project_id: 21,
          page_id: 31,
        }),
        session_name: 'AI 页面 会话',
      })
    })
    await waitFor(() => {
      expect(startAgentRunMock).toHaveBeenCalledWith(
        'manual-session',
        expect.objectContaining({ page_id: 31 }),
        expect.objectContaining({
          message: '开启新讨论',
          agent_id: DEFAULT_AGENT_ID,
        }),
      )
      expect(streamAgentRunEventsByRunIdMock).toHaveBeenCalled()
    })
  })

  it('快速重复触发送出动作时只应创建一个会话和一个 run', async () => {
    let resolveCreateSession!: () => void
    createAgentSessionMock.mockImplementationOnce(() => new Promise((resolve) => {
      resolveCreateSession = () => resolve({
        session_id: 'dedupe-session',
        agent_id: DEFAULT_AGENT_ID,
        session_name: 'AI 页面 会话',
        created_at: '2026-04-18T10:40:00+08:00',
        updated_at: '2026-04-18T10:40:00+08:00',
        metadata: {
          scope_type: 'page',
          workspace_id: 11,
          project_id: 21,
          page_id: 31,
          page_title: 'AI 页面',
          source: 'editor-page-detail',
        },
      })
    }))

    render(AgentConversationPanel, createTestingRenderOptions())

    await waitFor(() => {
      expect(listAgentsMock).toHaveBeenCalled()
    })

    await fireEvent.update(screen.getByPlaceholderText(DEFAULT_PLACEHOLDER), '快速发送一次')
    const sendButton = screen.getByRole('button', { name: /发送/ })
    void fireEvent.click(sendButton)
    await fireEvent.click(sendButton)
    resolveCreateSession()

    await waitFor(() => {
      expect(createAgentSessionMock).toHaveBeenCalledTimes(1)
      expect(startAgentRunMock).toHaveBeenCalledTimes(1)
    })
    expect(startAgentRunMock).toHaveBeenCalledWith(
      'dedupe-session',
      expect.objectContaining({ page_id: 31 }),
      expect.objectContaining({ message: '快速发送一次' }),
    )
  })

  it('切换项目、组件、资源和主题会话时应生成对应路由', async () => {
    listAgentSessionsMock.mockResolvedValueOnce([
      {
        session_id: 'project-session',
        agent_id: DEFAULT_AGENT_ID,
        session_name: '项目会话',
        created_at: '2026-04-18T10:00:00+08:00',
        updated_at: '2026-04-18T10:30:00+08:00',
        metadata: {
          scope_type: 'project',
          workspace_id: 11,
          project_id: 21,
          project_name: '演示项目',
          source: 'editor-agent-sidebar',
        },
      },
      {
        session_id: 'component-scope-session',
        agent_id: DEFAULT_AGENT_ID,
        session_name: '组件详情会话',
        created_at: '2026-04-18T09:00:00+08:00',
        updated_at: '2026-04-18T09:30:00+08:00',
        metadata: {
          scope_type: 'component',
          workspace_id: 11,
          component_id: 99,
          component_name: '销售卡片',
          source: 'editor-component-library',
        },
      },
      {
        session_id: 'component-library-session',
        agent_id: 'component-manager',
        session_name: '组件库会话',
        created_at: '2026-04-18T08:45:00+08:00',
        updated_at: '2026-04-18T09:15:00+08:00',
        metadata: {
          scope_type: 'workspace',
          workspace_id: 11,
          workspace_name: '默认空间',
          source: 'editor-component-library',
        },
      },
      {
        session_id: 'legacy-component-library-session',
        agent_id: 'component-manager',
        session_name: '历史组件助手会话',
        created_at: '2026-04-18T08:35:00+08:00',
        updated_at: '2026-04-18T09:05:00+08:00',
        metadata: {
          scope_type: 'workspace',
          workspace_id: 11,
          workspace_name: '默认空间',
        },
      },
      {
        session_id: 'asset-session',
        agent_id: DEFAULT_AGENT_ID,
        session_name: '资源会话',
        created_at: '2026-04-18T08:00:00+08:00',
        updated_at: '2026-04-18T08:30:00+08:00',
        metadata: {
          scope_type: 'workspace',
          workspace_id: 11,
          workspace_name: '默认空间',
          source: 'editor-asset-library',
        },
      },
      {
        session_id: 'theme-session',
        agent_id: DEFAULT_AGENT_ID,
        session_name: '主题会话',
        created_at: '2026-04-18T07:00:00+08:00',
        updated_at: '2026-04-18T07:30:00+08:00',
        metadata: {
          scope_type: 'workspace',
          workspace_id: 11,
          workspace_name: '默认空间',
          source: 'editor-theme-font-library',
        },
      },
    ])

    render(AgentConversationPanel, createTestingRenderOptions({
      projectId: null,
      pageId: null,
      pageTitle: '',
    }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '切换会话' })).toBeTruthy()
    })

    const expectedRoutes: Array<[RegExp, string]> = [
      [/项目会话/, '/workspaces/11/projects/21/pages'],
      [/组件详情会话/, '/workspaces/11/components'],
      [/组件库会话/, '/workspaces/11/components'],
      [/历史组件助手会话/, '/workspaces/11/components'],
      [/资源会话/, '/workspaces/11/assets'],
      [/主题会话/, '/workspaces/11/themes'],
    ]

    for (const [name, targetRoute] of expectedRoutes) {
      routerPushMock.mockClear()
      await fireEvent.click(screen.getByRole('button', { name: '切换会话' }))
      await fireEvent.click(await screen.findByRole('button', { name }))
      expect(routerPushMock).toHaveBeenCalledWith(targetRoute)
    }
  })

  it('不可启动路由上的助手切换应选中第一个项目会话但不切换路由', async () => {
    mockContentAgentRouteUnavailable()
    listAgentSessionsMock.mockResolvedValueOnce([
      {
        session_id: 'page-session',
        agent_id: DEFAULT_AGENT_ID,
        session_name: '页面会话',
        created_at: '2026-04-18T10:00:00+08:00',
        updated_at: '2026-04-18T10:30:00+08:00',
        metadata: {
          scope_type: 'page',
          workspace_id: 11,
          project_id: 21,
          page_id: 31,
          page_title: '封面页',
          source: 'editor-page-detail',
        },
      },
      {
        session_id: 'workspace-session',
        agent_id: DEFAULT_AGENT_ID,
        session_name: '历史工作空间会话',
        created_at: '2026-04-18T09:00:00+08:00',
        updated_at: '2026-04-18T09:30:00+08:00',
        metadata: {
          scope_type: 'workspace',
          workspace_id: 11,
          source: 'editor-agent-sidebar',
        },
      },
    ])

    render(AgentConversationPanel, createTestingRenderOptions({
      projectId: null,
      pageId: null,
      pageTitle: '',
      routeAvailable: false,
      routeUnavailableReason: '内容助手需要进入具体项目后才能启动。',
      autoCreateKey: 'agent-coordinator:1',
    }))

    await waitFor(() => {
      expect(screen.getByText('当前页面不在此会话工作范围。')).toBeTruthy()
    })
    expect(screen.queryByText('内容助手当前不可用')).toBeNull()
    expect(screen.queryByRole('button', { name: '前往 AI 设置' })).toBeNull()
    expect(routerPushMock).not.toHaveBeenCalled()
    expect(messageWarningMock).not.toHaveBeenCalled()
  })

  it('路由切到不可启动范围时应保留项目会话且不展示助手不可用大卡片', async () => {
    listAgentSessionsMock.mockResolvedValueOnce([
      {
        session_id: 'page-session',
        agent_id: DEFAULT_AGENT_ID,
        session_name: '页面会话',
        created_at: '2026-04-18T10:00:00+08:00',
        updated_at: '2026-04-18T10:30:00+08:00',
        metadata: {
          scope_type: 'page',
          workspace_id: 11,
          project_id: 21,
          page_id: 31,
          page_title: '封面页',
          source: 'editor-page-detail',
        },
      },
    ])

    const { rerender } = render(AgentConversationPanel, createTestingRenderOptions())

    await waitFor(() => {
      expect(listAgentSessionsMock).toHaveBeenCalled()
    })

    mockContentAgentRouteUnavailable()
    routeMock.fullPath = '/workspaces/11/home'
    routeMock.path = '/workspaces/11/home'
    await rerender({
      workspaceId: 11,
      projectId: null,
      pageId: null,
      pageTitle: '',
      routeAvailable: false,
      routeUnavailableReason: '内容助手需要进入具体项目后才能启动。',
    })

    await waitFor(() => {
      expect(screen.getByText('当前页面不在此会话工作范围。')).toBeTruthy()
    })
    expect(screen.queryByText('内容助手当前不可用')).toBeNull()
    expect(screen.queryByRole('button', { name: '前往 AI 设置' })).toBeNull()
    expect(routerPushMock).not.toHaveBeenCalled()
  })

  it('不可启动路由没有项目会话时应展示进入具体项目提示', async () => {
    mockContentAgentRouteUnavailable()
    listAgentSessionsMock.mockResolvedValueOnce([
      {
        session_id: 'workspace-session',
        agent_id: DEFAULT_AGENT_ID,
        session_name: '历史工作空间会话',
        created_at: '2026-04-18T09:00:00+08:00',
        updated_at: '2026-04-18T09:30:00+08:00',
        metadata: {
          scope_type: 'workspace',
          workspace_id: 11,
          source: 'editor-agent-sidebar',
        },
      },
    ])

    render(AgentConversationPanel, createTestingRenderOptions({
      projectId: null,
      pageId: null,
      pageTitle: '',
      routeAvailable: false,
      routeUnavailableReason: '内容助手需要进入具体项目后才能启动。',
      autoCreateKey: 'agent-coordinator:1',
    }))

    await waitFor(() => {
      expect(screen.getByText('内容助手需要进入具体项目后才能启动。')).toBeTruthy()
    })
    expect(screen.queryByText('内容助手当前不可用')).toBeNull()
    expect(routerPushMock).not.toHaveBeenCalled()
  })

  it('助手切换触发的 autoCreateKey 应先进入虚拟会话，首条消息再实际创建', async () => {
    createAgentSessionMock.mockResolvedValueOnce({
      session_id: 'component-auto-session',
      agent_id: 'component-manager',
      session_name: '组件库 会话',
      created_at: '2026-04-18T10:00:00+08:00',
      updated_at: '2026-04-18T10:00:00+08:00',
      metadata: {
        scope_type: 'workspace',
        workspace_id: 11,
        source: 'editor-component-library',
      },
    })

    render(AgentConversationPanel, createTestingRenderOptions({
      agentId: 'component-manager',
      projectId: null,
      pageId: null,
      pageTitle: '',
      contextTitle: '组件库',
      autoCreateKey: 'component-manager:1',
      autoNavigateTarget: '/workspaces/11/components',
      scope: {
        scope_type: 'workspace',
        workspace_id: 11,
        project_id: null,
        page_id: null,
        component_id: null,
        workspace_name: null,
        project_name: null,
        page_title: null,
        component_name: null,
        source: 'editor-component-library',
      },
    }))

    await waitFor(() => {
      expect(routerPushMock).toHaveBeenCalledWith('/workspaces/11/components')
    })
    expect(createAgentSessionMock).not.toHaveBeenCalled()
    expect(localStorage.getItem('agent-session:v2:component-manager:workspace:11::::editor-component-library')).toBeNull()

    await fireEvent.update(screen.getByPlaceholderText(DEFAULT_PLACEHOLDER), '整理组件库')
    await fireEvent.click(screen.getByRole('button', { name: /发送/ }))

    await waitFor(() => {
      expect(createAgentSessionMock).toHaveBeenCalledWith({
        agent_id: 'component-manager',
        scope: expect.objectContaining({
          scope_type: 'workspace',
          workspace_id: 11,
          component_id: null,
          source: 'editor-component-library',
        }),
        session_name: '组件库 会话',
      })
    })
    await waitFor(() => {
      expect(localStorage.getItem('agent-session:v2:component-manager:workspace:11::::editor-component-library')).toBe('component-auto-session')
      expect(startAgentRunMock).toHaveBeenCalledWith(
        'component-auto-session',
        expect.objectContaining({ source: 'editor-component-library' }),
        expect.objectContaining({
          message: '整理组件库',
          agent_id: 'component-manager',
        }),
      )
      expect(streamAgentRunEventsByRunIdMock).toHaveBeenCalled()
    })
  })

  it('应通过输入区圆环展示上下文用量并主动刷新统计', async () => {
    localStorage.setItem('agent-session:agent-coordinator:11', 'session-1')
    listAgentSessionsMock.mockResolvedValueOnce([
      {
        session_id: 'session-1',
        agent_id: DEFAULT_AGENT_ID,
        session_name: '视觉优化讨论',
        created_at: '2026-04-18T10:00:00+08:00',
        updated_at: '2026-04-18T10:30:00+08:00',
        metadata: {
          scope_type: 'page',
          workspace_id: 11,
          project_id: 21,
          page_id: 31,
          page_title: 'AI 页面',
          source: 'editor-page-detail',
        },
      },
    ])
    const summarizedContextStatus = {
      session_id: 'session-1',
      agent_id: DEFAULT_AGENT_ID,
      compression_enabled: true,
      compression_required: true,
      summary_available: true,
      summary: '旧上下文摘要：用户希望优化首页视觉。',
      topics: ['首页视觉'],
      summary_updated_at: '2026-04-18T10:30:00+08:00',
      context_window_tokens: 128000,
      max_output_tokens: 32000,
      history_token_ratio: 0.5,
      compression_target_ratio: 0.1,
      safety_margin_tokens: 10240,
      current_input_tokens: 0,
      fixed_context_tokens: 1000,
      history_budget_tokens: 64000,
      compression_target_tokens: 12800,
      estimated_history_tokens: 66000,
      retained_recent_history_tokens: 10000,
      retained_recent_message_count: 18,
    }
    getAgentSessionContextStatusMock.mockResolvedValueOnce(summarizedContextStatus)
    getAgentSessionRuntimeMock.mockResolvedValueOnce(createRuntimeSnapshot({
      context_status: summarizedContextStatus,
    }))

    const target = document.createElement('div')
    target.id = 'agent-scope-target'
    document.body.appendChild(target)

    render(AgentConversationPanel, createTestingRenderOptions({
      headerScopeTarget: '#agent-scope-target',
    }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '上下文用量' })).toBeTruthy()
    })
    expect(screen.queryByText('旧上下文已摘要')).toBeNull()

    await fireEvent.click(screen.getByRole('button', { name: '上下文用量' }))

    await waitFor(() => {
      expect(getAgentSessionContextStatusMock).toHaveBeenCalledWith(
        'session-1',
        expect.objectContaining({
          workspace_id: 11,
          project_id: 21,
          page_id: 31,
          source: 'editor-page-detail',
        }),
        DEFAULT_AGENT_ID,
      )
    })
    expect(screen.getByRole('dialog', { name: '上下文用量详情' })).toBeTruthy()
    expect(screen.getByText('已用上下文')).toBeTruthy()
    expect(screen.getByText('可用上下文')).toBeTruthy()
    expect(screen.getByText('66 K')).toBeTruthy()
    expect(screen.getByText('64 K')).toBeTruthy()
    expect(screen.queryByText('压缩目标')).toBeNull()
    expect(screen.queryByText('最近原文')).toBeNull()
  })

  it('手动切到其他页面时不应恢复旧页面会话', async () => {
    localStorage.setItem('agent-session:agent-coordinator:11', 'session-1')
    listAgentSessionsMock.mockResolvedValueOnce([
      {
        session_id: 'session-1',
        agent_id: DEFAULT_AGENT_ID,
        session_name: '页面一会话',
        created_at: '2026-04-18T10:00:00+08:00',
        updated_at: '2026-04-18T10:30:00+08:00',
        metadata: {
          scope_type: 'page',
          workspace_id: 11,
          project_id: 21,
          page_id: 31,
          page_title: '页面一',
          source: 'editor-page-detail',
        },
      },
    ])

    render(AgentConversationPanel, createTestingRenderOptions({
      pageId: 32,
      pageTitle: '页面二',
    }))

    await waitFor(() => {
      expect(listAgentSessionsMock).toHaveBeenCalled()
    })

    expect(screen.queryByText('页面一历史仍然可见。')).toBeNull()
    expect(screen.queryByText('当前页面不在此会话工作范围。')).toBeNull()
    expect(getAgentSessionMessagesMock).not.toHaveBeenCalled()
    const textarea = screen.getByPlaceholderText(DEFAULT_PLACEHOLDER) as HTMLTextAreaElement
    expect(textarea.disabled).toBe(false)
  })

  it('路由切换时应保留当前会话并禁用跨范围输入', async () => {
    listAgentSessionsMock.mockResolvedValueOnce([
      {
        session_id: 'session-1',
        agent_id: DEFAULT_AGENT_ID,
        session_name: '页面一会话',
        created_at: '2026-04-18T10:00:00+08:00',
        updated_at: '2026-04-18T10:30:00+08:00',
        metadata: {
          scope_type: 'page',
          workspace_id: 11,
          project_id: 21,
          page_id: 31,
          page_title: '页面一',
          source: 'editor-page-detail',
        },
      },
      {
        session_id: 'session-2',
        agent_id: DEFAULT_AGENT_ID,
        session_name: '页面二会话',
        created_at: '2026-04-18T09:00:00+08:00',
        updated_at: '2026-04-18T09:30:00+08:00',
        metadata: {
          scope_type: 'page',
          workspace_id: 11,
          project_id: 21,
          page_id: 32,
          page_title: '页面二',
          source: 'editor-page-detail',
        },
      },
    ])
    getAgentSessionRuntimeMock.mockResolvedValueOnce(createRuntimeSnapshot({
      messages: [
        {
          id: 'message-session-1',
          role: 'assistant',
          content: '页面一会话内容应继续显示。',
          created_at: '2026-04-18T10:30:00+08:00',
          tool_name: null,
          tool_call_id: null,
          tool_args: null,
          tool_call_error: null,
        },
      ],
    }))

    const { rerender } = render(AgentConversationPanel, createTestingRenderOptions({
      pageId: 31,
      pageTitle: '页面一',
    }))

    await waitFor(() => {
      expect(screen.getByText('页面一会话内容应继续显示。')).toBeTruthy()
    })

    routeMock.fullPath = buildTestingRoutePath({
      workspaceId: 11,
      projectId: 21,
      pageId: 32,
    })
    routeMock.path = routeMock.fullPath
    await rerender({
      workspaceId: 11,
      projectId: 21,
      pageId: 32,
      pageTitle: '页面二',
    })

    await waitFor(() => {
      expect(screen.getByText('页面一会话内容应继续显示。')).toBeTruthy()
      expect(screen.getByText('当前页面不在此会话工作范围。')).toBeTruthy()
    })
    expect(screen.queryByText('页面二会话')).toBeNull()
    const textarea = screen.getByPlaceholderText(DEFAULT_PLACEHOLDER) as HTMLTextAreaElement
    expect(textarea.disabled).toBe(true)

    await fireEvent.click(screen.getByRole('button', { name: '打开此会话工作页面' }))
    expect(routerPushMock).toHaveBeenCalledWith('/workspaces/11/projects/21/pages/31')
  })

  it('项目 run 创建页面后切入页面 scope 仍应保留会话并按项目 scope 收尾', async () => {
    const projectSession = {
      session_id: 'project-session',
      agent_id: DEFAULT_AGENT_ID,
      session_name: '项目会话',
      created_at: '2026-04-18T10:00:00+08:00',
      updated_at: '2026-04-18T10:00:00+08:00',
      metadata: {
        scope_type: 'project',
        workspace_id: 11,
        project_id: 21,
        project_name: '演示项目',
        source: 'editor-agent-sidebar',
      },
    }
    const pausedRun = {
      run_id: 'run-project',
      session_id: 'project-session',
      agent_id: DEFAULT_AGENT_ID,
      status: 'paused',
      pending_requirement: {
        requirement_id: 'requirement-route',
        run_id: 'run-project',
        kind: 'tool_confirmation',
        tool_execution: {
          tool_call_id: 'tool-route',
          tool_name: 'apply_project_route_tree',
          arguments: {},
        },
      },
      content: null,
      created_at: '2026-04-18T10:00:00+08:00',
      updated_at: '2026-04-18T10:01:00+08:00',
      cancel_requested_at: null,
      event_index: 3,
    }

    createAgentSessionMock.mockResolvedValueOnce(projectSession)
    getAgentSessionRuntimeMock
      .mockResolvedValueOnce(createRuntimeSnapshot({
        session: projectSession,
      }))
      .mockResolvedValue(createRuntimeSnapshot({
        session: projectSession,
        active_run: pausedRun,
        pending_requirement: pausedRun.pending_requirement,
        event_index: 3,
      }))
    streamAgentRunEventsByRunIdMock.mockImplementationOnce(async (_runId: string, _payload: unknown, options?: { onEvent?: (event: any) => void }) => {
      options?.onEvent?.({ event: 'run.started', run_id: 'run-project', session_id: 'project-session', content: null, data: {}, sequence: 1 })
      options?.onEvent?.({
        event: 'tool.completed',
        run_id: 'run-project',
        session_id: 'project-session',
        content: null,
        sequence: 2,
        data: {
          tool_call_id: 'tool-create-page',
          tool_name: 'create_project_page',
          result: {
            success: true,
            page_id: 53,
            project_id: 21,
            title: '新页面',
          },
        },
      })
      options?.onEvent?.({
        event: 'run.paused',
        run_id: 'run-project',
        session_id: 'project-session',
        content: null,
        sequence: 3,
        data: { requirement: pausedRun.pending_requirement },
      })
    })

    let rerenderPanel: ((props: Record<string, unknown>) => Promise<void>) | null = null
    const projectPagesUpdatedSpy = vi.fn(() => {
      void rerenderPanel?.({
        workspaceId: 11,
        projectId: 21,
        pageId: 53,
        pageTitle: '新页面',
      })
    })
    const renderResult = render(AgentConversationPanel, createTestingRenderOptions({
      pageId: null,
      pageTitle: '',
      onProjectPagesUpdated: projectPagesUpdatedSpy,
    }))
    rerenderPanel = renderResult.rerender

    await fireEvent.update(screen.getByPlaceholderText(DEFAULT_PLACEHOLDER), '创建项目页')
    await fireEvent.click(screen.getByRole('button', { name: /发送/ }))

    await waitFor(() => {
      expect(projectPagesUpdatedSpy).toHaveBeenCalled()
      expect(getAgentSessionRuntimeMock).toHaveBeenCalledWith(
        'project-session',
        expect.objectContaining({
          scope_type: 'project',
          project_id: 21,
          page_id: null,
          source: 'editor-agent-sidebar',
        }),
        DEFAULT_AGENT_ID,
      )
    })
    expect(getAgentSessionRuntimeMock).not.toHaveBeenCalledWith(
      'project-session',
      expect.objectContaining({ scope_type: 'page' }),
      DEFAULT_AGENT_ID,
    )
    expect(messageWarningMock).not.toHaveBeenCalled()

    await fireEvent.click(screen.getByRole('button', { name: '切换会话' }))
    expect(await screen.findByRole('button', { name: /项目会话/ })).toBeTruthy()
  })

  it.each([
    ['component-manager', 'editor-component-library', '/workspaces/11/components'],
    ['resource-manager', 'editor-asset-library', '/workspaces/11/assets'],
  ])('页面路由上打开 %s 历史会话时应显示越界检测和工作页入口', async (targetAgentId, source, targetRoute) => {
    listAgentSessionsMock.mockResolvedValueOnce([
      {
        session_id: 'library-session',
        agent_id: targetAgentId,
        session_name: '库管理会话',
        created_at: '2026-04-18T10:00:00+08:00',
        updated_at: '2026-04-18T10:30:00+08:00',
        metadata: {
          scope_type: 'workspace',
          workspace_id: 11,
          source,
        },
      },
    ])
    getAgentSessionRuntimeMock.mockResolvedValueOnce(createRuntimeSnapshot({
      session: {
        session_id: 'library-session',
        agent_id: targetAgentId,
        session_name: '库管理会话',
        created_at: '2026-04-18T10:00:00+08:00',
        updated_at: '2026-04-18T10:30:00+08:00',
        metadata: {
          scope_type: 'workspace',
          workspace_id: 11,
          source,
        },
      },
    }))

    render(AgentConversationPanel, createTestingRenderOptions({
      agentId: targetAgentId,
      projectId: null,
      pageId: null,
      pageTitle: '',
      contextTitle: '库管理',
      scope: {
        scope_type: 'workspace',
        workspace_id: 11,
        project_id: null,
        page_id: null,
        component_id: null,
        workspace_name: null,
        project_name: null,
        page_title: null,
        component_name: null,
        source,
      },
      routeScope: {
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
      },
    }))

    await waitFor(() => {
      expect(screen.getByText('当前页面不在此会话工作范围。')).toBeTruthy()
    })

    await fireEvent.click(screen.getByRole('button', { name: '打开此会话工作页面' }))
    expect(routerPushMock).toHaveBeenCalledWith(targetRoute)
  })

})
