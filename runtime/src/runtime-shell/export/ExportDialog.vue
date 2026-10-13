<!--
  文件用途：页面导出弹窗，负责选择导出方式与范围、展示进度和结果；执行与取消逻辑见 useExportRunner。
-->

<template>
  <div
    v-if="isVisible"
    class="fixed inset-0 z-[9999] flex items-center justify-center bg-slate-950/55 px-4 py-6 backdrop-blur-sm"
    role="dialog" aria-modal="true" aria-labelledby="export-dialog-title" @click.self="closeDialog">
    <div
      class="flex max-h-[min(760px,calc(100vh-48px))] w-full max-w-[700px] flex-col overflow-hidden rounded-[10px] bg-white shadow-2xl ring-1 ring-slate-900/10">
      <header class="flex items-center justify-between border-b border-slate-200 px-7 py-5">
        <div class="min-w-0">
          <h3 id="export-dialog-title" class="text-xl font-semibold tracking-tight text-slate-950">
            导出
          </h3>
          <p class="mt-1 text-sm text-slate-500">
            选择文件格式和页面范围
          </p>
        </div>
        <button
          type="button"
          class="inline-flex h-9 w-9 items-center justify-center rounded-md text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
          :disabled="isExporting" aria-label="关闭导出弹窗" @click="closeDialog">
          <X :size="20" />
        </button>
      </header>

      <main class="flex-1 overflow-y-auto px-7 py-6">
        <form v-if="!isExporting && !exportResult" class="space-y-6" @submit.prevent="startExport">
          <section class="space-y-3">
            <div class="flex items-center justify-between gap-4">
              <h4 class="text-sm font-semibold text-slate-800">
                生成方式
              </h4>
              <span class="text-xs text-slate-400">选择合适的导出格式</span>
            </div>
            <div class="grid gap-3 sm:grid-cols-3">
              <label
                v-for="option in methodOptions" :key="option.value"
                class="group cursor-pointer rounded-lg border p-4 transition-all hover:border-blue-300 hover:bg-blue-50/40"
                :class="exportMethod === option.value ? 'border-blue-500 bg-blue-50 shadow-sm ring-1 ring-blue-500/20' : 'border-slate-200 bg-white'">
                <input v-model="exportMethod" type="radio" :value="option.value" class="sr-only">
                <span class="flex items-start gap-3">
                  <span
                    class="mt-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md"
                    :class="exportMethod === option.value ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-500 group-hover:bg-blue-100 group-hover:text-blue-700'">
                    <component :is="option.icon" :size="18" />
                  </span>
                  <span class="min-w-0">
                    <span class="block text-sm font-semibold text-slate-900">{{ option.label }}</span>
                    <span class="mt-1 block w-full truncate text-xs leading-5 text-slate-500" :title="option.description">
                      {{ option.description }}
                    </span>
                  </span>
                </span>
              </label>
            </div>
          </section>

          <section class="space-y-3">
            <h4 class="text-sm font-semibold text-slate-800">
              导出范围
            </h4>
            <div class="grid grid-cols-2 gap-3">
              <label
                v-for="option in rangeOptions" :key="option.value"
                class="cursor-pointer rounded-lg border px-4 py-3 transition-all hover:border-blue-300 hover:bg-blue-50/40"
                :class="exportMode === option.value ? 'border-blue-500 bg-blue-50 ring-1 ring-blue-500/20' : 'border-slate-200 bg-white'">
                <input v-model="exportMode" type="radio" :value="option.value" class="sr-only">
                <span
                  class="flex items-center gap-2 text-sm font-medium"
                  :class="exportMode === option.value ? 'text-blue-700' : 'text-slate-700'">
                  <component :is="option.icon" :size="17" />
                  {{ option.label }}
                </span>
              </label>
            </div>
          </section>

          <section class="space-y-2">
            <label v-if="!isBrowserPrint" for="filename" class="block text-sm font-semibold text-slate-800">
              文件名（可选）
            </label>
            <input
              v-if="!isBrowserPrint" id="filename" v-model="filename" type="text" :placeholder="filenamePlaceholder"
              class="h-11 w-full rounded-lg border border-slate-300 px-3 text-sm text-slate-900 outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-100">
            <div
              v-else
              class="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-800">
              浏览器打印模式会打开系统打印对话框，文件名由打印对话框决定。
            </div>
          </section>
        </form>

        <ExportProgress
          v-else-if="isExporting"
          :method="exportMethod" :mode="exportMode" :progress="progress" @cancel="cancelExport" />

        <div v-else-if="exportResult" class="py-4 text-center">
          <div
            class="mx-auto mb-4 inline-flex h-14 w-14 items-center justify-center rounded-full"
            :class="exportResult.success ? 'bg-emerald-50 text-emerald-600' : 'bg-red-50 text-red-600'">
            <CheckCircle2 v-if="exportResult.success" :size="30" />
            <AlertCircle v-else :size="30" />
          </div>

          <h4 class="text-lg font-semibold text-slate-950">
            {{ exportResult.success ? successTitle : '导出失败' }}
          </h4>
          <p
            class="mx-auto mt-2 max-w-sm text-sm leading-6"
            :class="exportResult.success ? 'text-slate-500' : 'text-red-600'">
            {{ exportResult.success ? successMessage : (exportResult.error || '未知错误') }}
          </p>

          <div
            v-if="exportResult.success"
            class="mt-4 rounded-lg bg-slate-50 px-4 py-3 text-left text-xs leading-6 text-slate-500">
            <p v-if="exportResult.filename">
              文件名：{{ exportResult.filename }}
            </p>
            <p>页面数：{{ exportResult.pageCount || 0 }}</p>
            <p>耗时：{{ Math.round((exportResult.duration || 0) / 1000) }} 秒</p>
          </div>

          <PptxExportReport :report="pptxReport" />
        </div>
      </main>

      <footer class="flex items-center justify-end gap-3 border-t border-slate-200 bg-slate-50 px-7 py-5">
        <button
          v-if="!isExporting && !exportResult" type="button"
          class="h-11 rounded-lg bg-white px-5 text-sm font-semibold text-slate-700 ring-1 ring-slate-200 transition hover:bg-slate-100"
          @click="closeDialog">
          取消
        </button>
        <button
          v-if="!isExporting && !exportResult" type="button"
          class="inline-flex h-11 items-center gap-2 rounded-lg bg-blue-600 px-5 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-700"
          @click="startExport">
          <Printer v-if="isBrowserPrint" :size="17" />
          <FileDown v-else :size="17" />
          {{ primaryActionLabel }}
        </button>
        <button
          v-if="exportResult" type="button"
          class="inline-flex h-11 items-center gap-2 rounded-lg bg-blue-600 px-5 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-700"
          @click="resetDialog">
          <RotateCcw :size="17" />
          重新导出
        </button>
        <button
          v-if="exportResult" type="button"
          class="h-11 rounded-lg bg-white px-5 text-sm font-semibold text-slate-700 ring-1 ring-slate-200 transition hover:bg-slate-100"
          @click="closeDialog">
          关闭
        </button>
      </footer>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import {
  AlertCircle,
  CheckCircle2,
  File as FileIcon,
  FileDown,
  FileText,
  Files,
  Printer,
  RotateCcw,
  X,
} from '@lucide/vue'
import type { ExportMethod } from '@/core/types/pdf-export'
import ExportProgress from './ExportProgress.vue'
import PptxExportReport from './PptxExportReport.vue'
import { isPptxExportResult, type DialogExportMethod, type DialogExportResult } from './export-dialog-types'
import { useExportRunner } from './useExportRunner'

