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
          :empty-conversation-text="emptyConversationText"
          :loading="sessionLoading"
          :loading-text="sessionLoadingText"
          :last-run-issue="lastRunIssue"
          :active-run="activeRun"
          :cancelling-run-force-available="cancellingRunForceAvailable"
          :is-streaming="isStreaming"
          :streaming-timeline-item-id="streamingTimelineItemId"
          :promote-attachment="handlePromoteImage"
          @apply-suggested-patch="applySuggestedPatch"
          @remove-draft-patch="removeDraftPatch"
          @open-tool-detail="openToolDetail"
          @open-member-run-detail="openMemberRunDetail"
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
            <span
              v-if="isNewSessionDraft || activeSessionLlmLabel || selectedRunLlmConfig"
              class="relative inline-flex"
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
            </span>
          </template>
        </AgentComposer>
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
import { Building2, ChevronDown, ExternalLink, Eye, FolderKanban, Globe2, Route, UserRound, WandSparkles } from '@lucide/vue'

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
  updateAgentSessionPreferences,
} from '@/api/ai'
import { listProjects } from '@/api/catalog'
import { listLlmConfigs, listLlmSlots } from '@/api/llm'
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
import { AGENT_IMAGE_ATTACHMENT_MAX_COUNT } from '@/components/agent/agent-image-attachment-constants'
import { useAgentStreamControllers } from '@/components/agent/agent-stream-controllers'
import { useAgentForceCancelTicker } from '@/components/agent/agent-force-cancel-ticker'
import { useAgentSessionNavigation } from '@/components/agent/agent-session-navigation'
import {
  buildSessionRouteLocation,
  findLatestSessionForScope,
  getSelectedSession,
  getSelectedWorkspaceSession,
  isRouteScopeInsideSessionScope,
  isSessionTargetCurrentScope,
  resolveSessionDisplayName,
  resolveSessionScope,
  setSelectedSession,
  setSelectedWorkspaceSession,
} from '@/components/agent/agent-session-scope'
import { normalizeAgentRunEvent } from '@/components/agent/agent-run-state'
import AgentComposer from '@/components/agent/AgentComposer.vue'
import AgentConversationBody from '@/components/agent/AgentConversationBody.vue'
import AgentConversationDialogs from '@/components/agent/AgentConversationDialogs.vue'
import AgentIdleHeaderBrand from '@/components/agent/AgentIdleHeaderBrand.vue'
import AgentScopeStatus from '@/components/agent/AgentScopeStatus.vue'
import AgentSessionControls from '@/components/agent/AgentSessionControls.vue'
import { UiButton, UiCheckbox, UiDropdownMenu, UiInput, UiPopover, UiSegmentedControl } from '@/components/ui'
import type { DropdownMenuEntry } from '@/components/ui'
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
  LlmConfigItem,
  LlmSlotBindingItem,
} from '@/types/api'
import { useAgentSessionStore } from '@/stores/agent-session'
import { logClientWarning } from '@/utils/client-logger'
import { createClientUuid } from '@/utils/id'
import { Message } from '@/utils/message'
import { buildGlobalPageLocation } from '@/utils/global-page-navigation'

const FORCE_CANCEL_AVAILABLE_DELAY_MS = 10_000

/** 等待后台保存的最新偏好变更；保存进行中的新变更在此排队，完成后自动补提。 */
let queuedPreferenceOverrides: Partial<Pick<AgentSessionItem, 'focus_mode' | 'pinned_project_id' | 'work_scope_mode' | 'allowed_project_ids'>> | null = null

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

type SessionFocusPreferences = Pick<
  AgentSessionItem,
  'focus_mode' | 'pinned_project_id' | 'work_scope_mode' | 'allowed_project_ids'
>

