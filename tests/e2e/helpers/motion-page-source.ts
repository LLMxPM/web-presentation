/**
 * 文件功能：提供跨 E2E 场景共用的正式 Runtime Kit 短时间轴页面源码。
 */

/** 构造默认海报可读的短时间轴页面。 */
export function buildMotionPage(): string {
  return `<template>
  <main ref="root" class="motion-e2e-page">
    <h1 class="motion-e2e-title">时间轴第一页</h1>
  </main>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import { usePageTimeline } from '@runtime-kit/public/composables/motion/usePageTimeline.v1'
const root = ref<HTMLElement | null>(null)
usePageTimeline({
  root,
  bindings: { title: '.motion-e2e-title' },
  applyPoster: true,
  definition: {
    schemaVersion: 1,
    timelineId: 'e2e-advance',
    poster: { atMs: 1800 },
    tracks: [{ type: 'dom', id: 'title', target: 'title', preset: 'fade', durationMs: 1800 }],
  },
})
</script>
<style scoped>
.motion-e2e-page { width: 100%; height: 100%; display: grid; place-items: center; background: #f8fafc; }
.motion-e2e-title { font-size: 64px; color: #b91c1c; }
</style>`
}
