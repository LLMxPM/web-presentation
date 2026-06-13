<!-- 文件功能：渲染智能体工具调用详情弹窗。 -->
<template>
  <BaseDialog
    v-model="toolDetailDialogVisible"
    :title="activeToolDetail ? `工具调用 · ${resolveToolDetailName(activeToolDetail)}` : '工具调用详情'"
    size="wide"
    :z-index="memberRunDialogVisible ? 1010 : 1000"
  >
    <div v-if="activeToolDetail" class="space-y-4">
      <section class="rounded-2xl border border-slate-200 bg-slate-50/80 p-4">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="min-w-0">
            <p class="text-sm font-semibold text-slate-800">{{ resolveToolDetailName(activeToolDetail) }}</p>
            <div class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
              <span>{{ getToolSourceLabel(activeToolDetail.source) }}</span>
              <span v-if="activeToolDetail.memberAgentName">成员：{{ activeToolDetail.memberAgentName }}</span>
              <span v-if="activeToolDetail.toolCallId">调用 ID：{{ activeToolDetail.toolCallId }}</span>
              <span v-if="activeToolDetail.createdAt">{{ formatDateTime(activeToolDetail.createdAt) }}</span>
            </div>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <button
              type="button"
              class="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 shadow-sm transition hover:border-sky-200 hover:text-sky-700"
              title="复制工具调用详情"
              @click="copyActiveToolDetail"
            >
              <Copy class="h-3.5 w-3.5" />
              复制详情
            </button>
            <span class="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-600">
              {{ toolStatusLabelMap[activeToolDetail.status] }}
            </span>
          </div>
        </div>
      </section>

      <div class="grid gap-3 md:grid-cols-2">
        <section class="min-w-0 space-y-2">
          <h4 class="text-sm font-semibold text-slate-800">工具输入</h4>
          <pre class="max-h-[360px] overflow-auto whitespace-pre-wrap break-words rounded-2xl bg-slate-950 p-4 text-xs leading-6 text-slate-100">{{
            formatToolPayload(activeToolDetail.inputPayload, '历史消息未保留输入参数。') }}</pre>
        </section>

        <section class="min-w-0 space-y-2">
          <h4 class="text-sm font-semibold text-slate-800">工具输出</h4>
          <pre class="max-h-[360px] overflow-auto whitespace-pre-wrap break-words rounded-2xl bg-slate-950 p-4 text-xs leading-6 text-slate-100">{{
            formatToolPayload(activeToolDetail.outputPayload, activeToolDetail.message || '暂无输出。') }}</pre>
        </section>
      </div>
    </div>
  </BaseDialog>

  <BaseDialog
    v-model="memberRunDialogVisible"
    :title="selectedMemberRun ? `${selectedMemberRun.agent_name || selectedMemberRun.agent_id || '成员助手'}运行详情` : '成员助手运行详情'"
    size="standard"
    body-preset="dense"
    body-class="flex min-h-0 flex-col overflow-hidden"
  >
    <div v-if="selectedMemberRun" class="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden">
      <div
        v-if="activeMemberRuns.length > 1"
        class="max-h-24 shrink-0 overflow-y-auto pr-1"
      >
        <div class="flex flex-wrap gap-1.5">
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
      </div>

      <section class="shrink-0 rounded-lg border border-slate-200 bg-slate-50/80 px-3 py-2">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="min-w-0">
            <p class="truncate text-sm font-semibold text-slate-800">{{ selectedMemberRun.agent_name || selectedMemberRun.agent_id || '成员助手' }}</p>
            <p class="mt-0.5 break-all text-xs text-slate-500">Run ID：{{ selectedMemberRun.run_id }}</p>
          </div>
          <span class="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-xs text-slate-600">
            {{ resolveMemberRunStatusLabel(selectedMemberRun.status) }}
          </span>
        </div>
      </section>

      <div class="flex min-h-[180px] flex-1 flex-col overflow-hidden rounded-lg border border-slate-100 bg-white">
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
import { Copy } from '@lucide/vue'
import { computed, ref, watch } from 'vue'

import BaseDialog from '@/components/ui/BaseDialog.vue'
import AgentConversationBody from '@/components/agent/AgentConversationBody.vue'
import { buildTimelineDisplayItems, formatToolPayload, type ToolCallDetail } from '@/components/agent/agent-conversation-panel'
import { getToolSourceLabel, toolStatusLabelMap } from '@/components/agent/agent-message-display'
import type { AgentActiveRunStatus, AgentMemberRunItem } from '@/types/api'
import { formatDateTime } from '@/utils/format'
import { Message } from '@/utils/message'

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

/**
 * 复制当前工具调用详情，便于用户把工具上下文直接反馈给 LLM 或开发者。
 */
async function copyActiveToolDetail(): Promise<void> {
  if (!props.activeToolDetail) {
    return
  }
  try {
    await navigator.clipboard.writeText(buildToolDetailCopyText(props.activeToolDetail))
    Message.success('工具调用详情已复制。')
  } catch {
    Message.error('复制工具调用详情失败，请检查浏览器剪贴板权限。')
  }
}

/**
 * 生成工具详情复制文本；工具 id 使用工具注册名，缺失时再退回调用 id 或时间线项 id。
 * @param tool 当前弹窗展示的工具调用详情
 * @returns 分行展示的工具详情复制文本
 */
function buildToolDetailCopyText(tool: ToolCallDetail): string {
  const toolId = tool.toolName || tool.toolCallId || tool.id
  const input = formatToolPayload(tool.inputPayload, '历史消息未保留输入参数。')
  const output = formatToolPayload(tool.outputPayload, tool.message || '暂无输出。')
  return `工具id:${toolId}\nLLM输入:\n${input}\n工具输出:\n${output}`
}

function resolveMemberRunStatusLabel(status: AgentActiveRunStatus): string {
  if (status === 'running' || status === 'pending') return '进行中'
  if (status === 'paused') return '待处理'
  if (status === 'failed') return '失败'
  if (status === 'cancelled' || status === 'cancelling') return '已停止'
  return '已完成'
}
</script>

