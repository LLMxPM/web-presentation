<!-- 文件功能：项目路由配置弹窗，负责加载并编辑项目的结构化路由树。 -->
<template>
  <BaseDialog :model-value="modelValue" :title="project ? `路由配置 · ${project.name}` : '路由配置'" width="1240px"
    @update:model-value="handleVisibleChange">
    <div v-if="project" class="space-y-3">

      <ProjectRouteEditor v-model="draftRoutes" :pages="routePages" :icons="routeIcons" :loading="routeEditorLoading" />
    </div>

    <div v-else class="py-10 text-center text-sm text-slate-400">
      当前没有可编辑的项目。
    </div>

    <template #footer>
      <BaseButton variant="ghost" @click="handleVisibleChange(false)">取消</BaseButton>
      <BaseButton variant="primary" :loading="loading" :disabled="!project" @click="handleSave">
        保存路由
      </BaseButton>
    </template>
  </BaseDialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

import { listWorkspaceAssets } from '@/api/assets'
import { getProjectRoutes, listPages } from '@/api/catalog'
import { getErrorMessage } from '@/api/http'
import ProjectRouteEditor from '@/components/project/ProjectRouteEditor.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import type { AssetResponse, PageItem, ProjectItem, ProjectRouteItemWrite } from '@/types/api'
import { mapRouteTreeToWriteItems, validateProjectRoutes } from '@/utils/project-route'
import { Message } from '@/utils/message'

const props = withDefaults(defineProps<{
  modelValue: boolean
  project: ProjectItem | null
  loading?: boolean
}>(), {
  loading: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  save: [{
    routes: ProjectRouteItemWrite[]
  }]
}>()

const routePages = ref<PageItem[]>([])
const routeIcons = ref<AssetResponse[]>([])
const draftRoutes = ref<ProjectRouteItemWrite[]>([])
const routeEditorLoading = ref(false)
const routeLoadToken = ref(0)

/**
 * 向父组件同步弹窗开关状态。
 */
function handleVisibleChange(value: boolean): void {
  emit('update:modelValue', value)
}

/**
 * 提交当前路由树草稿。
 */
function handleSave(): void {
  const validationErrors = validateProjectRoutes(draftRoutes.value)
  if (validationErrors.length > 0) {
    Message.error(validationErrors[0])
    return
  }

  emit('save', {
    routes: draftRoutes.value,
  })
}

/**
 * 加载项目路由编辑所需的页面列表、图标资源和当前路由树。
 * @param project 当前项目，用于读取项目 ID 和工作空间 ID
 */
async function loadRouteEditorData(project: ProjectItem): Promise<void> {
  const currentToken = routeLoadToken.value + 1
  routeLoadToken.value = currentToken
  routeEditorLoading.value = true

  try {
    const [pagesResponse, routesResponse, iconResponse] = await Promise.all([
      listPages({ page: 1, page_size: 100, project_id: project.id }),
      getProjectRoutes(project.id),
      listWorkspaceAssets(project.workspace_id, { assetType: 'icon', page: 1, page_size: 100 }),
    ])

    if (routeLoadToken.value !== currentToken) {
      return
    }

    routePages.value = pagesResponse.items
    routeIcons.value = iconResponse.items
    draftRoutes.value = mapRouteTreeToWriteItems(routesResponse.routes)
  } catch (error) {
    if (routeLoadToken.value !== currentToken) {
      return
    }

    routePages.value = []
    routeIcons.value = []
    draftRoutes.value = []
    Message.error(getErrorMessage(error, '加载项目路由数据失败。'))
  } finally {
    if (routeLoadToken.value === currentToken) {
      routeEditorLoading.value = false
    }
  }
}

watch(
  () => [props.modelValue, props.project] as const,
  ([visible, currentProject]) => {
    if (visible && currentProject) {
      void loadRouteEditorData(currentProject)
    }
  },
  { immediate: true },
)
</script>
