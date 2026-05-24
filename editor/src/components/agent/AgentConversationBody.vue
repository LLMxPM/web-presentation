<!-- 文件功能：渲染智能体会话正文、草稿箱、内嵌工具调用与运行状态提示。 -->
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
          v-if="conversationMessages.length === 0"
          class="flex min-h-[140px] items-center justify-center text-center text-[12px] leading-5 text-slate-400"
        >
          {{ emptyConversationText }}
        </div>

        <article
          v-for="item in conversationDisplayItems"
          :key="item.message.id"
          class="conversation-message flex px-0.5 py-0"
          :class="item.message.role === 'user' ? 'conversation-message--user justify-end' : item.message.role === 'assistant' ? 'conversation-message--assistant justify-start' : 'conversation-message--system justify-start'"
        >
          <div class="message-group min-w-0" :class="item.message.role === 'user' ? 'max-w-[92%]' : 'w-[92%]'">
            <div
              class="message-shell min-w-0"
              :class="item.message.role === 'user'
                ? 'rounded-md border border-slate-200 bg-slate-100 px-2.5 py-1 text-slate-700'
                : item.message.role === 'assistant'
                  ? 'px-1 py-0.5 text-slate-700'
                  : 'rounded-md border border-slate-100 bg-slate-50/70 px-2 py-1 text-slate-600'"
            >
              <div v-if="item.message.role === 'assistant'" class="assistant-markdown">
                <details v-if="resolveMessageReasoning(item.message)" class="reasoning-details mb-0.5 text-slate-500">
                  <summary class="inline-flex cursor-pointer select-none items-center gap-0.5 rounded px-1 py-0 font-medium text-slate-400 transition hover:bg-slate-50 hover:text-slate-600">
                    <ChevronRight class="h-2.5 w-2.5 transition details-chevron" />
                    <span>{{ isMessageStreaming(item.message) ? '思考中' : '思考过程' }}</span>
                    <span v-if="isMessageStreaming(item.message)" class="thinking-dots" aria-hidden="true">
                      <span />
                      <span />
                      <span />
                    </span>
                  </summary>
                  <div class="reasoning-markdown mt-0.5 max-h-[100px] overflow-auto border-l border-slate-100 pl-1.5">
                    <MarkdownRender
                      :nodes="resolveMessageReasoningMarkdownNodes(item.message)"
                      :max-live-nodes="isMessageStreaming(item.message) ? 0 : 160"
                      batch-rendering
                      :initial-render-batch-size="assistantBatchRendering.initialRenderBatchSize"
                      :render-batch-size="assistantBatchRendering.renderBatchSize"
                      :render-batch-delay="assistantBatchRendering.renderBatchDelay"
                      :render-batch-budget-ms="assistantBatchRendering.renderBatchBudgetMs"
                    />
                  </div>
                </details>

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

                <div v-if="item.embeddedTools.length" class="tool-call-block mt-1.5 space-y-1 text-[10px] text-slate-500">
                  <template v-if="item.embeddedTools.length === 1">
                    <button
                      v-for="tool in item.embeddedTools"
                      :key="tool.id"
                      type="button"
                      class="tool-call-row flex w-full min-w-0 items-center justify-between gap-2 border border-slate-200/80 bg-slate-50/60 px-1.5 py-0.5 text-left text-[10px] transition hover:bg-slate-100/70"
                      :class="getToolChipClass(tool.status)"
                      @click="$emit('open-tool-detail', tool.id)"
                    >
                      <span class="min-w-0 truncate">{{ resolveToolDisplayName(tool) }}</span>
                      <span class="shrink-0 opacity-60" aria-hidden="true">{{ toolStatusLabelMap[tool.status] }}</span>
                    </button>
                  </template>
                  <details v-else class="tool-call-group" :open="shouldExpandToolGroup(item.embeddedTools)">
                    <summary class="flex cursor-pointer select-none items-center gap-1.5 border border-slate-200/80 bg-slate-50/60 px-1.5 py-0.5 text-[10px] text-slate-500 transition hover:bg-slate-100/70">
                      <ChevronRight class="h-2.5 w-2.5 transition details-chevron" />
                      <span class="min-w-0 flex-1 truncate">{{ formatToolGroupSummary(item.embeddedTools) }}</span>
                    </summary>
                    <div class="mt-1 space-y-1">
                      <button
                        v-for="tool in item.embeddedTools"
                        :key="tool.id"
                        type="button"
                        class="tool-call-row flex w-full min-w-0 items-center justify-between gap-2 border border-slate-200/80 bg-slate-50/60 px-1.5 py-0.5 text-left text-[10px] transition hover:bg-slate-100/70"
                        :class="getToolChipClass(tool.status)"
                        @click="$emit('open-tool-detail', tool.id)"
                      >
                        <span class="min-w-0 truncate">{{ resolveToolDisplayName(tool) }}</span>
                        <span class="shrink-0 opacity-60" aria-hidden="true">{{ toolStatusLabelMap[tool.status] }}</span>
                      </button>
                    </div>
                  </details>
                </div>
              </div>
              <div v-else>
                <div v-if="item.message.attachments?.length" class="mt-1.5 flex flex-wrap gap-1.5">
                  <img
                    v-for="attachment in item.message.attachments"
                    :key="attachment.id"
                    :src="attachment.url"
                    :alt="attachment.original_name"
                    class="h-14 w-14 rounded border border-white/30 object-cover shadow-sm"
                  >
                </div>
                <pre class="whitespace-pre-wrap break-words text-[12.5px] font-sans leading-[17px]">{{ item.message.content || (item.message.attachments?.length ? '（已发送图片）' : '...') }}</pre>
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
      </div>
    </section>

    <section v-if="lastRunIssue" class="space-y-2 rounded-3xl border border-red-200 bg-red-50/80 p-4">
      <p class="text-sm font-semibold text-red-800">{{ lastRunIssue.title }}</p>
      <p class="text-sm leading-6 text-red-700">{{ lastRunIssue.detail }}</p>
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
import MarkdownRender, { getMarkdown } from 'markstream-vue'
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
  resolveMessageReasoning as resolveDisplayedMessageReasoning,
  resolveMessageReasoningMarkdownNodes as buildMessageReasoningMarkdownNodes,
  shouldExpandToolGroup,
  shouldShowAssistantPlaceholder as shouldDisplayAssistantPlaceholder,
  toolStatusLabelMap,
} from '@/components/agent/agent-message-display'
import type { ConversationDisplayItem, ToolCallDetail } from '@/components/agent/agent-conversation-panel'
import type { AgentActiveRunItem, AgentMessageItem, AgentSuggestedPatch } from '@/types/api'

