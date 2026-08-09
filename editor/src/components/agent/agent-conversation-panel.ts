/**
 * 文件功能：抽离内容助手面板的 run-first 时间线展示、工具详情与格式化逻辑。
 */
import type {
  AgentMemberRunItem,
  AgentMessageAttachmentItem,
  AgentMessageItem,
  AgentPendingRequirement,
  AgentRunContextSummary,
  AgentTimelineItem,
  AgentUserFeedbackQuestion,
} from '@/types/api'
import {
  collectEntityChangesByRun,
  isRunTerminalForEntitySummary,
  type AgentEntityChangeItem,
} from '@/components/agent/agent-entity-change-summary'

export interface ToolCallDetail {
  id: string
  runId: string | null
  toolCallId: string | null
  toolName: string
  memberAgentId?: string | null
  memberAgentName?: string | null
  memberRunId?: string | null
  status: 'running' | 'completed' | 'error' | 'interrupted'
  inputPayload: unknown
  outputPayload: unknown
  message: string
  progress: { phase?: string, message?: string, current?: number, total?: number } | null
  source: 'event' | 'message' | 'synthetic'
  createdAt: string | null
  delegatedMemberRuns: AgentMemberRunItem[]
  attachments: AgentMessageAttachmentItem[]
  inputAttachments: AgentMessageAttachmentItem[]
  outputAttachments: AgentMessageAttachmentItem[]
}

export interface FeedbackRequestEntry {
  question: string
  answerText: string | null
}

export type TimelineDisplayItem =
  | { id: string, kind: 'run_context', item: AgentTimelineItem, context: AgentRunContextSummary }
  | { id: string, kind: 'message', item: AgentTimelineItem, message: AgentMessageItem }
  | { id: string, kind: 'reasoning', item: AgentTimelineItem, content: string, streaming: boolean }
  | { id: string, kind: 'tool_group', items: AgentTimelineItem[], tools: ToolCallDetail[] }
  | {
    id: string
    kind: 'feedback_request'
    item: AgentTimelineItem
    requirement: AgentPendingRequirement | null
    tool: ToolCallDetail | null
    entries: FeedbackRequestEntry[]
    pending: boolean
    status: string | null
  }
  | { id: string, kind: 'entity_summary', runId: string, items: AgentEntityChangeItem[] }
  | { id: string, kind: 'run_status', item: AgentTimelineItem, status: string | null, content: string }
  | { id: string, kind: 'requirement', item: AgentTimelineItem, status: string | null, content: string }

export interface AgentMutationRefreshEvent {
  kind: 'page' | 'project-pages' | 'project' | 'component' | 'asset' | 'theme' | 'style'
  workspaceId: number | null
  projectId: number | null
  pageId: number | null
  componentId: number | null
  assetId?: number | null
  themeId?: number | null
  styleId?: number | null
  toolName: string
  result: unknown
}

/**
 * 将 timeline tool item 转成弹窗与工具卡片统一使用的详情结构。
 */
export function toolDetailFromTimelineItem(item: AgentTimelineItem, memberRuns: AgentMemberRunItem[] = []): ToolCallDetail | null {
  if (item.kind !== 'tool' || !item.tool) {
    return null
  }
  const delegateToolCallId = item.tool.tool_call_id || item.id
  const hideFailedGeneratedOutput = item.tool.tool_name === 'generate_image' && item.tool.status === 'error'
  return {
    id: item.id,
    runId: item.run_id || null,
    toolCallId: item.tool.tool_call_id,
    toolName: resolveLogicalToolName(item.tool.tool_name || '工具调用', item.tool.input_payload),
    memberAgentId: item.tool.member_agent_id ?? null,
    memberAgentName: item.tool.member_agent_name ?? null,
    memberRunId: item.tool.member_run_id ?? null,
    status: item.tool.status,
    inputPayload: item.tool.input_payload,
    outputPayload: item.tool.output_payload,
    message: item.tool.message,
    progress: item.tool.progress ?? null,
    source: item.source,
    createdAt: item.created_at,
    attachments: hideFailedGeneratedOutput ? [] : item.attachments ?? [],
    inputAttachments: item.tool.input_attachments ?? [],
    outputAttachments: hideFailedGeneratedOutput ? [] : item.tool.output_attachments ?? item.attachments ?? [],
    delegatedMemberRuns: isDelegateToolName(item.tool.tool_name)
      ? memberRuns.filter(memberRun => (
          memberRun.parent_run_id === item.run_id
          && (
            memberRun.delegate_tool_call_id === delegateToolCallId
            || (!memberRun.delegate_tool_call_id && delegateToolMatchesMember(item.tool?.input_payload, memberRun.agent_id))
          )
        ))
      : [],
  }
}

