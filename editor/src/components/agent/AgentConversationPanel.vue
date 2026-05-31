<!-- 文件功能：提供通用内容助手面板，承载会话切换、消息流、工具调用详情与确认动作联动。 -->
<template>
  <Teleport v-if="props.headerScopeTarget && headerScopeReady" defer :to="props.headerScopeTarget">
    <AgentScopeStatus
      :active-session-scope-summary="activeSessionScopeSummary"
      :active-session-scope-tooltip="activeSessionScopeTooltip"
      :route-scope-summary="routeScopeSummary"
      :route-scope-tooltip="routeScopeTooltip"
      :current-route-in-active-session-scope="currentRouteInActiveSessionScope"
    />
  </Teleport>

  <Teleport v-if="props.headerActionsTarget && headerActionsReady" defer :to="props.headerActionsTarget">
    <AgentSessionControls
      :sessions="sessionsQuery.data.value"
      :active-session-id="activeSessionId"
      :active-session-label="activeSessionLabel"
      :is-fetching="sessionsQuery.isFetching.value"
      :menu-visible="sessionMenuVisible"
      :create-disabled="createSessionMutation.isPending.value || hasBindingIssue || !props.routeAvailable"
      :switch-disabled="hasBindingIssue"
      :get-session-run-badge="getSessionRunBadge"
      align="right"
      @create="handleCreateSession"
      @toggle="toggleSessionMenu"
      @close="closeSessionMenu"
      @switch-session="handleSwitchSession"
    />
  </Teleport>

  <section :class="panelShellClass">
    <header v-if="!props.headerActionsTarget || !headerActionsReady" class="border-b border-slate-100 px-5 py-4">
      <AgentSessionControls
        :sessions="sessionsQuery.data.value"
        :active-session-id="activeSessionId"
        :active-session-label="activeSessionLabel"
        :is-fetching="sessionsQuery.isFetching.value"
        :menu-visible="sessionMenuVisible"
        :create-disabled="createSessionMutation.isPending.value || hasBindingIssue || !props.routeAvailable"
        :switch-disabled="hasBindingIssue"
        :get-session-run-badge="getSessionRunBadge"
        align="left"
        @create="handleCreateSession"
        @toggle="toggleSessionMenu"
        @close="closeSessionMenu"
        @switch-session="handleSwitchSession"
      />
    </header>

    <div class="flex min-h-0 flex-1 flex-col overflow-hidden">
      <section v-if="hasBindingIssue" class="m-4 space-y-4 rounded-3xl border border-amber-200 bg-amber-50/80 p-5">
        <div class="space-y-2">
          <p class="text-base font-semibold text-amber-800">{{ agentIssueTitle }}</p>
          <p class="text-sm leading-6 text-amber-700">
            {{ agentIssueDetail }}
          </p>
        </div>
        <div class="rounded-2xl border border-white/80 bg-white/70 px-4 py-3 text-sm text-slate-600">
          <p>当前 agent：{{ selectedAgent?.name || agentDisplayName }}</p>
          <p>已绑定模型：{{ selectedAgent?.bound_llm_name || '未绑定' }}</p>
        </div>
        <div class="flex justify-end">
          <BaseButton variant="primary" @click="goToAiSettings">
            前往 AI 设置
          </BaseButton>
        </div>
      </section>

      <template v-else>
        <AgentConversationBody
          :timeline-display-items="timelineDisplayItems"
          :draft-patches="draftPatches"
          :empty-conversation-text="emptyConversationText"
          :loading="sessionLoading"
          :loading-text="sessionLoadingText"
          :last-run-issue="lastRunIssue"
          :active-run="activeRun"
          :cancelling-run-force-available="cancellingRunForceAvailable"
          :is-streaming="isStreaming"
          :streaming-timeline-item-id="streamingTimelineItemId"
          @apply-suggested-patch="applySuggestedPatch"
          @remove-draft-patch="removeDraftPatch"
          @open-tool-detail="openToolDetail"
          @open-member-run-detail="openMemberRunDetail"
          @force-cancel-run="handleForceCancelRun"
        />

        <section v-if="composerContextIssue"
          class="flex items-center gap-2 border-t border-amber-100 bg-amber-50/90 px-4 py-3 text-xs leading-5 text-amber-700">
          <span class="min-w-0 flex-1">{{ composerContextIssue }}</span>
          <button
            v-if="canOpenActiveSessionRoute"
            type="button"
            class="inline-flex h-7 shrink-0 items-center gap-1 rounded-md border border-amber-200 bg-white px-2 text-[11px] font-semibold text-amber-700 shadow-sm transition hover:border-amber-300 hover:bg-amber-100"
            aria-label="打开此会话工作页面"
            title="打开此会话工作页面"
            @click="openActiveSessionRoute"
          >
            <ExternalLink class="h-3 w-3" />
            打开
          </button>
        </section>

        <AgentComposer v-model="composerText" :streaming="isStreaming"
          :interrupting="isInterrupting" :action-disabled="composerActionDisabled"
          :disabled="composerInputDisabled"
          :placeholder="composerPlaceholderText"
          :context-used-tokens="contextUsageTokens.used"
          :context-available-tokens="contextUsageTokens.available"
          :image-attachments="pendingImageAttachments"
          :image-uploading="imageUploading"
          :image-upload-disabled="imageUploadDisabled"
          :image-upload-disabled-reason="imageUploadDisabledReason"
          :pending-requirement="pendingRequirement"
          :hitl-loading="isStreaming"
          :can-apply-suggested-patch="canApplySuggestedPatch"
          @upload-image="handleUploadImage"
          @remove-image="handleRemoveImage"
          @promote-image="handlePromoteImage"
          @hitl-confirm="handleContinueRun('confirm')"
          @hitl-reject="handleContinueRun('reject')"
          @hitl-feedback-submit="handleSubmitFeedbackRun"
          @hitl-cancel="handleCancelPausedRun"
          @apply-suggested-patch="applySuggestedPatch"
          @save-draft-patch="saveDraftPatch"
          @context-usage-open="handleContextUsageOpen"
          @action="handleComposerPrimaryAction" />
      </template>
    </div>
  </section>

  <AgentConversationDialogs
    v-model:tool-detail-visible="toolDetailDialogVisible"
    v-model:member-run-visible="memberRunDialogVisible"
    :active-tool-detail="activeToolDetail"
    :active-member-runs="activeMemberRuns"
    @open-tool-detail="openToolDetail"
  />
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { storeToRefs } from 'pinia'
import { useRoute, useRouter } from 'vue-router'
import { ExternalLink } from '@lucide/vue'

import {
  AgentRequestError,
  AgentStreamInterruptedError,
  cancelAgentSessionActiveRun,
  continueAgentSessionActiveRun,
  createAgentSession,
  deleteAgentImageAttachment,
  getAgentSessionContextStatus,
  getAgentSessionRuntime,
  listAgents,
  listAgentSessions,
  promoteAgentImageAttachment,
  renameAgentSession,
  streamAgentRun,
  streamAgentRunEvents,
  uploadAgentImageAttachment,
} from '@/api/ai'
import {
  buildTimelineDisplayItems,
  buildRunIssueState,
  extractTimelineToolDetails,
  type AgentMutationRefreshEvent,
  type ToolCallDetail,
} from '@/components/agent/agent-conversation-panel'
import {
  compactMutationRefreshEvents,
  buildMutationRefreshEvents,
} from '@/components/agent/agent-mutation-refresh'
import {
  buildSessionRouteLocation,
  findLatestSessionForScope,
  formatScopeTooltip,
  getSelectedSession,
  isRouteScopeInsideSessionScope,
  isSessionTargetCurrentScope,
  resolveScopeSummary,
  resolveSessionDisplayName,
  resolveSessionScope,
  setSelectedSession,
} from '@/components/agent/agent-session-scope'
import { buildAgentLocalTimelineItem, normalizeAgnoRunEvent } from '@/components/agent/agent-run-state'
import AgentComposer from '@/components/agent/AgentComposer.vue'
import AgentConversationBody from '@/components/agent/AgentConversationBody.vue'
import AgentConversationDialogs from '@/components/agent/AgentConversationDialogs.vue'
import AgentScopeStatus from '@/components/agent/AgentScopeStatus.vue'
import AgentSessionControls from '@/components/agent/AgentSessionControls.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import type {
  AgentActiveRunItem,
  AgentContextStatusItem,
  AgentDescriptor,
  AgentFeedbackSelection,
  AgentImageAttachmentItem,
  AgentMemberRunItem,
  AgentPendingRequirement,
  AgentRunEvent,
  AgentScopeContext,
  AgentSessionItem,
  AgentSessionRuntimeSnapshot,
  AgentSuggestedPatch,
  AgentTimelineItem,
} from '@/types/api'
import { useAgentSessionStore } from '@/stores/agent-session'
import { logClientWarning } from '@/utils/client-logger'
import { Message } from '@/utils/message'

