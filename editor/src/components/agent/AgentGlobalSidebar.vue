<!-- 文件功能：提供后台左侧全局智能体入口，按当前路由上下文切换助手并校验可用性。 -->
<template>
  <aside class="flex h-full shrink-0 bg-white">
    <div v-if="!expanded" class="flex w-14 flex-col items-center gap-2 border-r border-slate-100 py-4">
      <button
        v-for="agent in agentButtons"
        :key="agent.id"
        type="button"
        :data-testid="agent.id === 'agent-coordinator' ? 'agent-sidebar-toggle' : undefined"
        class="flex h-10 w-10 items-center justify-center rounded-lg border text-slate-500 transition"
        :class="getAgentRailButtonClass(agent.id, agent.icon)"
        :title="resolveAgentButtonTitle(agent.id, agent.name)"
        :disabled="!canOpenAgent(agent.id)"
        @click="openAgent(agent.id)"
      >
        <span class="flex h-7 w-7 items-center justify-center rounded-lg ring-1 transition" :class="getAgentIconShellClass(agent.icon, agent.id === agentId)">
          <component :is="resolveAgentIconComponent(agent.icon)" class="h-4 w-4" />
        </span>
      </button>
    </div>

    <Transition name="agent-panel">
      <section v-if="expanded" data-testid="agent-sidebar-panel" class="flex h-full w-[576px] flex-col overflow-hidden border border-slate-200 bg-slate-50">
        <header class="border-b border-slate-200 bg-white p-3">
          <div class="grid h-8 grid-cols-[minmax(0,1fr)_auto] items-center gap-2">
            <div class="min-w-0 flex-1 overflow-hidden">
              <div class="inline-flex h-8 max-w-full rounded-xl border border-slate-200 bg-slate-100 p-0.5 shadow-inner" role="tablist" aria-label="智能体切换">
                <button
                  v-for="agent in agentButtons"
                  :key="agent.id"
                  type="button"
                  role="tab"
                  class="inline-flex h-7 min-w-0 items-center gap-1.5 rounded-lg border px-3 text-xs font-semibold transition"
                  :class="getAgentTabClass(agent.id, agent.icon)"
                  :aria-selected="agent.id === agentId"
                  :disabled="!canOpenAgent(agent.id)"
                  :title="resolveAgentButtonTitle(agent.id, agent.name)"
                  @click="openAgent(agent.id)"
                >
                  <span class="flex h-5 w-5 shrink-0 items-center justify-center rounded-md ring-1" :class="getAgentIconShellClass(agent.icon, agent.id === agentId)">
                    <component :is="resolveAgentIconComponent(agent.icon)" class="h-3.5 w-3.5" />
                  </span>
                  <span class="truncate">{{ agent.name }}</span>
                </button>
              </div>
            </div>
            <button
              type="button"
              class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-transparent text-slate-500 transition hover:border-slate-200 hover:bg-slate-50 hover:text-slate-800"
              title="收起"
              @click="expanded = false"
            >
              <PanelLeftClose class="h-4 w-4" />
            </button>
          </div>

          <div class="mt-2 grid h-8 grid-cols-[minmax(0,1fr)_auto] items-center gap-2">
            <div :id="headerScopeId" class="min-w-0 flex-1" />
            <div :id="headerActionsId" class="flex shrink-0 items-center justify-end" />
          </div>
        </header>

        <div v-if="!workspaceId" class="p-4 text-sm leading-6 text-slate-500">
          当前路由缺少工作空间上下文，智能体入口暂不可用。
        </div>
        <AgentAssistantPanel
          v-else
          :key="agentId"
          embedded
          :workspace-id="workspaceId"
          :project-id="scope.project_id ?? null"
          :page-id="scope.page_id ?? null"
          :component-id="scope.component_id ?? null"
          :agent-id="agentId"
          :agent-display-name="selectedAgent?.name || '内容助手'"
          :scope="scope"
          :route-scope="routeScope"
          :context-title="contextTitle"
          :header-scope-target="headerScopeTarget"
          :header-actions-target="headerActionsTarget"
          :auto-create-key="autoCreateKey"
          :auto-navigate-target="agentTargetRoute"
          :enable-page-patch-actions="scope.scope_type === 'page'"
          :empty-text="emptyText"
          :composer-placeholder="composerPlaceholder"
          :route-available="isAgentRunAvailable(agentId)"
          :route-unavailable-reason="activeAgentUnavailableReason"
          @apply-suggested-content="handleApplySuggestedContent"
          @page-updated="handlePageUpdated"
          @project-pages-updated="handleProjectPagesUpdated"
          @project-updated="handleProjectUpdated"
          @component-updated="handleComponentUpdated"
          @asset-updated="handleAssetUpdated"
        />
      </section>
    </Transition>
  </aside>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useQuery } from '@tanstack/vue-query'
