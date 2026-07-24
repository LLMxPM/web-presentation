<!-- 文件功能：渲染页面详情的 Runtime 预览画布，保持主区域聚焦在实际页面效果。 -->
<template>
  <ToolPanel class="group relative h-full min-h-0 bg-[rgb(var(--ui-surface-muted))]" :scroll-body="false">
    <div class="absolute right-5 top-5 z-10 flex items-center gap-2 opacity-0 shadow-popover backdrop-blur transition-opacity duration-200 group-hover:opacity-100 focus-within:opacity-100">
      <UiIconButton
        label="刷新预览"
        :disabled="!props.previewFrameUrl"
        @click="emit('refresh')"
      >
        <RefreshCw class="h-4 w-4" />
      </UiIconButton>

      <UiIconButton
        label="放大查看"
        :disabled="!props.previewFrameUrl"
        @click="openPreviewDialog"
      >
        <Maximize2 class="h-4 w-4" />
      </UiIconButton>

      <UiIconButton
        :label="props.speakerNotesPanelOpen ? '关闭备注' : '打开备注'"
        @click="emit('toggleSpeakerNotes')"
      >
        <FileText class="h-4 w-4" />
      </UiIconButton>
    </div>

    <RuntimePreviewFrame
      :frame-url="activePreviewFrameUrl"
      title="runtime-preview"
      :viewport="props.previewViewport"
      layout="fill"
      container-class="h-full overflow-hidden bg-white"
      :empty-title="currentPreviewEmptyTitle"
      :empty-description="currentPreviewEmptyDescription"
    />

    <UiDialog
      :open="isPreviewDialogOpen"
      :title="previewDialogTitle"
      size="workbench"
      body-preset="immersive"
      overlay-class="bg-slate-950/70 backdrop-blur-sm"
      @update:open="isPreviewDialogOpen = $event"
    >
      <div class="h-full min-h-0 bg-slate-100 p-3">
        <RuntimePreviewFrame
          v-if="props.previewFrameUrl"
          :frame-url="props.previewFrameUrl"
          title="runtime-preview-dialog"
          :viewport="props.previewViewport"
          layout="fill"
          container-class="h-full overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"
        />
      </div>
    </UiDialog>
  </ToolPanel>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { FileText, Maximize2, RefreshCw } from '@lucide/vue'

import RuntimePreviewFrame from '@/components/runtime-preview/RuntimePreviewFrame.vue'
import ToolPanel from '@/components/patterns/ToolPanel.vue'
import { UiDialog, UiIconButton } from '@/components/ui'

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
  speakerNotesPanelOpen: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  refresh: []
  toggleSpeakerNotes: []
}>()

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

</script>