interface AgentSessionLlmMetadata {
  selection_kind?: 'explicit_config' | 'slot_binding'
  config_id?: number | string | null
  scope?: 'global' | 'personal' | string
  name?: string | null
  provider_config_id?: number | string | null
  provider_config_name?: string | null
  provider_key?: string | null
  provider_label?: string | null
  model_id?: string | null
  supports_image_input?: boolean | null
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
  'theme-updated': [event: AgentMutationRefreshEvent]
  'style-updated': [event: AgentMutationRefreshEvent]
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
const localPreferences = ref<SessionFocusPreferences>(createDefaultSessionPreferences())
const draftPatches = ref<AgentSuggestedPatch[]>([])
const headerScopeReady = ref(false)
const headerActionsReady = ref(false)
const sessionMenuVisible = ref(false)
const nextRunMenuVisible = ref(false)
const focusProjectSearch = ref('')
const workScopeProjectSearch = ref('')
const toolDetailDialogVisible = ref(false)
const memberRunDialogVisible = ref(false)
const activeToolDetailId = ref<string | null>(null)
const activeMemberRunIds = ref<string[]>([])
const sendInFlightBySession = ref<Record<string, boolean>>({})
const selectedRunLlmConfigId = ref<number | null>(null)
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
  || '描述目标；内容助手可以管理当前工作空间内的项目、页面、组件、资源、主题和样式。'
))
const activeRun = computed(() => readSessionValue(activeRunBySession.value, activeSessionId.value, null))
const isStreaming = computed(() => isSessionRunning(activeSessionId.value))
const isInterrupting = computed(() => readSessionValue(interruptingBySession.value, activeSessionId.value, false))
const isSendInFlight = computed(() => isSessionSendInFlight(activeSessionId.value))
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
  return forceCancelTick.value - new Date(run.cancel_requested_at).getTime() >= FORCE_CANCEL_AVAILABLE_DELAY_MS
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
    queryFn: () => listAgentSessions(scope.value, agentId.value),
    enabled: !!scope.value.workspace_id,
  })),
)

const projectsQuery = useQuery(
  computed(() => ({
    queryKey: ['projects', 'agent-focus', scope.value.workspace_id],
    queryFn: () => listProjects({ workspace_id: scope.value.workspace_id, page: 1, page_size: 100 }),
    enabled: !!scope.value.workspace_id,
  })),
)
const workspaceProjects = computed(() => projectsQuery.data.value?.items ?? [])
const focusModeOptions = [
  { label: '跟随当前路由', value: 'follow_route' },
  { label: '固定项目', value: 'pinned_project' },
  { label: '工作空间级', value: 'workspace' },
]
const workScopeOptions = [
  { label: '全部项目', value: 'workspace' },
  { label: '仅选择的项目', value: 'selected_projects' },
]
const filteredFocusProjects = computed(() => filterProjectsByKeyword(workspaceProjects.value, focusProjectSearch.value))
const filteredWorkScopeProjects = computed(() => filterProjectsByKeyword(workspaceProjects.value, workScopeProjectSearch.value))

const llmConfigsQuery = useQuery({
  queryKey: ['llm-configs', 'agent-conversation'],
  queryFn: listLlmConfigs,
})

const llmSlotsQuery = useQuery({
  queryKey: ['llm-slots', 'agent-conversation'],
  queryFn: listLlmSlots,
})

const normalizedSessions = computed(() => sessionsQuery.data.value?.map(normalizeSessionItem))
const activeSession = computed<AgentSessionItem | null>(() => {
  const item = normalizedSessions.value?.find(candidate => candidate.session_id === activeSessionId.value)
    ?? knownSessionsById.value[activeSessionId.value]
    ?? null
  return item ? normalizeSessionItem(item) : null
})
const sessionPreferences = computed<SessionFocusPreferences>(() => localPreferences.value)
/**
 * 会话切换或服务端返回更新时同步本地偏好；保存排队期间保留用户最新操作。
 */
