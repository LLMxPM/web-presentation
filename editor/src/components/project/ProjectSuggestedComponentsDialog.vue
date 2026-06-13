<!-- 文件功能：封装项目建议组件快照 API，允许项目直接维护内容助手默认组件范围。 -->
<template>
  <SuggestedComponentsDialog
    :model-value="modelValue"
    :workspace-id="workspaceId"
    :target-id="projectId"
    :title="projectName ? `${projectName} · 建议组件` : '项目建议组件'"
    unavailable-text="当前没有可编辑的项目。"
    load-error-message="加载项目建议组件失败。"
    save-error-message="保存项目建议组件失败。"
    success-message="项目建议组件已保存。"
    :load-suggested-components="loadProjectSuggestedComponents"
    :update-suggested-components="updateProjectSuggestedComponentsSelection"
    @update:model-value="emit('update:modelValue', $event)"
    @saved="emit('saved', $event)"
  />
</template>

<script setup lang="ts">
import {
  getProjectSuggestedComponents,
  updateProjectSuggestedComponents,
} from '@/api/catalog'
import SuggestedComponentsDialog from '@/components/project/SuggestedComponentsDialog.vue'
import type { SuggestedComponentsResponse, SuggestedComponentItem } from '@/types/api'

defineProps<{
  modelValue: boolean
  projectId: number | null
  workspaceId: number | null
  projectName?: string | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: [items: SuggestedComponentItem[]]
}>()

/**
 * 读取项目当前建议组件快照。
 * @param projectId 项目 ID
 */
function loadProjectSuggestedComponents(projectId: number): Promise<SuggestedComponentsResponse> {
  return getProjectSuggestedComponents(projectId)
}

/**
 * 覆盖保存项目建议组件快照。
 * @param projectId 项目 ID
 * @param componentIds 建议组件 ID，顺序即保存顺序
 */
function updateProjectSuggestedComponentsSelection(
  projectId: number,
  componentIds: number[],
): Promise<SuggestedComponentsResponse> {
  return updateProjectSuggestedComponents(projectId, componentIds)
}
</script>
