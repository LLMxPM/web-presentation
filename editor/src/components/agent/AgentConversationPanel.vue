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
      :sessions="displayedSessions"
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
        :sessions="displayedSessions"
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
            v-if="composerContextRouteTarget"
            type="button"
            class="inline-flex h-7 shrink-0 items-center gap-1 rounded-md border border-amber-200 bg-white px-2 text-[11px] font-semibold text-amber-700 shadow-sm transition hover:border-amber-300 hover:bg-amber-100"
            :aria-label="composerContextRouteTitle"
            :title="composerContextRouteTitle"
            @click="openComposerContextRoute"
          >
            <ExternalLink class="h-3 w-3" />
            {{ composerContextRouteLabel }}
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
          :hitl-loading="hitlActionInFlight"
          :can-apply-suggested-patch="canApplySuggestedPatch"
          :hitl-force-release-available="hitlForceReleaseAvailable"
          @upload-image="handleUploadImage"
          @remove-image="handleRemoveImage"
          @promote-image="handlePromoteImage"
          @hitl-confirm="handleContinueRun('confirm')"
          @hitl-reject="handleContinueRun('reject')"
          @hitl-feedback-submit="handleSubmitFeedbackRun"
          @hitl-cancel="handleCancelPausedRun"
          @hitl-force-release="handleForceReleaseHitl"
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
  createAgentSession,
  getAgentSessionContextStatus,
  getAgentSessionRuntime,
  listAgents,
  listAgentSessions,
  renameAgentSession,
  streamAgentRun,
  streamAgentRunEvents,
} from '@/api/ai'
import { getErrorMessage } from '@/api/http'
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
import { useAgentHitlActions } from '@/components/agent/agent-hitl-actions'
import { useAgentImageAttachments } from '@/components/agent/agent-image-attachments'
import { useAgentStreamControllers } from '@/components/agent/agent-stream-controllers'
import { useAgentForceCancelTicker } from '@/components/agent/agent-force-cancel-ticker'
import { useAgentSessionNavigation } from '@/components/agent/agent-session-navigation'
import {
  buildSessionRouteLocation,
  findLatestSessionForScope,
  formatScopeTooltip,
  getSelectedSession,
  getSelectedWorkspaceSession,
  isRouteScopeInsideSessionScope,
  isSessionTargetCurrentScope,
  resolveScopeSummary,
  resolveSessionDisplayName,
  resolveSessionScope,
  setSelectedSession,
  setSelectedWorkspaceSession,
} from '@/components/agent/agent-session-scope'
import { normalizeAgentRunEvent } from '@/components/agent/agent-run-state'
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
const knownSessionsById = ref<Record<string, AgentSessionItem>>({})
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
const autoNamingSessionIds = new Set<string>()
const hitlActionInFlightBySession = ref<Record<string, boolean>>({})
let componentDisposed = false
const {
  abortAllStreamControllers,
  clearStreamAbortController,
  createStreamAbortController,
  getStreamAbortController,
  hasStreamAbortController,
} = useAgentStreamControllers()
const {
  forceCancelTick,
  startForceCancelTicker,
  stopForceCancelTicker,
} = useAgentForceCancelTicker()

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
  get: () => {
    const run = activeRun.value
    return run?.status === 'paused' ? run.pending_requirement : null
  },
  set: value => agentSessionStore.setPendingRequirement(activeSessionId.value, value),
})
const hitlActionInFlight = computed(() => readSessionValue(hitlActionInFlightBySession.value, activeSessionId.value, false))
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
    used: Math.max(0, status.context_used_tokens ?? 0),
    available: Math.max(0, status.context_input_budget_tokens ?? 0),
  }
})
const cancellingRunForceAvailable = computed(() => {
  const run = activeRun.value
  if (run?.status !== 'cancelling' || !run.cancel_requested_at) {
    return false
  }
  return forceCancelTick.value - new Date(run.cancel_requested_at).getTime() >= 30_000
})
const hitlForceReleaseAvailable = computed(() => activeRun.value?.status === 'paused' && pendingRequirement.value !== null)

const agentsQuery = useQuery(
  computed(() => ({
    queryKey: ['ai-agents', agentId.value, scope.value.scope_type, scope.value.workspace_id, scope.value.project_id, scope.value.page_id, scope.value.component_id, scope.value.source],
    queryFn: () => listAgents(scope.value, agentId.value),
    enabled: !!scope.value.workspace_id,
  })),
)