watch(() => activeSession.value, (session) => {
  if (!session || queuedPreferenceOverrides) {
    return
  }
  localPreferences.value = extractSessionPreferences(session)
}, { immediate: true })
const displayedSessions = computed<AgentSessionItem[] | undefined>(() => {
  const sessions = normalizedSessions.value
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
const nextRunFocus = computed<AgentScopeContext>(() => {
  const preferences = sessionPreferences.value
  if (preferences.focus_mode === 'follow_route') {
    return currentRouteScope.value
  }
  if (preferences.focus_mode === 'pinned_project' && preferences.pinned_project_id) {
    const project = workspaceProjects.value.find(item => item.id === preferences.pinned_project_id)
    return {
      scope_type: 'project',
      workspace_id: scope.value.workspace_id,
      project_id: preferences.pinned_project_id,
      project_name: project?.name ?? null,
      source: 'session-pinned-project',
    }
  }
  return {
    scope_type: 'workspace',
    workspace_id: scope.value.workspace_id,
    workspace_name: currentRouteScope.value.workspace_name ?? scope.value.workspace_name ?? null,
    source: 'session-workspace',
  }
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
const pinnedProjectId = computed(() => (
  sessionPreferences.value.focus_mode === 'pinned_project' ? sessionPreferences.value.pinned_project_id : null
))
const workScopeCompactLabel = computed(() => {
  const preferences = sessionPreferences.value
  if (preferences.work_scope_mode === 'workspace') return '全部项目'
  return preferences.allowed_project_ids.length ? `已选 ${preferences.allowed_project_ids.length} 项` : '未选择项目'
})
const workScopeBadgeClass = computed(() => {
  const preferences = sessionPreferences.value
  if (preferences.work_scope_mode === 'workspace') {
    return 'bg-surface-muted text-text-muted'
  }
  return preferences.allowed_project_ids.length
    ? 'bg-info-muted text-info-strong'
    : 'bg-warning-muted text-warning-strong'
})
const isNewSessionDraft = computed(() => !activeSessionId.value)
const activeLlmConfigs = computed<LlmConfigItem[]>(() => (
  (llmConfigsQuery.data.value ?? []).filter(item => (
    item.status === 'active'
    && (item.model_type ?? 'chat') === 'chat'
    && (item.scope === 'global' || item.scope === 'personal')
  ))
))
const activeGlobalLlmConfigs = computed(() => activeLlmConfigs.value.filter(item => item.scope === 'global'))
const activePersonalLlmConfigs = computed(() => activeLlmConfigs.value.filter(item => item.scope === 'personal'))
const llmConfigById = computed(() => new Map(activeLlmConfigs.value.map(item => [item.id, item])))
/**
 * 模型菜单下拉项，带图标、描述和选中指示。
 */
const llmModelDropdownItems = computed<DropdownMenuEntry[]>(() =>
  activeLlmConfigs.value.map(item => ({
    label: item.name,
    value: String(item.id),
    description: `${item.provider_label} / ${item.model_id}`,
    icon: item.scope === 'global' ? Globe2 : UserRound,
    active: item.id === selectedRunLlmConfigId.value,
  })),
)
const selectableModelCount = computed(() => activeLlmConfigs.value.length)
const modelSelectionDisabled = computed(() => (
  llmConfigsQuery.isFetching.value
  || selectableModelCount.value === 0
  || Boolean(activeRun.value && !['completed', 'cancelled', 'failed'].includes(activeRun.value.status))
))
const boundDraftLlmConfigId = computed(() => {
  const slot = selectedAgent.value?.llm_slot
  if (!slot) {
    return null
  }
  const binding = (llmSlotsQuery.data.value ?? []).find((item: LlmSlotBindingItem) => item.slot === slot)
  const configId = binding?.binding_ready ? binding.llm_config_id : null
  return configId && llmConfigById.value.has(configId) ? configId : null
})
const defaultNewSessionLlmConfigId = computed(() => (
  boundDraftLlmConfigId.value
  ?? activeGlobalLlmConfigs.value[0]?.id
  ?? activePersonalLlmConfigs.value[0]?.id
  ?? null
))
const selectedRunLlmConfig = computed(() => (
  selectedRunLlmConfigId.value ? llmConfigById.value.get(selectedRunLlmConfigId.value) ?? null : null
))
const activeSessionLlmMetadata = computed(() => extractSessionLlmMetadata(activeSession.value))
const activeSessionLlmConfigId = computed(() => normalizeLlmConfigId(activeSessionLlmMetadata.value?.config_id))
const activeSessionLlmConfig = computed(() => (
  activeSessionLlmConfigId.value ? llmConfigById.value.get(activeSessionLlmConfigId.value) ?? null : null
))
const activeSessionLlmLabel = computed(() => {
  if (!activeSession.value) {
    return ''
  }
  if (activeSessionLlmConfig.value) {
    return formatLlmConfigLabel(activeSessionLlmConfig.value)
  }
  if (activeSessionLlmMetadata.value) {
    return formatLlmMetadataLabel(activeSessionLlmMetadata.value)
  }
  return selectedAgent.value?.bound_llm_name || ''
})
const currentLlmModelLabel = computed(() => (
  selectedRunLlmConfig.value
    ? formatLlmConfigLabel(selectedRunLlmConfig.value)
    : activeSessionLlmLabel.value
))
const currentLlmScope = computed(() => {
  return selectedRunLlmConfig.value?.scope ?? activeSessionLlmConfig.value?.scope ?? activeSessionLlmMetadata.value?.scope ?? 'personal'
})
const currentLlmCompactName = computed(() => {
  return selectedRunLlmConfig.value?.name ?? activeSessionLlmConfig.value?.name ?? activeSessionLlmMetadata.value?.name ?? '选择模型'
})
const llmModelButtonTitle = computed(() => {
  const label = currentLlmModelLabel.value || currentLlmCompactName.value
  return activeSessionId.value ? `下次运行模型：${label}` : `新会话模型：${label}`
})
const showVisualCapabilityStatus = computed(() => (
  agentId.value === 'agent-coordinator'
  && selectedAgent.value !== null
))
const imageAnalysisAvailable = computed(() => Boolean(selectedAgent.value?.image_analysis_available))
const imageGenerationAvailable = computed(() => Boolean(selectedAgent.value?.image_generation_available))
const visualAttachmentCapabilityAvailable = computed(() => (
  imageAnalysisAvailable.value || imageGenerationAvailable.value
))
const visualCapabilityConfigurationRequired = computed(() => (
  !imageAnalysisAvailable.value || !imageGenerationAvailable.value
))
const imageAnalysisCapabilityTitle = computed(() => (
  imageAnalysisAvailable.value
    ? 'analyze_visuals 已配置，可按需分析附件、工作空间图片资源或页面截图'
    : selectedAgent.value?.image_analysis_unavailable_reason || 'analyze_visuals 未配置图片理解模型'
))
const imageGenerationCapabilityTitle = computed(() => (
  imageGenerationAvailable.value
    ? 'generate_image 已配置，可生成或编辑图片并保存到资源库'
    : selectedAgent.value?.image_generation_unavailable_reason || 'generate_image 未配置图片生成模型'
))

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
    workspace_id: scope.value.workspace_id,
    focus_mode: sessionPreferences.value.focus_mode,
    pinned_project_id: sessionPreferences.value.pinned_project_id,
    work_scope_mode: sessionPreferences.value.work_scope_mode,
    allowed_project_ids: [...sessionPreferences.value.allowed_project_ids],
    session_name: sessionName ?? selectedAgent.value?.default_session_name ?? `${contextTitle.value} 对话`,
    llm_config_id: selectedRunLlmConfigId.value,
  }),
})