/**
 * 把固定通用工具名转换为用户可读的真实逻辑操作。
 */
export function resolveLogicalToolName(toolName: string, inputPayload: unknown): string {
  // query_entities 已退出运行时目录，仅保留识别以兼容历史会话工具卡。
  if (!['query_entities', 'list_entities', 'get_entity', 'create_entity', 'update_entity', 'archive_entity', 'validate_entity', 'execute_action', 'execute_dangerous_action', 'get_operation_guide'].includes(toolName)) {
    return toolName
  }
  const payload = isRecord(inputPayload) ? inputPayload : {}
  const operationKey = String(payload.operation_key || '')
  const operationResourceType = operationKey.split('.')[0] || ''
  const resourceLabel = {
    project: '项目',
    page: '页面',
    component: '组件',
    asset: '资源',
    theme: '主题',
    style: '样式',
    runtime_kit: 'Runtime Kit',
    font: '字体',
  }[String(payload.resource_type || operationResourceType)] || '业务对象'
  if (toolName === 'get_operation_guide') {
    return operationKey ? `查看${resourceLabel}操作手册` : '查看操作手册索引'
  }
  if (toolName === 'query_entities') return `查询${resourceLabel}`
  if (toolName === 'list_entities') return `罗列${resourceLabel}`
  if (toolName === 'get_entity') return `读取${resourceLabel}`
  if (toolName === 'create_entity') {
    const mode = String(payload.mode || 'new')
    if (mode === 'copy') return `复制${resourceLabel}`
    if (mode === 'upload') return `从上传创建${resourceLabel}`
    return `创建${resourceLabel}`
  }
  if (toolName === 'update_entity') return `修改${resourceLabel}`
  if (toolName === 'validate_entity') return actionLabelForValidation(payload.action, resourceLabel)
  if (toolName === 'archive_entity') {
    const count = Array.isArray(payload.target_ids) ? payload.target_ids.length : 0
    return count > 1 ? `批量归档${resourceLabel}` : `归档${resourceLabel}`
  }
  const action = String(payload.action || '')
  const fullActionLabel: Record<string, string> = {
    replace_routes: '覆盖项目路由',
    replace_style_config: '覆盖项目样式配置',
    rename_key: '重命名主题 Key',
  }
  if (fullActionLabel[action]) return fullActionLabel[action]
  const actionLabel = {
    // restore 已退出运行时动作，仅保留历史工具卡名称回放。
    restore: '恢复',
    publish: '发布',
    copy: '复制',
    check: '检查',
  }[action] || '执行操作'
  return `${actionLabel}${resourceLabel}`
}

function actionLabelForValidation(action: unknown, resourceLabel: string): string {
  return String(action || '') === 'preview' ? `预览${resourceLabel}改动` : `检查${resourceLabel}`
}

/** 判断未知值是否为普通对象。 */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * 将 run-first 时间线转换成渲染项，普通工具轻量折叠，ask_user 作为提问卡片展示。
 */
