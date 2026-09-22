/**
 * 文件用途：定义页面可视化编辑的版本化协议，统一源码分析、Runtime 选区与 Backend 编辑操作使用的定位元数据。
 */

export const PAGE_VISUAL_EDIT_PROTOCOL_VERSION = 1 as const
export const PAGE_VISUAL_EDIT_SELECTION_EVENT =
  'page-visual-edit:selection' as const
export const PAGE_VISUAL_EDIT_SELECT_NODE_EVENT =
  'page-visual-edit:select-node' as const

export type PageVisualEditProtocolVersion =
  typeof PAGE_VISUAL_EDIT_PROTOCOL_VERSION
export type VisualEditLiteralValue = string | number | boolean | null
export type VisualEditJsonValue =
  | VisualEditLiteralValue
  | VisualEditJsonValue[]
  | { [key: string]: VisualEditJsonValue }

export interface VisualEditSourceRange {
  /** UTF-16 源码起始偏移，包含该位置。 */
  start: number
  /** UTF-16 源码结束偏移，不包含该位置。 */
  end: number
}

export type VisualEditReadonlyReason =
  | 'SFC_PARSE_ERROR'
  | 'TEMPLATE_UNSUPPORTED'
  | 'DYNAMIC_EXPRESSION'
  | 'DYNAMIC_SCRIPT_SOURCE'
  | 'SCRIPT_SOURCE_NOT_FOUND'
  | 'LOOP_SOURCE_UNSUPPORTED'
  | 'NESTED_LOOP_UNSUPPORTED'
  | 'LOOP_MEMBER_UNSUPPORTED'
  | 'MEMBER_NOT_FOUND'
  | 'MEMBER_VALUE_DYNAMIC'
  | 'ATTRIBUTE_VALUE_MISSING'
  | 'RICH_TEXT_DYNAMIC_CONTENT'
  | 'RICH_TEXT_UNSUPPORTED_STRUCTURE'
  | 'RICH_TEXT_SOURCE_RANGE_UNRESOLVED'
  | 'STRUCTURE_ROOT_UNSUPPORTED'
  | 'STRUCTURE_CONTROL_FLOW_UNSUPPORTED'
  | 'STRUCTURE_LOOP_INSTANCE_REQUIRED'

export type VisualEditBindingKind =
  | 'text'
  | 'rich_text'
  | 'class'
  | 'prop'
  | 'json'
export type VisualEditValueType =
  | 'string'
  | 'number'
  | 'boolean'
  | 'null'
  | 'json'
  | 'unknown'
export type VisualEditNodeKind = 'root' | 'element' | 'component'
export type VisualEditScriptCollectionKind =
  | 'const-array'
  | 'ref-array'
  | 'reactive-array'

export interface VisualEditTailwindCatalogOption {
  className: string
  label: string
}

export interface VisualEditTailwindCatalogGroup {
  key: string
  label: string
  options: VisualEditTailwindCatalogOption[]
}

export interface VisualEditTailwindCatalog {
  version: 1
  groups: VisualEditTailwindCatalogGroup[]
}

/**
 * 描述一个循环实例。Runtime 后续通过 key 或 index 把实际 DOM 实例映射回源码数组项。
 */
interface VisualEditInstancePathSegmentBase {
  loopNodeId: string
}

export type VisualEditInstancePathSegment = VisualEditInstancePathSegmentBase &
  ({ key: string | number; index?: number } | { key?: never; index: number })

/**
 * 描述脚本数组中某个成员的静态写入位置。
 */
export interface VisualEditScriptMemberLocation {
  index: number
  key?: string | number
  value?: VisualEditLiteralValue
  sourceRange?: VisualEditSourceRange
  editable: boolean
  readonlyReason?: VisualEditReadonlyReason
}

/**
 * 描述模板 `item.member` 与 `<script setup>` 数组字面量之间的静态关系。
 */
export interface VisualEditScriptArrayBindingSource {
  kind: 'script-array-item'
  collectionName: string
  collectionKind: VisualEditScriptCollectionKind
  itemAlias: string
  member: string
  keyMember?: string
  locations: VisualEditScriptMemberLocation[]
}

/**
 * 模板本地字面量的定位信息，例如静态文本或静态属性。
 */
export interface VisualEditTemplateBindingSource {
  kind: 'template-literal'
}

/** 模板元素内部受限富文本片段的定位信息。 */
export interface VisualEditTemplateRichTextBindingSource {
  kind: 'template-rich-text'
}

/** 绑定引用 Manifest 中去重的整块 JSON 源。 */
export interface VisualEditJsonBindingSource {
  kind: 'json-source'
  sourceId: string
}

export type VisualEditBindingSource =
  | VisualEditScriptArrayBindingSource
  | VisualEditTemplateBindingSource
  | VisualEditTemplateRichTextBindingSource
  | VisualEditJsonBindingSource

/**
 * 模板中一个可展示在属性面板的值绑定。
 */
export interface VisualEditBinding {
  bindingId: string
  nodeId: string
  kind: VisualEditBindingKind
  /** prop/class 名称；文本绑定不设置。 */
  name?: string
  valueType: VisualEditValueType
  value?: VisualEditJsonValue
  expression?: string
  sourceRange: VisualEditSourceRange
  editable: boolean
  readonlyReason?: VisualEditReadonlyReason
  source?: VisualEditBindingSource
}

