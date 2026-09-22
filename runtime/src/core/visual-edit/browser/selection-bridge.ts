/**
 * 文件用途：在页面可视化编辑专用 artifact 中捕获插桩节点点击，并向明确的父页面 origin 回传只读选区。
 */

import type {
  RuntimePreloadedConfigBundle,
  RuntimePreviewContext,
} from '@/core/shared/runtime-preview'
import { getRuntimePreloadedConfig, getRuntimePreviewContext } from '@/core/utils/path'

import {
  PAGE_VISUAL_EDIT_PROTOCOL_VERSION,
  PAGE_VISUAL_EDIT_SELECT_NODE_EVENT,
  PAGE_VISUAL_EDIT_SELECTION_EVENT,
  type VisualEditInstancePathSegment,
  type VisualEditSelectNodeMessage,
  type VisualEditSelectionMessage,
} from '../protocol'
import {
  VISUAL_EDIT_LOOP_ATTRIBUTE,
  VISUAL_EDIT_LOOP_INDEX_ATTRIBUTE,
  VISUAL_EDIT_LOOP_KEY_ATTRIBUTE,
  VISUAL_EDIT_NODE_ATTRIBUTE,
} from '../instrumentation/markers'
import { createHoverOverlay, createSelectionOverlay } from './selection-overlay'

interface VisualEditMessageTarget {
  postMessage(message: unknown, targetOrigin: string): void
}

interface NodeSelectionScope {
  loopNodeId?: string
  loopBlocked: boolean
  renderNodeIds: string[]
}

interface SelectionBridgeContext {
  artifactId: string
  nodeScopes: Map<string, NodeSelectionScope>
  parentOrigin: string
  postMessageTarget: VisualEditMessageTarget
}

export interface VisualEditSelectionBridgeOptions {
  runtimeWindow?: Window
  runtimeDocument?: Document
  preloadedConfig?: RuntimePreloadedConfigBundle
  previewContext?: RuntimePreviewContext
  /** 仅用于单元测试覆盖浏览器只读 referrer；生产调用必须留空。 */
  referrer?: string
  /** 仅用于单元测试替换 WindowProxy；生产调用必须留空。 */
  postMessageTarget?: VisualEditMessageTarget
}

/**
 * 仅为合法的 page_visual_edit_preview 安装点击捕获器。
 * @returns 清理函数；普通预览或上下文不可信时返回 null，且不安装任何监听器
 */
export function registerPageVisualEditSelectionBridge(
  options: VisualEditSelectionBridgeOptions = {},
): (() => void) | null {
  const runtimeWindow = options.runtimeWindow || window
  const runtimeDocument = options.runtimeDocument || document
  const context = resolveBridgeContext(options, runtimeWindow, runtimeDocument)
  if (!context) {
    return null
  }

  const selectionOverlay = createSelectionOverlay(runtimeWindow, runtimeDocument)
  const hoverOverlay = createHoverOverlay(runtimeWindow, runtimeDocument)
  let selectedTargets: Element[] = []
  let hoveredTarget: Element | null = null

  /** 更新悬停提示；非法 marker 与已选中节点不重复绘制。 */
  const updateHoveredTarget = (target: EventTarget | null): void => {
    const markerElement = findMarkerElement(target)
    if (
      !markerElement
      || !resolveMarkerSelection(markerElement, context)
      || selectedTargets.includes(markerElement)
    ) {
      hoveredTarget = null
      hoverOverlay.clear()
      return
    }
    if (hoveredTarget === markerElement) {
      return
    }
    hoveredTarget = markerElement
    hoverOverlay.show([markerElement])
  }

  /** 显示选区并清理与选区重合的悬停提示。 */
  const showSelection = (targets: Element[]): void => {
    selectedTargets = targets
    selectionOverlay.show(targets)
    if (hoveredTarget && selectedTargets.includes(hoveredTarget)) {
      hoveredTarget = null
      hoverOverlay.clear()
    }
  }

  const handleClick = (event: MouseEvent): void => {
    const markerElement = findMarkerElement(event.target)
    if (!markerElement) {
      return
    }
    const selection = resolveMarkerSelection(markerElement, context)
    if (!selection) {
      return
    }

    event.preventDefault()
    event.stopPropagation()
    event.stopImmediatePropagation()
    showSelection([markerElement])
    context.postMessageTarget.postMessage(selection, context.parentOrigin)
  }

  const handleMouseOver = (event: MouseEvent): void => {
    updateHoveredTarget(event.target)
  }

  const handleMouseOut = (event: MouseEvent): void => {
    updateHoveredTarget(event.relatedTarget)
  }

  const handleMessage = (event: MessageEvent<unknown>): void => {
    if (event.source !== runtimeWindow.parent || event.origin !== context.parentOrigin) return
    const message = parseSelectNodeMessage(event.data, context)
    if (!message) return
    const targets = findSelectionTargets(runtimeDocument, message, context)
    if (!targets.length) {
      selectedTargets = []
      selectionOverlay.clear()
      return
    }
    targets[0]?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })
    showSelection(targets)
  }

  runtimeDocument.addEventListener('click', handleClick, true)
  runtimeDocument.addEventListener('mouseover', handleMouseOver, true)
  runtimeDocument.addEventListener('mouseout', handleMouseOut, true)
  runtimeWindow.addEventListener('message', handleMessage)
  return () => {
    runtimeDocument.removeEventListener('click', handleClick, true)
    runtimeDocument.removeEventListener('mouseover', handleMouseOver, true)
    runtimeDocument.removeEventListener('mouseout', handleMouseOut, true)
    runtimeWindow.removeEventListener('message', handleMessage)
    selectionOverlay.dispose()
    hoverOverlay.dispose()
  }
}

