<!-- 文件功能：渲染智能体 run-first 时间线正文、草稿箱、工具调用与运行状态提示。 -->
<template>
  <div
    ref="scrollContainerRef"
    class="flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto px-2 py-2"
    @scroll="handleConversationScroll"
  >
    <section v-if="draftPatches.length" class="space-y-1.5">
      <div class="flex items-center justify-between gap-2">
        <h3 class="text-[11px] font-semibold uppercase tracking-wide text-slate-500">草稿箱</h3>
        <span class="text-[10px] text-slate-400">{{ draftPatches.length }} 条</span>
      </div>
      <div class="space-y-1.5">
        <article
          v-for="draft in draftPatches"
          :key="`${draft.tool_name}-${draft.unified_diff}`"
          class="rounded-lg border border-amber-200 bg-amber-50/80 p-2"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <p class="text-[13px] font-semibold text-amber-800">{{ draft.change_note || '页面改写草稿' }}</p>
              <p class="mt-0.5 text-[11px] text-amber-700">来自 {{ draft.tool_name }}</p>
            </div>
            <div class="flex items-center gap-1.5">
              <BaseButton variant="ghost" size="sm" @click="$emit('apply-suggested-patch', draft)">
                应用
              </BaseButton>
              <BaseButton variant="ghost" size="sm" @click="$emit('remove-draft-patch', draft)">
                移除
              </BaseButton>
            </div>
          </div>
        </article>
      </div>
    </section>

    <section class="flex min-h-[140px] flex-1 flex-col">
      <div class="flex flex-1 flex-col gap-1 py-0.5">
        <div
          v-if="loading"
          class="flex min-h-[140px] flex-col items-center justify-center gap-2 text-center text-[12px] leading-5 text-slate-400"
          role="status"
          aria-live="polite"
        >
          <span class="h-5 w-5 animate-spin rounded-full border-2 border-sky-200 border-t-sky-500" aria-hidden="true" />
          <span>{{ loadingText }}</span>
        </div>

        <div
          v-else-if="timelineDisplayItems.length === 0"
          class="flex min-h-[140px] items-center justify-center text-center text-[12px] leading-5 text-slate-400"
        >
          {{ emptyConversationText }}
        </div>

        <template v-for="item in timelineDisplayItems" :key="item.id">
          <article
            v-if="item.kind === 'message'"
            class="conversation-message flex px-0.5 py-0"
            :class="item.message.role === 'user' ? 'conversation-message--user justify-end' : 'conversation-message--assistant justify-start'"
          >
            <div class="message-group min-w-0" :class="item.message.role === 'user' ? 'max-w-[92%]' : 'w-[92%]'">
              <div
                class="message-shell min-w-0"
                :class="item.message.role === 'user'
                  ? 'rounded-md border border-slate-200 bg-slate-100 px-2.5 py-1 text-slate-700'
                  : 'px-1 py-0.5 text-slate-700'"
              >
                <div v-if="item.message.role === 'assistant'" class="assistant-markdown">
                  <p v-if="shouldShowAssistantPlaceholder(item)" class="text-[13px] leading-[18px] text-slate-400">...</p>
                  <MarkdownRender
                    v-else-if="resolveMessageContent(item.message)"
                    :nodes="resolveMessageMarkdownNodes(item.message)"
                    :max-live-nodes="isMessageStreaming(item.message) ? 0 : 320"
                    batch-rendering
                    :initial-render-batch-size="assistantBatchRendering.initialRenderBatchSize"
                    :render-batch-size="assistantBatchRendering.renderBatchSize"
                    :render-batch-delay="assistantBatchRendering.renderBatchDelay"
                    :render-batch-budget-ms="assistantBatchRendering.renderBatchBudgetMs"
                  />
                </div>
                <div v-else>
                  <pre class="whitespace-pre-wrap break-words text-[12.5px] font-sans leading-[17px]">{{ item.message.content || '...' }}</pre>
                </div>
              </div>
              <div
                v-if="item.message.role === 'user' && item.message.created_at"
                class="message-time mt-0.5 px-1 text-right text-[10px] font-medium text-slate-400"
              >
                {{ formatMessageTime(item.message.created_at) }}
              </div>
            </div>
          </article>

          <article v-else-if="item.kind === 'reasoning'" class="conversation-message conversation-message--assistant flex justify-start px-0.5 py-0">
            <div class="message-group w-[92%] min-w-0 px-1 py-0.5">
              <details class="reasoning-details text-slate-500" :open="item.streaming">
                <summary class="inline-flex cursor-pointer select-none items-center gap-0.5 rounded px-1 py-0 font-medium text-slate-400 transition hover:bg-slate-50 hover:text-slate-600">
                  <ChevronRight class="h-2.5 w-2.5 transition details-chevron" />
                  <span>{{ item.streaming ? '思考中' : '思考过程' }}</span>
                  <span v-if="item.streaming" class="thinking-dots" aria-hidden="true">
                    <span />
                    <span />
                    <span />
                  </span>
                </summary>
                <div class="reasoning-markdown mt-0.5 max-h-[100px] overflow-auto border-l border-slate-100 pl-1.5">
                  <MarkdownRender
                    :nodes="resolveReasoningMarkdownNodes(item)"
                    :max-live-nodes="item.streaming ? 0 : 160"
                    batch-rendering
                    :initial-render-batch-size="assistantBatchRendering.initialRenderBatchSize"
                    :render-batch-size="assistantBatchRendering.renderBatchSize"
                    :render-batch-delay="assistantBatchRendering.renderBatchDelay"
                    :render-batch-budget-ms="assistantBatchRendering.renderBatchBudgetMs"
                  />
                </div>
              </details>
            </div>
          </article>

          <article v-else-if="item.kind === 'feedback_request'" class="conversation-message conversation-message--assistant flex justify-start px-0.5 py-0">
            <div class="message-group w-[92%] min-w-0 px-1 py-0.5">
              <div class="rounded-md border border-sky-100 border-l-[3px] border-l-sky-400 bg-sky-50/65 px-2.5 py-1.5 text-slate-700 shadow-[0_1px_0_rgba(14,165,233,0.06)]">
                <div
                  v-for="(entry, entryIndex) in item.entries"
                  :key="`${entry.question}-${entryIndex}`"
                  class="border-t border-sky-100/70 pt-1.5 first:border-t-0 first:pt-0"
                >
                  <p class="break-words text-[12.5px] font-medium leading-[18px] text-slate-700">{{ entry.question }}</p>
                  <p
                    class="mt-1 inline-flex max-w-full break-words rounded bg-white/70 px-1.5 py-0.5 text-[11.5px] leading-4"
                    :class="entry.answerText ? 'text-slate-700' : 'text-sky-500'"
                  >
                    {{ entry.answerText || '未回复' }}
                  </p>
                </div>
              </div>
            </div>
          </article>

          <article v-else-if="item.kind === 'tool_group'" class="conversation-message conversation-message--assistant flex justify-start px-0.5 py-0">
            <div class="message-group w-[92%] min-w-0 px-1 py-0.5">
              <template v-if="item.tools.length === 1">
                <button
                  v-for="tool in item.tools"
                  :key="tool.id"
                  type="button"
                  class="tool-call-row flex w-full min-w-0 items-center justify-between gap-2 border border-slate-200/80 bg-slate-50/60 px-1.5 py-0.5 text-left text-[10px] transition hover:bg-slate-100/70"
                  :class="getToolChipClass(tool.status)"
                  @click="handleToolRowClick(tool)"
                >
                  <span class="min-w-0 truncate">{{ resolveToolDisplayName(tool) }}</span>
                  <span class="shrink-0 opacity-60" aria-hidden="true">{{ toolStatusLabelMap[tool.status] }}</span>
                </button>
              </template>
              <details v-else class="tool-call-group" :open="shouldExpandToolGroup(item.tools)">
                <summary class="flex cursor-pointer select-none items-center gap-1.5 border border-slate-200/80 bg-slate-50/60 px-1.5 py-0.5 text-[10px] text-slate-500 transition hover:bg-slate-100/70">
                  <ChevronRight class="h-2.5 w-2.5 transition details-chevron" />
                  <span class="min-w-0 flex-1 truncate">{{ formatToolGroupSummary(item.tools) }}</span>
                </summary>
                <div class="mt-1 space-y-1">
                  <button
                    v-for="tool in item.tools"
                    :key="tool.id"
                    type="button"
                    class="tool-call-row flex w-full min-w-0 items-center justify-between gap-2 border border-slate-200/80 bg-slate-50/60 px-1.5 py-0.5 text-left text-[10px] transition hover:bg-slate-100/70"
                    :class="getToolChipClass(tool.status)"
                    @click="handleToolRowClick(tool)"
                  >
                    <span class="min-w-0 truncate">{{ resolveToolDisplayName(tool) }}</span>
                    <span class="shrink-0 opacity-60" aria-hidden="true">{{ toolStatusLabelMap[tool.status] }}</span>
                  </button>
                </div>
              </details>
            </div>
          </article>

          <article v-else-if="item.kind === 'run_status'" class="conversation-message conversation-message--run-status px-4 py-1">
            <div class="flex w-full items-center gap-2">
              <span class="h-px flex-1" :class="getRunStatusLineClass(item.status)" />
              <span
                class="inline-flex max-w-[80%] shrink-0 items-center gap-1.5 rounded-full px-2 py-0.5 text-[10.5px] font-medium leading-4"
                :class="getRunStatusBadgeClass(item.status)"
              >
                <span class="h-1.5 w-1.5 shrink-0 rounded-full" :class="getRunStatusDotClass(item.status)" />
                <span class="min-w-0 truncate">{{ item.content }}</span>
                <span v-if="shouldAnimateRunStatus(item.status)" class="thinking-dots shrink-0" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                </span>
              </span>
              <span class="h-px flex-1" :class="getRunStatusLineClass(item.status)" />
            </div>
          </article>

          <article
            v-else
            class="conversation-message conversation-message--system flex justify-start px-0.5 py-0"
          >
            <div
              class="message-group max-w-[92%] rounded-md border px-2 py-1 text-[11px] leading-5"
              :class="getRequirementStatusClass(item.status)"
            >
              {{ item.content }}
            </div>
          </article>
        </template>
      </div>
    </section>

    <section v-if="lastRunIssue" class="space-y-1.5 rounded-xl border border-amber-200 bg-amber-50/80 px-3 py-2.5">
      <p class="text-[12.5px] font-semibold text-amber-800">{{ lastRunIssue.title }}</p>
      <p class="text-[12px] leading-5 text-amber-700">{{ lastRunIssue.detail }}</p>
    </section>

    <section
      v-if="activeRun?.status === 'cancelling'"
      class="flex items-center justify-between gap-3 rounded-3xl border border-amber-200 bg-amber-50/80 p-4"
    >
      <div class="min-w-0">
        <p class="text-sm font-semibold text-amber-800">正在停止当前运行</p>
        <p class="mt-1 text-xs leading-5 text-amber-700">如果长时间没有响应，可以强制释放当前会话占用。</p>
      </div>
      <BaseButton v-if="cancellingRunForceAvailable" variant="secondary" size="sm" @click="$emit('force-cancel-run')">
        强制结束
      </BaseButton>
    </section>
  </div>
