/**
 * 文件功能：验证智能体 API 的 scope 查询参数，避免全局入口被默认 agent_id 过滤。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { fetchMock, getMock } = vi.hoisted(() => ({
  fetchMock: vi.fn(),
  getMock: vi.fn(),
}))

vi.mock('@/api/http', () => ({
  http: {
    get: getMock,
  },
  resolveApiBaseUrl: () => '',
  getErrorMessage: (_error: unknown, fallback: string) => fallback,
}))

import {
  AgentStreamInterruptedError,
  continueAgentSessionActiveRun,
  getAgentSessionContextStatus,
  listAgents,
  listAgentSessions,
  streamAgentRun,
} from '@/api/ai'
import type { AgentScopeContext } from '@/types/api'

describe('ai api', () => {
  const scope: AgentScopeContext = {
    scope_type: 'project',
    workspace_id: 11,
    project_id: 21,
    page_id: null,
    component_id: null,
    source: 'editor-agent-sidebar',
  }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('fetch', fetchMock)
  })

  it('拉取智能体列表时不应默认带指定智能体过滤', async () => {
    getMock.mockResolvedValueOnce({ data: [] })

    await listAgents(scope)

    expect(getMock).toHaveBeenCalledWith('/ai/agents', {
      params: {
        scope_type: 'project',
        workspace_id: '11',
        source: 'editor-agent-sidebar',
        project_id: '21',
      },
    })
  })

  it('会话列表默认限定内容助手入口', async () => {
    getMock.mockResolvedValueOnce({ data: [] })

    await listAgentSessions(scope)

    expect(getMock).toHaveBeenCalledWith('/ai/sessions', {
      params: {
        scope_type: 'project',
        workspace_id: '11',
        source: 'editor-agent-sidebar',
        agent_id: 'agent-coordinator',
        scope_mode: 'exact',
        project_id: '21',
      },
    })
  })

  it('会话列表可请求当前工作空间内同智能体全量会话', async () => {
    getMock.mockResolvedValueOnce({ data: [] })

    await listAgentSessions(scope, 'agent-coordinator', 'workspace')

    expect(getMock).toHaveBeenCalledWith('/ai/sessions', {
      params: {
        scope_type: 'project',
        workspace_id: '11',
        source: 'editor-agent-sidebar',
        agent_id: 'agent-coordinator',
        scope_mode: 'workspace',
        project_id: '21',
      },
    })
  })

  it('上下文状态接口应携带当前 scope 和 agent_id', async () => {
    getMock.mockResolvedValueOnce({ data: null })

    await getAgentSessionContextStatus('session-1', scope)

    expect(getMock).toHaveBeenCalledWith('/ai/sessions/session-1/context-status', {
      params: {
        scope_type: 'project',
        workspace_id: '11',
        source: 'editor-agent-sidebar',
        agent_id: 'agent-coordinator',
        project_id: '21',
      },
    })
  })

  it('流式运行和继续运行应透传 AbortSignal', async () => {
    const signal = new AbortController().signal
    const buildEmptyStreamResponse = () => new Response(new ReadableStream<Uint8Array>({
      start(controller) {
        controller.close()
      },
    }), { status: 200 })
    fetchMock.mockImplementation(() => Promise.resolve(buildEmptyStreamResponse()))

    await streamAgentRun('session-1', scope, { run_id: 'run-1', message: '开始' }, { signal })
    await continueAgentSessionActiveRun('session-1', scope, {
      decision: 'confirm',
      note: null,
      tool_execution: {},
    }, { signal })

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      expect.stringContaining('/ai/sessions/session-1/runs/stream'),
      expect.objectContaining({ signal }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      expect.stringContaining('/ai/sessions/session-1/active-run/continue'),
      expect.objectContaining({ signal }),
    )
  })

  it('继续结构化提问时应提交 feedback selections', async () => {
    fetchMock.mockResolvedValueOnce(new Response(new ReadableStream<Uint8Array>({
      start(controller) {
        controller.close()
      },
    }), { status: 200 }))

    await continueAgentSessionActiveRun('session-1', scope, {
      decision: null,
      tool_execution: { tool_name: 'ask_user' },
      feedback_selections: [
        { question: '目标区域？', selected_label: '首屏', custom_text: null },
        { question: '视觉风格？', selected_label: null, custom_text: '保留图标风格' },
      ],
    })

    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body))
    expect(body).toEqual(expect.objectContaining({
      decision: null,
      feedback_selections: [
        { question: '目标区域？', selected_label: '首屏', custom_text: null },
        { question: '视觉风格？', selected_label: null, custom_text: '保留图标风格' },
      ],
    }))
  })

  it('fetch 被 AbortController 中断时应抛出流式中断错误', async () => {
    fetchMock.mockRejectedValueOnce(Object.assign(new Error('aborted'), { name: 'AbortError' }))

    await expect(streamAgentRun('session-1', scope, { run_id: 'run-abort', message: '开始' }))
      .rejects
      .toBeInstanceOf(AgentStreamInterruptedError)
  })

  it('读取 SSE body 时被中断也应抛出流式中断错误', async () => {
    const abortError = Object.assign(new Error('aborted'), { name: 'AbortError' })
    fetchMock.mockResolvedValueOnce(new Response(new ReadableStream<Uint8Array>({
      pull(controller) {
        controller.error(abortError)
      },
    }), { status: 200 }))

    await expect(streamAgentRun('session-1', scope, { run_id: 'run-body-abort', message: '开始' }))
      .rejects
      .toBeInstanceOf(AgentStreamInterruptedError)
  })

  it('SSE 解析应兼容 CRLF 与心跳注释行', async () => {
    const events: unknown[] = []
    const encoder = new TextEncoder()
    fetchMock.mockResolvedValueOnce(new Response(new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode(': ping\r\nevent: message.delta\r\ndata: {"event":"message.delta","run_id":"run-1","session_id":"session-1","content":"你好","data":{},"sequence":2}\r\n\r\n'))
        controller.close()
      },
    }), { status: 200 }))

    await streamAgentRun('session-1', scope, { run_id: 'run-sse', message: '开始' }, {
      onEvent: event => events.push(event),
    })

    expect(events).toEqual([
      expect.objectContaining({
        event: 'message.delta',
        run_id: 'run-1',
        content: '你好',
        sequence: 2,
      }),
    ])
  })

  it('SSE 解析应支持跨 chunk 和多 data 行', async () => {
    const events: unknown[] = []
    const encoder = new TextEncoder()
    fetchMock.mockResolvedValueOnce(new Response(new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode('event: message.delta\ndata: {"event":"message.delta",'))
        controller.enqueue(encoder.encode('\ndata: "run_id":"run-1","session_id":"session-1","content":"多行正文","data":{},"sequence":3}\n\n'))
        controller.close()
      },
    }), { status: 200 }))

    await streamAgentRun('session-1', scope, { run_id: 'run-sse-chunks', message: '开始' }, {
      onEvent: event => events.push(event),
    })

    expect(events).toEqual([
      expect.objectContaining({
        event: 'message.delta',
        run_id: 'run-1',
        content: '多行正文',
        sequence: 3,
        event_index: 3,
      }),
    ])
  })

  it('SSE 解析应使用命名 event 补齐 payload event', async () => {
    const events: unknown[] = []
    const encoder = new TextEncoder()
    fetchMock.mockResolvedValueOnce(new Response(new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode('event: reasoning.delta\ndata: {"run_id":"run-1","session_id":"session-1","content":"先思考","data":{},"sequence":4}\n\n'))
        controller.close()
      },
    }), { status: 200 }))

    await streamAgentRun('session-1', scope, { run_id: 'run-sse-named', message: '开始' }, {
      onEvent: event => events.push(event),
    })

    expect(events).toEqual([
      expect.objectContaining({
        event: 'reasoning.delta',
        run_id: 'run-1',
        content: '先思考',
        sequence: 4,
      }),
    ])
  })

  it('SSE 解析遇到非法 JSON 时应回退为文本事件', async () => {
    const events: unknown[] = []
    const encoder = new TextEncoder()
    fetchMock.mockResolvedValueOnce(new Response(new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode('event: run.error\ndata: 模型连接中断\n\n'))
        controller.close()
      },
    }), { status: 200 }))

    await streamAgentRun('session-1', scope, { run_id: 'run-sse-invalid-json', message: '开始' }, {
      onEvent: event => events.push(event),
    })

    expect(events).toEqual([
      expect.objectContaining({
        event: 'run.error',
        content: '模型连接中断',
        data: {},
        sequence: null,
        event_index: null,
      }),
    ])
  })
})
