/**
 * 文件用途：使用 TypeScript AST 对 Vue 模板表达式做受约束分类，并提供稳定 ID 与源码范围辅助能力。
 */

import ts from 'typescript'

import type {
  VisualEditLiteralValue,
  VisualEditSourceRange,
  VisualEditValueType,
} from '../protocol'
import type { CompilerLocation } from './compiler-node-types'

export interface ParsedTemplateExpression {
  literal?: VisualEditLiteralValue
  valueType: VisualEditValueType
  member?: {
    object: string
    property: string
  }
}

/**
 * 识别基本字面量和直接属性访问，调用、拼接、条件及计算属性均保持为未知动态表达式。
 */
export function parseTemplateExpression(
  expressionText: string
): ParsedTemplateExpression {
  const sourceFile = ts.createSourceFile(
    'visual-edit-expression.ts',
    `const __visualEditExpression = (${expressionText})`,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS
  )
  const statement = sourceFile.statements[0]
  if (!statement || !ts.isVariableStatement(statement)) {
    return { valueType: 'unknown' }
  }
  const initializer = statement.declarationList.declarations[0]?.initializer
  if (!initializer) {
    return { valueType: 'unknown' }
  }
  const value = unwrapTemplateExpression(initializer)
  if (ts.isStringLiteral(value) || ts.isNoSubstitutionTemplateLiteral(value)) {
    return { literal: value.text, valueType: 'string' }
  }
  if (ts.isNumericLiteral(value)) {
    return { literal: Number(value.text), valueType: 'number' }
  }
  if (
    value.kind === ts.SyntaxKind.TrueKeyword ||
    value.kind === ts.SyntaxKind.FalseKeyword
  ) {
    return {
      literal: value.kind === ts.SyntaxKind.TrueKeyword,
      valueType: 'boolean',
    }
  }
  if (value.kind === ts.SyntaxKind.NullKeyword) {
    return { literal: null, valueType: 'null' }
  }
  if (
    ts.isPropertyAccessExpression(value) &&
    ts.isIdentifier(value.expression)
  ) {
    return {
      valueType: 'unknown',
      member: { object: value.expression.text, property: value.name.text },
    }
  }
  return { valueType: 'unknown' }
}

/**
 * 解析 `item.id` 形式的直接成员表达式。
 */
export function parseDirectMemberExpression(
  expression: string
): { object: string; property: string } | undefined {
  return parseTemplateExpression(expression).member
}

/**
 * 剥离模板表达式外围括号和 TypeScript 类型断言。
 */
function unwrapTemplateExpression(expression: ts.Expression): ts.Expression {
  let current = expression
  while (
    ts.isParenthesizedExpression(current) ||
    ts.isAsExpression(current) ||
    ts.isTypeAssertionExpression(current) ||
    ts.isSatisfiesExpression(current) ||
    ts.isNonNullExpression(current)
  ) {
    current = current.expression
  }
  return current
}

/**
 * 判断字符串是否为无路径、调用或运算的简单标识符。
 */
export function isIdentifier(value: string): boolean {
  return /^[$A-Z_a-z][$\w]*$/.test(value)
}

/**
 * 使用确定性 FNV-1a 生成短 ID；同一结构槽位始终得到相同结果。
 */
export function createStableId(
  prefix: 'node' | 'binding' | 'source',
  ...parts: Array<string | number>
): string {
  const input = parts.join('\u001f')
  let hash = 0x811c9dc5
  for (let index = 0; index < input.length; index += 1) {
    hash ^= input.charCodeAt(index)
    hash = Math.imul(hash, 0x01000193)
  }
  return `${prefix}_${(hash >>> 0).toString(36)}`
}

/**
 * 规范化模块路径，避免 Windows 分隔符影响稳定 ID。
 */
export function normalizeModulePath(modulePath: string): string {
  return String(modulePath || '')
    .trim()
    .replace(/\\/g, '/')
    .replace(/^\/+/, '')
}

/**
 * 将 Vue 编译器位置转换为协议范围；其偏移已经相对完整 SFC。
 */
export function toSourceRange(
  location: CompilerLocation
): VisualEditSourceRange {
  return { start: location.start.offset, end: location.end.offset }
}
