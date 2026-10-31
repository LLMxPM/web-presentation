/** 文件功能：联合样例的模型与旁白编排，依赖真实句柄片段，不猜索引/签名，不预估媒体完成。 */
import type { ModelSceneHandle } from '@runtime-kit/public/components/assets/AssetModel.v1.vue'
import type { PageSceneAuthoringContext } from '@runtime-kit/public/composables/motion/usePageScene.v1'
import { createSceneMediaTask } from '@runtime-kit/public/composables/media/createSceneMediaTask.v1'

/** 在同一 Scene 中添加两个顺序模型动作、实际 ended 的旁白与可选交互 cue；视觉序列由调用者登记。 */
export function defineModelNarration(scene: PageSceneAuthoringContext, model: ModelSceneHandle | null, narration: HTMLMediaElement | null,
  playCue: (key: string) => Promise<unknown>): void {
  if (!model?.isReady()) throw new Error('联合样例需要已完成首帧的真实模型。')
  const clips = model.animations().filter(clip => clip.signature && clip.durationMs > 0)
  if (clips.length < 2) throw new Error('联合样例需要至少两个真实、已签名的模型动作，请重新查询资源详情。')
  scene.onCleanup(model.reset)
  scene.task(model.animation({ id: 'model-first', role: 'blocking', clipIndex: clips[0].index, signature: clips[0].signature! }))
  scene.task(model.animation({ id: 'model-second', role: 'blocking', clipIndex: clips[1].index, signature: clips[1].signature!, afterTrack: 'model-first', offsetMs: 100 }))
  scene.task(createSceneMediaTask({ id: 'narration', role: 'blocking', target: () => narration }))
  scene.task({ id: 'finish-cue', role: 'ambient', afterTrack: 'model-second', async run() { await playCue('interaction.scene-finished') } })
}
