<!-- 文件功能：提供组件预览标题栏中的紧凑页面配置条，集中编辑页面尺寸与主题。 -->
<template>
  <div
    class="flex items-end gap-3"
    :class="resolveRootClass()"
  >
    <div v-if="inline" :class="simplified ? 'min-w-[220px] flex-[1_1_224px] space-y-1' : 'w-[224px] space-y-1'">
      <span class="block text-[11px] font-semibold text-slate-500">预览容器尺寸</span>
      <div class="inline-flex h-9 w-full items-center overflow-hidden rounded-xl border border-slate-200 bg-white">
        <div class="h-full min-w-0 flex-1">
          <PreviewSizePresetSelect
            :current-width="modelValue.page.width"
            :current-height="modelValue.page.height"
            :current-base-font-size="modelValue.page.base_font_size"
            :current-icon-default-stroke-width="modelValue.page.icon_default_stroke_width"
            compact
            embedded
            @apply="applyPagePreset"
          />
        </div>

        <span class="h-5 w-px shrink-0 bg-slate-100" />

        <div class="grid h-full w-[104px] shrink-0 grid-cols-[minmax(0,1fr)_12px_minmax(0,1fr)] items-center">
          <input
            :value="String(modelValue.page.width)"
            type="text"
            inputmode="numeric"
            class="h-full w-full min-w-0 bg-transparent px-0.5 text-center text-xs font-semibold tabular-nums text-slate-700 outline-none transition focus:bg-slate-50"
            title="页面宽度"
            @input="updatePageDimensionField('width', ($event.target as HTMLInputElement).value)"
            @blur="normalizePageDimensionField('width')"
          >
          <span class="text-center text-xs text-slate-300">×</span>
          <input
            :value="String(modelValue.page.height)"
            type="text"
            inputmode="numeric"
            class="h-full w-full min-w-0 bg-transparent px-0.5 text-center text-xs font-semibold tabular-nums text-slate-700 outline-none transition focus:bg-slate-50"
            title="页面高度"
            @input="updatePageDimensionField('height', ($event.target as HTMLInputElement).value)"
            @blur="normalizePageDimensionField('height')"
          >
        </div>
      </div>
    </div>

    <div v-else class="grid grid-cols-[48px_164px] items-center gap-x-3 gap-y-1">
      <span class="text-[11px] font-semibold text-slate-500">预览容器尺寸</span>
      <div class="min-w-0">
        <PreviewSizePresetSelect
          :current-width="modelValue.page.width"
          :current-height="modelValue.page.height"
          :current-base-font-size="modelValue.page.base_font_size"
          :current-icon-default-stroke-width="modelValue.page.icon_default_stroke_width"
          compact
          @apply="applyPagePreset"
        />
      </div>

      <div class="col-start-2 inline-flex h-9 w-full items-center overflow-hidden rounded-xl border border-slate-200 bg-white">
        <input
          :value="String(modelValue.page.width)"
          type="text"
          inputmode="numeric"
          class="h-full min-w-0 flex-1 bg-transparent px-1 text-center text-xs font-semibold tabular-nums text-slate-700 outline-none transition focus:bg-slate-50"
          title="页面宽度"
          @input="updatePageDimensionField('width', ($event.target as HTMLInputElement).value)"
          @blur="normalizePageDimensionField('width')"
        >
        <span class="text-xs text-slate-300">×</span>
        <input
          :value="String(modelValue.page.height)"
          type="text"
          inputmode="numeric"
          class="h-full min-w-0 flex-1 bg-transparent px-1 text-center text-xs font-semibold tabular-nums text-slate-700 outline-none transition focus:bg-slate-50"
          title="页面高度"
          @input="updatePageDimensionField('height', ($event.target as HTMLInputElement).value)"
          @blur="normalizePageDimensionField('height')"
        >
      </div>
    </div>

    <div v-if="inline && !simplified" class="w-[236px] space-y-1">
      <span class="block text-[11px] font-semibold text-slate-500">字号与描边</span>
      <div class="grid h-9 grid-cols-2 overflow-hidden rounded-xl border border-slate-200 bg-white">
        <input
          :value="modelValue.page.base_font_size"
          type="text"
          inputmode="numeric"
          class="h-full min-w-0 bg-transparent px-1 text-center text-xs font-semibold text-slate-700 outline-none transition focus:bg-slate-50"
          title="基础字号"
          @input="updateBaseFontSize(($event.target as HTMLInputElement).value)"
          @blur="normalizeBaseFontSizeField"
        >
        <input
          :value="String(modelValue.page.icon_default_stroke_width)"
          type="text"
          inputmode="numeric"
          class="h-full min-w-0 border-l border-slate-100 bg-transparent px-1 text-center text-xs font-semibold tabular-nums text-slate-700 outline-none transition focus:bg-slate-50"
          title="默认图标描边"
          @input="updateIntegerPageSpecField('icon_default_stroke_width', ($event.target as HTMLInputElement).value, 1, 64)"
          @blur="normalizeIntegerPageSpecField('icon_default_stroke_width', 2, 1, 64)"
        >
      </div>
    </div>

    <div v-else-if="!simplified" class="grid grid-cols-[48px_164px] items-center gap-x-3 gap-y-1">
      <span class="text-[11px] font-semibold text-slate-500">页面规格</span>
      <div class="col-start-2 grid h-9 grid-cols-2 overflow-hidden rounded-xl border border-slate-200 bg-white">
        <input
          :value="modelValue.page.base_font_size"
          type="text"
          inputmode="numeric"
          class="h-full min-w-0 bg-transparent px-1 text-center text-xs font-semibold text-slate-700 outline-none transition focus:bg-slate-50"
          title="基础字号"
          @input="updateBaseFontSize(($event.target as HTMLInputElement).value)"
          @blur="normalizeBaseFontSizeField"
        >
        <input
          :value="String(modelValue.page.icon_default_stroke_width)"
          type="text"
          inputmode="numeric"
          class="h-full min-w-0 border-l border-slate-100 bg-transparent px-1 text-center text-xs font-semibold tabular-nums text-slate-700 outline-none transition focus:bg-slate-50"
          title="默认图标描边"
          @input="updateIntegerPageSpecField('icon_default_stroke_width', ($event.target as HTMLInputElement).value, 1, 64)"
          @blur="normalizeIntegerPageSpecField('icon_default_stroke_width', 2, 1, 64)"
        >
      </div>
    </div>

    <div class="space-y-1" :class="inline && simplified ? 'min-w-[164px] flex-[1_1_164px]' : ''">
      <span class="block text-[11px] font-semibold text-slate-500">主题</span>
      <div :class="inline ? (simplified ? 'w-full' : 'w-[164px]') : 'w-[180px] max-w-full'">
        <ThemeSelectorField
          :workspace-id="workspaceId ?? null"
          :model-value="modelValue.page.theme_key"
          :preferred-key="preferredThemeKey ?? null"
          label=""
          :show-preview="false"
          compact
          @update:model-value="updateReleaseThemeKey"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">