interface Props {
  workspaceId: number
  projectId?: number | null
  pageId?: number | null
  componentId?: number | null
  pageTitle?: string
  agentId?: string
  agentDisplayName?: string
  scope?: AgentScopeContext | null
  routeScope?: AgentScopeContext | null
  contextTitle?: string
  enablePagePatchActions?: boolean
  emptyText?: string
  composerPlaceholder?: string
  embedded?: boolean
  headerScopeTarget?: string | null
  headerActionsTarget?: string | null
  routeAvailable?: boolean
  routeUnavailableReason?: string
  autoCreateKey?: string | number | null
  autoNavigateTarget?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  projectId: null,
  pageId: null,
  componentId: null,
  pageTitle: '',
  agentId: 'agent-coordinator',
  agentDisplayName: '内容助手',
  scope: null,
  routeScope: null,
  contextTitle: '',
  enablePagePatchActions: true,
  emptyText: '',
  composerPlaceholder: '',
  embedded: false,
  headerScopeTarget: null,
  headerActionsTarget: null,
  routeAvailable: true,
  routeUnavailableReason: '',
  autoCreateKey: null,
  autoNavigateTarget: null,
})

const emit = defineEmits<{
  'apply-suggested-content': [content: string]
  'page-updated': [event: AgentMutationRefreshEvent]
  'project-pages-updated': [event: AgentMutationRefreshEvent]
  'project-updated': [event: AgentMutationRefreshEvent]
  'component-updated': [event: AgentMutationRefreshEvent]
  'asset-updated': [event: AgentMutationRefreshEvent]
}>()

const queryClient = useQueryClient()
const agentSessionStore = useAgentSessionStore()
const {
  timelineItemsBySession,
  memberRunsBySession,
  pendingRequirementBySession,
  pendingImageAttachmentsBySession,
  activeRunBySession,
  streamingBySession,
  interruptingBySession,
  imageUploadingBySession,
  currentRunIdBySession,
  streamingTimelineItemIdBySession,
  lastRunIssueBySession,
  contextStatusBySession,
  mutationRefreshEventsBySession,
} = storeToRefs(agentSessionStore)
const router = useRouter()
const route = useRoute()

const composerText = ref('')
const activeSessionId = ref('')
const pendingRouteSessionId = ref('')
const pendingUnavailableSessionSelectionKey = ref<string | number | null>(null)
const manuallySelectedSessionId = ref('')
const lastHandledAutoCreateKey = ref<string | number | null>(null)
const virtualNewSessionKey = ref<string | number | null>(null)
const virtualNewSessionSequence = ref(0)
const draftPatches = ref<AgentSuggestedPatch[]>([])
const headerScopeReady = ref(false)
const headerActionsReady = ref(false)
const sessionMenuVisible = ref(false)
const toolDetailDialogVisible = ref(false)
const memberRunDialogVisible = ref(false)
const activeToolDetailId = ref<string | null>(null)
const activeMemberRunIds = ref<string[]>([])
const sendInFlight = ref(false)
const streamAbortControllersByRun = new Map<string, AbortController>()
const autoNamingSessionIds = new Set<string>()
const forceCancelTick = ref(Date.now())
let forceCancelTimer: number | null = null
let componentDisposed = false
const IMAGE_ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024
const ALLOWED_IMAGE_ATTACHMENT_TYPES = new Set(['image/png', 'image/jpeg', 'image/webp'])

const scope = computed<AgentScopeContext>(() => props.scope ?? {
  scope_type: props.pageId ? 'page' : props.projectId ? 'project' : 'workspace',
  workspace_id: props.workspaceId,
  project_id: props.projectId ?? null,
  page_id: props.pageId ?? null,
  component_id: props.componentId ?? null,
  workspace_name: null,
  project_name: null,
  page_title: props.pageTitle || null,
  component_name: null,
  source: props.pageId ? 'editor-page-detail' : 'editor-agent-sidebar',
})
const currentRouteScope = computed<AgentScopeContext>(() => props.routeScope ?? scope.value)
const agentId = computed(() => props.agentId || 'agent-coordinator')
const agentDisplayName = computed(() => selectedAgent.value?.name || props.agentDisplayName || '内容助手')
const contextTitle = computed(() => props.contextTitle || props.pageTitle || selectedAgent.value?.default_session_name || '智能体会话')
const emptyConversationText = computed(() => props.emptyText || `${agentDisplayName.value} 会结合当前上下文和可用工具给出建议。`)
const composerPlaceholderText = computed(() => (
  props.composerPlaceholder
  || '描述目标；内容助手会处理页面/项目任务，并按需调用组件或资源助手。'
))
const routeScopeSummary = computed(() => resolveScopeSummary(currentRouteScope.value, contextTitle.value))
const activeRun = computed(() => readSessionValue(activeRunBySession.value, activeSessionId.value, null))
const isStreaming = computed(() => isSessionRunning(activeSessionId.value))
const isInterrupting = computed(() => readSessionValue(interruptingBySession.value, activeSessionId.value, false))
const timelineItems = computed<AgentTimelineItem[]>({
  get: () => readSessionValue(timelineItemsBySession.value, activeSessionId.value, []),
  set: value => agentSessionStore.setTimelineItems(activeSessionId.value, value),
})
const memberRuns = computed<AgentMemberRunItem[]>(() => (
  readSessionValue(memberRunsBySession.value, activeSessionId.value, [])
))
const pendingRequirement = computed<AgentPendingRequirement | null>({
  get: () => activeRun.value?.pending_requirement ?? readSessionValue(pendingRequirementBySession.value, activeSessionId.value, null),
  set: value => agentSessionStore.setPendingRequirement(activeSessionId.value, value),
})
const streamingTimelineItemId = computed<string | null>({
  get: () => readSessionValue(streamingTimelineItemIdBySession.value, activeSessionId.value, null),
  set: value => agentSessionStore.setStreamingTimelineItemId(activeSessionId.value, value),
})
const lastRunIssue = computed<{ title: string, detail: string } | null>({
  get: () => readSessionValue(lastRunIssueBySession.value, activeSessionId.value, null),
  set: value => agentSessionStore.setLastIssue(activeSessionId.value, value),
})
const contextStatus = computed<AgentContextStatusItem | null>({
  get: () => readSessionValue(contextStatusBySession.value, activeSessionId.value, null),
  set: value => agentSessionStore.setContextStatus(activeSessionId.value, value),
})
const pendingImageAttachments = computed<AgentImageAttachmentItem[]>({
  get: () => readSessionValue(pendingImageAttachmentsBySession.value, activeSessionId.value, []),
  set: value => agentSessionStore.setPendingImageAttachments(activeSessionId.value, value),
})
const imageUploading = computed<boolean>({
  get: () => readSessionValue(imageUploadingBySession.value, activeSessionId.value, false),
  set: value => writeSessionValue(imageUploadingBySession.value, activeSessionId.value, value),
})
const contextUsageTokens = computed(() => {
  const status = contextStatus.value
  if (!status) {
    return { used: null, available: null }
  }
  return {
    used: Math.max(0, status.estimated_history_tokens),
    available: Math.max(0, status.history_budget_tokens),
  }
})
const cancellingRunForceAvailable = computed(() => {
  const run = activeRun.value
  if (run?.status !== 'cancelling' || !run.cancel_requested_at) {
    return false
  }
  return forceCancelTick.value - new Date(run.cancel_requested_at).getTime() >= 30_000
})

