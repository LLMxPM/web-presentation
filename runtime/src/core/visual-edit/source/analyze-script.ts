/**
 * 文件用途：使用 TypeScript AST 提取 `<script setup>` 中可静态定位的数组字面量及其对象成员。
 */

import ts from 'typescript'

import type {
  VisualEditJsonSource,
  VisualEditLiteralValue,
  VisualEditReadonlyReason,
  VisualEditScriptCollectionKind,
  VisualEditSourceRange,
  VisualEditValueType,
} from '../protocol'
import { createStableId } from './template-expression'
import {
  parseJsonExpression,
  unwrapExpression as unwrapJsonExpression,
} from './json-literal'

export interface ScriptLiteralMember {
  value?: VisualEditLiteralValue
  valueType: VisualEditValueType
  sourceRange?: VisualEditSourceRange
  editable: boolean
  readonlyReason?: VisualEditReadonlyReason
}

export interface ScriptCollectionItem {
  index: number
  sourceRange: VisualEditSourceRange
  members: Map<string, ScriptLiteralMember>
}

export interface ScriptCollectionDefinition {
  name: string
  kind?: VisualEditScriptCollectionKind
  sourceRange: VisualEditSourceRange
  arrayRange?: VisualEditSourceRange
  items: ScriptCollectionItem[]
  editable: boolean
  readonlyReason?: VisualEditReadonlyReason
}

/** 分析结果同时提供字段级对象数组和整块 JSON 数据源。 */
export interface ScriptAnalysisResult {
  collections: Map<string, ScriptCollectionDefinition>
  jsonSources: Map<string, VisualEditJsonSource>
}

/** 一次解析 script setup，同时生成现有数组成员模型和去重 JSON source。 */
export function analyzeScript(
  content: string,
  sourceOffset: number,
  lang = 'ts',
  modulePath = ''
): ScriptAnalysisResult {
  return {
    collections: analyzeScriptCollections(content, sourceOffset, lang),
    jsonSources: analyzeScriptJsonSources(
      content,
      sourceOffset,
      lang,
      modulePath
    ),
  }
}

/**
 * 分析脚本顶层 const 声明。只把数组字面量以及 ref/reactive 包裹的数组字面量视为可编辑数据源。
 * @param content script setup 源码，不包含 SFC 标签
 * @param sourceOffset content 在完整 SFC 中的起始偏移
 * @param lang script setup 的语言
 * @returns 以变量名索引的数据源定义
 */
export function analyzeScriptCollections(
  content: string,
  sourceOffset: number,
  lang = 'ts'
): Map<string, ScriptCollectionDefinition> {
  const scriptKind = resolveScriptKind(lang)
  const sourceFile = ts.createSourceFile(
    'visual-edit-script.ts',
    content,
    ts.ScriptTarget.Latest,
    true,
    scriptKind
  )
  const collections = new Map<string, ScriptCollectionDefinition>()

  for (const statement of sourceFile.statements) {
    if (
      !ts.isVariableStatement(statement) ||
      !(statement.declarationList.flags & ts.NodeFlags.Const)
    ) {
      continue
    }
    for (const declaration of statement.declarationList.declarations) {
      if (!ts.isIdentifier(declaration.name) || !declaration.initializer) {
        continue
      }
      collections.set(
        declaration.name.text,
        analyzeCollectionDeclaration(
          declaration.name.text,
          declaration.initializer,
          sourceFile,
          sourceOffset
        )
      )
    }
  }

  return collections
}

