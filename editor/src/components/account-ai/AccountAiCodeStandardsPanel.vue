<!-- 文件功能：提供页面与组件代码规范的自定义编辑和恢复默认界面。 -->
<template>
  <div v-if="selectedStandard" class="code-standard-editor flex h-full min-h-0 w-full flex-col gap-4">
    <section class="flex min-h-0 flex-1 flex-col overflow-hidden rounded-ui-lg border border-border bg-surface">
      <header class="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-border-muted px-4 py-3">
        <div class="min-w-0 flex-1">
          <UiTabs
            :model-value="selectedType"
            :items="standardTypes"
            class="min-w-0"
            list-class="border-b-0"
            content-class="hidden"
            @update:model-value="emit('changeType', $event as StandardType)"
          />
          <p class="mt-1 block w-full text-xs leading-5 text-text-muted">
            当前{{ selectedStandard.customized ? '使用账号自定义代码规范' : '使用系统默认代码规范' }}。保存后会完整替换当前类型的系统默认内容，支持 Markdown。
          </p>
        </div>
        <span
          class="shrink-0 rounded-full px-2 py-1 text-[11px] font-semibold"
          :class="selectedStandard.customized ? 'bg-ai-muted text-ai-strong' : 'bg-surface-muted text-text-secondary'"
        >
          {{ selectedStandard.customized ? '账号自定义' : '系统默认' }}
        </span>
      </header>

      <div class="min-h-0 flex-1 p-3 sm:p-4">
        <label for="code-standard-editor" class="sr-only">代码规范</label>
        <UiInput
          input-id="code-standard-editor"
          class="code-standard-textarea"
          :model-value="draft"
          type="textarea"
          textarea-mode="fill"
          :rows="20"
          placeholder="输入页面或组件代码规范"
          @update:model-value="emit('updateDraft', String($event))"
        />
      </div>
    </section>

    <footer class="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t border-border-muted py-3">
      <p class="text-xs text-text-muted">{{ dirty ? '修改尚未保存，离开前请先保存。' : '当前内容已保存。' }}</p>
      <div class="flex shrink-0 items-center gap-2">
        <UiButton variant="ghost" :loading="saving" @click="emit('restore')">恢复系统默认</UiButton>
        <UiButton :disabled="!dirty" :loading="saving" @click="emit('save')">保存规范</UiButton>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { UiButton, UiInput, UiTabs } from '@/components/ui'
import type { AgentCodeStandardConfigItem } from '@/types/api'

type StandardType = AgentCodeStandardConfigItem['standard_type']

defineProps<{
  selectedType: StandardType
  selectedStandard: AgentCodeStandardConfigItem | null
  draft: string
  dirty: boolean
  saving: boolean
}>()

const emit = defineEmits<{
  changeType: [value: StandardType]
  updateDraft: [value: string]
  save: []
  restore: []
}>()

const standardTypes: Array<{ label: string; value: StandardType }> = [
  { label: '页面规范', value: 'page' },
  { label: '组件规范', value: 'component' },
]

</script>

<style scoped>
:deep(.code-standard-textarea) { min-height: 0; resize: none; line-height: 1.75; }
</style>
