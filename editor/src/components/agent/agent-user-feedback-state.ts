/**
 * 文件功能：处理 ask_user 用户反馈提交后的本地时间线收敛，避免继续流式输出期间残留等待状态。
 */
import type {
  AgentFeedbackSelection,
  AgentPendingRequirement,
  AgentTimelineItem,
} from '@/types/api'
import type { AgentSessionRuntimeState } from '@/components/agent/agent-run-state'

/**
 * 用户提交 ask_user 答案后，先在本地把提问时间线改成已回答状态。
 * 后端最终 runtime 快照会再次校准，这里负责覆盖继续流式输出期间的即时反馈。
 */
export function resolveAgentUserFeedbackRequirement(
  state: AgentSessionRuntimeState,
  requirement: AgentPendingRequirement,
  selections: AgentFeedbackSelection[],
): void {
  if (!isUserFeedbackRequirement(requirement)) {
    return
  }
  const runId = requirement.run_id || state.stream.runId || ''
  if (!runId) {
    return
  }
  const answeredSchema = buildAnsweredFeedbackSchema(requirement.user_feedback_schema, selections)
  const outputPayload = buildFeedbackToolResult(answeredSchema)
  const toolCallId = resolveToolExecutionCallId(requirement.tool_execution)
  const matchingRequirementItem = findMatchingRequirementTimelineItem(state, requirement)
  const existingToolItem = findMatchingAskUserToolTimelineItem(state, requirement)
  const nextToolItem = buildResolvedAskUserToolTimelineItem({
    state,
    requirement,
    answeredSchema,
    outputPayload,
    existingToolItem,
    matchingRequirementItem,
    runId,
    toolCallId,
  })

  state.timelineItems = [
    ...state.timelineItems
      .filter(item => item.id !== existingToolItem?.id && !isMatchingRequirementTimelineItem(item, requirement)),
    nextToolItem,
  ].sort((left, right) => left.order_index - right.order_index)
  state.pendingRequirement = null
  if (state.activeRun?.run_id === runId) {
    state.activeRun = { ...state.activeRun, status: 'running', pending_requirement: null, updated_at: new Date().toISOString() }
  }
}

function isUserFeedbackRequirement(requirement: AgentPendingRequirement): boolean {
  return requirement.kind === 'user_feedback' || requirement.tool_name === 'ask_user'
}

function buildAnsweredFeedbackSchema(
  questions: AgentPendingRequirement['user_feedback_schema'],
  selections: AgentFeedbackSelection[],
): AgentPendingRequirement['user_feedback_schema'] {
  const selectionByQuestion = new Map(
    selections
      .filter(selection => selection.question)
      .map(selection => [selection.question, selection]),
  )
  return questions.map((question) => {
    const selection = selectionByQuestion.get(question.question)
    const selectedOptions = resolveSelectedFeedbackOptions(selection)
    return {
      ...question,
      selected_options: selectedOptions.length ? selectedOptions : question.selected_options,
      options: question.options.map(option => ({
        ...option,
        selected: selectedOptions.length ? selectedOptions.includes(option.label) : option.selected,
      })),
    }
  })
}

function resolveSelectedFeedbackOptions(selection: AgentFeedbackSelection | undefined): string[] {
  if (!selection) {
    return []
  }
  const customText = selection.custom_text?.trim()
  if (customText) {
    return [`用户补充：${customText}`]
  }
  const selectedLabel = selection.selected_label?.trim()
  return selectedLabel ? [selectedLabel] : []
}

function buildFeedbackToolResult(schema: AgentPendingRequirement['user_feedback_schema']): string {
  const answers = schema.map(question => ({
    question: question.question,
    selected: question.selected_options ?? [],
  }))
  return `User feedback received: ${JSON.stringify(answers)}`
}

function findMatchingRequirementTimelineItem(
  state: AgentSessionRuntimeState,
  requirement: AgentPendingRequirement,
): AgentTimelineItem | null {
  return state.timelineItems.find(item => isMatchingRequirementTimelineItem(item, requirement)) ?? null
}

function isMatchingRequirementTimelineItem(item: AgentTimelineItem, requirement: AgentPendingRequirement): boolean {
  if (item.kind !== 'requirement' || item.run_id !== requirement.run_id) {
    return false
  }
  if (requirement.id && item.id.endsWith(`:requirement:${requirement.id}`)) {
    return true
  }
  const questionTexts = new Set(requirement.user_feedback_schema.map(question => question.question).filter(Boolean))
  return Boolean(item.content && questionTexts.has(item.content))
}

function findMatchingAskUserToolTimelineItem(
  state: AgentSessionRuntimeState,
  requirement: AgentPendingRequirement,
): AgentTimelineItem | null {
  const toolCallId = resolveToolExecutionCallId(requirement.tool_execution)
  return [...state.timelineItems].reverse().find(item => (
    item.kind === 'tool'
    && item.run_id === requirement.run_id
    && item.tool?.tool_name === 'ask_user'
    && (
      !toolCallId
      || item.tool.tool_call_id === toolCallId
    )
  )) ?? null
}

function buildResolvedAskUserToolTimelineItem(payload: {
  state: AgentSessionRuntimeState
  requirement: AgentPendingRequirement
  answeredSchema: AgentPendingRequirement['user_feedback_schema']
  outputPayload: string
  existingToolItem: AgentTimelineItem | null
  matchingRequirementItem: AgentTimelineItem | null
  runId: string
  toolCallId: string | null
}): AgentTimelineItem {
  const existingTool = payload.existingToolItem?.tool
  const orderIndex = payload.existingToolItem?.order_index
    ?? payload.matchingRequirementItem?.order_index
    ?? nextTimelineOrderIndex(payload.state)
  return {
    id: payload.existingToolItem?.id
      ?? `${payload.requirement.session_id || 'session'}:${payload.runId}:ask-user:${payload.toolCallId || payload.requirement.id || orderIndex}`,
    session_id: payload.requirement.session_id,
    run_id: payload.runId,
    kind: 'tool',
    role: null,
    event_index: payload.existingToolItem?.event_index ?? payload.matchingRequirementItem?.event_index ?? null,
    order_index: orderIndex,
    content: null,
    status: 'completed',
    tool: {
      tool_call_id: payload.toolCallId ?? existingTool?.tool_call_id ?? null,
      tool_name: 'ask_user',
      member_agent_id: payload.requirement.member_agent_id ?? existingTool?.member_agent_id ?? null,
      member_agent_name: payload.requirement.member_agent_name ?? existingTool?.member_agent_name ?? null,
      member_run_id: payload.requirement.member_run_id ?? existingTool?.member_run_id ?? null,
      status: 'completed',
      input_payload: {
        ...payload.requirement.tool_execution,
        user_feedback_schema: payload.answeredSchema,
        questions: payload.answeredSchema,
      },
      output_payload: payload.outputPayload,
      message: payload.outputPayload,
    },
    source: payload.existingToolItem?.source ?? 'synthetic',
    created_at: payload.existingToolItem?.created_at ?? payload.matchingRequirementItem?.created_at ?? new Date().toISOString(),
  }
}

function resolveToolExecutionCallId(toolExecution: Record<string, unknown>): string | null {
  const value = toolExecution.tool_call_id
  return typeof value === 'string' && value ? value : null
}

function nextTimelineOrderIndex(state: AgentSessionRuntimeState): number {
  return Math.max(-1, ...state.timelineItems.map(item => item.order_index)) + 1
}
