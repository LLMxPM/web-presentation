<!-- 文件功能：项目展示配置弹窗，统一编辑主题、页面尺寸、菜单模式与 PDF 导出按钮。 -->
<template>
  <BaseDialog :model-value="modelValue" title="项目展示配置" width="1040px" @update:model-value="handleVisibleChange">
    <div v-if="project && modelValue" class="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
      <section class="space-y-4">
        <WorkspaceStyleApplyField
          v-if="workspaceId"
          :workspace-id="workspaceId"
          @apply="applyWorkspaceStyle"
        />

        <div class="rounded-lg border border-slate-200 bg-white p-4">
          <ThemeSelectorField :workspace-id="workspaceId" :model-value="draft.themeKey" :preferred-key="defaultThemeKey"
            label="项目主题" :show-preview="false" @update:model-value="updateThemeKey" />
        </div>

        <div class="rounded-lg border border-slate-200 bg-white p-4">
          <BaseInput
            v-model="draft.styleSpecMarkdown"
            type="textarea"
            label="样式规范 Markdown"
            placeholder="记录内容助手生成页面时应遵循的版式、排版和视觉约束"
            :rows="12"
          />
        </div>
      </section>

      <aside class="space-y-4">
        <div class="rounded-lg border border-slate-200 bg-slate-50/70 p-4">
          <PreviewSizePresetSelect
            :current-width="normalizedPageWidth"
            :current-height="normalizedPageHeight"
            :current-base-font-size="normalizedBaseFontSize"
            :current-icon-default-stroke-width="normalizedIconDefaultStrokeWidth"
            label="尺寸模板"
            @apply="applyPageSizePreset"
          />
          <div class="mt-3 grid grid-cols-2 gap-3">
            <BaseInput v-model="draft.pageWidth" label="页面宽度(px)" placeholder="1920" />
            <BaseInput v-model="draft.pageHeight" label="页面高度(px)" placeholder="1080" />
          </div>
          <div class="mt-3 grid grid-cols-2 gap-3">
            <BaseInput v-model="draft.baseFontSize" label="基础字号" placeholder="20px" />
            <BaseInput v-model="draft.iconDefaultStrokeWidth" label="图标描边" placeholder="2" />
          </div>
        </div>

        <div class="rounded-lg border border-slate-200 bg-white p-4">
          <label class="ml-1 text-sm font-semibold text-slate-700">菜单模式</label>
          <div class="mt-3 grid grid-cols-3 gap-2 rounded-lg bg-slate-100 p-1">
            <button v-for="option in menuModeOptions" :key="option.value" type="button"
              class="flex min-h-11 flex-col items-center justify-center rounded-md px-3 py-2.5 text-xs font-bold transition-all"
              :class="draft.menuMode === option.value ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'"
              @click="draft.menuMode = option.value">
              <span>{{ option.label }}</span>
            </button>
          </div>
        </div>

        <div class="rounded-lg border border-slate-200 bg-white p-4">
          <label class="ml-1 text-sm font-semibold text-slate-700">PDF 导出按钮</label>
          <div class="mt-3 grid grid-cols-2 gap-2 rounded-lg bg-slate-100 p-1">
            <button v-for="option in pdfButtonOptions" :key="String(option.value)" type="button"
              class="flex min-h-11 items-center justify-center rounded-md px-3 py-2.5 text-xs font-bold transition-all"
              :class="draft.showPdfExportButton === option.value ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'"
              @click="draft.showPdfExportButton = option.value">
              {{ option.label }}
            </button>
          </div>
        </div>
      </aside>
    </div>

    <div v-else class="py-10 text-center text-sm text-slate-400">
      当前没有可编辑的项目。
    </div>

    <template #footer>
      <BaseButton variant="ghost" @click="handleVisibleChange(false)">取消</BaseButton>
      <BaseButton variant="ghost" :disabled="!project" @click="resetDraft">恢复当前值</BaseButton>
      <BaseButton variant="ghost" :disabled="!project || !workspaceId" @click="openSaveAsStyleDialog">另存为样式</BaseButton>
      <BaseButton variant="primary" :loading="loading" :disabled="!project" @click="handleSave">
        保存配置
      </BaseButton>
    </template>
  </BaseDialog>

  <WorkspaceStyleEditorDialog
    v-model="saveAsStyleDialogVisible"
    :workspace-id="workspaceId"
    :initial-style="saveAsStyleInitialValue"
    :default-theme-key="defaultThemeKey"
    :loading="saveAsStyleSaving"
    @save="handleSaveAsStyle"
  />
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'

import { createWorkspaceStyle, type WorkspaceStylePayload } from '@/api/styles'
import ThemeSelectorField from '@/components/theme/ThemeSelectorField.vue'
import PreviewSizePresetSelect from '@/components/preview-size/PreviewSizePresetSelect.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import BaseInput from '@/components/ui/BaseInput.vue'
import type { PreviewSizePreset, ProjectItem, ProjectMenuMode, WorkspaceStyleItem } from '@/types/api'
import { Message } from '@/utils/message'
import { getErrorMessage } from '@/api/http'
import WorkspaceStyleApplyField from './WorkspaceStyleApplyField.vue'
import WorkspaceStyleEditorDialog from './WorkspaceStyleEditorDialog.vue'