const agentsQuery = useQuery(
  computed(() => ({
    queryKey: ['ai-agents', agentId.value, scope.value.scope_type, scope.value.workspace_id, scope.value.project_id, scope.value.page_id, scope.value.component_id, scope.value.source],
    queryFn: () => listAgents(scope.value, agentId.value),
    enabled: !!scope.value.workspace_id,
  })),
)

const sessionsQuery = useQuery(
  computed(() => ({
    queryKey: ['ai-sessions', agentId.value, scope.value.workspace_id],
    queryFn: () => listAgentSessions(scope.value, agentId.value),
    enabled: !!scope.value.workspace_id,
  })),
)

const activeSession = computed<AgentSessionItem | null>(() => (
  sessionsQuery.data.value?.find(item => item.session_id === activeSessionId.value) ?? null
))
const activeSessionScope = computed(() => activeSession.value ? resolveSessionScope(activeSession.value) : null)
const activeSessionRuntimeScope = computed(() => activeSessionScope.value ?? scope.value)
const activeSessionRuntimeAgentId = computed(() => activeSession.value?.agent_id ?? agentId.value)

const runtimeQuery = useQuery(
  computed(() => ({
    queryKey: [
      'ai-session-runtime',
      activeSessionRuntimeAgentId.value,
      activeSessionId.value,
      activeSessionRuntimeScope.value.scope_type,
      activeSessionRuntimeScope.value.workspace_id,
      activeSessionRuntimeScope.value.project_id,
      activeSessionRuntimeScope.value.page_id,
      activeSessionRuntimeScope.value.component_id,
      activeSessionRuntimeScope.value.source,
    ],
    queryFn: () => getAgentSessionRuntime(
      activeSessionId.value,
      activeSessionRuntimeScope.value,
      activeSessionRuntimeAgentId.value,
    ),
    enabled: !!activeSessionId.value,
    refetchOnWindowFocus: true,
  })),
)

const sessionsInitialLoading = computed(() => (
  !virtualNewSessionKey.value
  && sessionsQuery.isFetching.value
  && sessionsQuery.data.value === undefined
))
const runtimeInitialLoading = computed(() => (
  Boolean(activeSessionId.value)
  && runtimeQuery.isFetching.value
  && runtimeQuery.data.value === undefined
  && timelineItems.value.length === 0
))
const sessionLoading = computed(() => sessionsInitialLoading.value || runtimeInitialLoading.value)
const sessionLoadingText = computed(() => (
  sessionsInitialLoading.value ? '正在加载智能体会话...' : '正在恢复会话内容...'
))

const createSessionMutation = useMutation({
  mutationFn: (sessionName?: string | null) => createAgentSession({
    agent_id: agentId.value,
    scope: scope.value,
    session_name: sessionName ?? selectedAgent.value?.default_session_name ?? `${contextTitle.value} 对话`,
  }),
})

const selectedAgent = computed<AgentDescriptor | null>(() => agentsQuery.data.value?.[0] ?? null)
const selectedAgentSupportsImageInput = computed(() => Boolean(selectedAgent.value?.supports_image_input))
const hasContextIssue = computed(() => (
  selectedAgent.value !== null
  && selectedAgent.value.available === false
  && props.routeAvailable
))
const hasBindingIssue = computed(() => (
  hasContextIssue.value || (selectedAgent.value !== null && selectedAgent.value.llm_binding_ready === false)
))
const agentIssueTitle = computed(() => (
  hasContextIssue.value ? `${agentDisplayName.value}当前不可用` : `${agentDisplayName.value}尚未绑定模型`
))
const agentIssueDetail = computed(() => (
  hasContextIssue.value
    ? selectedAgent.value?.unavailable_reason || '当前路由上下文缺少智能体所需信息。'
    : `当前智能体模型绑定 ${selectedAgent.value?.llm_slot || '未配置'} 还没有可用模型。先到“AI 设置”中创建模型并完成绑定，下一次执行会立即生效。`
))
const activeSessionScopeSummary = computed(() => (
  activeSessionScope.value
    ? resolveScopeSummary(activeSessionScope.value, activeSession.value?.session_name || '未命名会话')
    : {
        typeLabel: '',
        title: activeSession.value?.session_name || '未选择会话',
        colorClass: 'border-slate-200 bg-slate-50 text-slate-400',
      }
))
const activeSessionScopeTooltip = computed(() => (
  formatScopeTooltip('会话范围', activeSessionScopeSummary.value)
))
const routeScopeTooltip = computed(() => (
  formatScopeTooltip('当前路由', routeScopeSummary.value)
))
const currentRouteInActiveSessionScope = computed(() => {
  if (!activeSessionId.value || !activeSessionScope.value) {
    return true
  }
  return isRouteScopeInsideSessionScope(activeSessionScope.value, currentRouteScope.value)
})
const canApplySuggestedPatch = computed(() => (
  props.enablePagePatchActions
  && scope.value.page_id !== null
  && scope.value.page_id !== undefined
  && currentRouteInActiveSessionScope.value
))
const activeSessionLabel = computed(() => activeSession.value ? resolveSessionDisplayName(activeSession.value) : '未选择会话')
const activeSessionRouteLocation = computed(() => (
  activeSession.value ? buildSessionRouteLocation(activeSession.value) : null
))
const canOpenActiveSessionRoute = computed(() => {
  const target = activeSessionRouteLocation.value
  if (currentRouteInActiveSessionScope.value || !target) {
    return false
  }
  return !isCurrentRouteTarget(target)
})
const composerContextIssue = computed(() => {
  if (!currentRouteInActiveSessionScope.value) {
    return '当前页面不在此会话工作范围。'
  }
  if (!props.routeAvailable) {
    return props.routeUnavailableReason || '当前路由缺少工作空间上下文。'
  }
  return ''
})
const composerInputDisabled = computed(() => Boolean(composerContextIssue.value))
const imageUploadDisabledReason = computed(() => {
  if (!selectedAgentSupportsImageInput.value) {
    return '当前绑定模型不支持图片输入'
  }
  if (composerContextIssue.value) {
    return composerContextIssue.value
  }
  return ''
})
const imageUploadDisabled = computed(() => Boolean(imageUploadDisabledReason.value))
const resolvedToolCallDetails = computed(() => [
  ...extractTimelineToolDetails(timelineItems.value, memberRuns.value),
  ...memberRuns.value.flatMap(memberRun => extractTimelineToolDetails(memberRun.timeline_items)),
])
const activeToolDetail = computed<ToolCallDetail | null>(() => (
  resolvedToolCallDetails.value.find(item => item.id === activeToolDetailId.value) ?? null
))
const activeMemberRuns = computed(() => (
  activeMemberRunIds.value
    .map(runId => memberRuns.value.find(item => item.run_id === runId))
    .filter((item): item is AgentMemberRunItem => Boolean(item))
))
const panelShellClass = computed(() => (
  props.embedded
    ? 'flex h-full min-h-0 flex-col bg-transparent'
    : 'flex min-h-[720px] flex-col overflow-hidden rounded-3xl border border-slate-200 bg-white/95 shadow-sm backdrop-blur'
))
const timelineDisplayItems = computed(() => buildTimelineDisplayItems(timelineItems.value, {
  pendingRequirement: pendingRequirement.value,
  memberRuns: memberRuns.value,
}))
const composerActionDisabled = computed(() => (
  isStreaming.value
    ? isInterrupting.value
    : sendInFlight.value || pendingRequirement.value !== null || (!composerText.value.trim() && pendingImageAttachments.value.length === 0) || hasBindingIssue.value || composerInputDisabled.value
))

/**
 * 从按会话分片的状态中读取当前值。
 */
function readSessionValue<T>(source: Record<string, T>, sessionId: string, fallback: T): T {
  if (!sessionId) {
    return fallback
  }
  return source[sessionId] ?? fallback
}

/**
 * 向按会话分片的状态写入值，确保切会话时不同消息流互不污染。
 */
function writeSessionValue<T>(source: Record<string, T>, sessionId: string, value: T) {
  if (!sessionId) {
    return
  }
  source[sessionId] = value
}

/**
 * 继续 paused run 时插入一个本地 assistant 占位，后续 SSE delta 会接管内容。
 */
