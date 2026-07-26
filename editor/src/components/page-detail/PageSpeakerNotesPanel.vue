<!-- 文件功能：提供页面详情页的演讲者备注编辑面板，负责备注输入、字数提示和保存事件转发。 -->
<template>
  <ToolPanel class="h-full min-h-0" :scroll-body="false">
    <template #header>
      <div class="flex items-center justify-between gap-4">
      <div class="min-w-0">
        <div class="flex items-center gap-2 text-sm font-semibold text-text-strong">
          <FileText class="h-4 w-4 text-accent-emphasis" />
          演讲者备注
        </div>
        <p class="mt-1 truncate text-xs text-text-muted" :title="pageTitle">
          {{ pageTitle }}
        </p>
      </div>

      <UiButton
        variant="primary"
        size="sm"
        :disabled="disabled || !dirty || overLimit"
        :loading="loading"
        @click="emit('save')"
      >
        <Save class="h-3.5 w-3.5" />
        保存备注
      </UiButton>
      </div>
    </template>

    <div class="flex h-full min-h-0 flex-col gap-3">
      <UiInput
        type="textarea"
        textarea-mode="fill"
        :model-value="modelValue"
        class="leading-6"
        placeholder="记录演讲时只给自己看的提示、转场话术或需要强调的数据。备注会在 Runtime 演讲模式控制台展示，不会出现在观众窗口。"
        :disabled="disabled"
        @update:model-value="emit('update:modelValue', $event)"
      />

      <div class="flex items-center justify-between gap-4 text-xs">
        <span class="text-text-muted">
          纯文本备注会保留换行；空白内容保存后视为未填写。
        </span>
        <span :class="overLimit ? 'font-semibold text-danger' : 'text-text-disabled'">
          {{ noteLength }} / {{ maxLength }}
        </span>
      </div>
    </div>
  </ToolPanel>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { FileText, Save } from '@lucide/vue'

import ToolPanel from '@/components/patterns/ToolPanel.vue'
import { UiButton, UiInput } from '@/components/ui'

const props = defineProps<{
  modelValue: string
  pageTitle: string
  dirty: boolean
  loading?: boolean
  disabled?: boolean
  maxLength?: number
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  save: []
}>()

const maxLength = computed(() => props.maxLength ?? 10000)
const noteLength = computed(() => props.modelValue.length)
const overLimit = computed(() => noteLength.value > maxLength.value)

</script>