</template>

<script setup lang="ts">
import 'markstream-vue/index.css'
import MarkdownRender, { getMarkdown, parseMarkdownToStructure } from 'markstream-vue'
import { ChevronRight } from '@lucide/vue'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import BaseButton from '@/components/ui/BaseButton.vue'
import {
  createMessageStreamingResolver,
  formatMessageTime,
  formatToolGroupSummary,
  getToolChipClass,
  resolveMessageContent,
  resolveMessageMarkdownNodes as buildMessageMarkdownNodes,
  shouldExpandToolGroup,
  shouldShowAssistantPlaceholder as shouldDisplayAssistantPlaceholder,
  toolStatusLabelMap,
} from '@/components/agent/agent-message-display'
import type { TimelineDisplayItem, ToolCallDetail } from '@/components/agent/agent-conversation-panel'
import type { AgentActiveRunItem, AgentMessageItem, AgentSuggestedPatch } from '@/types/api'

const props = defineProps<{
  timelineDisplayItems: TimelineDisplayItem[]
  draftPatches: AgentSuggestedPatch[]
  emptyConversationText: string
  loading: boolean
  loadingText: string
  lastRunIssue: { title: string, detail: string } | null
  activeRun: AgentActiveRunItem | null
  cancellingRunForceAvailable: boolean
  isStreaming: boolean
  streamingTimelineItemId: string | null
}>()