const focusPreferenceMutation = useMutation({
  mutationFn: (payload: {
    focus_mode: AgentSessionItem['focus_mode']
    pinned_project_id: number | null
    work_scope_mode: AgentSessionItem['work_scope_mode']
    allowed_project_ids: number[]
  }) => updateAgentSessionPreferences(
    activeSessionId.value,
    scope.value.workspace_id,
    payload,
    activeSession.value?.agent_id ?? agentId.value,
  ),
  onSuccess: async (updated) => {
    rememberSessions([updated])
    await queryClient.invalidateQueries({ queryKey: ['ai-sessions'] })
  },
  onError: error => Message.error(getErrorMessage(error, '保存会话焦点失败。')),
})

const selectedAgent = computed<AgentDescriptor | null>(() => agentsQuery.data.value?.[0] ?? null)
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
    : 'flex min-h-[720px] flex-col overflow-hidden rounded-3xl border border-border bg-surface/95 shadow-sm backdrop-blur'
))
const timelineDisplayItems = computed(() => buildTimelineDisplayItems(timelineItems.value, {
  pendingRequirement: pendingRequirement.value,
  memberRuns: memberRuns.value,
  workspaceId: props.workspaceId,
  activeRunId: activeRun.value?.run_id ?? null,
}))
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
 * 读取指定会话的发送中状态；新会话草稿使用固定分片，避免创建会话前重复点击。
 */