export function buildTimelineDisplayItems(
  timelineItems: AgentTimelineItem[],
  options: {
    pendingRequirement?: AgentPendingRequirement | null
    memberRuns?: AgentMemberRunItem[]
    workspaceId?: number | null
    activeRunId?: string | null
  } = {},
): TimelineDisplayItem[] {
  const orderedItems = [...timelineItems].sort(compareTimelineItems)
  const displayItems: TimelineDisplayItem[] = []
  const pendingRequirement = options.pendingRequirement ?? null
  const memberRuns = options.memberRuns ?? []
  const workspaceId = options.workspaceId ?? null
  const activeRunId = options.activeRunId ?? null
  const entityChangesByRun = collectEntityChangesByRun(orderedItems, memberRuns, workspaceId)
  const insertedEntitySummaryRunIds = new Set<string>()
  const skippedRequirementIds = new Set<string>()
  let pendingTools: AgentTimelineItem[] = []
  for (const item of orderedItems) {
    if (!isAskUserToolItem(item)) {
      continue
    }
    const requirementItem = findMatchingAskUserRequirement(orderedItems, item, pendingRequirement)
    if (requirementItem) {
      skippedRequirementIds.add(requirementItem.id)
    }
  }

  const flushPendingTools = () => {
    if (!pendingTools.length) {
      return
    }
    const tools = pendingTools
      .map(item => toolDetailFromTimelineItem(item, memberRuns))
      .filter((tool): tool is ToolCallDetail => tool !== null)
    if (tools.length) {
      displayItems.push({
        id: `tool-group:${pendingTools.map(item => item.id).join('|')}`,
        kind: 'tool_group',
        items: [...pendingTools],
        tools,
      })
    }
    pendingTools = []
  }

  for (const item of orderedItems) {
    if (isCurrentPendingAskUserTimelineItem(item, pendingRequirement)) {
      continue
    }
    if (skippedRequirementIds.has(item.id)) {
      continue
    }
    if (item.kind === 'tool') {
      if (isAskUserToolItem(item)) {
        flushPendingTools()
        const matchedRequirement = findMatchingAskUserRequirement(orderedItems, item, pendingRequirement)
          ? pendingRequirement
          : null
        displayItems.push(buildFeedbackRequestDisplayItem(item, matchedRequirement, toolDetailFromTimelineItem(item, memberRuns)))
        continue
      }
      pendingTools.push(item)
      continue
    }
    flushPendingTools()
    if (item.kind === 'run_context' && item.run_context) {
      displayItems.push({
        id: item.id,
        kind: 'run_context',
        item,
        context: item.run_context,
      })
      continue
    }
    if (item.kind === 'message' && (item.role === 'user' || item.role === 'assistant')) {
      displayItems.push({
        id: item.id,
        kind: 'message',
        item,
        message: buildDisplayMessage(item),
      })
      continue
    }
    if (item.kind === 'reasoning') {
      displayItems.push({
        id: item.id,
        kind: 'reasoning',
        item,
        content: item.content ?? '',
        streaming: item.status === 'running',
      })
      continue
    }
    if (item.kind === 'run_status') {
      displayItems.push({
        id: item.id,
        kind: 'run_status',
        item,
        status: item.status,
        content: item.content || resolveRunStatusText(item.status),
      })
      continue
    }
    if (item.kind === 'requirement') {
      if (!isCurrentPendingRequirementTimelineItem(item, pendingRequirement)) {
        continue
      }
      const requirement = resolveAskUserRequirementForItem(item, pendingRequirement)
      if (requirement) {
        displayItems.push(buildFeedbackRequestDisplayItem(item, requirement, findMatchingAskUserToolDetail(orderedItems, item, requirement)))
        continue
      }
      displayItems.push({
        id: item.id,
        kind: 'requirement',
        item,
        status: item.status,
        content: item.content || '等待用户处理。',
      })
    }
  }
  flushPendingTools()
  insertEntitySummaries(displayItems, entityChangesByRun, insertedEntitySummaryRunIds, activeRunId)
  return displayItems
}

/**
 * 在每个已终态 run 的助手消息与工具组之后、run_status 之前插入实体变更摘要卡。
 * 不依赖时间线中的 run_status 项：后端主 run 快照通常不含该 kind。
 */
function insertEntitySummaries(
  displayItems: TimelineDisplayItem[],
  entityChangesByRun: Map<string, AgentEntityChangeItem[]>,
  insertedRunIds: Set<string>,
  activeRunId: string | null,
) {
  for (const runId of entityChangesByRun.keys()) {
    tryInsertEntitySummaryForRun(displayItems, runId, entityChangesByRun, insertedRunIds, activeRunId)
  }
}

/**
 * 将摘要卡插到本 run「助手消息与工具组」的最后位置之后。
 * 若该位置后紧跟本 run 的 run_status，则插在状态条之前。
 */
