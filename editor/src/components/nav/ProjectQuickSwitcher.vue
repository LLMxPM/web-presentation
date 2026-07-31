<!-- 文件功能：提供工作空间内的项目快速切换入口，便于在顶部导航中直接进入项目页面列表。 -->
<template>
  <div class="project-switcher relative shrink-0" data-testid="project-quick-switcher">
    <UiPopover :open="dropdownVisible" side="bottom" align="start" :side-offset="8" content-class="!p-0 w-72 rounded-2xl shadow-xl" @update:open="dropdownVisible = $event">
      <template #trigger>
        <!-- Trigger：与相邻的 WorkspaceSwitcher 触发器保持同一套视觉 -->
        <button
          type="button"
          data-testid="project-quick-switcher-trigger"
          class="flex max-w-[220px] cursor-pointer select-none items-center gap-2 rounded-xl border border-border/50 bg-surface-muted px-4 py-2 shadow-sm transition-all hover:bg-border disabled:cursor-not-allowed disabled:opacity-50"
          :class="{ 'bg-border': dropdownVisible }"
          :disabled="!workspaceId"
          title="快速切换项目"
        >
          <FolderKanban class="h-4 w-4 shrink-0 text-accent" />
          <span class="min-w-0 truncate text-sm font-bold text-text">{{ triggerLabel }}</span>
          <ChevronDown
            class="h-4 w-4 shrink-0 text-text-disabled transition-transform duration-200"
            :class="{ 'rotate-180': dropdownVisible }"
          />
        </button>
      </template>

      <!-- Dropdown Content -->
      <div class="py-2">
        <div class="mb-1 flex items-center justify-between gap-3 border-b border-border-muted px-4 py-2">
          <span class="text-[11px] font-bold uppercase tracking-widest text-text-disabled">快速切换项目</span>
          <UiButton
            variant="ghost"
            size="xs"
            data-testid="project-quick-switcher-home"
            class="text-text-disabled hover:text-text-secondary"
            @click="goToWorkspaceHome"
          >
            项目列表
            <span class="rounded-full bg-surface-muted px-1.5 py-0.5 text-[10px] font-bold leading-none text-text-secondary">{{ projects.length }}</span>
          </UiButton>
        </div>

        <div class="max-h-72 overflow-y-auto px-1.5 py-1">
          <button
            v-for="project in projects"
            :key="project.id"
            type="button"
            data-testid="project-quick-switcher-item"
            class="mb-0.5 flex w-full cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm font-semibold transition-all"
            :class="project.id === currentProjectId ? 'bg-surface-selected text-accent-hover' : 'text-text-emphasis hover:bg-surface-hover'"
            @click="switchProject(project.id)"
          >
            <FolderKanban class="h-4 w-4 shrink-0" :class="project.id === currentProjectId ? 'text-accent-emphasis' : 'text-text-disabled'" />
            <span class="min-w-0 flex-1 truncate">{{ project.name }}</span>
            <Check v-if="project.id === currentProjectId" class="h-4 w-4 shrink-0 text-accent-emphasis" />
          </button>

          <div v-if="projectsLoading" class="px-4 py-5 text-center text-xs font-medium text-text-disabled">
            正在加载项目...
          </div>
          <div v-else-if="projects.length === 0" class="px-4 py-5 text-center text-xs font-medium text-text-disabled">
            当前空间暂无项目
          </div>
        </div>
      </div>
    </UiPopover>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useQuery } from '@tanstack/vue-query'
import { Check, ChevronDown, FolderKanban } from '@lucide/vue'

import { listProjects } from '@/api/catalog'
import { UiButton, UiPopover } from '@/components/ui'
import { buildProjectPagesPath, buildWorkspaceHomePath } from '@/utils/workspace-routes'

const props = defineProps<{
  workspaceId: number | null
  currentProjectId: number | null
  currentProjectName?: string | null
}>()

const router = useRouter()
const dropdownVisible = ref(false)

const projectsQuery = useQuery(
  computed(() => ({
    queryKey: ['projects-by-ws', props.workspaceId, 'active'],
    queryFn: () => listProjects({
      page: 1,
      page_size: 100,
      workspace_id: props.workspaceId as number,
      status: 'active',
    }),
    enabled: Number.isFinite(props.workspaceId),
  })),
)

const projects = computed(() => projectsQuery.data.value?.items ?? [])
const projectsLoading = computed(() => projectsQuery.isFetching.value && projects.value.length === 0)
const currentProject = computed(() => projects.value.find(project => project.id === props.currentProjectId) ?? null)
const triggerLabel = computed(() => currentProject.value?.name ?? props.currentProjectName ?? '选择项目')

/**
 * 关闭项目切换菜单。
 */
function closeDropdown(): void {
  dropdownVisible.value = false
}

/**
 * 跳转到工作空间项目总览。
 */
function goToWorkspaceHome(): void {
  if (!props.workspaceId) return
  closeDropdown()
  void router.push(buildWorkspaceHomePath(props.workspaceId))
}

/**
 * 切换到指定项目的页面列表。
 * @param projectId 目标项目 ID
 */
function switchProject(projectId: number): void {
  if (!props.workspaceId) return
  closeDropdown()
  if (projectId === props.currentProjectId) {
    return
  }
  void router.push(buildProjectPagesPath(props.workspaceId, projectId))
}

watch(
  () => props.workspaceId,
  () => closeDropdown(),
)

</script>
