<!-- 文件功能：三种创作路线共享的真实媒体、骨骼与 DOM 目标，避免模板差异影响功能对照。 -->
<script setup lang="ts">
import { ref } from 'vue'
import type { Elements } from './types'
const root = ref<HTMLElement>(), audio = ref<HTMLAudioElement>(), video = ref<HTMLVideoElement>(), canvas = ref<HTMLCanvasElement>()
/** 只在 mounted 后提供作用域内目标，实验不向页面暴露全局 selector。 */
function elements(): Elements { return { root: root.value!, audio: audio.value!, video: video.value!, canvas: canvas.value! } }
defineExpose({ elements })
</script>
<template>
  <section ref="root" class="story">
    <p class="eyebrow">编排研究 · 真实资源</p>
    <h1 class="title">标题、骨骼与媒体，共用一个故事</h1>
    <div class="cards"><div v-for="label in ['旁白主时钟', '独立骨骼实例', '视频裁切']" :key="label" class="card">{{ label }}</div></div>
    <div class="panels">
      <div><canvas ref="canvas" width="400" height="200" /><p class="clip-caption">同一 GLB · 两个独立 Mixer · 相差 500ms</p></div>
      <div><video ref="video" muted playsinline width="320" height="180" /><p class="demo-caption">源视频 1—3 秒 · 接在动作结束之后</p></div>
    </div>
    <audio ref="audio" preload="auto" />
  </section>
</template>
