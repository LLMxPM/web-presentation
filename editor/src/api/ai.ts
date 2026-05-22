/**
 * 文件功能：封装内容助手相关接口，包括会话管理、消息查询和 SSE 流式运行。
 */
import { getErrorMessage, http, notifyUnauthorized, resolveApiBaseUrl } from '@/api/http'
import type {
  AgentActiveRunItem,
  AgentContextStatusItem,
  AgentDescriptor,
  AgentImageAttachmentItem,
  AgentMessageItem,
  AgentRunCancelResponse,
  AgentRunEvent,
  AgentRunStartResponse,
  AgentScopeContext,
  AgentSessionItem,
  AgentSessionRuntimeSnapshot,
} from '@/types/api'

export interface AgentStreamOptions {
  onEvent?: (event: AgentRunEvent) => void
  signal?: AbortSignal
}

export class AgentStreamInterruptedError extends Error {
  /** 标识用户主动中断了当前流式传输，调用方不应按执行失败展示。 */
  constructor(message = '智能体流式传输已中断。') {
    super(message)
    this.name = 'AgentStreamInterruptedError'
  }
}

export class AgentRequestError extends Error {
  /** 后端业务错误码，用于页面层按语义恢复状态。 */
  code: string | null

  constructor(message: string, code: string | null = null) {
    super(message)
    this.name = 'AgentRequestError'
    this.code = code
  }
}

/**
 * 仅在 Vite 开发模式输出调试日志，帮助排查 Agent 流式交互问题。
 */
function logAgentDev(stage: string, payload?: unknown) {
  if (!import.meta.env.DEV) {
    return
  }
  console.debug(`[agent:${stage}]`, payload)
}

/**
 * 读取当前页面范围内可用的智能体列表。
 */
export async function listAgents(scope: AgentScopeContext, agentId?: string) {
  const { data } = await http.get<AgentDescriptor[]>('/ai/agents', {
    params: buildScopeParams(scope, agentId),
  })
  return data
}

/**
 * 查询当前页面范围内的智能体会话列表。
 */
export async function listAgentSessions(scope: AgentScopeContext, agentId = 'agent-coordinator') {
  const { data } = await http.get<AgentSessionItem[]>('/ai/sessions', {
    params: buildScopeParams(scope, agentId),
  })
  return data
}

/**
 * 创建新的内容助手会话。
 */
export async function createAgentSession(payload: {
  agent_id?: string
  session_name?: string | null
  scope: AgentScopeContext
}) {
  const { data } = await http.post<AgentSessionItem>('/ai/sessions', payload)
  return data
}

/**
 * 查询会话历史消息。
 */
export async function getAgentSessionMessages(sessionId: string, scope: AgentScopeContext, agentId = 'agent-coordinator') {
  const { data } = await http.get<AgentMessageItem[]>(`/ai/sessions/${sessionId}/messages`, {
    params: buildScopeParams(scope, agentId),
  })
  return data
}

/**
 * 一次性读取当前会话的运行时快照，用于刷新或切会话后恢复 UI。
 */
export async function getAgentSessionRuntime(sessionId: string, scope: AgentScopeContext, agentId = 'agent-coordinator') {
  const { data } = await http.get<AgentSessionRuntimeSnapshot>(`/ai/sessions/${sessionId}/runtime`, {
    params: buildScopeParams(scope, agentId),
  })
  return data
}

/**
 * 重命名已存在的内容助手会话，或触发 Agno 自动生成名称。
 */
export async function renameAgentSession(
  sessionId: string,
  scope: AgentScopeContext,
  payload: {
    session_name?: string | null
    autogenerate?: boolean
  },
  agentId = 'agent-coordinator',
) {
  const { data } = await http.patch<AgentSessionItem>(`/ai/sessions/${sessionId}`, {
    session_name: payload.session_name ?? null,
    autogenerate: payload.autogenerate ?? false,
  }, {
    params: buildScopeParams(scope, agentId),
  })
  return data
}

/**
 * 启动一次智能体运行，并通过 SSE 回传流式事件。
 */
