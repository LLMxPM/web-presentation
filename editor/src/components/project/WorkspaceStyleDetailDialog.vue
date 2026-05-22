<!-- 文件功能：展示工作空间样式详情弹窗，集中呈现展示配置字段与 Markdown 样式规范。 -->
<template>
  <BaseDialog
    :model-value="modelValue"
    :title="style ? `${style.name} · 样式详情` : '样式详情'"
    width="860px"
    @update:model-value="handleVisibleChange"
  >
    <div v-if="style" class="space-y-5">
      <section class="rounded-lg border border-slate-200 bg-white p-4">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0">
            <h3 class="truncate text-lg font-black text-slate-900">{{ style.name }}</h3>
            <p class="mt-1 font-mono text-xs text-slate-400">{{ style.key }}</p>
          </div>
          <span class="rounded-full bg-indigo-50 px-3 py-1 text-xs font-black text-indigo-600">
            {{ style.theme_key || '不覆盖主题' }}
          </span>
        </div>
        <p class="mt-3 text-sm leading-6 text-slate-500">{{ style.description || '未填写样式说明。' }}</p>
      </section>

      <section class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <div
          v-for="item in detailItems"
          :key="item.label"
          class="rounded-lg border border-slate-100 bg-slate-50 px-4 py-3"
        >
          <p class="text-[11px] font-bold text-slate-400">{{ item.label }}</p>
          <p class="mt-1 text-sm font-black text-slate-800">{{ item.value }}</p>
        </div>
      </section>

      <section class="rounded-lg border border-slate-200 bg-white p-4">
        <h4 class="text-sm font-black text-slate-900">样式规范</h4>
        <div v-if="selectedStyleSpecMarkdown" class="style-spec-markdown mt-3 rounded-lg border border-slate-100 bg-slate-50 px-5 py-4">
          <MarkdownRender :nodes="selectedStyleSpecNodes" />
        </div>
        <div v-else class="mt-3 flex min-h-[160px] items-center justify-center rounded-lg border border-dashed border-slate-200 bg-slate-50 text-sm text-slate-400">
          当前样式还没有维护样式规范。
        </div>
      </section>
    </div>

    <div v-else class="py-10 text-center text-sm text-slate-400">
      当前没有可查看的样式。
    </div>

    <template #footer>
      <BaseButton variant="ghost" @click="handleVisibleChange(false)">关闭</BaseButton>
      <BaseButton variant="primary" :disabled="!style" @click="handleEditStyle">编辑样式</BaseButton>
    </template>
  </BaseDialog>
</template>

<script setup lang="ts">
import 'markstream-vue/index.css'

import { computed } from 'vue'
import MarkdownRender, { getMarkdown, parseMarkdownToStructure } from 'markstream-vue'

import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import type { ProjectMenuMode, WorkspaceStyleItem } from '@/types/api'

const props = defineProps<{
  modelValue: boolean
  style: WorkspaceStyleItem | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  edit: [style: WorkspaceStyleItem]
}>()

const markdownParser = getMarkdown()

const selectedStyleSpecMarkdown = computed(() => props.style?.style_spec_markdown?.trim() || '')
const selectedStyleSpecNodes = computed(() => parseMarkdownToStructure(selectedStyleSpecMarkdown.value, markdownParser, {
  final: true,
}))
const detailItems = computed(() => {
  const style = props.style
  if (!style) {
    return []
  }
  return [
    { label: '页面尺寸', value: `${style.page_width} x ${style.page_height}` },
    { label: '基础字号', value: style.base_font_size },
    { label: '图标描边', value: String(style.icon_default_stroke_width) },
    { label: '菜单模式', value: formatMenuMode(style.menu_mode) },
    { label: 'PDF 导出', value: style.show_pdf_export_button ? '显示' : '隐藏' },
    { label: '主题 key', value: style.theme_key || '不覆盖项目主题' },
  ]
})

/**
 * 向父组件同步详情弹窗可见状态。
 * @param value 目标可见状态
 */
function handleVisibleChange(value: boolean): void {
  emit('update:modelValue', value)
}

/**
 * 从详情弹窗进入当前样式编辑。
 */
function handleEditStyle(): void {
  if (!props.style) {
    return
  }
  emit('edit', props.style)
  handleVisibleChange(false)
}

/**
 * 格式化菜单模式展示文本。
 * @param mode 菜单模式
 */
function formatMenuMode(mode: ProjectMenuMode): string {
  if (mode === 'bottom-preview') return '底部缩略图'
  if (mode === 'text') return '文本菜单'
  return '侧边缩略图'
}
</script>

<style scoped>
.style-spec-markdown :deep(.markstream-vue) {
  background: transparent;
  color: rgb(51 65 85);
  font-size: 0.875rem;
  line-height: 1.75;
}

.style-spec-markdown :deep(.markstream-vue > :first-child) {
  margin-top: 0;
}

.style-spec-markdown :deep(.markstream-vue > :last-child) {
  margin-bottom: 0;
}

.style-spec-markdown :deep(.markstream-vue > * + *) {
  margin-top: 0.75rem;
}

.style-spec-markdown :deep(h1),
.style-spec-markdown :deep(h2),
.style-spec-markdown :deep(h3) {
  color: rgb(15 23 42);
  font-weight: 800;
  line-height: 1.3;
}

.style-spec-markdown :deep(h1) {
  font-size: 1.25rem;
}

.style-spec-markdown :deep(h2) {
  font-size: 1.125rem;
}

.style-spec-markdown :deep(h3) {
  font-size: 1rem;
}

.style-spec-markdown :deep(ul),
.style-spec-markdown :deep(ol) {
  padding-left: 1.25rem;
}

.style-spec-markdown :deep(code:not(pre code)) {
  border-radius: 0.375rem;
  background: rgb(241 245 249);
  padding: 0.125rem 0.375rem;
  color: rgb(30 41 59);
  font-size: 0.8125rem;
}

.style-spec-markdown :deep(pre) {
  overflow-x: auto;
  border-radius: 0.75rem;
  background: rgb(15 23 42);
  padding: 1rem;
  color: rgb(226 232 240);
}
</style>
