<!-- 文件功能：展示当前工作空间下的已归档项目列表，支持按名称搜索、恢复和删除项目。 -->
<template>
  <UiDialog :open="modelValue" title="已归档项目" size="standard" @update:open="handleDialogVisibleChange">
    <div class="flex flex-col gap-4">
      <SimpleSearchBar v-model="keyword" placeholder="按项目名称或编码搜索" />

      <div class="rounded-2xl border border-slate-200 bg-slate-50/50 overflow-hidden">
        <div class="flex items-center justify-between px-4 py-3 border-b border-slate-200 text-xs font-semibold text-slate-500">
          <span>共 {{ archivedProjects.length }} 个归档项目</span>
          <span>按归档时间从近到远排序</span>
        </div>

        <div v-if="query.isFetching.value" class="flex items-center justify-center py-12 text-sm text-slate-500">
          正在加载归档项目...
        </div>

        <div v-else-if="archivedProjects.length === 0" class="flex flex-col items-center justify-center py-12 gap-2 text-slate-500">
          <p class="text-sm font-semibold">{{ keyword.trim() ? '没有匹配的归档项目。' : '当前没有已归档项目。' }}</p>
          <p class="text-xs text-slate-400">恢复后的项目会重新出现在项目主页。</p>
        </div>

        <div v-else class="divide-y divide-slate-200">
          <div
            v-for="project in archivedProjects"
            :key="project.id"
            class="flex items-center justify-between gap-4 px-4 py-4 bg-white"
          >
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-3">
                <h4 class="text-sm font-semibold text-slate-900 truncate">{{ project.name }}</h4>
                <span class="text-[10px] font-bold text-slate-400 uppercase tracking-widest font-mono">{{ project.code }}</span>
              </div>
              <p class="mt-1 text-xs text-slate-500 line-clamp-2">
                {{ project.description || '此项目尚未添加具体功能说明' }}
              </p>
              <div class="mt-2 flex items-center gap-4 text-xs text-slate-400">
                <span>归档于 {{ formatDateTime(project.archived_at) }}</span>
                <span>更新于 {{ formatDateTime(project.updated_at) }}</span>
              </div>
            </div>

            <div class="flex shrink-0 items-center gap-2">
              <UiButton
                variant="secondary"
                :disabled="deletingProjectId === project.id"
                :loading="restoringProjectId === project.id"
                @click="handleRestoreProject(project.id)"
              >
                恢复
              </UiButton>
              <UiButton
                variant="danger"
                :disabled="restoringProjectId === project.id"
                :loading="deletingProjectId === project.id"
                @click="handleDeleteProject(project)"
              >
                删除
              </UiButton>
            </div>
          </div>
        </div>
      </div>
    </div>
  </UiDialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'

import { deleteProject, listProjects, updateProject } from '@/api/catalog'
import { getErrorMessage } from '@/api/http'
import type { ProjectItem } from '@/types/api'
import { createConfirm, Message } from '@/utils/message'
import { formatDateTime } from '@/utils/format'
import SimpleSearchBar from '@/components/patterns/SimpleSearchBar.vue'
import { UiButton, UiDialog } from '@/components/ui'

const props = defineProps<{
  modelValue: boolean
  workspaceId: number
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const queryClient = useQueryClient()
const keyword = ref('')
const restoringProjectId = ref<number | null>(null)
const deletingProjectId = ref<number | null>(null)

const query = useQuery(
  computed(() => ({
    queryKey: ['projects-by-ws', props.workspaceId, 'archived', keyword.value.trim()],
    queryFn: () =>
      listProjects({
        page: 1,
        page_size: 100,
        workspace_id: props.workspaceId,
        status: 'archived',
        keyword: keyword.value.trim(),
        sort_by: 'archived_at',
        sort_order: 'desc',
      }),
    enabled: props.modelValue && props.workspaceId > 0,
  })),
)

const archivedProjects = computed<ProjectItem[]>(() => query.data.value?.items ?? [])

const restoreMutation = useMutation({
  mutationFn: (projectId: number) => updateProject(projectId, { status: 'active' }),
})

const deleteMutation = useMutation({
  mutationFn: (projectId: number) => deleteProject(projectId),
})

watch(
  () => props.modelValue,
  (visible) => {
    if (!visible) {
      keyword.value = ''
      restoringProjectId.value = null
      deletingProjectId.value = null
    }
  },
)

/**
 * 关闭弹窗并同步给父组件，避免父子状态不一致。
 */
function handleDialogVisibleChange(value: boolean) {
  emit('update:modelValue', value)
}

/**
 * 将归档项目恢复为启用状态，并刷新主列表与归档列表缓存。
 */
async function handleRestoreProject(projectId: number) {
  restoringProjectId.value = projectId
  try {
    await restoreMutation.mutateAsync(projectId)
    await queryClient.invalidateQueries({ queryKey: ['projects-by-ws', props.workspaceId] })
    Message.success('项目已恢复。')
  } catch (error) {
    Message.error(getErrorMessage(error, '恢复项目失败。'))
  } finally {
    restoringProjectId.value = null
  }
}

/**
 * 二次确认后删除归档项目，并同步刷新启用与归档项目列表。
 * @param project 当前待删除的归档项目
 */
async function handleDeleteProject(project: ProjectItem) {
  const confirmed = await createConfirm(
    `删除后「${project.name}」将不再出现在项目列表中，确定删除吗？`,
    '删除归档项目',
  )
  if (!confirmed) {
    return
  }

  deletingProjectId.value = project.id
  try {
    await deleteMutation.mutateAsync(project.id)
    await queryClient.invalidateQueries({ queryKey: ['projects-by-ws', props.workspaceId] })
    Message.success('项目已删除。')
  } catch (error) {
    Message.error(getErrorMessage(error, '删除项目失败。'))
  } finally {
    deletingProjectId.value = null
  }
}
</script>