/**
 * 从预加载 artifact、公开预览上下文与 referrer 构造可信桥接上下文。
 */
function resolveBridgeContext(
  options: VisualEditSelectionBridgeOptions,
  runtimeWindow: Window,
  runtimeDocument: Document,
): SelectionBridgeContext | null {
  const config = options.preloadedConfig || getRuntimePreloadedConfig()
  const previewContext = options.previewContext || getRuntimePreviewContext()
  const artifact = config?.manifest
  const visualEdit = artifact?.visual_edit
  if (
    artifact?.artifact_kind !== 'page_visual_edit_preview'
    || visualEdit?.protocol_version !== PAGE_VISUAL_EDIT_PROTOCOL_VERSION
    || !previewContext
    || artifact.artifact_id !== previewContext.artifactId
  ) {
    return null
  }

  const nodeScopes = collectManifestNodeScopes(visualEdit.manifest)
  const parentOrigin = parseReferrerOrigin(options.referrer ?? runtimeDocument.referrer)
  if (!nodeScopes || !parentOrigin) {
    return null
  }

  const postMessageTarget = options.postMessageTarget || runtimeWindow.parent
  if (!options.postMessageTarget && postMessageTarget === runtimeWindow) {
    return null
  }
  return {
    artifactId: artifact.artifact_id,
    nodeScopes,
    parentOrigin,
    postMessageTarget,
  }
}

/**
 * 校验 Manifest 最小结构，并计算每个模板节点应携带的单层循环 marker。
 */
function collectManifestNodeScopes(manifest: unknown): Map<string, NodeSelectionScope> | null {
  if (!isRecord(manifest) || manifest.protocolVersion !== PAGE_VISUAL_EDIT_PROTOCOL_VERSION) {
    return null
  }
  const root = manifest.root
  if (!isRecord(root) || !Array.isArray(root.children)) {
    return null
  }

  const result = new Map<string, NodeSelectionScope>()
  const rootScope: NodeSelectionScope = { loopBlocked: false, renderNodeIds: [] }
  const childRenderIds: string[] = []
  for (const child of root.children) {
    const renderIds = collectNodeScope(child, rootScope, result)
    if (!renderIds) return null
    childRenderIds.push(...renderIds)
  }
  if (typeof root.nodeId !== 'string' || !root.nodeId || result.has(root.nodeId)) return null
  result.set(root.nodeId, { ...rootScope, renderNodeIds: childRenderIds })
  return result.size > 0 ? result : null
}

/**
 * 深度优先验证 nodeId 唯一性；不稳定或嵌套循环会阻断整棵子树的实例定位。
 */
function collectNodeScope(
  rawNode: unknown,
  parentScope: NodeSelectionScope,
  result: Map<string, NodeSelectionScope>,
): string[] | null {
  if (!isRecord(rawNode) || typeof rawNode.nodeId !== 'string' || !rawNode.nodeId || !Array.isArray(rawNode.children)) {
    return null
  }
  if (result.has(rawNode.nodeId)) {
    return null
  }

  const scope = resolveNodeScope(rawNode, parentScope)
  if (!scope) {
    return null
  }
  result.set(rawNode.nodeId, { ...scope, renderNodeIds: [] })
  const childRenderIds: string[] = []
  for (const child of rawNode.children) {
    const renderIds = collectNodeScope(child, scope, result)
    if (!renderIds) return null
    childRenderIds.push(...renderIds)
  }
  const renderNodeIds = rawNode.tag === 'template' ? childRenderIds : [rawNode.nodeId]
  result.set(rawNode.nodeId, { ...scope, renderNodeIds })
  return renderNodeIds
}

