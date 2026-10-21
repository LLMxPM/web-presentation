<!-- 文件功能：GSAP 原生视觉轨道与共享资源计划的 Luna 首轮候选实现。 -->
<script setup lang="ts">
import { ref } from 'vue'
import { gsap } from 'gsap'
import { BenchStage, compile, useStory } from '../sdk'
import type { Assets, Draft, StoryProps, Visual } from '../sdk'

const props = defineProps<StoryProps>()
const stage = ref<InstanceType<typeof BenchStage>>()

/** 根据已查询的真实资源构建资源计划和绝对时间采样的 GSAP 视觉。 */
function createStory(assets: Assets) {
  const detailStartMs = props.detailStartMs ?? 1700
  const clipRef = {
    index: assets.clip.index,
    signature: props.badClip ? 'stale' : assets.clip.signature,
  }
  const videoStartMs = detailStartMs + assets.clip.durationMs + 200
  const drafts: Draft[] = [
    { id: 'voice', type: 'voice', target: 'voice', start: { atMs: 0 } },
    { id: 'model', type: 'clip', target: 'model', clipRef, start: { atMs: detailStartMs } },
    { id: 'demo', type: 'video', target: 'video', start: { atMs: videoStartMs }, inMs: 1000, outMs: 3000 },
  ]
  const plan = compile(assets, drafts)
  const scope = assets.elements.root
  const timeline = gsap.timeline({ paused: true, defaults: { ease: 'none' } })
  /** 向同一绝对时间轴追加一组错峰入场的 chip 动画。 */
  function appendCalloutEntrance(selector: string, startMs: number) {
    timeline.fromTo(selector, { opacity: 0, y: 12 }, {
      opacity: 1,
      y: 0,
      duration: 0.2,
      stagger: 0.08,
      ease: 'none',
    }, startMs / 1000)
  }
  const context = gsap.context(() => {
    timeline.fromTo('.title', { opacity: 0, y: 32 }, { opacity: 1, y: 0, duration: 0.4 }, 0)
    timeline.fromTo('.card', { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.3, stagger: 0.1 }, 0.6)
    timeline.fromTo('.clip-caption', { opacity: 0 }, { opacity: 1, duration: 0.4 }, detailStartMs / 1000)
    timeline.fromTo('.demo-caption', { opacity: 0, y: 32 }, { opacity: 1, y: 0, duration: 0.4 }, videoStartMs / 1000)
    appendCalloutEntrance('.callout-model .chip', plan.get('model').startMs + 100)
    appendCalloutEntrance('.callout-demo .chip', plan.get('demo').startMs + 100)
  }, scope)

  const visual: Visual = {
    /** 将传输层绝对毫秒映射到 GSAP 时间线，并抑制定位过程中的回调。 */
    sample(ms: number) {
      timeline.time(Math.max(0, ms) / 1000, true)
    },
    /** 暂停时间线并保留当前已采样的可见样式。 */
    freeze() {
      timeline.pause()
    },
    /** 撤销 GSAP 对作用域的修改，并释放时间线。 */
    dispose() {
      timeline.kill()
      context.revert()
    },
  }
  return { plan, visual }
}

const controller = useStory(stage, props, createStory)
defineExpose(controller)
</script>

<template>
  <BenchStage ref="stage" />
</template>
