/**
 * 文件功能：定义组件预览面板、iframe 通信与 previewSchema 的共享类型。
 */

import type { ComponentPreviewPlacementOptions } from '@/types/api'

export type ComponentPreviewFieldType = 'string' | 'textarea' | 'number' | 'boolean' | 'select' | 'json'

export interface ComponentPreviewSelectOption {
  label: string
  value: string | number | boolean
}

export interface ComponentPreviewPropField {
  type: ComponentPreviewFieldType
  label?: string
  description?: string
  required?: boolean
  default?: unknown
  placeholder?: string
  options?: ComponentPreviewSelectOption[]
}

export interface ComponentPreviewSlotTextNode {
  type: 'text'
  value: string
}

export interface ComponentPreviewSlotHtmlNode {
  type: 'html'
  value: string
}

export interface ComponentPreviewSlotComponentNode {
  type: 'component'
  component: string
  props?: Record<string, unknown>
  children?: ComponentPreviewSlotNode[]
}

export type ComponentPreviewSlotNode =
  | ComponentPreviewSlotTextNode
  | ComponentPreviewSlotHtmlNode
  | ComponentPreviewSlotComponentNode

export interface ComponentPreviewSlotField {
  label?: string
  description?: string
  default?: ComponentPreviewSlotNode[]
}

export interface ComponentPreviewMockField {
  label?: string
  description?: string
  default?: unknown
}

export interface ComponentPreviewPreset {
  key: string
  label: string
  description?: string
  props?: Record<string, unknown>
  slots?: Record<string, ComponentPreviewSlotNode[]>
  mocks?: Record<string, unknown>
}

export interface ComponentPreviewSchema {
  props?: Record<string, ComponentPreviewPropField>
  slots?: Record<string, ComponentPreviewSlotField>
  mocks?: Record<string, ComponentPreviewMockField>
  presets?: ComponentPreviewPreset[]
}

export interface ComponentPreviewState {
  props: Record<string, unknown>
  slots: Record<string, ComponentPreviewSlotNode[]>
  mocks: Record<string, unknown>
  activePresetKey: string | null
}

export const COMPONENT_PREVIEW_READY_EVENT = 'component-preview:ready'
export const COMPONENT_PREVIEW_ERROR_EVENT = 'component-preview:error'
export const COMPONENT_PREVIEW_UPDATE_STATE_EVENT = 'component-preview:update-state'
export const COMPONENT_PREVIEW_UPDATE_PLACEMENT_EVENT = 'component-preview:update-placement'

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
  }
}

export interface ComponentPreviewUpdatePlacementMessage {
  type: typeof COMPONENT_PREVIEW_UPDATE_PLACEMENT_EVENT
  payload: {
    version: 1
    artifactId: string
    placement: ComponentPreviewPlacementOptions
  }
}

/**
 * 复制组件预览状态，避免编辑器内部直接复用 iframe 传来的对象引用。
 * @param value 原始状态
 * @returns 深拷贝后的状态
 */
export function cloneComponentPreviewState(value: ComponentPreviewState): ComponentPreviewState {
  return JSON.parse(JSON.stringify(value)) as ComponentPreviewState
}

/**
 * 基于 schema 默认值构建初始面板状态。
 * @param schema 组件预览 schema
 * @returns 默认状态
 */
export function buildInitialComponentPreviewState(schema: ComponentPreviewSchema | null): ComponentPreviewState {
  return {
    props: Object.fromEntries(
      Object.entries(schema?.props || {}).map(([fieldKey, fieldValue]) => [fieldKey, clonePreviewValue(fieldValue?.default)]),
    ),
    slots: Object.fromEntries(
      Object.entries(schema?.slots || {}).map(([fieldKey, fieldValue]) => [
        fieldKey,
        Array.isArray(fieldValue?.default) ? clonePreviewValue(fieldValue.default) : [],
      ]),
    ),
    mocks: Object.fromEntries(
      Object.entries(schema?.mocks || {}).map(([fieldKey, fieldValue]) => [fieldKey, clonePreviewValue(fieldValue?.default)]),
    ),
    activePresetKey: null,
  }
}

/**
 * 对预览值做 JSON 语义深拷贝。
 * @param value 原始值
 * @returns 深拷贝值
 */
export function clonePreviewValue<T>(value: T): T {
  if (value === undefined) {
    return value
  }
  return JSON.parse(JSON.stringify(value)) as T
}