function tryInsertEntitySummaryForRun(
  displayItems: TimelineDisplayItem[],
  runId: string | null | undefined,
  entityChangesByRun: Map<string, AgentEntityChangeItem[]>,
  insertedRunIds: Set<string>,
  activeRunId: string | null,
) {
  if (!runId || insertedRunIds.has(runId)) {
    return
  }
  if (!isRunTerminalForEntitySummary(runId, activeRunId)) {
    return
  }
  const items = entityChangesByRun.get(runId)
  if (!items?.length) {
    return
  }

  // 取助手消息与工具组二者中更靠后的锚点，避免卡插在「消息后、后续工具前」。
  let anchorAfter = -1
  for (let index = 0; index < displayItems.length; index += 1) {
    const item = displayItems[index]
    const isAssistantMessage = item.kind === 'message'
      && item.message.role === 'assistant'
      && item.item.run_id === runId
    const isRunToolGroup = item.kind === 'tool_group'
      && item.items.some(toolItem => toolItem.run_id === runId)
    if (isAssistantMessage || isRunToolGroup) {
      anchorAfter = index
    }
  }

  let insertAt = anchorAfter >= 0 ? anchorAfter + 1 : -1
  if (insertAt < 0) {
    // 无消息/工具时，退到本 run 其它展示项之后。
    for (let index = displayItems.length - 1; index >= 0; index -= 1) {
      const item = displayItems[index]
      if (
        (item.kind === 'message' && item.item.run_id === runId)
        || (item.kind === 'reasoning' && item.item.run_id === runId)
        || (item.kind === 'feedback_request' && item.item.run_id === runId)
        || (item.kind === 'run_context' && item.item.run_id === runId)
      ) {
        insertAt = index + 1
        break
      }
    }
  }
  if (insertAt < 0) {
    insertAt = displayItems.length
  }

  // insertAt 落在锚点后一项；若下一项是 run_status，splice 会自然插在状态条之前。
  displayItems.splice(insertAt, 0, {
    id: `entity-summary:${runId}`,
    kind: 'entity_summary',
    runId,
    items,
  })
  insertedRunIds.add(runId)
}

/**
 * 从时间线中提取所有工具详情，供详情弹窗按 id 查询。
 */
export function extractTimelineToolDetails(timelineItems: AgentTimelineItem[], memberRuns: AgentMemberRunItem[] = []): ToolCallDetail[] {
  return [...timelineItems]
    .sort(compareTimelineItems)
    .map(item => toolDetailFromTimelineItem(item, memberRuns))
    .filter((tool): tool is ToolCallDetail => tool !== null)
}

/**
 * 将工具输入输出格式化为可读文本；若是对象则按 JSON 缩进展示。
 */
export function formatToolPayload(payload: unknown, emptyText = '暂无内容。') {
  if (payload === null || payload === undefined || payload === '') {
    return emptyText
  }
  if (typeof payload === 'string') {
    const parsed = parseStructuredPayload(payload)
    if (typeof parsed === 'string') {
      return parsed
    }
    try {
      return JSON.stringify(parsed, null, 2)
    } catch {
      return String(parsed)
    }
  }
  try {
    return JSON.stringify(payload, null, 2)
  } catch {
    return String(payload)
  }
}

/**
 * 将运行失败信息归一化为更适合展示的标题和说明。
 */
export function buildRunIssueState(message: string, agentDisplayName = '内容助手') {
  const normalizedMessage = message.trim()
  if (message.includes('Unified Diff 无法应用')) {
    return {
      title: '页面写回失败',
      detail: `${message} 请先重新读取当前页面源码，再生成新的结构化 edits。若页面已被手工修改，旧编辑不能直接复用。`,
    }
  }
  if (isStreamInterruptedMessage(normalizedMessage)) {
    return {
      title: '模型连接中断',
      detail: '模型服务没有完整返回本次输出，前面已经生成的内容会保留。可以直接重试；如果连续出现，建议把任务拆小，或在 AI 设置里降低模型最大输出和思考强度。',
    }
  }
  if (isModelRequestRejectedMessage(normalizedMessage)) {
    return {
      title: '模型请求被拒绝',
      detail: '模型服务拒绝了本次请求。请检查当前绑定模型名称、模型能力和高级参数配置后再试。',
    }
  }
  if (isRateLimitedMessage(normalizedMessage)) {
    return {
      title: '模型服务繁忙',
      detail: '模型服务当前繁忙或触发限流，请稍后重试。',
    }
  }
  if (isTimeoutMessage(normalizedMessage)) {
    return {
      title: '模型响应超时',
      detail: '模型服务响应超时，本次运行已停止。请稍后重试，或把任务拆成更小的步骤。',
    }
  }
  return {
    title: `${agentDisplayName}执行失败`,
    detail: normalizedMessage || '智能体运行中断，请稍后重试。',
  }
}

