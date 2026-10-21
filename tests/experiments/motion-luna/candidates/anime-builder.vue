<!-- 文件功能：Anime.js builder 路线的 Luna 故事编排候选，桥接资源计划与可采样 DOM 动画。 -->
<script setup lang="ts">
import { ref } from 'vue'
import { createScope, createTimeline } from 'animejs'
import { BenchStage, storyBuilder, useStory, type Assets, type Plan, type StoryProps, type Visual } from '../sdk'

const props = defineProps<StoryProps>()
const stage = ref<InstanceType<typeof BenchStage>>()

/** 用资源依赖计划生成轨道，并将其时间点映射到本实例的 Anime.js 时间轴。 */
function createStory(assets: Assets): { plan: Plan; visual: Visual } {
  const detailStartMs = props.detailStartMs ?? 1700
  const clipRef = {
    index: assets.clip.index,
    signature: props.badClip ? 'stale' : assets.clip.signature,
  }
  const plan = storyBuilder(assets)
    .voice('voice')
    .clip('model', clipRef, { atMs: detailStartMs })
    .video('demo', { inMs: 1000, outMs: 3000 }, { after: 'model', offsetMs: 200 })
    .build()

  const root = assets.elements.root
  const scope = createScope({ root })
  let timeline: ReturnType<typeof createTimeline> | undefined
  const originalStyles = new Map<HTMLElement, { opacity: string; transform: string }>()

  /** 保存动画属性原值并立即落下各轨道初态，确保首次零点采样可见。 */
  function setInitial(element: HTMLElement, opacity: number, y: number): void {
    originalStyles.set(element, { opacity: element.style.opacity, transform: element.style.transform })
    element.style.opacity = String(opacity)
    element.style.transform = `translateY(${y}px)`
  }

  scope.add(() => {
    const title = root.querySelector<HTMLElement>('.title')
    const cards = root.querySelectorAll<HTMLElement>('.card')
    const clipCaption = root.querySelector<HTMLElement>('.clip-caption')
    const demoCaption = root.querySelector<HTMLElement>('.demo-caption')
    const modelStartMs = plan.get('model').startMs
    const demoStartMs = plan.get('demo').startMs

    if (title) setInitial(title, 0, 32)
    cards.forEach(card => setInitial(card, 0, 24))
    if (clipCaption) setInitial(clipCaption, 0, 0)
    if (demoCaption) setInitial(demoCaption, 0, 32)

    timeline = createTimeline({ autoplay: false })
    /** 为一组 chip 注册相同的错峰入场效果，并先设置采样前初态。 */
    function addChipEntrance(selector: string, startMs: number): void {
      root.querySelectorAll<HTMLElement>(selector).forEach((chip, index) => {
        setInitial(chip, 0, 12)
        timeline!.add(chip, { opacity: [0, 1], y: [12, 0], duration: 200, ease: 'linear' }, startMs + index * 80)
      })
    }

    if (title) timeline.add(title, { opacity: [0, 1], y: [32, 0], duration: 400, ease: 'linear' }, 0)
    cards.forEach((card, index) => {
      timeline!.add(card, { opacity: [0, 1], y: [24, 0], duration: 300, ease: 'linear' }, 600 + index * 100)
    })
    if (clipCaption) timeline.add(clipCaption, { opacity: [0, 1], duration: 400, ease: 'linear' }, modelStartMs)
    if (demoCaption) timeline.add(demoCaption, { opacity: [0, 1], y: [32, 0], duration: 400, ease: 'linear' }, demoStartMs)
    addChipEntrance('.callout-model .chip', modelStartMs + 100)
    addChipEntrance('.callout-demo .chip', demoStartMs + 100)
  })

  /** 按绝对毫秒定位时间轴，避免依赖调用顺序或触发业务回调。 */
  function sample(ms: number): void {
    timeline?.pause()
    timeline?.seek(ms, true)
  }

  /** 停止原生时间轴并保留当前已采样的可见状态。 */
  function freeze(): void {
    timeline?.pause()
  }

  /** 撤销作用域内的动画并恢复 Anime.js 改动的元素样式。 */
  function dispose(): void {
    timeline?.pause()
    scope.revert()
    originalStyles.forEach((style, element) => {
      element.style.opacity = style.opacity
      element.style.transform = style.transform
    })
  }

  return { plan, visual: { sample, freeze, dispose } }
}

const story = useStory(stage, props, createStory)
defineExpose(story)
</script>

<template>
  <BenchStage ref="stage" />
</template>
