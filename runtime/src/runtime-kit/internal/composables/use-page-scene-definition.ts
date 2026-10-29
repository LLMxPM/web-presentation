/** 文件功能：将页级 Scene 声明绑定到 Vue 页面寿命；公开入口切换前只供内部开发接线使用。 */
import { onBeforeUnmount, toValue, type MaybeRefOrGetter } from 'vue'
import { registerPageSceneDefinition, type PageSceneDefinition } from '@/core/scene/page-scene-definition'

export interface UsePageSceneDefinitionOptions extends Omit<PageSceneDefinition, 'root'> {
  root: MaybeRefOrGetter<HTMLElement | null | undefined>
}

/** setup 只登记声明；define 由放映或用户显式预览的 prepare 执行，卸载立即中止绑定会话。 */
export function usePageSceneDefinition(options: UsePageSceneDefinitionOptions): void {
  const unregister = registerPageSceneDefinition({ root: () => toValue(options.root), define: options.define })
  onBeforeUnmount(unregister)
}
