<!-- 文件功能：页面名称与描述独立编辑弹窗，用于维护页面基础信息。 -->
<template>
  <UiDialog :open="modelValue" :title="page ? `编辑页面 · ${page.title}` : '编辑页面'" size="compact" :panel-style="{ height: 'auto' }" @update:open="handleVisibleChange">
    <div class="space-y-4">
      <UiFormField label="页面名称" required :error="errors.title"><template #default="field"><UiInput v-model="form.title" placeholder="请输入页面名称" required :input-id="field.inputId" :described-by="field.describedBy" :invalid="field.invalid" /></template></UiFormField>
      <UiFormField label="页面描述"><template #default="field"><UiInput v-model="form.summary" type="textarea" placeholder="补充页面用途、关键内容或使用约束" :rows="4" :input-id="field.inputId" :described-by="field.describedBy" /></template></UiFormField>
      <p v-if="page" class="text-xs leading-5 text-text-disabled">
        页面编码：<span class="font-mono font-semibold uppercase">{{ page.code }}</span>
      </p>
    </div>

    <template #footer>
      <UiButton variant="ghost" @click="handleVisibleChange(false)">取消</UiButton>
      <UiButton variant="primary" :loading="loading" @click="handleSubmit">保存</UiButton>
    </template>
  </UiDialog>
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue'

import type { PageItem } from '@/types/api'
import { UiButton, UiDialog, UiFormField, UiInput } from '@/components/ui'

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