const emit = defineEmits<{
  'apply-suggested-patch': [patch: AgentSuggestedPatch]
  'remove-draft-patch': [patch: AgentSuggestedPatch]
  'open-tool-detail': [toolId: string]
  'open-member-run-detail': [toolId: string]
  'force-cancel-run': []
}>()

const markdownParser = getMarkdown()
const markdownNodeCache = new Map<string, ReturnType<typeof buildMessageMarkdownNodes>>()
const scrollContainerRef = ref<HTMLElement | null>(null)
const autoScrollEnabled = ref(true)
let scrollAnimationFrame: number | null = null
const assistantBatchRendering = {
  initialRenderBatchSize: 12,
  renderBatchSize: 16,
  renderBatchDelay: 8,
  renderBatchBudgetMs: 6,
}
const isMessageStreaming = createMessageStreamingResolver(
  () => props.isStreaming,
  () => props.streamingTimelineItemId,
)

watch(
  () => buildConversationChangeSignature(),
  () => {
    scheduleAutoScrollToBottom()
  },
  { flush: 'post' },
)

onMounted(() => {
  scheduleAutoScrollToBottom()
})

onBeforeUnmount(() => {
  if (scrollAnimationFrame !== null) {
    window.cancelAnimationFrame(scrollAnimationFrame)
  }
})

