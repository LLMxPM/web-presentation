<!-- 文件功能：评分前验证适配层自身的参考页，不作为 Luna 候选或生成成功样本。 -->
<script setup lang="ts">
import { ref } from 'vue'
import { BenchStage, useGsapStory, seconds, type StoryProps } from './sdk'
const props = defineProps<StoryProps>(), stage = ref<InstanceType<typeof BenchStage>>()
const story = useGsapStory(stage, props, ctx => {
  const clip = { index: ctx.assets.clip.index, signature: props.badClip ? 'stale' : ctx.assets.clip.signature }
  const plan = ctx.resources().voice('voice').clip('model', clip, { atMs: props.detailStartMs ?? 1200 })
    .video('demo', { inMs: 1000, outMs: 3000 }, { after: 'model', offsetMs: 200 }).build()
  return { plan, visual(timeline) {
    timeline.fromTo('.title', { opacity: 0, y: 32 }, { opacity: 1, y: 0, duration: seconds(400), immediateRender: false }, 0)
      .fromTo('.card', { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: seconds(300), stagger: seconds(100), immediateRender: false }, seconds(600))
      .fromTo('.clip-caption', { opacity: 0 }, { opacity: 1, duration: seconds(400), immediateRender: false }, 'model')
      .fromTo('.demo-caption', { opacity: 0, y: 32 }, { opacity: 1, y: 0, duration: seconds(400), immediateRender: false }, 'demo')
  } }
})
defineExpose(story)
</script>
<template><BenchStage ref="stage" /></template>
