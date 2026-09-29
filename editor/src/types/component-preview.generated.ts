/** 文件功能：由组件 previewSchema 生成的共享类型，勿手改；运行 pnpm run codegen:preview-types。 */

export type ComponentPreviewFieldType = "string" | "textarea" | "number" | "boolean" | "select" | "json"

export type ComponentPreviewMockField = {
  "label"?: string
  "description"?: string
  "default"?: unknown
  [key: string]: unknown
}

export type ComponentPreviewPreset = {
  "key": string
  "label": string
  "description"?: string
  "props"?: Record<string, unknown>
  "slots"?: Record<string, (ComponentPreviewSlotNode)[]>
  "mocks"?: Record<string, unknown>
  [key: string]: unknown
}

export type ComponentPreviewPropField = {
  "type": ComponentPreviewFieldType
  "label"?: string
  "description"?: string
  "required"?: boolean
  "default"?: unknown
  "placeholder"?: string
  "options"?: (ComponentPreviewSelectOption)[]
  "agent_visible"?: boolean
  [key: string]: unknown
}

export type ComponentPreviewSchema = {
  "props"?: Record<string, ComponentPreviewPropField>
  "slots"?: Record<string, ComponentPreviewSlotField>
  "mocks"?: Record<string, ComponentPreviewMockField>
  "presets"?: (ComponentPreviewPreset)[]
  [key: string]: unknown
}

export type ComponentPreviewSelectOption = {
  "label": string
  "value": string | number | boolean
  [key: string]: unknown
}

export type ComponentPreviewSlotComponentNode = {
  "type": "component"
  "component": string
  "props"?: Record<string, unknown>
  "children"?: (ComponentPreviewSlotNode)[]
  [key: string]: unknown
}

export type ComponentPreviewSlotField = {
  "label"?: string
  "description"?: string
  "default"?: (ComponentPreviewSlotNode)[]
  [key: string]: unknown
}

export type ComponentPreviewSlotHtmlNode = {
  "type": "html"
  "value": string
  [key: string]: unknown
}

export type ComponentPreviewSlotNode = (ComponentPreviewSlotTextNode) | (ComponentPreviewSlotHtmlNode) | (ComponentPreviewSlotComponentNode)

export type ComponentPreviewSlotTextNode = {
  "type": "text"
  "value": string
  [key: string]: unknown
}
