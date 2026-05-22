/**
 * 文件功能：抽离内容助手面板的工具详情、消息归并与展示格式化逻辑，降低组件复杂度。
 */
import type { AgentMessageItem, AgentMessageToolCallItem } from '@/types/api'

export interface ToolCallDetail {
  id: string
  runId: string | null
  toolCallId: string | null
  toolName: string
  memberAgentId?: string | null
  memberAgentName?: string | null
  memberRunId?: string | null
  status: 'running' | 'completed' | 'error'
  assistantMessageId: string | null
  inputPayload: unknown
  outputPayload: unknown
  message: string
  source: 'event' | 'history'
  createdAt: string | null
}

export interface ConversationDisplayItem {
  message: AgentMessageItem
  embeddedTools: ToolCallDetail[]
}

export interface AgentMutationRefreshEvent {
  kind: 'page' | 'project-pages' | 'project' | 'component' | 'asset'
  workspaceId: number | null
  projectId: number | null
  pageId: number | null
  componentId: number | null
  assetId?: number | null
  toolName: string
  result: unknown
}

/**
 * 从 Agno 消息历史中提取工具调用详情，assistant.tool_calls 是唯一位置锚点。
 */
export function extractHistoryToolCallDetails(messages: AgentMessageItem[]): ToolCallDetail[] {
  const toolDetails: ToolCallDetail[] = []
  const toolByCallId = new Map<string, ToolCallDetail>()
  const pendingToolsWithoutCallId = new Map<string, ToolCallDetail[]>()

  for (let index = 0; index < messages.length; index += 1) {
    const message = messages[index]
    if (message.role === 'assistant') {
      const assistantToolCalls = normalizeAssistantToolCalls(message)
      for (let toolIndex = 0; toolIndex < assistantToolCalls.length; toolIndex += 1) {
        const toolCall = assistantToolCalls[toolIndex]
        const runId = message.run_id ?? null
        const toolCallId = readToolCallId(toolCall)
        const detail: ToolCallDetail = {
          id: toolCallId || `history-${message.id}-tool-${toolIndex}`,
          runId,
          toolCallId,
          toolName: readToolCallName(toolCall) || '工具调用',
          memberAgentId: null,
          memberAgentName: null,
          memberRunId: null,
          status: 'running',
          assistantMessageId: message.id,
          inputPayload: readToolCallInput(toolCall),
          outputPayload: null,
          message: '',
          source: 'history',
          createdAt: message.created_at,
        }
        toolDetails.push(detail)
        if (toolCallId) {
          toolByCallId.set(resolveToolCallMapKey(runId, toolCallId), detail)
        } else {
          const pendingTools = pendingToolsWithoutCallId.get(resolveRunKey(runId)) ?? []
          pendingTools.push(detail)
          pendingToolsWithoutCallId.set(resolveRunKey(runId), pendingTools)
        }
      }
      continue
    }
    if (message.role !== 'tool') {
      continue
    }
    const matchedTool = resolveHistoryToolResultMatch(message, toolByCallId, pendingToolsWithoutCallId)
    if (matchedTool) {
      mergeToolMessageIntoDetail(matchedTool, message)
      continue
    }
    toolDetails.push({
      id: message.tool_call_id || `history-${message.id}`,
      runId: message.run_id ?? null,
      toolCallId: message.tool_call_id,
      toolName: message.tool_name || '工具调用',
      memberAgentId: null,
      memberAgentName: null,
      memberRunId: null,
      status: message.tool_call_error ? 'error' : 'completed',
      assistantMessageId: resolveAdjacentToolAssistantId(messages, index),
      inputPayload: message.tool_args,
      outputPayload: parseStructuredPayload(message.content),
      message: message.content,
      source: 'history',
      createdAt: message.created_at,
    })
  }

  return toolDetails
}

/**
 * 标准化 assistant.tool_calls，兼容 Agno 与 OpenAI 风格的工具调用结构。
 */
function normalizeAssistantToolCalls(message: AgentMessageItem): AgentMessageToolCallItem[] {
  if (!Array.isArray(message.tool_calls)) {
    return []
  }
  return message.tool_calls.filter(isToolCallPayload)
}

/**
 * 读取工具调用 ID，优先使用 OpenAI 风格 id，再兼容 Agno 字段。
 */
function readToolCallId(toolCall: AgentMessageToolCallItem) {
  return readStringProperty(toolCall, 'id') ?? readStringProperty(toolCall, 'tool_call_id')
}

/**
 * 读取工具名称，兼容 function.name、name 与 tool_name。
 */
function readToolCallName(toolCall: AgentMessageToolCallItem) {
  const functionPayload = readRecordProperty(toolCall, 'function')
  if (isRecord(functionPayload)) {
    const functionName = readStringProperty(functionPayload, 'name')
    if (functionName) {
      return functionName
    }
  }
  return readStringProperty(toolCall, 'name') ?? readStringProperty(toolCall, 'tool_name')
}

