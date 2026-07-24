<!-- 文件功能：承载组件草稿发布弹窗，负责填写发布名称与发布说明。 -->
<template>
  <UiDialog
    :open="modelValue"
    title="发布组件版本"
    size="compact"
    @update:open="emit('update:modelValue', $event)"
  >
    <div class="space-y-4">
      <p class="text-sm leading-6 text-slate-500">
        发布会把当前草稿定版为新的不可变版本，发布后页面和其他组件才能通过版本号引用。
      </p>
      <UiFormField label="发布名称">
        <UiInput
          :model-value="releaseName"
          placeholder="例如：稳定版、提审版"
          @update:model-value="emit('update:releaseName', String($event))"
        />
      </UiFormField>
      <UiFormField label="发布说明">
        <UiInput
          :model-value="changeNote"
          type="textarea"
          placeholder="说明本次发布的主要变化"
          :rows="3"
          @update:model-value="emit('update:changeNote', String($event))"
        />
      </UiFormField>
    </div>

    <template #footer>
      <UiButton variant="secondary" @click="emit('update:modelValue', false)">
        取消
      </UiButton>
      <UiButton variant="primary" :loading="loading" @click="emit('submit')">
        发布版本
      </UiButton>
    </template>
  </UiDialog>
</template>

<script setup lang="ts">
import UiButton from '@/components/ui/button/UiButton.vue'
import { UiDialog } from '@/components/ui'
import UiFormField from '@/components/ui/form-field/UiFormField.vue'
import UiInput from '@/components/ui/input/UiInput.vue'

defineProps<{
  modelValue: boolean
  releaseName: string
  changeNote: string
  loading: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'update:releaseName': [value: string]
  'update:changeNote': [value: string]
  submit: []
}>()
</script>

