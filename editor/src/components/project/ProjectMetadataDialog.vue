<!-- 文件功能：项目元数据编辑弹窗，统一承载项目创建与基础信息修改表单。 -->
<template>
  <BaseDialog :model-value="modelValue" :title="isEditMode ? '修改项目' : '新增项目'" width="1040px"
    @update:model-value="handleVisibleChange">
    <div class="space-y-4">
      <section class="rounded-lg border border-slate-200 bg-white p-3">
        <div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
          <BaseInput
            v-model="form.name"
            label="项目名称"
            placeholder="起一个具有辨识度的名称"
            required
            :error="errors.name"
          />
          <BaseInput
            v-model="form.description"
            label="项目描述"
            placeholder="概括此项目要阐述的内容"
          />
        </div>
      </section>

      <div class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div class="space-y-3">
          <section class="rounded-lg border border-slate-200 bg-slate-50/70 p-3">
            <div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_260px]">
              <WorkspaceStyleApplyField
                v-if="workspaceId"
                :workspace-id="workspaceId"
                embedded
                label="样式模板"
                hint="从模板快速填充项目样式。"
                @apply="applyWorkspaceStyle"
              />
              <div v-else>
                <label class="text-sm font-semibold text-slate-700">应用样式</label>
                <p class="mt-1 text-xs text-slate-400">缺少工作空间上下文，暂时不能从样式库填充项目草稿。</p>
              </div>
              <div class="border-t border-slate-200 pt-4 lg:border-l lg:border-t-0 lg:pl-4 lg:pt-0">
                <ThemeSelectorField
                  :workspace-id="workspaceId"
                  :model-value="form.theme_key"
                  :preferred-key="defaultThemeKey"
                  label="项目主题"
                  hint="样式可填充，也可手动覆盖。"
                  :show-preview="false"
                  @update:model-value="handleThemeChange"
                />
                <p v-if="errors.theme" class="mt-2 text-xs font-semibold text-rose-500">{{ errors.theme }}</p>
              </div>
            </div>
          </section>

          <section class="rounded-lg border border-slate-200 bg-white p-3">
            <BaseInput
              v-model="form.style_spec_markdown"
              type="textarea"
              label="样式规范 Markdown"
              placeholder="可记录版式、排版、色彩和内容生成约束"
              :rows="9"
            />
          </section>
        </div>

        <aside class="space-y-3">
          <section class="rounded-lg border border-slate-200 bg-slate-50/70 p-3">
            <PreviewSizePresetSelect :current-width="normalizedPageWidth" :current-height="normalizedPageHeight"
              :current-base-font-size="normalizedBaseFontSize"
              :current-icon-default-stroke-width="normalizedIconDefaultStrokeWidth"
              label="尺寸模板" @apply="applyPageSizePreset" />
            <div class="mt-2 grid grid-cols-2 gap-3">
              <BaseInput v-model="form.page_width" type="number" label="页面宽度(px)" placeholder="1920" />
              <BaseInput v-model="form.page_height" type="number" label="页面高度(px)" placeholder="1080" />
            </div>
            <div class="mt-2 grid grid-cols-2 gap-3">
              <BaseInput v-model="form.base_font_size" label="基础字号" placeholder="20px" />
              <BaseInput v-model="form.icon_default_stroke_width" type="number" label="图标描边" placeholder="2" />
            </div>

            <div class="mt-3 border-t border-slate-200 pt-2">
              <label class="ml-1 text-sm font-semibold text-slate-700">菜单模式</label>
              <div class="mt-2 grid grid-cols-3 gap-1.5 rounded-lg bg-slate-100 p-1">
                <button v-for="option in menuModeOptions" :key="option.value" type="button"
                  class="flex min-h-10 items-center justify-center gap-1.5 rounded-md px-2.5 py-2 text-xs font-bold leading-none transition-all whitespace-nowrap"
                  :class="form.menu_mode === option.value ? 'bg-white text-indigo-600 shadow-sm ring-1 ring-indigo-100' : 'text-slate-500 hover:bg-white/60 hover:text-slate-700'"
                  @click="form.menu_mode = option.value">
                  <component :is="option.icon" class="h-3.5 w-3.5 shrink-0" />
                  <span>{{ option.label }}</span>
                </button>
              </div>

              <label class="ml-1 mt-2 block text-sm font-semibold text-slate-700">PDF 导出按钮</label>
              <div class="mt-2 grid grid-cols-2 gap-1.5 rounded-lg bg-slate-100 p-1">
                <button v-for="option in pdfButtonOptions" :key="String(option.value)" type="button"
                  class="flex min-h-10 items-center justify-center gap-1.5 rounded-md px-3 py-2 text-xs font-bold transition-all whitespace-nowrap"
                  :class="form.show_pdf_export_button === option.value ? 'bg-white text-indigo-600 shadow-sm ring-1 ring-indigo-100' : 'text-slate-500 hover:bg-white/60 hover:text-slate-700'"
                  @click="form.show_pdf_export_button = option.value">
                  <component :is="option.icon" class="h-3.5 w-3.5 shrink-0" />
                  <span>{{ option.label }}</span>
                </button>
              </div>
            </div>
          </section>
        </aside>
      </div>
    </div>

    <template #footer>
      <BaseButton variant="ghost" @click="handleVisibleChange(false)">取消</BaseButton>
      <BaseButton variant="primary" :loading="loading" @click="handleSubmit">
        {{ isEditMode ? '同步修改' : '立即创建' }}
      </BaseButton>
    </template>
  </BaseDialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Eye, EyeOff, PanelBottom, PanelLeft, Type } from '@lucide/vue'