const sessionsQuery = useQuery(
  computed(() => ({
    queryKey: [
      'ai-sessions',
      agentId.value,
      scope.value.workspace_id,
      'workspace',
    ],
    queryFn: () => listAgentSessions(scope.value, agentId.value, 'workspace'),
    enabled: !!scope.value.workspace_id,
  })),
)

const activeSession = computed<AgentSessionItem | null>(() => (
  sessionsQuery.data.value?.find(item => item.session_id === activeSessionId.value)
    ?? knownSessionsById.value[activeSessionId.value]
    ?? null
))
const displayedSessions = computed<AgentSessionItem[] | undefined>(() => {
  const sessions = sessionsQuery.data.value
  const active = activeSession.value
  if (!active) {
    return sessions
  }
  if (!sessions) {
    return [active]
  }
  if (sessions.some(item => item.session_id === active.session_id)) {
    return sessions
  }
  return [active, ...sessions]
})
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
  return target !== route.fullPath && target !== route.path
})
const composerContextRouteTarget = computed(() => {
  if (canOpenActiveSessionRoute.value) {
    return activeSessionRouteLocation.value
  }
  if (!props.routeAvailable && props.autoNavigateTarget) {
    const target = props.autoNavigateTarget
    return target !== route.fullPath && target !== route.path ? target : null
  }
  return null
})
const composerContextRouteLabel = computed(() => (
  canOpenActiveSessionRoute.value ? '打开' : '前往'
))
const composerContextRouteTitle = computed(() => (
  canOpenActiveSessionRoute.value ? '打开此会话工作页面' : '前往可运行页面'
))
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

const {
  closeSessionMenu,
  handleCreateSession,
  handleSwitchSession,
  handleVirtualNewSession,
  openActiveSessionRoute,
  toggleSessionMenu,
} = useAgentSessionNavigation({
  activeSessionId,
  manuallySelectedSessionId,
  sessionMenuVisible,
  virtualNewSessionKey,
  virtualNewSessionSequence,
  getActiveSessionRouteLocation: () => activeSessionRouteLocation.value,
  getAgentId: () => agentId.value,
  getAgentIssueDetail: () => agentIssueDetail.value,
  getHasBindingIssue: () => hasBindingIssue.value,
  getRouteAvailable: () => props.routeAvailable,
  getRouteFullPath: () => route.fullPath,
  getRoutePath: () => route.path,
  getRouteUnavailableReason: () => props.routeUnavailableReason,
  getSessions: () => displayedSessions.value ?? [],
  pushRoute: target => void router.push(target),
})

/**
 * 打开当前提示对应的工作页面；会话越界时进入会话范围，不可运行时进入助手推荐入口。
 */
function openComposerContextRoute(): void {
  if (canOpenActiveSessionRoute.value) {
    openActiveSessionRoute()
    return
  }
  const target = composerContextRouteTarget.value
  if (target) {
    void router.push(target)
  }
}

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
 * 记录已经见过的会话；路由 scope 切换后仍可用会话自身 scope 恢复运行态。
 * @param sessions 从列表、创建结果或 runtime 快照获得的会话项
 */
function rememberSessions(sessions: AgentSessionItem[]) {
  if (!sessions.length) {
    return
  }
  knownSessionsById.value = {
    ...knownSessionsById.value,
    ...Object.fromEntries(sessions.map(session => [session.session_id, session])),
  }
}

/**
 * 更新当前会话的流式执行标记，用于脱离 task store 后控制按钮状态。
 */
