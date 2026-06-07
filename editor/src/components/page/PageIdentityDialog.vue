<!-- 文件功能：页面名称与描述独立编辑弹窗，用于维护页面基础信息。 -->
<template>
  <BaseDialog :model-value="modelValue" :title="page ? `编辑页面 · ${page.title}` : '编辑页面'" size="compact" @update:modelValue="handleVisibleChange">
    <div class="space-y-4">
      <BaseInput v-model="form.title" label="页面名称" placeholder="请输入页面名称" required :error="errors.title" />
      <BaseInput
        v-model="form.summary"
        type="textarea"
        label="页面描述"
        placeholder="补充页面用途、关键内容或使用约束"
        :rows="4"
      />
      <p v-if="page" class="text-xs leading-5 text-slate-400">
        页面编码：<span class="font-mono font-semibold uppercase">{{ page.code }}</span>
      </p>
    </div>

    <template #footer>
      <BaseButton variant="ghost" @click="handleVisibleChange(false)">取消</BaseButton>
      <BaseButton variant="primary" :loading="loading" @click="handleSubmit">保存</BaseButton>
    </template>
  </BaseDialog>
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue'

import type { PageItem } from '@/types/api'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import BaseInput from '@/components/ui/BaseInput.vue'

const props = defineProps<{
  modelValue: boolean
  page: PageItem | null
  loading?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submit: [payload: { title: string; summary: string | null }]
}>()

const form = reactive({
  title: '',
  summary: '',
})

const errors = reactive({
  title: '',
})

watch(
  () => [props.modelValue, props.page] as const,
  ([visible, page]) => {
    if (!visible || !page) {
      errors.title = ''
      return
    }

    form.title = page.title
    form.summary = page.summary ?? ''
    errors.title = ''
  },
  { immediate: true },
)

/**
 * 关闭弹窗并同步父组件状态。
 * @param value 最新显示状态
 */
function handleVisibleChange(value: boolean): void {
  emit('update:modelValue', value)
}

/**
 * 校验并提交页面基础信息。
 */
function handleSubmit(): void {
  const title = form.title.trim()
  if (!title) {
    errors.title = '请输入页面名称'
    return
  }

  errors.title = ''
  emit('submit', {
    title,
    summary: form.summary.trim() || null,
  })
}
</script>

