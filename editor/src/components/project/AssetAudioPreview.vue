<!-- 文件功能：为音频资源提供不自动播放的原生试听、元数据展示与播放生命周期清理。 -->
<template>
  <section class="flex h-full min-h-0 w-full items-center justify-center rounded-2xl border border-border bg-canvas p-5 sm:p-8">
    <div class="w-full max-w-2xl rounded-2xl border border-border bg-surface p-5 shadow-sm sm:p-7">
      <div class="flex items-start gap-4">
        <div class="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-accent-muted text-accent">
          <Music class="h-6 w-6" />
        </div>
        <div class="min-w-0 flex-1">
          <h3 class="truncate text-sm font-bold text-text">{{ asset.name }}</h3>
          <p class="mt-1 truncate font-mono text-xs text-text-disabled">{{ asset.original_name }}</p>
        </div>
        <span class="shrink-0 rounded-full bg-surface-muted px-2.5 py-1 text-[10px] font-black uppercase text-text-muted">
          {{ formatLabel }}
        </span>
      </div>

      <audio
        v-if="asset.url"
        ref="audioElement"
        :key="`${asset.id}:${asset.file_hash}`"
        class="mt-6 w-full"
        :src="asset.url"
        controls
        preload="metadata"
        @loadedmetadata="handleLoadedMetadata"
        @error="handleLoadError"
      >
        当前浏览器不支持音频播放。
      </audio>
      <div v-else class="mt-6 rounded-xl border border-dashed border-border p-5 text-center text-sm text-text-muted">
        当前资源没有可用的试听地址。
      </div>

      <dl class="mt-5 grid gap-3 text-xs sm:grid-cols-3">
        <div class="rounded-xl bg-canvas px-3 py-2.5">
          <dt class="text-text-muted">时长</dt>
          <dd class="mt-1 font-bold text-text">{{ durationText }}</dd>
        </div>
        <div class="rounded-xl bg-canvas px-3 py-2.5">
          <dt class="text-text-muted">文件大小</dt>
          <dd class="mt-1 font-bold text-text">{{ formatBytes(asset.file_size) }}</dd>
        </div>
        <div class="rounded-xl bg-canvas px-3 py-2.5">
          <dt class="text-text-muted">加载策略</dt>
          <dd class="mt-1 font-bold text-text">仅元数据</dd>
        </div>
      </dl>

      <p v-if="loadError" role="alert" class="mt-4 rounded-xl bg-danger-muted px-4 py-3 text-xs leading-5 text-danger-strong">
        无法加载音频元数据，请检查文件编码或访问权限。
      </p>
      <p v-else class="mt-4 text-xs leading-5 text-text-disabled">
        试听不会自动播放；发布素材建议优先使用 MP3，旁白建议使用清晰的人声编码。
      </p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Music } from '@lucide/vue'

import type { AssetResponse } from '@/types/api'

const props = defineProps<{
  asset: AssetResponse
}>()

const audioElement = ref<HTMLAudioElement | null>(null)
const durationSeconds = ref<number | null>(null)
const loadError = ref(false)

const formatLabel = computed(() => {
  const extension = props.asset.original_name.split('.').pop()?.trim().toUpperCase()
  return extension || 'AUDIO'
})

const durationText = computed(() => {
  if (durationSeconds.value === null) return '等待载入'
  const wholeSeconds = Math.max(0, Math.round(durationSeconds.value))
  const minutes = Math.floor(wholeSeconds / 60)
  const seconds = wholeSeconds % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
})

/** 停止当前音频并回到起点，防止资源切换或弹窗关闭后继续播放。 */
function stopPlayback(element = audioElement.value): void {
  if (!element) return
  element.pause()
  try {
    element.currentTime = 0
  }
  catch {
    // 尚未获得可定位媒体数据时，浏览器可能拒绝设置 currentTime。
  }
}

/** 读取浏览器解析出的媒体时长。 */
function handleLoadedMetadata(event: Event): void {
  const element = event.currentTarget as HTMLAudioElement
  loadError.value = false
  durationSeconds.value = Number.isFinite(element.duration) ? element.duration : null
}

/** 记录媒体加载失败状态，保留原生控件供用户重试。 */
function handleLoadError(): void {
  durationSeconds.value = null
  loadError.value = true
}

/** 格式化资源大小供试听摘要展示。 */
function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

watch(
  () => [props.asset.id, props.asset.file_hash, props.asset.url] as const,
  (_nextSource, _previousSource, onCleanup) => {
    const previousElement = audioElement.value
    stopPlayback(previousElement)
    durationSeconds.value = null
    loadError.value = false
    onCleanup(() => stopPlayback(previousElement))
  },
)

onBeforeUnmount(() => {
  stopPlayback()
})
</script>
