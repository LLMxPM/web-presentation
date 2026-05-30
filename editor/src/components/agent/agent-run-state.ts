/**
 * 文件功能：定义智能体 run-first 时间线状态机，统一处理快照、消息流、工具状态与终态。
 */
import type {
  AgentActiveRunItem,
  AgentImageAttachmentItem,
  AgentPendingRequirement,
  AgentRunEvent,
  AgentTimelineItem,
  AgentTimelineToolItem,
} from '@/types/api'
import { buildRunIssueState, parseStructuredPayload } from '@/components/agent/agent-conversation-panel'

export interface AgentRunStreamState {
  runId: string | null
  lastSequenceByRun: Record<string, number>
  streaming: boolean
  streamingTimelineItemId: string | null
}

export interface AgentSessionRuntimeState {
  timelineItems: AgentTimelineItem[]
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
    timelineItems: [],
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
      streamingTimelineItemId: null,
    },
  }
}

/**
 * 构造本地临时时间线项，供发送后和继续执行时立即展示。
 */
export function buildAgentLocalTimelineItem(
  sessionId: string,
  payload: {
    runId?: string | null
    kind: AgentTimelineItem['kind']
    role?: AgentTimelineItem['role']
    content?: string | null
    status?: string | null
    tool?: AgentTimelineToolItem | null
  },
): AgentTimelineItem {
  return {
    id: `local-${payload.kind}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
    session_id: sessionId,
    run_id: payload.runId ?? '',
    kind: payload.kind,
    role: payload.role ?? null,
    event_index: null,
    order_index: Date.now(),
    content: payload.content ?? null,
    status: payload.status ?? null,
    tool: payload.tool ?? null,
    source: 'synthetic',
    created_at: new Date().toISOString(),
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
  if (event.event === 'context.status') {
    state.contextStatus = event.data
    return { applied: true, terminal: false }
  }

  const runId = event.run_id || state.stream.runId
  if (!runId) {
    return { applied: false, terminal: false }
  }
  if (!shouldApplyEvent(state, event, runId)) {
    return { applied: false, terminal: false }
  }
  rememberEventSequence(state, runId, event.event_index ?? event.sequence)

  switch (event.event) {
    case 'run.started':
    case 'run.continued':
      state.pendingRequirement = null
      state.stream.runId = runId
      state.stream.streaming = true
      tagTrailingLocalItemsWithRunId(state, runId)
      state.activeRun = buildEventRunState(state, event, options.agentId, 'running')
      state.lastIssue = null
      return { applied: true, terminal: false }
    case 'run.cancelling':
      state.pendingRequirement = null
      state.stream.runId = runId
      state.stream.streaming = true
      state.activeRun = buildEventRunState(state, event, options.agentId, 'cancelling')
      state.lastIssue = null
      appendRunStatusItem(state, event, 'cancelling', '正在停止当前运行。')
      return { applied: true, terminal: false }
    case 'message.delta':
      {
        const splitContent = splitInlineReasoningDelta(event.content ?? '')
        appendReasoningDelta(
          state,
          event,
          [resolveEventReasoningContent(event), splitContent.reasoning].filter(Boolean).join('') || null,
        )
        appendAssistantDelta(state, event, splitContent.content)
      }
      return { applied: true, terminal: false }
    case 'tool.started':
      upsertToolTimelineItem(state, event, 'running')
      closeCurrentTextSegmentAfterTool(state)
      return { applied: true, terminal: false }
    case 'tool.completed':
      upsertToolTimelineItem(state, event, 'completed')
      closeCurrentTextSegmentAfterTool(state)
      return { applied: true, terminal: false }
    case 'tool.error':
      upsertToolTimelineItem(state, event, 'error')
      closeCurrentTextSegmentAfterTool(state)
      return { applied: true, terminal: false }
    case 'run.paused':
      state.pendingRequirement = (event.data.requirement as AgentPendingRequirement | null) ?? null
      state.activeRun = buildEventRunState(state, event, options.agentId, 'paused', state.pendingRequirement)
      state.stream.streaming = false
      state.lastIssue = null
      appendRequirementItem(state, event, state.pendingRequirement)
      clearStreamingTextItem(state)
      return { applied: true, terminal: true }
    case 'run.cancelled':
      state.pendingRequirement = null
      state.activeRun = null
      state.lastRun = buildEventRunState(state, event, options.agentId, 'cancelled')
      appendRunStatusItem(state, event, 'cancelled', '运行已停止。')
      clearStreamState(state)
      state.lastIssue = null
      return { applied: true, terminal: true }
    case 'run.error':
      state.activeRun = null
      state.lastRun = buildEventRunState(state, event, options.agentId, 'failed')
      appendRunStatusItem(state, event, 'failed', String(event.data.message || event.content || '智能体执行失败。'))
      clearStreamState(state)
      state.lastIssue = buildRunIssueState(String(event.data.message || event.content || '智能体执行失败。'), options.agentDisplayName)
      return { applied: true, terminal: true }
    case 'run.completed':
      state.activeRun = null
      state.lastRun = buildEventRunState(state, event, options.agentId, 'completed')
      if (event.content && shouldUseCompletedEventContent(state, event.content)) {
        appendAssistantDelta(state, event, event.content)
      }
      appendReasoningDelta(state, event, resolveEventReasoningContent(event))
      appendRunStatusItem(state, event, 'completed', '运行已完成。')
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
    timelineItems: AgentTimelineItem[]
    activeRun: AgentActiveRunItem | null
    lastRun: AgentActiveRunItem | null
    pendingRequirement: AgentPendingRequirement | null
    pendingImageAttachments: AgentImageAttachmentItem[]
    contextStatus: unknown | null
    eventIndex: number
  },
): void {
  const snapshotItems = [...payload.timelineItems]
  const activeStreamingRunId = payload.activeRun && STREAMING_RUN_STATUSES.has(payload.activeRun.status)
    ? payload.activeRun.run_id
    : null
  const cancelledRunId = payload.lastRun?.status === 'cancelled' ? payload.lastRun.run_id : null
  if (activeStreamingRunId && hasLocalRunProgress(state.timelineItems, activeStreamingRunId)) {
    state.timelineItems = mergeSnapshotWithLocalRun(snapshotItems, state.timelineItems, activeStreamingRunId)
  } else if (
    cancelledRunId
    && hasLocalRunProgress(state.timelineItems, cancelledRunId)
    && !hasRuntimeRunProgress(snapshotItems, cancelledRunId)
  ) {
    state.timelineItems = mergeSnapshotWithLocalRun(snapshotItems, state.timelineItems, cancelledRunId)
  } else {
    state.timelineItems = snapshotItems
  }
  state.activeRun = payload.activeRun
  state.lastRun = payload.lastRun
  state.pendingRequirement = payload.pendingRequirement
  state.pendingImageAttachments = [...payload.pendingImageAttachments]
  state.contextStatus = payload.contextStatus
  state.stream.runId = payload.activeRun?.run_id ?? null
  state.stream.streaming = Boolean(payload.activeRun && STREAMING_RUN_STATUSES.has(payload.activeRun.status))
  if (!state.stream.streaming) {
    state.stream.streamingTimelineItemId = null
  }
  const cursorRun = payload.activeRun && !STREAMING_RUN_STATUSES.has(payload.activeRun.status)
    ? payload.activeRun
    : payload.lastRun
  if (cursorRun?.run_id) {
    state.stream.lastSequenceByRun[cursorRun.run_id] = payload.eventIndex
  }
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
  const userFeedbackSchema = resolveUserFeedbackSchema(requirement, toolExecution, toolArgs)
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
    user_feedback_schema: userFeedbackSchema,
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

function shouldApplyEvent(state: AgentSessionRuntimeState, event: AgentRunEvent, runId: string): boolean {
  const currentRunId = state.stream.runId || state.activeRun?.run_id || null
  if (currentRunId && runId !== currentRunId && !['run.started', 'run.continued'].includes(event.event)) {
    return false
  }
  const sequence = event.event_index ?? event.sequence ?? null
  if (sequence === null) {
    return true
  }
  return sequence > (state.stream.lastSequenceByRun[runId] ?? -1)
}

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

function appendAssistantDelta(state: AgentSessionRuntimeState, event: AgentRunEvent, delta: string): void {
  if (!delta) return
  const item = ensureStreamingTextItem(state, event, 'message', 'assistant')
  item.content = `${item.content ?? ''}${delta}`
}

function appendReasoningDelta(state: AgentSessionRuntimeState, event: AgentRunEvent, reasoning: string | null): void {
  if (!reasoning) return
  const item = ensureStreamingTextItem(state, event, 'reasoning', null)
  item.content = `${item.content ?? ''}${reasoning}`
}

function ensureStreamingTextItem(
  state: AgentSessionRuntimeState,
  event: AgentRunEvent,
  kind: 'message' | 'reasoning',
  role: AgentTimelineItem['role'],
): AgentTimelineItem {
  const existing = state.stream.streamingTimelineItemId
    ? state.timelineItems.find(item => item.id === state.stream.streamingTimelineItemId)
    : null
  if (existing && existing.kind === kind && existing.role === role) {
    return existing
  }
  const item = buildAgentLocalTimelineItem(event.session_id || '', {
    runId: event.run_id || state.stream.runId,
    kind,
    role,
    content: '',
    status: 'running',
  })
  item.event_index = event.event_index ?? event.sequence ?? null
  item.order_index = nextTimelineOrderIndex(state)
  state.timelineItems = [...state.timelineItems, item]
  state.stream.streamingTimelineItemId = item.id
  return item
}

function upsertToolTimelineItem(
  state: AgentSessionRuntimeState,
  event: AgentRunEvent,
  status: AgentTimelineToolItem['status'],
): void {
  const toolCallId = typeof event.data.tool_call_id === 'string' ? event.data.tool_call_id : null
  const toolName = String(event.data.tool_name || '工具调用')
  const runId = event.run_id || state.stream.runId || ''
  const existingItem = findExistingToolTimelineItem(state, { runId, toolCallId, toolName })
  const itemId = existingItem?.id ?? (toolCallId
    ? `${event.session_id || 'session'}:${runId}:${toolCallId}`
    : `${event.session_id || 'session'}:${runId}:${toolName}:${event.event_index ?? event.sequence ?? Date.now()}`)
  const previousTool = existingItem?.tool
  const tool: AgentTimelineToolItem = {
    tool_call_id: toolCallId,
    tool_name: toolName,
    member_agent_id: resolveEventString(event.data.member_agent_id, previousTool?.member_agent_id ?? null),
    member_agent_name: resolveEventString(event.data.member_agent_name, previousTool?.member_agent_name ?? null),
    member_run_id: resolveEventString(event.data.member_run_id, previousTool?.member_run_id ?? null),
    status,
    input_payload: event.data.arguments ?? event.data.args ?? event.data.tool_args ?? previousTool?.input_payload ?? null,
    output_payload: event.data.result ?? event.data.output ?? previousTool?.output_payload ?? null,
    message: String(event.data.message || event.content || previousTool?.message || ''),
  }
  const nextItem: AgentTimelineItem = {
    id: itemId,
    session_id: event.session_id || '',
    run_id: runId,
    kind: 'tool',
    role: null,
    event_index: existingItem?.event_index ?? event.event_index ?? event.sequence ?? null,
    order_index: existingItem?.order_index ?? nextTimelineOrderIndex(state),
    content: null,
    status,
    tool,
    source: 'event',
    created_at: existingItem?.created_at ?? new Date().toISOString(),
  }
  state.timelineItems = existingItem
    ? state.timelineItems.map(item => (item.id === existingItem.id ? nextItem : item))
    : [...state.timelineItems, nextItem]
}

function findExistingToolTimelineItem(
  state: AgentSessionRuntimeState,
  payload: { runId: string, toolCallId: string | null, toolName: string },
): AgentTimelineItem | undefined {
  const directMatch = state.timelineItems.find(item => (
    item.kind === 'tool'
    && item.tool
    && item.run_id === payload.runId
    && (
      (payload.toolCallId && item.tool.tool_call_id === payload.toolCallId)
      || item.id.endsWith(`:${payload.toolCallId}`)
    )
  ))
  if (directMatch || payload.toolCallId) {
    return directMatch
  }
  return [...state.timelineItems].reverse().find(item => (
    item.kind === 'tool'
    && item.tool
    && item.run_id === payload.runId
    && item.tool.tool_call_id === null
    && item.tool.status === 'running'
    && item.tool.tool_name === payload.toolName
  ))
}

function appendRequirementItem(
  state: AgentSessionRuntimeState,
  event: AgentRunEvent,
  requirement: AgentPendingRequirement | null,
): void {
  if (!requirement) return
  appendUniqueTimelineItem(state, {
    id: `${event.session_id || ''}:${event.run_id || state.stream.runId || ''}:requirement:${requirement.id || requirement.tool_name || 'pending'}`,
    session_id: event.session_id || '',
    run_id: event.run_id || state.stream.runId || '',
    kind: 'requirement',
    role: null,
    event_index: event.event_index ?? event.sequence ?? null,
    order_index: nextTimelineOrderIndex(state),
    content: resolveRequirementTimelineContent(requirement),
    status: 'pending',
    tool: null,
    source: 'event',
    created_at: new Date().toISOString(),
  })
}

function resolveUserFeedbackSchema(
  requirement: Record<string, unknown>,
  toolExecution: Record<string, unknown>,
  toolArgs: Record<string, unknown>,
): AgentPendingRequirement['user_feedback_schema'] {
  for (const candidate of [requirement.user_feedback_schema, toolExecution.user_feedback_schema, toolArgs.questions]) {
    if (Array.isArray(candidate)) {
      return candidate as AgentPendingRequirement['user_feedback_schema']
    }
  }
  return []
}

function resolveRequirementTimelineContent(requirement: AgentPendingRequirement): string {
  if (requirement.kind === 'user_feedback' || requirement.tool_name === 'ask_user') {
    const firstQuestion = requirement.user_feedback_schema.find(question => question.question)?.question
    return firstQuestion || requirement.note || '等待用户回复。'
  }
  return requirement.note || requirement.tool_name || '等待用户处理。'
}

function appendRunStatusItem(
  state: AgentSessionRuntimeState,
  event: AgentRunEvent,
  status: string,
  content: string,
): void {
  appendUniqueTimelineItem(state, {
    id: `${event.session_id || ''}:${event.run_id || state.stream.runId || ''}:status:${status}`,
    session_id: event.session_id || '',
    run_id: event.run_id || state.stream.runId || '',
    kind: 'run_status',
    role: null,
    event_index: event.event_index ?? event.sequence ?? null,
    order_index: nextTimelineOrderIndex(state),
    content,
    status,
    tool: null,
    source: 'event',
    created_at: new Date().toISOString(),
  })
}

function appendUniqueTimelineItem(state: AgentSessionRuntimeState, item: AgentTimelineItem): void {
  if (state.timelineItems.some(existing => existing.id === item.id)) {
    state.timelineItems = state.timelineItems.map(existing => (existing.id === item.id ? item : existing))
    return
  }
  state.timelineItems = [...state.timelineItems, item]
}

function closeCurrentTextSegmentAfterTool(state: AgentSessionRuntimeState): void {
  state.stream.streamingTimelineItemId = null
}

function clearStreamingTextItem(state: AgentSessionRuntimeState): void {
  state.stream.streamingTimelineItemId = null
}

function clearStreamState(state: AgentSessionRuntimeState): void {
  for (const item of state.timelineItems) {
    if (item.status === 'running' && item.run_id === state.stream.runId && item.kind !== 'tool') {
      item.status = null
    }
  }
  state.stream.runId = null
  state.stream.streaming = false
  state.stream.streamingTimelineItemId = null
}

function resolveEventReasoningContent(event: AgentRunEvent): string | null {
  const reasoning = event.data.reasoning_content
  return typeof reasoning === 'string' && reasoning.length > 0 ? reasoning : null
}

function tagTrailingLocalItemsWithRunId(state: AgentSessionRuntimeState, runId: string): void {
  let shouldContinue = true
  state.timelineItems = [...state.timelineItems].reverse().map((item) => {
    if (!shouldContinue || item.run_id || !item.id.startsWith('local-')) {
      shouldContinue = false
      return item
    }
    return { ...item, run_id: runId }
  }).reverse()
}

function shouldUseCompletedEventContent(state: AgentSessionRuntimeState, content: string): boolean {
  if (looksLikeStructuredAggregate(content)) {
    return false
  }
  const runId = state.stream.runId
  if (!runId) {
    return true
  }
  const hasAssistantContent = state.timelineItems.some(item => (
    item.run_id === runId
    && item.kind === 'message'
    && item.role === 'assistant'
    && Boolean(item.content)
  ))
  return !hasAssistantContent
}

function hasLocalRunProgress(items: AgentTimelineItem[], runId: string): boolean {
  return items.some(item => itemBelongsToRun(item, runId) && item.kind !== 'message')
}

function hasRuntimeRunProgress(items: AgentTimelineItem[], runId: string): boolean {
  return items.some(item => item.run_id === runId && item.kind !== 'message')
}

function mergeSnapshotWithLocalRun(
  snapshotItems: AgentTimelineItem[],
  localItems: AgentTimelineItem[],
  runId: string,
): AgentTimelineItem[] {
  const localRunItems = localItems.filter(item => itemBelongsToRun(item, runId))
  return [
    ...snapshotItems.filter(item => item.run_id !== runId),
    ...localRunItems,
  ].sort((left, right) => left.order_index - right.order_index)
}

function itemBelongsToRun(item: AgentTimelineItem, runId: string): boolean {
  return item.run_id === runId || (!item.run_id && item.id.startsWith('local-'))
}

function nextTimelineOrderIndex(state: AgentSessionRuntimeState): number {
  return Math.max(-1, ...state.timelineItems.map(item => item.order_index)) + 1
}

function resolveEventString(value: unknown, fallback: string | null): string | null {
  if (typeof value === 'string' && value.trim()) {
    return value
  }
  return fallback
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

function looksLikeStructuredAggregate(content: string): boolean {
  const parsed = parseStructuredPayload(content)
  return typeof parsed !== 'string'
}

/**
 * 将流式正文里夹带的 think/reasoning 标签拆成独立时间线内容。
 */
function splitInlineReasoningDelta(content: string) {
  const reasoningParts: string[] = []
  let nextContent = content
  for (const pattern of [
    /<reasoning>([\s\S]*?)<\/reasoning>/gi,
    /<think>([\s\S]*?)<\/think>/gi,
  ]) {
    nextContent = nextContent.replace(pattern, (_match, reasoning: string) => {
      if (reasoning) {
        reasoningParts.push(reasoning)
      }
      return ''
    })
  }
  const openTagMatch = nextContent.match(/<(reasoning|think)>/i)
  if (openTagMatch?.index !== undefined) {
    const beforeReasoning = nextContent.slice(0, openTagMatch.index)
    const afterReasoning = nextContent.slice(openTagMatch.index + openTagMatch[0].length)
    if (afterReasoning) {
      reasoningParts.push(afterReasoning)
    }
    nextContent = beforeReasoning
  }
  nextContent = nextContent.replace(/<\/?(reasoning|think)>/gi, '')
  return {
    content: nextContent,
    reasoning: reasoningParts.join(''),
  }
}
