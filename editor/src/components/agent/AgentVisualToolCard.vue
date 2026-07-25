<!-- 文件功能：为图片理解与图片生成工具提供稳定的输入缩略图、进度和结果画廊回显。 -->
<template>
  <details class="visual-tool-details rounded-ui-md border border-border bg-surface-hover" :open="tool.status !== 'completed'">
    <summary class="flex min-h-control-sm cursor-pointer select-none items-center gap-1.5 px-2 text-xs font-medium text-text-muted transition-colors hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-border-focus">
      <ChevronRight class="visual-tool-chevron h-3 w-3 shrink-0 transition" />
      <span class="min-w-0 flex-1 truncate">{{ isAnalysis ? '图片理解' : '图片生成' }}</span>
      <UiBadge :tone="statusTone" size="sm">{{ statusText }}</UiBadge>
    </summary>

    <div class="space-y-2 border-t border-border bg-surface px-2 py-2">
      <p v-if="detailLabel" class="text-xs text-text-muted">{{ detailLabel }}</p>
      <div v-if="analysisPreviewAttachments.length" class="flex max-h-20 flex-wrap gap-1.5 overflow-y-auto">
        <button
          v-for="attachment in analysisPreviewAttachments"
          :key="attachment.id"
          type="button"
          class="h-16 w-16 shrink-0 overflow-hidden rounded-ui-md border border-border bg-surface transition hover:border-border-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-border-focus"
          :aria-label="`预览图片 ${attachment.original_name}`"
          @click="openImagePreview(attachment)"
        >
          <img :src="attachment.url" :alt="attachment.original_name" class="h-full w-full object-cover">
        </button>
      </div>

      <p v-if="summary" class="text-xs leading-5 text-text-secondary">{{ summary }}</p>
      <div v-if="!isAnalysis && tool.outputAttachments.length" class="grid grid-cols-2 gap-2">
        <button
          v-for="attachment in tool.outputAttachments"
          :key="attachment.id"
          type="button"
          class="group min-w-0 overflow-hidden rounded-ui-md border border-border bg-surface text-left transition hover:border-border-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-border-focus"
          :aria-label="`预览图片 ${attachment.original_name}`"
          @click="openImagePreview(attachment)"
        >
          <img :src="attachment.url" :alt="attachment.original_name" class="h-32 max-h-32 w-full object-cover transition group-hover:scale-[1.02]">
          <p class="truncate px-2 py-1 text-xs font-medium text-text-secondary">{{ attachment.original_name }}</p>
        </button>
      </div>
      <div v-if="!isAnalysis && outputAssets.length" class="flex flex-wrap gap-1">
        <UiBadge v-for="asset in outputAssets" :key="asset.id" tone="success" size="sm">{{ asset.name }}</UiBadge>
      </div>

      <div class="flex items-center justify-between gap-2 border-t border-border pt-1.5">
        <UiButton variant="ghost" size="xs" @click="$emit('openDetail')">查看工具详情</UiButton>
        <UiButton v-if="!isAnalysis && tool.outputAttachments.length" variant="ghost" size="xs" @click="openAssetLibrary">
          已保存到资源库 →
        </UiButton>
      </div>
    </div>
  </details>

  <UiDialog
    :open="!!previewAttachment"
    size="workbench"
    body-preset="immersive"
    :show-header="false"
    :show-close-button="false"
    :panel-style="{ background: 'transparent' }"
    panel-class="!pointer-events-none !border-0 !bg-transparent !shadow-none"
    overlay-class="bg-slate-900/90 backdrop-blur-md"
    :z-index="1200"
    @update:open="handlePreviewVisibleChange"
  >
    <div v-if="previewAttachment" class="pointer-events-none relative flex h-full min-h-0 items-center justify-center p-4 sm:p-6">
      <img
        :src="previewAttachment.url"
        :alt="previewAttachment.original_name"
        class="pointer-events-auto relative max-h-full max-w-full rounded-lg object-contain shadow-2xl drop-shadow-2xl"
      >
      <BaseCloseButton
        class="pointer-events-auto absolute right-3 top-3 sm:right-6 sm:top-6"
        tone="inverse"
        label="关闭图片预览"
        @click="previewAttachment = null"
      />
      <div class="pointer-events-none absolute bottom-3 left-1/2 max-w-[80%] -translate-x-1/2 truncate rounded-full bg-slate-800/60 px-4 py-2 text-xs tracking-widest text-white backdrop-blur sm:bottom-6">
        {{ previewAttachment.original_name }}
      </div>
    </div>
  </UiDialog>