function isStreamInterruptedMessage(message: string) {
  const normalized = message.toLowerCase()
  return [
    '模型连接中断',
    'incomplete chunked read',
    'peer closed connection',
    'remote protocol error',
    'server disconnected',
  ].some(pattern => normalized.includes(pattern.toLowerCase()))
}

function isModelRequestRejectedMessage(message: string) {
  const normalized = message.toLowerCase()
  return normalized.includes('模型服务拒绝')
    || normalized.includes('status_code: 400')
    || normalized.includes('invalid_request_error')
}

function isRateLimitedMessage(message: string) {
  const normalized = message.toLowerCase()
  return normalized.includes('模型服务当前繁忙')
    || normalized.includes('status_code: 429')
    || normalized.includes('rate limit')
}

function isTimeoutMessage(message: string) {
  const normalized = message.toLowerCase()
  return normalized.includes('模型服务响应超时')
    || normalized.includes('read timeout')
    || normalized.includes('timed out')
    || normalized.includes('timeout')
}

/**
 * 将实时事件或历史消息中的 payload 解析为结构化对象。
 */
export function parseStructuredPayload(payload: unknown) {
  if (typeof payload !== 'string') {
    return payload
  }
  const trimmed = payload.trim()
  if (!trimmed) {
    return ''
  }
  if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) {
    return payload
  }
  try {
    return JSON.parse(trimmed)
  } catch {
    return payload
  }
}

/**
 * 将时间线消息转换成既有 Markdown 渲染 helper 可消费的消息结构。
 */
function buildDisplayMessage(item: AgentTimelineItem): AgentMessageItem {
  return {
    id: item.id,
    run_id: item.run_id,
    role: item.role === 'user' ? 'user' : 'assistant',
    content: item.content ?? '',
    reasoning_content: null,
    created_at: item.created_at,
    tool_name: null,
    tool_call_id: null,
    tool_args: null,
    tool_call_error: null,
    tool_calls: [],
    attachments: item.attachments ?? [],
  }
}

/**
 * ask_user 是面向用户的提问，不作为普通工具名暴露在主时间线里。
 */
function isAskUserToolItem(item: AgentTimelineItem) {
  return item.kind === 'tool' && item.tool?.tool_name === 'ask_user'
}

/**
 * 判断工具是否为内容助手委派自身子运行的入口。
 */
export function isDelegateToolName(toolName: string | null | undefined) {
  return toolName === 'delegate_task_to_self'
}

function delegateToolMatchesMember(inputPayload: unknown, memberAgentId: string) {
  if (!inputPayload || typeof inputPayload !== 'object' || Array.isArray(inputPayload)) {
    return true
  }
  const memberId = (inputPayload as Record<string, unknown>).member_id
  return typeof memberId !== 'string' || !memberId || memberId === memberAgentId
}

/**
 * 构造提问展示项，优先使用 requirement schema，其次从工具参数里恢复问题。
 */
function buildFeedbackRequestDisplayItem(
  item: AgentTimelineItem,
  requirement: AgentPendingRequirement | null,
  tool: ToolCallDetail | null,
): Extract<TimelineDisplayItem, { kind: 'feedback_request' }> {
  const pending = item.status !== 'completed' && item.status !== 'cancelled'
  return {
    id: `feedback-request:${item.id}`,
    kind: 'feedback_request',
    item,
    requirement,
    tool,
    entries: resolveFeedbackEntries(requirement, tool, item),
    pending,
    status: item.status || 'pending',
  }
}

/**
 * 同 run 且同 tool_call_id 的 ask_user 工具和 requirement 视为同一条提问。
 */
function findMatchingAskUserRequirement(
  items: AgentTimelineItem[],
  toolItem: AgentTimelineItem,
  requirement: AgentPendingRequirement | null,
) {
  if (!requirement || !isAskUserRequirement(requirement) || !itemMatchesRequirement(toolItem, requirement)) {
    return null
  }
  return items.find(item => item.kind === 'requirement' && itemMatchesRequirement(item, requirement)) ?? null
}

/**
 * 从 requirement 反查 ask_user 工具详情，用于恢复已回答内容。
 */
function findMatchingAskUserToolDetail(
  items: AgentTimelineItem[],
  requirementItem: AgentTimelineItem,
  requirement: AgentPendingRequirement,
) {
  const toolItem = items.find(item => (
    isAskUserToolItem(item)
    && item.run_id === requirementItem.run_id
    && itemMatchesRequirement(item, requirement)
  ))
  return toolItem ? toolDetailFromTimelineItem(toolItem) : null
}