function appendLocalAssistantPlaceholder(sessionId: string, runId: string | null) {
  const currentItems = readSessionValue(timelineItemsBySession.value, sessionId, [])
  const item = {
    ...buildAgentLocalTimelineItem(sessionId, {
      runId,
      kind: 'message',
      role: 'assistant',
      content: '',
      status: 'running',
    }),
    order_index: Math.max(-1, ...currentItems.map(entry => entry.order_index)) + 1,
  }
  agentSessionStore.appendTimelineItems(sessionId, [item])
  agentSessionStore.setStreamingTimelineItemId(sessionId, item.id)
}

/**
 * 更新当前会话的流式执行标记，用于脱离 task store 后控制按钮状态。
 */
function setSessionStreaming(sessionId: string, value: boolean) {
  agentSessionStore.setStreaming(sessionId, value)
}

/**
 * 为一次会话流创建可中断控制器；同一会话旧控制器会被新请求替换。
 */
function createStreamAbortController(runId: string) {
  const controller = new AbortController()
  streamAbortControllersByRun.set(runId, controller)
  return controller
}

/**
 * 清理流控制器，只删除当前请求对应的实例，避免误删后续新请求。
 */
function clearStreamAbortController(runId: string, controller: AbortController) {
  if (streamAbortControllersByRun.get(runId) === controller) {
    streamAbortControllersByRun.delete(runId)
  }
}

/**
 * 判断 active-run 是否需要继续订阅后台事件。
 */
function shouldSubscribeRunEvents(run: AgentActiveRunItem) {
  return Boolean(run.run_id && (run.status === 'pending' || run.status === 'running' || run.status === 'cancelling'))
}

/**
 * 判断 runtime 快照是否属于当前会话；路由变化时仍允许保留并刷新原会话。
 */
function isRuntimeSnapshotForCurrentSession(runtime: AgentSessionRuntimeSnapshot) {
  if (runtime.session.session_id !== activeSessionId.value) {
    return false
  }
  return true
}

/**
 * 判断 runtime 快照是否可以写入本地状态；流式中只接受暂停、终态或非当前 run 的权威收敛。
 */
function shouldApplyRuntimeSnapshot(runtime: AgentSessionRuntimeSnapshot) {
  if (!isRuntimeSnapshotForCurrentSession(runtime)) {
    return false
  }
  if (hasLocalActiveRunProgress(runtime)) {
    return false
  }
  if (!isStreaming.value) {
    return true
  }
  const sessionId = activeSessionId.value
  const currentRunId = readSessionValue(currentRunIdBySession.value, sessionId, null)
  const snapshotRun = runtime.active_run ?? runtime.last_run
  if (!snapshotRun?.run_id || (currentRunId && snapshotRun.run_id !== currentRunId)) {
    return false
  }
  return runtime.active_run?.status === 'paused'
    || runtime.active_run?.status === 'cancelling'
    || runtime.active_run === null
}

/**
 * 判断本地是否已有同一 active run 的流式片段；有进度时不能用运行中快照覆盖消息。
 */
function hasLocalActiveRunProgress(runtime: AgentSessionRuntimeSnapshot) {
  return hasLocalActiveRunProgressForSession(activeSessionId.value, runtime)
}

/**
 * 判断指定会话本地是否已有同一 active run 的流式片段。
 */
function hasLocalActiveRunProgressForSession(sessionId: string, runtime: AgentSessionRuntimeSnapshot) {
  const run = runtime.active_run
  if (!sessionId || !run || !shouldSubscribeRunEvents(run)) {
    return false
  }
  const localRunId = readSessionValue(currentRunIdBySession.value, sessionId, null)
    ?? readSessionValue(activeRunBySession.value, sessionId, null)?.run_id
    ?? null
  if (localRunId !== run.run_id) {
    return false
  }
  return agentSessionStore.getLastSequence(sessionId, run.run_id) >= 0
    || readSessionValue(streamingTimelineItemIdBySession.value, sessionId, null) !== null
}

/**
 * 订阅已存在后台 run 的事件流；用于刷新、切回会话和停止后的状态收敛。
 */
function ensureRunEventSubscription(sessionId: string, run: AgentActiveRunItem, afterEventIndex = -1) {
  if (componentDisposed || !sessionId || !run.run_id || streamAbortControllersByRun.has(run.run_id)) {
    return
  }
  const streamAbortController = createStreamAbortController(run.run_id)
  setSessionStreaming(sessionId, true)
  streamAgentRunEvents(
    sessionId,
    run.run_id,
    scope.value,
    {
      agent_id: agentId.value,
      event_index: Math.max(afterEventIndex, agentSessionStore.getLastSequence(sessionId, run.run_id)),
    },
    { onEvent: event => handleRunEvent(event, sessionId), signal: streamAbortController.signal },
  )
    .then(() => {
      if (!componentDisposed) {
        return finalizeRun(sessionId)
      }
      return undefined
    })
    .catch((error) => {
      if (error instanceof AgentStreamInterruptedError) {
        return
      }
      logClientWarning('Failed to subscribe agent run events', error)
    })
    .finally(() => {
      clearStreamAbortController(run.run_id, streamAbortController)
      setSessionStreaming(sessionId, false)
    })
}

/**
 * 启动强制结束按钮的可用状态刷新计时。
 */
function startForceCancelTicker() {
  if (forceCancelTimer !== null) {
    return
  }
  forceCancelTick.value = Date.now()
  forceCancelTimer = window.setInterval(() => {
    forceCancelTick.value = Date.now()
  }, 1000)
}

/**
 * 停止强制结束状态刷新计时。
 */
function stopForceCancelTicker() {
  if (forceCancelTimer === null) {
    return
  }
  window.clearInterval(forceCancelTimer)
  forceCancelTimer = null
}

/**
 * 判断指定会话是否仍在流式运行或处于 Agno 非终态运行中。
 */
function isSessionRunning(sessionId: string) {
  if (!sessionId) {
    return false
  }
  if (readSessionValue(streamingBySession.value, sessionId, false)) {
    return true
  }
  const run = readSessionValue(activeRunBySession.value, sessionId, null)
  return run?.status === 'pending' || run?.status === 'running' || run?.status === 'cancelling'
}

/**
 * 同步后端 active-run 状态，并把 paused requirement 下沉到本地会话缓存。
 */
function syncActiveRun(sessionId: string, run: AgentActiveRunItem | null) {
  agentSessionStore.setActiveRun(sessionId, run)
}

/**
 * 打开上下文用量浮窗时刷新一次最新统计，避免长 run 中错过事件后读数陈旧。
 */
function handleContextUsageOpen() {
  void refreshContextStatusForSession(activeSessionId.value)
}

/**
 * 单独刷新会话上下文统计，不影响消息列表与工具详情的权威快照。
 */
async function refreshContextStatusForSession(sessionId: string) {
  if (!sessionId) {
    return
  }
  try {
    const runtimeRequest = resolveSessionRuntimeRequest(sessionId)
    const latestStatus = await getAgentSessionContextStatus(sessionId, runtimeRequest.scope, runtimeRequest.agentId)
    agentSessionStore.setContextStatus(sessionId, latestStatus)
  } catch (error) {
    logClientWarning('Failed to refresh agent context status', error)
  }
}

watch(
  () => props.headerScopeTarget,
  async (target) => {
    if (!target) {
      headerScopeReady.value = false
      return
    }
    await nextTick()
    headerScopeReady.value = document.querySelector(target) !== null
  },
  { immediate: true },
)

watch(
  () => props.headerActionsTarget,
  async (target) => {
    if (!target) {
      headerActionsReady.value = false
      return
    }
    await nextTick()
    headerActionsReady.value = document.querySelector(target) !== null
  },
  { immediate: true },
)

watch(
  () => [sessionsQuery.data.value, agentId.value] as const,
  ([sessions]) => {
    if (virtualNewSessionKey.value) {
      activeSessionId.value = ''
      pendingRouteSessionId.value = ''
      return
    }

    if (!sessions?.length) {
      activeSessionId.value = ''
      pendingRouteSessionId.value = ''
      return
    }

    const pendingSession = pendingRouteSessionId.value
      ? sessions.find(item => item.session_id === pendingRouteSessionId.value)
      : null
    if (pendingSession) {
      activeSessionId.value = pendingSession.session_id
      pendingRouteSessionId.value = ''
      return
    }

    const currentSession = activeSessionId.value
      ? sessions.find(item => item.session_id === activeSessionId.value)
      : null
    if (currentSession) {
      return
    }

    const persistedSessionId = getSelectedSession(scope.value, agentId.value, sessions)
    if (persistedSessionId) {
      activeSessionId.value = persistedSessionId
      return
    }

    activeSessionId.value = findLatestSessionForScope(sessions, scope.value)?.session_id ?? ''
  },
  { immediate: true },
)