import ThemeSelectorField from '@/components/theme/ThemeSelectorField.vue'
import PreviewSizePresetSelect from '@/components/preview-size/PreviewSizePresetSelect.vue'
import type { ComponentPreviewOptions, PreviewSizePreset } from '@/types/api'
import {
  cloneComponentPreviewOptions,
  normalizeBaseFontSize,
  normalizeIntegerWithinRange,
  normalizePositiveDimension,
} from './preview-config'

const props = defineProps<{
  modelValue: ComponentPreviewOptions
  workspaceId?: number | null
  preferredThemeKey?: string | null
  inline?: boolean
  simplified?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: ComponentPreviewOptions]
}>()

/**
 * 按使用场景返回根布局类；简化态需要在窄预览栏内换行，完整态保持横向工具条。
 */
function resolveRootClass(): string {
  if (!props.inline) {
    return 'min-w-0 flex-wrap justify-end'
  }
  return props.simplified
    ? 'min-w-0 flex-1 flex-wrap justify-start'
    : 'min-w-max flex-nowrap justify-start'
}

/**
 * 将用户预设尺寸应用到预览页面宽高。
 * @param preset 预设尺寸
 */
function applyPagePreset(preset: PreviewSizePreset) {
  const nextOptions = cloneComponentPreviewOptions(props.modelValue)
  nextOptions.page.width = normalizePositiveDimension(preset.width, nextOptions.page.width)
  nextOptions.page.height = normalizePositiveDimension(preset.height, nextOptions.page.height)
  nextOptions.page.base_font_size = normalizeBaseFontSize(preset.base_font_size, nextOptions.page.base_font_size)
  nextOptions.page.icon_default_stroke_width = normalizeIntegerWithinRange(
    preset.icon_default_stroke_width,
    nextOptions.page.icon_default_stroke_width,
    1,
    64,
  )
  emit('update:modelValue', nextOptions)
}

