<!-- 文件功能：提供通用内容助手面板，承载会话切换、消息流、工具调用详情与确认动作联动。 -->
<template>
  <Teleport v-if="props.headerScopeTarget && headerScopeReady" defer :to="props.headerScopeTarget">
    <AgentScopeStatus
      v-if="hasActiveTask"
      :type-label="currentFocusTypeLabel"
      :label="currentFocusLabel"
      :tooltip="currentFocusTooltip"
    />
    <AgentIdleHeaderBrand v-else />
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
    <header v-if="!props.headerActionsTarget || !headerActionsReady" class="flex min-w-0 items-center justify-between gap-3 border-b border-border-muted px-5 py-4">
      <AgentScopeStatus
        v-if="hasActiveTask"
        class="min-w-0 flex-1"
        :type-label="currentFocusTypeLabel"
        :label="currentFocusLabel"
        :tooltip="currentFocusTooltip"
      />
      <AgentIdleHeaderBrand v-else-if="!props.headerScopeTarget || !headerScopeReady" class="min-w-0 flex-1" />
      <span v-else class="min-w-0 flex-1" />
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
      <section v-if="hasBindingIssue" class="m-4 space-y-4 rounded-3xl border border-warning-border bg-warning-muted/80 p-5">
        <div class="space-y-2">
          <p class="text-base font-semibold text-warning-strong">{{ agentIssueTitle }}</p>
          <p class="text-sm leading-6 text-warning-strong">
            {{ agentIssueDetail }}
          </p>
        </div>
        <div class="rounded-2xl border border-surface/80 bg-surface/70 px-4 py-3 text-sm text-text-secondary">
          <p>当前 agent：{{ selectedAgent?.name || agentDisplayName }}</p>
          <p>当前模型：{{ currentLlmModelLabel || selectedAgent?.bound_llm_name || '未选择' }}</p>
        </div>
        <div class="flex justify-end">
          <UiButton variant="primary" @click="goToAiSettings">
            前往 AI 设置
          </UiButton>
        </div>
      </section>

      <template v-else>
        <AgentConversationBody
          :timeline-display-items="timelineDisplayItems"
          :draft-patches="draftPatches"
          :loading="sessionLoading"
          :loading-text="sessionLoadingText"
          :last-run-issue="lastRunIssue"
          :active-run="activeRun"
          :cancelling-run-force-available="cancellingRunForceAvailable"
          :is-streaming="isStreaming"
          :streaming-timeline-item-id="streamingTimelineItemId"
          :session-id="activeSessionId"
          :promote-attachment="handlePromoteImage"
          @apply-suggested-patch="applySuggestedPatch"
          @remove-draft-patch="removeDraftPatch"
          @open-tool-detail="openToolDetail"
          @force-cancel-run="handleForceCancelRun"
        />

        <section v-if="composerContextIssue"
          class="flex items-center gap-2 border-t border-warning-border bg-warning-muted/90 px-4 py-3 text-xs leading-5 text-warning-strong">
          <span class="min-w-0 flex-1">{{ composerContextIssue }}</span>
          <UiButton
            v-if="composerContextRouteTarget"
            variant="secondary"
            size="xs"
            class="inline-flex h-7 shrink-0 items-center gap-1 rounded-md border border-warning-border bg-surface px-2 text-[11px] font-semibold text-warning-strong shadow-sm transition hover:border-warning-border hover:bg-warning-muted"
            :aria-label="composerContextRouteTitle"
            :title="composerContextRouteTitle"
            @click="openComposerContextRoute"
          >
            <ExternalLink class="h-3 w-3" />
            {{ composerContextRouteLabel }}
          </UiButton>
        </section>

        <section
          v-if="showVisualCapabilityStatus"
          data-testid="visual-status-region"
          aria-label="视觉工具状态"
          class="flex shrink-0 items-center gap-1.5 border-t border-border-muted bg-canvas/80 px-3 py-1.5 text-[10px]"
        >
          <span
            class="inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 font-medium"
            :class="imageAnalysisAvailable
              ? 'border-success-border bg-success-muted text-success-strong'
              : 'border-border bg-surface text-text-disabled'"
            :title="imageAnalysisCapabilityTitle"
          >
            <Eye class="h-3 w-3" />
            看图
            <span>{{ imageAnalysisAvailable ? '可用' : '未配置' }}</span>
          </span>
          <span
            class="inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 font-medium"
            :class="imageGenerationAvailable
              ? 'border-ai-border bg-ai-muted text-ai-strong'
              : 'border-border bg-surface text-text-disabled'"
            :title="imageGenerationCapabilityTitle"
          >
            <WandSparkles class="h-3 w-3" />
            生成图片
            <span>{{ imageGenerationAvailable ? '可用' : '未配置' }}</span>
          </span>
          <UiButton
            v-if="visualCapabilityConfigurationRequired"
            variant="ghost"
            size="xs"
            class="ml-auto shrink-0 font-medium text-info transition hover:text-info-strong"
            title="前往 AI 设置配置视觉模型"
            @click="goToAiSettings"
          >
            配置
          </UiButton>
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
          @upload-image="handleUploadImages"
          @remove-image="handleRemoveImage"
          @hitl-confirm="handleContinueRun('confirm')"
          @hitl-reject="handleContinueRun('reject')"
          @hitl-feedback-submit="handleSubmitFeedbackRun"
          @hitl-cancel="handleCancelPausedRun"
          @hitl-force-release="handleForceReleaseHitl"
          @apply-suggested-patch="applySuggestedPatch"
          @save-draft-patch="saveDraftPatch"
          @context-usage-open="handleContextUsageOpen"
          @action="handleComposerPrimaryAction">
          <template #contextControls>
            <div class="flex min-w-0 items-center gap-1 text-[10px] text-text-muted" aria-label="下一轮焦点与工作范围">
              <UiPopover :open="nextRunMenuVisible" side="top" align="start" :side-offset="8" content-class="w-[400px] space-y-3" @update:open="nextRunMenuVisible = $event">
                <template #trigger>
                  <UiButton
                    variant="ghost"
                    size="xs"
                    content-align="start"
                    class="h-6 w-full min-w-0 px-1.5 text-[10px]"
                    :title="`下一轮焦点与工作范围：${nextFocusCompactLabel}，${workScopeCompactLabel}`"
                  >
                    <component :is="nextFocusIcon" class="h-3 w-3 shrink-0" />
                    <span class="shrink-0 text-text-muted">下一轮</span>
                    <span class="min-w-0 flex-1 truncate text-left font-semibold text-text-emphasis">{{ nextFocusCompactLabel }}</span>
                    <span class="shrink-0 rounded-ui-sm px-1 py-px text-[9px] font-medium" :class="workScopeBadgeClass">{{ workScopeCompactLabel }}</span>
                    <ChevronDown class="ml-auto h-3 w-3 shrink-0 opacity-60" />
                  </UiButton>
                </template>

                <div>
                  <p class="text-xs font-semibold text-text-emphasis">下一轮设置</p>
                  <p class="mt-1 text-[11px] leading-4 text-text-muted">选择下一轮对话的焦点与项目工作范围，不影响当前任务</p>
                </div>

                <div class="grid grid-cols-2 gap-3">
                  <section class="min-w-0 space-y-1.5">
                    <p class="text-[11px] font-semibold text-text-secondary">焦点</p>
                    <div v-if="sessionPreferences.focus_mode === 'follow_route'" class="rounded-ui-md bg-surface-muted px-2 py-1.5 text-[11px] leading-4 text-text-muted">
                      跟随当前路由：{{ formatFocusLabel(currentRouteScope) }}
                    </div>
                    <div v-else-if="sessionPreferences.focus_mode === 'pinned_project'" class="space-y-1">
                      <UiInput v-model="focusProjectSearch" placeholder="搜索项目" clearable class="h-8" aria-label="搜索固定焦点项目" />
                      <ul class="max-h-32 space-y-0.5 overflow-y-auto">
                        <li v-for="project in filteredFocusProjects" :key="project.id">
                          <label
                            class="flex cursor-pointer items-center gap-2 rounded-ui-sm px-1.5 py-1 text-xs text-text-secondary transition-colors hover:bg-surface-hover"
                            :class="{ 'bg-surface-selected text-text-emphasis': sessionPreferences.pinned_project_id === project.id }"
                          >
                            <UiCheckbox
                              :model-value="sessionPreferences.pinned_project_id === project.id"
                              @update:model-value="handlePinnedProjectChange(project.id)"
                            />
                            <span class="truncate">{{ project.name }}</span>
                          </label>
                        </li>
                        <li v-if="!filteredFocusProjects.length" class="px-1.5 py-1 text-xs text-text-muted">没有匹配的项目</li>
                      </ul>
                    </div>
                    <div v-else class="rounded-ui-md bg-surface-muted px-2 py-1.5 text-[11px] leading-4 text-text-muted">
                      作用于整个工作空间
                    </div>
                  </section>

                  <section class="min-w-0 space-y-1.5">
                    <p class="text-[11px] font-semibold text-text-secondary">项目工作范围</p>
                    <div v-if="sessionPreferences.work_scope_mode === 'workspace'" class="rounded-ui-md bg-surface-muted px-2 py-1.5 text-[11px] leading-4 text-text-muted">
                      智能体可操作工作空间内全部项目
                    </div>
                    <div v-else class="space-y-1">
                      <div class="flex items-center justify-between gap-2">
                        <span class="text-[11px] text-text-muted">已选 {{ sessionPreferences.allowed_project_ids.length }} 项</span>
                        <div class="flex items-center gap-0.5">
                          <UiButton variant="ghost" size="xs" class="h-6 px-1.5 text-[10px]" @click="selectAllWorkspaceProjects">全选</UiButton>
                          <UiButton variant="ghost" size="xs" class="h-6 px-1.5 text-[10px]" @click="clearSelectedProjects">清空</UiButton>
                        </div>
                      </div>
                      <UiInput v-model="workScopeProjectSearch" placeholder="搜索项目" clearable class="h-8" aria-label="搜索工作范围项目" />
                      <ul class="max-h-32 space-y-0.5 overflow-y-auto">
                        <li v-for="project in filteredWorkScopeProjects" :key="project.id">
                          <label
                            class="flex items-center gap-2 rounded-ui-sm px-1.5 py-1 text-xs text-text-secondary"
                            :class="isPinnedProject(project.id) ? 'cursor-not-allowed opacity-70' : 'cursor-pointer hover:bg-surface-hover'"
                          >
                            <UiCheckbox
                              :model-value="sessionPreferences.allowed_project_ids.includes(project.id)"
                              :disabled="isPinnedProject(project.id)"
                              @update:model-value="toggleAllowedProject(project.id)"
                            />
                            <span class="min-w-0 flex-1 truncate">{{ project.name }}</span>
                            <span v-if="isPinnedProject(project.id)" class="shrink-0 rounded-ui-sm bg-ai-muted px-1 py-px text-[9px] font-medium text-ai-strong">已固定</span>
                          </label>
                        </li>
                        <li v-if="!filteredWorkScopeProjects.length" class="px-1.5 py-1 text-xs text-text-muted">没有匹配的项目</li>
                      </ul>
                      <p v-if="!workspaceProjects.length" class="text-xs text-text-muted">暂无可选项目</p>
                      <p v-else-if="!sessionPreferences.allowed_project_ids.length" class="text-[11px] text-warning-strong">尚未选择项目，项目与页面操作将不可用。</p>
                    </div>
                  </section>
                </div>

                <section class="space-y-1.5 border-t border-border-muted pt-2.5">
                  <div class="flex items-center gap-2">
                    <span class="w-16 shrink-0 text-[11px] text-text-muted">焦点模式</span>
                    <UiSegmentedControl
                      class="min-w-0 flex-1"
                      :model-value="sessionPreferences.focus_mode"
                      :options="focusModeOptions"
                      @update:model-value="handleFocusModeChange"
                    />
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="w-16 shrink-0 text-[11px] text-text-muted">工作范围</span>
                    <UiSegmentedControl
                      class="min-w-0 flex-1"
                      :model-value="sessionPreferences.work_scope_mode"
                      :options="workScopeOptions"
                      @update:model-value="handleWorkScopeModeChange"
                    />
                  </div>
                </section>

                <p v-if="hasActiveTask" class="rounded-ui-md bg-info-muted px-2 py-1.5 text-[11px] leading-4 text-info-strong">
                  当前任务：{{ formatFocusLabel(activeRun?.focus) }}，不受上述设置影响
                </p>
              </UiPopover>
            </div>
          </template>
          <template #action-prefix>
            <div
              v-if="isNewSessionDraft || activeSessionLlmLabel || selectedRunLlmConfig"
              class="relative inline-flex items-center gap-1"
            >
              <UiDropdownMenu
                :items="llmModelDropdownItems"
                side="top"
                align="end"
                content-class="w-56"
                @select="handleLlmModelSelect"
              >
                <template #trigger>
                  <UiButton
                    type="button"
                    variant="ghost"
                    size="xs"
                    class="inline-flex h-6 max-w-[150px] items-center gap-1 rounded-md border px-1.5 text-[10px] font-medium transition"
                    :disabled="modelSelectionDisabled"
                    :title="llmModelButtonTitle"
                  >
                    <Globe2 v-if="currentLlmScope === 'global'" class="h-3 w-3 shrink-0" />
                    <UserRound v-else class="h-3 w-3 shrink-0" />
                    <span class="min-w-0 truncate">{{ currentLlmCompactName }}</span>
                    <ChevronDown v-if="!modelSelectionDisabled" class="h-3 w-3 shrink-0 opacity-60" />
                  </UiButton>
                </template>
              </UiDropdownMenu>
              <UiDropdownMenu
                :items="runReasoningDropdownItems"
                side="top"
                align="end"
                content-class="w-40"
                @select="handleRunReasoningSelect"
              >
                <template #trigger>
                  <UiButton
                    type="button"
                    variant="ghost"
                    size="xs"
                    class="inline-flex h-6 max-w-[120px] items-center gap-1 rounded-md border px-1.5 text-[10px] font-medium transition"
                    :disabled="modelSelectionDisabled"
                    :title="reasoningButtonTitle"
                  >
                    <span class="min-w-0 truncate">推理：{{ reasoningPolicyLabel }}</span>
                    <ChevronDown class="h-3 w-3 shrink-0 opacity-60" />
                  </UiButton>
                </template>
              </UiDropdownMenu>
            </div>
          </template>
        </AgentComposer>
      </template>
    </div>
  </section>

  <AgentConversationDialogs
    v-model:tool-detail-visible="toolDetailDialogVisible"
    :active-tool-detail="activeToolDetail"
    @open-tool-detail="openToolDetail"
  />
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useMutation, useQueryClient } from '@tanstack/vue-query'
import { useRoute, useRouter } from 'vue-router'
import { Building2, ChevronDown, ExternalLink, Eye, FolderKanban, Globe2, Route, UserRound, WandSparkles } from '@lucide/vue'