import { PanelLeftClose } from '@lucide/vue'

import { listAgents } from '@/api/ai'
import { getAgentIconShellClass, resolveAgentIconComponent } from '@/components/agent/agent-icon'
import {
  buildPageDetailPath,
  buildProjectPagesPath,
  buildWorkspaceAssetsPath,
  buildWorkspaceComponentsPath,
  buildWorkspaceHomePath,
} from '@/utils/workspace-routes'
import type { AgentMutationRefreshEvent } from '@/components/agent/agent-conversation-panel'
import type { AgentScopeContext } from '@/types/api'

interface Props {
  agentId?: string
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
  agentId: 'agent-coordinator',
  projectId: null,
  pageId: null,
  componentId: null,
  workspaceName: null,
  projectName: null,
  pageTitle: null,
  componentName: null,
  source: '',
})

const AgentAssistantPanel = defineAsyncComponent(() => import('@/components/agent/AgentAssistantPanel.vue'))
const expanded = ref(false)
const route = useRoute()
const activeAgentId = ref(props.agentId)
const agentId = computed(() => activeAgentId.value)
const headerScopeId = 'global-agent-scope-summary'
const headerScopeTarget = `#${headerScopeId}`
const headerActionsId = 'global-agent-session-actions'
const headerActionsTarget = `#${headerActionsId}`
const autoCreateKey = ref<string | number | null>(null)
const autoCreateSequence = ref(0)
const contentAgentProjectRequiredReason = '内容助手需要进入具体项目后才能启动。'
const componentAgentRouteRequiredReason = '组件助手只能在组件库页面发起对话。'
const resourceAgentRouteRequiredReason = '资源助手只能在资源库页面发起对话。'

const workspaceId = computed(() => props.workspaceId)
const projectId = computed(() => props.projectId ?? null)
const pageId = computed(() => props.pageId ?? null)
const workspaceName = computed(() => normalizeContextName(props.workspaceName))
const projectName = computed(() => normalizeContextName(props.projectName))
const pageTitle = computed(() => normalizeContextName(props.pageTitle))
const agentTarget = computed(() => resolveAgentTarget(agentId.value))
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
    queryKey: ['ai-agents', 'sidebar', agentId.value, scopeKey.value],
    queryFn: () => listAgents(scope.value),
    enabled: !!workspaceId.value,
  })),
)
const agentButtons = computed(() => agentsQuery.data.value?.length
  ? mergeAgentButtons(agentsQuery.data.value)
  : resolveFallbackAgentButtons())
const selectedAgent = computed(() => (
  agentButtons.value.find(agent => agent.id === agentId.value) ?? resolveFallbackAgentButton(agentId.value)
))
const activeAgentUnavailableReason = computed(() => (
  resolveAgentRunUnavailableReason(agentId.value) ?? ''
))
const contextTitle = computed(() => agentTarget.value.contextTitle)
const contextTypeLabel = computed(() => agentTarget.value.contextTypeLabel)
const emptyText = computed(() => `智能体会在 ${contextTitle.value}${contextTypeLabel.value ? `（${contextTypeLabel.value}）` : ''}内执行任务。`)
const composerPlaceholder = computed(() => '描述目标；内容助手会处理页面/项目任务，并按需调用组件或资源助手。')

function normalizeContextName(value: string | null | undefined): string {
  return value?.trim() ?? ''
}

interface AgentTarget {
  scope: AgentScopeContext
  routePath: string | null
  contextTitle: string
  contextTypeLabel: string
}

