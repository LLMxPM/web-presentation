<!-- 文件功能：使用 GSAP 原生时间轴编排 builder 资源计划对应的独立视觉效果。 -->
<script setup lang="ts">
import { ref } from 'vue'
import { gsap } from 'gsap'
import { BenchStage, storyBuilder, useStory } from '../sdk'
import type { Assets, Plan, StoryProps, Visual } from '../sdk'

const props = defineProps<StoryProps>()
const stage = ref<InstanceType<typeof BenchStage>>()

/** 根据实际资源建立语音、动作和裁切视频的依赖计划。 */
function createPlan(assets: Assets): Plan {
  const detailStartMs = props.detailStartMs ?? 1700
  const clipRef = {
    index: assets.clip.index,
    signature: props.badClip ? 'stale' : assets.clip.signature,
  }

  return storyBuilder(assets)
    .voice('voice')
    .clip('model', clipRef, { atMs: detailStartMs })
    .video('demo', { inMs: 1000, outMs: 3000 }, { after: 'model', offsetMs: 200 })
    .build()
}

/** 用原生 GSAP 时间轴定义视觉效果，并提供可绝对定位的控制接口。 */
function createVisual(assets: Assets, plan: Plan): Visual {
  const root = assets.elements.root
  const timeline = gsap.timeline({ paused: true })
  const context = gsap.context(() => {
    const title = root.querySelector('.title')
    const cards = root.querySelectorAll('.card')
    const clipCaption = root.querySelector('.clip-caption')
    const demoCaption = root.querySelector('.demo-caption')

    // 显式设置时间轴零点状态，确保首次采样及动画开始前都呈现初态。
    gsap.set(title, { opacity: 0, y: 32 })
    gsap.set(cards, { opacity: 0, y: 24 })
    gsap.set(clipCaption, { opacity: 0 })
    gsap.set(demoCaption, { opacity: 0, y: 32 })

    /** 为指定 callout 组设置初态并追加错峰入场动画。 */
    function addCalloutEntrance(selector: string, startMs: number): void {
      const chips = root.querySelectorAll(selector)
      gsap.set(chips, { opacity: 0, y: 12 })
      timeline.to(chips,
        { opacity: 1, y: 0, duration: 0.2, stagger: 0.08, ease: 'none' },
        startMs / 1000,
      )
    }

    timeline.to(title,
      { opacity: 1, y: 0, duration: 0.4, ease: 'none' },
      0,
    )
    timeline.to(cards,
      { opacity: 1, y: 0, duration: 0.3, stagger: 0.1, ease: 'none' },
      0.6,
    )
    timeline.to(clipCaption,
      { opacity: 1, duration: 0.4, ease: 'none' },
      plan.get('model').startMs / 1000,
    )
    timeline.to(demoCaption,
      { opacity: 1, y: 0, duration: 0.4, ease: 'none' },
      plan.get('demo').startMs / 1000,
    )
    addCalloutEntrance('.callout-model .chip', plan.get('model').startMs + 100)
    addCalloutEntrance('.callout-demo .chip', plan.get('demo').startMs + 100)
  }, root)

  /** 将任意毫秒时间定位到同一条暂停时间轴，不触发业务回调。 */
  function sample(ms: number): void {
    timeline.totalTime(Math.max(0, ms) / 1000, true)
  }

  /** 暂停原生动画并保留当前画面样式。 */
  function freeze(): void {
    timeline.pause()
  }

  /** 销毁时间轴并恢复本实例作用域内的 GSAP 样式。 */
  function dispose(): void {
    timeline.kill()
    context.revert()
  }

  return { sample, freeze, dispose }
}

const controller = useStory(stage, props, (assets) => {
  const plan = createPlan(assets)
  return { plan, visual: createVisual(assets, plan) }
})

defineExpose(controller)
</script>

<template>
  <BenchStage ref="stage" />
</template>