/**
 * 读取工具输入参数；字符串参数会尽量解析为结构化 JSON。
 */
function readToolCallInput(toolCall: AgentMessageToolCallItem) {
  const functionPayload = readRecordProperty(toolCall, 'function')
  if (isRecord(functionPayload)) {
    const functionArguments = readRecordProperty(functionPayload, 'arguments')
    if (functionArguments !== undefined) {
      return parseStructuredPayload(functionArguments)
    }
  }
  const argumentsPayload = readRecordProperty(toolCall, 'arguments')
  if (argumentsPayload !== undefined) {
    return parseStructuredPayload(argumentsPayload)
  }
  return parseStructuredPayload(readRecordProperty(toolCall, 'tool_args') ?? null)
}

/**
 * 用 tool_call_id 匹配后续 tool 结果；无 ID 时只在同 run 的未完成调用中按顺序匹配。
 */
function resolveHistoryToolResultMatch(
  message: AgentMessageItem,
  toolByCallId: Map<string, ToolCallDetail>,
  pendingToolsWithoutCallId: Map<string, ToolCallDetail[]>,
) {
  const runId = message.run_id ?? null
  if (message.tool_call_id) {
    return toolByCallId.get(resolveToolCallMapKey(runId, message.tool_call_id)) ?? null
  }
  const pendingTools = pendingToolsWithoutCallId.get(resolveRunKey(runId))
  return pendingTools?.shift() ?? null
}

/**
 * 将 Agno tool 结果消息补充到对应的 assistant.tool_calls 详情上。
 */
function mergeToolMessageIntoDetail(detail: ToolCallDetail, message: AgentMessageItem) {
  detail.toolCallId = message.tool_call_id ?? detail.toolCallId
  detail.toolName = message.tool_name || detail.toolName
  detail.status = message.tool_call_error ? 'error' : 'completed'
  detail.inputPayload = message.tool_args ?? detail.inputPayload
  detail.outputPayload = parseStructuredPayload(message.content)
  detail.message = message.content
  detail.createdAt = message.created_at ?? detail.createdAt
}

/**
 * 兼容旧历史中只有 tool 消息、没有 assistant.tool_calls 的情况，只在相邻回合内找锚点。
 */
function resolveAdjacentToolAssistantId(messages: AgentMessageItem[], toolIndex: number) {
  const runId = messages[toolIndex].run_id ?? null
  const previousUserIndex = findPreviousRoleIndex(messages, toolIndex, 'user')
  const nextUserIndex = findNextRoleIndex(messages, toolIndex, 'user')
  const turnStart = previousUserIndex + 1
  const turnEnd = nextUserIndex >= 0 ? nextUserIndex : messages.length
  const previousAssistant = findPreviousRoleIndex(messages, toolIndex, 'assistant', turnStart, runId)
  if (previousAssistant >= 0) {
    return messages[previousAssistant].id
  }
  const nextAssistant = findNextRoleIndex(messages, toolIndex, 'assistant', turnEnd, runId)
  if (nextAssistant >= 0) {
    return messages[nextAssistant].id
  }
  return null
}

/**
 * 向前查找指定角色消息，可选限制最小索引和 run_id。
 */
function findPreviousRoleIndex(
  messages: AgentMessageItem[],
  startIndex: number,
  role: AgentMessageItem['role'],
  minIndex = 0,
  runId: string | null = null,
) {
  for (let index = startIndex - 1; index >= minIndex; index -= 1) {
    if (messages[index].role === role && messageMatchesRun(messages[index], runId)) {
      return index
    }
  }
  return -1
}

/**
 * 向后查找指定角色消息，可选限制最大索引和 run_id。
 */
function findNextRoleIndex(
  messages: AgentMessageItem[],
  startIndex: number,
  role: AgentMessageItem['role'],
  maxIndex = messages.length,
  runId: string | null = null,
) {
  for (let index = startIndex + 1; index < maxIndex; index += 1) {
    if (messages[index].role === role && messageMatchesRun(messages[index], runId)) {
      return index
    }
  }
  return -1
}

/**
 * 判断消息是否属于同一个 run；缺少 run_id 的旧消息只在无法判断时参与相邻匹配。
 */
function messageMatchesRun(message: AgentMessageItem, runId: string | null) {
  if (!runId) {
    return true
  }
  return !message.run_id || message.run_id === runId
}

/**
 * 构造同 run 下 tool_call_id 的稳定索引键。
 */
function resolveToolCallMapKey(runId: string | null, toolCallId: string) {
  return `${resolveRunKey(runId)}:${toolCallId}`
}

/**
 * 构造 run 维度索引键。
 */
function resolveRunKey(runId: string | null) {
  return runId || 'run-unbound'
}

/**
 * 判断 unknown 是否是可读取的工具调用对象。
 */
function isToolCallPayload(value: unknown): value is AgentMessageToolCallItem {
  return isRecord(value)
}

