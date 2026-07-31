<!-- 文件功能：提供代码与 JSON 文本的放大编辑弹窗，复用 Monaco 编辑器并与父层内容实时双向同步。 -->
<template>
  <UiDialog
    :open="open"
    :title="title"
    :description="description"
    size="canvas"
    body-preset="editor"
    :z-index="zIndex"
    @update:open="emit('update:open', $event)"
  >
    <template #header-extra>
      <UiButton variant="ghost" size="sm" class="text-text-secondary" @click="formatContent">
        <WandSparkles class="h-3.5 w-3.5" />
        格式化
      </UiButton>
    </template>
    <div class="flex h-full min-h-0 flex-col gap-2">
      <div class="min-h-0 flex-1 overflow-hidden rounded-xl border border-border bg-surface focus-within:border-border-focus/50 focus-within:ring-2 focus-within:ring-border-focus/20">
        <MonacoCodeEditor
          :model-value="modelValue"
          :language="language"
          :auto-save-delay="0"
          height="100%"
          @update:model-value="emit('update:modelValue', $event)"
          @ready="editorReady = $event"
        />
      </div>
      <p v-if="error" class="shrink-0 text-xs font-semibold text-danger">{{ error }}</p>
    </div>
  </UiDialog>
</template>

<script setup lang="ts">
import { shallowRef } from 'vue'
import { WandSparkles } from '@lucide/vue'

import MonacoCodeEditor from '@/components/editor/MonacoCodeEditor.vue'
import { UiButton, UiDialog } from '@/components/ui'
import type { EditorLanguage, MonacoEditorReadyPayload } from '@/types/monaco'

const props = withDefaults(defineProps<{
  open: boolean
  modelValue: string
  title: string
  description?: string
  language?: EditorLanguage
  /** 父层错误提示；放大编辑期间沿用父层既有校验结果。 */
  error?: string
  /** 放大弹窗可能叠加在 workbench 级弹窗之上，默认使用更高层级。 */
  zIndex?: string | number
}>(), {
  language: 'json',
  zIndex: 1200,
})

const emit = defineEmits<{
  'update:open': [value: boolean]
  'update:modelValue': [value: string]
}>()

const editorReady = shallowRef<MonacoEditorReadyPayload | null>(null)

/**
 * 格式化当前内容：优先使用 Monaco 内置格式化动作，JSON 回退为两空格重序列化；
 * 非法 JSON 时保持原文，由父层既有校验给出提示。
 */
async function formatContent(): Promise<void> {
  const action = editorReady.value?.editor.getAction('editor.action.formatDocument')
  if (action) {
    await action.run()
    return
  }
  if (props.language !== 'json') return
  try {
    emit('update:modelValue', JSON.stringify(JSON.parse(props.modelValue), null, 2))
  } catch {
    /* 非法 JSON 不做格式化，错误由父层 error 提示展示 */
  }
}
</script>
