/**
 * 文件功能：定义智能体 run 事件状态机，统一处理消息流、工具状态、暂停与终态收敛。
 */
import type {
  AgentActiveRunItem,
  AgentImageAttachmentItem,
  AgentMessageItem,
  AgentPendingRequirement,
  AgentRunEvent,
  AgentToolCallDetailItem,
} from '@/types/api'
import { buildRunIssueState, type ToolCallDetail } from '@/components/agent/agent-conversation-panel'

export interface AgentRunStreamState {
  runId: string | null
  lastSequenceByRun: Record<string, number>
  streaming: boolean
  streamingAssistantMessageId: string | null
  assistantSegmentClosedByTool: boolean
}

export interface AgentSessionRuntimeState {
  messages: AgentMessageItem[]
  toolCallDetails: ToolCallDetail[]
  activeRun: AgentActiveRunItem | null
  lastRun: AgentActiveRunItem | null
  pendingRequirement: AgentPendingRequirement | null
  pendingImageAttachments: AgentImageAttachmentItem[]
  contextStatus: unknown | null
  lastIssue: { title: string, detail: string } | null
  stream: AgentRunStreamState
}

export interface ApplyAgentRunEventOptions {
  agentId: string
  agentDisplayName: string
}

export interface ApplyAgentRunEventResult {
  applied: boolean
  terminal: boolean
}

const STREAMING_RUN_STATUSES = new Set(['pending', 'running', 'cancelling'])

/**
 * 创建单个会话的默认运行时状态。
 */
export function createAgentSessionRuntimeState(): AgentSessionRuntimeState {
  return {
    messages: [],
    toolCallDetails: [],
    activeRun: null,
    lastRun: null,
    pendingRequirement: null,
    pendingImageAttachments: [],
    contextStatus: null,
    lastIssue: null,
    stream: {
      runId: null,
      lastSequenceByRun: {},
      streaming: false,
      streamingAssistantMessageId: null,
      assistantSegmentClosedByTool: false,
    },
  }
}

/**
 * 构造本地临时消息，供发送后和流式阶段立即展示。
 */