interface Props {
  visible?: boolean
}

interface Emits {
  (e: 'update:visible', value: boolean): void
  (e: 'export-start'): void
  (e: 'export-complete', result: DialogExportResult): void
  (e: 'export-error', error: Error): void
}

const props = withDefaults(defineProps<Props>(), {
  visible: false
})

const emit = defineEmits<Emits>()

/** 生成方式选项，顺序即展示顺序，默认选中第一项。 */
const methodOptions = [
  {
    value: 'pptx-editable' as DialogExportMethod,
    label: 'HTML转PPTX',
    description: '可编辑的PPTX文件',
    icon: FileText,
  },
  {
    value: 'browser-print' as ExportMethod,
    label: '打印PDF',
    description: '浏览器打印生成PDF',
    icon: Printer,
  },
  {
    value: 'canvas-pdf' as ExportMethod,
    label: '截图PDF',
    description: '截图拼接文件',
    icon: FileText,
  },
]

/** 导出范围选项。 */
const rangeOptions = [
  {
    value: 'current' as const,
    label: '当前页面',
    icon: FileIcon,
  },
  {
    value: 'all' as const,
    label: '所有页面',
    icon: Files,
  },
]

const isVisible = ref(props.visible)
const exportMode = ref<'current' | 'all'>('current')
const exportMethod = ref<DialogExportMethod>('pptx-editable')
const filename = ref('')