function resolveAskUserRequirementForItem(
  item: AgentTimelineItem,
  requirement: AgentPendingRequirement | null,
) {
  if (item.kind !== 'requirement' || !requirement || !isAskUserRequirement(requirement)) {
    return null
  }
  return itemMatchesRequirement(item, requirement) ? requirement : null
}

function isAskUserRequirement(requirement: AgentPendingRequirement) {
  return requirement.kind === 'user_feedback' || requirement.tool_name === 'ask_user'
}

function isCurrentPendingAskUserTimelineItem(item: AgentTimelineItem, requirement: AgentPendingRequirement | null) {
  if (!requirement || !isAskUserRequirement(requirement) || !itemMatchesRequirement(item, requirement)) {
    return false
  }
  if (item.kind === 'requirement') {
    return true
  }
  if (isAskUserToolItem(item)) {
    return item.status !== 'completed' && item.status !== 'cancelled'
  }
  return false
}

function isCurrentPendingRequirementTimelineItem(item: AgentTimelineItem, requirement: AgentPendingRequirement | null) {
  if (item.kind !== 'requirement' || !requirement || item.run_id !== requirement.run_id) {
    return false
  }
  const requirementId = requirement.id?.trim()
  if (requirementId) {
    return item.id === requirementId
      || item.id === `requirement-${requirementId}`
      || item.id.endsWith(`:${requirementId}`)
  }
  const toolCallId = resolveToolExecutionCallId(requirement.tool_execution)
  if (toolCallId && (item.id === toolCallId || item.id.endsWith(`:${toolCallId}`))) {
    return true
  }
  return true
}

function itemMatchesRequirement(item: AgentTimelineItem, requirement: AgentPendingRequirement) {
  if (item.run_id !== requirement.run_id) {
    return false
  }
  const requirementCallId = resolveToolExecutionCallId(requirement.tool_execution)
  if (item.tool?.tool_call_id && requirementCallId) {
    return item.tool.tool_call_id === requirementCallId
  }
  return true
}

function resolveToolExecutionCallId(toolExecution: Record<string, unknown>) {
  const value = toolExecution.tool_call_id
  return typeof value === 'string' && value ? value : null
}

function resolveFeedbackEntries(
  requirement: AgentPendingRequirement | null,
  tool: ToolCallDetail | null,
  item: AgentTimelineItem,
): FeedbackRequestEntry[] {
  const questions = resolveFeedbackQuestions(requirement, tool, item)
  const answersByQuestion = resolveAskUserAnswers(tool?.outputPayload)
  if (questions.length) {
    return questions.map(question => ({
      question: question.question,
      answerText: answersByQuestion.get(question.question) ?? resolveQuestionSelectedText(question),
    }))
  }
  const answeredEntries = [...answersByQuestion.entries()]
    .filter((entry): entry is [string, string] => Boolean(entry[0] && entry[1]))
    .map(([question, answerText]) => ({ question, answerText }))
  if (answeredEntries.length) {
    return answeredEntries
  }
  return [{
    question: item.content?.trim() || requirement?.note?.trim() || '需要补充信息',
    answerText: null,
  }]
}

function resolveAskUserAnswers(outputPayload: unknown) {
  const parsed = parseFeedbackResultPayload(outputPayload)
  const answers = new Map<string, string>()
  if (!Array.isArray(parsed)) {
    return answers
  }
  for (const item of parsed) {
    if (!item || typeof item !== 'object' || Array.isArray(item)) {
      continue
    }
    const record = item as Record<string, unknown>
    const question = typeof record.question === 'string' ? record.question.trim() : ''
    const answerText = resolveFeedbackAnswerText(
      record.custom_text ?? record.selected ?? record.selected_options ?? record.selected_label ?? record.answer,
    )
    if (question && answerText) {
      answers.set(question, answerText)
    }
  }
  return answers
}

function parseFeedbackResultPayload(outputPayload: unknown) {
  if (Array.isArray(outputPayload)) {
    return outputPayload
  }
  if (typeof outputPayload !== 'string') {
    return null
  }
  const text = outputPayload.trim()
  const match = text.match(/User feedback received:\s*(\[[\s\S]*\])$/)
  const jsonText = match ? match[1] : text.startsWith('[') ? text : ''
  if (!jsonText) {
    return null
  }
  try {
    return JSON.parse(jsonText)
  } catch {
    return null
  }
}

