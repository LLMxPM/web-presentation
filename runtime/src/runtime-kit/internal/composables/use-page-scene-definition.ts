/** 文件功能：为公开页级 Scene 入口绑定 Vue 页面寿命，保持登记与实际播放准备分离。 */
import { onBeforeUnmount, onMounted, toValue, type MaybeRefOrGetter } from 'vue'
import { notifyPageSceneDefinitions, registerPageSceneDefinition, type PageSceneDefinition } from '@/core/scene/page-scene-definition'

export interface UsePageSceneDefinitionOptions extends Omit<PageSceneDefinition, 'root'> {
  root: MaybeRefOrGetter<HTMLElement | null | undefined>
}

/** setup 只登记声明；define 由放映或用户显式预览的 prepare 执行，卸载立即中止绑定会话。 */
export function usePageSceneDefinition(options: UsePageSceneDefinitionOptions): void {
  const unregister = registerPageSceneDefinition({ root: () => toValue(options.root), define: options.define })
  onMounted(notifyPageSceneDefinitions)
  onBeforeUnmount(unregister)
}