import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import BaseInput from '@/components/ui/BaseInput.vue'
import PreviewSizePresetSelect from '@/components/preview-size/PreviewSizePresetSelect.vue'
import ThemeSelectorField from '@/components/theme/ThemeSelectorField.vue'
import { DEFAULT_PROJECT_STYLE_SPEC_MARKDOWN } from '@/constants/project-style'
import WorkspaceStyleApplyField from './WorkspaceStyleApplyField.vue'
import type { PreviewSizePreset, ProjectItem, ProjectMenuMode, RecordStatus, WorkspaceStyleItem } from '@/types/api'

const DEFAULT_PROJECT_PAGE_WIDTH = 1920
const DEFAULT_PROJECT_PAGE_HEIGHT = 1080
const DEFAULT_PROJECT_BASE_FONT_SIZE = '20px'

const props = withDefaults(defineProps<{
  modelValue: boolean
  project?: ProjectItem | null
  workspaceId?: number | null
  defaultThemeKey?: string | null
  loading?: boolean
}>(), {
  project: null,
  workspaceId: null,
  defaultThemeKey: null,
  loading: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submit: [payload: {
    name: string
    description: string | null
    status: RecordStatus
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

const form = reactive({
  name: '',
  description: '',
  status: 'active' as RecordStatus,
  page_width: String(DEFAULT_PROJECT_PAGE_WIDTH),
  page_height: String(DEFAULT_PROJECT_PAGE_HEIGHT),
  base_font_size: DEFAULT_PROJECT_BASE_FONT_SIZE,
  icon_default_stroke_width: '2',
  show_pdf_export_button: true,
  menu_mode: 'preview' as ProjectMenuMode,
  theme_key: null as string | null,
  style_spec_markdown: DEFAULT_PROJECT_STYLE_SPEC_MARKDOWN,
})

const errors = reactive({
  name: '',
  theme: '',
})
const appliedWorkspaceStyleId = ref<number | null>(null)

const menuModeOptions = [
  { label: '侧边', value: 'preview' as const, icon: PanelLeft },
  { label: '底部', value: 'bottom-preview' as const, icon: PanelBottom },
  { label: '文本', value: 'text' as const, icon: Type },
]

const pdfButtonOptions = [
  { label: '显示', value: true, icon: Eye },
  { label: '隐藏', value: false, icon: EyeOff },
]

const isEditMode = computed(() => !!props.project)
const normalizedPageWidth = computed(() => normalizeDimension(form.page_width, DEFAULT_PROJECT_PAGE_WIDTH))
const normalizedPageHeight = computed(() => normalizeDimension(form.page_height, DEFAULT_PROJECT_PAGE_HEIGHT))
const normalizedBaseFontSize = computed(() => normalizeBaseFontSize(form.base_font_size, DEFAULT_PROJECT_BASE_FONT_SIZE))
const normalizedIconDefaultStrokeWidth = computed(() => normalizeIntegerWithinRange(form.icon_default_stroke_width, 2, 1, 64))

/**
 * 根据当前项目同步弹窗草稿，确保新建与编辑场景共享同一套表单。
 */
function syncFormFromProject(project: ProjectItem | null): void {
  form.name = project?.name ?? ''
  form.description = project?.description ?? ''
  form.status = project?.status ?? 'active'
  form.page_width = String(project?.page_width ?? DEFAULT_PROJECT_PAGE_WIDTH)
  form.page_height = String(project?.page_height ?? DEFAULT_PROJECT_PAGE_HEIGHT)
  form.base_font_size = project?.base_font_size ?? DEFAULT_PROJECT_BASE_FONT_SIZE
  form.icon_default_stroke_width = String(project?.icon_default_stroke_width ?? 2)
  form.show_pdf_export_button = project?.show_pdf_export_button ?? true
  form.menu_mode = project?.menu_mode ?? 'preview'
  form.theme_key = project?.theme_key ?? props.defaultThemeKey ?? null
  form.style_spec_markdown = project?.style_spec_markdown ?? DEFAULT_PROJECT_STYLE_SPEC_MARKDOWN
  appliedWorkspaceStyleId.value = null
  errors.name = ''
  errors.theme = ''
}

/**
 * 向父组件同步弹窗开关状态。
 */
function handleVisibleChange(value: boolean): void {
  emit('update:modelValue', value)
}

/**
 * 将用户预设尺寸应用到项目基础信息表单。
 * @param preset 预设尺寸
 */
function applyPageSizePreset(preset: PreviewSizePreset): void {
  form.page_width = String(normalizeDimension(String(preset.width), DEFAULT_PROJECT_PAGE_WIDTH))
  form.page_height = String(normalizeDimension(String(preset.height), DEFAULT_PROJECT_PAGE_HEIGHT))
  form.base_font_size = normalizeBaseFontSize(preset.base_font_size || DEFAULT_PROJECT_BASE_FONT_SIZE, DEFAULT_PROJECT_BASE_FONT_SIZE)
  form.icon_default_stroke_width = String(normalizeIntegerWithinRange(String(preset.icon_default_stroke_width ?? 2), 2, 1, 64))
}

/**
 * 将工作空间样式复制到项目草稿，不建立持久关联。
 * @param style 被应用的工作空间样式
 */
function applyWorkspaceStyle(style: WorkspaceStyleItem): void {
  form.page_width = String(normalizeDimension(String(style.page_width), DEFAULT_PROJECT_PAGE_WIDTH))
  form.page_height = String(normalizeDimension(String(style.page_height), DEFAULT_PROJECT_PAGE_HEIGHT))
  form.base_font_size = normalizeBaseFontSize(style.base_font_size, DEFAULT_PROJECT_BASE_FONT_SIZE)
  form.icon_default_stroke_width = String(normalizeIntegerWithinRange(String(style.icon_default_stroke_width), 2, 1, 64))
  form.show_pdf_export_button = style.show_pdf_export_button
  form.menu_mode = style.menu_mode
  if (style.theme_key) {
    form.theme_key = style.theme_key
  }
  form.style_spec_markdown = style.style_spec_markdown
  appliedWorkspaceStyleId.value = style.id
}

/**
 * 更新项目主题选择，并清理主题必填错误。
 * @param value 主题 key
 */
function handleThemeChange(value: string | null): void {
  form.theme_key = value
  if (value) {
    errors.theme = ''
  }
}

/**
 * 校验并提交项目元数据表单。
 */
function handleSubmit(): void {
  if (!form.name.trim()) {
    errors.name = '请输入项目名称'
    return
  }
  if (!form.theme_key) {
    errors.theme = '请选择项目主题'
    return
  }

  errors.name = ''
  errors.theme = ''
  const payload: {
    name: string
    description: string | null
    status: RecordStatus
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
    name: form.name.trim(),
    description: form.description.trim() ? form.description.trim() : null,
    status: form.status,
    page_width: normalizedPageWidth.value,
    page_height: normalizedPageHeight.value,
    base_font_size: normalizedBaseFontSize.value,
    icon_default_stroke_width: normalizedIconDefaultStrokeWidth.value,
    show_pdf_export_button: form.show_pdf_export_button,
    menu_mode: form.menu_mode,
    theme_key: form.theme_key,
    style_spec_markdown: form.style_spec_markdown,
  }
  if (appliedWorkspaceStyleId.value !== null) {
    payload.suggested_component_source_style_id = appliedWorkspaceStyleId.value
  }
  emit('submit', payload)
}

/**
 * 归一化页面尺寸输入。
 * @param value 原始输入
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
 * 归一化基础字号输入。
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

watch(
  () => [props.modelValue, props.project] as const,
  ([visible, project]) => {
    if (visible) {
      syncFormFromProject(project)
    }
  },
  { immediate: true },
)
</script>
