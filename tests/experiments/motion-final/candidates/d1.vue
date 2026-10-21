<!-- 文件功能：定义固定 GSAP 故事的资源依赖与页面原生视觉动画。 -->
<script setup lang="ts">
import { ref } from 'vue'
import { BenchStage, seconds, useGsapStory } from '../sdk'
import type { StoryProps } from '../sdk'

const props = defineProps<StoryProps>()
const stage = ref<InstanceType<typeof BenchStage>>()

/** 声明资源时间关系，并在适配层提供的时间轴上追加页面入场动画。 */
const controls = useGsapStory(stage, props, context => {
  const modelStartMs = props.detailStartMs ?? 1200
  const plan = context.resources()
    .voice('voice')
    .clip('model', {
      index: context.assets.clip.index,
      signature: props.badClip ? 'stale' : context.assets.clip.signature,
    }, { atMs: modelStartMs })
    .video('demo', { inMs: 1000, outMs: 3000 }, { after: 'model', offsetMs: 200 })
    .build()

  return {
    plan,
    visual(timeline) {
      timeline.fromTo('.title',
        { opacity: 0, y: 32 },
        { opacity: 1, y: 0, duration: seconds(400), ease: 'none', immediateRender: false },
        seconds(0))
      timeline.fromTo('.card',
        { opacity: 0, y: 24 },
        { opacity: 1, y: 0, duration: seconds(300), stagger: seconds(100), ease: 'none', immediateRender: false },
        seconds(600))
      timeline.fromTo('.clip-caption',
        { opacity: 0 },
        { opacity: 1, duration: seconds(400), ease: 'none', immediateRender: false },
        'model')
      timeline.fromTo('.demo-caption',
        { opacity: 0, y: 32 },
        { opacity: 1, y: 0, duration: seconds(400), ease: 'none', immediateRender: false },
        'demo')
    },
  }
})

defineExpose(controls)
</script>

<template>
  <BenchStage ref="stage" />
</template>