watch(
  () => [
    sessionsQuery.data.value,
    sessionsQuery.isFetching.value,
    props.routeAvailable,
    agentId.value,
    scope.value.project_id,
    activeSessionId.value,
    activeSessionScope.value?.project_id ?? null,
    pendingUnavailableSessionSelectionKey.value,
  ] as const,
  ([, isFetching]) => {
    if (!shouldAutoSelectRunnableSessionForUnavailableRoute()) {
      if (props.routeAvailable) {
        pendingUnavailableSessionSelectionKey.value = null
      }
      return
    }
    if (selectFirstRunnableSession()) {
      pendingUnavailableSessionSelectionKey.value = null
      return
    }
    if (!isFetching) {
      pendingUnavailableSessionSelectionKey.value = null
    }
  },
  { immediate: true },
)

watch(
  () => runtimeQuery.data.value,
  (runtime) => {
    if (!activeSessionId.value || !runtime || !isRuntimeSnapshotForCurrentSession(runtime)) {
      return
    }
    const sessionId = activeSessionId.value
    if (shouldApplyRuntimeSnapshot(runtime)) {
      agentSessionStore.applyRuntimeSnapshot(sessionId, runtime)
    }
    if (runtime.active_run && shouldSubscribeRunEvents(runtime.active_run)) {
      ensureRunEventSubscription(sessionId, runtime.active_run, agentSessionStore.getLastSequence(sessionId, runtime.active_run.run_id))
    }
  },
  { immediate: true },
)

watch(activeSessionId, () => {
  sessionMenuVisible.value = false
  toolDetailDialogVisible.value = false
  memberRunDialogVisible.value = false
  activeToolDetailId.value = null
  activeMemberRunIds.value = []
  if (activeSessionId.value) {
    const session = sessionsQuery.data.value?.find(item => item.session_id === activeSessionId.value)
    if (!session || isSessionTargetCurrentScope(session, scope.value)) {
      setSelectedSession(scope.value, agentId.value, activeSessionId.value)
    }
  }
})

watch(activeRun, (run) => {
  if (run?.status === 'cancelling') {
    startForceCancelTicker()
  } else {
    stopForceCancelTicker()
  }
}, { immediate: true })

watch(
  () => props.autoCreateKey,
  (autoCreateKey) => {
    if (autoCreateKey === null || autoCreateKey === undefined || autoCreateKey === '') {
      return
    }
    if (autoCreateKey === lastHandledAutoCreateKey.value) {
      return
    }
    lastHandledAutoCreateKey.value = autoCreateKey
    handleVirtualNewSession(autoCreateKey)
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  componentDisposed = true
  for (const controller of streamAbortControllersByRun.values()) {
    if (!controller.signal.aborted) {
      controller.abort()
    }
  }
  streamAbortControllersByRun.clear()
  stopForceCancelTicker()
})

/**
 * 手动进入虚拟新会话态；真正的后端会话会在第一条消息发送时创建。
 */
function handleCreateSession() {
  if (hasBindingIssue.value) {
    Message.error(agentIssueDetail.value)
    return
  }
  if (!props.routeAvailable) {
    Message.warning(props.routeUnavailableReason || '当前路由缺少工作空间上下文。')
    return
  }
  virtualNewSessionSequence.value += 1
  enterVirtualNewSession(`manual:${virtualNewSessionSequence.value}`, null)
}

/**
 * 响应全局侧栏的助手切换动作：仅进入虚拟新会话态，并在需要时跳转到该助手默认工作台。
 */
function handleVirtualNewSession(autoCreateKey: string | number) {
  if (hasBindingIssue.value) {
    Message.error(agentIssueDetail.value)
    return
  }
  if (!props.routeAvailable) {
    if (selectFirstRunnableSession()) {
      return
    }
    pendingUnavailableSessionSelectionKey.value = autoCreateKey
    return
  }
  enterVirtualNewSession(autoCreateKey, props.autoNavigateTarget)
}

/**
 * 判断不可启动路由下是否需要自动回落到首个可运行历史会话。
 */
function shouldAutoSelectRunnableSessionForUnavailableRoute(): boolean {
  if (props.routeAvailable || agentId.value !== 'agent-coordinator' || scope.value.project_id) {
    return false
  }
  if (activeSessionId.value && manuallySelectedSessionId.value === activeSessionId.value) {
    return false
  }
  if (pendingUnavailableSessionSelectionKey.value) {
    return true
  }
  if (!activeSessionId.value) {
    return true
  }
  return !activeSessionScope.value?.project_id
}

/**
 * 当前路由不可启动时，优先选中第一个带项目上下文的会话，但不切换路由。
 */
function selectFirstRunnableSession(): boolean {
  const targetSession = (sessionsQuery.data.value ?? []).find((session) => {
    const sessionScope = resolveSessionScope(session)
    if (!sessionScope || !buildSessionRouteLocation(session)) {
      return false
    }
    if (agentId.value === 'agent-coordinator' && !sessionScope.project_id) {
      return false
    }
    return true
  })
  if (!targetSession) {
    return false
  }
  virtualNewSessionKey.value = null
  pendingRouteSessionId.value = ''
  manuallySelectedSessionId.value = ''
  activeSessionId.value = targetSession.session_id
  return true
}

/**
 * 统一设置虚拟新会话态，避免助手切换和手动新会话提前制造空会话。
 */
function enterVirtualNewSession(virtualKey: string | number, navigateTarget: string | null | undefined) {
  virtualNewSessionKey.value = virtualKey
  activeSessionId.value = ''
  pendingRouteSessionId.value = ''
  manuallySelectedSessionId.value = ''
  sessionMenuVisible.value = false
  if (navigateTarget && navigateTarget !== route.fullPath) {
    void router.push(navigateTarget)
  }
}

/**
 * 打开当前会话绑定的工作页面，让用户回到可继续运行该会话的路由。
 */
function openActiveSessionRoute() {
  const targetLocation = activeSessionRouteLocation.value
  if (!targetLocation || isCurrentRouteTarget(targetLocation)) {
    return
  }
  pendingRouteSessionId.value = activeSessionId.value
  void router.push(targetLocation)
}

/**
 * 比较目标工作页和当前路由；目标页不带 query 时允许当前路由携带筛选参数。
 */
function isCurrentRouteTarget(targetLocation: string): boolean {
  return targetLocation === route.fullPath || targetLocation === route.path
}

/**
 * 确保当前存在一个活跃会话；若没有则自动创建。
 */
async function ensureActiveSession() {
  if (activeSessionId.value) {
    return activeSessionId.value
  }
  if (!props.routeAvailable) {
    throw new Error(props.routeUnavailableReason || '当前路由缺少工作空间上下文。')
  }
  const created = await createSessionMutation.mutateAsync(`${contextTitle.value} 会话`)
  virtualNewSessionKey.value = null
  activeSessionId.value = created.session_id
  sessionMenuVisible.value = false
  await queryClient.invalidateQueries({ queryKey: ['ai-sessions'] })
  return created.session_id
}

/**
 * 统一处理输入框主按钮：空闲态发送，运行态中断。
 */
function handleComposerPrimaryAction() {
  if (isStreaming.value) {
    void handleInterruptRun()
    return
  }
  if (sendInFlight.value) {
    return
  }
  void handleSend()
}

/**
 * 切换会话下拉菜单显示状态。
 */
function toggleSessionMenu() {
  if (hasBindingIssue.value) {
    return
  }
  sessionMenuVisible.value = !sessionMenuVisible.value
}

/**
 * 关闭会话切换菜单。
 */
function closeSessionMenu() {
  sessionMenuVisible.value = false
}

/**
 * 切换到指定会话并关闭菜单。
 */