const runner = useExportRunner({
  onStart: () => emit('export-start'),
  onComplete: result => emit('export-complete', result),
  onError: error => emit('export-error', error),
})
const { isExporting, exportResult, progress } = runner

const isBrowserPrint = computed(() => exportMethod.value === 'browser-print')
const isPptxEditable = computed(() => exportMethod.value === 'pptx-editable')

const primaryActionLabel = computed(() => {
  return isBrowserPrint.value ? '打开打印' : '开始导出'
})

const filenamePlaceholder = computed(() => {
  if (isPptxEditable.value) {
    return exportMode.value === 'all'
      ? '留空使用项目标题 + 本地时间，扩展名'
      : '留空使用页面标题 + 本地时间，扩展名'
  }

  return exportMode.value === 'all'
    ? '留空使用项目标题 + 本地时间'
    : '留空使用页面标题 + 本地时间'
})

const successTitle = computed(() => {
  return exportResult.value?.method === 'browser-print' ? '已打开打印对话框' : '导出成功'
})

const successMessage = computed(() => {
  const result = exportResult.value
  if (!result) {
    return ''
  }

  if (result.method === 'browser-print') {
    return result.message || `已准备 ${result.pageCount || 0} 个页面`
  }

  if (isPptxExportResult(result)) {
    return `已成功导出 ${result.pageCount || 0} 个页面，报告见下方明细`
  }

  return `已成功导出 ${result.pageCount || 0} 个页面`
})

/** PPTX 导出报告；其它方式没有报告，子组件据此不渲染。 */
const pptxReport = computed(() => {
  const result = exportResult.value
  return isPptxExportResult(result) ? result.report ?? null : null
})

watch(() => props.visible, (newValue) => {
  isVisible.value = newValue
})

watch(isVisible, (newValue) => {
  emit('update:visible', newValue)
})

/**
 * 关闭对话框；导出进行中不允许关闭，避免任务在后台继续而界面无反馈。
 */
function closeDialog(): void {
  if (isExporting.value) {
    return
  }

  isVisible.value = false
  resetDialog()
}

/**
 * 重置为表单态，保留用户已选的方式、范围与文件名。
 */
function resetDialog(): void {
  runner.resetRun()
}

/**
 * 按当前表单发起导出。
 */
function startExport(): void {
  void runner.startExport({
    method: exportMethod.value,
    mode: exportMode.value,
    filename: filename.value.trim() || undefined,
  })
}

/**
 * 取消当前导出；在飞的服务结果会被运行器判定为过期并丢弃。
 */
function cancelExport(): void {
  runner.cancelExport(exportMethod.value)
}

/**
 * 处理键盘事件。
 * @param event 键盘事件
 */
function handleKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape' && !isExporting.value) {
    closeDialog()
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
})

defineExpose({
  show: () => {
    isVisible.value = true
  },
  hide: () => {
    closeDialog()
  },
  reset: () => {
    resetDialog()
  }
})
</script>
