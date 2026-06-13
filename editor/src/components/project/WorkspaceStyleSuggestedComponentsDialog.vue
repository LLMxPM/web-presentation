<!-- 文件功能：封装工作空间样式建议组件 API，复用通用建议组件选择弹窗。 -->
<template>
  <SuggestedComponentsDialog
    :model-value="modelValue"
    :workspace-id="workspaceId"
    :target-id="style?.id ?? null"
    :title="style ? `${style.name} · 建议组件` : '建议组件'"
    unavailable-text="当前没有可编辑的样式。"
    load-error-message="加载样式建议组件失败。"
    save-error-message="保存样式建议组件失败。"
    success-message="样式建议组件已保存。"
    :load-suggested-components="loadStyleSuggestedComponents"
    :update-suggested-components="updateStyleSuggestedComponents"
    @update:model-value="emit('update:modelValue', $event)"
    @saved="emit('saved', $event)"
  />
</template>

<script setup lang="ts">
import {
  getWorkspaceStyleSuggestedComponents,
  updateWorkspaceStyleSuggestedComponents,
} from '@/api/styles'
import SuggestedComponentsDialog from '@/components/project/SuggestedComponentsDialog.vue'
import type { SuggestedComponentsResponse, SuggestedComponentItem, WorkspaceStyleItem } from '@/types/api'

const props = defineProps<{
  modelValue: boolean
  workspaceId: number | null
  style: WorkspaceStyleItem | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: [items: SuggestedComponentItem[]]
}>()

/**
 * 读取当前样式建议组件，工作空间由父级上下文约束。
 * @param styleId 样式 ID
 */
function loadStyleSuggestedComponents(styleId: number): Promise<SuggestedComponentsResponse> {
  if (!props.workspaceId) {
    return Promise.resolve({ items: [] })
  }
  return getWorkspaceStyleSuggestedComponents(props.workspaceId, styleId)
}

/**
 * 覆盖保存当前样式建议组件。
 * @param styleId 样式 ID
 * @param componentIds 建议组件 ID，顺序即保存顺序
 */
function updateStyleSuggestedComponents(styleId: number, componentIds: number[]): Promise<SuggestedComponentsResponse> {
  if (!props.workspaceId) {
    return Promise.resolve({ items: [] })
  }
  return updateWorkspaceStyleSuggestedComponents(props.workspaceId, styleId, componentIds)
}
</script>