import { createAgentSession, getAgentSessionContextStatus } from '@/api/ai'
import {
  buildTimelineDisplayItems,
  extractTimelineToolDetails,
  type ToolCallDetail,
} from '@/components/agent/agent-conversation-panel'
import type { AgentMutationRefreshEvent } from '@/components/agent/agent-mutation-refresh'
import { useAgentHitlActions } from '@/components/agent/agent-hitl-actions'
import { useAgentImageAttachments } from '@/components/agent/agent-image-attachments'
import { AGENT_IMAGE_ATTACHMENT_MAX_COUNT } from '@/components/agent/agent-image-attachment-constants'
import { useAgentSessionNavigation } from '@/components/agent/agent-session-navigation'
import { useAgentSessionPreferences } from '@/components/agent/useAgentSessionPreferences'
import { useAgentModelSelection } from '@/components/agent/useAgentModelSelection'
import { useAgentSessionContext } from '@/components/agent/useAgentSessionContext'
import { useAgentRunLifecycle } from '@/components/agent/useAgentRunLifecycle'
import {
  buildSessionRouteLocation,
  isRouteScopeInsideSessionScope,
  resolveSessionDisplayName,
} from '@/components/agent/agent-session-scope'
import AgentComposer from '@/components/agent/AgentComposer.vue'
import AgentConversationBody from '@/components/agent/AgentConversationBody.vue'
import AgentConversationDialogs from '@/components/agent/AgentConversationDialogs.vue'
import AgentIdleHeaderBrand from '@/components/agent/AgentIdleHeaderBrand.vue'
import AgentScopeStatus from '@/components/agent/AgentScopeStatus.vue'
import AgentSessionControls from '@/components/agent/AgentSessionControls.vue'
import { UiButton, UiCheckbox, UiDropdownMenu, UiInput, UiPopover, UiSegmentedControl } from '@/components/ui'
import type {
  AgentContextStatusItem,
  AgentDescriptor,
  AgentImageAttachmentItem,
  AgentPendingRequirement,
  AgentScopeContext,
  AgentSuggestedPatch,
  AgentTimelineItem,
} from '@/types/api'
import { useAgentSessionStore } from '@/stores/agent-session'
import { logClientWarning } from '@/utils/client-logger'
import { parseApiDate } from '@/utils/timezone'
import { Message } from '@/utils/message'
import { buildGlobalPageLocation } from '@/utils/global-page-navigation'

