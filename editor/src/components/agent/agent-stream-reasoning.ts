/**
 * 文件功能：解析模型流式正文中夹带的 think/reasoning 标签，支持标签跨 delta 分片。
 */

export interface InlineReasoningStreamState {
  mode: 'content' | 'reasoning'
  activeTag: 'think' | 'reasoning' | null
  pendingTag: string
}

export interface InlineReasoningSplitResult {
  content: string
  reasoning: string
  segments: Array<{
    kind: 'content' | 'reasoning'
    text: string
  }>
}

/**
 * 创建一个新的 inline reasoning 解析状态。
 */
export function createInlineReasoningStreamState(): InlineReasoningStreamState {
  return {
    mode: 'content',
    activeTag: null,
    pendingTag: '',
  }
}

/**
 * 重置解析状态；用于新模型请求、暂停和终态，避免未闭合标签污染后续输出。
 */
export function resetInlineReasoningStreamState(state: InlineReasoningStreamState): void {
  state.mode = 'content'
  state.activeTag = null
  state.pendingTag = ''
}

/**
 * 将单个正文 delta 拆为展示正文和 reasoning 文本，识别跨分片标签。
 */
export function splitInlineReasoningDelta(
  content: string,
  state: InlineReasoningStreamState,
): InlineReasoningSplitResult {
  const result: InlineReasoningSplitResult = { content: '', reasoning: '', segments: [] }
  let input = `${state.pendingTag}${content}`
  state.pendingTag = ''

  while (input) {
    const tagStart = input.indexOf('<')
    if (tagStart < 0) {
      appendByMode(result, state, input)
      break
    }

    if (tagStart > 0) {
      appendByMode(result, state, input.slice(0, tagStart))
      input = input.slice(tagStart)
      continue
    }

    const tagEnd = input.indexOf('>')
    if (tagEnd < 0) {
      if (isReasoningTagPrefix(input)) {
        state.pendingTag = input
      } else {
        appendByMode(result, state, input)
      }
      break
    }

    const rawTag = input.slice(0, tagEnd + 1)
    const parsed = parseReasoningTag(rawTag)
    if (parsed) {
      if (parsed.kind === 'open') {
        state.mode = 'reasoning'
        state.activeTag = parsed.tag
      } else {
        state.mode = 'content'
        state.activeTag = null
      }
    } else {
      appendByMode(result, state, rawTag)
    }
    input = input.slice(tagEnd + 1)
  }

  return result
}

function appendByMode(
  result: InlineReasoningSplitResult,
  state: InlineReasoningStreamState,
  text: string,
): void {
  if (!text) {
    return
  }
  if (state.mode === 'reasoning') {
    result.reasoning += text
    appendSegment(result, 'reasoning', text)
    return
  }
  result.content += text
  appendSegment(result, 'content', text)
}

function appendSegment(
  result: InlineReasoningSplitResult,
  kind: 'content' | 'reasoning',
  text: string,
): void {
  const latest = result.segments.at(-1)
  if (latest?.kind === kind) {
    latest.text += text
    return
  }
  result.segments.push({ kind, text })
}

function parseReasoningTag(rawTag: string): { kind: 'open' | 'close', tag: 'think' | 'reasoning' } | null {
  const normalized = rawTag.trim().toLowerCase()
  const openMatch = normalized.match(/^<\s*(think|reasoning)\s*>$/)
  if (openMatch) {
    return { kind: 'open', tag: openMatch[1] as 'think' | 'reasoning' }
  }
  const closeMatch = normalized.match(/^<\s*\/\s*(think|reasoning)\s*>$/)
  if (closeMatch) {
    return { kind: 'close', tag: closeMatch[1] as 'think' | 'reasoning' }
  }
  return null
}

function isReasoningTagPrefix(value: string): boolean {
  const compact = value.toLowerCase().replace(/\s+/g, '')
  return ['<think>', '</think>', '<reasoning>', '</reasoning>'].some(tag => tag.startsWith(compact))
}