</template>

<script setup lang="ts">
import { ChevronRight } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import type { ToolCallDetail } from '@/components/agent/agent-conversation-panel'
import BaseCloseButton from '@/components/ui/BaseCloseButton.vue'
import { UiBadge, UiButton, UiDialog } from '@/components/ui'

const props = defineProps<{ tool: ToolCallDetail }>()
defineEmits<{ openDetail: [] }>()

const route = useRoute()
const router = useRouter()
type VisualAttachment = ToolCallDetail['outputAttachments'][number]
const previewAttachment = ref<VisualAttachment | null>(null)
const isAnalysis = computed(() => props.tool.toolName === 'analyze_visuals')
const input = computed<Record<string, unknown>>(() => isRecord(props.tool.inputPayload) ? props.tool.inputPayload : {})
const output = computed<Record<string, unknown>>(() => isRecord(props.tool.outputPayload) ? props.tool.outputPayload : {})
const detailLabel = computed(() => {
  if (isAnalysis.value) {
    const analysisType = String(input.value.analysis_type || '')
    return analysisType ? (analysisTypeLabels[analysisType] || '图片分析') : ''
  }
  return input.value.operation === 'edit' ? '编辑图片' : ''
})
const analysisPreviewAttachments = computed(() => {
  if (!isAnalysis.value) return []
  const byId = new Map<number, (typeof props.tool.inputAttachments)[number]>()
  for (const attachment of [...props.tool.inputAttachments, ...props.tool.outputAttachments]) {
    byId.set(attachment.id, attachment)
  }
  return [...byId.values()]
})
const outputAssets = computed(() => (
  Array.isArray(output.value.assets)
    ? output.value.assets.filter((item): item is { id: number, name: string } => (
        isRecord(item) && typeof item.id === 'number' && typeof item.name === 'string'
      ))
    : []
))
const summary = computed(() => {
  if (isAnalysis.value) return String(output.value.summary || props.tool.message || '')
  if (outputAssets.value.length) return `已生成 ${outputAssets.value.length} 张图片，并创建工作空间资源。`
  return props.tool.progress?.message || props.tool.message || ''
})
const statusText = computed(() => {
  if (props.tool.status === 'error') return '失败'
  if (props.tool.status === 'completed') return '已完成'
  return phaseLabels[String(props.tool.progress?.phase || 'running')] || '处理中'
})
const statusTone = computed(() => {
  if (props.tool.status === 'error') return 'danger' as const
  if (props.tool.status === 'completed') return 'success' as const
  return 'info' as const
})
const phaseLabels: Record<string, string> = {
  queued: '排队中',
  running: '生成中',
  saving: '保存中',
  completed: '已完成',
  error: '失败',
}
const analysisTypeLabels: Record<string, string> = {
  general: '通用分析',
  ocr: '文字识别',
  layout: '布局分析',
  comparison: '图片对比',
  presentation_fit: '演示适配分析',
}

/** 在当前页面的统一沉浸式预览层中查看工具图片。 */
function openImagePreview(attachment: VisualAttachment) {
  previewAttachment.value = attachment
}

/** 响应预览层遮罩和 Esc 关闭，并保留受控弹窗状态。 */
function handlePreviewVisibleChange(open: boolean) {
  if (!open) {
    previewAttachment.value = null
  }
}

/** 跳转当前工作空间资源库；缺少路由参数时保留在对话并由详情兜底。 */
function openAssetLibrary() {
  const workspaceId = Number(route.params.workspaceId)
  if (Number.isFinite(workspaceId) && workspaceId > 0) {
    void router.push({ name: 'assets', params: { workspaceId } })
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}
</script>

<style scoped>
.visual-tool-details > summary {
  list-style: none;
}

.visual-tool-details > summary::-webkit-details-marker {
  display: none;
}

.visual-tool-details[open] .visual-tool-chevron {
  transform: rotate(90deg);
}
</style>
