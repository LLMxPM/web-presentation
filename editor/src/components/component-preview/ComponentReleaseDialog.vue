<!-- 文件功能：承载组件草稿发布弹窗，负责填写发布名称与发布说明。 -->
<template>
  <BaseDialog
    :model-value="modelValue"
    title="发布组件版本"
    size="compact"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="space-y-4">
      <p class="text-sm leading-6 text-slate-500">
        发布会把当前草稿定版为新的不可变版本，发布后页面和其他组件才能通过版本号引用。
      </p>
      <BaseInput
        :model-value="releaseName"
        label="发布名称"
        placeholder="例如：稳定版、提审版"
        @update:model-value="emit('update:releaseName', String($event))"
      />
      <BaseInput
        :model-value="changeNote"
        type="textarea"
        label="发布说明"
        placeholder="说明本次发布的主要变化"
        :rows="3"
        @update:model-value="emit('update:changeNote', String($event))"
      />
    </div>

    <template #footer>
      <BaseButton variant="secondary" @click="emit('update:modelValue', false)">
        取消
      </BaseButton>
      <BaseButton variant="primary" :loading="loading" @click="emit('submit')">
        发布版本
      </BaseButton>
    </template>
  </BaseDialog>
</template>

<script setup lang="ts">
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import BaseInput from '@/components/ui/BaseInput.vue'

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

