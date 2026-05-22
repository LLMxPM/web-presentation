<!-- 文件功能：渲染智能体工具调用详情弹窗。 -->
<template>
  <BaseDialog
    v-model="toolDetailDialogVisible"
    :title="activeToolDetail ? `工具调用 · ${resolveToolDetailName(activeToolDetail)}` : '工具调用详情'"
    width="720px"
  >
    <div v-if="activeToolDetail" class="space-y-4">
      <section class="rounded-2xl border border-slate-200 bg-slate-50/80 p-4">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p class="text-sm font-semibold text-slate-800">{{ resolveToolDetailName(activeToolDetail) }}</p>
            <div class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
              <span>{{ getToolSourceLabel(activeToolDetail.source) }}</span>
              <span v-if="activeToolDetail.memberAgentName">成员：{{ activeToolDetail.memberAgentName }}</span>
              <span v-if="activeToolDetail.toolCallId">调用 ID：{{ activeToolDetail.toolCallId }}</span>
              <span v-if="activeToolDetail.createdAt">{{ formatDateTime(activeToolDetail.createdAt) }}</span>
            </div>
          </div>
          <span class="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-600">
            {{ toolStatusLabelMap[activeToolDetail.status] }}
          </span>
        </div>
      </section>

      <section class="space-y-2">
        <h4 class="text-sm font-semibold text-slate-800">工具输入</h4>
        <pre class="max-h-[240px] overflow-auto rounded-2xl bg-slate-950 p-4 text-xs leading-6 text-slate-100">{{
          formatToolPayload(activeToolDetail.inputPayload, '历史消息未保留输入参数。') }}</pre>
      </section>

      <section class="space-y-2">
        <h4 class="text-sm font-semibold text-slate-800">工具输出</h4>
        <pre class="max-h-[280px] overflow-auto rounded-2xl bg-slate-950 p-4 text-xs leading-6 text-slate-100">{{
          formatToolPayload(activeToolDetail.outputPayload, activeToolDetail.message || '暂无输出。') }}</pre>
      </section>
    </div>
  </BaseDialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import BaseDialog from '@/components/ui/BaseDialog.vue'
import { formatToolPayload, type ToolCallDetail } from '@/components/agent/agent-conversation-panel'
import { getToolSourceLabel, toolStatusLabelMap } from '@/components/agent/agent-message-display'
import { formatDateTime } from '@/utils/format'

const props = defineProps<{
  activeToolDetail: ToolCallDetail | null
  toolDetailVisible: boolean
}>()

const emit = defineEmits<{
  'update:toolDetailVisible': [visible: boolean]
}>()

const toolDetailDialogVisible = computed({
  get: () => props.toolDetailVisible,
  set: value => emit('update:toolDetailVisible', value),
})

function resolveToolDetailName(tool: ToolCallDetail): string {
  return tool.memberAgentName ? `${tool.memberAgentName} · ${tool.toolName}` : tool.toolName
}
</script>
