<!-- 文件功能：使用 Anime.js 原生时间轴和 native 资源计划呈现 Luna 评测故事。 -->
<script setup lang="ts">
import { ref } from 'vue'
import { createScope, createTimeline } from 'animejs'
import { BenchStage, compile, useStory } from '../sdk'
import type { Assets, Draft, Plan, StoryProps, Visual } from '../sdk'

const props = defineProps<StoryProps>()
const stage = ref<InstanceType<typeof BenchStage>>()

/** 根据已解析的媒体信息构建资源轨道，并将插入点映射到原生视觉时间轴。 */
function createStory(assets: Assets): { plan: Plan; visual: Visual } {
  const actionStartMs = props.detailStartMs ?? 1200
  const clipRef = {
    index: assets.clip.index,
    signature: props.badClip ? 'stale' : assets.clip.signature,
  }
  const drafts: Draft[] = [
    { id: 'voice', type: 'voice', target: 'voice', start: { atMs: 0 } },
    { id: 'model', type: 'clip', target: 'model', start: { atMs: actionStartMs }, clipRef },
    {
      id: 'demo', type: 'video', target: 'video',
      start: { atMs: actionStartMs + assets.clip.durationMs + 200 }, inMs: 1000, outMs: 3000,
    },
  ]
  const plan = compile(assets, drafts)
  const root = assets.elements.root
  const title = root.querySelector<HTMLElement>('.title')
  const cards = [...root.querySelectorAll<HTMLElement>('.card')]
  const clipCaption = root.querySelector<HTMLElement>('.clip-caption')
  const demoCaption = root.querySelector<HTMLElement>('.demo-caption')
  if (!title || cards.length !== 3 || !clipCaption || !demoCaption) {
    throw new Error('故事视觉目标缺失')
  }

  let timeline = createTimeline({ autoplay: false })
  const scope = createScope({ root }).add(() => {
    timeline = createTimeline({ autoplay: false })
    timeline.add(title, {
      opacity: [0, 1], y: [32, 0], duration: 400, ease: 'linear',
    }, 0)
    cards.forEach((card, index) => {
      timeline.add(card, {
        opacity: [0, 1], y: [24, 0], duration: 300, ease: 'linear',
      }, 600 + index * 100)
    })
    timeline.add(clipCaption, {
      opacity: [0, 1], duration: 400, ease: 'linear',
    }, plan.get('model').startMs)
    timeline.add(demoCaption, {
      opacity: [0, 1], y: [32, 0], duration: 400, ease: 'linear',
    }, plan.get('demo').startMs)
  })
  return {
    plan,
    visual: {
      /** 按绝对毫秒定位，避免依赖上一次采样位置。 */
      sample(ms: number) { timeline.seek(ms) },
      /** 暂停时间轴并保留当前可见帧。 */
      freeze() { timeline.pause() },
      /** 撤销 Anime.js 对本实例作用域的全部修改。 */
      dispose() { scope.revert() },
    },
  }
}

const story = useStory(stage, props, createStory)
defineExpose(story)
</script>

<template>
  <BenchStage ref="stage" />
</template>
