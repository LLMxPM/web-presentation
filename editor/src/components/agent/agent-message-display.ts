/**
 * 文件功能：提供智能体消息展示所需的时间、Markdown 与 reasoning 内容格式化逻辑。
 */
import { parseMarkdownToStructure, type BaseNode } from 'markstream-vue'

import type { AgentMessageItem } from '@/types/api'
import type { ToolCallDetail } from '@/components/agent/agent-conversation-panel'
import { formatDateTime } from '@/utils/format'
import { APP_TIMEZONE } from '@/utils/timezone'

export const toolStatusLabelMap: Record<ToolCallDetail['status'], string> = {
  running: '进行中',
  completed: '已完成',
  error: '失败',
}

/**
 * 多条连续工具调用中存在运行中或失败项时，默认展开便于及时查看状态。
 */
export function shouldExpandToolGroup(tools: ToolCallDetail[]) {
  return tools.some(tool => tool.status !== 'completed')
}

/**
 * 生成折叠工具组摘要，避免多次连续工具调用挤占对话正文空间。
 */
export function formatToolGroupSummary(tools: ToolCallDetail[]) {
  const statusOrder: ToolCallDetail['status'][] = ['running', 'error', 'completed']
  const parts = statusOrder
    .map((status) => {
      const count = tools.filter(tool => tool.status === status).length
      return count > 0 ? `${count} ${toolStatusLabelMap[status]}` : ''
    })
    .filter(Boolean)
  return `${tools.length} 次工具调用${parts.length ? ` · ${parts.join(' / ')}` : ''}`
}

/**
 * 根据工具状态返回弱化行样式，避免工具调用比助手正文更抢眼。
 */
export function getToolChipClass(status: ToolCallDetail['status']) {
  if (status === 'error') {
    return 'border-red-200 text-red-600 hover:bg-red-50/40'
  }
  if (status === 'running') {
    return 'border-slate-300 text-slate-600 hover:bg-slate-50'
  }
  return 'border-slate-200 text-slate-500 hover:bg-slate-50'
}

/**
 * 返回工具详情来源标签文案。
 */
export function getToolSourceLabel(source: ToolCallDetail['source']) {
  if (source === 'message') {
    return '历史消息'
  }
  if (source === 'synthetic') {
    return '本地状态'
  }
  return '本轮运行采集'
}

/**
 * 格式化 token 数，减少上下文状态面板中的长数字噪声。
 */
export function formatTokenCount(value: number | null | undefined) {
  const normalized = Number(value ?? 0)
  if (!Number.isFinite(normalized)) {
    return '0 tokens'
  }
  return `${Math.round(normalized).toLocaleString('zh-CN')} tokens`
}

/**
 * 消息流内使用更短的时间：当天只显示时分，跨天补充月日。
 */
export function formatMessageTime(value: string | null | undefined) {
  if (!value) {
    return ''
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return formatDateTime(value)
  }
  const targetDate = getAppDateParts(date)
  const today = getAppDateParts(new Date())
  const timeText = formatAppTime(date)
  if (targetDate.key === today.key) {
    return timeText
  }
  return `${targetDate.month}/${targetDate.day} ${timeText}`
}

/**
 * 只有空 assistant 占位才显示省略号；已有思考过程或工具调用时不再额外占位。
 */
export function shouldShowAssistantPlaceholder(
  item: { message: AgentMessageItem, embeddedTools: ToolCallDetail[] },
  isStreamingMessage: (message: AgentMessageItem) => boolean,
) {
  return !resolveMessageContent(item.message)
    && !resolveMessageReasoning(item.message, isStreamingMessage)
    && item.embeddedTools.length === 0
}

/**
 * 返回消息正文，兜底移除模型直接输出的 think/reasoning 标签块。
 */
export function resolveMessageContent(message: AgentMessageItem | undefined) {
  if (!message) return ''
  return splitInlineReasoning(message.content).content
}

/**
 * 按 markstream-vue 文档推荐，流式场景预解析为 nodes 再交给渲染器。
 */
