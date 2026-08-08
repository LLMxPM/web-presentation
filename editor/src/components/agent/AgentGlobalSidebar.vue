<!-- 文件功能：提供后台左侧全局智能体对话面板，按当前路由上下文切换助手并校验可用性。 -->
<template>
  <aside class="flex h-full shrink-0 bg-surface">
    <Transition name="agent-panel">
      <section v-if="expanded" data-testid="agent-sidebar-panel" class="agent-sidebar-panel flex h-full flex-col overflow-hidden border border-border bg-canvas">
        <header class="border-b border-border bg-surface p-3">
          <div class="grid h-8 grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-2">
            <div :id="headerScopeId" class="min-w-0 flex-1" />
            <div :id="headerActionsId" class="flex shrink-0 items-center justify-end" />
            <UiIconButton
              label="收起"
              size="sm"
              class="shrink-0 border-transparent text-text-muted hover:border-border hover:bg-surface-hover hover:text-text"
              @click="emit('update:expanded', false)"
            >
              <PanelLeftClose class="h-4 w-4" />
            </UiIconButton>
          </div>
        </header>

        <div v-if="!workspaceId" class="p-4 text-sm leading-6 text-text-muted">
          当前路由缺少工作空间上下文，智能体入口暂不可用。
        </div>
        <AgentAssistantPanel
          v-else
          :key="agentPanelKey"
          embedded
          :workspace-id="workspaceId"
          :project-id="scope.project_id ?? null"
          :page-id="scope.page_id ?? null"
          :component-id="scope.component_id ?? null"
          :agent-id="agentId"
          :agent-display-name="'内容助手'"
          :scope="scope"
          :route-scope="routeScope"
          :context-title="contextTitle"
          :header-scope-target="headerScopeTarget"
          :header-actions-target="headerActionsTarget"
          :auto-navigate-target="agentTargetRoute"
          :enable-page-patch-actions="scope.scope_type === 'page'"
          :empty-text="emptyText"
          :composer-placeholder="composerPlaceholder"
          :route-available="isAgentRunAvailable()"
          :route-unavailable-reason="activeAgentUnavailableReason"
          @apply-suggested-content="handleApplySuggestedContent"
          @page-updated="handlePageUpdated"
          @project-pages-updated="handleProjectPagesUpdated"
          @project-updated="handleProjectUpdated"
          @component-updated="handleComponentUpdated"
          @asset-updated="handleAssetUpdated"
          @theme-updated="handleThemeUpdated"
          @style-updated="handleStyleUpdated"
        />
      </section>
    </Transition>
  </aside>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import { useRoute } from 'vue-router'
import { useQuery } from '@tanstack/vue-query'
import { PanelLeftClose } from '@lucide/vue'

import { listAgents } from '@/api/ai'
import { UiIconButton } from '@/components/ui'
import {
  buildPageDetailPath,
  buildProjectPagesPath,
} from '@/utils/workspace-routes'
import type { AgentMutationRefreshEvent } from '@/components/agent/agent-conversation-panel'
import type { AgentScopeContext } from '@/types/api'

interface Props {
  expanded?: boolean
  workspaceId: number | null
  projectId?: number | null
  pageId?: number | null
  componentId?: number | null
  workspaceName?: string | null
  projectName?: string | null
  pageTitle?: string | null
  componentName?: string | null
  source?: string
}

const props = withDefaults(defineProps<Props>(), {
  expanded: true,
  projectId: null,
  pageId: null,
  componentId: null,
  workspaceName: null,
  projectName: null,
  pageTitle: null,
  componentName: null,
  source: '',
})
const emit = defineEmits<{
  'update:expanded': [expanded: boolean]
}>()

const AgentAssistantPanel = defineAsyncComponent(() => import('@/components/agent/AgentAssistantPanel.vue'))
const agentId = 'agent-coordinator'
const route = useRoute()
const headerScopeId = 'global-agent-scope-summary'
const headerScopeTarget = `#${headerScopeId}`
const headerActionsId = 'global-agent-session-actions'
const headerActionsTarget = `#${headerActionsId}`

