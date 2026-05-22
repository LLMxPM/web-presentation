<!-- 文件功能：提供工作空间组件的纯编辑面板，承载基础信息、previewSchema 与 Vue 源码编辑，不直接访问 API。 -->
<template>
  <section class="flex h-full min-h-0 flex-col overflow-hidden bg-white">
    <div class="flex shrink-0 items-center justify-between gap-3 border-b border-slate-200 px-5 py-3">
      <div class="min-w-0">
        <div class="flex items-center gap-2">
          <Code2 class="h-4 w-4 text-indigo-500" />
          <h3 class="truncate text-sm font-bold text-slate-900">
            {{ mode === 'create' ? '新建组件草稿' : '编辑组件草稿' }}
          </h3>
        </div>
        <p class="mt-1 text-xs text-slate-400">保存后仍是草稿，发布版本后才能被页面或其他组件引用。</p>
      </div>

      <div class="flex shrink-0 items-center gap-2">
        <BaseButton variant="ghost" size="sm" @click="emit('cancel-edit')">
          取消
        </BaseButton>
        <BaseButton variant="secondary" size="sm" :loading="previewLoading" @click="emit('preview-draft')">
          预览当前草稿
        </BaseButton>
        <BaseButton variant="primary" size="sm" :loading="saving" @click="emit('save-draft')">
          {{ mode === 'create' ? '创建草稿' : '保存草稿' }}
        </BaseButton>
        <BaseButton v-if="mode === 'edit'" variant="secondary" size="sm" :disabled="!canPublish" @click="emit('publish')">
          发布版本
        </BaseButton>
        <button
          type="button"
          class="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-400 transition-colors hover:border-slate-300 hover:bg-slate-50 hover:text-slate-700"
          aria-label="关闭组件编辑"
          title="关闭组件编辑"
          @click="emit('cancel-edit')"
        >
          <X class="h-4 w-4" />
        </button>
      </div>
    </div>

    <div class="grid min-h-0 flex-1 grid-cols-[420px_minmax(0,1fr)] divide-x divide-slate-100 overflow-hidden">
      <aside class="h-full overflow-y-auto bg-slate-50/60 p-5">
        <div class="space-y-6">
          <section class="space-y-4">
            <h4 class="text-[11px] font-black uppercase tracking-[0.18em] text-slate-400">基本信息</h4>
            <BaseInput
              :model-value="form.name"
              label="组件名称"
              placeholder="如：数据统计卡片"
              required
              :error="errors.name"
              @update:model-value="updateField('name', String($event))"
            />

            <BaseInput
              :model-value="form.import_name"
              label="源码引用名"
              placeholder="如：SalesMetricCard"
              required
              :error="errors.import_name"
              @update:model-value="updateField('import_name', String($event))"
            />

            <div class="flex w-full flex-col gap-1.5">
              <label class="ml-1 text-sm font-semibold text-slate-700">
                组件类型
                <span class="text-red-500">*</span>
              </label>
              <SearchableSelect
                :model-value="form.component_type"
                :options="componentTypeOptions"
                placeholder="请选择组件类型"
                search-placeholder="搜索组件类型"
                empty-text="暂无匹配分类。"
                @update:model-value="handleComponentTypeChange"
              />
              <p v-if="errors.component_type" class="ml-1 mt-0.5 text-xs text-red-500">
                {{ errors.component_type }}
              </p>
            </div>

            <BaseInput
              :model-value="form.summary"
              type="textarea"
              label="组件摘要"
              placeholder="简述组件用途及使用限制..."
              :rows="3"
              @update:model-value="updateField('summary', String($event))"
            />
          </section>

          <section class="space-y-3 border-t border-slate-200/70 pt-5">
            <div class="flex items-center justify-between gap-3">
              <h4 class="text-[11px] font-black uppercase tracking-[0.18em] text-slate-400">预览配置 Schema</h4>
              <button
                type="button"
                class="inline-flex items-center gap-1 text-[10px] font-bold text-indigo-500 transition-colors hover:text-indigo-600"
                @click="emit('open-schema-help')"
              >
                <HelpCircle class="h-3.5 w-3.5" />
                配置说明
              </button>
            </div>

            <div class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm focus-within:border-indigo-500/50 focus-within:ring-2 focus-within:ring-indigo-500/20">
              <MonacoCodeEditor
                :model-value="form.preview_schema"
                language="json"
                theme="light"
                :auto-save-delay="0"
                height="320px"
                @update:model-value="updateField('preview_schema', $event)"
              />
            </div>
            <p v-if="errors.preview_schema" class="px-1 text-[10px] font-bold text-rose-500">
              {{ errors.preview_schema }}
            </p>
          </section>
        </div>
      </aside>

      <main class="flex h-full min-w-0 flex-col bg-white">
        <div class="flex shrink-0 items-center justify-between border-b border-slate-100 bg-slate-50/50 px-4 py-2.5">
          <div class="flex items-center gap-2">
            <div class="h-2 w-2 rounded-full bg-indigo-500"></div>
            <span class="text-[11px] font-black uppercase tracking-wider text-slate-600">组件源码 (.vue)</span>
          </div>
          <div class="flex rounded-lg bg-slate-200/60 p-0.5">
            <button
              v-for="theme in themeOptions"
              :key="theme"
              type="button"
              class="rounded-md px-2.5 py-1 text-[10px] font-bold transition-all"
              :class="editorTheme === theme ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'"
              @click="emit('update:editorTheme', theme)"
            >
              {{ theme === 'light' ? '明亮' : '暗黑' }}
            </button>
          </div>
        </div>

        <div class="relative min-h-0 flex-1">
          <MonacoCodeEditor
            :model-value="form.content"
            language="vue"
            :theme="editorTheme"
            :auto-save-delay="0"
            height="100%"
            @update:model-value="updateField('content', $event)"
          />
          <div
            v-if="errors.content"
            class="absolute bottom-4 left-4 right-4 rounded-lg border border-rose-100 bg-rose-50 p-3 shadow-lg"
          >
            <p class="text-xs font-bold text-rose-600">{{ errors.content }}</p>
          </div>
        </div>
      </main>
    </div>
  </section>
</template>

<script setup lang="ts">
import { Code2, HelpCircle, X } from 'lucide-vue-next'

import MonacoCodeEditor from '@/components/editor/MonacoCodeEditor.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseInput from '@/components/ui/BaseInput.vue'
import SearchableSelect from '@/components/ui/SearchableSelect.vue'
import type { SelectModelValue, SelectOption } from '@/components/ui/select'
import {
  normalizeComponentType,
  workspaceComponentTypeValues,
  type WorkspaceComponentDraftErrors,
  type WorkspaceComponentDraftForm,
} from '@/composables/useWorkspaceComponentDraft'
import type { EditorThemeMode } from '@/types/monaco'

const props = defineProps<{
  form: WorkspaceComponentDraftForm
  errors: WorkspaceComponentDraftErrors
  mode: 'create' | 'edit'
  editorTheme: EditorThemeMode
  saving: boolean
  previewLoading: boolean
  canPublish: boolean
}>()

const emit = defineEmits<{
  'update:form': [value: WorkspaceComponentDraftForm]
  'update:editorTheme': [value: EditorThemeMode]
  'preview-draft': []
  'save-draft': []
  publish: []
  'cancel-edit': []
  'open-schema-help': []
}>()

const themeOptions: EditorThemeMode[] = ['light', 'dark']
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
