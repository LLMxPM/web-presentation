/**
 * 文件功能：在组件库页面与全局智能体侧栏之间共享当前组件上下文。
 */
import type { InjectionKey, Ref } from 'vue'

import type { WorkspaceComponentItem } from '@/types/api'

export interface ComponentAgentContextBridge {
  selectedComponent: Ref<WorkspaceComponentItem | null>
  setSelectedComponent: (component: WorkspaceComponentItem | null) => void
}

export const componentAgentContextKey: InjectionKey<ComponentAgentContextBridge> = Symbol('componentAgentContext')
