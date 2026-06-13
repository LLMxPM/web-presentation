<!-- 文件功能：后台主布局，统一承载顶部栏、左侧 AI 助手、主工作区与右侧工作空间 Dock。 -->
<template>
  <div class="flex h-screen bg-slate-50 overflow-hidden">
    <AgentGlobalSidebar
      v-if="sidebarsVisible"
      :agent-id="activeAgentId"
      :workspace-id="workspaceId"
      :project-id="projectId"
      :page-id="pageId"
      :component-id="activeAgentComponentId"
      :workspace-name="workspaceQuery.data.value?.name"
      :project-name="projectQuery.data.value?.name"
      :page-title="pageQuery.data.value?.title"
      :component-name="activeAgentComponentName"
      :source="activeAgentSource"
      @update:expanded="agentSidebarExpanded = $event"
    />

    <div class="flex min-w-0 flex-1 flex-col overflow-hidden">
      <!-- Header Area -->
      <header class="h-16 bg-white border-b border-slate-200 flex items-center justify-between px-6 z-10 shrink-0">
        <div
          class="flex items-center transition-[width,opacity] duration-150"
          :class="agentSidebarExpanded ? 'w-0 overflow-hidden opacity-0' : 'w-48 opacity-100'"
        >
          <div v-if="!agentSidebarExpanded" data-testid="app-brand-title" class="text-xl font-extrabold text-slate-800 tracking-tight select-none">Web-Presentation</div>
        </div>

        <div class="flex min-w-0 flex-1 items-center justify-start gap-2 px-4">
          <WorkspaceSwitcher />
          <ProjectQuickSwitcher
            v-if="workspaceId && sidebarsVisible"
            :workspace-id="workspaceId"
            :current-project-id="projectId"
            :current-project-name="projectQuery.data.value?.name"
          />
          <nav
            v-if="headerBreadcrumbs.length > 0"
            aria-label="当前位置"
            class="ml-1 flex min-w-0 items-center gap-2 border-l border-slate-200 pl-3 text-sm font-semibold text-slate-500"
          >
            <template v-for="(item, index) in headerBreadcrumbs" :key="`${item.label}-${index}`">
              <ChevronRight v-if="index > 0" class="h-4 w-4 shrink-0 text-slate-300" />
              <RouterLink
                v-if="item.to"
                :to="item.to"
                class="max-w-[180px] truncate transition-colors hover:text-slate-800"
              >
                {{ item.label }}
              </RouterLink>
              <span v-else class="max-w-[180px] truncate text-slate-700">{{ item.label }}</span>
            </template>
          </nav>
        </div>

        <div class="flex items-center justify-end min-w-[180px] gap-4">
          <UserMenu />
        </div>
      </header>

      <!-- Main Content Area -->
      <div class="flex-1 flex overflow-hidden">
        <main
          class="min-h-0 min-w-0 flex-1 p-3"
          :class="fullHeightPage ? 'overflow-hidden' : 'overflow-y-auto scroll-smooth'"
        >
          <div
            class="max-w-[1600px] mx-auto"
            :class="fullHeightPage ? 'h-full min-h-0' : 'min-h-full'"
          >
            <RouterView v-slot="{ Component }">
              <Transition name="page" mode="out-in">
                <component :is="Component" />
              </Transition>
            </RouterView>
          </div>
        </main>

        <AssetManagerPanel
          v-if="workspaceDockVisible && assetPanelVisible"
          v-model="assetPanelVisible"
          :workspace-id="workspaceId"
        />
        <ComponentManagerPanel
          v-if="workspaceDockVisible && componentPanelVisible"
          v-model="componentPanelVisible"
          read-only
          :workspace-id="workspaceId"
        />
        <WorkspaceDock
          v-if="workspaceDockVisible && workspaceId"
          :workspace-id="workspaceId"
          :active-key="activeWorkspaceRouteKey"
          :active-panel="activeSupplementPanel"
          @navigate="handleDockNavigate"
          @toggle-panel="toggleSupplementPanel"
        />
      </div>

      <OpenSourceFooter />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, onUnmounted, provide, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { useQuery } from '@tanstack/vue-query'
