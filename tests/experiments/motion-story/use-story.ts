// 文件功能：共享 SFC 生命周期样板，所有研究路线接受同一资源准备与卸载约束。
import { onBeforeUnmount, onMounted, ref, type Ref } from 'vue'
import StoryStage from './StoryStage.vue'
import { loadAssets } from './assets'
import { createSession, type Session } from './session'
import type { Assets, Plan, StoryProps, Visual } from './types'

/** mounted 后查询资源再创建定义；准备期间卸载的结果只释放，不能发布旧 session。 */
export function useStory(stage: Ref<InstanceType<typeof StoryStage> | undefined>, props: StoryProps,
  factory: (assets: Assets) => { plan: Plan; visual: Visual }) {
  const ready = ref(false), error = ref<{ code: string; fieldPath: string; message: string } | null>(null)
  let cancelled = false, session: Session | undefined
  onMounted(async () => {
    let assets: Assets | undefined
    try {
      assets = await loadAssets(stage.value!.elements(), props)
      if (cancelled) { assets.dispose(); return }
      const { plan, visual } = factory(assets)
      session = createSession(assets, plan, visual)
      await session.sample(0)
      if (!cancelled) ready.value = true
    } catch (cause) {
      session ? session.dispose() : assets?.dispose()
      const failure = cause as Error & { code?: string; fieldPath?: string }
      if (!cancelled) error.value = { code: failure.code ?? 'PREPARE_FAILED', fieldPath: failure.fieldPath ?? '', message: failure.message }
    }
  })
  onBeforeUnmount(() => { cancelled = true; session?.dispose() })
  return {
    ready, error,
    sample: (ms: number) => session!.sample(ms), play: () => session!.play(), pause: () => session!.pause(),
    freeze: () => session!.freeze(), dispose: () => session?.dispose(), state: () => session!.state(),
  }
}
