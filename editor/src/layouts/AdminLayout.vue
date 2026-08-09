<!-- 文件功能：后台主布局，统一承载顶部栏、左侧 AI 助手、主工作区与右侧工作空间 Dock。 -->
<template>
  <div data-testid="admin-layout" class="admin-layout flex h-screen min-w-0 overflow-hidden bg-canvas text-text">
    <aside v-if="sidebarsVisible" class="admin-layout-agent">
      <AgentGlobalSidebar
        :expanded="agentSidebarExpanded"
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
    </aside>

    <AgentFloatingTrigger
      v-if="sidebarsVisible && workspaceId"
      :expanded="agentSidebarExpanded"
      @update:expanded="agentSidebarExpanded = $event"
    />

    <div class="flex min-w-0 flex-1 flex-col overflow-hidden">
      <!-- Header Area -->
      <header class="admin-layout-header flex h-14 shrink-0 items-center justify-between border-b border-border bg-surface px-3">
        <div class="admin-layout-context flex min-w-0 flex-1 items-center justify-start gap-2 px-2">
          <div v-if="globalPageTitle" class="flex min-w-0 items-center gap-2">
            <UiButton
              variant="ghost"
              size="sm"
              data-testid="global-page-return"
              :title="globalReturnTitle"
              @click="returnFromGlobalPage"
            >
              <ArrowLeft class="h-4 w-4" />
              {{ globalReturnLabel }}
            </UiButton>
            <div class="h-5 w-px shrink-0 bg-border" />
            <span class="truncate text-sm font-bold text-text">{{ globalPageTitle }}</span>
          </div>
          <div
            v-else-if="workspaceId"
            class="admin-layout-workspace-context flex shrink-0 items-center border-r border-border pr-3"
            aria-label="当前工作空间"
          >
            <WorkspaceSwitcher />
          </div>
          <nav
            v-if="!globalPageTitle && headerBreadcrumbs.length > 0"
            aria-label="当前位置"
            class="admin-layout-breadcrumb flex min-w-0 items-center gap-2 text-sm font-semibold text-text-muted"
          >
            <template v-for="(item, index) in headerBreadcrumbs" :key="`${item.label}-${index}`">
              <ChevronRight v-if="index > 0" class="h-4 w-4 shrink-0 text-text-faint" />
              <ProjectQuickSwitcher
                v-if="item.projectSwitcher && workspaceId"
                breadcrumb
                :workspace-id="workspaceId"
                :current-project-id="projectId"
                :current-project-name="projectQuery.data.value?.name"
              />
              <RouterLink
                v-else-if="item.to"
                :to="item.to"
                class="admin-layout-breadcrumb-item truncate transition-colors hover:text-text"
              >
                {{ item.label }}
              </RouterLink>
              <span v-else class="admin-layout-breadcrumb-item truncate text-text-secondary">{{ item.label }}</span>
            </template>
          </nav>
        </div>

        <div class="admin-layout-user-menu flex shrink-0 items-center justify-end gap-2">
          <ThemeModeMenu />
          <UserMenu />
        </div>
      </header>

      <!-- Main Content Area -->
      <div class="relative flex min-h-0 flex-1 overflow-hidden">
        <main
          data-testid="admin-layout-main"
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

        <WorkspaceDock
          v-if="workspaceDockVisible && workspaceId"
          :workspace-id="workspaceId"
          :active-key="activeWorkspaceRouteKey"
          @navigate="handleDockNavigate"
        />
      </div>

      <OpenSourceFooter />
    </div>

    <LibraryDrawerHost :workspace-id="workspaceId" />

    <div data-testid="admin-layout-restricted-notice" class="admin-layout-restricted-notice" role="status">
      当前窗口宽度较小，已隐藏辅助面板。建议使用至少 960px 宽的桌面窗口进行完整创作。
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, provide, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { useQuery } from '@tanstack/vue-query'
import { ArrowLeft, ChevronRight } from '@lucide/vue'
import { getPage, getProject, getWorkspace } from '@/api/catalog'
import UserMenu from '@/components/nav/UserMenu.vue'
import ThemeModeMenu from '@/components/nav/ThemeModeMenu.vue'
import WorkspaceSwitcher from '@/components/nav/WorkspaceSwitcher.vue'
import ProjectQuickSwitcher from '@/components/nav/ProjectQuickSwitcher.vue'
import WorkspaceDock from '@/components/nav/WorkspaceDock.vue'
import AgentGlobalSidebar from '@/components/agent/AgentGlobalSidebar.vue'
import AgentFloatingTrigger from '@/components/agent/AgentFloatingTrigger.vue'
import OpenSourceFooter from '@/components/layout/OpenSourceFooter.vue'
import LibraryDrawerHost from '@/components/project/LibraryDrawerHost.vue'
import { UiButton } from '@/components/ui'
import { agentSidebarExpandedKey } from '@/composables/agent-sidebar-state'
import { componentAgentContextKey } from '@/composables/component-agent-context'
import { buildWorkspaceHomePath, type WorkspaceRouteKey } from '@/utils/workspace-routes'
import { parseWorkspaceIdFromPath, resolveGlobalReturnPath } from '@/utils/global-page-navigation'
import type { WorkspaceComponentItem } from '@/types/api'

