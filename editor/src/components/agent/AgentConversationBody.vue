<!-- 文件功能：渲染智能体 run-first 时间线正文、草稿箱、工具调用与运行状态提示。 -->
<template>
  <div class="relative flex min-h-0 flex-1 overflow-hidden">
    <div
      ref="scrollContainerRef"
      class="agent-conversation-body flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto px-3 py-2.5"
      :class="{ 'agent-conversation-body--floating-toast': hasFloatingNotice }"
      @scroll="handleConversationScroll"
    >
    <section v-if="draftPatches.length" class="space-y-1.5">
      <div class="flex items-center justify-between gap-2">
        <h3 class="text-xs font-semibold text-text-secondary">草稿</h3>
        <span class="text-xs text-text-muted">{{ draftPatches.length }} 条</span>
      </div>
      <div class="space-y-1.5">
        <article
          v-for="draft in draftPatches"
          :key="`${draft.tool_name}-${draft.unified_diff}`"
          class="rounded-ui-md border border-warning/20 bg-warning-muted p-2.5"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <p class="text-sm font-semibold text-warning">{{ draft.change_note || '页面改写草稿' }}</p>
              <p class="mt-0.5 text-xs text-text-muted">来自 {{ draft.tool_name }}</p>
            </div>
            <div class="flex items-center gap-1.5">
              <UiButton variant="ghost" size="sm" @click="$emit('apply-suggested-patch', draft)">
                应用
              </UiButton>
              <UiButton variant="ghost" size="sm" @click="$emit('remove-draft-patch', draft)">
                移除
              </UiButton>
            </div>
          </div>
        </article>
      </div>
    </section>

    <section class="flex min-h-[140px] flex-1 flex-col">
      <DataState
        :state="conversationDataState"
        :title="conversationDataState === 'loading' ? loadingText : emptyConversationText"
        :description="conversationDataState === 'empty' ? '发送消息后，助手会在当前会话中持续反馈进度。' : undefined"
      >
        <div class="flex flex-col gap-2">
        <template v-for="item in timelineDisplayItems" :key="item.id">
          <article
            v-if="item.kind === 'message'"
            class="conversation-message flex px-0.5 py-0"
            :class="item.message.role === 'user' ? 'conversation-message--user justify-end' : 'conversation-message--assistant justify-start'"
          >
            <div class="message-group min-w-0" :class="item.message.role === 'user' ? 'max-w-[88%]' : 'w-full'">
              <div
                class="message-shell min-w-0"
                :class="item.message.role === 'user'
                  ? 'rounded-ui-md border border-border bg-surface-muted px-3 py-2 text-text-secondary'
                  : 'px-0.5 py-1 text-text-secondary'"
              >
                <div v-if="item.message.role === 'assistant'" class="assistant-markdown">
                  <p v-if="shouldShowAssistantPlaceholder(item)" class="text-sm leading-5 text-text-muted">...</p>
                  <MarkdownRender
                    v-else-if="resolveMessageContent(item.message)"
                    :nodes="resolveMessageMarkdownNodes(item.message)"
                    :max-live-nodes="320"
                    batch-rendering
                    :initial-render-batch-size="assistantBatchRendering.initialRenderBatchSize"
                    :render-batch-size="assistantBatchRendering.renderBatchSize"
                    :render-batch-delay="assistantBatchRendering.renderBatchDelay"
                    :render-batch-budget-ms="assistantBatchRendering.renderBatchBudgetMs"
                  />
                </div>
                <div v-else>
                  <UiButton
                    v-if="isUserMessageCollapsed(item.message)"
                    variant="ghost"
                    size="xs"
                    content-align="start"
                    class="max-w-full text-left text-text-muted"
                    title="展开用户消息"
                    aria-label="展开用户消息"
                    @click="toggleUserMessageCollapsed(item.message)"
                  >
                    <ChevronRight class="h-3 w-3 shrink-0" />
                    <span class="min-w-0 truncate">{{ formatCollapsedUserMessageSummary(item.message) }}</span>
                  </UiButton>
                  <pre v-else class="whitespace-pre-wrap break-words font-sans text-[13px] leading-5">{{ item.message.content || '...' }}</pre>
                </div>
                <div
                  v-if="item.message.attachments?.length && !isUserMessageCollapsed(item.message)"
                  class="mt-1 flex flex-wrap gap-1"
                  :class="item.message.role === 'user' ? 'justify-end' : 'justify-start'"
                >
                  <a
                    v-for="attachment in item.message.attachments"
                    :key="attachment.id"
                    :href="isAttachmentPreviewAvailable(attachment) ? attachment.url : undefined"
                    target="_blank"
                    rel="noreferrer"
                    class="message-attachment-thumb"
                    :title="attachment.original_name"
                    @click.stop
                  >
                    <img
                      v-if="isAttachmentPreviewAvailable(attachment)"
                      :src="attachment.url"
                      :alt="attachment.original_name"
                      class="h-full w-full object-cover"
                      @error="event => handleAttachmentImageError(event, attachment)"
                    >
                    <span v-else class="message-attachment-placeholder">{{ attachmentPlaceholderText(attachment) }}</span>
                  </a>
                </div>
              </div>
              <div
                v-if="item.message.role === 'user'"
                class="message-actions mt-0.5 flex items-center justify-end gap-1 px-1"
              >
                <span
                  v-if="item.message.created_at"
                  class="message-time mr-0.5 text-xs text-text-muted"
                >
                  {{ formatMessageTime(item.message.created_at) }}
                </span>
                <UiIconButton
                  label="复制用户消息"
                  size="xs"
                  class="message-action-button"
                  title="复制用户消息"
                  aria-label="复制用户消息"
                  @click="copyUserMessage(item.message)"
                >
                  <Copy class="h-3 w-3" />
                </UiIconButton>
                <UiIconButton
                  :label="isUserMessageCollapsed(item.message) ? '展开用户消息' : '折叠用户消息'"
                  size="xs"
                  class="message-action-button"
                  :title="isUserMessageCollapsed(item.message) ? '展开用户消息' : '折叠用户消息'"
                  :aria-label="isUserMessageCollapsed(item.message) ? '展开用户消息' : '折叠用户消息'"
                  @click="toggleUserMessageCollapsed(item.message)"
                >
                  <ChevronRight v-if="isUserMessageCollapsed(item.message)" class="h-3 w-3" />
                  <ChevronDown v-else class="h-3 w-3" />
                </UiIconButton>
              </div>
            </div>
          </article>

          <article v-else-if="item.kind === 'reasoning'" class="conversation-message conversation-message--trace px-0.5 py-0">
            <div class="message-group w-full min-w-0">
              <details class="reasoning-details rounded-ui-md border border-border bg-surface-hover text-text-muted" :open="item.streaming">
                <summary class="flex min-h-control-xs cursor-pointer select-none items-center gap-1.5 px-2 text-xs font-medium transition-colors hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-border-focus">
                  <ChevronRight class="h-3 w-3 transition details-chevron" />
                  <span>{{ item.streaming ? '思考中' : '思考过程' }}</span>
                  <span v-if="item.streaming" class="thinking-dots" aria-hidden="true">
                    <span />
                    <span />
                    <span />
                  </span>
                </summary>
                <div class="reasoning-markdown max-h-40 overflow-auto border-t border-border px-2 py-1.5">
                  <MarkdownRender
                    :nodes="resolveReasoningMarkdownNodes(item)"
                    :max-live-nodes="160"
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

          <article v-else-if="item.kind === 'feedback_request'" class="conversation-message conversation-message--action flex justify-start px-0.5 py-0">
            <div class="message-group w-full min-w-0">
              <details class="feedback-details rounded-ui-md border border-border bg-surface-hover" :open="item.pending">
                <summary class="flex min-h-control-sm cursor-pointer select-none items-center gap-1.5 px-2 text-xs font-medium text-text-muted transition-colors hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-border-focus">
                  <ChevronRight class="h-3 w-3 shrink-0 transition details-chevron" />
                  <span class="min-w-0 flex-1 truncate">{{ formatFeedbackRequestSummary(item) }}</span>
                  <UiBadge :tone="item.pending ? 'info' : 'neutral'" size="sm">
                    {{ item.pending ? '待回答' : '已回答' }}
                  </UiBadge>
                </summary>
                <div class="space-y-2 border-t border-border px-2 py-1.5">
                  <div
                    v-for="(entry, entryIndex) in item.entries"
                    :key="`${entry.question}-${entryIndex}`"
                    class="grid gap-0.5"
                  >
                    <p class="break-words text-xs font-medium leading-5 text-text-secondary">{{ entry.question }}</p>
                    <p class="break-words text-xs leading-5" :class="entry.answerText ? 'text-text' : 'text-info'">
                      {{ entry.answerText || '未回复' }}
                    </p>
                  </div>
                </div>
              </details>
            </div>
          </article>

          <article v-else-if="item.kind === 'tool_group'" class="conversation-message conversation-message--trace flex justify-start px-0.5 py-0">
            <div class="message-group w-full min-w-0">
              <template v-if="item.tools.length === 1">
                <div
                  v-for="tool in item.tools"
                  :key="tool.id"
                >
                  <AgentVisualToolCard
                    v-if="isVisualTool(tool)"
                    :tool="tool"
                    @open-detail="handleToolRowClick(tool)"
                  />
                  <template v-else>
                  <UiButton
                    variant="secondary"
                    size="xs"
                    content-align="between"
                    class="tool-call-row w-full min-w-0 text-left"
                    :aria-label="resolveToolDisplayName(tool)"
                    @click="handleToolRowClick(tool)"
                  >
                    <span class="min-w-0 truncate text-text-secondary">{{ resolveToolDisplayName(tool) }}</span>
                    <UiBadge :tone="getToolStatusTone(tool.status)" size="sm">{{ toolStatusLabelMap[tool.status] }}</UiBadge>
                  </UiButton>
                  <div v-if="tool.attachments.length" class="mt-1 flex flex-wrap gap-1">
                    <a
                      v-for="attachment in tool.attachments"
                      :key="attachment.id"
                      :href="isAttachmentPreviewAvailable(attachment) ? attachment.url : undefined"
                      target="_blank"
                      rel="noreferrer"
                      class="message-attachment-thumb"
                      :title="attachment.original_name"
                      @click.stop
                    >
                      <img
                        v-if="isAttachmentPreviewAvailable(attachment)"
                        :src="attachment.url"
                        :alt="attachment.original_name"
                        class="h-full w-full object-cover"
                        @error="event => handleAttachmentImageError(event, attachment)"
                      >
                      <span v-else class="message-attachment-placeholder">{{ attachmentPlaceholderText(attachment) }}</span>
                    </a>
                  </div>
                  </template>
                </div>
              </template>
              <details v-else class="tool-call-group rounded-ui-md border border-border bg-surface-hover" :open="shouldExpandToolGroup(item.tools)">
                <summary class="flex min-h-control-sm cursor-pointer select-none items-center gap-1.5 px-2 text-xs font-medium text-text-muted transition-colors hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-border-focus">
                  <ChevronRight class="h-3 w-3 transition details-chevron" />
                  <span class="min-w-0 flex-1 truncate">{{ formatToolGroupSummary(item.tools) }}</span>
                </summary>
                <div class="space-y-1 border-t border-border p-1.5">
                  <div
                    v-for="tool in item.tools"
                    :key="tool.id"
                  >
                    <AgentVisualToolCard
                      v-if="isVisualTool(tool)"
                      :tool="tool"
                      @open-detail="handleToolRowClick(tool)"
                    />
                    <template v-else>
                    <UiButton
                      variant="secondary"
                      size="xs"
                      content-align="between"
                      class="tool-call-row w-full min-w-0 text-left"
                      :aria-label="resolveToolDisplayName(tool)"
                      @click="handleToolRowClick(tool)"
                    >
                      <span class="min-w-0 truncate text-text-secondary">{{ resolveToolDisplayName(tool) }}</span>
                      <UiBadge :tone="getToolStatusTone(tool.status)" size="sm">{{ toolStatusLabelMap[tool.status] }}</UiBadge>
                    </UiButton>
                    <div v-if="tool.attachments.length" class="mt-1 flex flex-wrap gap-1">
                      <a
                        v-for="attachment in tool.attachments"
                        :key="attachment.id"
                        :href="isAttachmentPreviewAvailable(attachment) ? attachment.url : undefined"
                        target="_blank"
                        rel="noreferrer"
                        class="message-attachment-thumb"
                        :title="attachment.original_name"
                        @click.stop
                      >
                        <img
                          v-if="isAttachmentPreviewAvailable(attachment)"
                          :src="attachment.url"
                          :alt="attachment.original_name"
                          class="h-full w-full object-cover"
                          @error="event => handleAttachmentImageError(event, attachment)"
                        >
                        <span v-else class="message-attachment-placeholder">{{ attachmentPlaceholderText(attachment) }}</span>
                      </a>
                    </div>
                    </template>
                  </div>
                </div>
              </details>
            </div>
          </article>

          <article v-else-if="item.kind === 'run_status'" class="conversation-message conversation-message--trace px-0.5 py-0">
            <div class="flex min-h-control-xs w-full items-center gap-2 rounded-ui-md px-2 text-xs" :class="getRunStatusContainerClass(item.status)">
              <span class="h-1.5 w-1.5 shrink-0 rounded-full" :class="getRunStatusDotClass(item.status)" />
              <span class="min-w-0 flex-1 truncate">{{ item.content }}</span>
              <span v-if="shouldAnimateRunStatus(item.status)" class="thinking-dots shrink-0" aria-hidden="true">
                <span />
                <span />
                <span />
              </span>
            </div>
          </article>

          <article
            v-else
            class="conversation-message conversation-message--action flex px-0.5 py-0"
          >
            <div
              class="message-group flex min-h-control-sm w-full items-center rounded-ui-md border px-3 text-xs font-medium leading-5"
              :class="getRequirementStatusClass(item.status)"
            >
              {{ item.content }}
            </div>
          </article>
        </template>
        </div>
      </DataState>
    </section>

    </div>

    <section
      v-if="floatingNotice"
      class="pointer-events-none absolute inset-x-2 bottom-2 z-20 flex justify-center"
      role="status"
      aria-live="polite"
    >
      <div
        class="pointer-events-auto flex max-h-[45%] w-[min(100%,28rem)] items-start justify-between gap-3 overflow-auto rounded-ui-lg border px-3 py-2 text-left shadow-popover"
        :class="floatingNotice.tone === 'error'
          ? 'border-danger/20 bg-danger-muted'
          : 'border-warning/20 bg-warning-muted'"
      >
        <div class="min-w-0">
          <p
            class="break-words text-[13px] font-semibold leading-5"
            :class="floatingNotice.tone === 'error' ? 'text-danger' : 'text-warning'"
          >
            {{ floatingNotice.title }}
          </p>
          <p
            class="break-words text-xs leading-5"
            :class="floatingNotice.tone === 'error' ? 'text-danger' : 'text-warning'"
          >
            {{ floatingNotice.detail }}
          </p>
        </div>
        <UiButton
          v-if="floatingNotice.action === 'force_cancel' && cancellingRunForceAvailable"
          variant="secondary"
          size="sm"
          @click="$emit('force-cancel-run')"
        >
          强制结束
        </UiButton>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import 'markstream-vue/index.css'
