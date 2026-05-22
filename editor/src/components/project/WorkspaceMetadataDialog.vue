<!-- 文件功能：提供工作空间基础信息编辑弹窗，统一承载名称与描述的修改表单。 -->
<template>
  <BaseDialog :model-value="modelValue" title="编辑工作空间" width="560px" @update:model-value="handleVisibleChange">
    <div class="space-y-5">
      <BaseInput v-model="form.name" label="工作空间名称" placeholder="给工作空间起个清晰的名字" required :error="errors.name" />

      <BaseInput v-model="form.description" type="textarea" label="工作空间描述" placeholder="补充此工作空间的用途、归属或范围" :rows="4" />
    </div>

    <template #footer>
      <BaseButton variant="ghost" @click="handleVisibleChange(false)">取消</BaseButton>
      <BaseButton variant="primary" :loading="loading" @click="handleSubmit">保存</BaseButton>
    </template>
  </BaseDialog>
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue'

import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import BaseInput from '@/components/ui/BaseInput.vue'
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
