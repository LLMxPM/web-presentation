<!-- 文件功能：提供样式与项目共用的建议组件选择弹窗，维护有序已发布组件列表。 -->
<template>
  <BaseDialog
    :model-value="modelValue"
    :title="title"
    size="wide"
    body-preset="dense"
    @update:model-value="handleVisibleChange"
  >
    <SuggestedComponentsSelectorPanel
      v-if="workspaceId && targetId"
      v-model="selectedComponents"
      class="h-full"
      :workspace-id="workspaceId"
      :selected-title="selectedTitle"
      :loading="loading"
    />

    <div v-else class="py-10 text-center text-sm text-slate-400">
      {{ unavailableText }}
    </div>

    <template #footer>
      <BaseButton variant="ghost" @click="handleVisibleChange(false)">取消</BaseButton>
      <BaseButton variant="ghost" :disabled="loading || saving || !targetId" @click="loadDialogData">恢复当前值</BaseButton>
      <BaseButton variant="primary" :loading="saving" :disabled="!workspaceId || !targetId" @click="saveSelection">
        保存组件
      </BaseButton>
    </template>
  </BaseDialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

import { getErrorMessage } from '@/api/http'
import SuggestedComponentsSelectorPanel from '@/components/project/SuggestedComponentsSelectorPanel.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import type {
  SuggestedComponentItem,
  SuggestedComponentsResponse,
} from '@/types/api'
import { Message } from '@/utils/message'

const props = withDefaults(defineProps<{
  modelValue: boolean
  workspaceId: number | null
  targetId: number | null
  title: string
  selectedTitle?: string
  unavailableText: string
  loadSuggestedComponents: (targetId: number) => Promise<SuggestedComponentsResponse>
  updateSuggestedComponents: (targetId: number, componentIds: number[]) => Promise<SuggestedComponentsResponse>
  loadErrorMessage: string
  saveErrorMessage: string
  successMessage: string
}>(), {
  selectedTitle: '已选组件',
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: [items: SuggestedComponentItem[]]
}>()

const loading = ref(false)
const saving = ref(false)
const selectedComponents = ref<SuggestedComponentItem[]>([])

watch(
  () => [props.modelValue, props.workspaceId, props.targetId] as const,
  ([visible]) => {
    if (visible) {
      void loadDialogData()
    }
  },
  { immediate: true },
)

/**
 * 同步弹窗可见状态。
 * @param value 目标可见状态
 */
function handleVisibleChange(value: boolean): void {
  emit('update:modelValue', value)
}

/**
 * 读取当前对象已保存的建议组件。
 */
async function loadDialogData(): Promise<void> {
  if (!props.workspaceId || !props.targetId) {
    selectedComponents.value = []
    return
  }
  loading.value = true
  try {
    const response = await props.loadSuggestedComponents(props.targetId)
    selectedComponents.value = response.items
  } catch (error) {
    Message.error(getErrorMessage(error, props.loadErrorMessage))
  } finally {
    loading.value = false
  }
}

/**
 * 保存当前建议组件选择。
 */
async function saveSelection(): Promise<void> {
  if (!props.targetId) {
    return
  }
  if (selectedComponents.value.some(component => component.available === false)) {
    Message.warning('请先移除不可用的建议组件，再保存。')
    return
  }
  saving.value = true
  try {
    const componentIds = selectedComponents.value.map(component => component.id)
    const response = await props.updateSuggestedComponents(props.targetId, componentIds)
    selectedComponents.value = response.items
    emit('saved', response.items)
    handleVisibleChange(false)
    Message.success(props.successMessage)
  } catch (error) {
    Message.error(getErrorMessage(error, props.saveErrorMessage))
  } finally {
    saving.value = false
  }
}
</script>