function handleSwitchSession(sessionId: string) {
  closeSessionMenu()
  virtualNewSessionKey.value = null
  manuallySelectedSessionId.value = sessionId
  const session = sessionsQuery.data.value?.find(item => item.session_id === sessionId)
  if (!session) {
    activeSessionId.value = sessionId
    return
  }

  const sessionScope = resolveSessionScope(session)
  if (sessionScope) {
    setSelectedSession(sessionScope, agentId.value, sessionId)
  }

  const targetLocation = buildSessionRouteLocation(session)
  activeSessionId.value = sessionId
  if (targetLocation && targetLocation !== route.fullPath) {
    pendingRouteSessionId.value = sessionId
    void router.push(targetLocation)
    return
  }

  pendingRouteSessionId.value = ''
}

/**
 * 上传用户选择的图片附件，并把结果加入当前 Composer 待发送列表。
 */
async function handleUploadImage(file: File) {
  if (imageUploadDisabledReason.value) {
    Message.warning(imageUploadDisabledReason.value)
    return
  }
  if (!isAllowedImageFile(file)) {
    Message.error('图片附件仅支持 png、jpg、jpeg、webp。')
    return
  }
  if (file.size > IMAGE_ATTACHMENT_MAX_BYTES) {
    Message.error('单张图片不能超过 10MB。')
    return
  }

  let sessionId = ''
  try {
    sessionId = await ensureActiveSession()
  } catch (error) {
    Message.error(error instanceof Error ? error.message : '初始化智能体会话失败。')
    return
  }

  writeSessionValue(imageUploadingBySession.value, sessionId, true)
  try {
    const attachment = await uploadAgentImageAttachment(sessionId, scope.value, file, agentId.value)
    agentSessionStore.setPendingImageAttachments(sessionId, [
      ...readSessionValue(pendingImageAttachmentsBySession.value, sessionId, []),
      attachment,
    ])
  } catch (error) {
    Message.error(error instanceof Error ? error.message : '上传图片失败。')
  } finally {
    writeSessionValue(imageUploadingBySession.value, sessionId, false)
  }
}

/**
 * 从当前待发送列表移除图片，并通知后端归档附件记录。
 */
async function handleRemoveImage(attachmentId: number) {
  const sessionId = activeSessionId.value
  if (!sessionId) {
    return
  }
  pendingImageAttachments.value = pendingImageAttachments.value.filter(item => item.id !== attachmentId)
  try {
    await deleteAgentImageAttachment(sessionId, scope.value, attachmentId, agentId.value)
  } catch (error) {
    Message.error(error instanceof Error ? error.message : '删除图片失败。')
  }
}

/**
 * 将图片附件保存为工作空间资源，并刷新资源相关缓存。
 */
async function handlePromoteImage(attachmentId: number) {
  const sessionId = activeSessionId.value
  if (!sessionId) {
    return
  }
  try {
    const promoted = await promoteAgentImageAttachment(sessionId, scope.value, attachmentId, {}, agentId.value)
    pendingImageAttachments.value = pendingImageAttachments.value.map(item => (
      item.id === promoted.id ? promoted : item
    ))
    await queryClient.invalidateQueries({ queryKey: ['workspace-assets'] })
    Message.success('图片已保存为资源。')
  } catch (error) {
    Message.error(error instanceof Error ? error.message : '保存为资源失败。')
  }
}

/**
 * 发送一条用户消息并启动新的智能体 run。
 */
async function handleSend() {
  if (hasBindingIssue.value) {
    Message.error(agentIssueDetail.value)
    return
  }
  if (composerContextIssue.value) {
    Message.warning(composerContextIssue.value)
    return
  }
  const message = composerText.value.trim()
  const attachments = [...pendingImageAttachments.value]
  if ((!message && attachments.length === 0) || isStreaming.value || sendInFlight.value) return
  if (attachments.length && !selectedAgentSupportsImageInput.value) {
    Message.error('当前绑定模型不支持图片输入。')
    return
  }
  const runScope = { ...scope.value }
  const runAgentId = agentId.value
  const runAgentDisplayName = agentDisplayName.value

  sendInFlight.value = true
  let sessionId = ''
  try {
    sessionId = await ensureActiveSession()
  } catch (error) {
    sendInFlight.value = false
    Message.error(error instanceof Error ? error.message : '初始化智能体会话失败。')
    return
  }

  composerText.value = ''
  pendingImageAttachments.value = []
  pendingRequirement.value = null
  lastRunIssue.value = null
  writeSessionValue(mutationRefreshEventsBySession.value, sessionId, [])

  agentSessionStore.beginLocalRun(sessionId, message, attachments)
  setSessionStreaming(sessionId, true)

  let runId = crypto.randomUUID()
  try {
    agentSessionStore.setCurrentRunId(sessionId, runId)
    syncActiveRun(sessionId, {
      run_id: runId,
      session_id: sessionId,
      agent_id: runAgentId,
      status: 'running',
      pending_requirement: null,
      content: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      cancel_requested_at: null,
      event_index: -1,
    })
    const streamAbortController = createStreamAbortController(runId)
    await streamAgentRun(sessionId, runScope, {
      run_id: runId,
      message,
      agent_id: runAgentId,
      image_attachment_ids: attachments.map(attachment => attachment.id),
    }, {
      onEvent: event => handleRunEvent(event, sessionId),
      signal: streamAbortController.signal,
    })
    clearStreamAbortController(runId, streamAbortController)
    await finalizeRun(sessionId)
  } catch (error) {
    if (error instanceof AgentStreamInterruptedError) {
      if (!componentDisposed) {
        void refreshAfterStreamInterrupted(sessionId)
      }
      return
    }
    if (isAgentRunActiveError(error)) {
      await recoverActiveRunAfterConflict(sessionId)
      return
    }
    const detail = error instanceof Error ? error.message : '智能体执行失败。'
    agentSessionStore.setLastIssue(sessionId, buildRunIssueState(detail, runAgentDisplayName))
    Message.error(detail)
  } finally {
    if (runId) {
      const controller = streamAbortControllersByRun.get(runId)
      if (controller) {
        clearStreamAbortController(runId, controller)
      }
    }
    sendInFlight.value = false
    setSessionStreaming(sessionId, false)
  }
}

/**
 * 继续当前暂停中的 run。
 */
async function handleContinueRun(decision: 'confirm' | 'reject') {
  const sessionId = activeSessionId.value
  const requirement = pendingRequirement.value
  const pausedRun = activeRun.value
  if (!sessionId || !requirement || pausedRun?.status !== 'paused') return

  pendingRequirement.value = null
  appendLocalAssistantPlaceholder(sessionId, requirement.run_id || pausedRun.run_id || '')
  setSessionStreaming(sessionId, true)
  syncActiveRun(sessionId, { ...pausedRun, status: 'running', pending_requirement: null })

  const runId = requirement.run_id || pausedRun.run_id || ''
  let streamAbortController: AbortController | null = null
  try {
    streamAbortController = createStreamAbortController(runId)
    await continueAgentSessionActiveRun(sessionId, scope.value, {
      agent_id: agentId.value,
      decision,
      tool_execution: requirement.tool_execution,
    }, {
      onEvent: event => handleRunEvent(event, sessionId),
      signal: streamAbortController.signal,
    })
    await finalizeRun(sessionId)
  } catch (error) {
    if (error instanceof AgentStreamInterruptedError) {
      if (!componentDisposed) {
        void refreshAfterStreamInterrupted(sessionId)
      }
      return
    }
    Message.error(error instanceof Error ? error.message : '继续智能体执行失败。')
  } finally {
    if (streamAbortController) {
      clearStreamAbortController(runId, streamAbortController)
    }
    setSessionStreaming(sessionId, false)
  }
}

/**
 * 提交结构化提问的全部答案，并一次性恢复当前 paused run。
 */
