/**
 * 文件功能：封装智能体会话本地时间线的乐观更新，保持 Pinia store 聚焦状态分片同步。
 */
import {
  buildAgentLocalTimelineItem,
  MODEL_REQUEST_STATUS,
  MODEL_REQUEST_STATUS_TEXT,
  type AgentSessionRuntimeState,
} from '@/components/agent/agent-run-state'
import type {
  AgentFeedbackSelection,
  AgentImageAttachmentItem,
  AgentMessageAttachmentItem,
  AgentPendingRequirement,
  AgentTimelineItem,
} from '@/types/api'

/**
 * 发送用户消息后立即补齐本地等待状态，避免首个 SSE 事件前界面没有运行提示。
 */
export function appendLocalRunTimelineItems(
  state: AgentSessionRuntimeState,
  sessionId: string,
  message: string,
  attachments: AgentImageAttachmentItem[],
  runId?: string | null,
): void {
  const content = message || (attachments.length ? '（已发送图片）' : '')
  const userMessageOrderIndex = nextTimelineOrderIndex(state)
  state.timelineItems = [
    ...state.timelineItems,
    {
      ...buildAgentLocalTimelineItem(sessionId, {
        runId,
        kind: 'message',
        role: 'user',
        content,
        attachments: attachments.map(mapImageAttachmentToMessageAttachment),
      }),
      order_index: userMessageOrderIndex,
    },
  ]
  appendModelRequestStatusItem(state, sessionId, runId ?? state.stream.runId, userMessageOrderIndex + 1)
}

/**
 * 用户已处理 HITL 后更新本地时间线，等待后端 SSE 或快照覆盖为权威状态。
 */
export function markPendingRequirementResolvedInTimeline(
  state: AgentSessionRuntimeState,
  sessionId: string,
  requirement: AgentPendingRequirement,
  feedbackSelections: AgentFeedbackSelection[] = [],
): void {
  removeRequirementTimelineItem(state, requirement)
  if (isAskUserRequirement(requirement)) {
    upsertAnsweredAskUserToolItem(state, sessionId, requirement, feedbackSelections)
  }
  appendModelRequestStatusItem(state, sessionId, requirement.run_id || state.stream.runId, nextTimelineOrderIndex(state))
}

/**
 * 写入模型请求等待状态；id 与 SSE 状态项保持一致，后续事件可直接覆盖或清理。
 */
function appendModelRequestStatusItem(
  state: AgentSessionRuntimeState,
  sessionId: string,
  runId: string | null | undefined,
  orderIndex: number,
): void {
  if (!runId) {
    return
  }
  const item: AgentTimelineItem = {
    id: `${sessionId}:${runId}:status:${MODEL_REQUEST_STATUS}`,
    session_id: sessionId,
    run_id: runId,
    kind: 'run_status',
    role: null,
    event_index: null,
    order_index: orderIndex,
    content: MODEL_REQUEST_STATUS_TEXT,
    status: MODEL_REQUEST_STATUS,
    tool: null,
    attachments: [],
    source: 'synthetic',
    created_at: new Date().toISOString(),
  }
  state.timelineItems = state.timelineItems.some(current => current.id === item.id)
    ? state.timelineItems.map(current => (current.id === item.id ? { ...item, order_index: current.order_index } : current))
    : [...state.timelineItems, item]
}

/**
 * 用户已处理 HITL 后移除 requirement 占位，避免输入区消失后时间线仍显示待处理。
 */
function removeRequirementTimelineItem(state: AgentSessionRuntimeState, requirement: AgentPendingRequirement): void {
  state.timelineItems = state.timelineItems.filter(item => !(
    item.kind === 'requirement'
    && item.run_id === requirement.run_id
    && (item.status === 'pending' || item.status === 'paused')
  ))
}

/**
 * 结构化提问提交后立即把 ask_user 工具标为已回复。
 */