/**
 * 更新页面尺寸字段，并向父层发送新的完整配置对象。
 * @param field 页面宽高字段
 * @param value 原始输入值
 */
function updatePageDimensionField(
  field: 'width' | 'height',
  value: string,
) {
  const nextOptions = cloneComponentPreviewOptions(props.modelValue)
  const fallbackValue = field === 'width' ? nextOptions.page.width : nextOptions.page.height
  const parsedValue = Number(value)
  if (String(value).trim() !== '' && Number.isFinite(parsedValue)) {
    nextOptions.page[field] = normalizePositiveDimension(parsedValue, fallbackValue)
    emit('update:modelValue', nextOptions)
  }
}

/**
 * 在失焦时归一化页面尺寸，避免非法值残留。
 * @param field 页面宽高字段
 */
function normalizePageDimensionField(field: 'width' | 'height') {
  const nextOptions = cloneComponentPreviewOptions(props.modelValue)
  const fallbackValue = field === 'width' ? 1920 : 1080
  nextOptions.page[field] = normalizePositiveDimension(nextOptions.page[field], fallbackValue)
  emit('update:modelValue', nextOptions)
}

/**
 * 更新基础字号字段，输入过程中只接受可归一化值。
 * @param value 原始输入值
 */
function updateBaseFontSize(value: string) {
  const normalizedValue = String(value || '').trim()
  if (!normalizedValue || !/^(\d+)(px)?$/i.test(normalizedValue)) {
    return
  }
  const nextOptions = cloneComponentPreviewOptions(props.modelValue)
  nextOptions.page.base_font_size = normalizeBaseFontSize(normalizedValue, nextOptions.page.base_font_size)
  emit('update:modelValue', nextOptions)
}

/**
 * 在失焦时归一化基础字号。
 */
function normalizeBaseFontSizeField() {
  const nextOptions = cloneComponentPreviewOptions(props.modelValue)
  nextOptions.page.base_font_size = normalizeBaseFontSize(nextOptions.page.base_font_size, '20px')
  emit('update:modelValue', nextOptions)
}

/**
 * 更新页面规格中的整数项。
 * @param field 字段名
 * @param value 输入值
 * @param min 最小值
 * @param max 最大值
 */
function updateIntegerPageSpecField(
  field: 'icon_default_stroke_width',
  value: string,
  min: number,
  max: number,
) {
  const parsedValue = Number(value)
  if (String(value).trim() === '' || !Number.isFinite(parsedValue)) {
    return
  }
  const nextOptions = cloneComponentPreviewOptions(props.modelValue)
  nextOptions.page[field] = normalizeIntegerWithinRange(parsedValue, nextOptions.page[field], min, max)
  emit('update:modelValue', nextOptions)
}

/**
 * 在失焦时归一化页面规格中的整数项。
 * @param field 字段名
 * @param fallbackValue 回退值
 * @param min 最小值
 * @param max 最大值
 */
function normalizeIntegerPageSpecField(
  field: 'icon_default_stroke_width',
  fallbackValue: number,
  min: number,
  max: number,
) {
  const nextOptions = cloneComponentPreviewOptions(props.modelValue)
  nextOptions.page[field] = normalizeIntegerWithinRange(nextOptions.page[field], fallbackValue, min, max)
  emit('update:modelValue', nextOptions)
}

/**
 * 更新当前预览使用的主题 key。
 * @param value 主题 key
 */
function updateReleaseThemeKey(value: string | null) {
  const nextOptions = cloneComponentPreviewOptions(props.modelValue)
  nextOptions.page.theme_key = value
  emit('update:modelValue', nextOptions)
}
</script>
