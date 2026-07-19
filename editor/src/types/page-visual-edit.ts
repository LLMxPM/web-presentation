/**
 * 文件功能：定义页面可视化编辑的 Editor 领域模型、Backend 请求和编辑态 artifact 响应协议。
 */

import type { PreviewArtifactResponse } from '@/types/api'

/** 页面可视化编辑当前协议号，未知版本必须由调用方拒绝。 */
export const PAGE_VISUAL_EDIT_PROTOCOL_VERSION = 1 as const
export const PAGE_VISUAL_EDIT_SELECTION_EVENT = 'page-visual-edit:selection' as const
export const PAGE_VISUAL_EDIT_SELECT_NODE_EVENT = 'page-visual-edit:select-node' as const

export type PageVisualEditProtocolVersion = typeof PAGE_VISUAL_EDIT_PROTOCOL_VERSION
export type PageVisualEditOperationType = 'set_value' | 'set_json' | 'set_rich_text' | 'set_tailwind_tokens' | 'duplicate_node' | 'delete_node'
export type PageVisualEditValue = string | number | boolean | null
export type PageVisualEditJsonValue = PageVisualEditValue | PageVisualEditJsonValue[] | { [key: string]: PageVisualEditJsonValue }
export type PageVisualEditInstanceKey = string | number
export type PageVisualEditReadonlyReason =
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
  | 'STRUCTURE_ROOT_UNSUPPORTED'
  | 'STRUCTURE_CONTROL_FLOW_UNSUPPORTED'
  | 'STRUCTURE_LOOP_INSTANCE_REQUIRED'
export type PageVisualEditBindingKind = 'text' | 'rich_text' | 'class' | 'prop' | 'json'
export type PageVisualEditValueType = 'string' | 'number' | 'boolean' | 'null' | 'json' | 'unknown'
export type PageVisualEditNodeKind = 'root' | 'element' | 'component'
export type PageVisualEditScriptCollectionKind = 'const-array' | 'ref-array' | 'reactive-array'

interface PageVisualEditInstancePathSegmentBase {
  loopNodeId: string
}

/**
 * 描述一个运行时循环实例；每段至少携带稳定 key 或辅助 index。
 * Editor 使用 camelCase 与 Runtime 消息保持一致，API 层负责转为 snake_case。
 */
export type PageVisualEditInstancePathSegment = PageVisualEditInstancePathSegmentBase & (
  | { key: PageVisualEditInstanceKey; index?: number }
  | { key?: never; index: number }
)

/** 标识规范源码中的一个可编辑绑定及其运行时实例。 */
export interface PageVisualEditTarget {
  nodeId: string
  bindingId: string
  instancePath: PageVisualEditInstancePathSegment[]
}

/** 标识规范源码中的模板节点或循环实例。 */
export interface PageVisualEditNodeTarget {
  nodeId: string
  instancePath: PageVisualEditInstancePathSegment[]
}

/** Runtime iframe 向 Editor 上报的节点选择消息。 */
export interface PageVisualEditSelectionMessage {
  type: typeof PAGE_VISUAL_EDIT_SELECTION_EVENT
  payload: {
    protocolVersion: PageVisualEditProtocolVersion
    artifactId: string
    nodeId: string
    bindingId?: string
    instancePath: PageVisualEditInstancePathSegment[]
  }
}

/** Editor 向 Runtime iframe 下发的节点定位消息。 */
export interface PageVisualEditSelectNodeMessage {
  type: typeof PAGE_VISUAL_EDIT_SELECT_NODE_EVENT
  payload: {
    protocolVersion: PageVisualEditProtocolVersion
    artifactId: string
    nodeId: string
    instancePath: PageVisualEditInstancePathSegment[]
  }
}

interface PageVisualEditBindingOperationBase extends PageVisualEditTarget {
  type: 'set_value' | 'set_rich_text' | 'set_tailwind_tokens'
}

/** 设置文本、数字、布尔或空值字面量。 */
export interface PageVisualEditSetValueOperation extends PageVisualEditBindingOperationBase {
  type: 'set_value'
  value: PageVisualEditValue
}

export interface PageVisualEditSetJsonOperation {
  type: 'set_json'
  sourceId: string
  value: PageVisualEditJsonValue
}

/** 设置文本容器内部的规范化受限 HTML 片段。 */
export interface PageVisualEditSetRichTextOperation extends PageVisualEditBindingOperationBase {
  type: 'set_rich_text'
  html: string
}

/** 描述一个 Tailwind 冲突组的目标 class；null 表示移除该组当前 class。 */
export interface PageVisualEditTailwindTokenChange {
  group: string
  className?: string | null
}