function upsertAnsweredAskUserToolItem(
  state: AgentSessionRuntimeState,
  sessionId: string,
  requirement: AgentPendingRequirement,
  feedbackSelections: AgentFeedbackSelection[],
): void {
  const outputPayload = buildFeedbackOutputPayload(feedbackSelections)
  let matched = false
  state.timelineItems = state.timelineItems.map((item) => {
    if (!isAskUserToolForRequirement(item, requirement)) {
      return item
    }
    matched = true
    return {
      ...item,
      status: 'completed',
      tool: item.tool
        ? {
            ...item.tool,
            status: 'completed',
            output_payload: outputPayload,
            message: item.tool.message || '已收到用户回答。',
          }
        : item.tool,
    }
  })
  if (matched) {
    return
  }

  const runId = requirement.run_id || state.stream.runId || ''
  const toolCallId = resolveToolExecutionCallId(requirement.tool_execution)
  state.timelineItems = [
    ...state.timelineItems,
    {
      id: toolCallId
        ? `${sessionId}:${runId}:${toolCallId}`
        : `${sessionId}:${runId}:ask_user:answered`,
      session_id: sessionId,
      run_id: runId,
      kind: 'tool',
      role: null,
      event_index: null,
      order_index: nextTimelineOrderIndex(state),
      content: null,
      status: 'completed',
      tool: {
        tool_call_id: toolCallId,
        tool_name: 'ask_user',
        status: 'completed',
        input_payload: resolveAskUserInputPayload(requirement),
        output_payload: outputPayload,
        message: '已收到用户回答。',
      },
      attachments: [],
      source: 'synthetic',
      created_at: new Date().toISOString(),
    },
  ]
}

function isAskUserRequirement(requirement: AgentPendingRequirement): boolean {
  return requirement.kind === 'user_feedback' || requirement.tool_name === 'ask_user'
}

function isAskUserToolForRequirement(item: AgentTimelineItem, requirement: AgentPendingRequirement): boolean {
  if (item.kind !== 'tool' || item.tool?.tool_name !== 'ask_user' || item.run_id !== requirement.run_id) {
    return false
  }
  const toolCallId = resolveToolExecutionCallId(requirement.tool_execution)
  return !toolCallId || item.tool.tool_call_id === toolCallId || item.id.endsWith(`:${toolCallId}`)
}

function resolveToolExecutionCallId(toolExecution: Record<string, unknown>): string | null {
  const value = toolExecution.tool_call_id
  return typeof value === 'string' && value ? value : null
}

function resolveAskUserInputPayload(requirement: AgentPendingRequirement): Record<string, unknown> {
  const toolArgs = requirement.tool_execution.tool_args
  if (toolArgs && typeof toolArgs === 'object' && !Array.isArray(toolArgs)) {
    const normalizedToolArgs = toolArgs as Record<string, unknown>
    return {
      ...normalizedToolArgs,
      questions: Array.isArray(normalizedToolArgs.questions)
        ? normalizedToolArgs.questions
        : requirement.user_feedback_schema,
    }
  }
  return { questions: requirement.user_feedback_schema }
}

function buildFeedbackOutputPayload(feedbackSelections: AgentFeedbackSelection[]): Record<string, unknown>[] {
  return feedbackSelections.map(selection => ({
    question: selection.question,
    selected_label: selection.selected_label ?? null,
    custom_text: selection.custom_text ?? null,
    selected: selection.custom_text
      ? [`用户补充：${selection.custom_text}`]
      : selection.selected_label
        ? [selection.selected_label]
        : [],
  }))
}

/**
 * 读取下一条本地时间线排序号。
 */
function nextTimelineOrderIndex(state: AgentSessionRuntimeState) {
  return Math.max(-1, ...state.timelineItems.map(item => item.order_index)) + 1
}

/**
 * 把 Composer 待发送附件转换为消息时间线可展示的附件摘要。
 */
function mapImageAttachmentToMessageAttachment(attachment: AgentImageAttachmentItem): AgentMessageAttachmentItem {
  return {
    id: attachment.id,
    source_kind: attachment.source_kind,
    original_name: attachment.original_name,
    content_type: attachment.content_type,
    file_size: attachment.file_size,
    url: attachment.url,
    preview_available: attachment.preview_available,
    promoted_asset_id: attachment.promoted_asset_id,
  }
}