function resolveQuestionSelectedText(question: AgentUserFeedbackQuestion) {
  const selectedOptions = question.selected_options?.length
    ? question.selected_options
    : question.options.filter(option => option.selected).map(option => option.label)
  return resolveFeedbackAnswerText(selectedOptions)
}

function resolveFeedbackAnswerText(value: unknown): string | null {
  if (Array.isArray(value)) {
    const parts = value
      .map(normalizeFeedbackAnswerValue)
      .filter((item): item is string => Boolean(item))
    return parts.length ? parts.join('、') : null
  }
  return normalizeFeedbackAnswerValue(value)
}

function normalizeFeedbackAnswerValue(value: unknown) {
  if (typeof value !== 'string') {
    return value === null || value === undefined ? null : String(value)
  }
  const trimmed = value.trim()
  if (!trimmed) {
    return null
  }
  return trimmed.startsWith('用户补充：') ? trimmed.slice('用户补充：'.length).trim() || null : trimmed
}

function resolveFeedbackQuestions(
  requirement: AgentPendingRequirement | null,
  tool: ToolCallDetail | null,
  item: AgentTimelineItem,
): AgentUserFeedbackQuestion[] {
  for (const source of [
    requirement?.user_feedback_schema,
    resolveFeedbackSchema(requirement?.tool_execution),
    resolveFeedbackSchema(tool?.inputPayload),
    resolveFeedbackSchema(item.tool?.input_payload),
  ]) {
    const questions = normalizeFeedbackQuestions(source)
    if (questions.length) {
      return questions
    }
  }
  return []
}

function resolveFeedbackSchema(payload: unknown): unknown {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return null
  }
  const record = payload as Record<string, unknown>
  if (Array.isArray(record.user_feedback_schema)) {
    return record.user_feedback_schema
  }
  if (Array.isArray(record.questions)) {
    return record.questions
  }
  const toolArgs = record.tool_args
  if (toolArgs && typeof toolArgs === 'object' && !Array.isArray(toolArgs)) {
    const args = toolArgs as Record<string, unknown>
    if (Array.isArray(args.questions)) {
      return args.questions
    }
  }
  return null
}

function normalizeFeedbackQuestions(value: unknown): AgentUserFeedbackQuestion[] {
  if (!Array.isArray(value)) {
    return []
  }
  return value
    .filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null && !Array.isArray(item))
    .map(item => ({
      question: typeof item.question === 'string' ? item.question : '',
      header: typeof item.header === 'string' ? item.header : '',
      multi_select: false,
      options: Array.isArray(item.options)
        ? item.options
            .filter((option): option is Record<string, unknown> => typeof option === 'object' && option !== null && !Array.isArray(option))
            .map(option => ({
              label: typeof option.label === 'string' ? option.label : '',
              description: typeof option.description === 'string' ? option.description : '',
              selected: typeof option.selected === 'boolean' ? option.selected : undefined,
            }))
            .filter(option => option.label)
        : [],
      selected_options: Array.isArray(item.selected_options)
        ? item.selected_options.filter((option): option is string => typeof option === 'string')
        : null,
    }))
    .filter(item => item.question)
}

/**
 * 时间线排序以 order_index 为主，缺失时用 event_index 和 id 兜底。
 */
function compareTimelineItems(left: AgentTimelineItem, right: AgentTimelineItem) {
  if (left.order_index !== right.order_index) {
    return left.order_index - right.order_index
  }
  const leftEventIndex = left.event_index ?? Number.MAX_SAFE_INTEGER
  const rightEventIndex = right.event_index ?? Number.MAX_SAFE_INTEGER
  if (leftEventIndex !== rightEventIndex) {
    return leftEventIndex - rightEventIndex
  }
  return left.id.localeCompare(right.id)
}

/**
 * 为缺少文案的运行状态项补齐前端兜底展示。
 */
function resolveRunStatusText(status: string | null) {
  if (status === 'failed') return '运行失败。'
  if (status === 'cancelled') return '运行已停止。'
  if (status === 'paused') return '等待用户处理。'
  if (status === 'waiting_external') return '页面变更正在后台处理。'
  if (status === 'completed') return '运行已完成。'
  return '运行状态已更新。'
}
