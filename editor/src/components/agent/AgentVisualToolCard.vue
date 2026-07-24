<!-- 文件功能：为图片理解与图片生成工具提供稳定的输入缩略图、进度和结果画廊回显。 -->
<template>
  <article class="overflow-hidden rounded-xl border border-violet-200 bg-gradient-to-br from-violet-50/80 to-white shadow-sm">
    <header class="flex items-start justify-between gap-3 border-b border-violet-100 px-3 py-2">
      <div class="min-w-0">
        <p class="text-xs font-bold text-slate-800">{{ isAnalysis ? '图片理解' : '图片生成' }}</p>
        <p class="mt-0.5 truncate text-[11px] text-slate-500">{{ subtitle }}</p>
      </div>
      <span class="rounded-full px-2 py-0.5 text-[10px] font-semibold" :class="statusClass">
        {{ statusText }}
      </span>
    </header>

    <div class="space-y-2 px-3 py-2.5">
      <div v-if="analysisPreviewAttachments.length" class="flex flex-wrap gap-1.5">
        <a v-for="attachment in analysisPreviewAttachments" :key="attachment.id" :href="attachment.url" target="_blank" class="h-12 w-12 overflow-hidden rounded-lg border border-slate-200 bg-white">
          <img :src="attachment.url" :alt="attachment.original_name" class="h-full w-full object-cover">
        </a>
      </div>

      <p v-if="summary" class="text-xs leading-5 text-slate-700">{{ summary }}</p>
      <div v-if="!isAnalysis && tool.outputAttachments.length" class="grid grid-cols-2 gap-2">
        <a v-for="attachment in tool.outputAttachments" :key="attachment.id" :href="attachment.url" target="_blank" class="group overflow-hidden rounded-lg border border-slate-200 bg-white">
          <img :src="attachment.url" :alt="attachment.original_name" class="aspect-square w-full object-cover transition group-hover:scale-[1.02]">
          <p class="truncate px-2 py-1 text-[10px] font-semibold text-slate-600">{{ attachment.original_name }}</p>
        </a>
      </div>
      <div v-if="!isAnalysis && outputAssets.length" class="flex flex-wrap gap-1">
        <span v-for="asset in outputAssets" :key="asset.id" class="rounded-md bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700">
          {{ asset.name }}
        </span>
      </div>

      <div class="flex items-center justify-between gap-2 border-t border-violet-100 pt-2">
        <UiButton variant="ghost" size="xs" class="text-violet-700 hover:text-violet-900" @click="$emit('openDetail')">查看工具详情</UiButton>
        <UiButton v-if="!isAnalysis && tool.outputAttachments.length" variant="ghost" size="xs" class="text-emerald-700 hover:text-emerald-900" @click="openAssetLibrary">
          已保存到资源库 →
        </UiButton>
      </div>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import type { ToolCallDetail } from '@/components/agent/agent-conversation-panel'
import { UiButton } from '@/components/ui'

const props = defineProps<{ tool: ToolCallDetail }>()
defineEmits<{ openDetail: [] }>()

const route = useRoute()
const router = useRouter()
const isAnalysis = computed(() => props.tool.toolName === 'analyze_visuals')
const input = computed<Record<string, unknown>>(() => isRecord(props.tool.inputPayload) ? props.tool.inputPayload : {})
const output = computed<Record<string, unknown>>(() => isRecord(props.tool.outputPayload) ? props.tool.outputPayload : {})
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
const subtitle = computed(() => {
  if (isAnalysis.value) return String(input.value.analysis_type || 'general')
  return props.tool.progress?.message || (input.value.operation === 'edit' ? '编辑图片' : '生成图片')
})
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
const statusClass = computed(() => {
  if (props.tool.status === 'error') return 'bg-rose-50 text-rose-700'
  if (props.tool.status === 'completed') return 'bg-emerald-50 text-emerald-700'
  return 'bg-sky-50 text-sky-700'
})
const phaseLabels: Record<string, string> = {
  queued: '排队中',
  running: '生成中',
  saving: '保存中',
  completed: '已完成',
  error: '失败',
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
