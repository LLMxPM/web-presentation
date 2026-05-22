<!-- 文件功能：提供工作空间内的项目快速切换入口，便于在顶部导航中直接进入项目页面列表。 -->
<template>
  <div class="project-switcher relative shrink-0" v-click-outside="closeDropdown" data-testid="project-quick-switcher">
    <button
      type="button"
      data-testid="project-quick-switcher-trigger"
      class="flex max-w-[220px] items-center gap-2 rounded-xl border border-slate-200/70 bg-white px-3 py-2 text-sm font-semibold text-slate-700 shadow-sm transition-all hover:border-slate-300 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
      :class="{ 'border-indigo-200 bg-indigo-50 text-indigo-700': dropdownVisible }"
      :disabled="!workspaceId"
      title="快速切换项目"
      @click="toggleDropdown"
    >
      <FolderKanban class="h-4 w-4 shrink-0 text-indigo-500" />
      <span class="truncate">{{ triggerLabel }}</span>
      <ChevronDown
        class="h-4 w-4 shrink-0 text-slate-400 transition-transform duration-200"
        :class="{ 'rotate-180': dropdownVisible }"
      />
    </button>

    <Transition name="fade-scale">
      <div
        v-if="dropdownVisible"
        class="absolute left-0 z-50 mt-2 w-72 rounded-2xl border border-slate-200 bg-white py-2 shadow-xl"
      >
        <div class="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-2">
          <span class="text-[11px] font-bold uppercase tracking-widest text-slate-400">快速切换项目</span>
          <span class="text-[11px] font-medium text-slate-400">{{ projects.length }} 个项目</span>
        </div>

        <div class="max-h-72 overflow-y-auto px-1.5 py-1">
          <button
            type="button"
            data-testid="project-quick-switcher-home"
            class="project-item"
            :class="!currentProjectId ? 'project-item-active' : 'project-item-idle'"
            @click="goToWorkspaceHome"
          >
            <LayoutDashboard class="h-4 w-4 shrink-0" />
            <span class="min-w-0 flex-1 truncate text-left">项目总览</span>
            <Check v-if="!currentProjectId" class="h-4 w-4 shrink-0" />
          </button>

          <button
            v-for="project in projects"
            :key="project.id"
            type="button"
            data-testid="project-quick-switcher-item"
            class="project-item"
            :class="project.id === currentProjectId ? 'project-item-active' : 'project-item-idle'"
            @click="switchProject(project.id)"
          >
            <FolderKanban class="h-4 w-4 shrink-0" />
            <span class="min-w-0 flex-1 truncate text-left">{{ project.name }}</span>
            <Check v-if="project.id === currentProjectId" class="h-4 w-4 shrink-0" />
          </button>

          <div v-if="projectsLoading" class="px-4 py-5 text-center text-xs font-medium text-slate-400">
            正在加载项目...
          </div>
          <div v-else-if="projects.length === 0" class="px-4 py-5 text-center text-xs font-medium text-slate-400">
            当前空间暂无项目
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, type Directive } from 'vue'
import { useRouter } from 'vue-router'
import { useQuery } from '@tanstack/vue-query'
import { Check, ChevronDown, FolderKanban, LayoutDashboard } from 'lucide-vue-next'

import { listProjects } from '@/api/catalog'
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
    queryKey: ['workspace-projects-quick-switcher', props.workspaceId],
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
 * 展开或收起项目切换菜单。
 */
function toggleDropdown(): void {
  dropdownVisible.value = !dropdownVisible.value
}

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

interface ClickOutsideElement extends HTMLElement {
  __projectClickOutside__?: EventListener
}

/**
 * 点击组件外部时关闭下拉菜单。
 */
const vClickOutside: Directive<ClickOutsideElement, () => void> = {
  mounted(el, binding) {
    const handler: EventListener = (event) => {
      if (!(el === event.target || el.contains(event.target as Node))) {
        binding.value()
      }
    }
    el.__projectClickOutside__ = handler
    document.body.addEventListener('click', handler)
  },
  unmounted(el) {
    if (el.__projectClickOutside__) {
      document.body.removeEventListener('click', el.__projectClickOutside__)
    }
  },
}
</script>

<style scoped>
.project-item {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 0.75rem;
  border-radius: 0.75rem;
  padding: 0.625rem 0.75rem;
  font-size: 0.875rem;
  font-weight: 700;
  transition: all 0.16s ease;
}

.project-item-idle {
  color: rgb(51 65 85);
}

.project-item-idle:hover {
  background: rgb(248 250 252);
  color: rgb(30 41 59);
}

.project-item-active {
  background: rgb(238 242 255);
  color: rgb(79 70 229);
}

.fade-scale-enter-active,
.fade-scale-leave-active {
  transition: all 0.18s ease-out;
}

.fade-scale-enter-from,
.fade-scale-leave-to {
  opacity: 0;
  transform: scale(0.97) translateY(-6px);
}
</style>
