// 文件功能：让候选只写资源依赖与 GSAP 视觉填充，底层生命周期由固定研究适配层拥有。
import type { Ref } from 'vue'
import BenchStage from '../motion-luna/BenchStage.vue'
import { useStory } from '../motion-story/use-story'
import { resourcePlan } from './resource-plan'
import { createVisual } from './visual'
import type { AuthorContext, StoryDefinition, StoryProps } from './api-types'
export { BenchStage }
export { seconds } from './visual'
export type { AuthorContext, StoryDefinition, StoryProps } from './api-types'

/** 不向作者传递内部 Assets；原生媒体/Mixer 的所有权始终保留在资源桥接。 */
export function useGsapStory(stage: Ref<InstanceType<typeof BenchStage> | undefined>, props: StoryProps,
  factory: (context: AuthorContext) => StoryDefinition) {
  return useStory(stage, props, internal => {
    const assets = Object.freeze({ clip: Object.freeze({ ...internal.clip }), voiceDurationMs: internal.voiceDurationMs, videoDurationMs: internal.videoDurationMs })
    const context: AuthorContext = Object.freeze({ root: internal.elements.root, assets, resources: () => resourcePlan(assets) })
    const definition = factory(context)
    return { plan: definition.plan, visual: createVisual(context.root, definition.plan, definition.visual) }
  })
}
