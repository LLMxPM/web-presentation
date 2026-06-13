<!-- 文件功能：提供页面详情页的演讲者备注编辑面板，负责备注输入、字数提示和保存事件转发。 -->
<template>
  <section class="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
    <header class="flex shrink-0 items-center justify-between gap-4 border-b border-slate-200 bg-slate-50 px-6 py-4">
      <div class="min-w-0">
        <div class="flex items-center gap-2 text-sm font-semibold text-slate-900">
          <FileText class="h-4 w-4 text-indigo-500" />
          演讲者备注
        </div>
        <p class="mt-1 truncate text-xs text-slate-500" :title="pageTitle">
          {{ pageTitle }}
        </p>
      </div>

      <BaseButton
        variant="primary"
        size="sm"
        :disabled="disabled || !dirty || overLimit"
        :loading="loading"
        @click="emit('save')"
      >
        <Save class="h-3.5 w-3.5" />
        保存备注
      </BaseButton>
    </header>

    <div class="flex min-h-0 flex-1 flex-col gap-3 p-6">
      <textarea
        :value="modelValue"
        class="min-h-0 flex-1 resize-none rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm leading-6 text-slate-800 outline-none transition focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400"
        placeholder="记录演讲时只给自己看的提示、转场话术或需要强调的数据。备注会在 Runtime 演讲模式控制台展示，不会出现在观众窗口。"
        :disabled="disabled"
        @input="handleInput"
      ></textarea>

      <div class="flex items-center justify-between gap-4 text-xs">
        <span class="text-slate-500">
          纯文本备注会保留换行；空白内容保存后视为未填写。
        </span>
        <span :class="overLimit ? 'font-semibold text-red-500' : 'text-slate-400'">
          {{ noteLength }} / {{ maxLength }}
        </span>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { FileText, Save } from '@lucide/vue'

import BaseButton from '@/components/ui/BaseButton.vue'

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

/**
 * 同步文本域输入到父组件，父组件负责持久化。
 * @param event 输入事件
 */
function handleInput(event: Event): void {
  const target = event.target as HTMLTextAreaElement
  emit('update:modelValue', target.value)
}
</script>