/**
 * 单层 v-for 的静态语义；嵌套循环首版仅展示并标记为只读。
 */
export interface VisualEditLoopContext {
  loopNodeId: string
  sourceExpression: string
  sourceBinding?: string
  itemAlias: string
  indexAlias?: string
  keyExpression?: string
  keyMember?: string
  editable: boolean
  readonlyReason?: VisualEditReadonlyReason
}

/** 描述循环数组中一个可由稳定 key 定位的数据项。 */
export interface VisualEditLoopItemLocation {
  index: number
  key: string | number
}

/** 节点模板级复制、删除能力。 */
export interface VisualEditTemplateActions {
  canDuplicate: boolean
  canDelete: boolean
  readonlyReason?: VisualEditReadonlyReason
}

/** 节点所在循环的数据项级复制、删除能力。 */
export interface VisualEditLoopItemActions {
  canDuplicate: boolean
  canDelete: boolean
  loopNodeId: string
  collectionName: string
  keyMember: string
  instances: VisualEditLoopItemLocation[]
  readonlyReason?: VisualEditReadonlyReason
}

/**
 * 与最终 DOM 不同，该树保留 Vue 模板中的容器与组件语义。
 */
export interface VisualEditTemplateNode {
  nodeId: string
  kind: VisualEditNodeKind
  tag: string
  sourceRange: VisualEditSourceRange
  loopContext?: VisualEditLoopContext
  templateActions: VisualEditTemplateActions
  loopItemActions?: VisualEditLoopItemActions
  bindings: VisualEditBinding[]
  children: VisualEditTemplateNode[]
}

export interface VisualEditDiagnostic {
  severity: 'warning' | 'error'
  code: VisualEditReadonlyReason
  message: string
  sourceRange?: VisualEditSourceRange
}

/**
 * 单个 Vue SFC 的可视化编辑分析结果；源码 hash 是后续保存时的并发校验基线。
 */
export interface VisualEditSfcManifest {
  protocolVersion: PageVisualEditProtocolVersion
  modulePath: string
  sourceHash: string
  tailwindCatalog: VisualEditTailwindCatalog
  jsonSources: VisualEditJsonSource[]
  root: VisualEditTemplateNode
  diagnostics: VisualEditDiagnostic[]
}

export type VisualEditJsonSourceKind =
  | 'const'
  | 'ref'
  | 'reactive'
  | 'template-expression'

/** 描述可由 set_json 原子替换的静态 JSON 字面量。 */
export interface VisualEditJsonSource {
  sourceId: string
  kind: VisualEditJsonSourceKind
  name?: string
  value: VisualEditJsonValue
  sourceRange: VisualEditSourceRange
  editable: true
}

export interface VisualEditSetValueOperation {
  type: 'set_value'
  nodeId: string
  bindingId: string
  instancePath: VisualEditInstancePathSegment[]
  value: VisualEditLiteralValue
}

/** 原子替换 Manifest 中一个去重 JSON 源。 */
export interface VisualEditSetJsonOperation {
  type: 'set_json'
  sourceId: string
  value: VisualEditJsonValue
}

export interface VisualEditTailwindTokenChange {
  group: string
  className: string | null
}

export interface VisualEditSetTailwindTokensOperation {
  type: 'set_tailwind_tokens'
  nodeId: string
  bindingId: string
  instancePath: VisualEditInstancePathSegment[]
  changes: VisualEditTailwindTokenChange[]
}

/** 使用规范化的受限 HTML 片段替换文本容器内部内容。 */
export interface VisualEditSetRichTextOperation {
  type: 'set_rich_text'
  nodeId: string
  bindingId: string
  instancePath: VisualEditInstancePathSegment[]
  html: string
}

/** 复制普通模板节点或携带实例路径的循环数据项。 */
export interface VisualEditDuplicateNodeOperation {
  type: 'duplicate_node'
  nodeId: string
  instancePath: VisualEditInstancePathSegment[]
}

/** 删除普通模板节点、整个循环模板或携带实例路径的循环数据项。 */
export interface VisualEditDeleteNodeOperation {
  type: 'delete_node'
  nodeId: string
  instancePath: VisualEditInstancePathSegment[]
}

export type VisualEditOperation =
  | VisualEditSetValueOperation
  | VisualEditSetJsonOperation
  | VisualEditSetRichTextOperation
  | VisualEditSetTailwindTokensOperation
  | VisualEditDuplicateNodeOperation
  | VisualEditDeleteNodeOperation

/**
 * Runtime iframe 向显式父页面 origin 发送的只读选区消息。
 */
export interface VisualEditSelectionMessage {
  type: typeof PAGE_VISUAL_EDIT_SELECTION_EVENT
  payload: {
    protocolVersion: PageVisualEditProtocolVersion
    artifactId: string
    nodeId: string
    instancePath: VisualEditInstancePathSegment[]
  }
}

/** Editor 图层树向 Runtime 下发的受信节点定位命令。 */
export interface VisualEditSelectNodeMessage {
  type: typeof PAGE_VISUAL_EDIT_SELECT_NODE_EVENT
  payload: {
    protocolVersion: PageVisualEditProtocolVersion
    artifactId: string
    nodeId: string
    instancePath: VisualEditInstancePathSegment[]
  }
}
