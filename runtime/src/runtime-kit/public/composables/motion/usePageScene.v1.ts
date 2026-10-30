/** 文件功能：公开页级正向 Scene 声明入口，挂载只登记，由播放宿主或开发调试入口准备和启动。 */
import { usePageSceneDefinition, type UsePageSceneDefinitionOptions } from '@/runtime-kit/internal/composables/use-page-scene-definition'

export type UsePageSceneOptions = UsePageSceneDefinitionOptions
export type { PageSceneAuthoringContext } from '@/core/scene/page-scene-definition'
export type { SceneTask, SceneTaskContext, SceneTaskRole } from '@/core/scene/types'
export type { SceneVisualOptions, SceneVisualTimeline } from '@/core/scene/visual-types'

/** 每页声明一次，多条视觉和异步任务在 define 内登记；静态呈现使用同根的独立声明。 */
export function usePageScene(options: UsePageSceneOptions): void {
  usePageSceneDefinition(options)
}
