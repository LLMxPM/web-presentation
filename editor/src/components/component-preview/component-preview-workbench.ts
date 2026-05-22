/**
 * 文件功能：定义组件预览右侧工作台的来源类型，区分工作空间草稿和 Runtime Kit 只读能力。
 */
import type { RuntimeKitComponentCapabilityItem, WorkspaceComponentType } from '@/types/api'

export type ComponentPreviewWorkbenchSource =
  | {
    kind: 'workspace-draft'
    workspaceId: number | null
    componentId: number | null
    componentName: string
    content: string
    previewSchema: string | null
    isDraftPreview: boolean
    componentType?: WorkspaceComponentType | null
  }
  | {
    kind: 'runtime-kit'
    workspaceId: number | null
    item: RuntimeKitComponentCapabilityItem
  }
