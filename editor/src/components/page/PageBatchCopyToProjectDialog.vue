<!-- 文件功能：提供多页面批量复制到同工作空间其他项目的弹窗表单。 -->
<template>
  <BaseDialog
    :model-value="modelValue"
    title="批量复制到项目"
    size="standard"
    @update:model-value="handleDialogVisibleUpdate"
  >
    <div class="space-y-5">
      <div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-600">
        已选择 {{ pages.length }} 个页面
      </div>

      <div class="space-y-1.5">
        <label class="ml-1 text-sm font-semibold text-slate-700">
          目标项目
          <span class="text-red-500">*</span>
        </label>
        <SearchableSelect
          v-model="targetProjectId"
          :options="projectOptions"
          :disabled="loading || projectsLoading || projectOptions.length === 0"
          :placeholder="projectsLoading ? '项目加载中...' : '选择目标项目'"
          empty-text="没有可复制的目标项目。"
        />
      </div>

      <label class="flex items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-semibold text-slate-700">
        <input
          v-model="joinRoute"
          type="checkbox"
          class="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
          :disabled="loading"
        >
        复制后加入目标项目路由
      </label>

      <div v-if="joinRoute" class="space-y-4 rounded-lg border border-slate-200 bg-white p-4">
        <div class="grid grid-cols-2 gap-2">
          <button
            type="button"
            class="inline-flex h-10 items-center justify-center rounded-lg border text-sm font-semibold transition"
            :class="routePlacement === 'root'
              ? 'border-indigo-500 bg-indigo-50 text-indigo-700'
              : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'"
            @click="routePlacement = 'root'"
          >
            顶层路由
          </button>
          <button
            type="button"
            class="inline-flex h-10 items-center justify-center rounded-lg border text-sm font-semibold transition"
            :class="routePlacement === 'group'
              ? 'border-indigo-500 bg-indigo-50 text-indigo-700'
              : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'"
            @click="routePlacement = 'group'"
          >
            目标分组
          </button>
        </div>

        <div v-if="routePlacement === 'group'" class="space-y-1.5">
          <label class="ml-1 text-sm font-semibold text-slate-700">
            路由分组
            <span class="text-red-500">*</span>
          </label>
          <SearchableSelect
            v-model="parentRouteId"
            :options="groupOptions"
            :disabled="loading || routeOptionsLoading || !targetProjectId || groupOptions.length === 0"
            :placeholder="routeOptionsLoading ? '分组加载中...' : '选择目标分组'"
            empty-text="目标项目暂无分组。"
          />
        </div>
      </div>
    </div>

    <template #footer>
      <BaseButton variant="ghost" :disabled="loading" @click="closeDialog">取消</BaseButton>
      <BaseButton variant="primary" :loading="loading" :disabled="submitDisabled" @click="handleSubmit">
        批量复制
      </BaseButton>
    </template>
  </BaseDialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { getProjectRoutes, listProjects } from '@/api/catalog'
import { getErrorMessage } from '@/api/http'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import SearchableSelect from '@/components/ui/SearchableSelect.vue'
import type { SelectOption } from '@/components/ui/select'
import type {
  PageCopyRoutePlacement,
  PageCopyToProjectPayload,
  PageItem,
  ProjectItem,
  ProjectRouteTreeItem,
} from '@/types/api'
import { Message } from '@/utils/message'

const props = withDefaults(defineProps<{
  modelValue: boolean
  pages: PageItem[]
  workspaceId: number
  currentProjectId: number
  loading?: boolean
}>(), {
  loading: false,
})

const emit = defineEmits<{
  'update:modelValue': [visible: boolean]
  submit: [payload: PageCopyToProjectPayload]
}>()

const projectsLoading = ref(false)
const routeOptionsLoading = ref(false)
const projects = ref<ProjectItem[]>([])
const routeGroups = ref<ProjectRouteTreeItem[]>([])
const targetProjectId = ref<number | null>(null)
const parentRouteId = ref<number | null>(null)
const joinRoute = ref(false)
const routePlacement = ref<PageCopyRoutePlacement>('none')
let routeLoadSeq = 0