function setSessionStreaming(sessionId: string, value: boolean) {
  agentSessionStore.setStreaming(sessionId, value)
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
 * 订阅已存在后台 run 的事件流；用于刷新、切回会话和停止后的状态收敛。
 */
function ensureRunEventSubscription(sessionId: string, run: AgentActiveRunItem, afterEventIndex = -1) {
  if (componentDisposed || !sessionId || !run.run_id || hasStreamAbortController(run.run_id)) {
    return
  }
  const streamAbortController = createStreamAbortController(run.run_id)
  const runtimeRequest = resolveSessionRuntimeRequest(sessionId)
  setSessionStreaming(sessionId, true)
  streamAgentRunEvents(
    sessionId,
    run.run_id,
    runtimeRequest.scope,
    {
      agent_id: runtimeRequest.agentId,
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
 * 判断指定会话是否仍在流式运行或处于平台非终态运行中。
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
 * 设置当前会话 HITL 操作请求状态，避免与 run streaming 状态相互污染。
 */
function setHitlActionInFlight(sessionId: string, value: boolean) {
  writeSessionValue(hitlActionInFlightBySession.value, sessionId, value)
}

const {
  handleContinueRun,
  handleSubmitFeedbackRun,
  handleCancelPausedRun,
  handleForceReleaseHitl,
} = useAgentHitlActions({
  getActiveSessionId: () => activeSessionId.value,
  getPendingRequirement: () => pendingRequirement.value,
  getActiveRun: () => activeRun.value,
  getScope: () => activeSessionRuntimeScope.value,
  getAgentId: () => activeSessionRuntimeAgentId.value,
  isDisposed: () => componentDisposed,
  setHitlActionInFlight,
  setSessionStreaming,
  syncActiveRun,
  setPendingRequirementForSession: (sessionId, requirement) => {
    agentSessionStore.setPendingRequirement(sessionId, requirement)
  },
  markPendingRequirementResolved: (sessionId, requirement, feedbackSelections) => {
    const previousItems = [...readSessionValue(timelineItemsBySession.value, sessionId, [])]
    agentSessionStore.markPendingRequirementResolved(sessionId, requirement, feedbackSelections)
    return () => {
      agentSessionStore.setTimelineItems(sessionId, previousItems)
    }
  },
  createStreamAbortController,
  clearStreamAbortController,
  handleRunEvent,
  finalizeRun,
  refreshAfterStreamInterrupted,
})

const {
  handlePromoteImage,
  handleRemoveImage,
  handleUploadImage,
} = useAgentImageAttachments({
  getActiveSessionId: () => activeSessionId.value,
  getScope: () => scope.value,
  getAgentId: () => agentId.value,
  getImageUploadDisabledReason: () => imageUploadDisabledReason.value,
  ensureActiveSession,
  getPendingImageAttachments: sessionId => readSessionValue(pendingImageAttachmentsBySession.value, sessionId, []),
  setPendingImageAttachments: (sessionId, attachments) => {
    agentSessionStore.setPendingImageAttachments(sessionId, attachments)
  },
  setImageUploading: (sessionId, uploading) => {
    writeSessionValue(imageUploadingBySession.value, sessionId, uploading)
  },
  invalidateWorkspaceAssets: async () => {
    await queryClient.invalidateQueries({ queryKey: ['workspace-assets'] })
  },
})

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
      return
    }

    if (sessions === undefined) {
      return
    }
    rememberSessions(sessions)

    if (!sessions?.length) {
      if (!activeSession.value) {
        activeSessionId.value = ''
      }
      return
    }

    const currentSession = activeSessionId.value
      ? sessions.find(item => item.session_id === activeSessionId.value)
      : null
    if (currentSession) {
      return
    }
    if (activeSession.value) {
      return
    }

    const workspaceSessionId = getSelectedWorkspaceSession(scope.value, agentId.value, sessions)
    if (workspaceSessionId) {
      activeSessionId.value = workspaceSessionId
      return
    }

    const exactSessionId = getSelectedSession(scope.value, agentId.value, sessions)
    if (exactSessionId) {
      activeSessionId.value = exactSessionId
      return
    }

    activeSessionId.value = findLatestSessionForScope(sessions, scope.value)?.session_id ?? ''
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
    rememberSessions([runtime.session])
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
    const session = activeSession.value
    const sessionScope = session ? resolveSessionScope(session) : null
    if (sessionScope) {
      setSelectedSession(sessionScope, agentId.value, activeSessionId.value)
      setSelectedWorkspaceSession(sessionScope, agentId.value, activeSessionId.value)
    } else if (!session || isSessionTargetCurrentScope(session, scope.value)) {
      setSelectedSession(scope.value, agentId.value, activeSessionId.value)
      setSelectedWorkspaceSession(scope.value, agentId.value, activeSessionId.value)
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
  abortAllStreamControllers()
  stopForceCancelTicker()
})

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
  rememberSessions([created])
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
    Message.error(getErrorMessage(error, '初始化智能体会话失败。'))
    return
  }

  composerText.value = ''
  pendingImageAttachments.value = []
  pendingRequirement.value = null
  lastRunIssue.value = null
  writeSessionValue(mutationRefreshEventsBySession.value, sessionId, [])

  const runId = crypto.randomUUID()
  agentSessionStore.beginLocalRun(sessionId, message, attachments, runId)
  setSessionStreaming(sessionId, true)

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
    await finalizeRunAfterStream(sessionId)
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
    const detail = getErrorMessage(error, '智能体执行失败。')
    const issue = buildRunIssueState(detail, runAgentDisplayName)
    agentSessionStore.setLastIssue(sessionId, issue)
    Message.warning(issue.title)
  } finally {
    if (runId) {
      const controller = getStreamAbortController(runId)
      if (controller) {
        clearStreamAbortController(runId, controller)
      }
    }
    sendInFlight.value = false
    setSessionStreaming(sessionId, false)
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
    const runtimeRequest = resolveSessionRuntimeRequest(sessionId)
    const response = await cancelAgentSessionActiveRun(sessionId, runtimeRequest.scope, {
      agent_id: runtimeRequest.agentId,
    })
    syncActiveRun(sessionId, {
      run_id: response.run_id,
      session_id: response.session_id,
      agent_id: runtimeRequest.agentId,
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
      agent_id: runtimeRequest.agentId,
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
    Message.error(getErrorMessage(error, '停止失败，请稍后再试。'))
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
    const runtimeRequest = resolveSessionRuntimeRequest(sessionId)
    const response = await cancelAgentSessionActiveRun(sessionId, runtimeRequest.scope, {
      agent_id: runtimeRequest.agentId,
      force: true,
    })
    Message.info('已停止。')
    await finalizeRun(response.session_id, { preserveLocalCancelled: true })
  } catch (error) {
    Message.error(getErrorMessage(error, '强制结束失败，请稍后再试。'))
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
  const normalizedEvent = normalizeAgentRunEvent(event)
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
    case 'member.tool.completed':
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
        Message.warning(lastRunIssue.value.title)
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
  const runtimeRequest = resolveSessionRuntimeRequest(sessionId)
  const nextEvents = buildMutationRefreshEvents(event, {
    workspaceId: runtimeRequest.scope.workspace_id ?? null,
    projectId: runtimeRequest.scope.project_id ?? null,
    pageId: runtimeRequest.scope.page_id ?? null,
    componentId: runtimeRequest.scope.component_id ?? null,
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
  const latestRun = latestRuntime?.active_run ?? null
  const localRunBeforeSnapshot = readSessionValue(activeRunBySession.value, sessionId, null)
  const preserveLocalCancelled = Boolean(
    options.preserveLocalCancelled
    && localRunBeforeSnapshot?.status === 'cancelled'
    && shouldPreserveLocalCancelled(localRunBeforeSnapshot, latestRun),
  )
  if (latestRuntime) {
    rememberSessions([latestRuntime.session])
    agentSessionStore.applyRuntimeSnapshot(sessionId, latestRuntime)
  }
  if (preserveLocalCancelled && localRunBeforeSnapshot) {
    syncActiveRun(sessionId, localRunBeforeSnapshot)
  } else {
    syncActiveRun(sessionId, latestRun)
  }
  const latestContextStatus = latestRuntime?.context_status ?? null
  agentSessionStore.setContextStatus(sessionId, latestContextStatus)
  if (latestRuntime) {
    await maybeAutonameActiveSession(latestSessions, latestRuntime.timeline_items, sessionId)
  }
  emitMutationRefreshEvents(sessionId)
  agentSessionStore.setStreamingTimelineItemId(sessionId, null)
}

/**
 * 流式请求已正常结束后的收尾刷新失败只影响 UI 收敛，不应误报为执行失败。
 * @param sessionId 需要刷新运行态的会话 ID
 */
async function finalizeRunAfterStream(sessionId: string) {
  try {
    await finalizeRun(sessionId)
  } catch (error) {
    logClientWarning('Failed to finalize agent run after stream closed', error)
    void refreshAfterStreamInterrupted(sessionId)
  }
}

/**
 * 中断后后端可能短暂仍返回 running/pending；此时保留本地 cancelled，等下一轮刷新自然收敛。
 */
function shouldPreserveLocalCancelled(localRun: AgentActiveRunItem, latestRun: AgentActiveRunItem | null) {
  return latestRun !== null
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
 * 在首轮消息完成后尝试自动生成会话名，避免会话列表长期停留在通用标题。
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
  const session = sessions.find(item => item.session_id === sessionId) ?? knownSessionsById.value[sessionId] ?? null
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
