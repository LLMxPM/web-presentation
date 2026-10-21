<!-- 文件功能：独立模型创作评测的固定 DOM、真实资源及后续复用段落目标。 -->
<script setup lang="ts">
import { ref } from 'vue'
import type { Elements } from '../motion-story/types'
const root = ref<HTMLElement>(), audio = ref<HTMLAudioElement>(), video = ref<HTMLVideoElement>(), canvas = ref<HTMLCanvasElement>()
/** 只在 mounted 后返回本实例目标，保持与研究 SDK 的结构兼容。 */
function elements(): Elements { return { root: root.value!, audio: audio.value!, video: video.value!, canvas: canvas.value! } }
defineExpose({ elements })
</script>
<template>
  <section ref="root" class="story">
    <p class="eyebrow">Luna 独立编写 · 固定资源</p>
    <h1 class="title">标题、骨骼与媒体，共用一个故事</h1>
    <div class="cards"><div v-for="label in ['旁白主时钟', '独立骨骼实例', '视频裁切']" :key="label" class="card">{{ label }}</div></div>
    <div class="panels">
      <div><canvas ref="canvas" width="400" height="200" /><p class="clip-caption">同一 GLB · 两个独立 Mixer</p></div>
      <div><video ref="video" muted playsinline width="320" height="180" /><p class="demo-caption">源视频 1—3 秒 · 接在动作之后</p></div>
    </div>
    <div class="callouts"><div v-for="section in ['model', 'demo']" :key="section" :class="`callout-${section}`"><span v-for="i in 3" :key="i" class="chip">{{ section }} · {{ i }}</span></div></div>
    <audio ref="audio" preload="auto" />
  </section>
</template>