const projectOptions = computed<SelectOption[]>(() => projects.value.map(project => ({
  label: project.name,
  value: project.id,
  description: project.code,
  keywords: [project.code, project.name],
})))

const groupOptions = computed<SelectOption[]>(() => routeGroups.value.map(group => ({
  label: group.display_title || group.group_title || group.route,
  value: group.id,
  description: `/${group.route}`,
  keywords: [group.route, group.group_title ?? '', group.display_title],
})))

const submitDisabled = computed(() => {
  if (props.loading || projectsLoading.value || props.pages.length === 0) {
    return true
  }
  if (!targetProjectId.value) {
    return true
  }
  if (joinRoute.value && routePlacement.value === 'group' && !parentRouteId.value) {
    return true
  }
  return false
})

watch(
  () => props.modelValue,
  (visible) => {
    if (!visible) {
      return
    }
    resetForm()
    void loadProjects()
  },
  { immediate: true },
)

watch(targetProjectId, () => {
  parentRouteId.value = null
  routeGroups.value = []
  if (targetProjectId.value) {
    void loadRouteGroups(targetProjectId.value)
  }
})

watch(joinRoute, (enabled) => {
  routePlacement.value = enabled ? 'root' : 'none'
  if (!enabled) {
    parentRouteId.value = null
  }
})

/**
 * 重置批量复制表单草稿。
 */
function resetForm(): void {
  targetProjectId.value = null
  parentRouteId.value = null
  routeGroups.value = []
  joinRoute.value = false
  routePlacement.value = 'none'
}

/**
 * 加载同工作空间下除当前项目外的 active 项目。
 */
async function loadProjects(): Promise<void> {
  if (!props.workspaceId) {
    projects.value = []
    return
  }

  projectsLoading.value = true
  try {
    const response = await listProjects({
      page: 1,
      page_size: 100,
      workspace_id: props.workspaceId,
      status: 'active',
    })
    projects.value = response.items.filter(project => (
      project.id !== props.currentProjectId
      && project.workspace_id === props.workspaceId
      && project.status === 'active'
    ))
    if (projects.value.length === 1) {
      targetProjectId.value = projects.value[0].id
    }
  } catch (error) {
    Message.error(getErrorMessage(error, '加载目标项目失败。'))
    projects.value = []
  } finally {
    projectsLoading.value = false
  }
}

/**
 * 读取目标项目路由树中的分组节点。
 * @param projectId 目标项目 ID
 */
async function loadRouteGroups(projectId: number): Promise<void> {
  const seq = ++routeLoadSeq
  routeOptionsLoading.value = true
  try {
    const response = await getProjectRoutes(projectId)
    if (seq !== routeLoadSeq) {
      return
    }
    routeGroups.value = response.routes.filter(route => route.route_type === 'group')
  } catch (error) {
    if (seq === routeLoadSeq) {
      Message.error(getErrorMessage(error, '加载目标项目路由分组失败。'))
      routeGroups.value = []
    }
  } finally {
    if (seq === routeLoadSeq) {
      routeOptionsLoading.value = false
    }
  }
}

/**
 * 将 BaseDialog 可见性事件转发给父组件。
 * @param visible 是否显示弹窗
 */
function handleDialogVisibleUpdate(visible: boolean): void {
  emit('update:modelValue', visible)
}

function closeDialog(): void {
  emit('update:modelValue', false)
}

/**
 * 校验草稿并提交批量复制 payload。
 */
function handleSubmit(): void {
  if (!targetProjectId.value) {
    Message.warning('请选择目标项目。')
    return
  }
  if (joinRoute.value && routePlacement.value === 'group' && !parentRouteId.value) {
    Message.warning('请选择目标路由分组。')
    return
  }

  emit('submit', {
    target_project_id: targetProjectId.value,
    route_placement: routePlacement.value,
    parent_route_id: routePlacement.value === 'group' ? parentRouteId.value : null,
    route: null,
  })
}
</script>

