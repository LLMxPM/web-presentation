<!-- 文件功能：封装 Runtime 预览 iframe 与空态展示，统一处理比例容器和填充容器两种模式。 -->
<template>
  <div data-testid="page-preview-frame" :class="props.containerClass" :style="containerStyle">
    <iframe
      v-if="props.frameUrl"
      :src="props.frameUrl"
      :title="props.title"
      :class="props.iframeClass"
      referrerpolicy="same-origin"
    />
    <div v-else :class="props.emptyContentClass">
      <div class="space-y-3">
        <p v-if="props.emptyTitle" class="text-base font-semibold text-slate-700">{{ props.emptyTitle }}</p>
        <p v-if="props.emptyDescription" class="text-sm text-slate-500">{{ props.emptyDescription }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  frameUrl: string
  title: string
  viewport?: {
    width: number
    height: number
  } | null
  minHeight?: string
  layout?: 'aspect' | 'fill'
  containerClass?: string
  iframeClass?: string
  emptyContentClass?: string
  emptyTitle?: string
  emptyDescription?: string
}

const props = withDefaults(defineProps<Props>(), {
  viewport: null,
  minHeight: '',
  layout: 'aspect',
  containerClass: 'overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm',
  iframeClass: 'block h-full w-full bg-slate-50',
  emptyContentClass: 'flex h-full items-center justify-center px-8 text-center',
  emptyTitle: '',
  emptyDescription: '',
})

const containerStyle = computed(() => {
  const nextStyle: Record<string, string> = {}

  if (props.layout === 'aspect' && hasValidViewport(props.viewport)) {
    nextStyle.aspectRatio = `${props.viewport.width} / ${props.viewport.height}`
  }

  if (props.minHeight) {
    nextStyle.minHeight = props.minHeight
  }

  return nextStyle
})

/**
 * 判断传入的视口尺寸是否可用于生成合法比例。
 * @param viewport 预览视口
 * @returns 是否同时存在大于 0 的宽高
 */
function hasValidViewport(viewport: Props['viewport']): viewport is NonNullable<Props['viewport']> {
  return Boolean(viewport && viewport.width > 0 && viewport.height > 0)
}
</script>
