<!-- 文件功能：GSAP 原生 Vue SFC 编排样例，使用标签、子段落和对象轨道验证局部修改。 -->
<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { gsap } from 'gsap'

const props = withDefaults(defineProps<{ detailStartMs?: number }>(), { detailStartMs: 900 })
const root = ref<HTMLElement | null>(null)
const modelClock = reactive({ timeMs: 0 })
let timeline: gsap.core.Timeline | undefined
let context: gsap.Context | undefined

onMounted(() => {
  context = gsap.context(() => {
    const detail = gsap.timeline()
      .fromTo(modelClock, { timeMs: 0 }, { timeMs: 2000, duration: 2, ease: 'none' })
      .fromTo('.demo', { opacity: 0 }, { opacity: 1, duration: 0.3, ease: 'none' }, '+=0.2')
    timeline = gsap.timeline({ paused: true })
      .fromTo('.title', { opacity: 0, y: 32 }, { opacity: 1, y: 0, duration: 0.4, ease: 'none' }, 0)
      .fromTo('.card', { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.3, stagger: 0.1, ease: 'none' }, 0.6)
      .addLabel('detail', props.detailStartMs / 1000)
      .add(detail, 'detail')
  }, root.value!)
})

/** 暂停后定位；静态采样抑制回调，资源就绪仍由未来 Runtime 负责。 */
function sample(ms: number) { timeline?.pause().seek(ms / 1000, true) }
/** 撤销本组件的全部库对象及其样式；不接触其它页面。 */
function dispose() { context?.revert() }
onBeforeUnmount(dispose)
defineExpose({ sample, dispose, play: () => timeline?.play(), modelMs: () => modelClock.timeMs, durationMs: () => (timeline?.duration() ?? 0) * 1000 })
</script>

<template>
  <section ref="root" class="scene">
    <h1 class="title">产品演示</h1>
    <div class="cards"><div v-for="i in 3" :key="i" class="card">卡片 {{ i }}</div></div>
    <p>模型时间代理：{{ Math.round(modelClock.timeMs) }}ms</p>
    <div class="demo">动作之后出现的演示</div>
  </section>
</template>