export async function streamAgentRun(
  sessionId: string,
  scope: AgentScopeContext,
  payload: { message: string; agent_id?: string; image_attachment_ids?: number[] },
  options: AgentStreamOptions = {},
) {
  logAgentDev('run.start', { sessionId, scope, payload })
  await streamSse(
    `/ai/sessions/${sessionId}/runs/stream?${buildScopeQuery(scope, payload.agent_id)}`,
    {
      method: 'POST',
      body: JSON.stringify({
        message: payload.message,
        image_attachment_ids: payload.image_attachment_ids ?? [],
      }),
    },
    options,
  )
}

/**
 * 启动一次后台智能体运行；事件需要再通过 run_id 订阅。
 */
export async function startAgentRun(
  sessionId: string,
  scope: AgentScopeContext,
  payload: { message: string; agent_id?: string; image_attachment_ids?: number[] },
) {
  const { data } = await http.post<AgentRunStartResponse>(
    `/ai/sessions/${sessionId}/runs`,
    {
      message: payload.message,
      image_attachment_ids: payload.image_attachment_ids ?? [],
    },
    {
      params: buildScopeParams(scope, payload.agent_id ?? 'agent-coordinator'),
    },
  )
  return data
}

/**
 * 订阅已存在后台 run 的事件流，先回放历史事件再接收 live 事件。
 */
export async function streamAgentRunEvents(
  sessionId: string,
  runId: string,
  scope: AgentScopeContext,
  payload: { agent_id?: string; after_sequence?: number },
  options: AgentStreamOptions = {},
) {
  logAgentDev('run.events.subscribe', { sessionId, runId, scope, payload })
  await streamSse(
    `/ai/sessions/${sessionId}/runs/${runId}/events/stream?${buildScopeQuery(scope, payload.agent_id, {
      after_sequence: String(payload.after_sequence ?? 0),
    })}`,
    {
      method: 'GET',
    },
    options,
  )
}

/**
 * 按 run_id 订阅后台事件，接口会先回放历史事件再返回 live 事件。
 */
export async function streamAgentRunEventsByRunId(
  runId: string,
  payload: { after_sequence?: number },
  options: AgentStreamOptions = {},
) {
  logAgentDev('run.events.subscribe-by-run', { runId, payload })
  await streamSse(
    `/ai/runs/${runId}/events?${new URLSearchParams({
      after_sequence: String(payload.after_sequence ?? 0),
    }).toString()}`,
    {
      method: 'GET',
    },
    options,
  )
}

/**
 * 上传会话图片附件，后续 run 会通过 attachment id 引用。
 */
export async function uploadAgentImageAttachment(
  sessionId: string,
  scope: AgentScopeContext,
  file: File,
  agentId = 'agent-coordinator',
) {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await http.post<AgentImageAttachmentItem>(
    `/ai/sessions/${sessionId}/attachments/images`,
    formData,
    {
      params: buildScopeParams(scope, agentId),
    },
  )
  return data
}

/**
 * 删除尚未发送或不再需要的会话图片附件。
 */
export async function deleteAgentImageAttachment(
  sessionId: string,
  scope: AgentScopeContext,
  attachmentId: number,
  agentId = 'agent-coordinator',
) {
  await http.delete(`/ai/sessions/${sessionId}/attachments/images/${attachmentId}`, {
    params: buildScopeParams(scope, agentId),
  })
}

/**
 * 将会话图片附件保存为工作空间资源。
 */
export async function promoteAgentImageAttachment(
  sessionId: string,
  scope: AgentScopeContext,
  attachmentId: number,
  payload: {
    name?: string | null
    description?: string | null
    tags?: string[]
    overwrite?: boolean
  } = {},
  agentId = 'agent-coordinator',
) {
  const { data } = await http.post<AgentImageAttachmentItem>(
    `/ai/sessions/${sessionId}/attachments/images/${attachmentId}/promote`,
    {
      name: payload.name ?? null,
      description: payload.description ?? null,
      tags: payload.tags ?? [],
      overwrite: payload.overwrite ?? false,
    },
    {
      params: buildScopeParams(scope, agentId),
    },
  )
  return data
}

