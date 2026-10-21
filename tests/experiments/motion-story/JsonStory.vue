<!-- 文件功能：原 JSON tracks 草案的有限对照，显式列出各个 DOM enter 与资源依赖。 -->
<script setup lang="ts">
import { ref } from 'vue'
import StoryStage from './StoryStage.vue'
import { useStory } from './use-story'
import { compile } from './plan'
import { jsonVisual } from './visuals'
import type { Engine } from './types'
const props = defineProps<{ engine: Engine; detailStartMs?: number; modelFile?: string; badClip?: boolean }>()
const stage = ref<InstanceType<typeof StoryStage>>()
const story = useStory(stage, props, assets => {
  const clipRef = { index: assets.clip.index, signature: props.badClip ? 'stale' : assets.clip.signature }
  const plan = compile(assets, [
    { id: 'voice', type: 'voice', target: 'voice', start: { atMs: 0 } },
    { id: 'title', type: 'enter', target: 'title', durationMs: 400, fromY: 32, start: { atMs: 0 } },
    { id: 'card1', type: 'enter', target: 'card1', durationMs: 300, fromY: 24, start: { atMs: 600 } },
    { id: 'card2', type: 'enter', target: 'card2', durationMs: 300, fromY: 24, start: { atMs: 700 } },
    { id: 'card3', type: 'enter', target: 'card3', durationMs: 300, fromY: 24, start: { atMs: 800 } },
    { id: 'model', type: 'clip', target: 'model', clipRef, start: { atLabel: 'detail' } },
    { id: 'clip-caption', type: 'enter', target: 'clip-caption', durationMs: 400, start: { atLabel: 'detail' } },
    { id: 'demo', type: 'video', target: 'video', inMs: 1000, outMs: 3000, start: { after: 'model', offsetMs: 200 } },
    { id: 'demo-caption', type: 'enter', target: 'demo-caption', durationMs: 400, fromY: 32, start: { after: 'model', offsetMs: 200 } },
  ], { detail: props.detailStartMs ?? 1200 })
  return { plan, visual: jsonVisual(props.engine, assets.elements.root, plan) }
})
defineExpose(story)
</script>
<template><StoryStage ref="stage" /></template>
