<!--
  文件用途：导出进行中的进度面板，按导出方式与范围渲染标题、进度文案、进度条与取消入口。
-->

<template>
  <div class="space-y-6 py-2">
    <div class="text-center">
      <div
        class="mx-auto mb-4 inline-flex h-14 w-14 items-center justify-center rounded-full bg-blue-50 text-blue-600">
        <Loader2 class="animate-spin" :size="28" />
      </div>
      <h4 class="text-lg font-semibold text-slate-950">
        {{ exportingTitle }}
      </h4>
      <p class="mt-2 text-sm text-slate-500">
        {{ progressText }}
      </p>
    </div>

    <div class="space-y-2">
      <div class="h-2 overflow-hidden rounded-full bg-slate-100">
        <div
          class="h-full rounded-full bg-blue-600 transition-all duration-300"
          :style="{ width: `${progress.percentage}%` }"></div>
      </div>
      <div v-if="progress.total > 0" class="flex items-center justify-between text-xs text-slate-500">
        <span>{{ progress.current }} / {{ progress.total }}</span>
        <span v-if="progress.currentPageTitle" class="max-w-[320px] truncate">{{ progress.currentPageTitle }}</span>
      </div>
    </div>

    <div class="text-center">
      <button
        type="button"
        class="rounded-md px-4 py-2 text-sm font-medium text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-800"
        @click="emit('cancel')">
        取消导出
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Loader2 } from '@lucide/vue'
import type { ExportMode, ExportProgress } from '@/core/types/export-common'
import type { DialogExportMethod } from './export-dialog-types'

interface Props {
  /** 当前导出方式，决定标题与进度文案 */
  method: DialogExportMethod
  /** 当前导出范围；单页导出没有逐页进度 */
  mode: ExportMode
  /** 逐页进度快照 */
  progress: ExportProgress
}

interface Emits {
  (e: 'cancel'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

/** 进行中标题：打印不产出文件，动词与两种导出不同。 */
const EXPORTING_TITLES: Record<DialogExportMethod, string> = {
  'pptx-editable': '正在导出 PPTX',
  'browser-print': '正在准备打印',
  'canvas-pdf': '正在导出 PDF',
}

/**
 * 各方式的进度文案，按单页、逐页、待启动三种状态分别取值。
 * current 用于单页导出；page 是逐页文案的前缀，后面拼接当前页标题；idle 用于尚未收到首次进度上报时。
 */
const PROGRESS_TEXTS: Record<DialogExportMethod, { current: string; page: string; idle: string }> = {
  'pptx-editable': {
    current: '正在转换当前页面...',
    page: '正在转换',
    idle: '正在准备 PPTX 导出...',
  },
  'browser-print': {
    current: '正在准备当前页面打印...',
    page: '正在准备打印',
    idle: '正在准备打印文档...',
  },
  'canvas-pdf': {
    current: '正在捕获当前页面...',
    page: '正在处理',
    idle: '正在准备导出...',
  },
}

const exportingTitle = computed(() => EXPORTING_TITLES[props.method])

const progressText = computed(() => {
  const texts = PROGRESS_TEXTS[props.method]
  if (props.mode === 'current') {
    return texts.current
  }

  if (props.progress.currentPageTitle) {
    return `${texts.page}: ${props.progress.currentPageTitle}`
  }

  return texts.idle
})
</script>
