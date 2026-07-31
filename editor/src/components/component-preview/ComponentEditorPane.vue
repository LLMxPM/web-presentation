<!-- 文件功能：提供工作空间组件的纯编辑面板，承载基础信息、previewSchema 与 Vue 源码编辑，不直接访问 API。 -->
<template>
  <section class="flex h-full min-h-0 flex-col overflow-hidden bg-surface">
    <div class="flex shrink-0 items-center justify-between gap-3 border-b border-border px-5 py-3">
      <div class="min-w-0">
        <div class="flex items-center gap-2">
          <Code2 class="h-4 w-4 text-accent-emphasis" />
          <h3 class="truncate text-sm font-bold text-text-strong">
            {{ mode === 'create' ? '新增组件草稿' : '编辑组件草稿' }}
          </h3>
          <span class="shrink-0 rounded-full bg-surface-muted px-2 py-0.5 text-[10px] font-bold text-text-muted">
            {{ mode === 'create' ? '新建' : '编辑' }}
          </span>
        </div>
        <p class="mt-1 text-xs text-text-disabled">保存后仍是草稿，发布版本后才能被页面或其他组件引用。</p>
      </div>

      <div class="flex shrink-0 flex-wrap items-center justify-end gap-2">
        <UiButton v-if="canViewHistory" variant="ghost" size="sm" @click="emit('open-version-history')">
          <History class="h-3.5 w-3.5" />
          版本
        </UiButton>
        <UiButton variant="secondary" size="sm" :loading="previewLoading" @click="emit('preview-draft')">
          <Eye class="h-3.5 w-3.5" />
          保存并预览
        </UiButton>
        <UiButton variant="primary" size="sm" :loading="saving" @click="emit('save-draft')">
          {{ mode === 'create' ? '创建草稿' : '保存草稿' }}
        </UiButton>

        <BaseCloseButton label="关闭组件编辑" @click="emit('cancel-edit')" />
      </div>
    </div>

    <div class="grid min-h-0 flex-1 grid-cols-[380px_minmax(0,1fr)] divide-x divide-border-muted overflow-hidden">
      <aside class="h-full overflow-y-auto bg-canvas/60 p-4">
        <div class="space-y-4">
          <section class="space-y-3">
            <h4 class="text-[11px] font-black uppercase tracking-[0.18em] text-text-disabled">基本信息</h4>
            <UiFormField label="组件名称" required :error="errors.name">
              <UiInput
                :model-value="form.name"
                placeholder="如：数据统计卡片"
                required
                @update:model-value="updateField('name', String($event))"
              />
            </UiFormField>

            <UiFormField label="源码引用名" required :error="errors.import_name">
              <UiInput
                :model-value="form.import_name"
                placeholder="如：SalesMetricCard"
                required
                @update:model-value="updateField('import_name', String($event))"
              />
            </UiFormField>

            <div class="flex w-full flex-col gap-1.5">
              <label class="ml-1 text-sm font-semibold text-text-emphasis">
                组件类型
                <span class="text-danger">*</span>
              </label>
              <UiSelect
                :model-value="form.component_type"
                :options="componentTypeOptions"
                placeholder="请选择组件类型"
                empty-text="暂无匹配分类。"
                @update:model-value="handleComponentTypeChange"
              />
              <p v-if="errors.component_type" class="ml-1 mt-0.5 text-xs text-danger">
                {{ errors.component_type }}
              </p>
            </div>

            <UiFormField label="组件摘要">
              <UiInput
                :model-value="form.summary"
                type="textarea"
                placeholder="简述组件用途及使用限制..."
                :rows="3"
                @update:model-value="updateField('summary', String($event))"
              />
            </UiFormField>
          </section>

          <section class="space-y-3 border-t border-border/70 pt-4">
            <div class="flex items-center justify-between gap-3">
              <h4 class="text-[11px] font-black uppercase tracking-[0.18em] text-text-disabled">预览配置 Schema</h4>
              <div class="flex shrink-0 items-center gap-1">
                <UiButton
                  variant="ghost"
                  size="xs"
                  class="inline-flex items-center gap-1 text-[10px] font-bold text-accent-emphasis transition-colors hover:text-accent"
                  @click="emit('open-schema-help')"
                >
                  <HelpCircle class="h-3.5 w-3.5" />
                  配置说明
                </UiButton>
                <UiButton
                  variant="ghost"
                  size="xs"
                  class="inline-flex items-center gap-1 text-[10px] font-bold text-text-muted transition-colors hover:text-text-emphasis"
                  @click="schemaZoomVisible = true"
                >
                  <Maximize2 class="h-3.5 w-3.5" />
                  放大编辑
                </UiButton>
              </div>
            </div>

            <div class="overflow-hidden rounded-xl border border-border bg-surface shadow-sm focus-within:border-border-focus/50 focus-within:ring-2 focus-within:ring-border-focus/20">
              <MonacoCodeEditor
                :model-value="form.preview_schema"
                language="json"
                :auto-save-delay="0"
                height="260px"
                @update:model-value="updateField('preview_schema', $event)"
              />
            </div>
            <p v-if="errors.preview_schema" class="px-1 text-[10px] font-bold text-danger">
              {{ errors.preview_schema }}
            </p>
          </section>
        </div>
      </aside>

      <main class="flex h-full min-w-0 flex-col bg-surface">
        <div class="flex shrink-0 items-center justify-between border-b border-border-muted bg-canvas/50 px-4 py-2.5">
          <div class="flex items-center gap-2">
            <div class="h-2 w-2 rounded-full bg-accent-emphasis"></div>
            <span class="text-[11px] font-black uppercase tracking-wider text-text-secondary">组件源码 (.vue)</span>
          </div>
        </div>

        <div class="relative min-h-0 flex-1">
          <MonacoCodeEditor
            :model-value="form.content"
            language="vue"
            :auto-save-delay="0"
            height="100%"
            @update:model-value="updateField('content', $event)"
          />
          <div
            v-if="errors.content"
            class="absolute bottom-4 left-4 right-4 rounded-lg border border-danger-border bg-danger-muted p-3 shadow-lg"
          >
            <p class="text-xs font-bold text-danger">{{ errors.content }}</p>
          </div>
        </div>
      </main>
    </div>

    <CodeZoomEditDialog
      v-model:open="schemaZoomVisible"
      :model-value="form.preview_schema"
      title="放大编辑预览配置 Schema"
      description="修改会实时同步回左侧表单，关闭弹窗后继续保存草稿即可生效。"
      language="json"
      :error="errors.preview_schema"
      @update:model-value="updateField('preview_schema', $event)"
    />
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Code2, Eye, HelpCircle, History, Maximize2 } from '@lucide/vue'