/**
 * 判断 unknown 是否是普通对象。
 */
function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}

/**
 * 从普通对象读取字段，避免对不同来源的 JSON 结构做强制类型假设。
 */
function readRecordProperty(payload: unknown, key: string) {
  if (!isRecord(payload)) {
    return undefined
  }
  return payload[key]
}

/**
 * 从普通对象读取非空字符串字段。
 */
function readStringProperty(payload: unknown, key: string) {
  const value = readRecordProperty(payload, key)
  if (typeof value !== 'string') {
    return null
  }
  const trimmed = value.trim()
  return trimmed || null
}

/**
 * 合并实时事件和历史缓存，历史消息锚点优先，缓存只补输入输出等详情。
 */
export function mergeToolCallDetails(
  historyTools: ToolCallDetail[],
  eventTools: ToolCallDetail[],
): ToolCallDetail[] {
  const mergedMap = new Map<string, ToolCallDetail>()

  for (const tool of historyTools) {
    mergedMap.set(resolveToolIdentity(tool), tool)
  }

  for (const tool of eventTools) {
    const identity = resolveToolIdentity(tool)
    const historyTool = mergedMap.get(identity)
    if (!historyTool) {
      if (tool.source === 'history') {
        continue
      }
      mergedMap.set(identity, tool)
      continue
    }
    mergedMap.set(identity, {
      ...historyTool,
      ...tool,
      toolCallId: tool.toolCallId ?? historyTool.toolCallId,
      memberAgentId: tool.memberAgentId ?? historyTool.memberAgentId,
      memberAgentName: tool.memberAgentName ?? historyTool.memberAgentName,
      memberRunId: tool.memberRunId ?? historyTool.memberRunId,
      runId: tool.runId ?? historyTool.runId,
      assistantMessageId: historyTool.assistantMessageId ?? tool.assistantMessageId,
      inputPayload: tool.inputPayload ?? historyTool.inputPayload,
      outputPayload: tool.outputPayload ?? historyTool.outputPayload,
      message: tool.message || historyTool.message,
      createdAt: tool.createdAt ?? historyTool.createdAt,
    })
  }

  return [...mergedMap.values()]
}

/**
 * 解析消息流与工具调用明细，构造面向渲染的对话项。
 */
export function buildConversationDisplayItems(
  messages: AgentMessageItem[],
  tools: ToolCallDetail[],
): ConversationDisplayItem[] {
  const items: ConversationDisplayItem[] = []
  const assistantItemMap = new Map<string, ConversationDisplayItem>()
  const lastAssistantIdByRun = new Map<string, string>()
  let lastAssistantId: string | null = null

  for (const message of messages) {
    if (message.role === 'tool') {
      continue
    }
    const nextItem: ConversationDisplayItem = {
      message,
      embeddedTools: [],
    }
    items.push(nextItem)
    if (message.role === 'assistant') {
      assistantItemMap.set(message.id, nextItem)
      lastAssistantId = message.id
      if (message.run_id) {
        lastAssistantIdByRun.set(message.run_id, message.id)
      }
    }
  }

  for (const tool of tools) {
    const targetAssistantId = tool.assistantMessageId ?? (
      tool.source === 'event'
        ? (tool.runId ? lastAssistantIdByRun.get(tool.runId) : null) ?? lastAssistantId
        : null
    )
    if (!targetAssistantId) {
      continue
    }
    const assistantItem = assistantItemMap.get(targetAssistantId)
    if (!assistantItem) {
      continue
    }
    assistantItem.embeddedTools.push(tool)
  }

  return items
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
  if (message.includes('Unified Diff 无法应用')) {
    return {
      title: '页面写回失败',
      detail: `${message} 请先重新读取当前页面源码，再生成新的结构化 edits。若页面已被手工修改，旧编辑不能直接复用。`,
    }
  }
  return {
    title: `${agentDisplayName}执行失败`,
    detail: message,
  }
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
 * 把工具 identity 统一折叠为稳定键，便于历史与实时详情合并。
 */
function resolveToolIdentity(tool: ToolCallDetail) {
  if (tool.toolCallId) {
    return `tool-call:${tool.toolCallId}`
  }
  return [
    tool.runId || 'run-unbound',
    tool.assistantMessageId || 'assistant-unbound',
    tool.toolName,
    normalizeToolPayloadForKey(tool.outputPayload, tool.message),
  ].join('|')
}

/**
 * 将工具输出压平成稳定键值，供去重与归并时使用。
 */
function normalizeToolPayloadForKey(payload: unknown, fallbackMessage: string) {
  const resolved = payload ?? fallbackMessage
  if (resolved === null || resolved === undefined || resolved === '') {
    return 'empty'
  }
  if (typeof resolved === 'string') {
    return resolved
  }
  try {
    return JSON.stringify(resolved)
  } catch {
    return String(resolved)
  }
}
