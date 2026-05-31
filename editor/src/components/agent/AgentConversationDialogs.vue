<!-- 文件功能：渲染智能体工具调用详情弹窗。 -->
<template>
  <BaseDialog
    v-model="toolDetailDialogVisible"
    :title="activeToolDetail ? `工具调用 · ${resolveToolDetailName(activeToolDetail)}` : '工具调用详情'"
    width="720px"
    :z-index="memberRunDialogVisible ? 1010 : 1000"
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

  <BaseDialog
    v-model="memberRunDialogVisible"
    :title="selectedMemberRun ? `${selectedMemberRun.agent_name || selectedMemberRun.agent_id || '成员助手'}运行详情` : '成员助手运行详情'"
    width="860px"
    body-class="flex h-[calc(100vh-10rem)] max-h-[640px] flex-col overflow-hidden px-6 py-5"
  >
    <div v-if="selectedMemberRun" class="flex min-h-0 flex-1 flex-col gap-3">
      <div
        v-if="activeMemberRuns.length > 1"
        class="flex flex-wrap gap-1.5"
      >
        <button
          v-for="memberRun in activeMemberRuns"
          :key="memberRun.run_id"
          type="button"
          class="rounded-md border px-2 py-1 text-xs"
          :class="memberRun.run_id === selectedMemberRun.run_id ? 'border-sky-300 bg-sky-50 text-sky-700' : 'border-slate-200 bg-white text-slate-500'"
          @click="selectedMemberRunId = memberRun.run_id"
        >
          {{ memberRun.agent_name || memberRun.agent_id || '成员助手' }}
        </button>
      </div>

      <section class="rounded-lg border border-slate-200 bg-slate-50/80 px-3 py-2">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="min-w-0">
            <p class="truncate text-sm font-semibold text-slate-800">{{ selectedMemberRun.agent_name || selectedMemberRun.agent_id || '成员助手' }}</p>
            <p class="mt-0.5 text-xs text-slate-500">Run ID：{{ selectedMemberRun.run_id }}</p>
          </div>
          <span class="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-xs text-slate-600">
            {{ resolveMemberRunStatusLabel(selectedMemberRun.status) }}
          </span>
        </div>
      </section>

      <div class="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-slate-100 bg-white">
        <AgentConversationBody
          :timeline-display-items="selectedMemberTimelineItems"
          :draft-patches="[]"
          empty-conversation-text="暂无成员助手输出。"
          :loading="false"
          loading-text=""
          :last-run-issue="null"
          :active-run="null"
          :cancelling-run-force-available="false"
          :is-streaming="selectedMemberRun.status === 'running' || selectedMemberRun.status === 'pending'"
          :streaming-timeline-item-id="null"
          @open-tool-detail="toolId => emit('open-tool-detail', toolId)"
          @apply-suggested-patch="() => undefined"
          @remove-draft-patch="() => undefined"
          @force-cancel-run="() => undefined"
        />
      </div>
    </div>
  </BaseDialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import BaseDialog from '@/components/ui/BaseDialog.vue'
import AgentConversationBody from '@/components/agent/AgentConversationBody.vue'
import { buildTimelineDisplayItems, formatToolPayload, type ToolCallDetail } from '@/components/agent/agent-conversation-panel'
import { getToolSourceLabel, toolStatusLabelMap } from '@/components/agent/agent-message-display'
import type { AgentActiveRunStatus, AgentMemberRunItem } from '@/types/api'
import { formatDateTime } from '@/utils/format'

const props = defineProps<{
  activeToolDetail: ToolCallDetail | null
  toolDetailVisible: boolean
  activeMemberRuns: AgentMemberRunItem[]
  memberRunVisible: boolean
}>()

const emit = defineEmits<{
  'update:toolDetailVisible': [visible: boolean]
  'update:memberRunVisible': [visible: boolean]
  'open-tool-detail': [toolId: string]
}>()

const toolDetailDialogVisible = computed({
  get: () => props.toolDetailVisible,
  set: value => emit('update:toolDetailVisible', value),
})
const memberRunDialogVisible = computed({
  get: () => props.memberRunVisible,
  set: value => emit('update:memberRunVisible', value),
})
const selectedMemberRunId = ref<string | null>(null)
const selectedMemberRun = computed(() => (
  props.activeMemberRuns.find(item => item.run_id === selectedMemberRunId.value)
  ?? props.activeMemberRuns[0]
  ?? null
))
const selectedMemberTimelineItems = computed(() => (
  selectedMemberRun.value
    ? buildTimelineDisplayItems(selectedMemberRun.value.timeline_items)
    : []
))

watch(
  () => props.activeMemberRuns.map(item => item.run_id).join('|'),
  () => {
    selectedMemberRunId.value = props.activeMemberRuns[0]?.run_id ?? null
  },
  { immediate: true },
)

function resolveToolDetailName(tool: ToolCallDetail): string {
  return tool.memberAgentName ? `${tool.memberAgentName} · ${tool.toolName}` : tool.toolName
}

function resolveMemberRunStatusLabel(status: AgentActiveRunStatus): string {
  if (status === 'running' || status === 'pending') return '进行中'
  if (status === 'paused') return '待处理'
  if (status === 'failed') return '失败'
  if (status === 'cancelled' || status === 'cancelling') return '已停止'
  return '已完成'
}
</script>
