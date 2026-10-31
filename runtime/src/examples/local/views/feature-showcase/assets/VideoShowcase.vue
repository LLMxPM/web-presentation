<!--
  文件用途：本地示例页，展示 AssetVideo 的视频渲染、封面回退与播放参数控制。
-->
<template>
  <ShowcasePage
    title="视频渲染"
    subtitle="视频资源由 AssetVideo 渲染，播放受运行时媒体策略约束"
    :capabilities="capabilities"
  >
    <div class="grid h-full min-h-0 grid-cols-[1.55fr_0.95fr] gap-5">
      <section class="flex min-h-0 flex-col rounded-lg border border-border-subtle bg-background-subtle p-4">
        <div class="mb-3 flex items-center gap-2">
          <Icon name="全屏" class="size-4 text-primary" />
          <h2 class="font-heading text-base font-semibold text-primary">播放区域</h2>
          <span class="ml-auto font-code text-xs text-secondary">fit={{ fitMode }}</span>
        </div>
        <AssetVideo
          :key="reloadKey"
          name=""
          :fallback="videoUrl"
          :poster="posterUrl"
          purpose="content"
          :controls="controls"
          :loop="loop"
          :muted="muted"
          :volume="0.8"
          preload="metadata"
          :fit="fitMode"
          position="center"
          width="100%"
          height="100%"
          class="min-h-0 flex-1 rounded-md"
          background-color="#020617"
          :show-border="true"
          border-color="#334155"
          border-radius="12px"
        />
        <p class="mt-3 font-body text-xs leading-6 text-secondary">
          本地 fixture 用 fallback 传入示例视频；平台页面传资源名 name，封面可用 posterName 绑定另一张资源。
        </p>
      </section>

      <section class="flex min-h-0 flex-col gap-4">
        <div class="rounded-lg border border-border bg-background-subtle p-5">
          <div class="mb-3 flex items-center gap-2">
            <Icon name="slider" class="size-4 text-primary" />
            <h3 class="font-heading text-base font-semibold text-primary">播放参数</h3>
          </div>

          <div class="space-y-3">
            <label class="block space-y-1.5">
              <span class="font-body text-xs text-secondary">填充方式 fit</span>
              <select v-model="fitMode" class="showcase-input">
                <option value="contain">contain · 完整展示</option>
                <option value="cover">cover · 铺满裁剪</option>
                <option value="fill">fill · 拉伸铺满</option>
              </select>
            </label>

            <label v-for="toggle in toggles" :key="toggle.key" class="flex items-center gap-2.5">
              <input v-model="toggle.model.value" type="checkbox" class="size-4 accent-primary" />
              <span class="font-body text-xs text-primary">{{ toggle.label }}</span>
            </label>
          </div>

          <p class="mt-3 font-body text-xs leading-6 text-secondary">
            组件不暴露 autoplay：自动播放由播放策略与显式 Scene 任务决定。
          </p>
        </div>

        <div class="flex min-h-0 flex-1 flex-col rounded-lg border border-border bg-background-subtle p-5">
          <div class="mb-3 flex items-center gap-2">
            <Icon name="刷新" class="size-4 text-primary" />
            <h3 class="font-heading text-base font-semibold text-primary">资源状态</h3>
          </div>
          <p class="font-body text-xs leading-6 text-secondary">{{ status }}</p>
          <button type="button" class="mt-3 rounded-md bg-primary px-4 py-2 font-body text-sm font-semibold text-invert" @click="reload">
            重新载入示例视频
          </button>
          <pre class="mt-auto overflow-auto rounded-md bg-default p-3 font-code text-xs leading-6 text-primary">&lt;AssetVideo name="demo-video" poster-name="demo-cover"
  fit="cover" loop muted /&gt;</pre>
        </div>
      </section>
    </div>
  </ShowcasePage>
</template>

<script setup lang="ts">
import { computed, ref, type Ref } from 'vue'
import ShowcasePage, { type ShowcaseCapability } from '@/examples/local/components/ShowcasePage.vue'
import AssetVideo from '@runtime-kit/public/components/assets/AssetVideo.v1.vue'
import Icon from '@runtime-kit/public/components/primitives/Icon.v1.vue'

type ObjectFitMode = 'contain' | 'cover' | 'fill'
interface ToggleOption {
  key: string
  label: string
  model: Ref<boolean>
}

const capabilities: ShowcaseCapability[] = [
  { name: 'AssetVideo.v1', path: '@runtime-kit/public/components/assets/AssetVideo.v1.vue' },
]

const videoUrl = `${import.meta.env.BASE_URL}video/runtime-video-showcase.webm`
const reloadKey = ref(0)
const status = ref('示例视频已就绪，可测试播放、循环、静音与填充方式。')
const fitMode = ref<ObjectFitMode>('contain')
const controls = ref(true)
const loop = ref(true)
const muted = ref(true)

const toggles: ToggleOption[] = [
  { key: 'controls', label: '显示播放控件', model: controls },
  { key: 'loop', label: '循环播放', model: loop },
  { key: 'muted', label: '静音播放', model: muted },
]

/**
 * 用内联 SVG 生成封面，避免示例页依赖额外图片资源。
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

/** 重建视频元素，便于重复验证加载与播放状态。 */
function reload(): void {
  reloadKey.value += 1
  status.value = '示例视频已重新载入，可继续测试循环、静音与填充方式。'
}
</script>

<style scoped>
.showcase-input {
  width: 100%;
  border-radius: 8px;
  border: 1px solid var(--tw-color-border-default);
  background: var(--tw-color-bg-default);
  padding: 8px 10px;
  color: var(--tw-color-text-primary);
  font-size: 13px;
  outline: none;
}
</style>