/**
 * 查询当前会话最近一次 Agno run 状态。
 */
export async function getAgentSessionActiveRun(sessionId: string, scope: AgentScopeContext, agentId = 'agent-coordinator') {
  const { data } = await http.get<AgentActiveRunItem | null>(`/ai/sessions/${sessionId}/active-run`, {
    params: buildScopeParams(scope, agentId),
  })
  return data
}

/**
 * 查询当前会话的上下文预算、压缩状态与摘要。
 */
export async function getAgentSessionContextStatus(sessionId: string, scope: AgentScopeContext, agentId = 'agent-coordinator') {
  const { data } = await http.get<AgentContextStatusItem>(`/ai/sessions/${sessionId}/context-status`, {
    params: buildScopeParams(scope, agentId),
  })
  return data
}

/**
 * 继续当前会话中暂停的智能体运行。
 */
export async function continueAgentSessionActiveRun(
  sessionId: string,
  scope: AgentScopeContext,
  payload: {
    decision?: 'confirm' | 'reject' | null
    note?: string | null
    tool_execution: Record<string, unknown>
    feedback_selections?: Array<{
      question: string
      selected_label?: string | null
      custom_text?: string | null
    }>
    agent_id?: string
  },
  options: AgentStreamOptions = {},
) {
  logAgentDev('run.continue', { sessionId, scope, payload })
  await streamSse(
    `/ai/sessions/${sessionId}/active-run/continue?${buildScopeQuery(scope, payload.agent_id)}`,
    {
      method: 'POST',
      body: JSON.stringify({
        session_id: sessionId,
        decision: payload.decision ?? null,
        note: payload.note ?? null,
        tool_execution: payload.tool_execution,
        feedback_selections: payload.feedback_selections ?? [],
      }),
    },
    options,
  )
}

/**
 * 按 run_id 继续暂停运行。
 */
export async function continueAgentRun(
  runId: string,
  payload: {
    decision?: 'confirm' | 'reject' | null
    note?: string | null
    tool_execution: Record<string, unknown>
    feedback_selections?: Array<{
      question: string
      selected_label?: string | null
      custom_text?: string | null
    }>
  },
) {
  const { data } = await http.post<AgentRunStartResponse>(
    `/ai/runs/${runId}/continue`,
    {
      decision: payload.decision ?? null,
      note: payload.note ?? null,
      tool_execution: payload.tool_execution,
      feedback_selections: payload.feedback_selections ?? [],
    },
  )
  return data
}

/**
 * 向后端发送中断请求，要求当前会话的 active run 在安全点停止。
 */
export async function cancelAgentSessionActiveRun(
  sessionId: string,
  scope: AgentScopeContext,
  payload: {
    agent_id?: string
    force?: boolean
  },
) {
  logAgentDev('run.cancel.request', { sessionId, scope, payload })
  const { data } = await http.post<AgentRunCancelResponse>(
    `/ai/sessions/${sessionId}/active-run/cancel`,
    {
      session_id: sessionId,
      force: payload.force ?? false,
    },
    {
      params: buildScopeParams(scope, payload.agent_id ?? 'agent-coordinator'),
    },
  )
  logAgentDev('run.cancel.response', data)
  return data
}

/**
 * 按 run_id 取消或强制结束运行。
 */
export async function cancelAgentRun(
  runId: string,
  payload: {
    force?: boolean
  } = {},
) {
  logAgentDev('run.cancel-by-run.request', { runId, payload })
  const { data } = await http.post<AgentRunCancelResponse>(
    `/ai/runs/${runId}/cancel`,
    {
      force: payload.force ?? false,
    },
  )
  logAgentDev('run.cancel-by-run.response', data)
  return data
}

/**
 * 基于 fetch 消费后端 text/event-stream 响应。
 */