async function handleSubmitFeedbackRun(selections: AgentFeedbackSelection[]) {
  const sessionId = activeSessionId.value
  const requirement = pendingRequirement.value
  const pausedRun = activeRun.value
  if (!sessionId || !requirement || pausedRun?.status !== 'paused') return

  agentSessionStore.resolveUserFeedbackRequirement(sessionId, requirement, selections)
  appendLocalAssistantPlaceholder(sessionId, requirement.run_id || pausedRun.run_id || '')
  setSessionStreaming(sessionId, true)
  syncActiveRun(sessionId, { ...pausedRun, status: 'running', pending_requirement: null })

  const runId = requirement.run_id || pausedRun.run_id || ''
  let streamAbortController: AbortController | null = null
  try {
    streamAbortController = createStreamAbortController(runId)
    await continueAgentSessionActiveRun(sessionId, scope.value, {
      agent_id: agentId.value,
      decision: null,
      tool_execution: requirement.tool_execution,
      feedback_selections: selections,
    }, {
      onEvent: event => handleRunEvent(event, sessionId),
      signal: streamAbortController.signal,
    })
    await finalizeRun(sessionId)
  } catch (error) {
    if (error instanceof AgentStreamInterruptedError) {
      if (!componentDisposed) {
        void refreshAfterStreamInterrupted(sessionId)
      }
      return
    }
    Message.error(error instanceof Error ? error.message : '继续智能体执行失败。')
  } finally {
    if (streamAbortController) {
      clearStreamAbortController(runId, streamAbortController)
    }
    setSessionStreaming(sessionId, false)
  }
}

/**
 * 忽略结构化提问时取消当前 paused run，不向模型返回空答案。
 */
async function handleCancelPausedRun() {
  const sessionId = activeSessionId.value
  if (!sessionId || activeRun.value?.status !== 'paused') {
    return
  }

  try {
    pendingRequirement.value = null
    const response = await cancelAgentSessionActiveRun(sessionId, scope.value, {
      agent_id: agentId.value,
    })
    Message.info('已停止。')
    await finalizeRun(response.session_id, { preserveLocalCancelled: true })
  } catch (error) {
    Message.error(error instanceof Error ? error.message : '忽略失败，请稍后再试。')
  }
}

/**
 * 中断当前仍在执行中的 run；停止语义必须先写入后端，SSE 订阅只负责接收结果。
 */
async function handleInterruptRun() {
  const sessionId = activeSessionId.value
  if (!sessionId || !isStreaming.value || isInterrupting.value) {
    return
  }

  try {
    writeSessionValue(interruptingBySession.value, sessionId, true)
    const targetRunId = activeRun.value?.run_id || readSessionValue(currentRunIdBySession.value, sessionId, null)
    if (!targetRunId) {
      throw new Error('当前运行缺少 run_id，无法停止。')
    }
    const response = await cancelAgentSessionActiveRun(sessionId, scope.value, {
      agent_id: agentId.value,
    })
    syncActiveRun(sessionId, {
      run_id: response.run_id,
      session_id: response.session_id,
      agent_id: agentId.value,
      status: 'cancelling',
      pending_requirement: null,
      content: null,
      created_at: activeRun.value?.created_at ?? new Date().toISOString(),
      updated_at: new Date().toISOString(),
      cancel_requested_at: new Date().toISOString(),
      event_index: activeRun.value?.event_index ?? -1,
    })
    ensureRunEventSubscription(sessionId, {
      run_id: response.run_id,
      session_id: response.session_id,
      agent_id: agentId.value,
      status: 'cancelling',
      pending_requirement: null,
      content: null,
      created_at: activeRun.value?.created_at ?? new Date().toISOString(),
      updated_at: new Date().toISOString(),
      cancel_requested_at: new Date().toISOString(),
      event_index: activeRun.value?.event_index ?? -1,
    }, activeRun.value?.event_index ?? -1)
    window.setTimeout(() => {
      void refreshAfterStreamInterrupted(sessionId)
    }, 5000)
  } catch (error) {
    writeSessionValue(interruptingBySession.value, sessionId, false)
    Message.error(error instanceof Error ? error.message : '停止失败，请稍后再试。')
  }
}

/**
 * 停止中超过兜底窗口后，允许用户强制释放当前会话占用。
 */
async function handleForceCancelRun() {
  const sessionId = activeSessionId.value
  if (!sessionId || activeRun.value?.status !== 'cancelling') {
    return
  }
  try {
    const response = await cancelAgentSessionActiveRun(sessionId, scope.value, {
      agent_id: agentId.value,
      force: true,
    })
    Message.info('已停止。')
    await finalizeRun(response.session_id, { preserveLocalCancelled: true })
  } catch (error) {
    Message.error(error instanceof Error ? error.message : '强制结束失败，请稍后再试。')
  }
}

/**
 * 流式中断后的刷新不阻塞按钮反馈；失败只记录日志，避免误报为执行失败。
 */
async function refreshAfterStreamInterrupted(sessionId: string) {
  if (componentDisposed) {
    return
  }
  try {
    await finalizeRun(sessionId, { preserveLocalCancelled: true })
    const run = readSessionValue(activeRunBySession.value, sessionId, null)
    if (run && shouldSubscribeRunEvents(run)) {
      ensureRunEventSubscription(sessionId, run, run.event_index ?? -1)
    }
  } catch (error) {
    logClientWarning('Failed to refresh after stream interruption', error)
  }
}

/**
 * 发送新消息遇到后端 active-run 冲突时，刷新状态并恢复事件订阅。
 */
async function recoverActiveRunAfterConflict(sessionId: string) {
  await finalizeRun(sessionId)
  const run = readSessionValue(activeRunBySession.value, sessionId, null)
  if (run && shouldSubscribeRunEvents(run)) {
    ensureRunEventSubscription(sessionId, run, run.event_index ?? -1)
  }
  Message.warning('当前会话已有未结束的智能体运行，已恢复运行状态。')
}

/**
 * 判断异常是否表示当前会话已有未结束 run。
 */
function isAgentRunActiveError(error: unknown) {
  return error instanceof AgentRequestError && error.code === 'AI_SESSION_RUN_ACTIVE'
}

/**
 * 消费后端返回的流式事件，并同步更新消息、内嵌工具状态与待确认状态。
 */
function handleRunEvent(event: AgentRunEvent, fallbackSessionId = activeSessionId.value) {
  const normalizedEvent = normalizeAgnoRunEvent(event)
  const targetSessionId = normalizedEvent.session_id || fallbackSessionId
  if (!targetSessionId) {
    return
  }
  const isActiveEvent = targetSessionId === activeSessionId.value
  const result = agentSessionStore.applyRunEvent(targetSessionId, normalizedEvent, {
    agentId: agentId.value,
    agentDisplayName: agentDisplayName.value,
  })
  if (!result.applied) {
    return
  }
  switch (normalizedEvent.event) {
    case 'context.status':
      break
    case 'run.started':
      break
    case 'run.continued':
      break
    case 'message.delta':
      break
    case 'tool.started':
      break
    case 'tool.completed':
      appendMutationRefreshEvents(targetSessionId, normalizedEvent)
      emitMutationRefreshEvents(targetSessionId)
      break
    case 'tool.error':
      break
    case 'run.paused':
      break
    case 'run.cancelled':
      writeSessionValue(interruptingBySession.value, targetSessionId, false)
      if (isActiveEvent) {
        Message.info('已停止。')
      }
      break
    case 'run.error':
      writeSessionValue(interruptingBySession.value, targetSessionId, false)
      if (isActiveEvent && lastRunIssue.value) {
        Message.error(lastRunIssue.value.detail)
      }
      break
    case 'run.completed':
      writeSessionValue(interruptingBySession.value, targetSessionId, false)
      break
    default:
      break
  }
}

/**
 * 记录工具写入带来的领域刷新事件，供工具完成即时派发和 run 结束兜底派发复用。
 */
function appendMutationRefreshEvents(sessionId: string, event: AgentRunEvent): void {
  const nextEvents = buildMutationRefreshEvents(event, {
    workspaceId: scope.value.workspace_id ?? null,
    projectId: scope.value.project_id ?? null,
    pageId: scope.value.page_id ?? null,
    componentId: scope.value.component_id ?? null,
  })
  if (!nextEvents.length) {
    return
  }
  const currentEvents = readSessionValue(mutationRefreshEventsBySession.value, sessionId, [])
  writeSessionValue(
    mutationRefreshEventsBySession.value,
    sessionId,
    compactMutationRefreshEvents([...currentEvents, ...nextEvents]),
  )
}

/**
 * 批量派发领域刷新事件；同类同目标事件只保留最后一次。
 */
