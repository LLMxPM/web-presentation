<!-- 文件功能：项目名称与描述独立编辑弹窗，用于在页面列表页快速修改项目基础标识信息。 -->
<template>
  <BaseDialog :model-value="modelValue" title="修改项目基础信息" width="720px" @update:model-value="handleVisibleChange">
    <div v-if="project" class="space-y-5">
      <div class="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
        <p class="text-sm font-semibold text-slate-700">{{ project.code }}</p>
        <p class="mt-1 text-xs leading-5 text-slate-500">
          这里只修改项目名称与描述，不影响页面尺寸、菜单模式、导出按钮和主题配置。
        </p>
      </div>

      <BaseInput v-model="form.name" label="项目名称" placeholder="起一个具有辨识度的名称" required :error="errors.name" />

      <BaseInput v-model="form.description" type="textarea" label="项目描述" placeholder="概括此项目要阐述的内容" :rows="4" />
    </div>

    <div v-else class="py-10 text-center text-sm text-slate-400">
      当前没有可编辑的项目。
    </div>

    <template #footer>
      <BaseButton variant="ghost" @click="handleVisibleChange(false)">取消</BaseButton>
      <BaseButton variant="primary" :loading="loading" :disabled="!project" @click="handleSubmit">
        保存修改
      </BaseButton>
    </template>
  </BaseDialog>
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue'

import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import BaseInput from '@/components/ui/BaseInput.vue'
import type { ProjectItem } from '@/types/api'

const props = withDefaults(defineProps<{
  modelValue: boolean
  project: ProjectItem | null
  loading?: boolean
}>(), {
  loading: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submit: [payload: {
    name: string
    description: string | null
  }]
}>()

const form = reactive({
  name: '',
  description: '',
})

const errors = reactive({
  name: '',
})

/**
 * 根据当前项目刷新编辑草稿，确保每次打开弹窗都以最新后端状态为准。
 * @param project 当前项目
 */
function syncFormFromProject(project: ProjectItem | null): void {
  form.name = project?.name ?? ''
  form.description = project?.description ?? ''
  errors.name = ''
}

/**
 * 向父组件同步弹窗可见状态。
 * @param value 目标可见状态
 */
function handleVisibleChange(value: boolean): void {
  emit('update:modelValue', value)
}

/**
 * 校验并提交项目名称与描述。
 */
function handleSubmit(): void {
  if (!form.name.trim()) {
    errors.name = '请输入项目名称'
    return
  }

  errors.name = ''
  emit('submit', {
    name: form.name.trim(),
    description: form.description.trim() ? form.description.trim() : null,
  })
}

watch(
  () => [props.modelValue, props.project] as const,
  ([visible, project]) => {
    if (visible) {
      syncFormFromProject(project)
    }
  },
  { immediate: true },
)
</script>
