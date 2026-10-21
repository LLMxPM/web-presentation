<!-- 文件功能：GSAP 原生子时间轴加显式资源桥接的完整 SFC 对照。 -->
<script setup lang="ts">
import { ref } from 'vue'
import { gsap } from 'gsap'
import StoryStage from './StoryStage.vue'
import { useStory } from './use-story'
import { compile } from './plan'
const props = defineProps<{ detailStartMs?: number; modelFile?: string; badClip?: boolean }>()
const stage = ref<InstanceType<typeof StoryStage>>()
const story = useStory(stage, props, assets => {
  const detailMs = props.detailStartMs ?? 1200
  const clipRef = { index: assets.clip.index, signature: props.badClip ? 'stale' : assets.clip.signature }
  // 原生桥接作者显式映射资源时长与视觉插入点；不在 .call 中播放媒体。
  const demoMs = detailMs + assets.clip.durationMs + 200
  const plan = compile(assets, [
    { id: 'voice', type: 'voice', target: 'voice', start: { atMs: 0 } },
    { id: 'model', type: 'clip', target: 'model', clipRef, start: { atMs: detailMs } },
    { id: 'demo', type: 'video', target: 'video', inMs: 1000, outMs: 3000, start: { atMs: demoMs } },
  ])
  let timeline: gsap.core.Timeline
  const context = gsap.context(() => {
    const intro = gsap.timeline()
      .fromTo('.title', { opacity: 0, y: 32 }, { opacity: 1, y: 0, duration: 0.4, ease: 'none' })
      .fromTo('.card', { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.3, stagger: 0.1, ease: 'none' }, 0.6)
    timeline = gsap.timeline({ paused: true }).add(intro, 0).addLabel('detail', detailMs / 1000).addLabel('demo', demoMs / 1000)
      .fromTo('.clip-caption', { opacity: 0 }, { opacity: 1, duration: 0.4, ease: 'none' }, 'detail')
      .fromTo('.demo-caption', { opacity: 0, y: 32 }, { opacity: 1, y: 0, duration: 0.4, ease: 'none' }, 'demo')
  }, assets.elements.root)
  return { plan, visual: { sample: ms => { timeline!.totalTime(ms / 1000, true) }, freeze: () => { timeline!.kill() }, dispose: () => context.revert() } }
})
defineExpose(story)
</script>
<template><StoryStage ref="stage" /></template>
