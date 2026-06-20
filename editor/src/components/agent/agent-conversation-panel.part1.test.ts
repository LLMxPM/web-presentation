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
    history_budget_tokens: 0,
    compression_target_tokens: 12800,
    estimated_history_tokens: 0,
    retained_recent_history_tokens: 0,
    retained_recent_message_count: 0,
    context_input_budget_tokens: 85760,
    context_used_tokens: 0,
    context_remaining_tokens: 85760,
    last_input_tokens: 0,
    last_output_tokens: 0,
    last_total_tokens: 0,
    last_reasoning_tokens: 0,
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
      history_budget_tokens: 0,
      compression_target_tokens: 12800,
      estimated_history_tokens: 0,
      retained_recent_history_tokens: 0,
      retained_recent_message_count: 0,
      context_input_budget_tokens: 85760,
      context_used_tokens: 0,
      context_remaining_tokens: 85760,
      last_input_tokens: 0,
      last_output_tokens: 0,
      last_total_tokens: 0,
      last_reasoning_tokens: 0,
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
        history_budget_tokens: 0,
        compression_target_tokens: 12800,
        estimated_history_tokens: 0,
        retained_recent_history_tokens: 0,
        retained_recent_message_count: 0,
        context_input_budget_tokens: 85760,
        context_used_tokens: 0,
        context_remaining_tokens: 85760,
        last_input_tokens: 0,
        last_output_tokens: 0,
        last_total_tokens: 0,
        last_reasoning_tokens: 0,
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

  it('会话列表与 runtime 快照首次加载时应展示明确加载态', async () => {
    const sessionsDeferred = createDeferred<any[]>()
    const runtimeDeferred = createDeferred<any>()
    listAgentSessionsMock.mockReturnValueOnce(sessionsDeferred.promise)
    getAgentSessionRuntimeMock.mockReturnValueOnce(runtimeDeferred.promise)

    render(AgentConversationPanel, createTestingRenderOptions())

    expect(await screen.findByText('正在加载智能体会话...')).toBeTruthy()

    sessionsDeferred.resolve([
      {
        session_id: 'session-1',
        agent_id: DEFAULT_AGENT_ID,
        session_name: '历史会话',
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

    await waitFor(() => {
      expect(getAgentSessionRuntimeMock).toHaveBeenCalledWith(
        'session-1',
        expect.objectContaining({ page_id: 31 }),
        DEFAULT_AGENT_ID,
      )
    })
    expect(screen.getByText('正在恢复会话内容...')).toBeTruthy()

    runtimeDeferred.resolve(createRuntimeSnapshot({
      messages: [
        {
          id: 'message-assistant-1',
          role: 'assistant',
          content: '历史会话已经恢复。',
          created_at: '2026-04-18T10:30:00+08:00',
          tool_name: null,
          tool_call_id: null,
          tool_args: null,
          tool_call_error: null,
        },
      ],
    }))

    await waitFor(() => {
      expect(screen.getByText('历史会话已经恢复。')).toBeTruthy()
    })
  })

  it('apply_page_edits 完成后应直接刷新页面，而不是进入确认流程', async () => {
    const pageUpdatedSpy = vi.fn()
    render(AgentConversationPanel, createTestingRenderOptions({
      onPageUpdated: pageUpdatedSpy,
    }))

    await waitFor(() => {
      expect(listAgentsMock).toHaveBeenCalled()
    })

    const textarea = screen.getByPlaceholderText(DEFAULT_PLACEHOLDER)
    await fireEvent.update(textarea, '帮我优化一下页面')
    await fireEvent.click(screen.getByRole('button', { name: /发送/ }))

    await waitFor(() => {
      expect(startAgentRunMock).toHaveBeenCalled()
      expect(pageUpdatedSpy).toHaveBeenCalledWith(expect.objectContaining({
        kind: 'page',
        workspaceId: 11,
        projectId: 21,
        pageId: 31,
        componentId: null,
        toolName: 'apply_page_edits',
        result: expect.objectContaining({
          success: true,
          version_no: 2,
        }),
      }))
    })

    expect(screen.queryByText('待确认动作')).toBeNull()
    expect(screen.queryByRole('button', { name: '确认执行' })).toBeNull()
    expect(screen.queryByText('只有在你确认后，页面代码才会真正写回后端并生成新版本。')).toBeNull()
  })

  it('发送后首个 SSE 可见事件到达前应显示等待输出提示', async () => {
    const streamDeferred = createDeferred<void>()
    streamAgentRunMock.mockImplementationOnce(async (sessionId: string, scope: unknown, payload: { run_id?: string }) => {
      startAgentRunMock(sessionId, scope, payload)
      await streamDeferred.promise
    })

    render(AgentConversationPanel, createTestingRenderOptions())

    await waitFor(() => {
      expect(listAgentsMock).toHaveBeenCalled()
    })

    const textarea = screen.getByPlaceholderText(DEFAULT_PLACEHOLDER)
    await fireEvent.update(textarea, '帮我整理页面资源')
    await fireEvent.click(screen.getByRole('button', { name: /发送/ }))

    expect(await screen.findByText('帮我整理页面资源')).toBeTruthy()
    expect(screen.getByText('等待智能体输出中')).toBeTruthy()
    streamDeferred.resolve()
  })

  it('reasoning 后工具参数静默阶段不应本地推断等待输出提示', async () => {
    const toolStartDeferred = createDeferred<void>()
    const streamDeferred = createDeferred<void>()
    streamAgentRunMock.mockImplementationOnce(async (sessionId: string, scope: unknown, payload: { run_id?: string }, options?: { onEvent?: (event: any) => void }) => {
      const runId = payload?.run_id ?? 'run-tool-args-silent'
      startAgentRunMock(sessionId, scope, payload)
      options?.onEvent?.({ event: 'run.started', run_id: runId, session_id: sessionId, content: null, data: {}, event_index: 0 })
      options?.onEvent?.({
        event: 'reasoning.delta',
        run_id: runId,
        session_id: sessionId,
        content: '先判断需要读取资源。',
        data: { reasoning_content: '先判断需要读取资源。' },
        event_index: 1,
      })
      await toolStartDeferred.promise
      options?.onEvent?.({
        event: 'tool.started',
        run_id: runId,
        session_id: sessionId,
        content: null,
        data: {
          tool_call_id: 'tool-assets-silent',
          tool_name: 'list_workspace_render_assets',
          arguments: { workspace_id: 11 },
        },
        event_index: 2,
      })
      await streamDeferred.promise
    })

    render(AgentConversationPanel, createTestingRenderOptions())

    await waitFor(() => {
      expect(listAgentsMock).toHaveBeenCalled()
    })

    const textarea = screen.getByPlaceholderText(DEFAULT_PLACEHOLDER)
    await fireEvent.update(textarea, '帮我整理页面资源')
    await fireEvent.click(screen.getByRole('button', { name: /发送/ }))

    await waitFor(() => {
      expect(screen.getByText('思考中')).toBeTruthy()
    })
    expect(screen.queryByText('等待智能体输出中')).toBeNull()

    toolStartDeferred.resolve()
    await waitFor(() => {
      expect(screen.queryByText('等待智能体输出中')).toBeNull()
      expect(screen.getByRole('button', { name: 'list_workspace_render_assets' })).toBeTruthy()
    })
    streamDeferred.resolve()
  })

  it('正文后工具参数静默阶段不应本地推断等待输出提示', async () => {
    const toolStartDeferred = createDeferred<void>()
    const streamDeferred = createDeferred<void>()
    streamAgentRunMock.mockImplementationOnce(async (sessionId: string, scope: unknown, payload: { run_id?: string }, options?: { onEvent?: (event: any) => void }) => {
      const runId = payload?.run_id ?? 'run-message-tool-args-silent'
      startAgentRunMock(sessionId, scope, payload)
      options?.onEvent?.({ event: 'run.started', run_id: runId, session_id: sessionId, content: null, data: {}, event_index: 0 })
      options?.onEvent?.({
        event: 'message.delta',
        run_id: runId,
        session_id: sessionId,
        content: '我先检查现有资源。',
        data: {},
        event_index: 1,
      })
      await toolStartDeferred.promise
      options?.onEvent?.({
        event: 'tool.started',
        run_id: runId,
        session_id: sessionId,
        content: null,
        data: {
          tool_call_id: 'tool-assets-after-message',
          tool_name: 'list_workspace_render_assets',
          arguments: { workspace_id: 11 },
        },
        event_index: 2,
      })
      await streamDeferred.promise
    })

    render(AgentConversationPanel, createTestingRenderOptions())

    await waitFor(() => {
      expect(listAgentsMock).toHaveBeenCalled()
    })

    const textarea = screen.getByPlaceholderText(DEFAULT_PLACEHOLDER)
    await fireEvent.update(textarea, '帮我整理页面资源')
    await fireEvent.click(screen.getByRole('button', { name: /发送/ }))

    await waitFor(() => {
      expect(screen.getByText('我先检查现有资源。')).toBeTruthy()
    })
    expect(screen.queryByText('等待智能体输出中')).toBeNull()

    toolStartDeferred.resolve()
    await waitFor(() => {
      expect(screen.queryByText('等待智能体输出中')).toBeNull()
      expect(screen.getByRole('button', { name: 'list_workspace_render_assets' })).toBeTruthy()
    })
    streamDeferred.resolve()
  })

  it('create_project_page 完成后应发出项目页面列表刷新事件', async () => {
    const projectPagesUpdatedSpy = vi.fn()
    streamAgentRunEventsByRunIdMock.mockImplementationOnce(async (_runId: string, _payload: unknown, options?: { onEvent?: (event: any) => void }) => {
      options?.onEvent?.({ event: 'run.started', run_id: 'run-project-pages', session_id: 'session-1', content: null, data: {} })
      options?.onEvent?.({
        event: 'tool.completed',
        run_id: 'run-project-pages',
        session_id: 'session-1',
        content: null,
        data: {
          tool_call_id: 'tool-create-page',
          tool_name: 'create_project_page',
          result: {
            success: true,
            page_id: 41,
            project_id: 21,
            title: '新页面',
          },
        },
      })
      options?.onEvent?.({ event: 'run.completed', run_id: 'run-project-pages', session_id: 'session-1', content: '页面已创建。', data: {} })
    })

    render(AgentConversationPanel, createTestingRenderOptions({
      onProjectPagesUpdated: projectPagesUpdatedSpy,
    }))

    await waitFor(() => {
      expect(listAgentsMock).toHaveBeenCalled()
    })
    await fireEvent.update(screen.getByPlaceholderText(DEFAULT_PLACEHOLDER), '新增一个项目页面')
    await fireEvent.click(screen.getByRole('button', { name: /发送/ }))

    await waitFor(() => {
      expect(projectPagesUpdatedSpy).toHaveBeenCalledWith(expect.objectContaining({
        kind: 'project-pages',
        workspaceId: 11,
        projectId: 21,
        pageId: 41,
        toolName: 'create_project_page',
      }))
    })
  })

  it('工具完成后应在 run 完成前立即派发页面刷新事件', async () => {
    const pageUpdatedSpy = vi.fn()
    const streamRelease = createDeferred()
    streamAgentRunEventsByRunIdMock.mockImplementationOnce(async (_runId: string, _payload: unknown, options?: { onEvent?: (event: any) => void }) => {
      options?.onEvent?.({ event: 'run.started', run_id: 'run-immediate', session_id: 'session-1', content: null, data: {} })
      options?.onEvent?.({
        event: 'tool.completed',
        run_id: 'run-immediate',
        session_id: 'session-1',
        content: null,
        data: {
          tool_call_id: 'tool-page-diff',
          tool_name: 'apply_page_edits',
          result: { success: true, page_id: 31, version_no: 2 },
        },
      })
      await streamRelease.promise
      options?.onEvent?.({ event: 'run.completed', run_id: 'run-immediate', session_id: 'session-1', content: '页面已更新。', data: {} })
    })

    render(AgentConversationPanel, createTestingRenderOptions({
      onPageUpdated: pageUpdatedSpy,
    }))

    await waitFor(() => {
      expect(listAgentsMock).toHaveBeenCalled()
    })
    await fireEvent.update(screen.getByPlaceholderText(DEFAULT_PLACEHOLDER), '立即更新当前页面')
    await fireEvent.click(screen.getByRole('button', { name: /发送/ }))

    await waitFor(() => {
      expect(pageUpdatedSpy).toHaveBeenCalledWith(expect.objectContaining({
        kind: 'page',
        pageId: 31,
        toolName: 'apply_page_edits',
      }))
    })
    expect(pageUpdatedSpy).toHaveBeenCalledTimes(1)

    streamRelease.resolve()
    await waitFor(() => {
      expect(streamAgentRunEventsByRunIdMock).toHaveBeenCalled()
    })
  })

  it('项目样式配置工具完成后应派发项目刷新事件', async () => {
    const projectUpdatedSpy = vi.fn()
    streamAgentRunEventsByRunIdMock.mockImplementationOnce(async (_runId: string, _payload: unknown, options?: { onEvent?: (event: any) => void }) => {
      options?.onEvent?.({ event: 'run.started', run_id: 'run-project-style', session_id: 'session-1', content: null, data: {} })
      options?.onEvent?.({
        event: 'tool.completed',
        run_id: 'run-project-style',
        session_id: 'session-1',
        content: null,
        data: {
          tool_call_id: 'tool-project-style',
          tool_name: 'update_project_style_config',
          result: { success: true, project_id: 21 },
        },
      })
      options?.onEvent?.({ event: 'run.completed', run_id: 'run-project-style', session_id: 'session-1', content: '样式配置已更新。', data: {} })
    })

    render(AgentConversationPanel, createTestingRenderOptions({
      onProjectUpdated: projectUpdatedSpy,
    }))

    await waitFor(() => {
      expect(listAgentsMock).toHaveBeenCalled()
    })
    await fireEvent.update(screen.getByPlaceholderText(DEFAULT_PLACEHOLDER), '更新项目样式配置')
    await fireEvent.click(screen.getByRole('button', { name: /发送/ }))

    await waitFor(() => {
      expect(projectUpdatedSpy).toHaveBeenCalledWith(expect.objectContaining({
        kind: 'project',
        workspaceId: 11,
        projectId: 21,
        pageId: 31,
        toolName: 'update_project_style_config',
      }))
    })
  })

  it('页面写入工具完成后应立即刷新且 run 结束不重复派发', async () => {
    const pageUpdatedSpy = vi.fn()
    const projectPagesUpdatedSpy = vi.fn()
    streamAgentRunEventsByRunIdMock.mockImplementationOnce(async (_runId: string, _payload: unknown, options?: { onEvent?: (event: any) => void }) => {
      options?.onEvent?.({ event: 'run.started', run_id: 'run-page-dedupe', session_id: 'session-1', content: null, data: {} })
      options?.onEvent?.({
        event: 'tool.completed',
        run_id: 'run-page-dedupe',
        session_id: 'session-1',
        content: null,
        data: {
          tool_call_id: 'tool-page-diff',
          tool_name: 'apply_page_edits',
          result: { success: true, page_id: 31, version_no: 2 },
        },
      })
      options?.onEvent?.({
        event: 'tool.completed',
        run_id: 'run-page-dedupe',
        session_id: 'session-1',
        content: null,
        data: {
          tool_call_id: 'tool-page-meta',
          tool_name: 'update_page_metadata',
          result: { success: true, page_id: 31, title: '新标题' },
        },
      })
      options?.onEvent?.({ event: 'run.completed', run_id: 'run-page-dedupe', session_id: 'session-1', content: '页面已更新。', data: {} })
    })

    render(AgentConversationPanel, createTestingRenderOptions({
      onPageUpdated: pageUpdatedSpy,
      onProjectPagesUpdated: projectPagesUpdatedSpy,
    }))

    await waitFor(() => {
      expect(listAgentsMock).toHaveBeenCalled()
    })
    await fireEvent.update(screen.getByPlaceholderText(DEFAULT_PLACEHOLDER), '更新页面内容和标题')
    await fireEvent.click(screen.getByRole('button', { name: /发送/ }))

    await waitFor(() => {
      expect(pageUpdatedSpy).toHaveBeenCalledTimes(2)
      expect(pageUpdatedSpy).toHaveBeenNthCalledWith(1, expect.objectContaining({
        kind: 'page',
        pageId: 31,
        toolName: 'apply_page_edits',
      }))
      expect(pageUpdatedSpy).toHaveBeenNthCalledWith(2, expect.objectContaining({
        kind: 'page',
        pageId: 31,
        toolName: 'update_page_metadata',
      }))
      expect(projectPagesUpdatedSpy).toHaveBeenCalledTimes(2)
    })
  })

  it.each([
    [
      'create_component',
      {
        success: true,
        component: {
          id: 99,
          name: '销售卡片',
          import_name: 'SalesCard',
        },
      },
    ],
    [
      'apply_component_edits',
      {
        success: true,
        component_id: 99,
        component: {
          id: 99,
          name: '销售卡片',
          import_name: 'SalesCard',
        },
      },
    ],
    [
      'update_component_metadata',
      {
        success: true,
        component: {
          id: 99,
          name: '销售卡片',
          import_name: 'SalesCard',
        },
      },
    ],
    [
      'publish_component',
      {
        success: true,
        component: {
          id: 99,
          name: '销售卡片',
          import_name: 'SalesCard',
          current_version_no: 2,
        },
      },
    ],
    [
      'delete_component',
      {
        success: true,
        component_id: 99,
      },
    ],
  ] as const)('组件写入工具 %s 完成后应发出组件刷新事件', async (toolName, result) => {
    const componentUpdatedSpy = vi.fn()
    const componentSession = {
      session_id: 'session-1',
      agent_id: DEFAULT_AGENT_ID,
      session_name: '销售卡片 会话',
      created_at: '2026-04-18T10:00:00+08:00',
      updated_at: '2026-04-18T10:00:00+08:00',
      metadata: {
        scope_type: 'component',
        workspace_id: 11,
        project_id: null,
        page_id: null,
        component_id: 99,
        component_name: '销售卡片',
        source: 'editor-component-library',
      },
    }
    createAgentSessionMock.mockResolvedValueOnce(componentSession)
    getAgentSessionRuntimeMock.mockResolvedValue(createRuntimeSnapshot({ session: componentSession }))
    streamAgentRunEventsByRunIdMock.mockImplementationOnce(async (_runId: string, _payload: unknown, options?: { onEvent?: (event: any) => void }) => {
      options?.onEvent?.({ event: 'run.started', run_id: 'run-component', session_id: 'session-1', content: null, data: {} })
      options?.onEvent?.({
        event: 'tool.completed',
        run_id: 'run-component',
        session_id: 'session-1',
        content: null,
        data: {
          tool_call_id: 'tool-component-diff',
          tool_name: toolName,
          result,
        },
      })
      options?.onEvent?.({ event: 'run.completed', run_id: 'run-component', session_id: 'session-1', content: '组件已更新。', data: {} })
    })

    render(AgentConversationPanel, createTestingRenderOptions({
      pageId: null,
      projectId: null,
      componentId: 99,
      contextTitle: '销售卡片',
      scope: {
        scope_type: 'component',
        workspace_id: 11,
        project_id: null,
        page_id: null,
        component_id: 99,
        workspace_name: null,
        project_name: null,
        page_title: null,
        component_name: '销售卡片',
        source: 'editor-component-library',
      },
      onComponentUpdated: componentUpdatedSpy,
    }))

    await waitFor(() => {
      expect(listAgentsMock).toHaveBeenCalled()
    })
    await fireEvent.update(screen.getByPlaceholderText(DEFAULT_PLACEHOLDER), '修改组件源码')
    await fireEvent.click(screen.getByRole('button', { name: /发送/ }))

    await waitFor(() => {
      expect(componentUpdatedSpy).toHaveBeenCalledWith(expect.objectContaining({
        kind: 'component',
        workspaceId: 11,
        projectId: null,
        pageId: null,
        componentId: 99,
        toolName,
      }))
    })
  })

  it('读取和预览类工具完成后不应触发领域刷新事件', async () => {
    const pageUpdatedSpy = vi.fn()
    const projectPagesUpdatedSpy = vi.fn()
    const componentUpdatedSpy = vi.fn()
    streamAgentRunEventsByRunIdMock.mockImplementationOnce(async (_runId: string, _payload: unknown, options?: { onEvent?: (event: any) => void }) => {
      options?.onEvent?.({ event: 'run.started', run_id: 'run-readonly', session_id: 'session-1', content: null, data: {} })
      options?.onEvent?.({
        event: 'tool.completed',
        run_id: 'run-readonly',
        session_id: 'session-1',
        content: null,
        data: {
          tool_call_id: 'tool-list-components',
          tool_name: 'list_workspace_components',
          result: {
            total: 1,
            items: ['SalesCard'],
          },
        },
      })
      options?.onEvent?.({ event: 'run.completed', run_id: 'run-readonly', session_id: 'session-1', content: '组件列表已读取。', data: {} })
    })

    render(AgentConversationPanel, createTestingRenderOptions({
      onPageUpdated: pageUpdatedSpy,
      onProjectPagesUpdated: projectPagesUpdatedSpy,
      onComponentUpdated: componentUpdatedSpy,
    }))

    await waitFor(() => {
      expect(listAgentsMock).toHaveBeenCalled()
    })
    await fireEvent.update(screen.getByPlaceholderText(DEFAULT_PLACEHOLDER), '读取组件列表')
    await fireEvent.click(screen.getByRole('button', { name: /发送/ }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'list_workspace_components' })).toBeTruthy()
    })
    expect(pageUpdatedSpy).not.toHaveBeenCalled()
    expect(projectPagesUpdatedSpy).not.toHaveBeenCalled()
    expect(componentUpdatedSpy).not.toHaveBeenCalled()
  })

  it('标题和输入区不应再展示旧的说明文案', async () => {
    listAgentsMock.mockResolvedValueOnce([
      {
        id: 'agent-coordinator',
        name: '内容助手',
        icon: 'content-spark',
        summary: '内容助手 Team 入口，负责页面/项目处理和成员调度。',
        default_session_name: '内容助手会话',
        capabilities: ['页面/项目处理', '组件助手调度', '资源助手调度'],
        llm_slot: 'agent_coordinator',
        llm_binding_ready: true,
        bound_llm_name: '总控模型',
        bound_provider_label: 'OpenAI',
        scope: {
          workspace_id: 11,
          project_id: 21,
          page_id: 31,
          source: 'editor-page-detail',
        },
      },
    ])

    render(AgentConversationPanel, createTestingRenderOptions())

    await waitFor(() => {
      expect(listAgentsMock).toHaveBeenCalled()
    })

    expect(screen.queryByText('内容助手 Team 入口，负责页面/项目处理和成员调度。')).toBeNull()
    expect(screen.queryByText('默认中文输出；涉及写入页面代码时，助手会先读取最新源码，再直接应用 Diff 并保存新版本。')).toBeNull()
  })

  it('运行中应允许发起中断请求', async () => {
    const streamSignalRef: { value: AbortSignal | null } = { value: null }
    cancelAgentSessionActiveRunMock.mockResolvedValueOnce({
      run_id: 'run-2',
      session_id: 'session-1',
      cancel_requested: true,
    })
    streamAgentRunEventsByRunIdMock.mockImplementation(async (_runId: string, _payload: unknown, options?: { onEvent?: (event: any) => void, signal?: AbortSignal }) => {
      options?.onEvent?.({ event: 'run.started', run_id: 'run-2', session_id: 'session-1', content: null, data: {} })
      streamSignalRef.value = options?.signal ?? null
      await new Promise<void>((_resolve, reject) => {
        options?.signal?.addEventListener('abort', () => reject(new AgentStreamInterruptedErrorMock()), { once: true })
      })
    })

    render(AgentConversationPanel, createTestingRenderOptions())

    await waitFor(() => {
      expect(listAgentsMock).toHaveBeenCalled()
    })

    const textarea = screen.getByPlaceholderText(DEFAULT_PLACEHOLDER)
    await fireEvent.update(textarea, '开始长任务')
    await fireEvent.click(screen.getByRole('button', { name: /发送/ }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '停止' })).toBeTruthy()
    })

    await fireEvent.click(screen.getByRole('button', { name: '停止' }))

    await waitFor(() => {
      expect(cancelAgentSessionActiveRunMock).toHaveBeenCalledWith(
        'session-1',
        expect.objectContaining({ page_id: 31 }),
        expect.objectContaining({ agent_id: DEFAULT_AGENT_ID }),
      )
    })
    expect(streamSignalRef.value?.aborted).toBe(false)
    expect(messageErrorMock).not.toHaveBeenCalled()
    expect(messageInfoMock).not.toHaveBeenCalledWith('已停止。')
    expect(messageInfoMock).not.toHaveBeenCalledWith('当前运行已被用户取消，后台执行句柄已释放。')
  })

  it('取消终态快照暂时为空时应以快照清理本地流式消息', async () => {
    startAgentRunMock.mockResolvedValueOnce({
      run_id: 'run-cancel',
      session_id: 'session-1',
      status: 'pending',
      event_index: -1,
    })
    const cancelledRuntime = createRuntimeSnapshot({
      messages: [],
      last_run: {
        run_id: 'run-cancel',
        session_id: 'session-1',
        agent_id: DEFAULT_AGENT_ID,
        status: 'cancelled',
        pending_requirement: null,
        content: null,
        created_at: '2026-04-18T10:05:00+08:00',
        event_index: 3,
      },
      event_index: 3,
    })
    getAgentSessionRuntimeMock.mockImplementation(async () => (
      streamAgentRunEventsByRunIdMock.mock.calls.length > 0
        ? cancelledRuntime
        : createRuntimeSnapshot()
    ))
    streamAgentRunEventsByRunIdMock.mockImplementationOnce(async (_runId: string, _payload: unknown, options?: { onEvent?: (event: any) => void }) => {
      options?.onEvent?.({ event: 'run.started', run_id: 'run-cancel', session_id: 'session-1', content: null, data: {}, sequence: 1 })
      options?.onEvent?.({ event: 'message.delta', run_id: 'run-cancel', session_id: 'session-1', content: '已流出的局部内容。', data: {}, sequence: 2 })
      options?.onEvent?.({ event: 'run.cancelled', run_id: 'run-cancel', session_id: 'session-1', content: null, data: {}, sequence: 3 })
    })

    render(AgentConversationPanel, createTestingRenderOptions())

    await waitFor(() => {
      expect(listAgentsMock).toHaveBeenCalled()
    })

    await fireEvent.update(screen.getByPlaceholderText(DEFAULT_PLACEHOLDER), '开始长任务后停止')
    await fireEvent.click(screen.getByRole('button', { name: /发送/ }))

    await waitFor(() => {
      expect(messageInfoMock).toHaveBeenCalledWith('已停止。')
    })
    await waitFor(() => {
      expect(screen.queryByText('已流出的局部内容。')).toBeNull()
    })
  })

  it('缺少本地流控制器时应使用后端取消接口兜底', async () => {
    localStorage.setItem('agent-session:agent-coordinator:11', 'session-1')
    localStorage.setItem('agent-session:v2:agent-coordinator:page:11:21:31::editor-page-detail', 'session-1')
    listAgentSessionsMock.mockResolvedValueOnce([
      {
        session_id: 'session-1',
        agent_id: DEFAULT_AGENT_ID,
        session_name: '运行中会话',
        created_at: '2026-04-18T10:00:00+08:00',
        updated_at: '2026-04-18T10:05:00+08:00',
        metadata: {
          workspace_id: 11,
          project_id: 21,
          page_id: 31,
          source: 'editor-page-detail',
        },
      },
    ])
    const fallbackRun = {
      run_id: 'run-fallback',
      session_id: 'session-1',
      agent_id: DEFAULT_AGENT_ID,
      status: 'running',
      pending_requirement: null,
      content: null,
      created_at: '2026-04-18T10:05:00+08:00',
    }
    getAgentSessionActiveRunMock.mockResolvedValue(fallbackRun)
    getAgentSessionRuntimeMock.mockResolvedValueOnce(createRuntimeSnapshot({
      active_run: fallbackRun,
      event_index: -1,
    }))
    streamAgentRunEventsByRunIdMock.mockImplementationOnce(async () => {
      await new Promise<void>(() => {})
    })
    cancelAgentSessionActiveRunMock.mockResolvedValueOnce({
      run_id: 'run-fallback',
      session_id: 'session-1',
      cancel_requested: true,
    })

    render(AgentConversationPanel, createTestingRenderOptions())

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '停止' })).toBeTruthy()
    })

    await fireEvent.click(screen.getByRole('button', { name: '停止' }))

    await waitFor(() => {
      expect(cancelAgentSessionActiveRunMock).toHaveBeenCalledWith(
        'session-1',
        expect.objectContaining({ page_id: 31 }),
        expect.objectContaining({ agent_id: DEFAULT_AGENT_ID }),
      )
    })
    expect(messageInfoMock).not.toHaveBeenCalledWith('已停止。')
  })

  it('停止超时应显示强制结束入口并调用 force cancel', async () => {
    localStorage.setItem('agent-session:agent-coordinator:11', 'session-1')
    localStorage.setItem('agent-session:v2:agent-coordinator:page:11:21:31::editor-page-detail', 'session-1')
    listAgentSessionsMock.mockResolvedValueOnce([
      {
        session_id: 'session-1',
        agent_id: DEFAULT_AGENT_ID,
        session_name: '停止中会话',
        created_at: '2026-04-18T10:00:00+08:00',
        updated_at: '2026-04-18T10:05:00+08:00',
        metadata: {
          workspace_id: 11,
          project_id: 21,
          page_id: 31,
          source: 'editor-page-detail',
        },
      },
    ])
    const cancellingRun = {
      run_id: 'run-force',
      session_id: 'session-1',
      agent_id: DEFAULT_AGENT_ID,
      status: 'cancelling',
      pending_requirement: null,
      content: null,
      created_at: '2026-04-18T10:05:00+08:00',
      updated_at: '2026-04-18T10:05:05+08:00',
      cancel_requested_at: '2026-04-18T10:05:05+08:00',
      event_index: 2,
    }
    getAgentSessionActiveRunMock.mockResolvedValue(cancellingRun)
    getAgentSessionRuntimeMock.mockResolvedValueOnce(createRuntimeSnapshot({
      active_run: cancellingRun,
      event_index: 2,
    }))
    streamAgentRunEventsByRunIdMock.mockImplementationOnce(async () => {
      await new Promise<void>(() => {})
    })
    cancelAgentSessionActiveRunMock.mockResolvedValueOnce({
      run_id: 'run-force',
      session_id: 'session-1',
      cancel_requested: true,
    })

    render(AgentConversationPanel, createTestingRenderOptions())

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '强制结束' })).toBeTruthy()
    })

    await fireEvent.click(screen.getByRole('button', { name: '强制结束' }))

    await waitFor(() => {
      expect(cancelAgentSessionActiveRunMock).toHaveBeenCalledWith(
        'session-1',
        expect.objectContaining({ page_id: 31 }),
        expect.objectContaining({ agent_id: DEFAULT_AGENT_ID, force: true }),
      )
    })
    expect(messageInfoMock).toHaveBeenCalledWith('已停止。')
  })

})
