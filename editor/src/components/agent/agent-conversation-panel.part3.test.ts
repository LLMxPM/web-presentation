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
const listLlmConfigsMock = vi.fn()
const listLlmSlotsMock = vi.fn()
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

vi.mock('@/api/llm', () => ({
  listLlmConfigs: (...args: unknown[]) => listLlmConfigsMock(...args),
  listLlmSlots: (...args: unknown[]) => listLlmSlotsMock(...args),
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
    compression_status: 'idle',
    compression_method: 'none',
    compression_error_message: null,
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

function createLlmConfigItem(overrides: Record<string, unknown> = {}) {
  return {
    id: 7,
    scope: 'global',
    owner_user_id: null,
    editable: false,
    name: '平台模型',
    provider_key: 'openai',
    provider_label: 'OpenAI',
    model_id: 'gpt-4.1-mini',
    base_url: null,
    thinking_enabled: false,
    thinking_effort: null,
    supports_image_input: false,
    context_window_tokens: 128000,
    max_output_tokens: 32000,
    history_token_ratio: 0.5,
    compression_target_ratio: 0.1,
    advanced_config_json: {},
    status: 'active',
    has_api_key: true,
    api_key_masked: 'sk-****',
    created_at: '2026-04-18T10:00:00+08:00',
    updated_at: '2026-04-18T10:00:00+08:00',
    ...overrides,
  }
}

function createLlmSlotBindingItem(overrides: Record<string, unknown> = {}) {
  return {
    slot: 'agent_coordinator',
    slot_label: '内容助手',
    llm_config_id: 7,
    llm_config_name: '平台模型',
    provider_key: 'openai',
    provider_label: 'OpenAI',
    model_id: 'gpt-4.1-mini',
    binding_ready: true,
    supports_image_input: false,
    inherited_from_global: true,
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
    listLlmConfigsMock.mockResolvedValue([
      createLlmConfigItem({ id: 7, scope: 'global', name: '平台模型', supports_image_input: false }),
    ])
    listLlmSlotsMock.mockResolvedValue([
      createLlmSlotBindingItem({ slot: 'agent_coordinator', llm_config_id: 7, binding_ready: true }),
    ])
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
    getAgentSessionContextStatusMock.mockResolvedValue(createContextStatus())
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
      context_status: createContextStatus(),
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

  it('待确认工具应显示强制释放入口并提交 tool_call_id', async () => {
    localStorage.setItem('agent-session:agent-coordinator:11', 'session-1')
    listAgentSessionsMock.mockResolvedValue([
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
      run_id: 'run-paused-force',
      session_id: 'session-1',
      agent_id: DEFAULT_AGENT_ID,
      status: 'paused',
      pending_requirement: {
        id: null,
        kind: 'confirmation',
        run_id: 'run-paused-force',
        session_id: 'session-1',
        tool_name: 'apply_page_edits',
        tool_execution: { tool_name: 'apply_page_edits', tool_call_id: 'tool-force-confirm', tool_args: {} },
        suggested_patch: null,
        user_feedback_schema: [],
        note: null,
      },
      content: null,
      created_at: '2026-04-18T10:30:00+08:00',
    }
    getAgentSessionActiveRunMock.mockResolvedValueOnce(pausedRun)
    getAgentSessionRuntimeMock
      .mockResolvedValueOnce(createRuntimeSnapshot({
        active_run: pausedRun,
        pending_requirement: pausedRun.pending_requirement,
        event_index: -1,
      }))
      .mockResolvedValue(createRuntimeSnapshot())
    cancelAgentSessionActiveRunMock.mockResolvedValueOnce({
      run_id: 'run-paused-force',
      session_id: 'session-1',
      cancel_requested: true,
    })

    render(AgentConversationPanel, createTestingRenderOptions())

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '强制释放' })).toBeTruthy()
    })
    await fireEvent.click(screen.getByRole('button', { name: '强制释放' }))

    await waitFor(() => {
      expect(cancelAgentSessionActiveRunMock).toHaveBeenCalledWith(
        'session-1',
        expect.objectContaining({ page_id: 31 }),
        expect.objectContaining({
          agent_id: DEFAULT_AGENT_ID,
          force: true,
          tool_call_id: 'tool-force-confirm',
        }),
      )
    })
    expect(createConfirmMock).toHaveBeenCalledWith(
      expect.stringContaining('不会执行工具'),
      '强制释放 HITL',
    )
    expect(messageInfoMock).toHaveBeenCalledWith('已释放当前待处理动作。')
  })

  it('结构化提问应显示强制释放且不提交回答', async () => {
    localStorage.setItem('agent-session:agent-coordinator:11', 'session-1')
    listAgentSessionsMock.mockResolvedValueOnce([
      {
        session_id: 'session-1',
        agent_id: DEFAULT_AGENT_ID,
        session_name: '待回答会话',
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
      run_id: 'run-feedback-force',
      session_id: 'session-1',
      agent_id: DEFAULT_AGENT_ID,
      status: 'paused',
      pending_requirement: {
        id: null,
        kind: 'user_feedback',
        run_id: 'run-feedback-force',
        session_id: 'session-1',
        tool_name: 'ask_user',
        tool_execution: { tool_name: 'ask_user', tool_call_id: 'tool-force-feedback', tool_args: {} },
        suggested_patch: null,
        user_feedback_schema: [
          {
            question: '优先调整哪个区域？',
            header: '范围',
            options: [{ label: '首屏', description: null }, { label: '全页面', description: null }],
            multi_select: false,
            selected_options: null,
          },
        ],
        note: null,
      },
      content: null,
      created_at: '2026-04-18T10:30:00+08:00',
    }
    getAgentSessionActiveRunMock.mockResolvedValueOnce(pausedRun)
    getAgentSessionRuntimeMock
      .mockResolvedValueOnce(createRuntimeSnapshot({
        active_run: pausedRun,
        pending_requirement: pausedRun.pending_requirement,
        event_index: -1,
      }))
      .mockResolvedValue(createRuntimeSnapshot())
    cancelAgentSessionActiveRunMock.mockResolvedValueOnce({
      run_id: 'run-feedback-force',
      session_id: 'session-1',
      cancel_requested: true,
    })

    render(AgentConversationPanel, createTestingRenderOptions())

    await waitFor(() => {
      expect(screen.getByText('优先调整哪个区域？')).toBeTruthy()
      expect(screen.getByRole('button', { name: '强制释放' })).toBeTruthy()
    })
    await fireEvent.click(screen.getByRole('button', { name: '强制释放' }))

    await waitFor(() => {
      expect(cancelAgentSessionActiveRunMock).toHaveBeenCalledWith(
        'session-1',
        expect.objectContaining({ page_id: 31 }),
        expect.objectContaining({
          agent_id: DEFAULT_AGENT_ID,
          force: true,
          tool_call_id: 'tool-force-feedback',
        }),
      )
    })
    expect(continueAgentSessionActiveRunMock).not.toHaveBeenCalled()
  })

  it('结构化提问提交后应隐藏待回答提示并显示已回复状态', async () => {
    localStorage.setItem('agent-session:agent-coordinator:11', 'session-1')
    listAgentSessionsMock.mockResolvedValueOnce([
      {
        session_id: 'session-1',
        agent_id: DEFAULT_AGENT_ID,
        session_name: '待回答会话',
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
    const requirement: AgentPendingRequirement = {
      id: null,
      kind: 'user_feedback',
      run_id: 'run-feedback-submit',
      session_id: 'session-1',
      tool_name: 'ask_user',
      tool_execution: { tool_name: 'ask_user', tool_call_id: 'tool-feedback-submit', tool_args: {} },
      suggested_patch: null,
      user_feedback_schema: [
        {
          question: '优先调整哪个区域？',
          header: '范围',
          options: [{ label: '首屏', description: null }, { label: '全页面', description: null }],
          multi_select: false,
          selected_options: null,
        },
      ],
      note: null,
    }
    const pausedRun = {
      run_id: requirement.run_id,
      session_id: 'session-1',
      agent_id: DEFAULT_AGENT_ID,
      status: 'paused',
      pending_requirement: requirement,
      content: null,
      created_at: '2026-04-18T10:30:00+08:00',
    }
    getAgentSessionRuntimeMock.mockResolvedValueOnce(createRuntimeSnapshot({
      timeline_items: [
        {
          id: 'tool-feedback-submit',
          session_id: 'session-1',
          run_id: requirement.run_id,
          kind: 'tool',
          role: null,
          event_index: 1,
          order_index: 0,
          content: null,
          status: 'running',
          tool: {
            tool_call_id: 'tool-feedback-submit',
            tool_name: 'ask_user',
            status: 'running',
            input_payload: { questions: requirement.user_feedback_schema },
            output_payload: null,
            message: '',
          },
          attachments: [],
          source: 'event',
          created_at: '2026-04-18T10:30:00+08:00',
        },
        {
          id: 'requirement-feedback-submit',
          session_id: 'session-1',
          run_id: requirement.run_id,
          kind: 'requirement',
          role: null,
          event_index: 2,
          order_index: 1,
          content: '优先调整哪个区域？',
          status: 'pending',
          tool: null,
          attachments: [],
          source: 'event',
          created_at: '2026-04-18T10:30:01+08:00',
        },
      ],
      active_run: pausedRun,
      pending_requirement: requirement,
      event_index: 2,
    }))
    const continueDeferred = createDeferred<void>()
    continueAgentSessionActiveRunMock.mockImplementationOnce(async () => {
      await continueDeferred.promise
    })

    render(AgentConversationPanel, createTestingRenderOptions())

    await waitFor(() => {
      expect(screen.getByText('优先调整哪个区域？')).toBeTruthy()
      expect(screen.getByRole('button', { name: /提交回答/ })).toBeTruthy()
    })
    await fireEvent.click(screen.getByText('首屏'))
    await fireEvent.click(screen.getByRole('button', { name: /提交回答/ }))

    await waitFor(() => {
      expect(continueAgentSessionActiveRunMock).toHaveBeenCalled()
      expect(screen.queryByRole('button', { name: /提交回答/ })).toBeNull()
      expect(screen.getByText('等待智能体输出中')).toBeTruthy()
      expect(screen.getByText('首屏')).toBeTruthy()
      expect(screen.queryByText('未回复')).toBeNull()
    })
    continueDeferred.resolve()
  })

  it('paused 结构化提问不应因残留 streaming 状态禁用提交按钮', async () => {
    localStorage.setItem('agent-session:agent-coordinator:11', 'session-1')
    listAgentSessionsMock.mockResolvedValueOnce([
      {
        session_id: 'session-1',
        agent_id: DEFAULT_AGENT_ID,
        session_name: '待回答会话',
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
      run_id: 'run-feedback-loading',
      session_id: 'session-1',
      agent_id: DEFAULT_AGENT_ID,
      status: 'paused',
      pending_requirement: {
        id: null,
        kind: 'user_feedback',
        run_id: 'run-feedback-loading',
        session_id: 'session-1',
        tool_name: 'ask_user',
        tool_execution: { tool_name: 'ask_user', tool_call_id: 'tool-feedback-loading', tool_args: {} },
        suggested_patch: null,
        user_feedback_schema: [
          {
            question: '优先调整哪个区域？',
            header: '范围',
            options: [{ label: '首屏', description: null }, { label: '全页面', description: null }],
            multi_select: false,
            selected_options: null,
          },
        ],
        note: null,
      },
      content: null,
      created_at: '2026-04-18T10:30:00+08:00',
    }
    getAgentSessionRuntimeMock.mockResolvedValueOnce(createRuntimeSnapshot({
      active_run: pausedRun,
      pending_requirement: pausedRun.pending_requirement,
      event_index: -1,
    }))
    const pinia = createPinia()
    setActivePinia(pinia)
    render(AgentConversationPanel, createTestingRenderOptions({}, pinia))

    await waitFor(() => {
      expect(screen.getByText('优先调整哪个区域？')).toBeTruthy()
    })
    await fireEvent.click(screen.getByText('首屏'))
    useAgentSessionStore().setStreaming('session-1', true)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /提交回答/ })).toHaveProperty('disabled', false)
    })
  })

  it('running activeRun 不应从残留 pending map 恢复旧 ask_user', async () => {
    localStorage.setItem('agent-session:agent-coordinator:11', 'session-1')
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
    const staleRequirement: AgentPendingRequirement = {
      id: 'req-stale-ask',
      kind: 'user_feedback',
      run_id: 'run-feedback-stale',
      session_id: 'session-1',
      tool_name: 'ask_user',
      tool_execution: { tool_name: 'ask_user', tool_call_id: 'tool-feedback-stale', tool_args: {} },
      suggested_patch: null,
      user_feedback_schema: [
        {
          question: '这个问题不应出现',
          header: '范围',
          options: [{ label: '首屏', description: null }, { label: '全页面', description: null }],
          multi_select: false,
          selected_options: null,
        },
      ],
      note: null,
    }
    getAgentSessionRuntimeMock.mockResolvedValueOnce(createRuntimeSnapshot({
      active_run: {
        run_id: 'run-feedback-stale',
        session_id: 'session-1',
        agent_id: DEFAULT_AGENT_ID,
        status: 'running',
        pending_requirement: null,
        content: null,
        created_at: '2026-04-18T10:30:00+08:00',
      },
      pending_requirement: null,
      event_index: -1,
    }))
    const pinia = createPinia()
    setActivePinia(pinia)
    render(AgentConversationPanel, createTestingRenderOptions({}, pinia))

    await waitFor(() => {
      expect(getAgentSessionRuntimeMock).toHaveBeenCalled()
    })
    useAgentSessionStore().setPendingRequirement('session-1', staleRequirement)

    await waitFor(() => {
      expect(screen.queryByText('这个问题不应出现')).toBeNull()
    })
  })

  it('强制释放失败时应恢复原 HITL 界面', async () => {
    localStorage.setItem('agent-session:agent-coordinator:11', 'session-1')
    listAgentSessionsMock.mockResolvedValue([
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
      run_id: 'run-force-failed',
      session_id: 'session-1',
      agent_id: DEFAULT_AGENT_ID,
      status: 'paused',
      pending_requirement: {
        id: null,
        kind: 'confirmation',
        run_id: 'run-force-failed',
        session_id: 'session-1',
        tool_name: 'apply_page_edits',
        tool_execution: { tool_name: 'apply_page_edits', tool_call_id: 'tool-force-failed', tool_args: {} },
        suggested_patch: null,
        user_feedback_schema: [],
        note: null,
      },
      content: null,
      created_at: '2026-04-18T10:30:00+08:00',
    }
    getAgentSessionActiveRunMock.mockResolvedValueOnce(pausedRun)
    getAgentSessionRuntimeMock
      .mockResolvedValueOnce(createRuntimeSnapshot({
        active_run: pausedRun,
        pending_requirement: pausedRun.pending_requirement,
        event_index: -1,
      }))
      .mockResolvedValue(createRuntimeSnapshot({
        active_run: pausedRun,
        pending_requirement: pausedRun.pending_requirement,
        event_index: -1,
      }))
    cancelAgentSessionActiveRunMock.mockRejectedValueOnce(new Error('force failed'))

    render(AgentConversationPanel, createTestingRenderOptions())

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '强制释放' })).toBeTruthy()
    })
    await fireEvent.click(screen.getByRole('button', { name: '强制释放' }))

    await waitFor(() => {
      expect(messageErrorMock).toHaveBeenCalledWith(expect.stringContaining('force failed'))
    })
    expect(screen.getByText('允许执行 apply_page_edits 吗？')).toBeTruthy()
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

})
