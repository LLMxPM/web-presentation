// 文件功能：首次生成的固定 GSAP 故事，声明资源依赖并追加标题、卡片与媒体说明入场。
<script setup lang="ts">
import { ref } from 'vue'
import { BenchStage, seconds, useGsapStory } from '../sdk'
import type { StoryProps } from '../sdk'

const props = defineProps<StoryProps>()
const stage = ref<InstanceType<typeof BenchStage>>()

/** 声明固定资源依赖，并在适配层提供的时间轴上追加线性视觉变化。 */
const controls = useGsapStory(stage, props, context => {
  const clip = context.assets.clip
  const plan = context.resources()
    .voice('voice')
    .clip('model', {
      index: clip.index,
      signature: props.badClip ? 'stale' : clip.signature,
    }, { atMs: props.detailStartMs ?? 1200 })
    .video('demo', { inMs: 1000, outMs: 3000 }, { after: 'model', offsetMs: 200 })
    .build()

  return {
    plan,
    visual(timeline) {
      timeline.fromTo('.title',
        { opacity: 0, y: 32 },
        { opacity: 1, y: 0, duration: seconds(400), ease: 'none' },
        0,
      )
      timeline.fromTo('.card',
        { opacity: 0, y: 24 },
        { opacity: 1, y: 0, duration: seconds(300), stagger: seconds(100), ease: 'none' },
        seconds(600),
      )
      timeline.fromTo('.clip-caption',
        { opacity: 0 },
        { opacity: 1, duration: seconds(400), ease: 'none' },
        'model',
      )
      timeline.fromTo('.demo-caption',
        { opacity: 0, y: 32 },
        { opacity: 1, y: 0, duration: seconds(400), ease: 'none' },
        'demo',
      )
    },
  }
})

defineExpose(controls)
</script>

<template>
  <BenchStage ref="stage" />
</template>