/**
 * 根据节点自身 loopContext 与父作用域生成期望 marker 范围。
 */
function resolveNodeScope(
  rawNode: Record<string, unknown>,
  parentScope: NodeSelectionScope,
): NodeSelectionScope | null {
  if (rawNode.loopContext == null) {
    return { ...parentScope, renderNodeIds: [] }
  }
  const loopContext = rawNode.loopContext
  if (!isRecord(loopContext)) {
    return null
  }
  const nodeId = rawNode.nodeId
  if (typeof nodeId !== 'string') {
    return null
  }
  const isStableTopLevelLoop = !parentScope.loopBlocked
    && !parentScope.loopNodeId
    && loopContext.editable === true
    && typeof loopContext.keyMember === 'string'
    && Boolean(loopContext.keyMember)
    && loopContext.loopNodeId === nodeId
  return isStableTopLevelLoop
    ? { loopNodeId: nodeId, loopBlocked: false, renderNodeIds: [] }
    : { loopBlocked: true, renderNodeIds: [] }
}

/** 校验 Editor 下发的节点定位消息，并拒绝额外或失配字段。 */
function parseSelectNodeMessage(
  value: unknown,
  context: SelectionBridgeContext,
): VisualEditSelectNodeMessage | null {
  if (
    !isRecord(value)
    || !hasExactFields(value, ['type', 'payload'])
    || value.type !== PAGE_VISUAL_EDIT_SELECT_NODE_EVENT
    || !isRecord(value.payload)
    || !hasExactFields(value.payload, ['protocolVersion', 'artifactId', 'nodeId', 'instancePath'])
  ) return null
  const payload = value.payload
  if (
    payload.protocolVersion !== PAGE_VISUAL_EDIT_PROTOCOL_VERSION
    || payload.artifactId !== context.artifactId
    || typeof payload.nodeId !== 'string'
    || !context.nodeScopes.has(payload.nodeId)
    || !Array.isArray(payload.instancePath)
    || !payload.instancePath.every(isInstancePathSegment)
  ) return null
  return value as unknown as VisualEditSelectNodeMessage
}

/** 根据逻辑节点与可选循环实例找到实际带 marker 的 DOM 元素。 */
function findSelectionTargets(
  runtimeDocument: Document,
  message: VisualEditSelectNodeMessage,
  context: SelectionBridgeContext,
): Element[] {
  const scope = context.nodeScopes.get(message.payload.nodeId)
  if (!scope) return []
  const renderIds = new Set(scope.renderNodeIds)
  return [...runtimeDocument.querySelectorAll(`[${VISUAL_EDIT_NODE_ATTRIBUTE}]`)].filter((element) => {
    if (!renderIds.has(element.getAttribute(VISUAL_EDIT_NODE_ATTRIBUTE) || '')) return false
    return message.payload.instancePath.length === 0
      || sameInstancePath(resolveElementInstancePath(element), message.payload.instancePath)
  })
}

/** 从 DOM marker 宽松读取实例路径，供父页面主动定位过滤。 */
function resolveElementInstancePath(element: Element): VisualEditInstancePathSegment[] {
  const loopNodeId = element.getAttribute(VISUAL_EDIT_LOOP_ATTRIBUTE)
  const rawKey = element.getAttribute(VISUAL_EDIT_LOOP_KEY_ATTRIBUTE)
  const rawIndex = element.getAttribute(VISUAL_EDIT_LOOP_INDEX_ATTRIBUTE)
  if (!loopNodeId || rawKey === null) return []
  const key = parseLoopKey(rawKey)
  const index = rawIndex === null ? undefined : parseLoopIndex(rawIndex)
  if (key === undefined) return []
  return [{ loopNodeId, key, ...(index === undefined ? {} : { index }) }]
}

/** 比较两个单层实例路径，稳定 key 优先且 index 仅辅助校验。 */
function sameInstancePath(left: VisualEditInstancePathSegment[], right: VisualEditInstancePathSegment[]): boolean {
  if (left.length !== right.length) return false
  return left.every((segment, index) => {
    const target = right[index]
    return target?.loopNodeId === segment.loopNodeId
      && target.key === segment.key
      && (target.index === undefined || target.index === segment.index)
  })
}

