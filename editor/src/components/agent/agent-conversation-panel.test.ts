/**
 * 文件功能：验证内容助手面板的流式消息渲染、工具详情与页面写回联动。
 */
import { render, fireEvent, screen, waitFor } from '@testing-library/vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AgentConversationPanel from '@/components/agent/AgentConversationPanel.vue'
import { useAgentSessionStore } from '@/stores/agent-session'

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

  it('取消终态快照暂时为空时不应清空本地流式消息', async () => {
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
    expect(screen.getByText('已流出的局部内容。')).toBeTruthy()
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

  it('runtime 快照会话与当前路由不一致时不应写入当前消息流', async () => {
    localStorage.setItem('agent-session:v2:agent-coordinator:page:11:21:32::editor-page-detail', 'session-32')
    listAgentSessionsMock.mockResolvedValueOnce([
      {
        session_id: 'session-32',
        agent_id: DEFAULT_AGENT_ID,
        session_name: '页面二会话',
        created_at: '2026-04-18T10:00:00+08:00',
        updated_at: '2026-04-18T10:30:00+08:00',
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
      session: {
        session_id: 'session-31',
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
      messages: [
        {
          id: 'stale-message',
          role: 'assistant',
          content: '页面一的旧快照不应显示在页面二。',
          created_at: '2026-04-18T10:30:00+08:00',
          tool_name: null,
          tool_call_id: null,
          tool_args: null,
          tool_call_error: null,
        },
      ],
    }))

    render(AgentConversationPanel, createTestingRenderOptions({
      pageId: 32,
      pageTitle: '页面二',
    }))

    await waitFor(() => {
      expect(getAgentSessionRuntimeMock).toHaveBeenCalledWith(
        'session-32',
        expect.objectContaining({ page_id: 32 }),
        DEFAULT_AGENT_ID,
      )
    })
    expect(screen.queryByText('页面一的旧快照不应显示在页面二。')).toBeNull()
    await waitFor(() => {
      expect(screen.getByText(/内容助手 会结合当前上下文/)).toBeTruthy()
    })
  })

  it('切回本地已有进度的运行中会话时应从本地 sequence 恢复订阅', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useAgentSessionStore()
    store.applyRunEvent('session-1', {
      event: 'run.started',
      run_id: 'run-resume',
      session_id: 'session-1',
      content: null,
      data: {},
      sequence: 1,
    }, {
      agentId: DEFAULT_AGENT_ID,
      agentDisplayName: '内容助手',
    })
    store.applyRunEvent('session-1', {
      event: 'message.delta',
      run_id: 'run-resume',
      session_id: 'session-1',
      content: '已经流出的片段。',
      data: {},
      sequence: 2,
    }, {
      agentId: DEFAULT_AGENT_ID,
      agentDisplayName: '内容助手',
    })
    localStorage.setItem('agent-session:v2:agent-coordinator:page:11:21:31::editor-page-detail', 'session-1')
    listAgentSessionsMock.mockResolvedValueOnce([
      {
        session_id: 'session-1',
        agent_id: DEFAULT_AGENT_ID,
        session_name: '运行中会话',
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
    getAgentSessionRuntimeMock.mockResolvedValueOnce(createRuntimeSnapshot({
      messages: [
        {
          id: 'stale-assistant',
          role: 'assistant',
          content: '运行中快照里的旧内容不应覆盖本地片段。',
          created_at: '2026-04-18T10:30:00+08:00',
          tool_name: null,
          tool_call_id: null,
          tool_args: null,
          tool_call_error: null,
        },
      ],
      active_run: {
        run_id: 'run-resume',
        session_id: 'session-1',
        agent_id: DEFAULT_AGENT_ID,
        status: 'running',
        pending_requirement: null,
        content: null,
        created_at: '2026-04-18T10:30:00+08:00',
        event_index: 5,
      },
      event_index: 5,
    }))
    streamAgentRunEventsByRunIdMock.mockImplementationOnce(async () => {
      await new Promise<void>(() => {})
    })

    render(AgentConversationPanel, createTestingRenderOptions(undefined, pinia))

    await waitFor(() => {
      expect(streamAgentRunEventsByRunIdMock).toHaveBeenCalledWith(
        'run-resume',
        { after_sequence: 2 },
        expect.objectContaining({ onEvent: expect.any(Function) }),
      )
    })
    expect(screen.getByText('已经流出的片段。')).toBeTruthy()
    expect(screen.queryByText('运行中快照里的旧内容不应覆盖本地片段。')).toBeNull()
  })

  it('后台订阅事件缺少 session_id 时应写回订阅目标会话', async () => {
    const subscribedOnEvent = { current: null as ((event: any) => void) | null }
    localStorage.setItem('agent-session:v2:agent-coordinator:page:11:21:31::editor-page-detail', 'session-1')
    listAgentSessionsMock.mockResolvedValueOnce([
      {
        session_id: 'session-1',
        agent_id: DEFAULT_AGENT_ID,
        session_name: '运行中会话',
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
        session_name: '另一个会话',
        created_at: '2026-04-18T09:00:00+08:00',
        updated_at: '2026-04-18T09:30:00+08:00',
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
    getAgentSessionRuntimeMock
      .mockResolvedValueOnce(createRuntimeSnapshot({
        active_run: {
          run_id: 'run-background',
          session_id: 'session-1',
          agent_id: DEFAULT_AGENT_ID,
          status: 'running',
          pending_requirement: null,
          content: null,
          created_at: '2026-04-18T10:30:00+08:00',
          event_index: 0,
        },
        event_index: 0,
      }))
      .mockResolvedValueOnce(createRuntimeSnapshot({
        session: {
          session_id: 'session-2',
          agent_id: DEFAULT_AGENT_ID,
          session_name: '另一个会话',
          created_at: '2026-04-18T09:00:00+08:00',
          updated_at: '2026-04-18T09:30:00+08:00',
          metadata: {
            scope_type: 'page',
            workspace_id: 11,
            project_id: 21,
            page_id: 31,
            page_title: 'AI 页面',
            source: 'editor-page-detail',
          },
        },
      }))
    streamAgentRunEventsByRunIdMock.mockImplementationOnce(async (_runId: string, _payload: unknown, options?: { onEvent?: (event: any) => void }) => {
      subscribedOnEvent.current = options?.onEvent ?? null
      await new Promise<void>(() => {})
    })

    render(AgentConversationPanel, createTestingRenderOptions())

    await waitFor(() => {
      expect(subscribedOnEvent.current).not.toBeNull()
    })
    await fireEvent.click(screen.getByRole('button', { name: '切换会话' }))
    await fireEvent.click(await screen.findByRole('button', { name: /另一个会话/ }))

    subscribedOnEvent.current?.({
      event: 'message.delta',
      run_id: 'run-background',
      session_id: null,
      content: '后台继续输出的片段。',
      data: {},
      sequence: 1,
    })

    expect(screen.queryByText('后台继续输出的片段。')).toBeNull()

    await fireEvent.click(screen.getByRole('button', { name: '切换会话' }))
    await fireEvent.click(await screen.findByRole('button', { name: /运行中会话/ }))

    await waitFor(() => {
      expect(screen.getByText('后台继续输出的片段。')).toBeTruthy()
    })
  })

  it('顶部 scope 手动切路由后应只展示当前路由范围', async () => {
    const headerScopeTarget = document.createElement('div')
    headerScopeTarget.id = 'scope-target'
    document.body.appendChild(headerScopeTarget)
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
      headerScopeTarget: '#scope-target',
      pageId: 32,
      pageTitle: '页面二',
    }))

    await waitFor(() => {
      expect(screen.getByText('页面二')).toBeTruthy()
      expect(screen.getByText('未选择会话')).toBeTruthy()
    })
    expect(screen.queryByText('页面一')).toBeNull()
    expect(screen.queryByText('不在范围')).toBeNull()
    expect(screen.queryByText('会话')).toBeNull()
    expect(screen.queryByText('当前')).toBeNull()
    expect(screen.queryByText('页面')).toBeNull()

    headerScopeTarget.remove()
  })

  it('刷新后应通过 active-run 恢复待确认状态', async () => {
    localStorage.setItem('agent-session:agent-coordinator:11', 'session-1')
    listAgentSessionsMock.mockResolvedValueOnce([
      {
        session_id: 'session-1',
        agent_id: DEFAULT_AGENT_ID,
        session_name: '待确认会话',
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
    const pausedRun = {
      run_id: 'run-paused-1',
      session_id: 'session-1',
      agent_id: DEFAULT_AGENT_ID,
      status: 'paused',
      pending_requirement: {
        id: null,
        kind: 'confirmation',
        run_id: 'run-paused-1',
        session_id: 'session-1',
        tool_name: 'apply_page_edits',
        tool_execution: { tool_name: 'apply_page_edits', tool_call_id: 'tool-confirm-1', tool_args: {} },
        suggested_patch: null,
        user_feedback_schema: [],
        note: null,
      },
      content: null,
      created_at: '2026-04-18T10:30:00+08:00',
    }
    getAgentSessionActiveRunMock.mockResolvedValueOnce(pausedRun)
    getAgentSessionRuntimeMock.mockResolvedValueOnce(createRuntimeSnapshot({
      active_run: pausedRun,
      pending_requirement: pausedRun.pending_requirement,
      event_index: -1,
    }))

    render(AgentConversationPanel, createTestingRenderOptions())

    await waitFor(() => {
      expect(screen.getByText('允许执行 apply_page_edits 吗？')).toBeTruthy()
      expect(screen.queryByPlaceholderText(DEFAULT_PLACEHOLDER)).toBeNull()
    })

    await fireEvent.click(screen.getByRole('button', { name: /提交/ }))

    await waitFor(() => {
      expect(continueAgentSessionActiveRunMock).toHaveBeenCalled()
    })
    expect(continueAgentSessionActiveRunMock.mock.calls[0][0]).toBe('session-1')
    expect(continueAgentSessionActiveRunMock.mock.calls[0][2]).toEqual(expect.objectContaining({
      decision: 'confirm',
      tool_execution: { tool_name: 'apply_page_edits', tool_call_id: 'tool-confirm-1', tool_args: {} },
    }))
    expect(continueAgentSessionActiveRunMock.mock.calls[0][2]).not.toHaveProperty('note')
  })

  it('应将工具调用内嵌到助手消息中，并支持查看输入输出详情', async () => {
    const finalMessages = [
      {
        id: 'message-user-1',
        role: 'user',
        content: '检查当前页面资源',
        created_at: '2026-04-18T10:00:00+08:00',
        tool_name: null,
      },
      {
        id: 'message-assistant-1',
        role: 'assistant',
        content: '我已经读取当前页面资源并完成检查。',
        created_at: '2026-04-18T10:00:02+08:00',
        tool_name: null,
      },
    ]
    getAgentSessionMessagesMock
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce(finalMessages)
    getAgentSessionRuntimeMock
      .mockResolvedValueOnce(createRuntimeSnapshot())
      .mockResolvedValue(createRuntimeSnapshot({ messages: finalMessages }))

    streamAgentRunEventsByRunIdMock.mockImplementationOnce(async (_runId: string, _payload: unknown, options?: { onEvent?: (event: any) => void }) => {
      options?.onEvent?.({ event: 'run.started', run_id: 'run-3', session_id: 'session-1', content: null, data: {} })
      options?.onEvent?.({ event: 'message.delta', run_id: 'run-3', session_id: 'session-1', content: '我先读取页面资源。', data: {} })
      options?.onEvent?.({
        event: 'tool.started',
        run_id: 'run-3',
        session_id: 'session-1',
        content: null,
        data: {
          tool_call_id: 'tool-asset-1',
          tool_name: 'list_workspace_render_assets',
          tool_args: {
            workspace_id: 11,
            limit: 20,
          },
        },
      })
      options?.onEvent?.({
        event: 'tool.completed',
        run_id: 'run-3',
        session_id: 'session-1',
        content: null,
        data: {
          tool_call_id: 'tool-asset-1',
          tool_name: 'list_workspace_render_assets',
          message: 'list_workspace_render_assets(limit=20) completed in 0.0111s.',
          result: {
            total: 2,
            items: ['hero.png', 'cover.png'],
          },
        },
      })
      options?.onEvent?.({ event: 'run.completed', run_id: 'run-3', session_id: 'session-1', content: null, data: {} })
    })

    render(AgentConversationPanel, createTestingRenderOptions())

    await waitFor(() => {
      expect(listAgentsMock).toHaveBeenCalled()
    })

    await fireEvent.update(
      screen.getByPlaceholderText(DEFAULT_PLACEHOLDER),
      '检查当前页面资源',
    )
    await fireEvent.click(screen.getByRole('button', { name: /发送/ }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'list_workspace_render_assets' })).toBeTruthy()
    })

    expect(screen.queryByText('工具时间线')).toBeNull()

    await fireEvent.click(screen.getByRole('button', { name: 'list_workspace_render_assets' }))

    await waitFor(() => {
      expect(screen.getByText('工具输入')).toBeTruthy()
      expect(screen.getByText('工具输出')).toBeTruthy()
      expect(screen.getByText(/"workspace_id": 11/)).toBeTruthy()
      expect(screen.getByText(/hero\.png/)).toBeTruthy()
      expect(screen.queryByText(/completed in 0\.0111s/)).toBeNull()
    })

    await fireEvent.click(screen.getByRole('button', { name: '复制详情' }))

    expect(clipboardWriteTextMock).toHaveBeenCalledWith(
      '工具id:list_workspace_render_assets\nLLM输入:\n{\n  "workspace_id": 11,\n  "limit": 20\n}\n工具输出:\n{\n  "total": 2,\n  "items": [\n    "hero.png",\n    "cover.png"\n  ]\n}',
    )
    expect(messageSuccessMock).toHaveBeenCalledWith('工具调用详情已复制。')
  })

  it('delegate 工具应打开成员运行弹窗，并可查看成员子工具详情', async () => {
    localStorage.setItem('agent-session:agent-coordinator:11', 'session-1')
    listAgentSessionsMock.mockResolvedValueOnce([
      {
        session_id: 'session-1',
        agent_id: DEFAULT_AGENT_ID,
        session_name: '成员运行历史',
        created_at: '2026-04-18T10:00:00+08:00',
        updated_at: '2026-04-18T10:20:00+08:00',
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
    getAgentSessionRuntimeMock.mockResolvedValueOnce(createRuntimeSnapshot({
      timeline_items: [
        {
          id: 'delegate-tool',
          session_id: 'session-1',
          run_id: 'parent-run-1',
          kind: 'tool',
          role: null,
          event_index: 1,
          order_index: 0,
          content: null,
          status: 'completed',
          tool: {
            tool_call_id: 'delegate-call-resource',
            tool_name: 'delegate_task_to_member',
            status: 'completed',
            input_payload: { member_id: 'resource-manager', task: '整理资源' },
            output_payload: { success: true },
            message: '',
          },
          source: 'event',
          created_at: '2026-04-18T10:00:00+08:00',
        },
      ],
      member_runs: [
        {
          parent_run_id: 'parent-run-1',
          run_id: 'member-run-resource',
          agent_id: 'resource-manager',
          agent_name: '资源助手',
          status: 'completed',
          created_at: '2026-04-18T10:00:01+08:00',
          updated_at: '2026-04-18T10:00:02+08:00',
          delegate_tool_call_id: 'delegate-call-resource',
          timeline_items: [
            {
              id: 'member-tool-list-assets',
              session_id: 'session-1',
              run_id: 'member-run-resource',
              kind: 'tool',
              role: null,
              event_index: 1,
              order_index: 0,
              content: null,
              status: 'completed',
              tool: {
                tool_call_id: 'child-tool-list-assets',
                tool_name: 'list_workspace_render_assets',
                member_agent_id: 'resource-manager',
                member_agent_name: '资源助手',
                member_run_id: 'member-run-resource',
                status: 'completed',
                input_payload: { workspace_id: 11 },
                output_payload: { total: 2, items: ['hero.png'] },
                message: '',
              },
              source: 'event',
              created_at: '2026-04-18T10:00:02+08:00',
            },
          ],
        },
      ],
    }))

    render(AgentConversationPanel, createTestingRenderOptions())

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '资源助手运行' })).toBeTruthy()
    })

    await fireEvent.click(screen.getByRole('button', { name: '资源助手运行' }))

    await waitFor(() => {
      expect(screen.getByText('资源助手运行详情')).toBeTruthy()
      expect(screen.getByRole('button', { name: /list_workspace_render_assets/ })).toBeTruthy()
    })

    await fireEvent.click(screen.getByRole('button', { name: /list_workspace_render_assets/ }))

    await waitFor(() => {
      expect(screen.getByText('工具输入')).toBeTruthy()
      expect(screen.getByText('工具输出')).toBeTruthy()
      expect(screen.getByText(/"workspace_id": 11/)).toBeTruthy()
      expect(screen.getByText(/hero\.png/)).toBeTruthy()
    })
  })

  it('连续工具调用应默认折叠为弱化摘要并可展开查看详情', async () => {
    getAgentSessionMessagesMock
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        {
          id: 'message-user-1',
          role: 'user',
          content: '连续检查资源和组件',
          created_at: '2026-04-18T10:00:00+08:00',
          tool_name: null,
          tool_call_id: null,
          tool_args: null,
          tool_call_error: null,
        },
        {
          id: 'message-assistant-1',
          role: 'assistant',
          content: '检查完成。',
          created_at: '2026-04-18T10:00:02+08:00',
          tool_name: null,
          tool_call_id: null,
          tool_args: null,
          tool_call_error: null,
        },
      ])

    streamAgentRunEventsByRunIdMock.mockImplementationOnce(async (_runId: string, _payload: unknown, options?: { onEvent?: (event: any) => void }) => {
      options?.onEvent?.({ event: 'run.started', run_id: 'run-tools-group', session_id: 'session-1', content: null, data: {} })
      options?.onEvent?.({ event: 'message.delta', run_id: 'run-tools-group', session_id: 'session-1', content: '开始连续检查。', data: {} })
      options?.onEvent?.({
        event: 'tool.completed',
        run_id: 'run-tools-group',
        session_id: 'session-1',
        content: null,
        data: {
          tool_call_id: 'tool-assets',
          tool_name: 'list_workspace_render_assets',
          result: { total: 1, items: ['hero.png'] },
        },
      })
      options?.onEvent?.({
        event: 'tool.completed',
        run_id: 'run-tools-group',
        session_id: 'session-1',
        content: null,
        data: {
          tool_call_id: 'tool-components',
          tool_name: 'list_workspace_components',
          result: { total: 1, items: ['HeroCard'] },
        },
      })
      options?.onEvent?.({ event: 'run.completed', run_id: 'run-tools-group', session_id: 'session-1', content: null, data: {} })
    })

    render(AgentConversationPanel, createTestingRenderOptions())

    await waitFor(() => {
      expect(listAgentsMock).toHaveBeenCalled()
    })

    await fireEvent.update(
      screen.getByPlaceholderText(DEFAULT_PLACEHOLDER),
      '连续检查资源和组件',
    )
    await fireEvent.click(screen.getByRole('button', { name: /发送/ }))

    await waitFor(() => {
      expect(screen.getByText('2 次工具调用 · 2 已完成')).toBeTruthy()
    })
    const details = screen.getByText('2 次工具调用 · 2 已完成').closest('details')
    expect(details?.hasAttribute('open')).toBe(false)

    await fireEvent.click(screen.getByText('2 次工具调用 · 2 已完成'))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'list_workspace_render_assets' })).toBeTruthy()
      expect(screen.getByRole('button', { name: 'list_workspace_components' })).toBeTruthy()
    })
  })

  it('连续工具调用包含进行中状态时应自动展开', async () => {
    let releaseStream = () => {}
    streamAgentRunEventsByRunIdMock.mockImplementationOnce(async (_runId: string, _payload: unknown, options?: { onEvent?: (event: any) => void }) => {
      options?.onEvent?.({ event: 'run.started', run_id: 'run-tools-running', session_id: 'session-1', content: null, data: {} })
      options?.onEvent?.({ event: 'message.delta', run_id: 'run-tools-running', session_id: 'session-1', content: '继续检查。', data: {} })
      options?.onEvent?.({
        event: 'tool.completed',
        run_id: 'run-tools-running',
        session_id: 'session-1',
        content: null,
        data: {
          tool_call_id: 'tool-assets-running',
          tool_name: 'list_workspace_render_assets',
          result: { total: 1 },
        },
      })
      options?.onEvent?.({
        event: 'tool.started',
        run_id: 'run-tools-running',
        session_id: 'session-1',
        content: null,
        data: {
          tool_call_id: 'tool-components-running',
          tool_name: 'list_workspace_components',
          tool_args: { limit: 20 },
        },
      })
      await new Promise<void>((resolve) => {
        releaseStream = resolve
      })
    })

    render(AgentConversationPanel, createTestingRenderOptions())

    await waitFor(() => {
      expect(listAgentsMock).toHaveBeenCalled()
    })

    await fireEvent.update(
      screen.getByPlaceholderText(DEFAULT_PLACEHOLDER),
      '连续检查资源和组件',
    )
    await fireEvent.click(screen.getByRole('button', { name: /发送/ }))

    await waitFor(() => {
      expect(screen.getByText('2 次工具调用 · 1 进行中 / 1 已完成')).toBeTruthy()
    })
    const details = screen.getByText('2 次工具调用 · 1 进行中 / 1 已完成').closest('details')
    expect(details?.hasAttribute('open')).toBe(true)
    expect(screen.getByRole('button', { name: 'list_workspace_components' })).toBeTruthy()

    releaseStream()
  })

  it('工具调用后的流式输出应形成独立 reasoning、tool 和 assistant 时间线项', async () => {
    let releaseStream = () => {}
    streamAgentRunEventsByRunIdMock.mockImplementationOnce(async (_runId: string, _payload: unknown, options?: { onEvent?: (event: any) => void }) => {
      options?.onEvent?.({ event: 'run.started', run_id: 'run-segmented-stream', session_id: 'session-1', content: null, data: {} })
      options?.onEvent?.({
        event: 'message.delta',
        run_id: 'run-segmented-stream',
        session_id: 'session-1',
        content: '',
        data: { reasoning_content: '先确认需要读取资源' },
      })
      options?.onEvent?.({
        event: 'tool.completed',
        run_id: 'run-segmented-stream',
        session_id: 'session-1',
        content: null,
        data: {
          tool_call_id: 'tool-segmented-assets',
          tool_name: 'list_workspace_render_assets',
          result: { total: 1, items: ['hero.png'] },
        },
      })
      options?.onEvent?.({
        event: 'message.delta',
        run_id: 'run-segmented-stream',
        session_id: 'session-1',
        content: '资源检查完成，建议继续使用 hero.png。',
        data: {},
      })
      await new Promise<void>((resolve) => {
        releaseStream = resolve
      })
    })

    render(AgentConversationPanel, createTestingRenderOptions())

    await waitFor(() => {
      expect(listAgentsMock).toHaveBeenCalled()
    })

    await fireEvent.update(
      screen.getByPlaceholderText(DEFAULT_PLACEHOLDER),
      '检查资源后给建议',
    )
    await fireEvent.click(screen.getByRole('button', { name: /发送/ }))

    await waitFor(() => {
      expect(screen.getByText('资源检查完成，建议继续使用 hero.png。')).toBeTruthy()
    })

    const toolArticle = screen.getByRole('button', { name: 'list_workspace_render_assets' }).closest('article')
    const answerArticle = screen.getByText('资源检查完成，建议继续使用 hero.png。').closest('article')
    const reasoningArticle = screen.getByText(/思考(中|过程)/).closest('article')
    expect(toolArticle).toBeTruthy()
    expect(answerArticle).toBeTruthy()
    expect(reasoningArticle).not.toBe(toolArticle)
    expect(answerArticle).not.toBe(toolArticle)

    releaseStream()
  })

  it('run.completed 若携带聚合内容，不应覆盖已流式渲染的助手正文', async () => {
    const finalMessages = [
      {
        id: 'message-user-1',
        role: 'user',
        content: '检查当前页面资源',
        created_at: '2026-04-18T10:00:00+08:00',
        tool_name: null,
        tool_call_id: null,
        tool_args: null,
        tool_call_error: null,
      },
      {
        id: 'message-assistant-1',
        role: 'assistant',
        content: '我已经完成资源检查。',
        created_at: '2026-04-18T10:00:02+08:00',
        tool_name: null,
        tool_call_id: null,
        tool_args: null,
        tool_call_error: null,
      },
    ]
    getAgentSessionMessagesMock
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce(finalMessages)
    getAgentSessionRuntimeMock
      .mockResolvedValueOnce(createRuntimeSnapshot())
      .mockResolvedValue(createRuntimeSnapshot({ messages: finalMessages }))

    streamAgentRunEventsByRunIdMock.mockImplementationOnce(async (_runId: string, _payload: unknown, options?: { onEvent?: (event: any) => void }) => {
      options?.onEvent?.({ event: 'run.started', run_id: 'run-aggregate', session_id: 'session-1', content: null, data: {} })
      options?.onEvent?.({ event: 'message.delta', run_id: 'run-aggregate', session_id: 'session-1', content: '我先读取页面资源。', data: {} })
      options?.onEvent?.({
        event: 'run.completed',
        run_id: 'run-aggregate',
        session_id: 'session-1',
        content: '{"total":2,"items":["hero.png","cover.png"]}',
        data: {},
      })
    })

    render(AgentConversationPanel, createTestingRenderOptions())

    await waitFor(() => {
      expect(listAgentsMock).toHaveBeenCalled()
    })

    await fireEvent.update(
      screen.getByPlaceholderText(DEFAULT_PLACEHOLDER),
      '检查当前页面资源',
    )
    await fireEvent.click(screen.getByRole('button', { name: /发送/ }))

    await waitFor(() => {
      expect(screen.getByText('我已经完成资源检查。')).toBeTruthy()
    })

    expect(screen.queryByText(/"total":2/)).toBeNull()
  })

  it('应将 think 内容显示为默认折叠的思考过程', async () => {
    streamAgentRunEventsByRunIdMock.mockImplementationOnce(async (_runId: string, _payload: unknown, options?: { onEvent?: (event: any) => void }) => {
      options?.onEvent?.({ event: 'run.started', run_id: 'run-think', session_id: 'session-1', content: null, data: {} })
      options?.onEvent?.({
        event: 'message.delta',
        run_id: 'run-think',
        session_id: 'session-1',
        content: '<think>先判断用户意图</think>\n你好！',
        data: {},
      })
      options?.onEvent?.({ event: 'run.completed', run_id: 'run-think', session_id: 'session-1', content: null, data: {} })
    })

    render(AgentConversationPanel, createTestingRenderOptions())

    await waitFor(() => {
      expect(listAgentsMock).toHaveBeenCalled()
    })

    await fireEvent.update(
      screen.getByPlaceholderText(DEFAULT_PLACEHOLDER),
      '你好',
    )
    await fireEvent.click(screen.getByRole('button', { name: /发送/ }))

    await waitFor(() => {
      expect(screen.getByText('你好！')).toBeTruthy()
    })
    const summary = screen.getByText('思考过程')
    const details = summary.closest('details')
    expect(details).toBeTruthy()
    expect(details?.hasAttribute('open')).toBe(false)
    expect(screen.queryByText(/<think>/)).toBeNull()
  })

  it('流式思考片段不应被额外插入换行', async () => {
    let releaseStream = () => {}
    streamAgentRunEventsByRunIdMock.mockImplementationOnce(async (_runId: string, _payload: unknown, options?: { onEvent?: (event: any) => void }) => {
      options?.onEvent?.({ event: 'run.started', run_id: 'run-reasoning-delta', session_id: 'session-1', content: null, data: {} })
      options?.onEvent?.({
        event: 'message.delta',
        run_id: 'run-reasoning-delta',
        session_id: 'session-1',
        content: '',
        data: { reasoning_content: '先' },
      })
      options?.onEvent?.({
        event: 'message.delta',
        run_id: 'run-reasoning-delta',
        session_id: 'session-1',
        content: '',
        data: { reasoning_content: '判断用户意图' },
      })
      await new Promise<void>((resolve) => {
        releaseStream = resolve
      })
      options?.onEvent?.({
        event: 'run.completed',
        run_id: 'run-reasoning-delta',
        session_id: 'session-1',
        content: null,
        data: { reasoning_content: '先判断用户意图' },
      })
    })

    render(AgentConversationPanel, createTestingRenderOptions())

    await waitFor(() => {
      expect(listAgentsMock).toHaveBeenCalled()
    })

    await fireEvent.update(
      screen.getByPlaceholderText(DEFAULT_PLACEHOLDER),
      '你好',
    )
    await fireEvent.click(screen.getByRole('button', { name: /发送/ }))

    await waitFor(() => {
      expect(screen.getByText('思考中')).toBeTruthy()
    })
    const details = screen.getByText('思考中').closest('details')
    const reasoningText = details?.querySelector('.reasoning-markdown')?.textContent
    expect(reasoningText).toBe('先判断用户意图')
    expect(reasoningText).not.toContain('先\n判断')

    releaseStream()
  })

  it('流式思考片段应即时保留模型输出的换行', async () => {
    let releaseStream = () => {}
    streamAgentRunEventsByRunIdMock.mockImplementationOnce(async (_runId: string, _payload: unknown, options?: { onEvent?: (event: any) => void }) => {
      options?.onEvent?.({ event: 'run.started', run_id: 'run-reasoning-newline', session_id: 'session-1', content: null, data: {} })
      options?.onEvent?.({
        event: 'message.delta',
        run_id: 'run-reasoning-newline',
        session_id: 'session-1',
        content: '',
        data: { reasoning_content: '第一步' },
      })
      options?.onEvent?.({
        event: 'message.delta',
        run_id: 'run-reasoning-newline',
        session_id: 'session-1',
        content: '',
        data: { reasoning_content: '\n' },
      })
      options?.onEvent?.({
        event: 'message.delta',
        run_id: 'run-reasoning-newline',
        session_id: 'session-1',
        content: '',
        data: { reasoning_content: '第二步' },
      })
      await new Promise<void>((resolve) => {
        releaseStream = resolve
      })
    })

    render(AgentConversationPanel, createTestingRenderOptions())

    await waitFor(() => {
      expect(listAgentsMock).toHaveBeenCalled()
    })

    await fireEvent.update(
      screen.getByPlaceholderText(DEFAULT_PLACEHOLDER),
      '你好',
    )
    await fireEvent.click(screen.getByRole('button', { name: /发送/ }))

    await waitFor(() => {
      expect(screen.getByText('思考中')).toBeTruthy()
    })
    await waitFor(() => {
      const details = screen.getByText('思考中').closest('details')
      const reasoningText = details?.querySelector('.reasoning-markdown')?.textContent
      expect(reasoningText).toContain('第一步\n第二步')
    })

    releaseStream()
  })

  it('历史记录中的工具调用详情应保留输入输出，不应出现空白弹窗', async () => {
    localStorage.setItem('agent-session:agent-coordinator:11', 'session-1')
    listAgentSessionsMock.mockResolvedValueOnce([
      {
        session_id: 'session-1',
        agent_id: DEFAULT_AGENT_ID,
        session_name: '历史资源排查',
        created_at: '2026-04-18T10:00:00+08:00',
        updated_at: '2026-04-18T10:20:00+08:00',
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
    const historyMessages = [
      {
        id: 'message-assistant-1',
        role: 'assistant',
        content: '我已经完成资源排查。',
        created_at: '2026-04-18T10:00:02+08:00',
        tool_name: null,
        tool_call_id: null,
        tool_args: null,
        tool_call_error: null,
      },
      {
        id: 'message-tool-1',
        role: 'tool',
        content: '{"total":2,"items":["hero.png","cover.png"]}',
        created_at: '2026-04-18T10:00:03+08:00',
        tool_name: 'list_workspace_render_assets',
        tool_call_id: 'tool-history-1',
        tool_args: {
          workspace_id: 11,
          limit: 20,
        },
        tool_call_error: null,
      },
    ]
    getAgentSessionMessagesMock.mockResolvedValueOnce(historyMessages)
    getAgentSessionRuntimeMock.mockResolvedValueOnce(createRuntimeSnapshot({
      messages: historyMessages,
    }))

    render(AgentConversationPanel, createTestingRenderOptions())

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'list_workspace_render_assets' })).toBeTruthy()
    })

    await fireEvent.click(screen.getByRole('button', { name: 'list_workspace_render_assets' }))

    await waitFor(() => {
      expect(screen.getByText('工具输入')).toBeTruthy()
      expect(screen.getByText(/"workspace_id": 11/)).toBeTruthy()
      expect(screen.getByText(/hero\.png/)).toBeTruthy()
      expect(screen.getByText(/tool-history-1/)).toBeTruthy()
    })
  })

  it('未绑定模型时应展示空状态并允许跳转到管理页', async () => {
    listAgentsMock.mockResolvedValueOnce([
      {
        id: 'agent-coordinator',
        name: '内容助手',
        icon: 'content-spark',
        summary: '帮助你分析页面与生成修改建议。',
        default_session_name: '内容助手会话',
        capabilities: ['组件依赖分析'],
        llm_slot: 'agent_coordinator',
        llm_binding_ready: false,
        bound_llm_name: null,
        bound_provider_label: null,
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
      expect(screen.getByText('内容助手尚未绑定模型')).toBeTruthy()
    })

    expect(screen.getByRole('button', { name: '新会话' })).toHaveProperty('disabled', true)
    await fireEvent.click(screen.getByRole('button', { name: '前往 AI 设置' }))
    expect(routerPushMock).toHaveBeenCalledWith({ name: 'accountAiSettings' })
  })

  it('页面写回冲突时应展示内联错误说明', async () => {
    streamAgentRunEventsByRunIdMock.mockImplementationOnce(async (_runId: string, _payload: unknown, options?: { onEvent?: (event: any) => void }) => {
      options?.onEvent?.({ event: 'run.started', run_id: 'run-error', session_id: 'session-1', content: null, data: {} })
      options?.onEvent?.({
        event: 'run.error',
        run_id: 'run-error',
        session_id: 'session-1',
        content: null,
        data: {
          message: 'Unified Diff 无法应用：上下文内容不匹配。 hunk #1 第 3 行期望 \'foo\'，实际为 \'bar\'。',
        },
      })
    })

    render(AgentConversationPanel, createTestingRenderOptions())

    await waitFor(() => {
      expect(listAgentsMock).toHaveBeenCalled()
    })

    await fireEvent.update(
      screen.getByPlaceholderText(DEFAULT_PLACEHOLDER),
      '帮我优化一下页面',
    )
    await fireEvent.click(screen.getByRole('button', { name: /发送/ }))

    await waitFor(() => {
      expect(screen.getByText('页面写回失败')).toBeTruthy()
      expect(screen.getByText(/请先重新读取当前页面源码/)).toBeTruthy()
    })
    expect(messageErrorMock).toHaveBeenCalledWith(expect.stringContaining('请先重新读取当前页面源码'))
  })
})