import CodeZoomEditDialog from '@/components/editor/CodeZoomEditDialog.vue'
import MonacoCodeEditor from '@/components/editor/MonacoCodeEditor.vue'
import UiButton from '@/components/ui/button/UiButton.vue'
import BaseCloseButton from '@/components/ui/BaseCloseButton.vue'
import UiFormField from '@/components/ui/form-field/UiFormField.vue'
import UiInput from '@/components/ui/input/UiInput.vue'
import { UiSelect } from '@/components/ui'
import type { SelectModelValue, SelectOption } from '@/components/ui/select'
import {
  normalizeComponentType,
  workspaceComponentTypeValues,
  type WorkspaceComponentDraftErrors,
  type WorkspaceComponentDraftForm,
} from '@/composables/useWorkspaceComponentDraft'

const props = defineProps<{
  form: WorkspaceComponentDraftForm
  errors: WorkspaceComponentDraftErrors
  mode: 'create' | 'edit'
  saving: boolean
  previewLoading: boolean
  canPublish: boolean
  canViewHistory?: boolean
}>()

const emit = defineEmits<{
  'update:form': [value: WorkspaceComponentDraftForm]
  'preview-draft': []
  'save-draft': []
  publish: []
  'cancel-edit': []
  'open-version-history': []
  'open-schema-help': []
}>()

const schemaZoomVisible = ref(false)
const componentTypeOptions: SelectOption[] = workspaceComponentTypeValues.map(value => ({
  label: value,
  value,
}))

/**
 * 更新草稿表单的单个字段，并通过完整对象同步给父层。
 * @param field 字段名
 * @param value 字段值
 */
function updateField<K extends keyof WorkspaceComponentDraftForm>(field: K, value: WorkspaceComponentDraftForm[K]): void {
  emit('update:form', {
    ...props.form,
    [field]: value,
  })
}

/**
 * 处理组件类型选择器输出，兼容单选组件可能返回的数组值。
 * @param value 选择器值
 */
function handleComponentTypeChange(value: SelectModelValue): void {
  const selectedValue = Array.isArray(value) ? value[0] : value
  updateField('component_type', normalizeComponentType(selectedValue))
}
</script>