export function buildAgentLocalMessage(
  role: AgentMessageItem['role'],
  content: string,
  attachments: AgentImageAttachmentItem[] = [],
): AgentMessageItem {
  return {
    id: `local-${role}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
    run_id: null,
    role,
    content,
    reasoning_content: null,
    created_at: new Date().toISOString(),
    tool_name: null,
    tool_call_id: null,
    tool_args: null,
    tool_call_error: null,
    attachments: attachments.map(attachment => ({
      id: attachment.id,
      original_name: attachment.original_name,
      content_type: attachment.content_type,
      file_size: attachment.file_size,
      url: attachment.url,
      promoted_asset_id: attachment.promoted_asset_id,
    })),
  }
}

/**
 * 把后端 SSE 事件应用到指定会话状态；重复或过期事件会被忽略。
 */
export function applyAgentRunEvent(
  state: AgentSessionRuntimeState,
  event: AgentRunEvent,
  options: ApplyAgentRunEventOptions,
): ApplyAgentRunEventResult {
  event = normalizeAgnoRunEvent(event)
  const runId = event.run_id || state.stream.runId
  if (!runId) {
    return { applied: false, terminal: false }
  }
  if (!shouldApplyEvent(state, event, runId)) {
    return { applied: false, terminal: false }
  }
  rememberEventSequence(state, runId, event.event_index ?? event.sequence)

  switch (event.event) {
    case 'context.status':
      state.contextStatus = event.data
      return { applied: true, terminal: false }
    case 'run.started':
    case 'run.continued':
      state.stream.runId = runId
      state.stream.streaming = true
      tagTrailingLocalMessagesWithRunId(state, runId)
      state.activeRun = buildEventRunState(state, event, options.agentId, 'running')
      state.lastIssue = null
      return { applied: true, terminal: false }
    case 'run.cancelling':
      state.pendingRequirement = null
      state.stream.runId = runId
      state.stream.streaming = true
      state.activeRun = buildEventRunState(state, event, options.agentId, 'cancelling')
      state.lastIssue = null
      return { applied: true, terminal: false }
    case 'message.delta':
      appendAssistantDelta(state, event.content ?? '')
      appendAssistantReasoning(state, resolveEventReasoningContent(event))
      return { applied: true, terminal: false }
    case 'tool.started':
      upsertToolCallDetail(state, event, 'running')
      closeCurrentAssistantSegmentAfterTool(state)
      return { applied: true, terminal: false }
    case 'tool.completed':
      upsertToolCallDetail(state, event, 'completed')
      closeCurrentAssistantSegmentAfterTool(state)
      return { applied: true, terminal: false }
    case 'tool.error':
      upsertToolCallDetail(state, event, 'error')
      closeCurrentAssistantSegmentAfterTool(state)
      return { applied: true, terminal: false }
    case 'run.paused':
      state.pendingRequirement = (event.data.requirement as AgentPendingRequirement | null) ?? null
      state.activeRun = buildEventRunState(state, event, options.agentId, 'paused', state.pendingRequirement)
      state.stream.streaming = false
      state.lastIssue = null
      return { applied: true, terminal: true }
    case 'run.cancelled':
      state.pendingRequirement = null
      state.activeRun = null
      state.lastRun = buildEventRunState(state, event, options.agentId, 'cancelled')
      clearStreamState(state)
      state.lastIssue = null
      return { applied: true, terminal: true }
    case 'run.error':
      state.activeRun = null
      state.lastRun = buildEventRunState(state, event, options.agentId, 'failed')
      clearStreamState(state)
      state.lastIssue = buildRunIssueState(String(event.data.message || event.content || '智能体执行失败。'), options.agentDisplayName)
      return { applied: true, terminal: true }
    case 'run.completed':
      state.activeRun = null
      state.lastRun = buildEventRunState(state, event, options.agentId, 'completed')
      if (event.content && shouldUseCompletedEventContent(state, event.content)) {
        appendAssistantDelta(state, event.content)
      }
      appendCompletedAssistantReasoning(state, resolveEventReasoningContent(event))
      clearStreamState(state)
      state.lastIssue = null
      return { applied: true, terminal: true }
    default:
      return { applied: true, terminal: false }
  }
}

/**
 * 将 runtime snapshot 写入本地会话状态。
 */
export function applyAgentRuntimeSnapshot(
  state: AgentSessionRuntimeState,
  payload: {
    messages: AgentMessageItem[]
    activeRun: AgentActiveRunItem | null
    lastRun: AgentActiveRunItem | null
    pendingRequirement: AgentPendingRequirement | null
    pendingImageAttachments: AgentImageAttachmentItem[]
    contextStatus: unknown | null
    eventIndex: number
    toolDetails?: AgentToolCallDetailItem[]
  },
): void {
  const shouldKeepLocalCancelledMessages = shouldPreserveLocalCancelledSnapshotMessages(state, payload)
  const activeStreamingRunId = payload.activeRun && STREAMING_RUN_STATUSES.has(payload.activeRun.status)
    ? payload.activeRun.run_id
    : null
  const snapshotMessages = activeStreamingRunId
    ? payload.messages.filter(message => message.run_id !== activeStreamingRunId || message.role === 'user')
    : payload.messages
  state.messages = shouldKeepLocalCancelledMessages ? state.messages : [...snapshotMessages]
  if (payload.toolDetails) {
    state.toolCallDetails = mergeSnapshotToolDetails(
      state.toolCallDetails,
      payload.toolDetails,
      payload.activeRun ? null : payload.lastRun?.run_id ?? null,
    )
  }
  state.activeRun = payload.activeRun
  state.lastRun = payload.lastRun
  state.pendingRequirement = payload.pendingRequirement
  state.pendingImageAttachments = [...payload.pendingImageAttachments]
  state.contextStatus = payload.contextStatus
  state.stream.runId = payload.activeRun?.run_id ?? null
  state.stream.streaming = Boolean(payload.activeRun && STREAMING_RUN_STATUSES.has(payload.activeRun.status))
  if (!state.stream.streaming) {
    state.stream.streamingAssistantMessageId = null
    state.stream.assistantSegmentClosedByTool = false
  }
  const cursorRun = payload.activeRun && !STREAMING_RUN_STATUSES.has(payload.activeRun.status)
    ? payload.activeRun
    : payload.lastRun
  if (cursorRun?.run_id) {
    state.stream.lastSequenceByRun[cursorRun.run_id] = payload.eventIndex
  }
}

function shouldPreserveLocalCancelledSnapshotMessages(
  state: AgentSessionRuntimeState,
  payload: {
    messages: AgentMessageItem[]
    lastRun: AgentActiveRunItem | null
  },
): boolean {
  const cancelledRun = payload.lastRun?.status === 'cancelled' ? payload.lastRun : null
  if (!cancelledRun || state.messages.length === 0) {
    return false
  }
  const localRunId = state.activeRun?.run_id ?? state.lastRun?.run_id ?? state.stream.runId
  if (localRunId && cancelledRun.run_id !== localRunId) {
    return false
  }
  const runtimeRunMessages = payload.messages.filter(message => message.run_id === cancelledRun.run_id)
  if (runtimeRunMessages.length === 0) {
    return true
  }
  return hasAssistantProgressForRun(state.messages, cancelledRun.run_id)
    && !hasAssistantProgressForRun(runtimeRunMessages, cancelledRun.run_id)
}

function hasAssistantProgressForRun(messages: AgentMessageItem[], runId: string): boolean {
  return messages.some(message => (
    messageBelongsToCancelledRun(message, runId)
    && message.role === 'assistant'
    && (message.content.length > 0 || Boolean(message.reasoning_content))
  ))
}

function messageBelongsToCancelledRun(message: AgentMessageItem, runId: string): boolean {
  return message.run_id === runId || (message.run_id === null && message.id.startsWith('local-'))
}

/**
 * 将 Agno raw event 投影成内部 UI 状态机事件；SSE 公共契约仍保留 raw payload。
 */
export function normalizeAgnoRunEvent(rawEvent: AgentRunEvent): AgentRunEvent {
  if (rawEvent.event.includes('.')) {
    return { ...rawEvent, data: rawEvent.data ?? {}, event_index: rawEvent.event_index ?? rawEvent.sequence ?? null }
  }
  const eventName = rawEvent.event
  const runId = resolveRawString(rawEvent.run_id) ?? null
  const sessionId = resolveRawString(rawEvent.session_id) ?? null
  const eventIndex = resolveRawNumber(rawEvent.event_index) ?? resolveRawNumber(rawEvent.sequence)
  const data: Record<string, unknown> = { ...rawEvent }
  delete data.data

  if (['RunStarted', 'RunStartedEvent', 'TeamRunStarted'].includes(eventName)) {
    return {
      event: 'run.started',
      run_id: runId,
      session_id: sessionId,
      content: null,
      data: { ...data, agent_id: rawEvent.agent_id ?? rawEvent.team_id },
      event_index: eventIndex,
    }
  }
  if (['RunContinued', 'RunContinuedEvent', 'TeamRunContinued'].includes(eventName)) {
    return { event: 'run.continued', run_id: runId, session_id: sessionId, content: null, data, event_index: eventIndex }
  }
  if ([
    'RunContent',
    'RunContentEvent',
    'IntermediateRunContent',
    'IntermediateRunContentEvent',
    'RunIntermediateContent',
    'TeamRunContent',
    'TeamRunIntermediateContent',
    'ReasoningContentDelta',
  ].includes(eventName)) {
    const content = typeof rawEvent.content === 'string' ? rawEvent.content : ''
    const reasoning = typeof rawEvent.reasoning_content === 'string'
      ? rawEvent.reasoning_content
      : typeof rawEvent.redacted_reasoning_content === 'string'
        ? rawEvent.redacted_reasoning_content
        : null
    return {
      event: 'message.delta',
      run_id: runId,
      session_id: sessionId,
      content,
      data: { ...data, reasoning_content: reasoning },
      event_index: eventIndex,
    }
  }
  if (['ToolCallStarted', 'ToolCallStartedEvent', 'TeamToolCallStarted'].includes(eventName)) {
    const tool = resolveRawObject(rawEvent.tool)
    return {
      event: 'tool.started',
      run_id: runId,
      session_id: sessionId,
      content: null,
      data: {
        ...data,
        tool_name: tool.tool_name,
        tool_call_id: tool.tool_call_id,
        tool_args: tool.tool_args ?? {},
      },
      event_index: eventIndex,
    }
  }
  if (['ToolCallCompleted', 'ToolCallCompletedEvent', 'TeamToolCallCompleted'].includes(eventName)) {
    const tool = resolveRawObject(rawEvent.tool)
    return {
      event: 'tool.completed',
      run_id: runId,
      session_id: sessionId,
      content: typeof rawEvent.content === 'string' ? rawEvent.content : null,
      data: {
        ...data,
        tool_name: tool.tool_name,
        tool_call_id: tool.tool_call_id,
        result: tool.result ?? rawEvent.content ?? null,
        message: rawEvent.content ?? null,
      },
      event_index: eventIndex,
    }
  }
  if (['ToolCallError', 'ToolCallErrorEvent', 'TeamToolCallError'].includes(eventName)) {
    const tool = resolveRawObject(rawEvent.tool)
    return {
      event: 'tool.error',
      run_id: runId,
      session_id: sessionId,
      content: typeof rawEvent.content === 'string' ? rawEvent.content : null,
      data: {
        ...data,
        tool_name: tool.tool_name,
        tool_call_id: tool.tool_call_id,
        message: rawEvent.content ?? rawEvent.error ?? tool.error ?? null,
      },
      event_index: eventIndex,
    }
  }
  if (['RunPaused', 'RunPausedEvent', 'TeamRunPaused'].includes(eventName)) {
    return {
      event: 'run.paused',
      run_id: runId,
      session_id: sessionId,
      content: null,
      data: { ...data, requirement: buildPendingRequirementFromAgno(rawEvent, runId, sessionId) },
      event_index: eventIndex,
    }
  }
  if (['RunCompleted', 'RunCompletedEvent', 'TeamRunCompleted'].includes(eventName)) {
    return {
      event: 'run.completed',
      run_id: runId,
      session_id: sessionId,
      content: typeof rawEvent.content === 'string' ? rawEvent.content : null,
      data,
      event_index: eventIndex,
    }
  }
  if (['RunCancelled', 'RunCancelledEvent', 'TeamRunCancelled'].includes(eventName)) {
    return { event: 'run.cancelled', run_id: runId, session_id: sessionId, content: null, data, event_index: eventIndex }
  }
  if (['RunError', 'RunErrorEvent', 'TeamRunError'].includes(eventName)) {
    return {
      event: 'run.error',
      run_id: runId,
      session_id: sessionId,
      content: typeof rawEvent.content === 'string' ? rawEvent.content : null,
      data: { ...data, message: rawEvent.content ?? rawEvent.error ?? data.message },
      event_index: eventIndex,
    }
  }
  return { event: 'trace.event', run_id: runId, session_id: sessionId, content: null, data, event_index: eventIndex }
}

function buildPendingRequirementFromAgno(
  rawEvent: AgentRunEvent,
  runId: string | null,
  sessionId: string | null,
): AgentPendingRequirement | null {
  const requirement = resolveActiveRequirement(rawEvent)
  if (!requirement || !runId || !sessionId) {
    return null
  }
  const toolExecution = resolveRawObject(requirement.tool_execution)
  const toolArgs = resolveRawObject(toolExecution.tool_args)
  const kind = toolExecution.requires_user_input === true ? 'user_feedback' : 'confirmation'
  return {
    id: resolveRawString(requirement.id),
    kind,
    run_id: runId,
    session_id: sessionId,
    member_agent_id: resolveRawString(requirement.member_agent_id),
    member_agent_name: resolveRawString(requirement.member_agent_name),
    member_run_id: resolveRawString(requirement.member_run_id),
    tool_name: resolveRawString(toolExecution.tool_name),
    tool_execution: toolExecution,
    suggested_patch: null,
    user_feedback_schema: Array.isArray(toolArgs.questions) ? toolArgs.questions as AgentPendingRequirement['user_feedback_schema'] : [],
    note: resolveRawString(requirement.note),
  }
}

function resolveActiveRequirement(rawEvent: AgentRunEvent): Record<string, unknown> | null {
  const requirements = Array.isArray(rawEvent.requirements) ? rawEvent.requirements : []
  for (const item of [...requirements].reverse()) {
    const requirement = resolveRawObject(item)
    const toolExecution = resolveRawObject(requirement.tool_execution)
    if (isAgnoRequirementActive(requirement, toolExecution)) {
      return requirement
    }
  }
  const tools = Array.isArray(rawEvent.tools) ? rawEvent.tools : []
  for (const item of [...tools].reverse()) {
    const toolExecution = resolveRawObject(item)
    if (isAgnoToolExecutionActive(toolExecution)) {
      return { id: null, tool_execution: toolExecution }
    }
  }
  return null
}

function isAgnoRequirementActive(requirement: Record<string, unknown>, toolExecution: Record<string, unknown>) {
  if (toolExecution.requires_confirmation === true && requirement.confirmation == null && toolExecution.confirmed == null) return true
  if (toolExecution.requires_user_input === true && toolExecution.answered !== true) return true
  if (toolExecution.external_execution_required === true && requirement.external_execution_result == null && toolExecution.result == null) return true
  return false
}

function isAgnoToolExecutionActive(toolExecution: Record<string, unknown>) {
  if (toolExecution.requires_confirmation === true && toolExecution.confirmed == null) return true
  if (toolExecution.requires_user_input === true && toolExecution.answered !== true) return true
  if (toolExecution.external_execution_required === true && toolExecution.result == null) return true
  return false
}

function resolveRawObject(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function resolveRawString(value: unknown): string | null {
  return typeof value === 'string' && value ? value : null
}

function resolveRawNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

/**
 * 判断事件是否属于当前 run 且 sequence 未被消费。
 */
function shouldApplyEvent(state: AgentSessionRuntimeState, event: AgentRunEvent, runId: string): boolean {
  const currentRunId = state.stream.runId || state.activeRun?.run_id || null
  if (currentRunId && runId !== currentRunId && !['run.started', 'run.continued'].includes(event.event)) {
    return false
  }
  const sequence = event.event_index ?? event.sequence ?? null
  if (sequence === null) {
    return true
  }
  return sequence > (state.stream.lastSequenceByRun[runId] ?? 0)
}

/**
 * 记录指定 run 已消费的最大事件序号。
 */
function rememberEventSequence(state: AgentSessionRuntimeState, runId: string, sequence?: number | null): void {
  if (sequence === null || sequence === undefined) return
  state.stream.lastSequenceByRun[runId] = Math.max(state.stream.lastSequenceByRun[runId] ?? -1, sequence)
}

function buildEventRunState(
  state: AgentSessionRuntimeState,
  event: AgentRunEvent,
  agentId: string,
  status: AgentActiveRunItem['status'],
  requirement: AgentPendingRequirement | null = null,
): AgentActiveRunItem {
  const runId = event.run_id || state.stream.runId || ''
  return {
    run_id: runId,
    session_id: event.session_id || state.activeRun?.session_id || '',
    agent_id: String(event.data.agent_id || agentId),
    status,
    pending_requirement: requirement,
    content: event.content ?? null,
    created_at: state.activeRun?.created_at ?? new Date().toISOString(),
    updated_at: new Date().toISOString(),
    cancel_requested_at: status === 'cancelling' ? new Date().toISOString() : null,
    event_index: event.event_index ?? event.sequence ?? state.stream.lastSequenceByRun[runId] ?? -1,
  }
}

function appendAssistantDelta(state: AgentSessionRuntimeState, delta: string): void {
  if (!delta) return
  const streamingMessageId = ensureStreamingAssistantMessage(state)
  state.messages = state.messages.map((message) => {
    if (message.id !== streamingMessageId) return message
    return { ...message, content: `${message.content}${delta}` }
  })
}

function appendAssistantReasoning(state: AgentSessionRuntimeState, reasoning: string | null): void {
  if (!reasoning) return
  const streamingMessageId = ensureStreamingAssistantMessage(state)
  state.messages = state.messages.map((message) => {
    if (message.id !== streamingMessageId) return message
    const existingReasoning = message.reasoning_content ?? ''
    return { ...message, reasoning_content: `${existingReasoning}${reasoning}` }
  })
}

function appendCompletedAssistantReasoning(state: AgentSessionRuntimeState, reasoning: string | null): void {
  if (!reasoning || !shouldUseCompletedEventReasoning(state)) return
  appendAssistantReasoning(state, reasoning)
}

function ensureStreamingAssistantMessage(state: AgentSessionRuntimeState): string {
  if (state.stream.streamingAssistantMessageId && !state.stream.assistantSegmentClosedByTool) {
    return state.stream.streamingAssistantMessageId
  }
  const placeholder = {
    ...buildAgentLocalMessage('assistant', ''),
    run_id: state.stream.runId,
  }
  state.messages = [...state.messages, placeholder]
  state.stream.streamingAssistantMessageId = placeholder.id
  state.stream.assistantSegmentClosedByTool = false
  return placeholder.id
}

function closeCurrentAssistantSegmentAfterTool(state: AgentSessionRuntimeState): void {
  if (state.stream.streamingAssistantMessageId) {
    state.stream.assistantSegmentClosedByTool = true
  }
}

function upsertToolCallDetail(
  state: AgentSessionRuntimeState,
  event: AgentRunEvent,
  status: ToolCallDetail['status'],
): void {
  const toolCallId = typeof event.data.tool_call_id === 'string' ? event.data.tool_call_id : null
  const toolName = String(event.data.tool_name || '工具调用')
  const runId = event.run_id || state.stream.runId
  const id = toolCallId || `${runId || 'run'}:${toolName}:${event.sequence ?? Date.now()}`
  const assistantMessageId = resolveCurrentAssistantMessageId(state)
  const existingItem = findExistingToolCallDetail(state, {
    id,
    runId,
    toolCallId,
    toolName,
    assistantMessageId,
  })
  const nextItem: ToolCallDetail = {
    id: existingItem?.id ?? id,
    runId: existingItem?.runId ?? runId,
    toolCallId,
    toolName,
    memberAgentId: resolveEventString(event.data.member_agent_id, existingItem?.memberAgentId ?? null),
    memberAgentName: resolveEventString(event.data.member_agent_name, existingItem?.memberAgentName ?? null),
    memberRunId: resolveEventString(event.data.member_run_id, existingItem?.memberRunId ?? null),
    status,
    assistantMessageId: existingItem?.assistantMessageId ?? assistantMessageId,
    inputPayload: event.data.arguments ?? event.data.args ?? event.data.tool_args ?? existingItem?.inputPayload ?? null,
    outputPayload: event.data.result ?? event.data.output ?? existingItem?.outputPayload ?? null,
    message: String(event.data.message || event.content || existingItem?.message || ''),
    source: 'event',
    createdAt: existingItem?.createdAt ?? new Date().toISOString(),
  }
  state.toolCallDetails = existingItem
    ? state.toolCallDetails.map(item => (item.id === existingItem.id ? nextItem : item))
    : [...state.toolCallDetails, nextItem]
}

function findExistingToolCallDetail(
  state: AgentSessionRuntimeState,
  payload: {
    id: string
    runId: string | null
    toolCallId: string | null
    toolName: string
    assistantMessageId: string | null
  },
): ToolCallDetail | undefined {
  const directMatch = state.toolCallDetails.find(item => (
    item.id === payload.id || (payload.toolCallId && item.toolCallId === payload.toolCallId)
  ))
  if (directMatch || payload.toolCallId) {
    return directMatch
  }
  return [...state.toolCallDetails].reverse().find(item => (
    item.source === 'event'
    && item.runId === payload.runId
    && item.toolCallId === null
    && item.status === 'running'
    && item.toolName === payload.toolName
    && item.assistantMessageId === payload.assistantMessageId
  ))
}

function resolveEventString(value: unknown, fallback: string | null): string | null {
  if (typeof value === 'string' && value.trim()) {
    return value
  }
  return fallback
}

function resolveCurrentAssistantMessageId(state: AgentSessionRuntimeState): string | null {
  if (state.stream.streamingAssistantMessageId) {
    return state.stream.streamingAssistantMessageId
  }
  if (state.stream.streaming) {
    return ensureStreamingAssistantMessage(state)
  }
  return [...state.messages].reverse().find(message => message.role === 'assistant')?.id ?? null
}

function shouldUseCompletedEventContent(state: AgentSessionRuntimeState, content: string): boolean {
  if (looksLikeStructuredAggregate(content)) {
    return false
  }
  const streamingMessageId = state.stream.streamingAssistantMessageId
  if (!streamingMessageId) {
    return true
  }
  if (state.stream.assistantSegmentClosedByTool) {
    return true
  }
  const currentStreamingMessage = state.messages.find(message => message.id === streamingMessageId)
  return !currentStreamingMessage?.content
}

function shouldUseCompletedEventReasoning(state: AgentSessionRuntimeState): boolean {
  const streamingMessageId = state.stream.streamingAssistantMessageId
  if (!streamingMessageId || state.stream.assistantSegmentClosedByTool) {
    return false
  }
  const currentStreamingMessage = state.messages.find(message => message.id === streamingMessageId)
  return !currentStreamingMessage?.reasoning_content
}

function clearStreamState(state: AgentSessionRuntimeState): void {
  state.stream.runId = null
  state.stream.streaming = false
  state.stream.streamingAssistantMessageId = null
  state.stream.assistantSegmentClosedByTool = false
}

function resolveEventReasoningContent(event: AgentRunEvent): string | null {
  const reasoning = event.data.reasoning_content
  return typeof reasoning === 'string' && reasoning.length > 0 ? reasoning : null
}

function tagTrailingLocalMessagesWithRunId(state: AgentSessionRuntimeState, runId: string): void {
  let shouldContinue = true
  state.messages = [...state.messages].reverse().map((message) => {
    if (!shouldContinue || message.run_id || !message.id.startsWith('local-')) {
      shouldContinue = false
      return message
    }
    return { ...message, run_id: runId }
  }).reverse()
}

function mergeSnapshotToolDetails(
  existingDetails: ToolCallDetail[],
  snapshotDetails: AgentToolCallDetailItem[],
  terminalRunId: string | null,
): ToolCallDetail[] {
  const eventDetails = existingDetails.filter(detail => (
    detail.source === 'event'
    && (!terminalRunId || detail.runId !== terminalRunId)
  ))
  const historyDetails = snapshotDetails.map<ToolCallDetail>(detail => ({
    id: detail.id,
    runId: detail.run_id,
    toolCallId: detail.tool_call_id,
    toolName: detail.tool_name,
    memberAgentId: detail.member_agent_id ?? null,
    memberAgentName: detail.member_agent_name ?? null,
    memberRunId: detail.member_run_id ?? null,
    status: detail.status,
    assistantMessageId: detail.assistant_message_id,
    inputPayload: detail.input_payload,
    outputPayload: detail.output_payload,
    message: detail.message,
    source: 'history',
    createdAt: detail.created_at,
  }))
  return [...historyDetails, ...eventDetails]
}

function looksLikeStructuredAggregate(content: string): boolean {
  const trimmed = content.trim()
  if (!trimmed) {
    return false
  }
  if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) {
    return false
  }
  try {
    JSON.parse(trimmed)
    return true
  } catch {
    return false
  }
}