async function streamSse(path: string, init: RequestInit, options: AgentStreamOptions) {
  logAgentDev('sse.connect', { path, method: init.method ?? 'GET' })
  let response: Response
  try {
    response = await fetch(`${resolveApiBaseUrl()}${path}`, {
      ...init,
      credentials: 'include',
      signal: options.signal,
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        ...(init.headers ?? {}),
      },
    })
  } catch (error) {
    if (isAbortError(error)) {
      logAgentDev('sse.aborted', { path })
      throw new AgentStreamInterruptedError()
    }
    throw error
  }

  if (!response.ok) {
    if (response.status === 401) {
      notifyUnauthorized()
    }
    let detail = '内容助手请求失败。'
    let code: string | null = null
    try {
      const errorPayload = await response.json()
      code = typeof errorPayload?.code === 'string' ? errorPayload.code : null
      detail = String(errorPayload?.message || errorPayload?.detail || detail)
    } catch {
      detail = getErrorMessage(null, detail)
    }
    logAgentDev('sse.error', { path, detail })
    throw new AgentRequestError(detail, code)
  }

  const reader = response.body?.getReader()
  if (!reader) {
    logAgentDev('sse.empty', { path })
    return
  }

  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) {
        break
      }
      buffer += decoder.decode(value, { stream: true })
      buffer = buffer.replace(/\r\n/g, '\n')
      const blocks = buffer.split(/\n\n+/)
      buffer = blocks.pop() ?? ''
      for (const block of blocks) {
        const parsedEvent = parseSseBlock(block)
        if (parsedEvent) {
          logAgentDev('sse.event', parsedEvent)
          options.onEvent?.(parsedEvent)
        }
      }
    }
  } catch (error) {
    if (isAbortError(error)) {
      logAgentDev('sse.aborted', { path })
      throw new AgentStreamInterruptedError()
    }
    throw error
  }

  if (buffer.trim()) {
    const parsedEvent = parseSseBlock(buffer)
    if (parsedEvent) {
      logAgentDev('sse.event', parsedEvent)
      options.onEvent?.(parsedEvent)
    }
  }
  logAgentDev('sse.closed', { path })
}

/**
 * 判断 fetch 或 reader.read 抛出的错误是否来自 AbortController。
 */
function isAbortError(error: unknown) {
  return typeof error === 'object'
    && error !== null
    && 'name' in error
    && (error as { name?: unknown }).name === 'AbortError'
}

/**
 * 解析单个 SSE 数据块。
 */
function parseSseBlock(block: string): AgentRunEvent | null {
  const lines = block.split(/\r?\n/)
  let eventName = ''
  const dataLines: string[] = []
  for (const line of lines) {
    if (!line || line.startsWith(':')) {
      continue
    }
    if (line.startsWith('event:')) {
      eventName = line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).replace(/^ /, ''))
    }
  }
  if (!dataLines.length) {
    return null
  }

  try {
    const payload = JSON.parse(dataLines.join('\n')) as AgentRunEvent
    if (!payload.event && eventName) {
      payload.event = eventName
    }
    payload.sequence = payload.sequence ?? null
    return payload
  } catch {
    return {
      event: eventName || 'run.error',
      run_id: null,
      session_id: null,
      content: dataLines.join('\n'),
      data: {},
      sequence: null,
    }
  }
}

/**
 * 组装页面范围查询串，确保 BFF 与当前详情页上下文保持一致。
 */
function buildScopeQuery(scope: AgentScopeContext, agentId?: string, extra?: Record<string, string>) {
  return new URLSearchParams({
    ...buildScopeParams(scope, agentId),
    ...(extra ?? {}),
  }).toString()
}

/**
 * 组装泛化智能体 scope 查询参数，兼容项目、页面与组件上下文。
 */
function buildScopeParams(scope: AgentScopeContext, agentId?: string): Record<string, string> {
  const params: Record<string, string> = {
    scope_type: scope.scope_type,
    workspace_id: String(scope.workspace_id),
    source: scope.source,
  }
  if (agentId) {
    params.agent_id = agentId
  }
  if (scope.project_id !== undefined && scope.project_id !== null) {
    params.project_id = String(scope.project_id)
  }
  if (scope.page_id !== undefined && scope.page_id !== null) {
    params.page_id = String(scope.page_id)
  }
  if (scope.component_id !== undefined && scope.component_id !== null) {
    params.component_id = String(scope.component_id)
  }
  return params
}
