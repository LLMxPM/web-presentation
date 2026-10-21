<!-- 文件功能：Anime.js 原生 sync 段落加显式资源桥接的完整 SFC 对照。 -->
<script setup lang="ts">
import { ref } from 'vue'
import { createScope, createTimeline, stagger } from 'animejs'
import StoryStage from './StoryStage.vue'
import { useStory } from './use-story'
import { compile } from './plan'
const props = defineProps<{ detailStartMs?: number; modelFile?: string; badClip?: boolean }>()
const stage = ref<InstanceType<typeof StoryStage>>()
const story = useStory(stage, props, assets => {
  const detailMs = props.detailStartMs ?? 1200
  const clipRef = { index: assets.clip.index, signature: props.badClip ? 'stale' : assets.clip.signature }
  const demoMs = detailMs + assets.clip.durationMs + 200
  const plan = compile(assets, [
    { id: 'voice', type: 'voice', target: 'voice', start: { atMs: 0 } },
    { id: 'model', type: 'clip', target: 'model', clipRef, start: { atMs: detailMs } },
    { id: 'demo', type: 'video', target: 'video', inMs: 1000, outMs: 3000, start: { atMs: demoMs } },
  ])
  let timeline: ReturnType<typeof createTimeline>, intro: ReturnType<typeof createTimeline>
  const scope = createScope({ root: assets.elements.root }).add(() => {
    intro = createTimeline({ autoplay: false })
      .add('.title', { opacity: [0, 1], y: [32, 0], duration: 400, ease: 'linear' })
      .add('.card', { opacity: [0, 1], y: [24, 0], duration: 300, delay: stagger(100), ease: 'linear' }, 600).init()
    timeline = createTimeline({ autoplay: false }).sync(intro, 0).label('detail', detailMs).label('demo', demoMs)
      .add('.clip-caption', { opacity: [0, 1], duration: 400, ease: 'linear' }, 'detail')
      .add('.demo-caption', { opacity: [0, 1], y: [32, 0], duration: 400, ease: 'linear' }, 'demo').init()
  })
  return { plan, visual: { sample: ms => { timeline!.seek(ms, true) }, freeze: () => { timeline!.cancel(); intro!.cancel() }, dispose: () => scope.revert() } }
})
defineExpose(story)
</script>
<template><StoryStage ref="stage" /></template>
