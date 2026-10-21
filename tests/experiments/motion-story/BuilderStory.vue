<!-- 文件功能：有限资源 builder 表达依赖，DOM 继续使用候选库原生段落的 SFC 对照。 -->
<script setup lang="ts">
import { ref } from 'vue'
import StoryStage from './StoryStage.vue'
import { useStory } from './use-story'
import { storyBuilder } from './plan'
import { nativeVisual } from './visuals'
import type { Engine } from './types'
const props = defineProps<{ engine: Engine; detailStartMs?: number; modelFile?: string; badClip?: boolean }>()
const stage = ref<InstanceType<typeof StoryStage>>()
const story = useStory(stage, props, assets => {
  const clipRef = { index: assets.clip.index, signature: props.badClip ? 'stale' : assets.clip.signature }
  const plan = storyBuilder(assets).voice('voice')
    .clip('model', clipRef, { atMs: props.detailStartMs ?? 1200 })
    .video('demo', { inMs: 1000, outMs: 3000 }, { after: 'model', offsetMs: 200 }).build()
  return { plan, visual: nativeVisual(props.engine, assets.elements.root, plan.get('model').startMs, plan.get('demo').startMs) }
})
defineExpose(story)
</script>
<template><StoryStage ref="stage" /></template>