const DEFAULT_PROJECT_PAGE_WIDTH = 1920
const DEFAULT_PROJECT_PAGE_HEIGHT = 1080
const DEFAULT_PROJECT_BASE_FONT_SIZE = '20px'

const props = withDefaults(defineProps<{
  modelValue: boolean
  project: ProjectItem | null
  workspaceId: number | null
  defaultThemeKey?: string | null
  loading?: boolean
}>(), {
  defaultThemeKey: null,
  loading: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  save: [payload: {
    page_width: number
    page_height: number
    base_font_size: string
    icon_default_stroke_width: number
    show_pdf_export_button: boolean
    menu_mode: ProjectMenuMode
    theme_key: string | null
    style_spec_markdown: string
    suggested_component_source_style_id?: number | null
  }]
}>()

const draft = reactive({
  pageWidth: String(DEFAULT_PROJECT_PAGE_WIDTH),
  pageHeight: String(DEFAULT_PROJECT_PAGE_HEIGHT),
  baseFontSize: DEFAULT_PROJECT_BASE_FONT_SIZE,
  iconDefaultStrokeWidth: '2',
  showPdfExportButton: true,
  menuMode: 'preview' as ProjectMenuMode,
  themeKey: null as string | null,
  styleSpecMarkdown: '',
})

const saveAsStyleDialogVisible = ref(false)
const saveAsStyleSaving = ref(false)
const appliedWorkspaceStyleId = ref<number | null>(null)

const menuModeOptions = [
  { label: '侧边缩略图', value: 'preview' as const },
  { label: '底部缩略图', value: 'bottom-preview' as const },
  { label: '文本', value: 'text' as const },
]

const pdfButtonOptions = [
  { label: '显示', value: true },
  { label: '隐藏', value: false },
]

const normalizedPageWidth = computed(() => normalizeDimension(draft.pageWidth, DEFAULT_PROJECT_PAGE_WIDTH))
const normalizedPageHeight = computed(() => normalizeDimension(draft.pageHeight, DEFAULT_PROJECT_PAGE_HEIGHT))
const normalizedBaseFontSize = computed(() => normalizeBaseFontSize(draft.baseFontSize, DEFAULT_PROJECT_BASE_FONT_SIZE))
const normalizedIconDefaultStrokeWidth = computed(() => normalizeIntegerWithinRange(draft.iconDefaultStrokeWidth, 2, 1, 64))
const saveAsStyleInitialValue = computed<Partial<WorkspaceStylePayload>>(() => ({
  key: buildStyleKey(props.project?.name ?? 'project-style'),
  name: `${props.project?.name ?? '项目'}样式`,
  description: props.project?.description ?? null,
  page_width: normalizedPageWidth.value,
  page_height: normalizedPageHeight.value,
  base_font_size: normalizedBaseFontSize.value,
  icon_default_stroke_width: normalizedIconDefaultStrokeWidth.value,
  show_pdf_export_button: draft.showPdfExportButton,
  menu_mode: draft.menuMode,
  theme_key: draft.themeKey,
  style_spec_markdown: draft.styleSpecMarkdown,
}))

/**
 * 根据项目详情刷新展示配置草稿。
 * @param project 当前项目
 */
function syncDraftFromProject(project: ProjectItem | null): void {
  draft.pageWidth = String(project?.page_width ?? DEFAULT_PROJECT_PAGE_WIDTH)
  draft.pageHeight = String(project?.page_height ?? DEFAULT_PROJECT_PAGE_HEIGHT)
  draft.baseFontSize = project?.base_font_size ?? DEFAULT_PROJECT_BASE_FONT_SIZE
  draft.iconDefaultStrokeWidth = String(project?.icon_default_stroke_width ?? 2)
  draft.showPdfExportButton = project?.show_pdf_export_button ?? true
  draft.menuMode = project?.menu_mode ?? 'preview'
  draft.themeKey = project?.theme_key ?? props.defaultThemeKey ?? null
  draft.styleSpecMarkdown = project?.style_spec_markdown ?? ''
  appliedWorkspaceStyleId.value = null
}

/**
 * 向父组件同步弹窗可见状态。
 * @param value 目标可见状态
 */
function handleVisibleChange(value: boolean): void {
  emit('update:modelValue', value)
}

/**
 * 将主题选择结果写回草稿。
 * @param value 主题 key
 */
function updateThemeKey(value: string | null): void {
  draft.themeKey = value
}

/**
 * 将用户预设尺寸应用到项目页面尺寸草稿。
 * @param preset 预设尺寸
 */
function applyPageSizePreset(preset: PreviewSizePreset): void {
  draft.pageWidth = String(normalizeDimension(String(preset.width), DEFAULT_PROJECT_PAGE_WIDTH))
  draft.pageHeight = String(normalizeDimension(String(preset.height), DEFAULT_PROJECT_PAGE_HEIGHT))
  draft.baseFontSize = normalizeBaseFontSize(preset.base_font_size || DEFAULT_PROJECT_BASE_FONT_SIZE, DEFAULT_PROJECT_BASE_FONT_SIZE)
  draft.iconDefaultStrokeWidth = String(normalizeIntegerWithinRange(String(preset.icon_default_stroke_width ?? 2), 2, 1, 64))
}

/**
 * 将工作空间样式复制到项目配置草稿，不建立持久关联。
 * @param style 被应用的工作空间样式
 */
function applyWorkspaceStyle(style: WorkspaceStyleItem): void {
  draft.pageWidth = String(normalizeDimension(String(style.page_width), DEFAULT_PROJECT_PAGE_WIDTH))
  draft.pageHeight = String(normalizeDimension(String(style.page_height), DEFAULT_PROJECT_PAGE_HEIGHT))
  draft.baseFontSize = normalizeBaseFontSize(style.base_font_size, DEFAULT_PROJECT_BASE_FONT_SIZE)
  draft.iconDefaultStrokeWidth = String(normalizeIntegerWithinRange(String(style.icon_default_stroke_width), 2, 1, 64))
  draft.showPdfExportButton = style.show_pdf_export_button
  draft.menuMode = style.menu_mode
  if (style.theme_key) {
    draft.themeKey = style.theme_key
  }
  draft.styleSpecMarkdown = style.style_spec_markdown
  appliedWorkspaceStyleId.value = style.id
}

/**
 * 恢复到当前项目已保存的展示配置。
 */
function resetDraft(): void {
  syncDraftFromProject(props.project)
}

/**
 * 提交项目展示配置。
 */
function handleSave(): void {
  const payload: {
    page_width: number
    page_height: number
    base_font_size: string
    icon_default_stroke_width: number
    show_pdf_export_button: boolean
    menu_mode: ProjectMenuMode
    theme_key: string | null
    style_spec_markdown: string
    suggested_component_source_style_id?: number | null
  } = {
    page_width: normalizedPageWidth.value,
    page_height: normalizedPageHeight.value,
    base_font_size: normalizedBaseFontSize.value,
    icon_default_stroke_width: normalizedIconDefaultStrokeWidth.value,
    show_pdf_export_button: draft.showPdfExportButton,
    menu_mode: draft.menuMode,
    theme_key: draft.themeKey,
    style_spec_markdown: draft.styleSpecMarkdown,
  }
  if (appliedWorkspaceStyleId.value !== null) {
    payload.suggested_component_source_style_id = appliedWorkspaceStyleId.value
  }
  emit('save', payload)
}

/**
 * 打开另存为工作空间样式弹窗。
 */
function openSaveAsStyleDialog(): void {
  saveAsStyleDialogVisible.value = true
}

/**
 * 将当前项目样式草稿保存为工作空间样式。
 * @param payload 样式创建参数
 */
async function handleSaveAsStyle(payload: WorkspaceStylePayload): Promise<void> {
  if (!props.workspaceId) {
    return
  }
  saveAsStyleSaving.value = true
  try {
    await createWorkspaceStyle(props.workspaceId, payload)
    saveAsStyleDialogVisible.value = false
    Message.success('样式已保存到工作空间样式库。')
  } catch (error) {
    Message.error(getErrorMessage(error, '另存为样式失败。'))
  } finally {
    saveAsStyleSaving.value = false
  }
}

/**
 * 归一化页面尺寸，避免输入空值或非法字符时破坏预览。
 * @param value 原始输入值
 * @param fallback 默认尺寸
 */
function normalizeDimension(value: string, fallback: number): number {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return fallback
  }
  return Math.min(8192, Math.max(1, Math.round(parsed)))
}