/** 返回列表加载前的智能体按钮元数据，避免短暂回退到错误图标。 */
function resolveFallbackAgentButton(targetAgentId: string): { id: string; name: string; icon: string } {
  if (targetAgentId === 'component-manager') {
    return { id: targetAgentId, name: '组件助手', icon: 'component-blocks' }
  }
  if (targetAgentId === 'resource-manager') {
    return { id: targetAgentId, name: '资源助手', icon: 'resource-images' }
  }
  return { id: targetAgentId, name: '内容助手', icon: 'content-spark' }
}

/**
 * 后端通常会返回完整智能体列表；本地补齐可避免查询切换瞬间丢失切换入口。
 */
function resolveFallbackAgentButtons(): Array<{ id: string; name: string; icon: string }> {
  return [
    resolveFallbackAgentButton('agent-coordinator'),
    resolveFallbackAgentButton('component-manager'),
    resolveFallbackAgentButton('resource-manager'),
  ]
}

function mergeAgentButtons<T extends { id: string }>(loadedAgents: T[]): Array<T | { id: string; name: string; icon: string }> {
  const loadedIds = new Set(loadedAgents.map(agent => agent.id))
  return [
    ...loadedAgents,
    ...resolveFallbackAgentButtons().filter(agent => !loadedIds.has(agent.id)),
  ]
}

/**
 * 按“目标助手”解析工作范围和默认落点；只有显式切换助手时才会使用 routePath 自动跳转。
 */
