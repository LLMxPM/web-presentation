<!-- 文件功能：承载页面编辑弹窗中的 Monaco 源码区域，并向外转发编辑与保存事件。 -->
<template>
  <section
    class="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border shadow-sm transition-colors duration-300"
    :class="isDark ? 'border-surface-inverse-raised bg-surface-inverse' : 'border-border bg-surface'">
    <div class="min-h-0 flex-1">
      <MonacoCodeEditor :model-value="props.modelValue" :language="props.editorLanguage"
        :auto-save-delay="props.autoSaveDelay" :completion-config="{ includeDefault: true }"
        :height="props.editorHeight" @update:model-value="emit('update:modelValue', $event)"
        @save="emit('save', $event)" @ready="emit('ready', $event)" @dirty-change="emit('dirty-change', $event)" />
    </div>
  </section>
</template>

<script setup lang="ts">
import MonacoCodeEditor from '@/components/editor/MonacoCodeEditor.vue'
import { useTheme } from '@/composables/useTheme'
import type {
  EditorLanguage,
  EditorSaveReason,
  MonacoEditorReadyPayload,
} from '@/types/monaco'

interface Props {
  modelValue: string
  editorLanguage: EditorLanguage
  autoSaveDelay: number
  editorHeight: string | number
}

const props = defineProps<Props>()

// 容器边框与底色跟随全局主题，与 Monaco 编辑器底色保持一致。
const { isDark } = useTheme()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  save: [{ reason: EditorSaveReason; value: string }]
  ready: [payload: MonacoEditorReadyPayload]
  'dirty-change': [dirty: boolean]
}>()
</script>