function isSessionSendInFlight(sessionId: string) {
  return readSessionValue(sendInFlightBySession.value, sessionId || 'draft', false)
}

/**
 * 写入指定会话的发送中状态；完成后移除分片，避免长期积累无效会话键。
 */
function setSessionSendInFlight(sessionId: string, inFlight: boolean) {
  const key = sessionId || 'draft'
  if (inFlight) {
    sendInFlightBySession.value[key] = true
    return
  }
  delete sendInFlightBySession.value[key]
}

/** 将会话响应规范为工作空间级结构；仅用于组件内部稳定处理测试夹具与并发缓存。 */
function normalizeSessionItem(session: AgentSessionItem): AgentSessionItem {
  return {
    ...session,
    workspace_id: session.workspace_id ?? scope.value.workspace_id,
    focus_mode: session.focus_mode ?? 'follow_route',
    pinned_project_id: session.pinned_project_id ?? null,
    work_scope_mode: session.work_scope_mode ?? 'workspace',
    allowed_project_ids: session.allowed_project_ids ?? [],
    focus_version: session.focus_version ?? 0,
  }
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
    ...Object.fromEntries(sessions.map(session => {
      const normalized = normalizeSessionItem(session)
      return [normalized.session_id, normalized]
    })),
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
  return Boolean(run.run_id && (run.status === 'pending' || run.status === 'running' || run.status === 'waiting_external' || run.status === 'cancelling'))
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
    || runtime.active_run?.status === 'waiting_external'
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
  return run?.status === 'pending' || run?.status === 'running' || run?.status === 'waiting_external' || run?.status === 'cancelling'
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
  handleUploadImages,
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
    localPreferences.value = createDefaultSessionPreferences()
  }
})