const FORCE_CANCEL_AVAILABLE_DELAY_MS = 10_000

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
  'theme-updated': [event: AgentMutationRefreshEvent]
  'style-updated': [event: AgentMutationRefreshEvent]
}>()

const queryClient = useQueryClient()
const agentSessionStore = useAgentSessionStore()
const router = useRouter()
const route = useRoute()

const composerText = ref('')
const activeSessionId = ref('')
const lastHandledAutoCreateKey = ref<string | number | null>(null)
const virtualNewSessionKey = ref<string | number | null>(null)
const virtualNewSessionSequence = ref(0)
const draftPatches = ref<AgentSuggestedPatch[]>([])
const headerScopeReady = ref(false)
const headerActionsReady = ref(false)
const sessionMenuVisible = ref(false)
const nextRunMenuVisible = ref(false)
const toolDetailDialogVisible = ref(false)
const activeToolDetailId = ref<string | null>(null)
const draftSendInFlight = ref(false)

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
const composerPlaceholderText = computed(() => (
  props.composerPlaceholder
  || '描述目标；内容助手可以管理当前工作空间内的项目、页面、组件、资源、主题和样式。'
))
const activeSessionState = computed(() => agentSessionStore.getSession(activeSessionId.value))
const activeRuntime = computed(() => activeSessionState.value?.runtime ?? null)
const activeRun = computed(() => activeRuntime.value?.activeRun ?? null)
const isSendInFlight = computed(() => isSessionSendInFlight(activeSessionId.value))
const timelineItems = computed<AgentTimelineItem[]>({
  get: () => activeRuntime.value?.timelineItems ?? [],
  set: value => agentSessionStore.setTimelineItems(activeSessionId.value, value),
})
const pendingRequirement = computed<AgentPendingRequirement | null>({
  get: () => activeRun.value?.status === 'paused' ? activeRun.value.pending_requirement : null,
  set: value => agentSessionStore.setPendingRequirement(activeSessionId.value, value),
})
const hitlActionInFlight = computed(() => activeSessionState.value?.ui.hitlActionInFlight ?? false)
const streamingTimelineItemId = computed<string | null>({
  get: () => activeRuntime.value?.stream.streamingTimelineItemId ?? null,
  set: value => agentSessionStore.setStreamingTimelineItemId(activeSessionId.value, value),
})
const lastRunIssue = computed<{ title: string, detail: string } | null>({
  get: () => activeRuntime.value?.lastIssue ?? null,
  set: value => agentSessionStore.setLastIssue(activeSessionId.value, value),
})
const contextStatus = computed<AgentContextStatusItem | null>({
  get: () => (activeRuntime.value?.contextStatus ?? null) as AgentContextStatusItem | null,
  set: value => agentSessionStore.setContextStatus(activeSessionId.value, value),
})
const pendingImageAttachments = computed<AgentImageAttachmentItem[]>({
  get: () => activeRuntime.value?.pendingImageAttachments ?? [],
  set: value => agentSessionStore.setPendingImageAttachments(activeSessionId.value, value),
})
const imageUploading = computed(() => activeSessionState.value?.ui.imageUploading ?? false)
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
  return forceCancelTick.value - parseApiDate(run.cancel_requested_at).getTime() >= FORCE_CANCEL_AVAILABLE_DELAY_MS
})
const hitlForceReleaseAvailable = computed(() => activeRun.value?.status === 'paused' && pendingRequirement.value !== null)

