/**
 * 文件功能：在后台布局与业务页面之间共享全局智能体侧栏展开状态。
 */
import type { InjectionKey, Ref } from 'vue'
import { computed, inject } from 'vue'

export const agentSidebarExpandedKey: InjectionKey<Ref<boolean>> = Symbol('agentSidebarExpanded')

/**
 * 读取全局智能体侧栏是否展开；未处于后台布局时默认视为收起。
 * @returns 只读计算值，true 表示智能体对话面板已打开
 */
export function useAgentSidebarExpanded() {
  const injected = inject(agentSidebarExpandedKey, null)
  return computed(() => injected?.value ?? false)
}