/**
 * 归一化项目基础字号。
 * @param value 原始字号
 * @param fallback 回退字号
 */
function normalizeBaseFontSize(value: string, fallback: string): string {
  const normalized = String(value || '').trim().toLowerCase()
  const match = normalized.match(/^(\d+)(px)?$/)
  if (!match) {
    return fallback
  }
  const parsedValue = Number.parseInt(match[1], 10)
  if (!Number.isFinite(parsedValue) || parsedValue < 1 || parsedValue > 200) {
    return fallback
  }
  return `${parsedValue}px`
}

/**
 * 归一化项目页面规格整数。
 * @param value 原始输入
 * @param fallback 回退值
 * @param min 最小值
 * @param max 最大值
 */
function normalizeIntegerWithinRange(value: string, fallback: number, min: number, max: number): number {
  const parsedValue = Number(value)
  if (!Number.isFinite(parsedValue)) {
    return fallback
  }
  return Math.min(max, Math.max(min, Math.round(parsedValue)))
}

/**
 * 基于项目名称生成样式 key 候选值。
 * @param value 项目名称
 */
function buildStyleKey(value: string): string {
  const normalized = String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return normalized || 'project-style'
}

watch(
  () => [props.modelValue, props.project] as const,
  ([visible, project]) => {
    if (visible) {
      syncDraftFromProject(project)
    }
  },
  { immediate: true },
)
</script>