const workspaceId = computed(() => props.workspaceId)
const projectId = computed(() => props.projectId ?? null)
const pageId = computed(() => props.pageId ?? null)
const workspaceName = computed(() => normalizeContextName(props.workspaceName))
const projectName = computed(() => normalizeContextName(props.projectName))
const pageTitle = computed(() => normalizeContextName(props.pageTitle))
const agentPanelKey = computed(() => `${workspaceId.value ?? 'none'}:${agentId}`)
const agentTarget = computed(() => resolveAgentTarget())
const scope = computed(() => agentTarget.value.scope)
const routeScope = computed(() => resolveCurrentRouteScope())
const agentTargetRoute = computed(() => agentTarget.value.routePath)
const scopeKey = computed(() => [
  scope.value.scope_type,
  scope.value.workspace_id,
  scope.value.project_id ?? '',
  scope.value.page_id ?? '',
  scope.value.component_id ?? '',
  scope.value.source,
].join(':'))
const agentsQuery = useQuery(
  computed(() => ({
    queryKey: ['ai-agents', 'sidebar', agentId, scopeKey.value],
    queryFn: () => listAgents(scope.value),
    enabled: !!workspaceId.value,
  })),
)
const activeAgentUnavailableReason = computed(() => (
  resolveAgentRunUnavailableReason() ?? ''
))
const contextTitle = computed(() => agentTarget.value.contextTitle)
const contextTypeLabel = computed(() => agentTarget.value.contextTypeLabel)
const emptyText = computed(() => `智能体会在 ${contextTitle.value}${contextTypeLabel.value ? `（${contextTypeLabel.value}）` : ''}内执行任务。`)
const composerPlaceholder = computed(() => '描述目标；内容助手可以管理当前工作空间内的项目、页面、组件、资源、主题和样式。')

function normalizeContextName(value: string | null | undefined): string {
  return value?.trim() ?? ''
}

interface AgentTarget {
  scope: AgentScopeContext
  routePath: string | null
  contextTitle: string
  contextTypeLabel: string
}

/**
 * 按当前路由上下文解析统一内容助手的工作范围和默认落点。
 */
function resolveAgentTarget(): AgentTarget {
  const wid = workspaceId.value ?? 0
  if (!wid) {
    return {
      scope: buildWorkspaceScope(0, 'editor-agent-sidebar'),
      routePath: null,
      contextTitle: '智能体会话',
      contextTypeLabel: '',
    }
  }

  if (!isLibraryRoute() && pageId.value && projectId.value) {
    return {
      scope: {
        scope_type: 'page',
        workspace_id: wid,
        project_id: projectId.value,
        page_id: pageId.value,
        component_id: null,
        workspace_name: workspaceName.value || null,
        project_name: projectName.value || null,
        page_title: pageTitle.value || null,
        component_name: null,
        source: resolveContentSource(),
      },
      routePath: buildPageDetailPath(wid, projectId.value, pageId.value),
      contextTitle: pageTitle.value || '当前页面',
      contextTypeLabel: '页面',
    }
  }

  if (!isLibraryRoute() && projectId.value) {
    return {
      scope: {
        scope_type: 'project',
        workspace_id: wid,
        project_id: projectId.value,
        page_id: null,
        component_id: null,
        workspace_name: workspaceName.value || null,
        project_name: projectName.value || null,
        page_title: null,
        component_name: null,
        source: resolveContentSource(),
      },
      routePath: buildProjectPagesPath(wid, projectId.value),
      contextTitle: projectName.value || '当前项目',
      contextTypeLabel: '项目',
    }
  }

  return {
    scope: buildWorkspaceScope(wid, 'editor-agent-sidebar'),
    routePath: null,
    contextTitle: workspaceName.value || '当前工作空间',
    contextTypeLabel: '工作空间',
  }
}

function buildWorkspaceScope(wid: number, source: string): AgentScopeContext {
  return {
    scope_type: 'workspace',
    workspace_id: wid,
    project_id: null,
    page_id: null,
    component_id: null,
    workspace_name: workspaceName.value || null,
    project_name: null,
    page_title: null,
    component_name: null,
    source,
  }
}

/**
 * 返回真实当前路由范围；助手目标范围用于请求，当前路由范围只用于越界检测和状态展示。
 */
