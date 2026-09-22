<!--
  文件用途：本地示例页，用于展示 VideoViewer 的视频播放与统一渲染区域参数。
-->
<template>
  <DefaultContentPage title="Video 视频展示" subtitle="展示 VideoViewer 的视频渲染能力">
    <template #content>
      <div class="grid grid-cols-[2fr_1fr] gap-6">
        <section class="rounded-lg border border-border bg-background p-4">
          <VideoViewer
            :key="videoReloadKey"
            :src="videoUrl"
            :poster="posterUrl"
            :fit="fitMode"
            :controls="controls"
            :autoplay="autoplay"
            :loop="loop"
            :muted="muted"
            preload="metadata"
            width="100%"
            height="560px"
            min-height="360px"
            background-color="#020617"
            :show-border="showBorder"
            border-color="#334155"
            border-radius="16px"
          />
        </section>

        <aside class="space-y-6">
          <section class="rounded-lg border border-border bg-background-subtle p-5">
            <div class="mb-4 flex items-center gap-3">
              <Icon name="全屏" class="size-4" color="primary" />
              <h2 class="font-heading text-xl font-semibold text-primary">播放参数</h2>
            </div>

            <div class="space-y-4 text-sm">
              <label class="block space-y-2">
                <span class="font-medium text-secondary">填充方式</span>
                <select v-model="fitMode" class="video-select">
                  <option value="contain">contain</option>
                  <option value="cover">cover</option>
                  <option value="fill">fill</option>
                </select>
              </label>

              <label v-for="item in toggles" :key="item.key" class="flex items-center gap-3">
                <input v-model="item.model.value" type="checkbox" class="h-4 w-4 accent-primary" />
                <span>{{ item.label }}</span>
              </label>
            </div>
          </section>

          <section class="rounded-lg border border-border bg-background-subtle p-5">
            <div class="mb-4 flex items-center gap-3">
              <Icon name="刷新" class="size-4" color="primary" />
              <h2 class="font-heading text-xl font-semibold text-primary">视频状态</h2>
            </div>

            <p class="mb-4 text-sm leading-6 text-secondary">{{ generationStatus }}</p>
            <button type="button" class="regenerate-button" @click="reloadSampleVideo">
              重新载入示例视频
            </button>
          </section>
        </aside>
      </div>
    </template>
  </DefaultContentPage>
</template>

<script setup lang="ts">
import { computed, ref, type Ref } from 'vue'
import DefaultContentPage from '@/runtime-kit/public/components/page/templates/DefaultContentPage.vue'
import Icon from '@runtime-kit/public/components/primitives/Icon.v1.vue'
import VideoViewer from '@runtime-kit/internal/renderers/VideoViewer.vue'

type ObjectFitMode = 'contain' | 'cover' | 'fill'

interface ToggleOption {
  key: string
  label: string
  model: Ref<boolean>
}

defineOptions({
  name: 'VideoShowcase',
})

const sampleVideoUrl = `${import.meta.env.BASE_URL}video/runtime-video-showcase.webm`
const videoUrl = ref(sampleVideoUrl)
const videoReloadKey = ref(0)
const generationStatus = ref('示例视频已就绪，可直接测试播放、循环、填充和边框参数。')
const fitMode = ref<ObjectFitMode>('contain')
const controls = ref(true)
const autoplay = ref(false)
const loop = ref(true)
const muted = ref(true)
const showBorder = ref(true)

const toggles: ToggleOption[] = [
  { key: 'controls', label: '显示播放控件', model: controls },
  { key: 'autoplay', label: '自动播放', model: autoplay },
  { key: 'loop', label: '循环播放', model: loop },
  { key: 'muted', label: '静音播放', model: muted },
  { key: 'border', label: '显示边框', model: showBorder },
]

/**
 * 用内联 SVG 生成视频封面，避免示例页依赖额外图片资源。
 * @returns data URL 格式封面图
 */
const posterUrl = computed(() => {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 540">
      <defs>
        <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#0f172a"/>
          <stop offset="55%" stop-color="#155e75"/>
          <stop offset="100%" stop-color="#f97316"/>
        </linearGradient>
      </defs>
      <rect width="960" height="540" fill="url(#bg)"/>
      <circle cx="480" cy="270" r="74" fill="rgba(255,255,255,0.22)" stroke="rgba(255,255,255,0.65)" stroke-width="4"/>
      <path d="M462 226 L462 314 L536 270 Z" fill="white"/>
      <text x="48" y="74" fill="white" font-family="Arial, sans-serif" font-size="34" font-weight="700">Runtime Video 示例</text>
    </svg>`
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`
})

/**
 * 重建视频元素，便于重复验证同一示例视频的加载与播放状态。
 */
function reloadSampleVideo(): void {
  videoReloadKey.value += 1
  generationStatus.value = '示例视频已重新载入，可继续测试播放、循环、填充和边框参数。'
}
</script>

<style scoped>
.video-select {
  width: 100%;
  border-radius: 8px;
  border: 1px solid var(--tw-color-border-default);
  background: var(--tw-color-bg-default);
  padding: 10px 12px;
  color: var(--tw-color-text-primary);
  outline: none;
}

.video-select:focus {
  border-color: var(--tw-color-text-primary);
}

.regenerate-button {
  width: 100%;
  border-radius: 8px;
  background: var(--tw-color-text-primary);
  padding: 10px 14px;
  color: var(--tw-color-bg-default);
  font-weight: 700;
}
</style>