/** 提取顶层 const/ref/reactive 中可完整往返的纯 JSON 数组或对象。 */
export function analyzeScriptJsonSources(
  content: string,
  sourceOffset: number,
  lang = 'ts',
  modulePath = ''
): Map<string, VisualEditJsonSource> {
  const sourceFile = ts.createSourceFile(
    'visual-edit-json.ts',
    content,
    ts.ScriptTarget.Latest,
    true,
    resolveScriptKind(lang)
  )
  const sources = new Map<string, VisualEditJsonSource>()
  for (const statement of sourceFile.statements) {
    if (
      !ts.isVariableStatement(statement) ||
      !(statement.declarationList.flags & ts.NodeFlags.Const)
    )
      continue
    for (const declaration of statement.declarationList.declarations) {
      if (!ts.isIdentifier(declaration.name) || !declaration.initializer)
        continue
      const resolved = resolveJsonInitializer(declaration.initializer)
      if (!resolved) continue
      const value = parseJsonExpression(resolved.expression)
      if (
        value === undefined ||
        value === null ||
        (!Array.isArray(value) && typeof value !== 'object')
      )
        continue
      sources.set(declaration.name.text, {
        sourceId: createStableId(
          'source',
          modulePath,
          'script',
          declaration.name.text
        ),
        kind: resolved.kind,
        name: declaration.name.text,
        value,
        sourceRange: toSourceRange(
          resolved.expression,
          sourceFile,
          sourceOffset
        ),
        editable: true,
      })
    }
  }
  return sources
}

/** 识别整块 JSON 数据源的 const/ref/reactive 外壳，并返回真正替换的字面量。 */
function resolveJsonInitializer(raw: ts.Expression): {
  kind: VisualEditJsonSource['kind']
  expression: ts.Expression
} | null {
  const initializer = unwrapJsonExpression(raw)
  if (
    ts.isArrayLiteralExpression(initializer) ||
    ts.isObjectLiteralExpression(initializer)
  ) {
    return { kind: 'const', expression: initializer }
  }
  if (
    !ts.isCallExpression(initializer) ||
    !ts.isIdentifier(initializer.expression) ||
    initializer.arguments.length !== 1
  ) {
    return null
  }
  if (
    initializer.expression.text !== 'ref' &&
    initializer.expression.text !== 'reactive'
  )
    return null
  const expression = unwrapJsonExpression(
    initializer.arguments[0] as ts.Expression
  )
  if (
    !ts.isArrayLiteralExpression(expression) &&
    !ts.isObjectLiteralExpression(expression)
  )
    return null
  return { kind: initializer.expression.text, expression }
}

/**
 * 解析单个 const 初始化表达式，并保留动态定义供模板侧输出明确只读原因。
 */
function analyzeCollectionDeclaration(
  name: string,
  rawInitializer: ts.Expression,
  sourceFile: ts.SourceFile,
  sourceOffset: number
): ScriptCollectionDefinition {
  const declarationRange = toSourceRange(
    rawInitializer,
    sourceFile,
    sourceOffset
  )
  const resolved = resolveArrayInitializer(rawInitializer)
  if (!resolved) {
    return {
      name,
      sourceRange: declarationRange,
      items: [],
      editable: false,
      readonlyReason: 'DYNAMIC_SCRIPT_SOURCE',
    }
  }

  const items: ScriptCollectionItem[] = []
  let containsSpread = false
  resolved.array.elements.forEach((element, index) => {
    const unwrapped = unwrapExpression(element as ts.Expression)
    if (
      ts.isSpreadElement(element) ||
      !ts.isObjectLiteralExpression(unwrapped)
    ) {
      containsSpread = true
      return
    }
    const item = analyzeObjectItem(unwrapped, index, sourceFile, sourceOffset)
    items.push(item)
    containsSpread ||= unwrapped.properties.some(ts.isSpreadAssignment)
  })

  return {
    name,
    kind: resolved.kind,
    sourceRange: declarationRange,
    arrayRange: toSourceRange(resolved.array, sourceFile, sourceOffset),
    items,
    editable: !containsSpread,
    readonlyReason: containsSpread ? 'DYNAMIC_SCRIPT_SOURCE' : undefined,
  }
}

/**
 * 识别受支持的数组初始化形式，并剥离 `as const` 等不改变运行值的包装。
 */
function resolveArrayInitializer(rawInitializer: ts.Expression): {
  kind: VisualEditScriptCollectionKind
  array: ts.ArrayLiteralExpression
} | null {
  const initializer = unwrapExpression(rawInitializer)
  if (ts.isArrayLiteralExpression(initializer)) {
    return { kind: 'const-array', array: initializer }
  }
  if (
    !ts.isCallExpression(initializer) ||
    !ts.isIdentifier(initializer.expression) ||
    initializer.arguments.length !== 1
  ) {
    return null
  }

  const wrapper = initializer.expression.text
  if (wrapper !== 'ref' && wrapper !== 'reactive') {
    return null
  }
  const argument = unwrapExpression(initializer.arguments[0] as ts.Expression)
  if (!ts.isArrayLiteralExpression(argument)) {
    return null
  }
  return {
    kind: wrapper === 'ref' ? 'ref-array' : 'reactive-array',
    array: argument,
  }
}