/** 按冲突组设置受限 Tailwind class；复杂和未知类由 Backend/Runtime 保留并校验。 */
export interface PageVisualEditSetTailwindTokensOperation extends PageVisualEditBindingOperationBase {
  type: 'set_tailwind_tokens'
  changes: PageVisualEditTailwindTokenChange[]
}

export interface PageVisualEditDuplicateNodeOperation extends PageVisualEditNodeTarget {
  type: 'duplicate_node'
}

export interface PageVisualEditDeleteNodeOperation extends PageVisualEditNodeTarget {
  type: 'delete_node'
}

export type PageVisualEditOperation =
  | PageVisualEditSetValueOperation
  | PageVisualEditSetJsonOperation
  | PageVisualEditSetRichTextOperation
  | PageVisualEditSetTailwindTokensOperation
  | PageVisualEditDuplicateNodeOperation
  | PageVisualEditDeleteNodeOperation

/** Vue SFC 中以 UTF-16 offset 表示的半开源码区间。 */
export interface PageVisualEditSourceRange {
  start: number
  end: number
}

/** script setup 数组字面量中一个可定位成员。 */
export interface PageVisualEditScriptMemberLocation {
  index: number
  key?: PageVisualEditInstanceKey | null
  value?: PageVisualEditValue
  source_range?: PageVisualEditSourceRange | null
  editable: boolean
  readonly_reason?: PageVisualEditReadonlyReason | null
}

/** item.member 绑定对应的静态数组数据源。 */
export interface PageVisualEditScriptArrayBindingSource {
  kind: 'script-array-item'
  collection_name: string
  collection_kind: PageVisualEditScriptCollectionKind
  item_alias: string
  member: string
  key_member?: string | null
  locations: PageVisualEditScriptMemberLocation[]
}

/** Vue template 中可直接写回的字面量来源。 */
export interface PageVisualEditTemplateBindingSource {
  kind: 'template-literal'
}

/** 标识 binding 覆盖模板元素的内部受限富文本。 */
export interface PageVisualEditTemplateRichTextBindingSource {
  kind: 'template-rich-text'
}

export interface PageVisualEditJsonBindingSource {
  kind: 'json-source'
  source_id: string
}

export type PageVisualEditBindingSource =
  | PageVisualEditScriptArrayBindingSource
  | PageVisualEditTemplateBindingSource
  | PageVisualEditTemplateRichTextBindingSource
  | PageVisualEditJsonBindingSource

/** 属性检查器可展示的文本、class 或组件 prop 绑定。 */
export interface PageVisualEditBinding {
  binding_id: string
  node_id: string
  kind: PageVisualEditBindingKind
  name?: string | null
  value_type: PageVisualEditValueType
  value?: PageVisualEditJsonValue
  expression?: string | null
  source_range: PageVisualEditSourceRange
  editable: boolean
  readonly_reason?: PageVisualEditReadonlyReason | null
  source?: PageVisualEditBindingSource | null
}

/** 单层 v-for 的源码语义。 */
export interface PageVisualEditLoopContext {
  loop_node_id: string
  source_expression: string
  source_binding?: string | null
  item_alias: string
  index_alias?: string | null
  key_expression?: string | null
  key_member?: string | null
  editable: boolean
  readonly_reason?: PageVisualEditReadonlyReason | null
}

export interface PageVisualEditLoopItemLocation {
  index: number
  key: PageVisualEditInstanceKey
}

export interface PageVisualEditTemplateActions {
  can_duplicate: boolean
  can_delete: boolean
  readonly_reason?: PageVisualEditReadonlyReason | null
}

export interface PageVisualEditLoopItemActions {
  can_duplicate: boolean
  can_delete: boolean
  loop_node_id: string
  collection_name: string
  key_member: string
  instances: PageVisualEditLoopItemLocation[]
  readonly_reason?: PageVisualEditReadonlyReason | null
}

/** 保留 Vue 模板容器和组件边界的递归节点。 */
export interface PageVisualEditNode {
  node_id: string
  kind: PageVisualEditNodeKind
  tag: string
  source_range: PageVisualEditSourceRange
  loop_context?: PageVisualEditLoopContext | null
  template_actions: PageVisualEditTemplateActions
  loop_item_actions?: PageVisualEditLoopItemActions | null
  bindings: PageVisualEditBinding[]
  children: PageVisualEditNode[]
}

/** Tailwind 可视化控件中的一个有限 class 选项。 */
export interface PageVisualEditTailwindCatalogOption {
  class_name: string
  label: string
}

/** Tailwind 互斥样式组。 */
export interface PageVisualEditTailwindCatalogGroup {
  key: string
  label: string
  options: PageVisualEditTailwindCatalogOption[]
}

/** 由 Runtime safelist 派生的版本化 Tailwind 控件目录。 */
export interface PageVisualEditTailwindCatalog {
  version: 1
  groups: PageVisualEditTailwindCatalogGroup[]
}

