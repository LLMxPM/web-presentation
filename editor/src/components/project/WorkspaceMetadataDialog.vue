<!-- 文件功能：提供工作空间基础信息编辑弹窗，统一承载名称与描述的修改表单。 -->
<template>
  <UiDialog :open="modelValue" title="编辑工作空间" size="compact" @update:open="handleVisibleChange">
    <div class="space-y-5">
      <UiFormField label="工作空间名称" required :error="errors.name">
        <template #default="field">
          <UiInput
            v-model="form.name"
            :input-id="field.inputId"
            :described-by="field.describedBy"
            :invalid="field.invalid"
            placeholder="给工作空间起个清晰的名字"
            required
          />
        </template>
      </UiFormField>

      <UiFormField label="工作空间描述">
        <template #default="field">
          <UiInput
            v-model="form.description"
            type="textarea"
            :input-id="field.inputId"
            :described-by="field.describedBy"
            placeholder="补充此工作空间的用途、归属或范围"
            :rows="4"
          />
        </template>
      </UiFormField>
    </div>

    <template #footer>
      <UiButton variant="ghost" @click="handleVisibleChange(false)">取消</UiButton>
      <UiButton variant="primary" :loading="loading" @click="handleSubmit">保存</UiButton>
    </template>
  </UiDialog>
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue'

import { UiButton, UiDialog, UiFormField, UiInput } from '@/components/ui'
import type { WorkspaceItem } from '@/types/api'

const props = withDefaults(defineProps<{
  modelValue: boolean
  workspace?: WorkspaceItem | null
  loading?: boolean
}>(), {
  workspace: null,
  loading: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submit: [payload: { name: string; description: string | null }]
}>()

const form = reactive({
  name: '',
  description: '',
})

const errors = reactive({
  name: '',
})

/**
 * 根据当前工作空间详情同步弹窗草稿，确保每次打开都看到最新值。
 * @param workspace 当前工作空间详情
 */
function syncForm(workspace: WorkspaceItem | null): void {
  form.name = workspace?.name ?? ''
  form.description = workspace?.description ?? ''
  errors.name = ''
}

/**
 * 向父层同步弹窗显隐状态。
 * @param value 弹窗显隐值
 */
function handleVisibleChange(value: boolean): void {
  emit('update:modelValue', value)
}

/**
 * 校验并提交工作空间元数据表单。
 */
function handleSubmit(): void {
  if (!form.name.trim()) {
    errors.name = '请输入工作空间名称'
    return
  }

  errors.name = ''
  emit('submit', {
    name: form.name.trim(),
    description: form.description.trim() ? form.description.trim() : null,
  })
}

watch(
  () => [props.modelValue, props.workspace] as const,
  ([visible, workspace]) => {
    if (visible) {
      syncForm(workspace)
    }
  },
  { immediate: true },
)
</script>