function resolveAgentTarget(targetAgentId: string): AgentTarget {
  const wid = workspaceId.value ?? 0
  if (!wid) {
    return {
      scope: buildWorkspaceScope(0, 'editor-agent-sidebar'),
      routePath: null,
      contextTitle: '智能体会话',
      contextTypeLabel: '',
    }
  }

  if (targetAgentId === 'component-manager') {
    return {
      scope: buildWorkspaceScope(wid, 'editor-component-library'),
      routePath: buildWorkspaceComponentsPath(wid),
      contextTitle: workspaceName.value || '组件库',
      contextTypeLabel: '组件库',
    }
  }

  if (targetAgentId === 'resource-manager') {
    return {
      scope: buildWorkspaceScope(wid, 'editor-asset-library'),
      routePath: buildWorkspaceAssetsPath(wid),
      contextTitle: workspaceName.value || '资源库',
      contextTypeLabel: '资源库',
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
    routePath: buildWorkspaceHomePath(wid),
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
 * 读取当前路由上下文下指定助手的运行不可用原因；返回空值表示可以发起对话。
 * @param targetAgentId 待判断的智能体 ID
 */
function resolveAgentRunUnavailableReason(targetAgentId: string): string | null {
  if (!workspaceId.value) {
    return '当前路由缺少工作空间上下文。'
  }
  const routeBoundReason = resolveRouteBoundAgentUnavailableReason(targetAgentId)
  if (routeBoundReason) {
    return routeBoundReason
  }
  if (targetAgentId === 'agent-coordinator' && !projectId.value) {
    return contentAgentProjectRequiredReason
  }
  const loadedAgent = agentsQuery.data.value?.find(agent => agent.id === targetAgentId)
  if (loadedAgent?.available === false) {
    return loadedAgent.unavailable_reason || '当前路由上下文下不可用。'
  }
  return null
}

/**
 * 读取侧栏切换入口的不可用原因；库助手允许跨页面切换，但不能跨页面发起对话。
 * @param targetAgentId 待判断的智能体 ID
 */
function resolveAgentSwitchUnavailableReason(targetAgentId: string): string | null {
  if (!workspaceId.value) {
    return '当前路由缺少工作空间上下文。'
  }
  const loadedAgent = agentsQuery.data.value?.find(agent => agent.id === targetAgentId)
  if (loadedAgent?.available === false) {
    return loadedAgent.unavailable_reason || '当前路由上下文下不可用。'
  }
  return null
}

function isAgentRunAvailable(targetAgentId: string): boolean {
  return resolveAgentRunUnavailableReason(targetAgentId) === null
}

function canOpenAgent(targetAgentId: string): boolean {
  if (targetAgentId === 'agent-coordinator') {
    return Boolean(workspaceId.value)
  }
  return resolveAgentSwitchUnavailableReason(targetAgentId) === null
}

/**
 * 组件与资源助手只允许在各自完整库页面发起新对话，避免跨页面写入库资源。
 * @param targetAgentId 待判断的智能体 ID
 */
function resolveRouteBoundAgentUnavailableReason(targetAgentId: string): string | null {
  if (targetAgentId === 'component-manager' && route.name !== 'components') {
    return componentAgentRouteRequiredReason
  }
  if (targetAgentId === 'resource-manager' && route.name !== 'assets') {
    return resourceAgentRouteRequiredReason
  }
  return null
}

function resolveAgentButtonTitle(targetAgentId: string, name: string): string {
  const unavailableReason = resolveAgentSwitchUnavailableReason(targetAgentId)
  return unavailableReason ? `${name}：${unavailableReason}` : name
}

/**
 * 返回展开态 tab 的状态样式，让当前智能体在背景、边框和阴影上都明显区别于未选中项。
 */
function getAgentTabClass(targetAgentId: string, icon: string | null | undefined): string {
  if (!canOpenAgent(targetAgentId)) {
    return 'cursor-not-allowed border-transparent text-slate-300'
  }
  if (targetAgentId !== agentId.value) {
    return 'border-transparent text-slate-500 hover:border-slate-200 hover:bg-white hover:text-slate-800'
  }
  return resolveAgentActiveClass(icon, 'tab')
}

/**
 * 返回收起态窄栏按钮样式，与展开态 tab 使用同一套强调色。
 */
function getAgentRailButtonClass(targetAgentId: string, icon: string | null | undefined): string {
  if (!canOpenAgent(targetAgentId)) {
    return 'cursor-not-allowed border-transparent opacity-40 hover:bg-transparent hover:text-slate-500'
  }
  if (targetAgentId !== agentId.value) {
    return 'border-transparent hover:border-slate-200 hover:bg-slate-100 hover:text-slate-800'
  }
  return resolveAgentActiveClass(icon, 'rail')
}

/**
 * 根据智能体图标色系返回选中态样式，避免所有智能体都显示为同一种蓝色。
 */
function resolveAgentActiveClass(icon: string | null | undefined, mode: 'tab' | 'rail'): string {
  const normalizedIcon = String(icon || '').trim()
  if (normalizedIcon === 'component-blocks') {
    return mode === 'tab'
      ? 'border-violet-500 bg-violet-600 text-white shadow-md shadow-violet-100'
      : 'border-violet-200 bg-violet-50 text-violet-700 shadow-sm ring-2 ring-violet-100'
  }
  if (normalizedIcon === 'resource-images') {
    return mode === 'tab'
      ? 'border-emerald-500 bg-emerald-600 text-white shadow-md shadow-emerald-100'
      : 'border-emerald-200 bg-emerald-50 text-emerald-700 shadow-sm ring-2 ring-emerald-100'
  }
  if (normalizedIcon === 'content-spark') {
    return mode === 'tab'
      ? 'border-sky-500 bg-sky-600 text-white shadow-md shadow-sky-100'
      : 'border-sky-200 bg-sky-50 text-sky-700 shadow-sm ring-2 ring-sky-100'
  }
  return mode === 'tab'
    ? 'border-slate-700 bg-slate-800 text-white shadow-md shadow-slate-100'
    : 'border-slate-200 bg-slate-100 text-slate-800 shadow-sm ring-2 ring-slate-100'
}

function openAgent(targetAgentId: string): void {
  if (!canOpenAgent(targetAgentId)) {
    return
  }
  const agentChanged = targetAgentId !== activeAgentId.value
  activeAgentId.value = targetAgentId
  expanded.value = true
  if (agentChanged && isAgentRunAvailable(targetAgentId)) {
    autoCreateSequence.value += 1
    autoCreateKey.value = `${targetAgentId}:${autoCreateSequence.value}`
    return
  }
  autoCreateKey.value = null
}

watch(
  () => [props.agentId, route.name, workspaceId.value] as const,
  ([nextAgentId]) => {
    const routeAgentId = nextAgentId || 'agent-coordinator'
    if (!canOpenAgent(activeAgentId.value)) {
      activeAgentId.value = routeAgentId
      autoCreateKey.value = null
    }
  },
  { immediate: true },
)

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
</style>
