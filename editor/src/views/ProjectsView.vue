<!-- 文件功能：展示当前工作空间下的启用项目入口，并提供项目创建、归档与归档列表查看能力。 -->
<template>
  <div data-testid="workspace-project-list" class="projects-view pb-12">
    <header class="mb-6 animate-in fade-in slide-in-from-top-4 duration-700">
      <PageTitleBar
        :title="workspaceQuery.data.value?.name ?? '正在加载工作空间...'"
      >
        <template #actions>
          <BaseButton variant="primary" :disabled="!workspaceDetails" @click="openCreateDialog">
            <template #icon>
              <Plus class="w-4 h-4" />
            </template>
            新增项目
          </BaseButton>
          <BaseButton variant="ghost" :disabled="!workspaceDetails" @click="openWorkspaceEditDialog">
            <template #icon>
              <Settings2 class="w-4 h-4" />
            </template>
            编辑工作空间
          </BaseButton>
          <button
            type="button"
            class="inline-flex items-center gap-2 px-4 py-2 rounded-xl border border-slate-200 bg-white text-sm font-semibold text-slate-600 shadow-sm transition-all hover:border-indigo-300 hover:text-indigo-600 hover:bg-indigo-50"
            @click="archivedDialogVisible = true"
          >
            <Archive class="w-4 h-4" />
            <span>已归档项目</span>
          </button>
        </template>
      </PageTitleBar>
    </header>

    <!-- 数据加载态 -->
    <div v-if="query.isFetching.value" class="flex flex-col items-center justify-center h-64 gap-4">
      <div class="w-12 h-12 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin"></div>
      <span class="text-slate-400 font-bold animate-pulse">正在获取项目数据...</span>
    </div>

    <!-- 卡片栅格区 -->
    <div v-else class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
      <div v-for="proj in projects" :key="proj.id" data-testid="project-card" @click="goToProject(proj.id)"
        class="card group hover:border-indigo-500 hover:-translate-y-1.5 transition-all duration-300 cursor-pointer flex flex-col p-7 relative">
        <div class="flex justify-between items-start mb-5">
          <div class="flex-1 min-w-0">
            <h3 class="text-xl font-bold text-slate-800 line-clamp-1 group-hover:text-indigo-600 transition-colors">{{
              proj.name }}</h3>
            <div class="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-1 font-mono"> {{ proj.code }}
            </div>
          </div>
          <div class="flex flex-col items-end gap-3 ml-4">
            <button
              type="button"
              class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-xs font-semibold text-slate-500 transition-all hover:border-amber-300 hover:bg-amber-50 hover:text-amber-700"
              :disabled="archivingProjectId === proj.id"
              @click.stop="handleArchiveProject(proj)"
            >
              <Archive class="w-3.5 h-3.5" />
              <span>{{ archivingProjectId === proj.id ? '归档中...' : '归档' }}</span>
            </button>
          </div>
        </div>

        <div class="flex-1 mb-6">
          <p class="text-sm text-slate-500 leading-relaxed line-clamp-2 italic font-medium">
            {{ proj.description || '此项目尚未添加具体功能说明' }}
          </p>
        </div>

        <div
          class="pt-5 border-t border-slate-50 flex items-center justify-between text-[11px] font-bold text-slate-400">
          <div class="flex items-center gap-2">
            <Calendar class="w-3.5 h-3.5" />
            <span>更新于 {{ formatDateTime(proj.updated_at) }}</span>
          </div>
          <ChevronRight class="w-4 h-4 opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all" />
        </div>
      </div>

      <!-- 新增项目卡片 -->
      <button @click="openCreateDialog"
        class="flex flex-col items-center justify-center p-8 border-2 border-dashed border-slate-200 rounded-2xl bg-slate-50/50 hover:bg-indigo-50 hover:border-indigo-400 hover:text-indigo-600 transition-all duration-300 group min-h-[220px]">
        <div
          class="w-16 h-16 rounded-full bg-white border border-slate-200 flex items-center justify-center mb-4 group-hover:bg-indigo-600 group-hover:text-white group-hover:scale-110 transition-all shadow-sm">
          <Plus class="w-8 h-8" />
        </div>
        <span class="text-lg font-bold">新增项目</span>
      </button>
    </div>

    <ProjectMetadataDialog
      v-model="dialogVisible"
      :workspace-id="workspaceId"
      :default-theme-key="workspaceDetails?.default_theme_key ?? null"
      :loading="saving"
      @submit="handleCreateProject"
    />
    <ArchivedProjectsDialog
      v-model="archivedDialogVisible"
      :workspace-id="workspaceId"
    />
    <WorkspaceMetadataDialog
      v-model="workspaceMetadataDialogVisible"
      :workspace="workspaceDetails"
      :loading="workspaceSaving"
      @submit="handleWorkspaceUpdate"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { Calendar, Plus, ChevronRight, Archive, Settings2 } from '@lucide/vue'

