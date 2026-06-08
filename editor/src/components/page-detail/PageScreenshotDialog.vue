<!-- 文件功能：展示页面截图信息、大图与下载入口，并提供重新截图操作。 -->
<template>
  <BaseDialog :model-value="props.modelValue" :title="`${props.pageTitle} · 页面截图`" size="wide" body-preset="editor"
    @update:model-value="emit('update:modelValue', $event)">
    <div class="flex h-full min-h-0 flex-col gap-4">
      <div class="flex items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
        <div class="min-w-0">
          <p class="text-sm font-semibold text-slate-900">{{ screenshotUpdatedText }}</p>
          <p v-if="props.screenshotUrl" class="mt-1 text-xs text-slate-500">截图版本：{{ screenshotVersionText }}</p>
        </div>
        <div class="flex items-center gap-2">
          <span v-if="shouldShowScreenshotOutdatedWarning"
            class="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-[11px] font-semibold text-amber-700">
            当前截图不是最新版本
          </span>
          <BaseButton
            v-if="props.screenshotUrl"
            variant="ghost"
            size="sm"
            @click="downloadScreenshot"
          >
            <Download class="h-3.5 w-3.5" />
            下载截图
          </BaseButton>
          <BaseButton
            variant="primary"
            size="sm"
            :disabled="props.screenshotDisabled"
            :loading="props.screenshotPending"
            @click="emit('save-screenshot')"
          >
            <Camera class="h-3.5 w-3.5" />
            重新截图
          </BaseButton>
        </div>
      </div>

      <div class="min-h-0 flex-1 overflow-hidden rounded-2xl border border-slate-200 bg-slate-50">
        <img
          v-if="props.screenshotUrl"
          :src="props.screenshotUrl"
          :alt="`${props.pageTitle} 页面截图大图`"
          class="block h-full w-full object-contain"
        >
        <div v-else class="flex h-full items-center justify-center px-6 text-center text-sm text-slate-400">
          暂无截图，点击“重新截图”后会在这里展示最新画面。
        </div>
      </div>
    </div>
  </BaseDialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Camera, Download } from '@lucide/vue'

import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import { formatDateTime } from '@/utils/format'
import { downloadPageScreenshot } from '@/utils/page-screenshot-download'

interface Props {
  modelValue: boolean
  pageTitle: string
  screenshotUrl: string | null
  screenshotVersionNo: number | null
  screenshotIsLatest: boolean
  screenshotUpdatedAt: string | null
  screenshotPending: boolean
  screenshotDisabled: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'save-screenshot': []
}>()

const screenshotUpdatedText = computed(() => (
  props.screenshotUpdatedAt ? `更新于 ${formatDateTime(props.screenshotUpdatedAt)}` : '尚未保存页面截图'
))

const screenshotVersionText = computed(() => (
  props.screenshotVersionNo ? `v${props.screenshotVersionNo}` : '未标记'
))

const shouldShowScreenshotOutdatedWarning = computed(() => (
  Boolean(props.screenshotUrl) && !props.screenshotIsLatest
))

/**
 * 使用后端下载参数触发浏览器下载，避免前端跨域读取对象存储图片。
 */
function downloadScreenshot(): void {
  if (!props.screenshotUrl) return
  downloadPageScreenshot(props.screenshotUrl, props.pageTitle, props.screenshotVersionNo)
}
</script>

