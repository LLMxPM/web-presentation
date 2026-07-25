<!-- 文件功能：复用项目页面尺寸、字号、描边、菜单与导出按钮的展示配置表单。 -->
<template>
  <div class="grid h-full min-h-0 gap-4 2xl:grid-cols-[minmax(0,0.92fr)_minmax(280px,0.78fr)]">
    <div class="min-w-0">
      <PreviewSizePresetSelect
        :current-width="normalizedPageWidth"
        :current-height="normalizedPageHeight"
        :current-base-font-size="normalizedBaseFontSize"
        :current-icon-default-stroke-width="normalizedIconDefaultStrokeWidth"
        label="尺寸模板"
        compact
        @apply="applyPageSizePreset"
      />

      <div class="mt-3 grid grid-cols-2 gap-3">
        <UiFormField label="页面宽度">
          <template #default="field">
            <UiInput
              v-model="pageWidthModel"
              inputmode="numeric"
              placeholder="1920"
              :input-id="field.inputId"
              :described-by="field.describedBy"
            />
          </template>
        </UiFormField>
        <UiFormField label="页面高度">
          <template #default="field">
            <UiInput
              v-model="pageHeightModel"
              inputmode="numeric"
              placeholder="1080"
              :input-id="field.inputId"
              :described-by="field.describedBy"
            />
          </template>
        </UiFormField>
      </div>

      <div class="mt-3 grid grid-cols-2 gap-3">
        <UiFormField label="基础字号">
          <template #default="field">
            <UiUnitInput
              v-model="baseFontSizeModel"
              unit="px"
              :min="1"
              :max="200"
              :fallback="20"
              integer
              placeholder="20"
              :input-id="field.inputId"
              :described-by="field.describedBy"
            />
          </template>
        </UiFormField>
        <UiFormField label="默认图标描边">
          <template #default="field">
            <UiInput
              v-model="iconDefaultStrokeWidthModel"
              inputmode="numeric"
              placeholder="2"
              :input-id="field.inputId"
              :described-by="field.describedBy"
            />
          </template>
        </UiFormField>
      </div>
    </div>

    <div class="grid content-start gap-3 border-t border-border pt-3 sm:grid-cols-2 2xl:grid-cols-1 2xl:border-l 2xl:border-t-0 2xl:pl-4 2xl:pt-0">
      <fieldset class="min-w-0">
        <legend class="text-sm font-medium text-text">菜单模式</legend>
        <div class="mt-1.5">
          <UiSegmentedControl v-model="menuModeModel" aria-label="菜单模式" :options="menuModeOptions" />
        </div>
      </fieldset>

      <fieldset class="min-w-0">
        <legend class="text-sm font-medium text-text">导出按钮</legend>
        <div class="mt-1.5">
          <UiSegmentedControl v-model="pdfExportButtonSegment" aria-label="导出按钮" :options="pdfButtonOptions" />
        </div>
      </fieldset>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import PreviewSizePresetSelect from '@/components/preview-size/PreviewSizePresetSelect.vue'
import { UiFormField, UiInput, UiSegmentedControl, UiUnitInput } from '@/components/ui'
import type { PreviewSizePreset, ProjectMenuMode } from '@/types/api'
import {
  DEFAULT_PROJECT_BASE_FONT_SIZE,
  DEFAULT_PROJECT_PAGE_HEIGHT,
  DEFAULT_PROJECT_PAGE_WIDTH,
  normalizeProjectBaseFontSize,
  normalizeProjectDimension,
  normalizeProjectInteger,
} from './project-presentation-values'

const props = defineProps<{
  pageWidth: string
  pageHeight: string
  baseFontSize: string
  iconDefaultStrokeWidth: string
  showPdfExportButton: boolean
  menuMode: ProjectMenuMode
}>()

const emit = defineEmits<{
  'update:pageWidth': [value: string]
  'update:pageHeight': [value: string]
  'update:baseFontSize': [value: string]
  'update:iconDefaultStrokeWidth': [value: string]
  'update:showPdfExportButton': [value: boolean]
  'update:menuMode': [value: ProjectMenuMode]
}>()

const menuModeOptions = [
  { label: '侧边缩略图', value: 'preview' as const },
  { label: '底部缩略图', value: 'bottom-preview' as const },
  { label: '文本', value: 'text' as const },
]
const pdfButtonOptions = [
  { label: '显示', value: 'visible' },
  { label: '隐藏', value: 'hidden' },
]

const pageWidthModel = createStringModel('pageWidth')
const pageHeightModel = createStringModel('pageHeight')
const baseFontSizeModel = createStringModel('baseFontSize')
const iconDefaultStrokeWidthModel = createStringModel('iconDefaultStrokeWidth')
const menuModeModel = computed({
  get: () => props.menuMode,
  set: value => emit('update:menuMode', value),
})
const pdfExportButtonSegment = computed({
  get: () => props.showPdfExportButton ? 'visible' : 'hidden',
  set: value => emit('update:showPdfExportButton', value === 'visible'),
})
const normalizedPageWidth = computed(() => normalizeProjectDimension(props.pageWidth, DEFAULT_PROJECT_PAGE_WIDTH))
const normalizedPageHeight = computed(() => normalizeProjectDimension(props.pageHeight, DEFAULT_PROJECT_PAGE_HEIGHT))
const normalizedBaseFontSize = computed(() => normalizeProjectBaseFontSize(props.baseFontSize, DEFAULT_PROJECT_BASE_FONT_SIZE))
const normalizedIconDefaultStrokeWidth = computed(() => normalizeProjectInteger(props.iconDefaultStrokeWidth, 2, 1, 64))

/**
 * 为字符串规格字段建立受控双向绑定。
 * @param field 字段名
 */
function createStringModel(
  field: 'pageWidth' | 'pageHeight' | 'baseFontSize' | 'iconDefaultStrokeWidth',
) {
  return computed({
    get: () => props[field],
    set: value => updateStringField(field, value),
  })
}

/**
 * 按字段分派字符串更新事件，保持 Vue defineEmits 的严格事件类型。
 * @param field 字段名
 * @param value 新值
 */
function updateStringField(
  field: 'pageWidth' | 'pageHeight' | 'baseFontSize' | 'iconDefaultStrokeWidth',
  value: string,
): void {
  if (field === 'pageWidth') {
    emit('update:pageWidth', value)
  } else if (field === 'pageHeight') {
    emit('update:pageHeight', value)
  } else if (field === 'baseFontSize') {
    emit('update:baseFontSize', value)
  } else {
    emit('update:iconDefaultStrokeWidth', value)
  }
}

/**
 * 将尺寸模板一次性同步到四个相关展示规格字段。
 * @param preset 用户选择的尺寸模板
 */
function applyPageSizePreset(preset: PreviewSizePreset): void {
  emit('update:pageWidth', String(normalizeProjectDimension(preset.width, DEFAULT_PROJECT_PAGE_WIDTH)))
  emit('update:pageHeight', String(normalizeProjectDimension(preset.height, DEFAULT_PROJECT_PAGE_HEIGHT)))
  emit(
    'update:baseFontSize',
    normalizeProjectBaseFontSize(preset.base_font_size || DEFAULT_PROJECT_BASE_FONT_SIZE, DEFAULT_PROJECT_BASE_FONT_SIZE),
  )
  emit(
    'update:iconDefaultStrokeWidth',
    String(normalizeProjectInteger(preset.icon_default_stroke_width ?? 2, 2, 1, 64)),
  )
}
</script>