/** 判断未知值是否为合法单层实例路径段。 */
function isInstancePathSegment(value: unknown): value is VisualEditInstancePathSegment {
  if (!isRecord(value) || !hasOnlyFields(value, ['loopNodeId', 'key', 'index']) || typeof value.loopNodeId !== 'string') return false
  const hasKey = Object.prototype.hasOwnProperty.call(value, 'key')
  const hasIndex = Object.prototype.hasOwnProperty.call(value, 'index')
  const keyValid = typeof value.key === 'string'
    || (typeof value.key === 'number' && Number.isFinite(value.key) && Number.isInteger(value.key))
  const indexValid = typeof value.index === 'number' && Number.isInteger(value.index) && value.index >= 0
  return (!hasKey || keyValid) && (!hasIndex || indexValid) && ((hasKey && keyValid) || (hasIndex && indexValid))
}

/** 判断对象是否只包含且完整包含指定字段。 */
function hasExactFields(value: Record<string, unknown>, fields: string[]): boolean {
  return Object.keys(value).length === fields.length && fields.every(field => Object.prototype.hasOwnProperty.call(value, field))
}

/** 判断对象没有白名单之外的字段。 */
function hasOnlyFields(value: Record<string, unknown>, fields: string[]): boolean {
  const allowed = new Set(fields)
  return Object.keys(value).every(field => allowed.has(field))
}

/**
 * 从点击目标向上寻找最近的 Runtime node marker。
 */
function findMarkerElement(target: EventTarget | null): Element | null {
  if (!target || typeof (target as Element).closest !== 'function') {
    return null
  }
  return (target as Element).closest(`[${VISUAL_EDIT_NODE_ATTRIBUTE}]`)
}

/**
 * 校验 DOM marker 与 Manifest 预期一致，并构造无额外字段的选择消息。
 */
function resolveMarkerSelection(
  markerElement: Element,
  context: SelectionBridgeContext,
): VisualEditSelectionMessage | null {
  const nodeId = markerElement.getAttribute(VISUAL_EDIT_NODE_ATTRIBUTE) || ''
  const expectedScope = context.nodeScopes.get(nodeId)
  if (!expectedScope) {
    return null
  }

  const instancePath = resolveInstancePath(markerElement, expectedScope)
  if (!instancePath) {
    return null
  }
  return {
    type: PAGE_VISUAL_EDIT_SELECTION_EVENT,
    payload: {
      protocolVersion: PAGE_VISUAL_EDIT_PROTOCOL_VERSION,
      artifactId: context.artifactId,
      nodeId,
      instancePath,
    },
  }
}

/**
 * 解析单层实例 marker；key 仅接受 JSON 字符串或有限整数。
 */
function resolveInstancePath(
  markerElement: Element,
  expectedScope: NodeSelectionScope,
): VisualEditInstancePathSegment[] | null {
  const loopNodeId = markerElement.getAttribute(VISUAL_EDIT_LOOP_ATTRIBUTE)
  const rawKey = markerElement.getAttribute(VISUAL_EDIT_LOOP_KEY_ATTRIBUTE)
  const rawIndex = markerElement.getAttribute(VISUAL_EDIT_LOOP_INDEX_ATTRIBUTE)
  if (!expectedScope.loopNodeId) {
    return loopNodeId === null && rawKey === null && rawIndex === null ? [] : null
  }
  if (loopNodeId !== expectedScope.loopNodeId || rawKey === null) {
    return null
  }

  const key = parseLoopKey(rawKey)
  const index = rawIndex === null ? undefined : parseLoopIndex(rawIndex)
  if (key === undefined || (rawIndex !== null && index === undefined)) {
    return null
  }
  return [{
    loopNodeId,
    key,
    ...(index === undefined ? {} : { index }),
  }]
}

/**
 * 解析由插桩表达式 JSON.stringify 生成的 key 属性。
 */
function parseLoopKey(rawKey: string): string | number | undefined {
  try {
    const key: unknown = JSON.parse(rawKey)
    if (typeof key === 'string') {
      return key
    }
    return typeof key === 'number' && Number.isFinite(key) && Number.isInteger(key)
      ? key
      : undefined
  } catch {
    return undefined
  }
}

/**
 * 解析可选 index marker；它只作诊断辅助，稳定 key 仍是写入定位主键。
 */
function parseLoopIndex(rawIndex: string): number | undefined {
  if (!/^(0|[1-9]\d*)$/.test(rawIndex)) {
    return undefined
  }
  const index = Number(rawIndex)
  return Number.isFinite(index) && Number.isInteger(index) ? index : undefined
}

/**
 * 仅接受绝对 HTTP(S) referrer，并提取不可通配的 targetOrigin。
 */
function parseReferrerOrigin(referrer: string): string | null {
  try {
    const url = new URL(referrer)
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.origin : null
  } catch {
    return null
  }
}

/**
 * 判断未知值是否为非数组对象。
 */
function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}