import { ChevronRight } from '@lucide/vue'
import { getPage, getProject, getWorkspace } from '@/api/catalog'
import UserMenu from '@/components/nav/UserMenu.vue'
import WorkspaceSwitcher from '@/components/nav/WorkspaceSwitcher.vue'
import ProjectQuickSwitcher from '@/components/nav/ProjectQuickSwitcher.vue'
import WorkspaceDock from '@/components/nav/WorkspaceDock.vue'
import AgentGlobalSidebar from '@/components/agent/AgentGlobalSidebar.vue'
import OpenSourceFooter from '@/components/layout/OpenSourceFooter.vue'
import { componentAgentContextKey } from '@/composables/component-agent-context'
import { buildProjectPagesPath, type WorkspaceRouteKey } from '@/utils/workspace-routes'
import type { WorkspaceComponentItem } from '@/types/api'

const AssetManagerPanel = defineAsyncComponent(() => import('@/components/project/AssetManagerPanel.vue'))
const ComponentManagerPanel = defineAsyncComponent(() => import('@/components/project/ComponentManagerPanel.vue'))

type SupplementPanelKey = 'assets' | 'components'

const route = useRoute()
const router = useRouter()
const activeSupplementPanel = ref<SupplementPanelKey | null>(null)
const componentAgentSelection = ref<WorkspaceComponentItem | null>(null)
const agentSidebarExpanded = ref(false)

interface HeaderBreadcrumb {
  label: string
  to?: string
}

const assetPanelVisible = computed({
  get: () => activeSupplementPanel.value === 'assets',
  set: value => updateSupplementPanel('assets', value),
})
const componentPanelVisible = computed({
  get: () => activeSupplementPanel.value === 'components',
  set: value => updateSupplementPanel('components', value),
})

/**
 * 接收右侧辅助面板的 v-model 回写，确保同一时间只展开一个面板。
 * @param panel 目标面板 key
 * @param visible 是否展开
 */
function updateSupplementPanel(panel: SupplementPanelKey, visible: boolean): void {
  if (visible) {
    activeSupplementPanel.value = panel
    return
  }
  if (activeSupplementPanel.value === panel) {
    activeSupplementPanel.value = null
  }
}

/**
 * 处理右侧 Dock 的轻量面板切换。
 * @param panel 待切换面板 key
 */
function toggleSupplementPanel(panel: SupplementPanelKey): void {
  activeSupplementPanel.value = activeSupplementPanel.value === panel ? null : panel
}

/**
 * 处理右侧 Dock 的完整页面导航，导航前关闭轻量面板。
 * @param path 目标页面路径
 */
function handleDockNavigate(path: string): void {
  activeSupplementPanel.value = null
  void router.push(path)
}

/**
 * 同步组件库页面当前选中组件，供全局智能体侧栏切换 component scope。
 * @param component 当前选中的工作空间组件；为空时回到工作空间组件库上下文
 */
function setComponentAgentSelection(component: WorkspaceComponentItem | null) {
  componentAgentSelection.value = component
}

/**
 * 关闭布局级右侧辅助面板，避免跨路由保留上一个工作空间页面的侧栏状态。
 */
function closeSupplementPanels(): void {
  activeSupplementPanel.value = null
}

provide(componentAgentContextKey, {
  selectedComponent: componentAgentSelection,
  setSelectedComponent: setComponentAgentSelection,
})