const {
  manuallySelectedSessionId,
  agentsQuery,
  sessionsQuery,
  workspaceProjects,
  activeSession,
  displayedSessions,
  activeSessionScope,
  activeSessionRuntimeScope,
  activeSessionRuntimeAgentId,
  runtimeQuery,
  getSession,
  rememberSessions,
  resolveSessionRuntimeRequest,
} = useAgentSessionContext({
  scope,
  agentId,
  activeSessionId,
  virtualNewSessionKey,
})

const {
  focusProjectSearch,
  workScopeProjectSearch,
  focusModeOptions,
  workScopeOptions,
  filteredFocusProjects,
  filteredWorkScopeProjects,
  sessionPreferences,
  nextRunFocus,
  workScopeCompactLabel,
  workScopeBadgeClass,
  resetDraftPreferences,
  handleFocusModeChange,
  handlePinnedProjectChange,
  handleWorkScopeModeChange,
  toggleAllowedProject,
  isPinnedProject,
  selectAllWorkspaceProjects,
  clearSelectedProjects,
} = useAgentSessionPreferences({
  activeSessionId,
  activeSession,
  scope,
  currentRouteScope,
  workspaceProjects,
  getSession,
  rememberSession: session => rememberSessions([session]),
  invalidateSessions: async () => {
    await queryClient.invalidateQueries({ queryKey: ['ai-sessions'] })
  },
})
const hasActiveTask = computed(() => Boolean(
  activeRun.value && !['completed', 'cancelled', 'failed'].includes(activeRun.value.status),
))
const currentFocus = computed(() => activeRun.value?.focus ?? nextRunFocus.value)
const currentFocusTypeLabel = computed(() => formatFocusType(currentFocus.value))
const currentFocusLabel = computed(() => formatFocusName(currentFocus.value))
const currentFocusTooltip = computed(() => (
  `当前任务焦点：${currentFocusTypeLabel.value}“${currentFocusLabel.value}”。路由或偏好变化不会影响正在执行的任务。`
))
const nextFocusCompactLabel = computed(() => {
  if (sessionPreferences.value.focus_mode === 'workspace') return '当前空间'
  return `${formatFocusType(nextRunFocus.value)} · ${formatFocusName(nextRunFocus.value)}`
})
const nextFocusIcon = computed(() => {
  if (sessionPreferences.value.focus_mode === 'follow_route') return Route
  if (sessionPreferences.value.focus_mode === 'workspace') return Building2
  return FolderKanban
})
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
    workspace_id: scope.value.workspace_id,
    focus_mode: sessionPreferences.value.focus_mode,
    pinned_project_id: sessionPreferences.value.pinned_project_id,
    work_scope_mode: sessionPreferences.value.work_scope_mode,
    allowed_project_ids: [...sessionPreferences.value.allowed_project_ids],
    session_name: sessionName ?? selectedAgent.value?.default_session_name ?? `${contextTitle.value} 对话`,
    llm_config_id: selectedRunLlmConfigId.value,
  }),
})

