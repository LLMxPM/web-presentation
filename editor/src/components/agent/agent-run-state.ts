/**
 * 文件功能：定义智能体 run-first 时间线状态机，统一处理快照、消息流、工具状态与终态。
 */
import type {
  AgentActiveRunItem,
  AgentImageAttachmentItem,
  AgentMemberRunItem,
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
  memberStreamingTimelineItemIdByRun: Record<string, string | null>
}

export interface AgentSessionRuntimeState {
  timelineItems: AgentTimelineItem[]
  memberRuns: AgentMemberRunItem[]
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
const MODEL_REQUEST_STATUS = 'model_request'
const MODEL_REQUEST_STATUS_TEXT = '等待智能体输出中'

/**
 * 创建单个会话的默认运行时状态。
 */
export function createAgentSessionRuntimeState(): AgentSessionRuntimeState {
  return {
    timelineItems: [],
    memberRuns: [],
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
      memberStreamingTimelineItemIdByRun: {},
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
  event = normalizeAgentRunEvent(event)
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

  if (event.event.startsWith('member.')) {
    applyMemberRunEvent(state, event)
    return { applied: true, terminal: false }
  }

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
    case 'model.request.started':
      state.pendingRequirement = null
      state.stream.runId = runId
      state.stream.streaming = true
      if (!state.activeRun || state.activeRun.run_id === runId) {
        state.activeRun = buildEventRunState(state, event, options.agentId, 'running')
      }
      state.lastIssue = null
      finishCurrentTextSegment(state)
      appendRunStatusItem(state, event, MODEL_REQUEST_STATUS, MODEL_REQUEST_STATUS_TEXT)
      return { applied: true, terminal: false }
    case 'model.request.completed':
      state.stream.runId = runId
      state.stream.streaming = true
      return { applied: true, terminal: false }
    case 'message.delta':
      {
        const splitContent = splitInlineReasoningDelta(event.content ?? '')
        const reasoning = [resolveEventReasoningContent(event), splitContent.reasoning].filter(Boolean).join('') || null
        if (reasoning || splitContent.content) {
          removeModelRequestStatusItem(state, runId)
        }
        appendReasoningDelta(
          state,
          event,
          reasoning,
        )
        appendAssistantDelta(state, event, splitContent.content)
      }
      return { applied: true, terminal: false }
    case 'reasoning.delta':
      removeModelRequestStatusItem(state, runId)
      appendReasoningDelta(state, event, event.content ?? resolveEventReasoningContent(event))
      return { applied: true, terminal: false }
    case 'tool.started':
      removeModelRequestStatusItem(state, runId)
      upsertToolTimelineItem(state, event, 'running')
      finishCurrentTextSegment(state)
      return { applied: true, terminal: false }
    case 'tool.completed':
      removeModelRequestStatusItem(state, runId)
      upsertToolTimelineItem(state, event, 'completed')
      finishCurrentTextSegment(state)
      return { applied: true, terminal: false }
    case 'tool.error':
      removeModelRequestStatusItem(state, runId)
      upsertToolTimelineItem(state, event, 'error')
      finishCurrentTextSegment(state)
      return { applied: true, terminal: false }
    case 'run.paused':
      state.pendingRequirement = (event.data.requirement as AgentPendingRequirement | null) ?? null
      state.activeRun = buildEventRunState(state, event, options.agentId, 'paused', state.pendingRequirement)
      state.stream.streaming = false
      state.lastIssue = null
      removeModelRequestStatusItem(state, runId)
      appendRequirementItem(state, event, state.pendingRequirement)
      clearStreamingTextItem(state)
      return { applied: true, terminal: true }
    case 'run.cancelled':
      state.pendingRequirement = null
      state.activeRun = null
      state.lastRun = buildEventRunState(state, event, options.agentId, 'cancelled')
      removeModelRequestStatusItem(state, runId)
      appendRunStatusItem(state, event, 'cancelled', '运行已停止。')
      clearStreamState(state)
      state.lastIssue = null
      return { applied: true, terminal: true }
    case 'run.error':
      {
        const issue = buildRunIssueState(String(event.data.message || event.content || '智能体执行失败。'), options.agentDisplayName)
        failOpenToolTimelineItems(state, runId, issue.detail)
        state.activeRun = null
        state.lastRun = buildEventRunState(state, event, options.agentId, 'failed')
        removeModelRequestStatusItem(state, runId)
        appendRunStatusItem(state, event, 'failed', issue.title)
        clearStreamState(state)
        state.lastIssue = issue
      }
      return { applied: true, terminal: true }
    case 'run.completed':
      state.activeRun = null
      state.lastRun = buildEventRunState(state, event, options.agentId, 'completed')
      removeModelRequestStatusItem(state, runId)
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
    memberRuns?: AgentMemberRunItem[]
    activeRun: AgentActiveRunItem | null
    lastRun: AgentActiveRunItem | null
    pendingRequirement: AgentPendingRequirement | null
    pendingImageAttachments: AgentImageAttachmentItem[]
    contextStatus: unknown | null
    eventIndex: number
  },
): void {
  state.timelineItems = [...payload.timelineItems]
  state.memberRuns = [...(payload.memberRuns ?? [])]
  state.activeRun = normalizeActiveRun(payload.activeRun)
  state.lastRun = payload.lastRun
  state.pendingRequirement = state.activeRun?.status === 'paused'
    ? state.activeRun.pending_requirement
    : null
  state.pendingImageAttachments = [...payload.pendingImageAttachments]
  state.contextStatus = payload.contextStatus
  state.stream.runId = payload.activeRun?.run_id ?? null
  state.stream.streaming = Boolean(payload.activeRun && STREAMING_RUN_STATUSES.has(payload.activeRun.status))
  if (!state.stream.streaming) {
    state.stream.streamingTimelineItemId = null
  }
  const cursorRun = payload.activeRun ?? payload.lastRun
  if (cursorRun?.run_id) {
    state.stream.lastSequenceByRun[cursorRun.run_id] = Math.max(
      state.stream.lastSequenceByRun[cursorRun.run_id] ?? -1,
      payload.eventIndex,
    )
  }
}

/**
 * 归一化 active run，避免 running/pending/cancelling 状态残留旧 HITL requirement。
 */
function normalizeActiveRun(run: AgentActiveRunItem | null): AgentActiveRunItem | null {
  if (!run || run.status === 'paused' || run.pending_requirement === null) {
    return run
  }
  return { ...run, pending_requirement: null }
}

/**
 * 归一化平台 Agent 事件，确保 data 与 event_index 字段稳定存在。
 */
export function normalizeAgentRunEvent(rawEvent: AgentRunEvent): AgentRunEvent {
  if (rawEvent.event.includes('.')) {
    return { ...rawEvent, data: rawEvent.data ?? {}, event_index: rawEvent.event_index ?? rawEvent.sequence ?? null }
  }
  return {
    ...rawEvent,
    data: rawEvent.data ?? {},
    event_index: rawEvent.event_index ?? rawEvent.sequence ?? null,
  }
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

function failOpenToolTimelineItems(state: AgentSessionRuntimeState, runId: string, message: string): void {
  state.timelineItems = state.timelineItems.map((item) => {
    if (item.kind !== 'tool' || item.run_id !== runId || item.tool?.status !== 'running') {
      return item
    }
    return {
      ...item,
      status: 'error',
      tool: {
        ...item.tool,
        status: 'error',
        message: item.tool.message || message,
      },
    }
  })
}

function applyMemberRunEvent(state: AgentSessionRuntimeState, event: AgentRunEvent): void {
  const memberRun = ensureMemberRunItem(state, event)
  if (!memberRun) {
    return
  }
  switch (event.event) {
    case 'member.run.started':
    case 'member.run.continued':
      memberRun.status = 'running'
      memberRun.updated_at = new Date().toISOString()
      break
    case 'member.model.request.started':
      memberRun.status = 'running'
      finishMemberTextSegment(state, memberRun.run_id)
      appendMemberRunStatusItem(memberRun, event, MODEL_REQUEST_STATUS, MODEL_REQUEST_STATUS_TEXT)
      break
    case 'member.model.request.completed':
      memberRun.status = 'running'
      break
    case 'member.message.delta':
      {
        const splitContent = splitInlineReasoningDelta(event.content ?? '')
        const reasoning = [resolveEventReasoningContent(event), splitContent.reasoning].filter(Boolean).join('') || null
        if (reasoning || splitContent.content) {
          removeMemberModelRequestStatusItem(memberRun)
        }
        appendMemberReasoningDelta(
          state,
          memberRun,
          event,
          reasoning,
        )
        appendMemberAssistantDelta(state, memberRun, event, splitContent.content)
      }
      break
    case 'member.tool.started':
      removeMemberModelRequestStatusItem(memberRun)
      upsertMemberToolTimelineItem(memberRun, event, 'running')
      finishMemberTextSegment(state, memberRun.run_id)
      break
    case 'member.tool.completed':
      removeMemberModelRequestStatusItem(memberRun)
      upsertMemberToolTimelineItem(memberRun, event, 'completed')
      finishMemberTextSegment(state, memberRun.run_id)
      break
    case 'member.tool.error':
      removeMemberModelRequestStatusItem(memberRun)
      upsertMemberToolTimelineItem(memberRun, event, 'error')
      finishMemberTextSegment(state, memberRun.run_id)
      break
    case 'member.run.paused':
      memberRun.status = 'paused'
      removeMemberModelRequestStatusItem(memberRun)
      appendMemberRunStatusItem(memberRun, event, 'paused', '等待用户处理。')
      clearMemberStreamState(state, memberRun)
      break
    case 'member.run.cancelled':
      memberRun.status = 'cancelled'
      removeMemberModelRequestStatusItem(memberRun)
      appendMemberRunStatusItem(memberRun, event, 'cancelled', '运行已停止。')
      clearMemberStreamState(state, memberRun)
      break
    case 'member.run.error':
      memberRun.status = 'failed'
      removeMemberModelRequestStatusItem(memberRun)
      appendMemberRunStatusItem(
        memberRun,
        event,
        'failed',
        String(event.data.message || event.content || '成员助手执行失败。'),
      )
      clearMemberStreamState(state, memberRun)
      break
    case 'member.run.completed':
      memberRun.status = 'completed'
      removeMemberModelRequestStatusItem(memberRun)
      if (event.content && shouldUseMemberCompletedEventContent(memberRun, event.content)) {
        appendMemberAssistantDelta(state, memberRun, event, event.content)
      }
      appendMemberReasoningDelta(state, memberRun, event, resolveEventReasoningContent(event))
      appendMemberRunStatusItem(memberRun, event, 'completed', '运行已完成。')
      clearMemberStreamState(state, memberRun)
      break
    default:
      break
  }
  memberRun.updated_at = new Date().toISOString()
  assignMemberRunToDelegate(state, memberRun)
}

function ensureMemberRunItem(state: AgentSessionRuntimeState, event: AgentRunEvent): AgentMemberRunItem | null {
  const parentRunId = event.run_id || state.stream.runId || ''
  const memberRunId = resolveEventString(event.data.member_run_id, null)
  if (!parentRunId || !memberRunId) {
    return null
  }
  const existing = state.memberRuns.find(item => item.run_id === memberRunId)
  if (existing) {
    existing.agent_id = resolveEventString(event.data.member_agent_id, existing.agent_id) || existing.agent_id
    existing.agent_name = resolveEventString(event.data.member_agent_name, existing.agent_name ?? null)
    return existing
  }
  const memberRun: AgentMemberRunItem = {
    parent_run_id: parentRunId,
    run_id: memberRunId,
    agent_id: resolveEventString(event.data.member_agent_id, null) || '',
    agent_name: resolveEventString(event.data.member_agent_name, null),
    status: 'running',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    delegate_tool_call_id: null,
    timeline_items: [],
  }
  state.memberRuns = [...state.memberRuns, memberRun].sort(compareMemberRuns)
  return memberRun
}

function appendMemberAssistantDelta(
  state: AgentSessionRuntimeState,
  memberRun: AgentMemberRunItem,
  event: AgentRunEvent,
  delta: string,
): void {
  if (!delta) return
  const item = ensureMemberStreamingTextItem(state, memberRun, event, 'message', 'assistant')
  item.content = `${item.content ?? ''}${delta}`
}

function appendMemberReasoningDelta(
  state: AgentSessionRuntimeState,
  memberRun: AgentMemberRunItem,
  event: AgentRunEvent,
  reasoning: string | null,
): void {
  if (!reasoning) return
  const item = ensureMemberStreamingTextItem(state, memberRun, event, 'reasoning', null)
  item.content = `${item.content ?? ''}${reasoning}`
}

function ensureMemberStreamingTextItem(
  state: AgentSessionRuntimeState,
  memberRun: AgentMemberRunItem,
  event: AgentRunEvent,
  kind: 'message' | 'reasoning',
  role: AgentTimelineItem['role'],
): AgentTimelineItem {
  const streamingItemId = state.stream.memberStreamingTimelineItemIdByRun[memberRun.run_id]
  const existing = streamingItemId
    ? memberRun.timeline_items.find(item => item.id === streamingItemId)
    : null
  if (existing && existing.kind === kind && existing.role === role) {
    return existing
  }
  const item = buildAgentLocalTimelineItem(event.session_id || '', {
    runId: memberRun.run_id,
    kind,
    role,
    content: '',
    status: 'running',
  })
  item.event_index = event.event_index ?? event.sequence ?? null
  item.order_index = nextMemberTimelineOrderIndex(memberRun)
  memberRun.timeline_items = [...memberRun.timeline_items, item]
  state.stream.memberStreamingTimelineItemIdByRun[memberRun.run_id] = item.id
  return item
}

function upsertMemberToolTimelineItem(
  memberRun: AgentMemberRunItem,
  event: AgentRunEvent,
  status: AgentTimelineToolItem['status'],
): void {
  const toolCallId = typeof event.data.tool_call_id === 'string' ? event.data.tool_call_id : null
  const toolName = String(event.data.tool_name || '工具调用')
  const existingItem = findExistingMemberToolTimelineItem(memberRun, { toolCallId, toolName })
  const itemId = existingItem?.id ?? (toolCallId
    ? `${event.session_id || 'session'}:${memberRun.run_id}:${toolCallId}`
    : `${event.session_id || 'session'}:${memberRun.run_id}:${toolName}:${event.event_index ?? event.sequence ?? Date.now()}`)
  const previousTool = existingItem?.tool
  const tool: AgentTimelineToolItem = {
    tool_call_id: toolCallId,
    tool_name: toolName,
    member_agent_id: memberRun.agent_id || null,
    member_agent_name: memberRun.agent_name ?? null,
    member_run_id: memberRun.run_id,
    status,
    input_payload: event.data.arguments ?? event.data.args ?? event.data.tool_args ?? previousTool?.input_payload ?? null,
    output_payload: event.data.result ?? event.data.output ?? previousTool?.output_payload ?? null,
    message: String(event.data.message || event.content || previousTool?.message || ''),
  }
  const nextItem: AgentTimelineItem = {
    id: itemId,
    session_id: event.session_id || '',
    run_id: memberRun.run_id,
    kind: 'tool',
    role: null,
    event_index: existingItem?.event_index ?? event.event_index ?? event.sequence ?? null,
    order_index: existingItem?.order_index ?? nextMemberTimelineOrderIndex(memberRun),
    content: null,
    status,
    tool,
    source: 'event',
    created_at: existingItem?.created_at ?? new Date().toISOString(),
  }
  memberRun.timeline_items = existingItem
    ? memberRun.timeline_items.map(item => (item.id === existingItem.id ? nextItem : item))
    : [...memberRun.timeline_items, nextItem]
}

function findExistingMemberToolTimelineItem(
  memberRun: AgentMemberRunItem,
  payload: { toolCallId: string | null, toolName: string },
): AgentTimelineItem | undefined {
  const directMatch = memberRun.timeline_items.find(item => (
    item.kind === 'tool'
    && item.tool
    && (
      (payload.toolCallId && item.tool.tool_call_id === payload.toolCallId)
      || item.id.endsWith(`:${payload.toolCallId}`)
    )
  ))
  if (directMatch || payload.toolCallId) {
    return directMatch
  }
  return [...memberRun.timeline_items].reverse().find(item => (
    item.kind === 'tool'
    && item.tool
    && item.tool.tool_call_id === null
    && item.tool.status === 'running'
    && item.tool.tool_name === payload.toolName
  ))
}

function appendMemberRunStatusItem(
  memberRun: AgentMemberRunItem,
  event: AgentRunEvent,
  status: string,
  content: string,
): void {
  const itemId = `${event.session_id || ''}:${memberRun.run_id}:status:${status}`
  const existing = memberRun.timeline_items.find(item => item.id === itemId)
  const item: AgentTimelineItem = {
    id: itemId,
    session_id: event.session_id || '',
    run_id: memberRun.run_id,
    kind: 'run_status',
    role: null,
    event_index: event.event_index ?? event.sequence ?? null,
    order_index: existing?.order_index ?? nextMemberTimelineOrderIndex(memberRun),
    content,
    status,
    tool: null,
    source: 'event',
    created_at: existing?.created_at ?? new Date().toISOString(),
  }
  memberRun.timeline_items = existing
    ? memberRun.timeline_items.map(current => (current.id === itemId ? item : current))
    : [...memberRun.timeline_items, item]
}

function clearMemberStreamState(state: AgentSessionRuntimeState, memberRun: AgentMemberRunItem): void {
  for (const item of memberRun.timeline_items) {
    if (item.status === 'running' && item.kind !== 'tool') {
      item.status = null
    }
  }
  state.stream.memberStreamingTimelineItemIdByRun[memberRun.run_id] = null
}

function shouldUseMemberCompletedEventContent(memberRun: AgentMemberRunItem, content: string): boolean {
  if (looksLikeStructuredAggregate(content)) {
    return false
  }
  return !memberRun.timeline_items.some(item => (
    item.kind === 'message'
    && item.role === 'assistant'
    && Boolean(item.content)
  ))
}

function assignMemberRunToDelegate(state: AgentSessionRuntimeState, memberRun: AgentMemberRunItem): void {
  if (memberRun.delegate_tool_call_id) {
    return
  }
  const usedDelegateIds = new Set(
    state.memberRuns
      .filter(item => item.run_id !== memberRun.run_id)
      .map(item => item.delegate_tool_call_id)
      .filter((item): item is string => Boolean(item)),
  )
  const candidates = state.timelineItems
    .filter(item => (
      item.kind === 'tool'
      && item.run_id === memberRun.parent_run_id
      && item.tool
      && (item.tool.tool_name === 'delegate_task_to_member' || item.tool.tool_name === 'delegate_task_to_members')
      && (!usedDelegateIds.has(item.tool.tool_call_id || item.id) || item.tool.tool_name === 'delegate_task_to_members')
      && delegateToolMatchesMember(item.tool.input_payload, memberRun.agent_id)
    ))
    .sort((left, right) => left.order_index - right.order_index)
  const delegateItem = candidates[0]
  if (delegateItem?.tool) {
    memberRun.delegate_tool_call_id = delegateItem.tool.tool_call_id || delegateItem.id
  }
}

function delegateToolMatchesMember(inputPayload: unknown, memberAgentId: string): boolean {
  if (!inputPayload || typeof inputPayload !== 'object' || Array.isArray(inputPayload)) {
    return true
  }
  const memberId = (inputPayload as Record<string, unknown>).member_id
  return typeof memberId !== 'string' || !memberId || memberId === memberAgentId
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

/**
 * 清理等待智能体输出期间的临时状态，避免它进入最终时间线。
 */
function removeModelRequestStatusItem(state: AgentSessionRuntimeState, runId: string): void {
  state.timelineItems = state.timelineItems.filter(item => !(
    item.kind === 'run_status'
    && item.status === MODEL_REQUEST_STATUS
    && itemBelongsToRun(item, runId)
  ))
}

/**
 * 清理成员助手等待输出期间的临时状态。
 */
function removeMemberModelRequestStatusItem(memberRun: AgentMemberRunItem): void {
  memberRun.timeline_items = memberRun.timeline_items.filter(item => !(
    item.kind === 'run_status'
    && item.status === MODEL_REQUEST_STATUS
    && item.run_id === memberRun.run_id
  ))
}

function appendUniqueTimelineItem(state: AgentSessionRuntimeState, item: AgentTimelineItem): void {
  if (state.timelineItems.some(existing => existing.id === item.id)) {
    state.timelineItems = state.timelineItems.map(existing => (existing.id === item.id ? item : existing))
    return
  }
  state.timelineItems = [...state.timelineItems, item]
}

/**
 * 结束当前 run 的流式文本段，避免工具参数输出期间仍显示正文或“思考中”运行态。
 */
function finishCurrentTextSegment(state: AgentSessionRuntimeState): void {
  const itemId = state.stream.streamingTimelineItemId
  const currentItem = itemId
    ? state.timelineItems.find(item => item.id === itemId)
    : null
  const runId = currentItem?.run_id || state.stream.runId
  if (!itemId && !runId) {
    return
  }
  if (currentItem && currentItem.kind !== 'tool') {
    if (currentItem.kind === 'message' && currentItem.role === 'assistant' && !currentItem.content) {
      state.timelineItems = state.timelineItems.filter(item => item.id !== itemId)
    } else if (currentItem.status === 'running') {
      currentItem.status = null
    }
  }
  for (const item of state.timelineItems) {
    if (item.id !== itemId && item.run_id === runId && item.kind !== 'tool' && item.status === 'running') {
      item.status = null
    }
  }
  state.stream.streamingTimelineItemId = null
}

/**
 * 结束成员助手当前 run 的流式文本段，确保成员工具调用前的文本运行态收尾。
 */
function finishMemberTextSegment(state: AgentSessionRuntimeState, memberRunId: string): void {
  const itemId = state.stream.memberStreamingTimelineItemIdByRun[memberRunId]
  if (!itemId) {
    return
  }
  const memberRun = state.memberRuns.find(item => item.run_id === memberRunId)
  if (!memberRun) {
    state.stream.memberStreamingTimelineItemIdByRun[memberRunId] = null
    return
  }
  const currentItem = memberRun?.timeline_items.find(item => item.id === itemId)
  if (currentItem && currentItem.kind !== 'tool') {
    if (currentItem.kind === 'message' && currentItem.role === 'assistant' && !currentItem.content) {
      memberRun.timeline_items = memberRun.timeline_items.filter(item => item.id !== itemId)
    } else if (currentItem.status === 'running') {
      currentItem.status = null
    }
  }
  for (const item of memberRun.timeline_items) {
    if (item.id !== itemId && item.run_id === memberRun.run_id && item.kind !== 'tool' && item.status === 'running') {
      item.status = null
    }
  }
  state.stream.memberStreamingTimelineItemIdByRun[memberRunId] = null
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

function itemBelongsToRun(item: AgentTimelineItem, runId: string): boolean {
  return item.run_id === runId || (!item.run_id && item.id.startsWith('local-'))
}

function nextTimelineOrderIndex(state: AgentSessionRuntimeState): number {
  return Math.max(-1, ...state.timelineItems.map(item => item.order_index)) + 1
}

function nextMemberTimelineOrderIndex(memberRun: AgentMemberRunItem): number {
  return Math.max(-1, ...memberRun.timeline_items.map(item => item.order_index)) + 1
}

function compareMemberRuns(left: AgentMemberRunItem, right: AgentMemberRunItem): number {
  const leftCreated = left.created_at ?? ''
  const rightCreated = right.created_at ?? ''
  if (leftCreated !== rightCreated) {
    if (!leftCreated) return 1
    if (!rightCreated) return -1
    return leftCreated.localeCompare(rightCreated)
  }
  return left.run_id.localeCompare(right.run_id)
}

function resolveEventString(value: unknown, fallback: string | null): string | null {
  if (typeof value === 'string' && value.trim()) {
    return value
  }
  return fallback
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
