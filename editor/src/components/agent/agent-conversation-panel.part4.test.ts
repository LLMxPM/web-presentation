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
    expect(messageWarningMock).toHaveBeenCalledWith('页面写回失败')
  })
})