const route = useRoute()
const router = useRouter()
const componentAgentSelection = ref<WorkspaceComponentItem | null>(null)
/** 工作空间默认展示内容助手，用户可通过面板头部按钮主动收起。 */
const agentSidebarExpanded = ref(true)

interface HeaderBreadcrumb {
  label: string
  to?: string
  projectSwitcher?: boolean
}

/**
 * 同步组件库页面当前选中组件，供全局智能体侧栏切换 component scope。
 * @param component 当前选中的工作空间组件；为空时回到工作空间组件库上下文
 */
function setComponentAgentSelection(component: WorkspaceComponentItem | null) {
  componentAgentSelection.value = component
}

/**
 * 处理右侧 Dock 的完整页面导航。
 * @param path 目标页面路径
 */
function handleDockNavigate(path: string): void {
  void router.push(path)
}

provide(componentAgentContextKey, {
  selectedComponent: componentAgentSelection,
  setSelectedComponent: setComponentAgentSelection,
})
provide(agentSidebarExpandedKey, agentSidebarExpanded)

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
const activeAgentSource = computed(() => {
  if (route.name === 'components') return 'editor-component-library'
  if (route.name === 'assets') return 'editor-asset-library'
  return 'editor-agent-sidebar'
})
const fullHeightPage = computed(() => Boolean(route.meta.fullHeight))
const sidebarsVisible = computed(() => !route.meta.hideSidebars)
const globalPageTitle = computed(() => typeof route.meta.globalPageTitle === 'string' ? route.meta.globalPageTitle : '')
const globalReturnPath = computed(() => resolveGlobalReturnPath(route.query.returnTo))
const globalReturnWorkspaceId = computed(() => parseWorkspaceIdFromPath(globalReturnPath.value))
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
    }
  },
  { immediate: true },
)

const workspaceQuery = useQuery(
  computed(() => ({
    queryKey: ['workspace', workspaceId.value ?? globalReturnWorkspaceId.value],
    queryFn: () => getWorkspace((workspaceId.value ?? globalReturnWorkspaceId.value) as number),
    enabled: !!(workspaceId.value ?? globalReturnWorkspaceId.value),
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
  if (!workspaceId.value) {
    return []
  }

  const breadcrumbs: HeaderBreadcrumb[] = []
  if (route.name === 'workspaceHome') {
    return [{ label: '空间首页' }]
  }

  breadcrumbs.push({
    label: '空间首页',
    to: buildWorkspaceHomePath(workspaceId.value),
  })

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
      label: projectQuery.data.value?.name ?? '正在加载项目...',
      projectSwitcher: true,
    })
  }

  if (pageId.value) {
    breadcrumbs.push({
      label: pageQuery.data.value?.title ?? '正在加载页面...',
    })
  }

  return breadcrumbs
})

const globalReturnLabel = computed(() => {
  const workspaceName = workspaceQuery.data.value?.name
  return workspaceName ? `返回 ${workspaceName}` : '返回创作空间'
})
const globalReturnTitle = computed(() => globalReturnPath.value
  ? `返回 ${globalReturnPath.value}`
  : '返回最近使用的工作空间')

/** 从全局管理页面返回进入前的位置；缺少可靠来源时交给根入口恢复最近空间。 */
function returnFromGlobalPage(): void {
  void router.push(globalReturnPath.value ?? '/')
}

onMounted(() => {
  window.addEventListener('agent:project-updated', handleGlobalAgentProjectUpdated)
})

onUnmounted(() => {
  window.removeEventListener('agent:project-updated', handleGlobalAgentProjectUpdated)
})
</script>

<style scoped>
/* 文件功能：定义后台工作台的响应式骨架、面板覆盖规则与受限窗口提示。 */
:global(body) {
  min-width: 0;
}

.admin-layout-agent {
  z-index: var(--ui-z-dock);
}

.admin-layout-header {
  z-index: var(--ui-z-sticky);
}

.admin-layout-breadcrumb-item {
  max-width: 11.25rem;
}

.admin-layout-restricted-notice {
  display: none;
}

@media (min-width: 1440px) {
  .admin-layout-header {
    padding-right: 1.5rem;
    padding-left: 1.5rem;
  }
}

@media (min-width: 1180px) and (max-width: 1439px) {
  .admin-layout-breadcrumb-item {
    max-width: 8rem;
  }
}

@media (min-width: 960px) and (max-width: 1179px) {
  .admin-layout-breadcrumb-item {
    max-width: 6rem;
  }
}

@media (max-width: 959px) {
  .admin-layout-agent,
  .admin-layout-breadcrumb,
  :deep(.admin-layout-context > [data-testid='project-quick-switcher']) {
    display: none;
  }

  .admin-layout {
    padding-bottom: 2.5rem;
  }

  .admin-layout-header {
    height: 3.25rem;
  }

  .admin-layout-context {
    padding-left: 0;
  }

  .admin-layout-workspace-hint {
    max-width: 12rem;
    overflow: hidden;
    white-space: nowrap;
  }

  .admin-layout-restricted-notice {
    position: absolute;
    right: 0;
    bottom: 0;
    left: 0;
    z-index: var(--ui-z-sticky);
    display: block;
    overflow: hidden;
    border-top: 1px solid rgb(var(--ui-border));
    background: rgb(var(--ui-surface-muted));
    padding: 0.5rem 0.75rem;
    color: rgb(var(--ui-text-secondary));
    font-size: 0.75rem;
    line-height: 1rem;
    text-align: center;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

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
