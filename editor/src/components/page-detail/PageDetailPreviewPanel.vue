<!-- 文件功能：渲染页面详情的 Runtime 预览画布，保持主区域聚焦在实际页面效果。 -->
<template>
  <section class="group relative h-full min-h-0 overflow-hidden rounded-2xl border border-slate-200 bg-slate-100">
    <button
      type="button"
      title="放大查看"
      aria-label="放大查看"
      class="absolute right-4 top-4 z-10 inline-flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200 bg-white/80 text-slate-500 opacity-0 shadow-sm backdrop-blur transition hover:border-slate-300 hover:bg-white hover:text-slate-800 group-hover:opacity-100 focus-visible:opacity-100 disabled:cursor-not-allowed disabled:opacity-0"
      :disabled="!props.previewFrameUrl"
      @click="openPreviewDialog"
    >
      <Maximize2 class="h-4 w-4" />
    </button>

    <RuntimePreviewFrame
      :frame-url="activePreviewFrameUrl"
      title="runtime-preview"
      :viewport="props.previewViewport"
      layout="fill"
      container-class="h-full overflow-hidden bg-white"
      :empty-title="currentPreviewEmptyTitle"
      :empty-description="currentPreviewEmptyDescription"
    />

    <Teleport to="body">
      <Transition name="preview-dialog">
        <div v-if="isPreviewDialogOpen" class="fixed inset-0 z-[1000] bg-slate-950/70 p-4 backdrop-blur-sm">
          <div class="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
            <div class="flex h-12 shrink-0 items-center justify-between border-b border-slate-100 px-4">
              <h3 class="min-w-0 truncate text-sm font-semibold text-slate-900">{{ previewDialogTitle }}</h3>
              <BaseCloseButton label="关闭预览" @click="isPreviewDialogOpen = false" />
            </div>
            <div class="min-h-0 flex-1 bg-slate-100 p-3">
              <RuntimePreviewFrame
                v-if="props.previewFrameUrl"
                :frame-url="props.previewFrameUrl"
                title="runtime-preview-dialog"
                :viewport="props.previewViewport"
                layout="fill"
                container-class="h-full overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"
              />
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Maximize2 } from '@lucide/vue'

import RuntimePreviewFrame from '@/components/runtime-preview/RuntimePreviewFrame.vue'
import BaseCloseButton from '@/components/ui/BaseCloseButton.vue'

interface Props {
  previewEnabled: boolean
  previewUrl: string
  previewFrameUrl: string
  previewViewport: {
    width: number
    height: number
  }
  pageTitle: string
  previewDisplayFileName: string
}

const props = defineProps<Props>()
const isPreviewDialogOpen = ref(false)

const previewDialogTitle = computed(() => (
  props.previewDisplayFileName ? `Runtime 预览 · ${props.previewDisplayFileName}` : `Runtime 预览 · ${props.pageTitle}`
))

const activePreviewFrameUrl = computed(() => (
  props.previewEnabled && props.previewUrl ? props.previewFrameUrl : ''
))

const currentPreviewEmptyTitle = computed(() => (
  props.previewEnabled ? '预览尚未生成' : '预览不可用'
))

const currentPreviewEmptyDescription = computed(() => (
  props.previewEnabled
    ? '保存后会自动把当前页面推送到 Runtime，并在这里刷新展示最新结果。'
    : '当前页面暂时没有可用的 Runtime 预览地址。'
))

/**
 * 打开放大的 Runtime 预览弹窗，仅在已生成预览地址时生效。
 */
function openPreviewDialog(): void {
  if (!props.previewFrameUrl) return
  isPreviewDialogOpen.value = true
}

/**
 * 支持在放大预览中使用 Esc 快速关闭，避免用户被全屏浮层阻塞。
 * @param event 键盘事件
 */
function handleDialogKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape' && isPreviewDialogOpen.value) {
    isPreviewDialogOpen.value = false
  }
}

onMounted(() => window.addEventListener('keydown', handleDialogKeydown))
onUnmounted(() => window.removeEventListener('keydown', handleDialogKeydown))
</script>

<style scoped>
.preview-dialog-enter-active,
.preview-dialog-leave-active {
  transition: opacity 0.18s ease;
}

.preview-dialog-enter-from,
.preview-dialog-leave-to {
  opacity: 0;
}
</style>
