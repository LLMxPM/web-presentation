<!-- 文件功能：Anime.js v4 原生 Vue SFC 编排样例，使用 scope、毫秒标签及子时间轴同步。 -->
<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { createScope, createTimeline, stagger } from 'animejs'

const props = withDefaults(defineProps<{ detailStartMs?: number }>(), { detailStartMs: 900 })
const root = ref<HTMLElement | null>(null)
const modelClock = reactive({ timeMs: 0 })
let timeline: ReturnType<typeof createTimeline> | undefined
let scope: ReturnType<typeof createScope> | undefined

onMounted(() => {
  scope = createScope({ root: root.value! }).add(() => {
    const detail = createTimeline({ autoplay: false })
      .add(modelClock, { timeMs: [0, 2000], duration: 2000, ease: 'linear' })
      .add('.demo', { opacity: [0, 1], duration: 300, ease: 'linear' }, '+=200')
      .init()
    timeline = createTimeline({ autoplay: false })
      .add('.title', { opacity: [0, 1], y: [32, 0], duration: 400, ease: 'linear' }, 0)
      .add('.card', { opacity: [0, 1], y: [24, 0], duration: 300, delay: stagger(100), ease: 'linear' }, 600)
      .label('detail', props.detailStartMs)
      .sync(detail, 'detail')
      .init()
  })
})

/** 定位整条时间轴并静默回调，不用手工分别定位各元素。 */
function sample(ms: number) { timeline?.pause().seek(ms, true) }
/** 恢复本作用域产生的动画和样式，适配 Vue 卸载。 */
function dispose() { scope?.revert() }
onBeforeUnmount(dispose)
defineExpose({ sample, dispose, play: () => timeline?.play(), modelMs: () => modelClock.timeMs, durationMs: () => timeline?.duration ?? 0 })
</script>

<template>
  <section ref="root" class="scene">
    <h1 class="title">产品演示</h1>
    <div class="cards"><div v-for="i in 3" :key="i" class="card">卡片 {{ i }}</div></div>
    <p>模型时间代理：{{ Math.round(modelClock.timeMs) }}ms</p>
    <div class="demo">动作之后出现的演示</div>
  </section>
</template>