const selectedAgent = computed<AgentDescriptor | null>(() => agentsQuery.data.value?.[0] ?? null)
const {
  llmConfigsQuery,
  selectedRunLlmConfigId,
  selectedRunReasoning,
  isNewSessionDraft,
  llmModelDropdownItems,
  selectableModelCount,
  modelSelectionDisabled,
  selectedRunLlmConfig,
  activeSessionLlmLabel,
  currentLlmModelLabel,
  currentLlmScope,
  currentLlmCompactName,
  llmModelButtonTitle,
  runReasoningDropdownItems,
  reasoningPolicyLabel,
  reasoningButtonTitle,
  showVisualCapabilityStatus,
  imageAnalysisAvailable,
  imageGenerationAvailable,
  visualAttachmentCapabilityAvailable,
  visualCapabilityConfigurationRequired,
  imageAnalysisCapabilityTitle,
  imageGenerationCapabilityTitle,
  handleLlmModelSelect,
  handleRunReasoningSelect,
} = useAgentModelSelection({
  activeSessionId,
  activeSession,
  activeRun,
  selectedAgent,
  agentId,
})
const hasContextIssue = computed(() => (
  selectedAgent.value !== null
  && selectedAgent.value.available === false
  && props.routeAvailable
))
const isModelSelectionPending = computed(() => isNewSessionDraft.value && llmConfigsQuery.isFetching.value)
const hasModelSelectionIssue = computed(() => (
  !llmConfigsQuery.isFetching.value
  && selectableModelCount.value === 0
))
const hasBindingIssue = computed(() => (
  hasContextIssue.value || hasModelSelectionIssue.value
))
const agentIssueTitle = computed(() => (
  hasContextIssue.value ? `${agentDisplayName.value}当前不可用` : '没有可用模型'
))
const agentIssueDetail = computed(() => (
  hasContextIssue.value
    ? selectedAgent.value?.unavailable_reason || '当前路由上下文缺少智能体所需信息。'
    : '当前没有可用于发起会话的模型。请到“AI 设置”创建个人模型，或联系管理员提供全局模型。'
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
  if (!visualAttachmentCapabilityAvailable.value) {
    return '请前往 AI 设置配置图片理解或图片生成模型'
  }
  if (composerContextIssue.value) {
    return composerContextIssue.value
  }
  return ''
})
const imageUploadDisabled = computed(() => Boolean(imageUploadDisabledReason.value))
const resolvedToolCallDetails = computed(() => extractTimelineToolDetails(timelineItems.value))
const activeToolDetail = computed<ToolCallDetail | null>(() => (
  resolvedToolCallDetails.value.find(item => item.id === activeToolDetailId.value) ?? null
))
const panelShellClass = computed(() => (
  props.embedded
    ? 'flex h-full min-h-0 flex-col bg-transparent'
    : 'flex min-h-[720px] flex-col overflow-hidden rounded-3xl border border-border bg-surface/95 shadow-sm backdrop-blur'
))
const timelineDisplayItems = computed(() => buildTimelineDisplayItems(timelineItems.value, {
  pendingRequirement: pendingRequirement.value,
  workspaceId: props.workspaceId,
  activeRunId: activeRun.value?.run_id ?? null,
}))
const {
  isStreaming,
  isInterrupting,
  forceCancelTick,
  setSessionStreaming,
  syncActiveRun,
  restartRunEventSubscription,
  handleSend,
  handleInterruptRun,
  handleForceCancelRun,
  finalizeRun,
  getSessionRunBadge,
} = useAgentRunLifecycle({
  activeSessionId,
  activeRun,
  activeSession,
  agentId,
  agentDisplayName,
  selectedAgent,
  contextTitle,
  nextRunFocus,
  sessionPreferences,
  composerText,
  pendingImageAttachments,
  pendingRequirement,
  lastRunIssue,
  hasBindingIssue,
  agentIssueDetail,
  composerContextIssue,
  visualAttachmentCapabilityAvailable,
  selectedRunLlmConfigId,
  selectedRunReasoning,
  agentSessionStore,
  queryClient,
  runtimeSnapshot: runtimeQuery.data,
  refetchSessions: async () => (await sessionsQuery.refetch()).data ?? [],
  refetchActiveRuntime: async () => (await runtimeQuery.refetch()).data ?? null,
  rememberSessions,
  resolveSessionRuntimeRequest,
  ensureActiveSession,
  isSessionSendInFlight,
  setSessionSendInFlight,
  emitRefreshEvent: event => {
    if (event.kind === 'page') emit('page-updated', event)
    else if (event.kind === 'project-pages') emit('project-pages-updated', event)
    else if (event.kind === 'project') emit('project-updated', event)
    else if (event.kind === 'component') emit('component-updated', event)
    else if (event.kind === 'asset') emit('asset-updated', event)
    else if (event.kind === 'theme') emit('theme-updated', event)
    else if (event.kind === 'style') emit('style-updated', event)
  },
})
const composerActionDisabled = computed(() => (
  isStreaming.value
    ? isInterrupting.value
    : isSendInFlight.value || imageUploading.value || pendingImageAttachments.value.length > AGENT_IMAGE_ATTACHMENT_MAX_COUNT || pendingRequirement.value !== null || (!composerText.value.trim() && pendingImageAttachments.value.length === 0) || hasBindingIssue.value || isModelSelectionPending.value || composerInputDisabled.value
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
 * 读取指定会话的发送中状态；新会话草稿使用固定分片，避免创建会话前重复点击。
 */
function isSessionSendInFlight(sessionId: string) {
  return sessionId ? agentSessionStore.getSession(sessionId)?.ui.sendInFlight ?? false : draftSendInFlight.value
}

/**
 * 写入指定会话的发送中状态；完成后移除分片，避免长期积累无效会话键。
 */
function setSessionSendInFlight(sessionId: string, inFlight: boolean) {
  if (!sessionId) {
    draftSendInFlight.value = inFlight
  } else {
    agentSessionStore.setSendInFlight(sessionId, inFlight)
  }
}

/**
 * 设置当前会话 HITL 操作请求状态，避免与 run streaming 状态相互污染。
 */
function setHitlActionInFlight(sessionId: string, value: boolean) {
  agentSessionStore.setHitlActionInFlight(sessionId, value)
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
  setHitlActionInFlight,
  setSessionStreaming,
  syncActiveRun,
  setPendingRequirementForSession: (sessionId, requirement) => {
    agentSessionStore.setPendingRequirement(sessionId, requirement)
  },
  markPendingRequirementResolved: (sessionId, requirement, feedbackSelections) => {
    const previousItems = [...(agentSessionStore.getSession(sessionId)?.runtime.timelineItems ?? [])]
    agentSessionStore.markPendingRequirementResolved(sessionId, requirement, feedbackSelections)
    return () => {
      agentSessionStore.setTimelineItems(sessionId, previousItems)
    }
  },
  restartRunEventSubscription,
  finalizeRun,
})

const {
  handlePromoteImage,
  handleRemoveImage,
  handleUploadImages,
} = useAgentImageAttachments({
  getActiveSessionId: () => activeSessionId.value,
  getScope: () => scope.value,
  getAgentId: () => agentId.value,
  getImageUploadDisabledReason: () => imageUploadDisabledReason.value,
  ensureActiveSession,
  getPendingImageAttachments: sessionId => agentSessionStore.getSession(sessionId)?.runtime.pendingImageAttachments ?? [],
  setPendingImageAttachments: (sessionId, attachments) => {
    agentSessionStore.setPendingImageAttachments(sessionId, attachments)
  },
  setImageUploading: (sessionId, uploading) => {
    agentSessionStore.setImageUploading(sessionId, uploading)
  },
  invalidateWorkspaceAssets: async () => {
    await queryClient.invalidateQueries({ queryKey: ['workspace-assets'] })
  },
  refreshSessionRuntime: async sessionId => {
    await finalizeRun(sessionId)
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

watch(virtualNewSessionKey, (virtualKey, previousKey) => {
  if (virtualKey && virtualKey !== previousKey) {
    resetDraftPreferences()
  }
})

watch(activeSessionId, () => {
  sessionMenuVisible.value = false
  toolDetailDialogVisible.value = false
  activeToolDetailId.value = null
})

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

/** 返回焦点对象的层级类型，统一使用空间、项目、页面等短名称。 */
function formatFocusType(focus?: AgentScopeContext | null) {
  if (focus?.page_id) return '页面'
  if (focus?.project_id) return '项目'
  if (focus?.component_id) return '组件'
  return '空间'
}

/** 返回焦点对象名称；缺少名称时保留明确 ID 便于诊断。 */
function formatFocusName(focus?: AgentScopeContext | null) {
  if (!focus) return `#${scope.value.workspace_id}`
  if (focus.page_id) return focus.page_title?.trim() || `#${focus.page_id}`
  if (focus.project_id) return focus.project_name?.trim() || `#${focus.project_id}`
  if (focus.component_id) return focus.component_name?.trim() || `#${focus.component_id}`
  return focus.workspace_name?.trim() || `#${focus.workspace_id}`
}

/** 把焦点类型、名称组合为完整标签。 */
function formatFocusLabel(focus?: AgentScopeContext | null) {
  return `${formatFocusType(focus)} · ${formatFocusName(focus)}`
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
  if (!selectedRunLlmConfigId.value) {
    throw new Error('请选择用于本次会话的模型。')
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
  if (isSendInFlight.value) {
    return
  }
  void handleSend()
}

/**
 * 打开工具详情弹窗，查看当前保存的输入输出内容。
 */
function openToolDetail(toolId: string) {
  activeToolDetailId.value = toolId
  toolDetailDialogVisible.value = true
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
 * 跳转到 AI 设置页，供用户创建或维护个人模型。
 */
function goToAiSettings() {
  router.push(buildGlobalPageLocation('accountAiSettings', route.fullPath))
}
</script>
