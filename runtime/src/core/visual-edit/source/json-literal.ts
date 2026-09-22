/**
 * 文件用途：解析、限制并确定性序列化可视化编辑允许的纯 JSON TypeScript 字面量。
 */

import ts from 'typescript'

import type { VisualEditJsonValue } from '../protocol'

export const PAGE_VISUAL_EDIT_MAX_JSON_BYTES = 200_000
export const PAGE_VISUAL_EDIT_MAX_JSON_DEPTH = 32
export const PAGE_VISUAL_EDIT_MAX_JSON_NODES = 10_000

interface JsonWalkState {
  nodes: number
}

/** 将 TypeScript 表达式解析为纯 JSON；包含动态语义或重复键时返回 null。 */
export function parseJsonExpression(
  expression: ts.Expression
): VisualEditJsonValue | undefined {
  const state: JsonWalkState = { nodes: 0 }
  const value = parseJsonNode(unwrapExpression(expression), 1, state)
  if (value === undefined) return undefined
  try {
    validateVisualEditJsonValue(value)
  } catch {
    return undefined
  }
  return value
}

/** 解析 Vue 指令中的表达式文本，仅接受完整的纯 JSON 表达式。 */
export function parseJsonExpressionText(
  source: string
): VisualEditJsonValue | undefined {
  const file = ts.createSourceFile(
    'visual-edit-json-expression.ts',
    `const __value = (${source})`,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS
  )
  const statement = file.statements[0]
  const initializer =
    statement && ts.isVariableStatement(statement)
      ? statement.declarationList.declarations[0]?.initializer
      : undefined
  return initializer ? parseJsonExpression(initializer) : undefined
}

/** 校验来自线协议的 JSON 值规模、深度、节点数和有限数值约束。 */
export function validateVisualEditJsonValue(
  value: unknown
): asserts value is VisualEditJsonValue {
  const state: JsonWalkState = { nodes: 0 }
  validateJsonNode(value, 1, state)
  if (
    Buffer.byteLength(JSON.stringify(value), 'utf8') >
    PAGE_VISUAL_EDIT_MAX_JSON_BYTES
  ) {
    throw new Error('JSON 值超过 200000 字节上限。')
  }
}

/** 使用 TypeScript Printer 输出可安全嵌入脚本和双引号 Vue 属性的单引号 JS 字面量。 */
export function serializeVisualEditJsonValue(
  value: VisualEditJsonValue
): string {
  validateVisualEditJsonValue(value)
  const printer = ts.createPrinter({ newLine: ts.NewLineKind.LineFeed })
  const sourceFile = ts.createSourceFile(
    'value.ts',
    '',
    ts.ScriptTarget.Latest,
    false,
    ts.ScriptKind.TS
  )
  return printer
    .printNode(ts.EmitHint.Expression, buildExpression(value), sourceFile)
    .replace(/\\u([0-9A-Fa-f]{4})/g, (match, hex: string) => {
      const code = Number.parseInt(hex, 16)
      return code >= 0x80 && code !== 0x2028 && code !== 0x2029
        ? String.fromCharCode(code)
        : match
    })
}

