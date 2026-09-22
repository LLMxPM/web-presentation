/**
 * 文件用途：为可视化编辑结果生成带少量上下文的统一源码差异。
 */

const DIFF_CONTEXT_LINES = 3

/**
 * 生成单个连续差异块；可视化编辑只需提供审计摘要，不承担完整合并职责。
 */
export function buildVisualEditCanonicalDiff(currentSource: string, nextSource: string): string {
  if (currentSource === nextSource) {
    return ''
  }
  const currentLines = currentSource.split('\n')
  const nextLines = nextSource.split('\n')
  let commonPrefix = 0
  while (
    commonPrefix < currentLines.length
    && commonPrefix < nextLines.length
    && currentLines[commonPrefix] === nextLines[commonPrefix]
  ) {
    commonPrefix += 1
  }

  let commonSuffix = 0
  while (
    commonSuffix < currentLines.length - commonPrefix
    && commonSuffix < nextLines.length - commonPrefix
    && currentLines[currentLines.length - commonSuffix - 1] === nextLines[nextLines.length - commonSuffix - 1]
  ) {
    commonSuffix += 1
  }

  const contextStart = Math.max(0, commonPrefix - DIFF_CONTEXT_LINES)
  const currentEnd = Math.min(currentLines.length, currentLines.length - commonSuffix + DIFF_CONTEXT_LINES)
  const nextEnd = Math.min(nextLines.length, nextLines.length - commonSuffix + DIFF_CONTEXT_LINES)
  const before = currentLines.slice(contextStart, commonPrefix).map(line => ` ${line}`)
  const removed = currentLines.slice(commonPrefix, currentLines.length - commonSuffix).map(line => `-${line}`)
  const added = nextLines.slice(commonPrefix, nextLines.length - commonSuffix).map(line => `+${line}`)
  const after = nextLines.slice(nextLines.length - commonSuffix, nextEnd).map(line => ` ${line}`)
  return [
    '--- canonical',
    '+++ proposed',
    `@@ -${contextStart + 1},${currentEnd - contextStart} +${contextStart + 1},${nextEnd - contextStart} @@`,
    ...before,
    ...removed,
    ...added,
    ...after,
    '',
  ].join('\n')
}