/** Backend 对外返回的 snake_case 页面分析 Manifest。 */
export interface PageVisualEditManifest {
  protocol_version: PageVisualEditProtocolVersion
  module_path: string
  source_hash: string
  root: PageVisualEditNode
  diagnostics: PageVisualEditManifestDiagnostic[]
  tailwind_catalog: PageVisualEditTailwindCatalog
  json_sources: PageVisualEditJsonSource[]
}

export interface PageVisualEditJsonSource {
  source_id: string
  kind: 'const' | 'ref' | 'reactive' | 'template-expression'
  name?: string | null
  value: PageVisualEditJsonValue
  source_range: PageVisualEditSourceRange
  editable: true
}

export type PageVisualEditComponentPropControl =
  | 'string'
  | 'textarea'
  | 'number'
  | 'boolean'
  | 'select'
  | 'json'

/** 组件 previewSchema 中一个 select 有限选项。 */
export interface PageVisualEditComponentSelectOption {
  label: string
  value: string | number | boolean
}

/** Backend 筛选后允许属性面板消费的组件 prop 元数据。 */
export interface PageVisualEditComponentPropField {
  type: PageVisualEditComponentPropControl
  label?: string | null
  description?: string | null
  required?: boolean | null
  default?: unknown
  placeholder?: string | null
  options?: PageVisualEditComponentSelectOption[] | null
}

/** 页面本地组件标签绑定的钉住版本 previewSchema。 */
export interface PageVisualEditComponentSchema {
  source: 'workspace_component' | 'runtime_kit'
  import_path: string
  component_code: string
  version_no: number
  props?: Record<string, PageVisualEditComponentPropField> | null
}

/** 创建编辑态 preview artifact 的请求。 */
export interface CreatePageVisualEditPreviewArtifactPayload {
  base_version_no: number
}

/** 编辑态 artifact 附带的版本锚点和静态分析结果。 */
export interface PageVisualEditArtifactContext {
  protocol_version: PageVisualEditProtocolVersion
  page_id: number
  base_version_no: number
  source_hash: string
  module_path: string
  manifest: PageVisualEditManifest
  component_schemas: Record<string, PageVisualEditComponentSchema>
  warnings: PageVisualEditManifestDiagnostic[]
}

/** 创建编辑态 artifact 后返回的标准预览信息与可视化编辑上下文。 */
export interface PageVisualEditPreviewArtifactResponse extends PreviewArtifactResponse {
  visual_edit: PageVisualEditArtifactContext
}

/** 编辑态 Manifest 中由源码分析产生的只读或解析诊断。 */
export interface PageVisualEditManifestDiagnostic {
  severity: 'error' | 'warning'
  code: string
  message: string
  source_range?: {
    start: number
    end: number
  } | null
}

/** Backend/Runtime 在保存响应中返回的结构化诊断。 */
export interface PageVisualEditDiagnostic {
  severity: 'error' | 'warning' | 'info'
  source: string
  code: string
  message: string
  node_id?: string | null
  binding_id?: string | null
}

/**
 * Editor 调用批量保存 API 的输入。operations 保持 camelCase，API 封装会在发请求前序列化。
 */
export interface ApplyPageVisualEditPayload {
  artifact_id: string
  base_version_no: number
  source_hash: string
  operations: PageVisualEditOperation[]
  change_note: string | null
}

/** 批量保存成功后的版本推进、规范 diff 与诊断结果。 */
export interface PageVisualEditApplyResponse {
  protocol_version: PageVisualEditProtocolVersion
  success: true
  page_id: number
  previous_version_no: number
  current_version_no: number
  source_hash: string
  operations_applied: number
  canonical_diff: string
  diagnostics: PageVisualEditDiagnostic[]
  refresh_required: true
}

/** 可视化编辑面板向外层工具栏同步的交互状态。 */
export interface PageVisualEditPanelState {
  pendingCount: number
  hasPendingChanges: boolean
  stale: boolean
  saving: boolean
  hasValidationErrors: boolean
}

/** 草稿批量写入项：携带目标值及其规范源码基准值，用于恢复基准时自动移除操作。 */
export type PageVisualEditDraftChange =
  | {
    type: 'set_json'
    sourceId: string
    value: PageVisualEditJsonValue
    baselineValue: PageVisualEditJsonValue
  }
  | {
    type: 'set_value'
    target: PageVisualEditTarget
    value: PageVisualEditValue
    baselineValue: PageVisualEditValue | undefined
  }
  | {
    type: 'set_tailwind_tokens'
    target: PageVisualEditTarget
    changes: PageVisualEditTailwindTokenChange[]
    baselineChanges: PageVisualEditTailwindTokenChange[]
  }
  | {
    type: 'set_rich_text'
    target: PageVisualEditTarget
    html: string
    baselineHtml: string
  }