/** 递归读取仅由 JSON 节点组成的 TypeScript AST。 */
function parseJsonNode(
  expression: ts.Expression,
  depth: number,
  state: JsonWalkState
): VisualEditJsonValue | undefined {
  state.nodes += 1
  if (
    depth > PAGE_VISUAL_EDIT_MAX_JSON_DEPTH ||
    state.nodes > PAGE_VISUAL_EDIT_MAX_JSON_NODES
  )
    return undefined
  if (
    ts.isStringLiteral(expression) ||
    ts.isNoSubstitutionTemplateLiteral(expression)
  )
    return expression.text
  if (ts.isNumericLiteral(expression)) {
    const value = Number(expression.text)
    return Number.isFinite(value) ? value : undefined
  }
  if (expression.kind === ts.SyntaxKind.TrueKeyword) return true
  if (expression.kind === ts.SyntaxKind.FalseKeyword) return false
  if (expression.kind === ts.SyntaxKind.NullKeyword) return null
  if (
    ts.isPrefixUnaryExpression(expression) &&
    expression.operator === ts.SyntaxKind.MinusToken &&
    ts.isNumericLiteral(expression.operand)
  ) {
    const value = -Number(expression.operand.text)
    return Number.isFinite(value) ? value : undefined
  }
  if (ts.isArrayLiteralExpression(expression)) {
    const result: VisualEditJsonValue[] = []
    for (const element of expression.elements) {
      if (ts.isSpreadElement(element) || ts.isOmittedExpression(element))
        return undefined
      const value = parseJsonNode(unwrapExpression(element), depth + 1, state)
      if (value === undefined) return undefined
      result.push(value)
    }
    return result
  }
  if (ts.isObjectLiteralExpression(expression)) {
    const result: Record<string, VisualEditJsonValue> = Object.create(
      null
    ) as Record<string, VisualEditJsonValue>
    const keys = new Set<string>()
    for (const property of expression.properties) {
      if (!ts.isPropertyAssignment(property)) return undefined
      const key = resolvePropertyName(property.name)
      if (key === null || keys.has(key)) return undefined
      const value = parseJsonNode(
        unwrapExpression(property.initializer),
        depth + 1,
        state
      )
      if (value === undefined) return undefined
      keys.add(key)
      result[key] = value
    }
    return result
  }
  return undefined
}

/** 对未知线协议值执行递归约束校验。 */
function validateJsonNode(
  value: unknown,
  depth: number,
  state: JsonWalkState
): void {
  state.nodes += 1
  if (depth > PAGE_VISUAL_EDIT_MAX_JSON_DEPTH)
    throw new Error('JSON 嵌套深度超过 32。')
  if (state.nodes > PAGE_VISUAL_EDIT_MAX_JSON_NODES)
    throw new Error('JSON 节点数量超过 10000。')
  if (value === null || typeof value === 'string' || typeof value === 'boolean')
    return
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new Error('JSON 数字必须是有限值。')
    return
  }
  if (Array.isArray(value)) {
    value.forEach((item) => validateJsonNode(item, depth + 1, state))
    return
  }
  if (value && typeof value === 'object') {
    Object.values(value).forEach((item) =>
      validateJsonNode(item, depth + 1, state)
    )
    return
  }
  throw new Error('值不是合法 JSON。')
}

/** 将 JSON 值转换为 TypeScript 工厂表达式。 */
function buildExpression(value: VisualEditJsonValue): ts.Expression {
  if (value === null) return ts.factory.createNull()
  if (typeof value === 'string')
    return ts.factory.createStringLiteral(value, true)
  if (typeof value === 'number') {
    const literal = ts.factory.createNumericLiteral(Math.abs(value))
    return value < 0
      ? ts.factory.createPrefixUnaryExpression(
          ts.SyntaxKind.MinusToken,
          literal
        )
      : literal
  }
  if (typeof value === 'boolean')
    return value ? ts.factory.createTrue() : ts.factory.createFalse()
  if (Array.isArray(value)) {
    return ts.factory.createArrayLiteralExpression(
      value.map(buildExpression),
      true
    )
  }
  return ts.factory.createObjectLiteralExpression(
    Object.entries(value).map(([key, item]) =>
      ts.factory.createPropertyAssignment(
        ts.factory.createStringLiteral(key, true),
        buildExpression(item)
      )
    ),
    true
  )
}

/** 解析静态对象键，计算属性和动态名称不属于 JSON。 */
function resolvePropertyName(name: ts.PropertyName): string | null {
  if (
    ts.isIdentifier(name) ||
    ts.isStringLiteral(name) ||
    ts.isNumericLiteral(name)
  )
    return name.text
  return null
}

/** 剥离不改变运行值的 TypeScript 外围包装。 */
export function unwrapExpression(expression: ts.Expression): ts.Expression {
  let current = expression
  while (
    ts.isParenthesizedExpression(current) ||
    ts.isAsExpression(current) ||
    ts.isTypeAssertionExpression(current) ||
    ts.isSatisfiesExpression(current) ||
    ts.isNonNullExpression(current)
  )
    current = current.expression
  return current
}