import MarkdownRender, { getMarkdown, parseMarkdownToStructure } from 'markstream-vue'
import { ChevronDown, ChevronRight, Copy } from '@lucide/vue'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import DataState from '@/components/patterns/DataState.vue'
import { UiBadge, UiButton, UiIconButton } from '@/components/ui'
import AgentVisualToolCard from '@/components/agent/AgentVisualToolCard.vue'
import {
  createMessageStreamingResolver,
  formatCollapsedUserMessageSummary,
  formatMessageTime,
  formatToolGroupSummary,
  resolveMessageContent,
  resolveMessageMarkdownNodes as buildMessageMarkdownNodes,
  shouldExpandToolGroup,
  shouldAutoCollapseUserMessage,
  shouldShowAssistantPlaceholder as shouldDisplayAssistantPlaceholder,
  toolStatusLabelMap,
} from '@/components/agent/agent-message-display'
import type { TimelineDisplayItem, ToolCallDetail } from '@/components/agent/agent-conversation-panel'
import type { AgentActiveRunItem, AgentMessageAttachmentItem, AgentMessageItem, AgentSuggestedPatch } from '@/types/api'
import { Message } from '@/utils/message'

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
const failedAttachmentIds = ref(new Set<number>())
const userMessageCollapseOverrides = ref(new Map<string, boolean>())
let scrollAnimationFrame: number | null = null
const assistantBatchRendering = {
  initialRenderBatchSize: 12,
  renderBatchSize: 16,
  renderBatchDelay: 8,
  renderBatchBudgetMs: 6,
}
const floatingNotice = computed(() => {
  if (props.activeRun?.status === 'cancelling') {
    return {
      title: '正在停止当前运行',
      detail: '如果长时间没有响应，可以强制释放当前会话占用。',
      tone: 'warning' as const,
      action: 'force_cancel' as const,
    }
  }
  if (props.lastRunIssue) {
    return {
      title: props.lastRunIssue.title,
      detail: props.lastRunIssue.detail,
      tone: 'error' as const,
      action: null,
    }
  }
  return null
})
const hasFloatingNotice = computed(() => Boolean(floatingNotice.value))
const conversationDataState = computed<'loading' | 'empty' | 'ready'>(() => {
  if (props.loading) return 'loading'
  return props.timelineDisplayItems.length ? 'ready' : 'empty'
})
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