function emitMutationRefreshEvents(sessionId: string): void {
  const events = compactMutationRefreshEvents(readSessionValue(mutationRefreshEventsBySession.value, sessionId, []))
  if (!events.length) {
    return
  }
  writeSessionValue(mutationRefreshEventsBySession.value, sessionId, [])
  for (const event of events) {
    if (event.kind === 'page') {
      emit('page-updated', event)
    } else if (event.kind === 'project-pages') {
      emit('project-pages-updated', event)
    } else if (event.kind === 'project') {
      emit('project-updated', event)
    } else if (event.kind === 'component') {
      emit('component-updated', event)
    } else if (event.kind === 'asset') {
      emit('asset-updated', event)
    }
  }
}

/**
 * 在一次流式运行结束后刷新会话与消息缓存。
 */
async function finalizeRun(
  sessionId = activeSessionId.value,
  options: { preserveLocalCancelled?: boolean } = {},
) {
  if (!sessionId) {
    return
  }
  await queryClient.invalidateQueries({ queryKey: ['ai-sessions'] })
  await queryClient.invalidateQueries({ queryKey: ['ai-session-runtime'] })
  const latestSessions = (await sessionsQuery.refetch()).data ?? []
  const runtimeRequest = resolveSessionRuntimeRequest(sessionId, latestSessions)
  const latestRuntime = sessionId === activeSessionId.value
    ? (await runtimeQuery.refetch()).data ?? null
    : await getAgentSessionRuntime(sessionId, runtimeRequest.scope, runtimeRequest.agentId)
  const preserveLocalActiveRunTimeline = latestRuntime
    ? hasLocalActiveRunProgressForSession(sessionId, latestRuntime)
    : false
  if (latestRuntime) {
    if (!preserveLocalActiveRunTimeline) {
      agentSessionStore.applyRuntimeSnapshot(sessionId, latestRuntime)
    }
  }
  const latestRun = latestRuntime?.active_run ?? null
  if (!options.preserveLocalCancelled || !shouldPreserveLocalCancelled(sessionId, latestRun)) {
    syncActiveRun(sessionId, latestRun)
  }
  const latestContextStatus = latestRuntime?.context_status ?? null
  agentSessionStore.setContextStatus(sessionId, latestContextStatus)
  if (latestRuntime && !preserveLocalActiveRunTimeline) {
    await maybeAutonameActiveSession(latestSessions, latestRuntime.timeline_items, sessionId)
  }
  emitMutationRefreshEvents(sessionId)
  if (!preserveLocalActiveRunTimeline) {
    agentSessionStore.setStreamingTimelineItemId(sessionId, null)
  }
}

/**
 * 中断后后端可能短暂仍返回 running/pending；此时保留本地 cancelled，等下一轮刷新自然收敛。
 */
function shouldPreserveLocalCancelled(sessionId: string, latestRun: AgentActiveRunItem | null) {
  const localRun = readSessionValue(activeRunBySession.value, sessionId, null)
  return localRun?.status === 'cancelled'
    && latestRun !== null
    && (!localRun.run_id || localRun.run_id === latestRun.run_id)
    && (latestRun.status === 'pending' || latestRun.status === 'running')
}

/**
 * 返回会话列表中的运行状态标记。
 */
function getSessionRunBadge(sessionId: string) {
  const run = readSessionValue(activeRunBySession.value, sessionId, null)
  if (run?.status === 'paused') {
    return {
      label: '待确认',
      className: 'border-amber-200 bg-amber-50 text-amber-700',
    }
  }
  if (run?.status === 'cancelling') {
    return {
      label: '停止中',
      className: 'border-amber-200 bg-amber-50 text-amber-700',
    }
  }
  if (isSessionRunning(sessionId)) {
    return {
      label: readSessionValue(interruptingBySession.value, sessionId, false) ? '停止中' : '运行中',
      className: 'border-sky-200 bg-sky-50 text-sky-700',
    }
  }
  if (run?.status === 'failed') {
    return {
      label: '失败',
      className: 'border-red-200 bg-red-50 text-red-700',
    }
  }
  return null
}

/**
 * 校验前端允许上传给 Agent 的图片类型。
 */
function isAllowedImageFile(file: File) {
  if (ALLOWED_IMAGE_ATTACHMENT_TYPES.has(file.type)) {
    return true
  }
  return /\.(png|jpe?g|webp)$/i.test(file.name)
}

/**
 * 在首轮消息完成后尝试使用 Agno 自动生成会话名，避免会话列表长期停留在通用标题。
 */
async function maybeAutonameActiveSession(
  sessions: AgentSessionItem[],
  items: AgentTimelineItem[],
  sessionId = activeSessionId.value,
) {
  if (!sessionId || autoNamingSessionIds.has(sessionId)) {
    return
  }
  const session = sessions.find(item => item.session_id === sessionId)
  if (!shouldAutonameSession(session, items)) {
    return
  }
  autoNamingSessionIds.add(sessionId)
  try {
    const runtimeRequest = resolveSessionRuntimeRequest(sessionId, sessions)
    await renameAgentSession(sessionId, runtimeRequest.scope, { autogenerate: true }, runtimeRequest.agentId)
    await queryClient.invalidateQueries({ queryKey: ['ai-sessions'] })
    await sessionsQuery.refetch()
  } catch (error) {
    logClientWarning('Failed to autogenerate session name', error)
  } finally {
    autoNamingSessionIds.delete(sessionId)
  }
}

/**
 * 判断当前会话是否仍应视为“临时名”，满足首轮完成后自动改名的条件。
 */
function shouldAutonameSession(session: AgentSessionItem | null | undefined, items: AgentTimelineItem[]) {
  if (!session) {
    return false
  }
  const visibleMessages = items.filter(item => item.kind === 'message' && (item.role === 'user' || item.role === 'assistant'))
  if (visibleMessages.length < 2 || !visibleMessages.some(item => item.role === 'assistant' && (item.content ?? '').trim())) {
    return false
  }
  const sessionName = (session.session_name || '').trim()
  const fallbackNames = new Set([
    '',
    selectedAgent.value?.default_session_name ?? '',
    `${contextTitle.value} 会话`,
    `${contextTitle.value} 对话`,
  ])
  return fallbackNames.has(sessionName)
}

/**
 * 后台 run 可能在用户切路由后才收敛；这时必须用会话自身 scope 读取和命名，避免写入当前路由状态。
 */
function resolveSessionRuntimeRequest(sessionId: string, sessions: AgentSessionItem[] = sessionsQuery.data.value ?? []) {
  const session = sessions.find(item => item.session_id === sessionId)
  const sessionScope = session ? resolveSessionScope(session) : null
  return {
    scope: sessionScope ?? scope.value,
    agentId: session?.agent_id ?? agentId.value,
  }
}

/**
 * 打开工具详情弹窗，查看当前保存的输入输出内容。
 */
function openToolDetail(toolId: string) {
  activeToolDetailId.value = toolId
  toolDetailDialogVisible.value = true
}

function openMemberRunDetail(toolId: string) {
  const tool = resolvedToolCallDetails.value.find(item => item.id === toolId)
  const memberRunIds = tool?.delegatedMemberRuns.map(item => item.run_id) ?? []
  if (!memberRunIds.length) {
    openToolDetail(toolId)
    return
  }
  activeMemberRunIds.value = memberRunIds
  memberRunDialogVisible.value = true
}

/**
 * 把建议 patch 应用到父级 Monaco 缓冲区。
 */
function applySuggestedPatch(patch: AgentSuggestedPatch) {
  if (!canApplySuggestedPatch.value) {
    Message.warning('当前上下文不支持直接写入页面编辑器。')
    return
  }
  emit('apply-suggested-content', patch.proposed_content)
  Message.success('已将智能体建议写入当前编辑器缓冲区。')
}

/**
 * 将建议 patch 暂存到草稿箱，方便稍后再应用。
 */
function saveDraftPatch(patch: AgentSuggestedPatch) {
  if (!draftPatches.value.some(item => item.unified_diff === patch.unified_diff)) {
    draftPatches.value.unshift(patch)
  }
  Message.success('建议已加入草稿箱。')
}

/**
 * 从草稿箱删除一条草稿建议。
 */
function removeDraftPatch(patch: AgentSuggestedPatch) {
  draftPatches.value = draftPatches.value.filter(item => item.unified_diff !== patch.unified_diff)
}

/**
 * 跳转到 AI 设置页，供用户先完成模型绑定。
 */
function goToAiSettings() {
  router.push({ name: 'accountAiSettings' })
}
</script>
