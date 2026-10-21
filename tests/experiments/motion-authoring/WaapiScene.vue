<!-- 文件功能：裸 WAAPI 的同题 SFC；显式展示原生 API 之外所需的计划、对象采样和控制代码。 -->
<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'

const props = withDefaults(defineProps<{ detailStartMs?: number }>(), { detailStartMs: 900 })
const root = ref<HTMLElement | null>(null)
const modelClock = reactive({ timeMs: 0 })
const animations: Animation[] = []
let raf = 0
const detailEndMs = props.detailStartMs + 2000
const durationMs = () => Math.max(1100, detailEndMs + 500)

/** 建立局部 DOM 动画；标签解析、依赖和对象轨道并非 WAAPI 自带能力。 */
function add(selector: string, duration: number, start: number, y = 0, step = 0) {
  root.value!.querySelectorAll(selector).forEach((element, index) => {
    const animation = element.animate(
      [{ opacity: 0, transform: `translateY(${y}px)` }, { opacity: 1, transform: 'translateY(0px)' }],
      { duration, delay: start + step * index, fill: 'both', easing: 'linear' },
    )
    animation.pause(); animation.currentTime = 0; animations.push(animation)
  })
}
onMounted(() => {
  add('.title', 400, 0, 32)
  add('.card', 300, 600, 24, 100)
  add('.demo', 300, detailEndMs + 200)
})

/** 手工应用所有 DOM 与对象轨道；外部媒体时钟接入仍需 Runtime。 */
function sample(ms: number) {
  cancelAnimationFrame(raf); raf = 0
  animations.forEach(animation => { animation.currentTime = ms })
  modelClock.timeMs = Math.min(2000, Math.max(0, ms - props.detailStartMs))
}
/** 原生 API 没有本例需要的组播放器，此处手工实现一个示意控制循环。 */
function play() {
  const started = performance.now()
  const tick = () => {
    const ms = Math.min(durationMs(), performance.now() - started)
    sample(ms)
    if (ms < durationMs()) raf = requestAnimationFrame(tick)
  }
  tick()
}
/** 清理本组件持有的每个动画及自建循环。 */
function dispose() { cancelAnimationFrame(raf); raf = 0; animations.forEach(animation => animation.cancel()) }
onBeforeUnmount(dispose)
defineExpose({ sample, dispose, play, modelMs: () => modelClock.timeMs, durationMs })
</script>

<template>
  <section ref="root" class="scene">
    <h1 class="title">产品演示</h1>
    <div class="cards"><div v-for="i in 3" :key="i" class="card">卡片 {{ i }}</div></div>
    <p>模型时间代理：{{ Math.round(modelClock.timeMs) }}ms</p>
    <div class="demo">动作之后出现的演示</div>
  </section>
</template>