import { createProject, getWorkspace, listProjects, updateProject, updateWorkspace } from '@/api/catalog'
import { getErrorMessage } from '@/api/http'
import PageTitleBar from '@/components/layout/PageTitleBar.vue'
import ArchivedProjectsDialog from '@/components/project/ArchivedProjectsDialog.vue'
import ProjectMetadataDialog from '@/components/project/ProjectMetadataDialog.vue'
import WorkspaceMetadataDialog from '@/components/project/WorkspaceMetadataDialog.vue'
import { formatDateTime } from '@/utils/format'
import { createConfirm, Message } from '@/utils/message'
import BaseButton from '@/components/ui/BaseButton.vue'
import type { ProjectItem, ProjectMenuMode } from '@/types/api'
import { buildProjectPagesPath } from '@/utils/workspace-routes'

const route = useRoute()
const router = useRouter()
const queryClient = useQueryClient()

const workspaceId = computed(() => parseInt(route.params.workspaceId as string, 10))

const workspaceQuery = useQuery(
  computed(() => ({
    queryKey: ['workspace', workspaceId.value],
    queryFn: () => getWorkspace(workspaceId.value),
    enabled: !!workspaceId.value,
  })),
)

const query = useQuery(
  computed(() => ({
    queryKey: ['projects-by-ws', workspaceId.value, 'active'],
    queryFn: () => listProjects({ page: 1, page_size: 100, workspace_id: workspaceId.value, status: 'active' }),
    enabled: !!workspaceId.value,
  })),
)

const workspaceDetails = computed(() => workspaceQuery.data.value ?? null)
const projects = computed(() => query.data.value?.items ?? [])
const dialogVisible = ref(false)
const archivedDialogVisible = ref(false)
const saving = ref(false)
const archivingProjectId = ref<number | null>(null)
const workspaceMetadataDialogVisible = ref(false)
const workspaceSaving = ref(false)

function openCreateDialog() {
  dialogVisible.value = true
}

/**
 * 打开工作空间基础信息编辑弹窗。
 */
function openWorkspaceEditDialog(): void {
  workspaceMetadataDialogVisible.value = true
}

const saveMutation = useMutation({
  mutationFn: (payload: {
    name: string
    description: string | null
    status: 'active' | 'archived'
    page_width: number
    page_height: number
    base_font_size: string
    icon_default_stroke_width: number
    show_pdf_export_button: boolean
    menu_mode: ProjectMenuMode
    theme_key: string | null
    style_spec_markdown?: string
  }) => createProject({ ...payload, workspace_id: workspaceId.value }),
})

const archiveMutation = useMutation({
  mutationFn: (projectId: number) => updateProject(projectId, { status: 'archived' }),
})

/**
 * 创建新项目，并在成功后跳转到页面管理页继续操作。
 */
async function handleCreateProject(payload: {
  name: string
  description: string | null
  status: 'active' | 'archived'
  page_width: number
  page_height: number
  base_font_size: string
  icon_default_stroke_width: number
  show_pdf_export_button: boolean
  menu_mode: ProjectMenuMode
  theme_key: string | null
  style_spec_markdown?: string
}) {
  saving.value = true
  try {
    const res = await saveMutation.mutateAsync(payload)
    await queryClient.invalidateQueries({ queryKey: ['projects-by-ws', workspaceId.value] })
    dialogVisible.value = false
    Message.success('新项目已建立。')
    goToProject(res.id)
  } catch (error) {
    Message.error(getErrorMessage(error, '创建失败。'))
  } finally {
    saving.value = false
  }
}

/**
 * 将项目归档，并同步刷新启用列表与归档列表缓存。
 */
async function handleArchiveProject(project: ProjectItem) {
  const confirmed = await createConfirm(`归档后项目将从当前页面移入“已归档项目”列表，确定归档「${project.name}」吗？`, '归档项目')
  if (!confirmed) {
    return
  }

  archivingProjectId.value = project.id
  try {
    await archiveMutation.mutateAsync(project.id)
    await queryClient.invalidateQueries({ queryKey: ['projects-by-ws', workspaceId.value] })
    Message.success('项目已归档。')
  } catch (error) {
    Message.error(getErrorMessage(error, '归档项目失败。'))
  } finally {
    archivingProjectId.value = null
  }
}

function goToProject(id: number) {
  router.push(buildProjectPagesPath(workspaceId.value, id))
}

/**
 * 保存工作空间基础信息，并刷新当前工作空间详情。
 * @param payload 工作空间基础信息
 */
async function handleWorkspaceUpdate(payload: {
  name: string
  description: string | null
}) {
  if (!workspaceDetails.value) {
    return
  }

  workspaceSaving.value = true
  try {
    await updateWorkspace(workspaceDetails.value.id, payload)
    await queryClient.invalidateQueries({ queryKey: ['workspace', workspaceId.value] })
    window.dispatchEvent(new Event('workspace-list-updated'))
    workspaceMetadataDialogVisible.value = false
    Message.success('工作空间已更新。')
  } catch (error) {
    Message.error(getErrorMessage(error, '更新工作空间失败。'))
  } finally {
    workspaceSaving.value = false
  }
}

</script>