const workspaceId = computed(() => {
  const wid = route.params.workspaceId
  return wid ? parseInt(wid as string, 10) : null
})
const projectId = computed(() => {
  const pid = route.params.projectId
  return pid ? parseInt(pid as string, 10) : null
})
const pageId = computed(() => {
  const pid = route.params.pageId
  return pid ? parseInt(pid as string, 10) : null
})
const activeAgentId = computed(() => {
  if (route.name === 'components') return 'component-manager'
  if (route.name === 'assets') return 'resource-manager'
  return 'agent-coordinator'
})
const activeAgentSource = computed(() => {
  if (route.name === 'components') return 'editor-component-library'
  if (route.name === 'assets') return 'editor-asset-library'
  return 'editor-agent-sidebar'
})
const fullHeightPage = computed(() => Boolean(route.meta.fullHeight))
const sidebarsVisible = computed(() => !route.meta.hideSidebars)
const workspaceDockVisible = computed(() => sidebarsVisible.value && !!workspaceId.value)
const activeWorkspaceRouteKey = computed<WorkspaceRouteKey>(() => {
  const routeKey = route.meta.workspaceNav
  if (routeKey === 'components' || routeKey === 'assets' || routeKey === 'themes' || routeKey === 'styles') {
    return routeKey
  }
  return 'projects'
})
const activeAgentComponentId = computed(() => (
  route.name === 'components' ? componentAgentSelection.value?.id ?? null : null
))
const activeAgentComponentName = computed(() => (
  route.name === 'components' ? componentAgentSelection.value?.name ?? null : null
))

watch(
  () => route.name,
  (routeName) => {
    if (routeName !== 'components') {
      componentAgentSelection.value = null
    }
  },
  { immediate: true },
)

watch(
  () => [sidebarsVisible.value, workspaceId.value] as const,
  ([visible, nextWorkspaceId]) => {
    if (!visible || !nextWorkspaceId) {
      agentSidebarExpanded.value = false
      closeSupplementPanels()
    }
  },
  { immediate: true },
)

const workspaceQuery = useQuery(
  computed(() => ({
    queryKey: ['workspace', workspaceId.value],
    queryFn: () => getWorkspace(workspaceId.value as number),
    enabled: !!workspaceId.value,
  })),
)

const projectQuery = useQuery(
  computed(() => ({
    queryKey: ['project', projectId.value],
    queryFn: () => getProject(projectId.value as number),
    enabled: !!projectId.value,
  })),
)

const pageQuery = useQuery(
  computed(() => ({
    queryKey: ['page', pageId.value],
    queryFn: () => getPage(pageId.value as number),
    enabled: !!pageId.value,
  })),
)

/**
 * 智能体修改当前项目配置后，刷新顶部项目名称等布局级信息。
 */
function handleGlobalAgentProjectUpdated(event: Event): void {
  const detail = (event as CustomEvent<{ workspaceId?: number | null; projectId?: number | null }>).detail
  if (!projectId.value) {
    return
  }
  if (detail?.workspaceId && detail.workspaceId !== workspaceId.value) return
  if (detail?.projectId && detail.projectId !== projectId.value) return
  void projectQuery.refetch()
}

const headerBreadcrumbs = computed<HeaderBreadcrumb[]>(() => {
  if (route.name === 'accountAiSettings') {
    return [{ label: 'AI 设置' }]
  }

  if (!workspaceId.value) {
    return []
  }

  const breadcrumbs: HeaderBreadcrumb[] = []
  if (route.name === 'workspaceHome') {
    return [{ label: '项目总览' }]
  }

  if (route.name === 'components') {
    breadcrumbs.push({ label: '组件库' })
    return breadcrumbs
  }

  if (route.name === 'assets') {
    breadcrumbs.push({ label: '资源库' })
    return breadcrumbs
  }

  if (route.name === 'themes') {
    breadcrumbs.push({ label: '主题与字体' })
    return breadcrumbs
  }

  if (route.name === 'workspaceStyles') {
    breadcrumbs.push({ label: '样式库' })
    return breadcrumbs
  }

  if (projectId.value) {
    breadcrumbs.push({
      label: '项目首页',
      to: pageId.value ? buildProjectPagesPath(workspaceId.value, projectId.value) : undefined,
    })
  }

  if (pageId.value) {
    breadcrumbs.push({
      label: pageQuery.data.value?.title ?? '正在加载页面...',
    })
  }

  return breadcrumbs
})

onMounted(() => {
  window.addEventListener('agent:project-updated', handleGlobalAgentProjectUpdated)
})

onUnmounted(() => {
  window.removeEventListener('agent:project-updated', handleGlobalAgentProjectUpdated)
})
</script>

<style scoped>
.page-enter-active,
.page-leave-active {
  transition: all 0.2s ease;
}

.page-enter-from {
  opacity: 0;
  transform: translateY(10px);
}

.page-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}
</style>