/**
 * 只有空 assistant 占位才显示省略号。
 */
function shouldShowAssistantPlaceholder(item: Extract<TimelineDisplayItem, { kind: 'message' }>) {
  return shouldDisplayAssistantPlaceholder({ message: item.message, embeddedTools: [] }, isMessageStreaming)
}

/**
 * 按 markstream-vue 文档推荐，流式场景预解析为 nodes 再交给渲染器。
 */
function resolveMessageMarkdownNodes(message: AgentMessageItem) {
  return readMarkdownCache(
    buildMarkdownCacheKey('content', message.id, message.content, isMessageStreaming(message)),
    () => buildMessageMarkdownNodes(message, markdownParser, isMessageStreaming),
  )
}

/**
 * 思考过程作为独立时间线项渲染。
 */
function resolveReasoningMarkdownNodes(item: Extract<TimelineDisplayItem, { kind: 'reasoning' }>) {
  return readMarkdownCache(
    buildMarkdownCacheKey('reasoning', item.id, item.content, item.streaming),
    () => parseMarkdownToStructure(item.content, markdownParser, { final: !item.streaming }),
  )
}

/**
 * Team 成员工具调用在消息流中展示成员来源，避免与内容助手直连工具混淆。
 */
function resolveToolDisplayName(tool: ToolCallDetail) {
  if (tool.delegatedMemberRuns.length === 1) {
    return `${tool.delegatedMemberRuns[0].agent_name || tool.delegatedMemberRuns[0].agent_id || '成员助手'}运行`
  }
  if (tool.delegatedMemberRuns.length > 1) {
    return `成员助手运行 · ${tool.delegatedMemberRuns.length} 个`
  }
  return tool.memberAgentName ? `${tool.memberAgentName} · ${tool.toolName}` : tool.toolName
}

function handleToolRowClick(tool: ToolCallDetail) {
  if (tool.delegatedMemberRuns.length) {
    emit('open-member-run-detail', tool.id)
    return
  }
  emit('open-tool-detail', tool.id)
}

/**
 * 用户靠近底部时自动跟随新输出；手动上滑后保持当前位置，避免阅读历史时被拉回底部。
 */
