<!-- 文件功能：提供页面复制到同工作空间其他项目的弹窗表单。 -->
<template>
  <BaseDialog
    :model-value="modelValue"
    title="复制到项目"
    width="640px"
    @update:model-value="handleDialogVisibleUpdate"
  >
    <div class="space-y-5">
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

      <div class="grid gap-4 md:grid-cols-2">
        <BaseInput v-model="titleDraft" label="新页面标题" placeholder="请输入标题" required />
        <BaseInput v-model="routeDraft" label="路由片段" placeholder="留空时使用新页面编码" />
      </div>

      <BaseInput
        v-model="summaryDraft"
        type="textarea"
        label="摘要说明"
        placeholder="可为空"
        :rows="3"
      />

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
        复制页面
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
import BaseInput from '@/components/ui/BaseInput.vue'
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

const ROUTE_SEGMENT_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]*$/

const props = withDefaults(defineProps<{
  modelValue: boolean
  page: PageItem | null
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
const titleDraft = ref('')
const summaryDraft = ref('')
const routeDraft = ref('')
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
  if (props.loading || projectsLoading.value) {
    return true
  }
  if (!props.page || !targetProjectId.value || !titleDraft.value.trim()) {
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

watch(() => props.page?.id, () => {
  if (props.modelValue) {
    resetForm()
  }
})

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
 * 重置弹窗草稿为当前页面基础信息。
 */
function resetForm(): void {
  targetProjectId.value = null
  parentRouteId.value = null
  routeGroups.value = []
  titleDraft.value = props.page?.title ?? ''
  summaryDraft.value = props.page?.summary ?? ''
  routeDraft.value = ''
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
 * 校验草稿并提交复制 payload。
 */
function handleSubmit(): void {
  if (!props.page || !targetProjectId.value) {
    Message.warning('请选择目标项目。')
    return
  }
  const title = titleDraft.value.trim()
  if (!title) {
    Message.warning('请输入新页面标题。')
    return
  }

  const route = routeDraft.value.trim()
  if (route && !ROUTE_SEGMENT_PATTERN.test(route)) {
    Message.warning('路由片段只能使用单段英文、数字、下划线或中划线。')
    return
  }
  if (joinRoute.value && routePlacement.value === 'group' && !parentRouteId.value) {
    Message.warning('请选择目标路由分组。')
    return
  }

  emit('submit', {
    target_project_id: targetProjectId.value,
    title,
    summary: summaryDraft.value.trim() || null,
    route_placement: routePlacement.value,
    parent_route_id: routePlacement.value === 'group' ? parentRouteId.value : null,
    route: route || null,
  })
}
</script>
