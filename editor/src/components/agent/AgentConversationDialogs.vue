<!-- 文件功能：渲染智能体工具调用详情弹窗。 -->
<template>
  <UiDialog
    :open="toolDetailDialogVisible"
    :title="activeToolDetail ? `工具调用 · ${resolveToolDetailName(activeToolDetail)}` : '工具调用详情'"
    size="wide"
    body-preset="dense"
    body-class="flex min-h-0 flex-col overflow-hidden"
    @update:open="toolDetailDialogVisible = $event"
  >
    <div v-if="activeToolDetail" class="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden">
      <section class="shrink-0 rounded-ui-lg border border-border bg-surface-muted p-4">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="min-w-0 flex-1">
            <div class="flex min-w-0 items-center gap-2">
              <p class="truncate text-sm font-semibold text-text">{{ resolveToolDetailName(activeToolDetail) }}</p>
              <UiBadge :tone="getToolStatusTone(activeToolDetail.status)" size="sm" class="shrink-0">
                {{ toolStatusLabelMap[activeToolDetail.status] }}
              </UiBadge>
            </div>
            <div class="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-text-secondary">
              <span>{{ getToolSourceLabel(activeToolDetail.source) }}</span>
              <span v-if="activeToolDetail.toolCallId" class="break-all">调用 ID：{{ activeToolDetail.toolCallId }}</span>
              <span v-if="activeToolDetail.createdAt">{{ formatDateTime(activeToolDetail.createdAt) }}</span>
            </div>
          </div>
          <UiButton
            variant="secondary"
            size="sm"
            class="shrink-0"
            title="复制工具调用详情"
            @click="copyActiveToolDetail"
          >
            <Copy class="h-3.5 w-3.5" />
            复制详情
          </UiButton>
        </div>
      </section>

      <div class="grid min-h-0 flex-1 grid-rows-2 gap-3 md:grid-cols-2 md:grid-rows-1">
        <section class="flex min-h-0 min-w-0 flex-col gap-2">
          <div class="flex shrink-0 items-center justify-between gap-2">
            <h4 class="text-sm font-semibold text-text">工具输入</h4>
            <UiIconButton
              label="复制工具输入"
              size="xs"
              @click="copyToolPayload('input')"
            >
              <Copy />
            </UiIconButton>
          </div>
          <pre class="tool-payload-scroll min-h-0 flex-1 overflow-auto overscroll-contain whitespace-pre-wrap break-words rounded-ui-lg border border-border bg-surface p-4 font-mono text-xs leading-6 text-text">{{
            formatToolPayload(activeToolDetail.inputPayload, '历史消息未保留输入参数。') }}</pre>
        </section>

        <section class="flex min-h-0 min-w-0 flex-col gap-2">
          <div class="flex shrink-0 items-center justify-between gap-2">
            <h4 class="text-sm font-semibold text-text">工具输出</h4>
            <UiIconButton
              label="复制工具输出"
              size="xs"
              @click="copyToolPayload('output')"
            >
              <Copy />
            </UiIconButton>
          </div>
          <pre class="tool-payload-scroll min-h-0 flex-1 overflow-auto overscroll-contain whitespace-pre-wrap break-words rounded-ui-lg border border-border bg-surface p-4 font-mono text-xs leading-6 text-text">{{
            formatToolPayload(activeToolDetail.outputPayload, activeToolDetail.message || '暂无输出。') }}</pre>
        </section>
      </div>
    </div>
  </UiDialog>

</template>

<script setup lang="ts">
import { Copy } from '@lucide/vue'
import { computed } from 'vue'

import { UiBadge, UiButton, UiDialog, UiIconButton } from '@/components/ui'
import { formatToolPayload, type ToolCallDetail } from '@/components/agent/agent-conversation-panel'
import { getToolSourceLabel, getToolStatusTone, toolStatusLabelMap } from '@/components/agent/agent-message-display'
import { formatDateTime } from '@/utils/format'
import { Message } from '@/utils/message'

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
  return tool.toolName
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

/**
 * 复制当前工具的输入或输出格式化内容；内容为空时仅提示，不写入占位文案。
 */
async function copyToolPayload(kind: 'input' | 'output'): Promise<void> {
  const tool = props.activeToolDetail
  if (!tool) {
    return
  }
  const label = kind === 'input' ? '工具输入' : '工具输出'
  const text = formatToolPayload(kind === 'input' ? tool.inputPayload : tool.outputPayload, '')
  if (!text.trim()) {
    Message.warning(`${label}为空。`)
    return
  }
  try {
    await navigator.clipboard.writeText(text)
    Message.success(`${label}已复制。`)
  } catch {
    Message.error(`复制${label}失败，请检查浏览器剪贴板权限。`)
  }
}

</script>