function handleConversationScroll() {
  const container = scrollContainerRef.value
  if (!container) {
    return
  }
  autoScrollEnabled.value = isNearConversationBottom(container)
}

function scheduleAutoScrollToBottom() {
  if (!autoScrollEnabled.value) {
    return
  }
  void nextTick(() => {
    if (!autoScrollEnabled.value) {
      return
    }
    if (scrollAnimationFrame !== null) {
      window.cancelAnimationFrame(scrollAnimationFrame)
    }
    scrollAnimationFrame = window.requestAnimationFrame(() => {
      scrollAnimationFrame = null
      const container = scrollContainerRef.value
      if (!container || !autoScrollEnabled.value) {
        return
      }
      container.scrollTop = container.scrollHeight
    })
  })
}

function isNearConversationBottom(container: HTMLElement) {
  return container.scrollHeight - container.scrollTop - container.clientHeight <= 80
}

function buildConversationChangeSignature() {
  const lastItem = props.timelineDisplayItems.at(-1)
  return [
    props.timelineDisplayItems.length,
    lastItem?.id ?? '',
    lastItem && 'content' in lastItem ? lastItem.content.length : '',
    lastItem?.kind === 'feedback_request'
      ? lastItem.entries.map(entry => `${entry.question}:${entry.answerText ?? ''}`).join('|')
      : '',
    lastItem?.kind === 'tool_group' ? lastItem.tools.map(tool => `${tool.id}:${tool.status}`).join(',') : '',
    props.lastRunIssue?.detail ?? '',
    props.activeRun?.status ?? '',
  ].join('|')
}

function buildMarkdownCacheKey(kind: 'content' | 'reasoning', id: string, content: string, streaming: boolean) {
  return [
    kind,
    id,
    streaming ? 'live' : 'final',
    content,
  ].join('\u001f')
}

function readMarkdownCache(
  key: string,
  factory: () => ReturnType<typeof buildMessageMarkdownNodes>,
) {
  const cached = markdownNodeCache.get(key)
  if (cached) {
    return cached
  }
  const value = factory()
  markdownNodeCache.set(key, value)
  trimMarkdownCache()
  return value
}

function trimMarkdownCache() {
  const maxEntries = 160
  while (markdownNodeCache.size > maxEntries) {
    const firstKey = markdownNodeCache.keys().next().value
    if (!firstKey) {
      return
    }
    markdownNodeCache.delete(firstKey)
  }
}

function getRunStatusBadgeClass(status: string | null) {
  if (status === 'failed') return 'bg-red-50 text-red-600 ring-1 ring-red-100'
  if (status === 'cancelled' || status === 'cancelling') return 'bg-amber-50 text-amber-600 ring-1 ring-amber-100'
  if (status === 'completed') return 'bg-slate-50 text-slate-400 ring-1 ring-slate-100'
  return 'bg-sky-50 text-sky-600 ring-1 ring-sky-100'
}

function getRunStatusDotClass(status: string | null) {
  if (status === 'failed') return 'bg-red-400'
  if (status === 'cancelled' || status === 'cancelling') return 'bg-amber-400'
  if (status === 'completed') return 'bg-slate-300'
  return 'bg-sky-400'
}

function getRunStatusLineClass(status: string | null) {
  if (status === 'failed') return 'bg-red-100'
  if (status === 'cancelled' || status === 'cancelling') return 'bg-amber-100'
  if (status === 'completed') return 'bg-slate-100'
  return 'bg-sky-100'
}

/**
 * 运行中的模型请求状态用省略号提示用户仍在等待输出。
 */
function shouldAnimateRunStatus(status: string | null) {
  return status === 'model_request'
}

function getRequirementStatusClass(status: string | null) {
  if (status === 'failed') return 'border-red-100 bg-red-50/70 text-red-600'
  if (status === 'cancelled' || status === 'cancelling') return 'border-amber-100 bg-amber-50/70 text-amber-700'
  if (status === 'paused' || status === 'pending') return 'border-sky-100 bg-sky-50/70 text-sky-700'
  return 'border-slate-100 bg-slate-50/70 text-slate-500'
}
</script>