function isVisualTool(tool: ToolCallDetail) {
  return tool.toolName === 'analyze_visuals' || tool.toolName === 'generate_image'
}

/**
 * 判断用户消息是否处于折叠态；长文本默认收起，用户手动操作优先于默认规则。
 */
function isUserMessageCollapsed(message: AgentMessageItem) {
  return userMessageCollapseOverrides.value.get(message.id) ?? shouldAutoCollapseUserMessage(message)
}

/**
 * 切换用户消息折叠状态；替换 Map 引用以确保 Vue 响应式更新。
 */
function toggleUserMessageCollapsed(message: AgentMessageItem) {
  const nextOverrides = new Map(userMessageCollapseOverrides.value)
  nextOverrides.set(message.id, !isUserMessageCollapsed(message))
  userMessageCollapseOverrides.value = nextOverrides
}

/**
 * 复制用户原始消息文本；附件不写入剪贴板，避免生成不可用的伪路径。
 */
async function copyUserMessage(message: AgentMessageItem) {
  const content = message.content ?? ''
  if (!content.trim()) {
    Message.warning('用户消息为空，无法复制。')
    return
  }
  try {
    await navigator.clipboard.writeText(content)
    Message.success('用户消息已复制。')
  } catch {
    Message.error('复制用户消息失败，请检查浏览器剪贴板权限。')
  }
}