watch(
  () => [normalizedSessions.value, agentId.value] as const,
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

watch(
  () => [defaultNewSessionLlmConfigId.value, selectedRunLlmConfigId.value, activeSessionId.value] as const,
  () => {
    if (!isNewSessionDraft.value) {
      return
    }
    const selectedId = selectedRunLlmConfigId.value
    if (selectedId !== null && llmConfigById.value.has(selectedId)) {
      return
    }
    selectedRunLlmConfigId.value = defaultNewSessionLlmConfigId.value
  },
  { immediate: true },
)

watch(activeSessionId, () => {
  const sessionModelId = normalizeLlmConfigId(extractSessionLlmMetadata(activeSession.value)?.config_id)
  selectedRunLlmConfigId.value = sessionModelId && llmConfigById.value.has(sessionModelId)
    ? sessionModelId
    : defaultNewSessionLlmConfigId.value
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

watch(activeSessionLlmConfigId, (configId) => {
  if (!activeSessionId.value || !configId || !llmConfigById.value.has(configId)) {
    return
  }
  selectedRunLlmConfigId.value = configId
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
 * 选择下一次 run 使用的模型；Backend 会同时保存 run 快照和会话默认值。
 */
function handleLlmModelSelect(value: string) {
  const configId = Number(value)
  if (Number.isFinite(configId)) {
    selectedRunLlmConfigId.value = configId
  }
}

type SessionPreferenceOverrides = Partial<Pick<AgentSessionItem, 'focus_mode' | 'pinned_project_id' | 'work_scope_mode' | 'allowed_project_ids'>>

/** 从会话快照提取本地偏好状态。 */
function extractSessionPreferences(session: AgentSessionItem): SessionFocusPreferences {
  return {
    focus_mode: session.focus_mode,
    pinned_project_id: session.pinned_project_id,
    work_scope_mode: session.work_scope_mode,
    allowed_project_ids: [...session.allowed_project_ids],
  }
}

/**
 * 保存下一轮偏好：先乐观更新本地状态保证交互即时反馈，再串行排队提交到服务端。
 * 无活跃会话时只写本地草稿，创建会话时随 createAgentSession 一起提交。
 */
function saveSessionPreferences(overrides: SessionPreferenceOverrides) {
  localPreferences.value = {
    focus_mode: overrides.focus_mode ?? localPreferences.value.focus_mode,
    pinned_project_id: overrides.pinned_project_id !== undefined ? overrides.pinned_project_id : localPreferences.value.pinned_project_id,
    work_scope_mode: overrides.work_scope_mode ?? localPreferences.value.work_scope_mode,
    allowed_project_ids: overrides.allowed_project_ids ?? [...localPreferences.value.allowed_project_ids],
  }
  if (!activeSession.value) {
    return
  }
  queuedPreferenceOverrides = overrides
  if (focusPreferenceMutation.isPending.value) {
    return
  }
  void flushPreferenceSaves()
}

/**
 * 串行提交排队的偏好变更；每次提交前基于最新会话补齐未覆盖字段，
 * 失败时回滚本地状态并停止后续提交，避免连续失败。
 */
async function flushPreferenceSaves() {
  while (queuedPreferenceOverrides) {
    const overrides = queuedPreferenceOverrides
    queuedPreferenceOverrides = null
    const session = activeSession.value
    if (!session) {
      return
    }
    try {
      await focusPreferenceMutation.mutateAsync({
        focus_mode: overrides.focus_mode ?? session.focus_mode,
        pinned_project_id: overrides.pinned_project_id !== undefined ? overrides.pinned_project_id : session.pinned_project_id,
        work_scope_mode: overrides.work_scope_mode ?? session.work_scope_mode,
        allowed_project_ids: overrides.allowed_project_ids ?? [...session.allowed_project_ids],
      })
    } catch {
      queuedPreferenceOverrides = null
      const currentSession = activeSession.value
      if (currentSession) {
        localPreferences.value = extractSessionPreferences(currentSession)
      }
    }
  }
}

/** 切换三种焦点模式；固定项目优先采用当前路由项目或列表首项。 */
function handleFocusModeChange(value: string | number | Array<string | number> | null) {
  const focusMode = String(value) as AgentSessionItem['focus_mode']
  const nextPinnedProjectId = focusMode === 'pinned_project'
    ? (sessionPreferences.value.pinned_project_id ?? currentRouteScope.value.project_id ?? workspaceProjects.value[0]?.id ?? null)
    : null
  if (focusMode === 'pinned_project' && !nextPinnedProjectId) {
    Message.warning('当前工作空间没有可固定的项目。')
    return
  }
  const allowedProjectIds = focusMode === 'pinned_project'
    && sessionPreferences.value.work_scope_mode === 'selected_projects'
    && nextPinnedProjectId
    ? [...new Set([...sessionPreferences.value.allowed_project_ids, nextPinnedProjectId])]
    : undefined
  saveSessionPreferences({ focus_mode: focusMode, pinned_project_id: nextPinnedProjectId, allowed_project_ids: allowedProjectIds })
}

/** 修改固定项目，只影响后续 Run；固定项目始终并入显式工作集。 */
function handlePinnedProjectChange(projectId: number) {
  if (!Number.isFinite(projectId) || projectId <= 0) {
    return
  }
  const allowedProjectIds = sessionPreferences.value.work_scope_mode === 'selected_projects'
    ? [...new Set([...sessionPreferences.value.allowed_project_ids, projectId])]
    : undefined
  saveSessionPreferences({ focus_mode: 'pinned_project', pinned_project_id: projectId, allowed_project_ids: allowedProjectIds })
}

/** 放开会话到工作空间全部项目。 */
function setWorkspaceWorkScope() {
  saveSessionPreferences({ work_scope_mode: 'workspace', allowed_project_ids: [] })
}

/** 启用显式项目工作集；空列表明确表示暂不允许项目操作，固定项目始终保留。 */
function setSelectedProjectsWorkScope() {
  saveSessionPreferences({
    work_scope_mode: 'selected_projects',
    allowed_project_ids: pinnedProjectId.value ? [pinnedProjectId.value] : [],
  })
}

/** 根据单选结果切换项目工作集模式。 */
function handleWorkScopeModeChange(value: string) {
  if (value === 'workspace') {
    setWorkspaceWorkScope()
    return
  }
  setSelectedProjectsWorkScope()
}

/** 增删工作集项目并立即保存；固定项目不允许移出工作集。 */
function toggleAllowedProject(projectId: number) {
  if (isPinnedProject(projectId)) {
    return
  }
  const selected = new Set(sessionPreferences.value.allowed_project_ids)
  if (selected.has(projectId)) {
    selected.delete(projectId)
  } else {
    selected.add(projectId)
  }
  saveSessionPreferences({ work_scope_mode: 'selected_projects', allowed_project_ids: [...selected] })
}

/** 判断项目是否同时作为固定焦点存在，固定项目不可从工作集移除。 */
function isPinnedProject(projectId: number) {
  return pinnedProjectId.value === projectId
}

/** 全选当前过滤结果中的项目，固定项目始终保留。 */
function selectAllWorkspaceProjects() {
  const ids = new Set(filteredWorkScopeProjects.value.map(project => project.id))
  if (pinnedProjectId.value) {
    ids.add(pinnedProjectId.value)
  }
  saveSessionPreferences({ work_scope_mode: 'selected_projects', allowed_project_ids: [...ids] })
}

/** 清空工作集；固定项目作为唯一保留项继续留在集合中。 */
function clearSelectedProjects() {
  saveSessionPreferences({
    work_scope_mode: 'selected_projects',
    allowed_project_ids: pinnedProjectId.value ? [pinnedProjectId.value] : [],
  })
}

/** 按名称关键字过滤项目列表，忽略大小写；空关键字返回完整列表。 */
function filterProjectsByKeyword(projects: Array<{ id: number; name: string }>, keyword: string) {
  const query = keyword.trim().toLowerCase()
  if (!query) {
    return projects
  }
  return projects.filter(project => project.name.toLowerCase().includes(query))
}

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

/** 创建尚未落库的新会话默认偏好。 */
function createDefaultSessionPreferences(): SessionFocusPreferences {
  return {
    focus_mode: 'follow_route',
    pinned_project_id: null,
    work_scope_mode: 'workspace',
    allowed_project_ids: [],
  }
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
  const draftSessionId = activeSessionId.value
  if ((!message && attachments.length === 0) || isStreaming.value || isSessionSendInFlight(draftSessionId)) return
  if (attachments.length && !visualAttachmentCapabilityAvailable.value) {
    Message.error('请先在 AI 设置中配置图片理解或图片生成模型。')
    return
  }
  const runAgentDisplayName = agentDisplayName.value

  setSessionSendInFlight(draftSessionId, true)
  let sessionId = ''
  try {
    sessionId = await ensureActiveSession()
  } catch (error) {
    setSessionSendInFlight(draftSessionId, false)
    Message.error(getErrorMessage(error, '初始化智能体会话失败。'))
    return
  }
  if (sessionId !== draftSessionId) {
    setSessionSendInFlight(draftSessionId, false)
    setSessionSendInFlight(sessionId, true)
  }
  const runtimeRequest = resolveSessionRuntimeRequest(sessionId)
  const runScope = { ...nextRunFocus.value }
  const runAgentId = runtimeRequest.agentId

  composerText.value = ''
  pendingImageAttachments.value = []
  pendingRequirement.value = null
  lastRunIssue.value = null
  writeSessionValue(mutationRefreshEventsBySession.value, sessionId, [])

  const runId = createClientUuid()
  agentSessionStore.beginLocalRun(sessionId, message, attachments, runId)
  setSessionStreaming(sessionId, true)

  try {
    agentSessionStore.setCurrentRunId(sessionId, runId)
    syncActiveRun(sessionId, {
      run_id: runId,
      session_id: sessionId,
      agent_id: runAgentId,
      status: 'running',
      focus: runScope,
      work_scope_mode: activeSession.value?.work_scope_mode ?? 'workspace',
      allowed_project_ids: [...(activeSession.value?.allowed_project_ids ?? [])],
      focus_version: activeSession.value?.focus_version ?? 0,
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
      llm_config_id: selectedRunLlmConfigId.value,
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
    setSessionSendInFlight(sessionId, false)
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
      focus: activeRun.value?.focus ?? nextRunFocus.value,
      work_scope_mode: activeRun.value?.work_scope_mode ?? activeSession.value?.work_scope_mode ?? 'workspace',
      allowed_project_ids: activeRun.value?.allowed_project_ids ?? activeSession.value?.allowed_project_ids ?? [],
      focus_version: activeRun.value?.focus_version ?? activeSession.value?.focus_version ?? 0,
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
      focus: activeRun.value?.focus ?? nextRunFocus.value,
      work_scope_mode: activeRun.value?.work_scope_mode ?? activeSession.value?.work_scope_mode ?? 'workspace',
      allowed_project_ids: activeRun.value?.allowed_project_ids ?? activeSession.value?.allowed_project_ids ?? [],
      focus_version: activeRun.value?.focus_version ?? activeSession.value?.focus_version ?? 0,
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
    case 'run.waiting':
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
  const runFocus = readSessionValue(activeRunBySession.value, sessionId, null)?.focus ?? runtimeRequest.scope
  const nextEvents = buildMutationRefreshEvents(event, {
    workspaceId: runFocus.workspace_id ?? null,
    projectId: runFocus.project_id ?? null,
    pageId: runFocus.page_id ?? null,
    componentId: runFocus.component_id ?? null,
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
    } else if (event.kind === 'theme') {
      emit('theme-updated', event)
    } else if (event.kind === 'style') {
      emit('style-updated', event)
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
    const run = readSessionValue(activeRunBySession.value, sessionId, null)
    if (run && shouldSubscribeRunEvents(run)) {
      ensureRunEventSubscription(sessionId, run, run.event_index ?? -1)
    }
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
      tone: 'warning' as const,
    }
  }
  if (run?.status === 'cancelling') {
    return {
      label: '停止中',
      tone: 'warning' as const,
    }
  }
  if (isSessionRunning(sessionId)) {
    return {
      label: readSessionValue(interruptingBySession.value, sessionId, false) ? '停止中' : '运行中',
      tone: 'info' as const,
    }
  }
  if (run?.status === 'failed') {
    return {
      label: '失败',
      tone: 'danger' as const,
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
function resolveSessionRuntimeRequest(sessionId: string, sessions: AgentSessionItem[] = normalizedSessions.value ?? []) {
  const session = sessions.find(item => item.session_id === sessionId) ?? knownSessionsById.value[sessionId] ?? null
  const sessionScope = session ? resolveSessionScope(session) : null
  return {
    scope: sessionScope ?? scope.value,
    agentId: session?.agent_id ?? agentId.value,
  }
}

/**
 * 从会话 metadata 中读取固化的大模型信息，历史会话没有该字段时返回空。
 */
function extractSessionLlmMetadata(session: AgentSessionItem | null): AgentSessionLlmMetadata | null {
  const metadata = session?.metadata
  if (!metadata || typeof metadata !== 'object') {
    return null
  }
  const llm = (metadata as Record<string, unknown>).llm
  return llm && typeof llm === 'object' ? llm as AgentSessionLlmMetadata : null
}

/**
 * 兼容后端可能以字符串形式回传的配置 ID，无法解析时视为无固化模型。
 */
function normalizeLlmConfigId(value: AgentSessionLlmMetadata['config_id'] | undefined) {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  if (typeof value === 'string' && /^\d+$/.test(value.trim())) {
    return Number(value.trim())
  }
  return null
}

/**
 * 生成可选模型显示文案，区分管理员全局模型与当前用户个人模型。
 */
function formatLlmConfigLabel(config: LlmConfigItem) {
  const scopeLabel = config.scope === 'global' ? '全局模型' : '我的模型'
  return `${scopeLabel} · ${config.name}（${config.provider_config_name || config.provider_label} / ${config.model_id}）`
}

/**
 * 使用会话内固化的模型快照生成文案，适配模型后来被归档或删除的场景。
 */
function formatLlmMetadataLabel(metadata: AgentSessionLlmMetadata) {
  const scopeLabel = metadata.scope === 'global' ? '全局模型' : metadata.scope === 'personal' ? '我的模型' : '模型'
  const name = metadata.name || '已选模型'
  const provider = metadata.provider_config_name || metadata.provider_label || metadata.provider_key || ''
  const modelId = metadata.model_id || ''
  const detail = [provider, modelId].filter(Boolean).join(' / ')
  return detail ? `${scopeLabel} · ${name}（${detail}）` : `${scopeLabel} · ${name}`
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
 * 跳转到 AI 设置页，供用户创建或维护个人模型。
 */
function goToAiSettings() {
  router.push(buildGlobalPageLocation('accountAiSettings', route.fullPath))
}
</script>