export function resolveMessageMarkdownNodes(
  message: AgentMessageItem,
  markdownParser: Parameters<typeof parseMarkdownToStructure>[1],
  isStreamingMessage: (message: AgentMessageItem) => boolean,
): BaseNode[] {
  return parseMarkdownToStructure(resolveMessageContent(message), markdownParser, {
    final: !isStreamingMessage(message),
  })
}

/**
 * 思考过程也使用 Markdown 结构渲染，但保持更弱的视觉层级。
 */
export function resolveMessageReasoningMarkdownNodes(
  message: AgentMessageItem,
  markdownParser: Parameters<typeof parseMarkdownToStructure>[1],
  isStreamingMessage: (message: AgentMessageItem) => boolean,
): BaseNode[] {
  return parseMarkdownToStructure(resolveMessageReasoning(message, isStreamingMessage), markdownParser, {
    final: !isStreamingMessage(message),
  })
}

/**
 * 返回消息思考内容，优先使用后端拆出的 reasoning_content。
 */
export function resolveMessageReasoning(
  message: AgentMessageItem | undefined,
  isStreamingMessage: (message: AgentMessageItem) => boolean,
) {
  if (!message) return ''
  const parsed = splitInlineReasoning(message.content)
  const preserveBoundary = isStreamingMessage(message)
  return [
    normalizeReasoningForDisplay(message.reasoning_content, preserveBoundary),
    normalizeReasoningForDisplay(parsed.reasoning, preserveBoundary),
  ]
    .filter(Boolean)
    .join('\n\n')
}

/**
 * 判断某条 assistant 消息是否仍处于当前流式输出阶段。
 */
export function createMessageStreamingResolver(
  isStreaming: () => boolean,
  getStreamingTimelineItemId: () => string | null,
) {
  return (message: AgentMessageItem) => (
    isStreaming()
    && message.role === 'assistant'
    && message.id === getStreamingTimelineItemId()
  )
}

/**
 * 按业务时区提取消息日期，避免浏览器本地时区影响当天判断。
 */
function getAppDateParts(value: Date) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
    timeZone: APP_TIMEZONE,
  }).formatToParts(value)
  const year = parts.find(part => part.type === 'year')?.value ?? ''
  const month = parts.find(part => part.type === 'month')?.value ?? ''
  const day = parts.find(part => part.type === 'day')?.value ?? ''
  return {
    key: `${year}-${month}-${day}`,
    month,
    day,
  }
}

/**
 * 按业务时区输出消息使用的时分。
 */
function formatAppTime(value: Date) {
  return new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: APP_TIMEZONE,
  }).format(value)
}

/**
 * 历史消息去掉外层空白，流式消息保留尾随换行以便即时显示段落边界。
 */
function normalizeReasoningForDisplay(value: string | null | undefined, preserveBoundary: boolean) {
  if (typeof value !== 'string' || !value.trim()) {
    return ''
  }
  return preserveBoundary ? value : value.trim()
}

/**
 * 把正文里内嵌的 reasoning/think 标签拆开，避免流式阶段直接露出 XML 标签。
 */
function splitInlineReasoning(content: string) {
  const reasoningParts: string[] = []
  let nextContent = content
  for (const pattern of [
    /<reasoning>([\s\S]*?)<\/reasoning>/gi,
    /<think>([\s\S]*?)<\/think>/gi,
  ]) {
    nextContent = nextContent.replace(pattern, (_match, reasoning: string) => {
      if (reasoning.trim()) {
        reasoningParts.push(reasoning.trim())
      }
      return ''
    })
  }
  const openTagMatch = nextContent.match(/<(reasoning|think)>/i)
  if (openTagMatch?.index !== undefined) {
    const beforeReasoning = nextContent.slice(0, openTagMatch.index)
    const afterReasoning = nextContent.slice(openTagMatch.index + openTagMatch[0].length)
    if (afterReasoning.trim()) {
      reasoningParts.push(afterReasoning.trim())
    }
    nextContent = beforeReasoning
  }
  nextContent = nextContent
    .replace(/<\/?(reasoning|think)>/gi, '')
    .trim()
  return {
    content: nextContent,
    reasoning: reasoningParts.join('\n\n'),
  }
}