<style scoped>
details[open] .details-chevron {
  transform: rotate(90deg);
}

.reasoning-details > summary {
  list-style: none;
}

.reasoning-details > summary::-webkit-details-marker {
  display: none;
}

.tool-call-group > summary {
  list-style: none;
}

.tool-call-group > summary::-webkit-details-marker {
  display: none;
}

.tool-call-row,
.tool-call-group > summary {
  border-radius: 0.25rem;
}

.assistant-markdown {
  font-size: 0.8125rem;
  line-height: 1.32;
}

.assistant-markdown :deep(.markstream-vue) {
  background: transparent;
  color: inherit;
  font-size: 0.8125rem;
  line-height: 1.32;
}

.assistant-markdown :deep(.markstream-vue > :first-child),
.reasoning-markdown :deep(.markstream-vue > :first-child) {
  margin-top: 0;
}

.assistant-markdown :deep(.markstream-vue > :last-child),
.reasoning-markdown :deep(.markstream-vue > :last-child) {
  margin-bottom: 0;
}

.assistant-markdown :deep(.markstream-vue > * + *) {
  margin-top: 0.2rem;
}

.assistant-markdown :deep(p) {
  margin: 0;
  font-size: 0.8125rem;
  line-height: 1.32;
}

.assistant-markdown :deep(ul),
.assistant-markdown :deep(ol) {
  margin-top: 0.2rem;
  margin-bottom: 0.2rem;
  padding-left: 1.1rem;
  font-size: 0.8125rem;
  line-height: 1.32;
}

.assistant-markdown :deep(li) {
  font-size: 0.8125rem;
  line-height: 1.32;
}

.assistant-markdown :deep(pre) {
  margin: 0.25rem 0 0;
  overflow-x: auto;
  border-radius: 0.25rem;
}

.assistant-markdown :deep(code:not(pre code)) {
  border-radius: 0.25rem;
  background: rgb(226 232 240 / 0.8);
  padding: 0.0625rem 0.25rem;
  font-size: 0.75rem;
}

.assistant-markdown :deep(a) {
  color: rgb(2 132 199);
  text-decoration: underline;
  text-underline-offset: 0.2em;
}

.reasoning-details {
  font-size: 0.6875rem;
  line-height: 1.25;
}

.reasoning-markdown :deep(.markstream-vue) {
  background: transparent;
  color: rgb(100 116 139);
  font-size: 0.6875rem;
  line-height: 1.28;
  white-space: pre-wrap;
}

.reasoning-markdown :deep(.markstream-vue > * + *) {
  margin-top: 0.15rem;
}

.reasoning-markdown :deep(p),
.reasoning-markdown :deep(li) {
  margin: 0;
  font-size: 0.6875rem;
  line-height: 1.28;
}

.reasoning-markdown :deep(ul),
.reasoning-markdown :deep(ol) {
  margin-top: 0.15rem;
  margin-bottom: 0.15rem;
  padding-left: 0.9rem;
  font-size: 0.6875rem;
  line-height: 1.28;
}

.reasoning-markdown :deep(pre) {
  margin: 0.2rem 0 0;
  overflow-x: auto;
  border-radius: 0.25rem;
  font-size: 0.6875rem;
  line-height: 1.28;
}

.reasoning-markdown :deep(code:not(pre code)) {
  border-radius: 0.25rem;
  background: rgb(226 232 240 / 0.55);
  padding: 0.0625rem 0.25rem;
  font-size: 0.6875rem;
}

.thinking-dots {
  display: inline-flex;
  width: 1em;
  align-items: center;
  justify-content: flex-start;
}

.thinking-dots span {
  animation: thinking-dot 1.2s infinite ease-in-out;
}

.thinking-dots span::before {
  content: ".";
}

.thinking-dots span:nth-child(2) {
  animation-delay: 0.2s;
}

.thinking-dots span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes thinking-dot {
  0%,
  20% {
    opacity: 0;
  }

  45%,
  100% {
    opacity: 1;
  }
}
</style>
