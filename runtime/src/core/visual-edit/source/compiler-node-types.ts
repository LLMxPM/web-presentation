/**
 * 文件用途：声明可视化编辑分析器使用的 Vue 模板编译器节点最小结构，隔离编译器内部字段依赖。
 */

export const TEMPLATE_NODE_ROOT = 0
export const TEMPLATE_NODE_ELEMENT = 1
export const TEMPLATE_NODE_TEXT = 2
export const TEMPLATE_NODE_SIMPLE_EXPRESSION = 4
export const TEMPLATE_NODE_INTERPOLATION = 5
export const TEMPLATE_NODE_ATTRIBUTE = 6
export const TEMPLATE_NODE_DIRECTIVE = 7
export const TEMPLATE_TAG_COMPONENT = 1

export interface CompilerPosition {
  offset: number
}

export interface CompilerLocation {
  start: CompilerPosition
  end: CompilerPosition
  source: string
}

export interface CompilerSimpleExpression {
  type: typeof TEMPLATE_NODE_SIMPLE_EXPRESSION
  content: string
  isStatic: boolean
  loc: CompilerLocation
}

export interface CompilerAttributeNode {
  type: typeof TEMPLATE_NODE_ATTRIBUTE
  name: string
  value?: {
    content: string
    loc: CompilerLocation
  }
  loc: CompilerLocation
}

export interface CompilerDirectiveNode {
  type: typeof TEMPLATE_NODE_DIRECTIVE
  name: string
  arg?: CompilerSimpleExpression
  exp?: CompilerSimpleExpression
  loc: CompilerLocation
  forParseResult?: {
    source?: CompilerSimpleExpression
    value?: CompilerSimpleExpression
    key?: CompilerSimpleExpression
  }
}

export type CompilerPropNode = CompilerAttributeNode | CompilerDirectiveNode

export interface CompilerTextNode {
  type: typeof TEMPLATE_NODE_TEXT
  content: string
  loc: CompilerLocation
}

export interface CompilerInterpolationNode {
  type: typeof TEMPLATE_NODE_INTERPOLATION
  content: CompilerSimpleExpression
  loc: CompilerLocation
}

export interface CompilerElementNode {
  type: typeof TEMPLATE_NODE_ELEMENT
  tag: string
  tagType: number
  props: CompilerPropNode[]
  children: CompilerTemplateChild[]
  loc: CompilerLocation
}

export type CompilerTemplateChild = CompilerElementNode | CompilerTextNode | CompilerInterpolationNode | {
  type: number
  loc?: CompilerLocation
}

export interface CompilerRootNode {
  type: typeof TEMPLATE_NODE_ROOT
  children: CompilerTemplateChild[]
}