const props = defineProps<{
  conversationMessages: AgentMessageItem[]
  conversationDisplayItems: ConversationDisplayItem[]
  draftPatches: AgentSuggestedPatch[]
  emptyConversationText: string
  lastRunIssue: { title: string, detail: string } | null
  activeRun: AgentActiveRunItem | null
  cancellingRunForceAvailable: boolean
  isStreaming: boolean
  streamingAssistantMessageId: string | null
}>()

defineEmits<{
  'apply-suggested-patch': [patch: AgentSuggestedPatch]
  'remove-draft-patch': [patch: AgentSuggestedPatch]
  'open-tool-detail': [toolId: string]
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
  () => props.streamingAssistantMessageId,
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
 * 只有空 assistant 占位才显示省略号；已有思考过程或工具调用时不再额外占位。
 */
function shouldShowAssistantPlaceholder(item: ConversationDisplayItem) {
  return shouldDisplayAssistantPlaceholder(item, isMessageStreaming)
}

/**
 * 按 markstream-vue 文档推荐，流式场景预解析为 nodes 再交给渲染器。
 */
function resolveMessageMarkdownNodes(message: AgentMessageItem) {
  return readMarkdownCache(
    buildMarkdownCacheKey('content', message, isMessageStreaming(message)),
    () => buildMessageMarkdownNodes(message, markdownParser, isMessageStreaming),
  )
}

/**
 * 思考过程也使用 Markdown 结构渲染，但保持更弱的视觉层级。
 */
function resolveMessageReasoningMarkdownNodes(message: AgentMessageItem) {
  return readMarkdownCache(
    buildMarkdownCacheKey('reasoning', message, isMessageStreaming(message)),
    () => buildMessageReasoningMarkdownNodes(message, markdownParser, isMessageStreaming),
  )
}

/**
 * 返回消息思考内容，优先使用后端拆出的 reasoning_content。
 */
function resolveMessageReasoning(message: AgentMessageItem | undefined) {
  return resolveDisplayedMessageReasoning(message, isMessageStreaming)
}

/**
 * Team 成员工具调用在消息流中展示成员来源，避免与内容助手直连工具混淆。
 */
function resolveToolDisplayName(tool: ToolCallDetail) {
  return tool.memberAgentName ? `${tool.memberAgentName} · ${tool.toolName}` : tool.toolName
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
  const lastItem = props.conversationDisplayItems.at(-1)
  const lastMessage = lastItem?.message
  return [
    props.conversationDisplayItems.length,
    lastMessage?.id ?? '',
    lastMessage?.content.length ?? 0,
    lastMessage?.reasoning_content?.length ?? 0,
    lastItem?.embeddedTools.map(tool => `${tool.id}:${tool.status}`).join(',') ?? '',
    props.lastRunIssue?.detail ?? '',
    props.activeRun?.status ?? '',
  ].join('|')
}

function buildMarkdownCacheKey(kind: 'content' | 'reasoning', message: AgentMessageItem, streaming: boolean) {
  return [
    kind,
    message.id,
    streaming ? 'live' : 'final',
    message.content,
    message.reasoning_content ?? '',
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

.assistant-markdown :deep(.markstream-vue > :first-child) {
  margin-top: 0;
}

.assistant-markdown :deep(.markstream-vue > :last-child) {
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

.reasoning-markdown :deep(.markstream-vue > :first-child) {
  margin-top: 0;
}

.reasoning-markdown :deep(.markstream-vue > :last-child) {
  margin-bottom: 0;
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
