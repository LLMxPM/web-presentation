/**
 * 文件用途：定义组件预览 schema、状态初始化与 iframe 通信协议的共享辅助函数。
 */

import type {
  RuntimeComponentPreviewPlacementOptions,
  ComponentPreviewPreset,
  ComponentPreviewSchema,
  ComponentPreviewSlotField,
  ComponentPreviewSlotNode,
} from './runtime-preview'

export const COMPONENT_PREVIEW_READY_EVENT = 'component-preview:ready'
export const COMPONENT_PREVIEW_ERROR_EVENT = 'component-preview:error'
export const COMPONENT_PREVIEW_UPDATE_STATE_EVENT = 'component-preview:update-state'
export const COMPONENT_PREVIEW_UPDATE_PLACEMENT_EVENT = 'component-preview:update-placement'
export const COMPONENT_PREVIEW_RENDER_SETTLED_EVENT = 'component-preview:render-settled'

export interface ComponentPreviewState {
  props: Record<string, unknown>
  slots: Record<string, ComponentPreviewSlotNode[]>
  mocks: Record<string, unknown>
  activePresetKey: string | null
}

export interface ComponentPreviewReadyMessage {
  type: typeof COMPONENT_PREVIEW_READY_EVENT
  payload: {
    version: 1
    artifactId: string
    schema: ComponentPreviewSchema | null
    defaultState: ComponentPreviewState
    componentMeta: {
      code: string
      versionNo?: number
      displayName: string
      source?: 'workspace_component' | 'runtime_kit'
      runtimeKitComponentName?: string
      runtimeKitManifestVersion?: string
    }
  }
}

export interface ComponentPreviewErrorMessage {
  type: typeof COMPONENT_PREVIEW_ERROR_EVENT
  payload: {
    version: 1
    artifactId: string
    message: string
  }
}

export interface ComponentPreviewUpdateStateMessage {
  type: typeof COMPONENT_PREVIEW_UPDATE_STATE_EVENT
  payload: {
    version: 1
    artifactId: string
    state: ComponentPreviewState
    requestId?: string
  }
}

export interface ComponentPreviewRenderSettledMessage {
  type: typeof COMPONENT_PREVIEW_RENDER_SETTLED_EVENT
  payload: {
    version: 1
    artifactId: string
    requestId?: string
    activePresetKey: string | null
  }
}

export interface ComponentPreviewUpdatePlacementMessage {
  type: typeof COMPONENT_PREVIEW_UPDATE_PLACEMENT_EVENT
  payload: {
    version: 1
    artifactId: string
    placement: RuntimeComponentPreviewPlacementOptions
  }
}

/**
 * 规范化组件预览 schema，确保宿主页始终拿到可安全消费的对象结构。
 * @param value 组件模块导出的原始 previewSchema
 * @returns 规范化后的 schema；无效时返回 null
 */
export function normalizeComponentPreviewSchema(value: unknown): ComponentPreviewSchema | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }

  const source = value as Record<string, unknown>
  return {
    props: normalizeRecord<ComponentPreviewSchema['props']>(source.props),
    slots: normalizeRecord<ComponentPreviewSchema['slots']>(source.slots),
    mocks: normalizeRecord<ComponentPreviewSchema['mocks']>(source.mocks),
    presets: normalizePresetList(source.presets),
  }
}

/**
 * 基于 schema 默认值生成组件预览的初始状态。
 * @param schema 组件预览 schema
 * @returns 面板和宿主页共用的初始状态
 */
export function buildInitialComponentPreviewState(schema: ComponentPreviewSchema | null): ComponentPreviewState {
  return {
    props: Object.fromEntries(
      Object.entries(schema?.props || {}).map(([fieldKey, fieldValue]) => [fieldKey, clonePreviewValue(fieldValue?.default)]),
    ),
    slots: Object.fromEntries(
      Object.entries(schema?.slots || {}).map(([fieldKey, fieldValue]) => [
        fieldKey,
        cloneSlotNodes(fieldValue),
      ]),
    ),
    mocks: Object.fromEntries(
      Object.entries(schema?.mocks || {}).map(([fieldKey, fieldValue]) => [fieldKey, clonePreviewValue(fieldValue?.default)]),
    ),
    activePresetKey: null,
  }
}

/**
 * 对外部消息中的状态对象做最小归一化，避免非法结构污染宿主页状态。
 * @param value 外部传入状态
 * @returns 归一化状态
 */
export function normalizeComponentPreviewState(value: unknown): ComponentPreviewState {
  const source = isPlainObject(value) ? value : {}
  return {
    props: normalizeRecord<Record<string, unknown>>(source.props),
    slots: Object.fromEntries(
      Object.entries(normalizeRecord<Record<string, unknown>>(source.slots)).map(([slotKey, slotValue]) => [
        slotKey,
        Array.isArray(slotValue) ? (slotValue as ComponentPreviewSlotNode[]) : [],
      ]),
    ),
    mocks: normalizeRecord<Record<string, unknown>>(source.mocks),
    activePresetKey: typeof source.activePresetKey === 'string' ? source.activePresetKey : null,
  }
}

/**
 * 使用 JSON 语义对预览值做深拷贝，保证宿主页和 Editor 各自持有独立对象。
 * @param value 原始值
 * @returns 深拷贝后的值
 */
export function clonePreviewValue<T>(value: T): T {
  if (value === undefined) {
    return value
  }
  return JSON.parse(JSON.stringify(value)) as T
}

/**
 * 复制 slot 节点数组，避免跨窗口共享对象引用。
 * @param fieldValue slot 字段配置
 * @returns 拷贝后的默认节点数组
 */
function cloneSlotNodes(fieldValue: ComponentPreviewSlotField | undefined): ComponentPreviewSlotNode[] {
  return Array.isArray(fieldValue?.default) ? clonePreviewValue(fieldValue.default) : []
}

/**
 * 判断一个值是否为普通对象。
 * @param value 待判断值
 * @returns 是否为普通对象
 */
function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

/**
 * 归一化预设列表，兼容早期或 AI 生成配置中的 name 字段。
 * @param value 原始 presets 配置
 * @returns 可供 Editor 消费的预设列表
 */
function normalizePresetList(value: unknown): ComponentPreviewSchema['presets'] {
  if (!Array.isArray(value)) {
    return []
  }

  const normalizedPresets: ComponentPreviewPreset[] = []
  for (const item of value) {
    if (!isPlainObject(item)) {
      continue
    }
    const presetKey = typeof item.key === 'string' ? item.key : item.name
    if (typeof presetKey !== 'string' || typeof item.label !== 'string') {
      continue
    }
    normalizedPresets.push({
      ...item,
      key: presetKey,
      label: item.label,
    } as ComponentPreviewPreset)
  }
  return normalizedPresets
}

/**
 * 将未知值规范化为普通键值对象。
 * @param value 输入值
 * @returns 普通对象
 */
function normalizeRecord<T extends object>(value: unknown): T {
  return (isPlainObject(value) ? { ...value } : {}) as T
}