/**
 * 将工具运行状态映射到统一 Badge 语义，工具类别不再使用独立颜色。
 */
function getToolStatusTone(status: ToolCallDetail['status']) {
  if (status === 'error') return 'danger' as const
  if (status === 'running') return 'info' as const
  return 'success' as const
}

/**
 * 已完成的用户回答在主时间线只显示问题摘要，详情按需展开。
 */
function formatFeedbackRequestSummary(item: Extract<TimelineDisplayItem, { kind: 'feedback_request' }>) {
  const firstQuestion = item.entries[0]?.question?.trim() || '用户回答'
  return item.entries.length > 1 ? `${firstQuestion} · 共 ${item.entries.length} 题` : firstQuestion
}

function handleAttachmentImageError(event: Event, attachment: AgentMessageAttachmentItem) {
  void event
  failedAttachmentIds.value = new Set([...failedAttachmentIds.value, attachment.id])
}

function isAttachmentPreviewAvailable(attachment: AgentMessageAttachmentItem) {
  return attachment.preview_available && !failedAttachmentIds.value.has(attachment.id)
}

function attachmentPlaceholderText(attachment: AgentMessageAttachmentItem) {
  return attachment.source_kind === 'tool_output' ? '工具图片' : '图片'
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

function getRunStatusContainerClass(status: string | null) {
  if (status === 'failed') return 'bg-danger-muted text-danger'
  if (status === 'cancelled' || status === 'cancelling') return 'bg-warning-muted text-warning'
  if (status === 'completed') return 'bg-surface-hover text-text-muted'
  return 'bg-info-muted text-info'
}

function getRunStatusDotClass(status: string | null) {
  if (status === 'failed') return 'bg-danger'
  if (status === 'cancelled' || status === 'cancelling') return 'bg-warning'
  if (status === 'completed') return 'bg-text-disabled'
  return 'bg-info'
}

/**
 * 运行中的模型请求状态用省略号提示用户仍在等待输出。
 */
function shouldAnimateRunStatus(status: string | null) {
  return status === 'model_request' || status === 'tool_start' || status === 'tool_execution'
}

function getRequirementStatusClass(status: string | null) {
  if (status === 'failed') return 'border-danger/20 bg-danger-muted text-danger'
  if (status === 'cancelled' || status === 'cancelling') return 'border-warning/20 bg-warning-muted text-warning'
  if (status === 'paused' || status === 'pending' || status === 'waiting_external') return 'border-info/20 bg-info-muted text-info'
  return 'border-border bg-surface-hover text-text-muted'
}
</script>

<style scoped>
.agent-conversation-body--floating-toast {
  padding-bottom: 5.5rem;
}

details[open] .details-chevron {
  transform: rotate(90deg);
}

.reasoning-details > summary {
  list-style: none;
}

.reasoning-details > summary::-webkit-details-marker,
.feedback-details > summary::-webkit-details-marker {
  display: none;
}

.tool-call-group > summary,
.feedback-details > summary {
  list-style: none;
}

.tool-call-group > summary::-webkit-details-marker {
  display: none;
}

.tool-call-row,
.tool-call-group > summary {
  border-radius: 0.25rem;
}

.message-action-button {
  display: inline-flex;
  height: 1.25rem;
  width: 1.25rem;
  align-items: center;
  justify-content: center;
  border-radius: 0.25rem;
  color: rgb(var(--ui-text-muted));
  transition:
    background-color 0.15s ease,
    color 0.15s ease;
}

.message-action-button:hover {
  background: rgb(var(--ui-surface-hover));
  color: rgb(var(--ui-text-secondary));
}

.message-attachment-thumb {
  display: inline-flex;
  height: 3.5rem;
  width: 3.5rem;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border-radius: 0.375rem;
  border: 1px solid rgb(var(--ui-border));
  background: rgb(var(--ui-surface-hover));
  color: rgb(var(--ui-text-muted));
  text-decoration: none;
}

.message-attachment-placeholder {
  display: inline-flex;
  height: 100%;
  width: 100%;
  align-items: center;
  justify-content: center;
  padding: 0.25rem;
  text-align: center;
  font-size: 0.625rem;
  line-height: 0.875rem;
}

.assistant-markdown {
  font-size: 0.8125rem;
  line-height: 1.5;
}

.assistant-markdown :deep(.markstream-vue) {
  background: transparent;
  color: inherit;
  font-size: 0.8125rem;
  line-height: 1.32;
  --loading-shimmer: rgb(var(--ui-border) / 0.95);
  --tooltip-bg: rgb(var(--ui-text));
  --tooltip-fg: rgb(var(--ui-text-inverse));
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

.assistant-markdown :deep(.markstream-vue .node-placeholder),
.reasoning-markdown :deep(.markstream-vue .node-placeholder) {
  min-height: 0.875rem;
  border: 1px solid rgb(226 232 240 / 0.9);
  background: linear-gradient(90deg, rgb(248 250 252), rgb(241 245 249), rgb(248 250 252));
  opacity: 1;
}

.assistant-markdown :deep(p) {
  margin: 0;
  font-size: 0.8125rem;
  line-height: 1.5;
}

.assistant-markdown :deep(ul),
.assistant-markdown :deep(ol) {
  margin-top: 0.2rem;
  margin-bottom: 0.2rem;
  padding-left: 1.1rem;
  font-size: 0.8125rem;
  line-height: 1.5;
}

.assistant-markdown :deep(li) {
  font-size: 0.8125rem;
  line-height: 1.5;
}

.assistant-markdown :deep(pre) {
  margin: 0.25rem 0 0;
  max-width: 100%;
  overscroll-behavior-inline: contain;
  overflow-x: auto;
  border-radius: 0.25rem;
}

.assistant-markdown :deep(code:not(pre code)) {
  border-radius: 0.25rem;
  background: rgb(var(--ui-surface-muted));
  padding: 0.0625rem 0.25rem;
  font-size: 0.75rem;
}

.assistant-markdown :deep(a) {
  color: rgb(var(--ui-info));
  text-decoration: underline;
  text-underline-offset: 0.2em;
}

.reasoning-details {
  font-size: 0.6875rem;
  line-height: 1.25;
}

.reasoning-markdown :deep(.markstream-vue) {
  background: transparent;
  color: rgb(var(--ui-text-muted));
  font-size: 0.6875rem;
  line-height: 1.28;
  white-space: pre-wrap;
  --loading-shimmer: rgb(var(--ui-border) / 0.9);
  --tooltip-bg: rgb(var(--ui-text));
  --tooltip-fg: rgb(var(--ui-text-inverse));
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
  max-width: 100%;
  overscroll-behavior-inline: contain;
  overflow-x: auto;
  border-radius: 0.25rem;
  font-size: 0.6875rem;
  line-height: 1.28;
}

.reasoning-markdown :deep(code:not(pre code)) {
  border-radius: 0.25rem;
  background: rgb(var(--ui-surface-muted) / 0.75);
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