function resolveCurrentRouteScope(): AgentScopeContext {
  const wid = workspaceId.value ?? 0
  if (!wid) {
    return buildWorkspaceScope(0, props.source || 'editor-agent-sidebar')
  }

  if (route.name === 'components') {
    return buildWorkspaceScope(wid, 'editor-component-library')
  }

  if (route.name === 'assets') {
    return buildWorkspaceScope(wid, 'editor-asset-library')
  }

  if (route.name === 'themes') {
    return buildWorkspaceScope(wid, 'editor-theme-font-library')
  }

  if (pageId.value && projectId.value) {
    return {
      scope_type: 'page',
      workspace_id: wid,
      project_id: projectId.value,
      page_id: pageId.value,
      component_id: null,
      workspace_name: workspaceName.value || null,
      project_name: projectName.value || null,
      page_title: pageTitle.value || null,
      component_name: null,
      source: resolveContentSource(),
    }
  }

  if (projectId.value) {
    return {
      scope_type: 'project',
      workspace_id: wid,
      project_id: projectId.value,
      page_id: null,
      component_id: null,
      workspace_name: workspaceName.value || null,
      project_name: projectName.value || null,
      page_title: null,
      component_name: null,
      source: resolveContentSource(),
    }
  }

  return buildWorkspaceScope(wid, props.source || 'editor-agent-sidebar')
}

function isLibraryRoute(): boolean {
  return route.name === 'components' || route.name === 'assets' || route.name === 'themes' || route.name === 'workspaceStyles'
}

function resolveContentSource(): string {
  return props.source && !isLibraryRoute() ? props.source : 'editor-agent-sidebar'
}

/**
 * 读取当前路由上下文下统一内容助手的运行不可用原因；返回空值表示可以发起对话。
 */
function resolveAgentRunUnavailableReason(): string | null {
  if (!workspaceId.value) {
    return '当前路由缺少工作空间上下文。'
  }
  const loadedAgent = agentsQuery.data.value?.find(agent => agent.id === agentId)
  if (loadedAgent?.available === false) {
    return loadedAgent.unavailable_reason || '当前路由上下文下不可用。'
  }
  return null
}

function isAgentRunAvailable(): boolean {
  return resolveAgentRunUnavailableReason() === null
}

function handleApplySuggestedContent(content: string): void {
  window.dispatchEvent(new CustomEvent('agent:apply-suggested-content', {
    detail: { pageId: pageId.value, content },
  }))
}

function handlePageUpdated(event: AgentMutationRefreshEvent): void {
  window.dispatchEvent(new CustomEvent('agent:page-updated', {
    detail: buildMutationEventDetail(event),
  }))
}

function handleProjectPagesUpdated(event: AgentMutationRefreshEvent): void {
  window.dispatchEvent(new CustomEvent('agent:project-pages-updated', {
    detail: buildMutationEventDetail(event),
  }))
}

function handleProjectUpdated(event: AgentMutationRefreshEvent): void {
  window.dispatchEvent(new CustomEvent('agent:project-updated', {
    detail: buildMutationEventDetail(event),
  }))
}

function handleComponentUpdated(event: AgentMutationRefreshEvent): void {
  window.dispatchEvent(new CustomEvent('agent:component-updated', {
    detail: buildMutationEventDetail(event),
  }))
}

function handleAssetUpdated(event: AgentMutationRefreshEvent): void {
  window.dispatchEvent(new CustomEvent('agent:asset-updated', {
    detail: buildMutationEventDetail(event),
  }))
}

function handleThemeUpdated(event: AgentMutationRefreshEvent): void {
  window.dispatchEvent(new CustomEvent('agent:theme-updated', {
    detail: buildMutationEventDetail(event),
  }))
}

function handleStyleUpdated(event: AgentMutationRefreshEvent): void {
  window.dispatchEvent(new CustomEvent('agent:style-updated', {
    detail: buildMutationEventDetail(event),
  }))
}

/**
 * 补齐全局事件上下文，避免局部面板缺字段时下游无法判断刷新范围。
 */
function buildMutationEventDetail(event: AgentMutationRefreshEvent): AgentMutationRefreshEvent {
  return {
    ...event,
    workspaceId: event.workspaceId ?? workspaceId.value,
    projectId: event.projectId ?? projectId.value,
    pageId: event.pageId ?? pageId.value,
    componentId: event.componentId ?? scope.value.component_id ?? null,
    assetId: event.assetId ?? null,
    themeId: event.themeId ?? null,
    styleId: event.styleId ?? null,
  }
}
</script>

<style scoped>
.agent-panel-enter-active,
.agent-panel-leave-active {
  transition: width 0.18s ease, opacity 0.18s ease;
}

.agent-panel-enter-from,
.agent-panel-leave-to {
  width: 0;
  opacity: 0;
}

.agent-sidebar-panel {
  width: 544px;
}

@media (max-width: 1399px) {
  .agent-sidebar-panel {
    width: 480px;
  }
}
</style>