/**
 * 提取对象字面量中直接声明的属性；方法、访问器、简写和展开属性不建立可写位置。
 */
function analyzeObjectItem(
  objectNode: ts.ObjectLiteralExpression,
  index: number,
  sourceFile: ts.SourceFile,
  sourceOffset: number
): ScriptCollectionItem {
  const members = new Map<string, ScriptLiteralMember>()
  for (const property of objectNode.properties) {
    if (!ts.isPropertyAssignment(property)) {
      continue
    }
    const propertyName = resolvePropertyName(property.name)
    if (!propertyName) {
      continue
    }
    members.set(
      propertyName,
      analyzeLiteral(property.initializer, sourceFile, sourceOffset)
    )
  }
  return {
    index,
    sourceRange: toSourceRange(objectNode, sourceFile, sourceOffset),
    members,
  }
}

/**
 * 将 TypeScript 字面量转换为协议值；其它表达式保留源码范围但标记只读。
 */
function analyzeLiteral(
  rawExpression: ts.Expression,
  sourceFile: ts.SourceFile,
  sourceOffset: number
): ScriptLiteralMember {
  const expression = unwrapExpression(rawExpression)
  const sourceRange = toSourceRange(rawExpression, sourceFile, sourceOffset)
  if (
    ts.isStringLiteral(expression) ||
    ts.isNoSubstitutionTemplateLiteral(expression)
  ) {
    return {
      value: expression.text,
      valueType: 'string',
      sourceRange,
      editable: true,
    }
  }
  if (ts.isNumericLiteral(expression)) {
    return {
      value: Number(expression.text),
      valueType: 'number',
      sourceRange,
      editable: true,
    }
  }
  if (
    expression.kind === ts.SyntaxKind.TrueKeyword ||
    expression.kind === ts.SyntaxKind.FalseKeyword
  ) {
    return {
      value: expression.kind === ts.SyntaxKind.TrueKeyword,
      valueType: 'boolean',
      sourceRange,
      editable: true,
    }
  }
  if (expression.kind === ts.SyntaxKind.NullKeyword) {
    return { value: null, valueType: 'null', sourceRange, editable: true }
  }
  if (
    ts.isPrefixUnaryExpression(expression) &&
    expression.operator === ts.SyntaxKind.MinusToken &&
    ts.isNumericLiteral(expression.operand)
  ) {
    return {
      value: -Number(expression.operand.text),
      valueType: 'number',
      sourceRange,
      editable: true,
    }
  }
  return {
    valueType: 'unknown',
    sourceRange,
    editable: false,
    readonlyReason: 'MEMBER_VALUE_DYNAMIC',
  }
}

/**
 * 剥离不改变表达式运行值的 TypeScript 包装节点。
 */
function unwrapExpression(expression: ts.Expression): ts.Expression {
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
 * 解析对象字面量的静态属性名。
 */
function resolvePropertyName(name: ts.PropertyName): string | null {
  if (
    ts.isIdentifier(name) ||
    ts.isStringLiteral(name) ||
    ts.isNumericLiteral(name)
  ) {
    return name.text
  }
  return null
}

/**
 * 把脚本块内偏移转换成完整 SFC 偏移。
 */
function toSourceRange(
  node: ts.Node,
  sourceFile: ts.SourceFile,
  sourceOffset: number
): VisualEditSourceRange {
  return {
    start: sourceOffset + node.getStart(sourceFile),
    end: sourceOffset + node.getEnd(),
  }
}

/**
 * 根据 SFC lang 选择 TypeScript 解析模式；TS 解析器也可安全读取普通 JavaScript。
 */
function resolveScriptKind(lang: string): ts.ScriptKind {
  if (lang === 'tsx') {
    return ts.ScriptKind.TSX
  }
  if (lang === 'jsx') {
    return ts.ScriptKind.JSX
  }
  return lang === 'js' ? ts.ScriptKind.JS : ts.ScriptKind.TS
}
