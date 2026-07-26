<!-- 文件功能：承载页面版本快照创建弹窗，负责编辑快照名称并提交创建事件。 -->
<template>
  <UiDialog :open="props.modelValue" :title="`创建快照 · ${props.versionLabel}`" size="compact"
    @update:open="emit('update:modelValue', $event)">
    <div class="space-y-4">
      <p class="text-sm text-text-muted">
        为这个版本填写一个更容易识别的名称，后续在版本历史里会更好找。名称可留空。
      </p>
      <UiFormField label="快照名称">
        <UiInput
          :model-value="props.snapshotName"
          placeholder="例如：提审前定稿"
          @update:model-value="emit('update:snapshotName', String($event))"
        />
      </UiFormField>
    </div>

    <template #footer>
      <UiButton variant="secondary" @click="emit('update:modelValue', false)">
        取消
      </UiButton>
      <UiButton variant="primary" :loading="props.loading" @click="emit('submit')">
        创建快照
      </UiButton>
    </template>
  </UiDialog>
</template>

<script setup lang="ts">
import { UiButton, UiDialog, UiFormField, UiInput } from '@/components/ui'

interface Props {
  modelValue: boolean
  versionLabel: string
  snapshotName: string
  loading: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'update:snapshotName': [value: string]
  submit: []
}>()
</script>

