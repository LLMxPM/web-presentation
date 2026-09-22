/**
 * 文件用途：按模板文本、HTML 属性或 JavaScript 字面量上下文安全编码可视化编辑值。
 */

import type { VisualEditBinding, VisualEditLiteralValue, VisualEditValueType } from '../protocol'
import { VisualEditApplyError } from './errors'

export type VisualEditReplacementContext = 'template-text' | 'template-attribute' | 'javascript-literal'

/**
 * 校验目标类型并生成可直接替换源码范围的安全文本。
 */
export function encodeVisualEditValue(
  binding: VisualEditBinding,
  currentSourceToken: string,
  value: VisualEditLiteralValue,
  valueType: VisualEditValueType,
  context: VisualEditReplacementContext,
): string {
  if (!matchesValueType(value, valueType)) {
    throw new VisualEditApplyError(
      422,
      'PAGE_VISUAL_EDIT_VALUE_TYPE_MISMATCH',
      `新值类型与 ${binding.bindingId} 的 ${valueType} 目标不匹配。`,
    )
  }
  if (context === 'template-text') {
    return encodeHtmlText(value as string)
  }
  if (context === 'template-attribute') {
    return encodeHtmlAttribute(value as string, currentSourceToken)
  }
  return encodeJavaScriptLiteral(value, currentSourceToken)
}

/**
 * 根据 binding 来源和模板形态判定替换编码上下文。
 */
export function resolveReplacementContext(binding: VisualEditBinding): VisualEditReplacementContext {
  if (binding.source?.kind === 'script-array-item' || binding.expression) {
    return 'javascript-literal'
  }
  return binding.kind === 'text' ? 'template-text' : 'template-attribute'
}

/**
 * 按协议 valueType 严格判断 JSON 基本值，number 仅接受有限数值。
 */
export function matchesValueType(value: VisualEditLiteralValue, valueType: VisualEditValueType): boolean {
  if (valueType === 'null') {
    return value === null
  }
  if (valueType === 'number') {
    return typeof value === 'number' && Number.isFinite(value)
  }
  return valueType !== 'unknown' && typeof value === valueType
}

/**
 * 转义模板可见文本，并编码花括号以避免用户文本被重新解释成插值表达式。
 */
function encodeHtmlText(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/{/g, '&#123;')
    .replace(/}/g, '&#125;')
}

/**
 * 保留原属性引号风格，并对实体、引号、尖括号和换行做安全编码。
 */
function encodeHtmlAttribute(value: string, currentSourceToken: string): string {
  const quote = currentSourceToken.startsWith("'") && currentSourceToken.endsWith("'") ? "'" : '"'
  let escaped = value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\r/g, '&#13;')
    .replace(/\n/g, '&#10;')
  escaped = quote === '"' ? escaped.replace(/"/g, '&quot;') : escaped.replace(/'/g, '&#39;')
  return `${quote}${escaped}${quote}`
}

/**
 * 生成 JavaScript 基本字面量；字符串尽量沿用原单引号、双引号或模板引号。
 */
function encodeJavaScriptLiteral(value: VisualEditLiteralValue, currentSourceToken: string): string {
  if (typeof value !== 'string') {
    if (typeof value === 'number' && Object.is(value, -0)) {
      return '-0'
    }
    return String(value)
  }
  if (currentSourceToken.startsWith("'") && currentSourceToken.endsWith("'")) {
    return `'${escapeJavaScriptString(value, "'")}'`
  }
  if (currentSourceToken.startsWith('`') && currentSourceToken.endsWith('`')) {
    const escaped = escapeJavaScriptString(value, '`').replace(/\$\{/g, '\\${')
    return `\`${escaped}\``
  }
  return `"${escapeJavaScriptString(value, '"')}"`
}

/**
 * 转义 JavaScript 字符串中的控制字符、反斜杠与当前定界符。
 */
function escapeJavaScriptString(value: string, quote: "'" | '"' | '`'): string {
  return value
    .replace(/\\/g, '\\\\')
    .replace(/\r/g, '\\r')
    .replace(/\n/g, '\\n')
    .replace(/\u2028/g, '\\u2028')
    .replace(/\u2029/g, '\\u2029')
    .replace(new RegExp(escapeRegExp(quote), 'g'), `\\${quote}`)
}

/**
 * 转义用于构造单字符正则的定界符。
 */
function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}
