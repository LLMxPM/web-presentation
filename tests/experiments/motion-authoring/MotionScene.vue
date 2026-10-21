<!-- 文件功能：Motion for Vue 原生 sequence 样例，验证 useAnimate 作用域和可定位的整体序列。 -->
<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive } from 'vue'
import { useAnimate, stagger, type AnimationSequence } from 'motion-v'

const props = withDefaults(defineProps<{ detailStartMs?: number }>(), { detailStartMs: 900 })
const [scope, animate] = useAnimate()
const modelClock = reactive({ timeMs: 0 })
let controls: ReturnType<typeof animate> | undefined

/** 复用定义片段；这是数组展开，不是独立子播放器的嵌套。 */
function detailSection(): AnimationSequence {
  return [
    [modelClock, { timeMs: [0, 2000] }, { duration: 2, ease: 'linear', at: 'detail' }],
    ['.demo', { opacity: [0, 1] }, { duration: 0.3, ease: 'linear', at: '+0.2' }],
  ]
}
onMounted(() => {
  const sequence: AnimationSequence = [
    ['.title', { opacity: [0, 1], y: [32, 0] }, { duration: 0.4, ease: 'linear', at: 0 }],
    ['.card', { opacity: [0, 1], y: [24, 0] }, { duration: 0.3, ease: 'linear', delay: stagger(0.1), at: 0.6 }],
    { name: 'detail', at: props.detailStartMs / 1000 },
    ...detailSection(),
  ]
  controls = animate(sequence, { autoplay: false })
})

/** 序列作为整体定位；不通过 await 链条表达可拖动的时间轴。 */
function sample(ms: number) { if (controls) { controls.pause(); controls.time = ms / 1000 } }
/** useAnimate 自带卸载清理，这里另外显式取消以验证主动销毁。 */
function dispose() { controls?.cancel() }
onBeforeUnmount(dispose)
defineExpose({ sample, dispose, play: () => controls?.play(), modelMs: () => modelClock.timeMs, durationMs: () => (controls?.duration ?? 0) * 1000 })
</script>

<template>
  <section ref="scope" class="scene">
    <h1 class="title">产品演示</h1>
    <div class="cards"><div v-for="i in 3" :key="i" class="card">卡片 {{ i }}</div></div>
    <p>模型时间代理：{{ Math.round(modelClock.timeMs) }}ms</p>
    <div class="demo">动作之后出现的演示</div>
  </section>
</template>
