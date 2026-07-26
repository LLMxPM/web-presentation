<!-- 文件功能：提供组件预览占位控制，支持设置组件在页面中的宽高、对齐与留白。 -->
<template>
  <section :class="embedded ? '' : 'rounded-2xl border border-border bg-surface/90 p-4 shadow-sm'">
    <div v-if="inline" class="flex min-w-max items-end gap-2">
      <div class="space-y-1">
        <span class="block text-[11px] font-semibold text-text-muted">宽度</span>
        <div class="inline-flex h-9 items-center overflow-hidden rounded-xl border border-border bg-surface">
          <input
            :value="resolveInlineSizeInput(modelValue.placement.width_mode, modelValue.placement.width_value)"
            :disabled="modelValue.placement.width_mode === 'auto'"
            type="text"
            inputmode="numeric"
            class="h-full w-16 bg-transparent px-2 text-center text-xs font-semibold tabular-nums text-text-emphasis outline-none transition focus:bg-surface-hover disabled:bg-canvas disabled:text-text-faint"
            :placeholder="modelValue.placement.width_mode === 'auto' ? '—' : '值'"
            @input="updatePlacementNumberField('width_value', ($event.target as HTMLInputElement).value)"
            @blur="normalizePlacementNumberField('width_value')"
          >
          <UiDropdownMenu :items="widthModeMenuItems" side="bottom" align="start" @select="value => updatePlacementField('width_mode', value)">
            <template #trigger>
              <UiButton
                type="button"
                variant="ghost"
                size="sm"
                class="h-full w-[58px] rounded-none border-y-0 border-r-0 border-l border-border-muted bg-canvas/70 px-2 text-xs font-bold text-text-secondary hover:bg-surface-muted hover:text-text"
                title="宽度单位"
              >
                <span>{{ resolveSizeModeLabel(modelValue.placement.width_mode) }}</span>
                <ChevronDown class="h-3 w-3 text-text-disabled" />
              </UiButton>
            </template>
          </UiDropdownMenu>
        </div>
      </div>

      <div class="space-y-1">
        <span class="block text-[11px] font-semibold text-text-muted">高度</span>
        <div class="inline-flex h-9 items-center overflow-hidden rounded-xl border border-border bg-surface">
          <input
            :value="resolveInlineSizeInput(modelValue.placement.height_mode, modelValue.placement.height_value)"
            :disabled="modelValue.placement.height_mode === 'auto'"
            type="text"
            inputmode="numeric"
            class="h-full w-16 bg-transparent px-2 text-center text-xs font-semibold tabular-nums text-text-emphasis outline-none transition focus:bg-surface-hover disabled:bg-canvas disabled:text-text-faint"
            :placeholder="modelValue.placement.height_mode === 'auto' ? '—' : '值'"
            @input="updatePlacementNumberField('height_value', ($event.target as HTMLInputElement).value)"
            @blur="normalizePlacementNumberField('height_value')"
          >
          <UiDropdownMenu :items="heightModeMenuItems" side="bottom" align="start" @select="value => updatePlacementField('height_mode', value)">
            <template #trigger>
              <UiButton
                type="button"
                variant="ghost"
                size="sm"
                class="h-full w-[58px] rounded-none border-y-0 border-r-0 border-l border-border-muted bg-canvas/70 px-2 text-xs font-bold text-text-secondary hover:bg-surface-muted hover:text-text"
                title="高度单位"
              >
                <span>{{ resolveSizeModeLabel(modelValue.placement.height_mode) }}</span>
                <ChevronDown class="h-3 w-3 text-text-disabled" />
              </UiButton>
            </template>
          </UiDropdownMenu>
        </div>
      </div>

      <div class="space-y-1">
        <span class="block text-[11px] font-semibold text-text-muted">水平</span>
        <div class="inline-flex h-9 overflow-hidden rounded-xl border border-border bg-surface p-0.5">
          <UiIconButton
            v-for="option in horizontalAlignOptions"
            :key="option.value"
            type="button"
            :label="option.label"
            size="sm"
            class="h-8 w-8 rounded-lg"
            :class="modelValue.placement.horizontal_align === option.value
              ? 'bg-surface-selected text-accent'
              : 'text-text-disabled hover:bg-surface-hover hover:text-text-emphasis'"
            :title="option.label"
            :aria-label="option.label"
            @click="updatePlacementField('horizontal_align', option.value)"
          >
            <component :is="option.icon" class="h-4 w-4" />
          </UiIconButton>
        </div>
      </div>

      <div class="space-y-1">
        <span class="block text-[11px] font-semibold text-text-muted">垂直</span>
        <div class="inline-flex h-9 overflow-hidden rounded-xl border border-border bg-surface p-0.5">
          <UiIconButton
            v-for="option in verticalAlignOptions"
            :key="option.value"
            type="button"
            :label="option.label"
            size="sm"
            class="h-8 w-8 rounded-lg"
            :class="modelValue.placement.vertical_align === option.value
              ? 'bg-surface-selected text-accent'
              : 'text-text-disabled hover:bg-surface-hover hover:text-text-emphasis'"
            :title="option.label"
            :aria-label="option.label"
            @click="updatePlacementField('vertical_align', option.value)"
          >
            <component :is="option.icon" class="h-4 w-4" />
          </UiIconButton>
        </div>
      </div>

      <div class="space-y-1">
        <span class="block text-[11px] font-semibold text-text-muted">留白</span>
        <label class="inline-flex h-9 items-center overflow-hidden rounded-xl border border-border bg-surface">
          <input
            :value="String(modelValue.placement.padding)"
            type="text"
            inputmode="numeric"
            class="h-full w-14 bg-transparent px-2 text-center text-xs font-semibold tabular-nums text-text-emphasis outline-none transition focus:bg-surface-hover"
            @input="updatePlacementNumberField('padding', ($event.target as HTMLInputElement).value)"
            @blur="normalizePlacementNumberField('padding')"
          >
          <span class="w-8 border-l border-border-muted text-center text-[10px] font-bold text-text-disabled">px</span>
        </label>
      </div>

      <UiButton
        variant="ghost"
        size="sm"
        custom-class="!h-9 !px-2.5 !text-xs !text-text-muted"
        @click="emit('reset-defaults')"
      >
        默认
      </UiButton>
    </div>



    <div v-if="!inline" class="space-y-4">
      <div class="flex items-center justify-between gap-2">
        <h4 v-if="!embedded" class="text-sm font-bold text-text">组件占位</h4>
        <UiButton
          variant="ghost"
          size="sm"
          :custom-class="embedded ? '!h-8 !justify-start !px-0 !text-xs' : ''"
          @click="emit('reset-defaults')"
        >
          恢复默认
        </UiButton>
      </div>

      <div class="grid grid-cols-2 gap-2">
        <label class="space-y-1.5">
          <span class="text-[11px] font-semibold text-text-muted">宽度模式</span>
          <UiSelect :model-value="modelValue.placement.width_mode" :options="sizeModeSelectOptions" @update:model-value="value => updatePlacementField('width_mode', String(value))" />
        </label>

        <label class="space-y-1.5">
          <span class="text-[11px] font-semibold text-text-muted">宽度值</span>
          <input
            :value="resolveSizeInput(modelValue.placement.width_value)"
            :disabled="modelValue.placement.width_mode === 'auto'"
            type="text"
            inputmode="numeric"
            class="h-9 w-full rounded-xl border border-border bg-canvas px-3 text-sm font-medium text-text-emphasis outline-none transition focus:border-border-focus focus:bg-surface disabled:text-text-faint"
            @input="updatePlacementNumberField('width_value', ($event.target as HTMLInputElement).value)"
            @blur="normalizePlacementNumberField('width_value')"
          >
        </label>

        <label class="space-y-1.5">
          <span class="text-[11px] font-semibold text-text-muted">高度模式</span>
          <UiSelect :model-value="modelValue.placement.height_mode" :options="sizeModeSelectOptions" @update:model-value="value => updatePlacementField('height_mode', String(value))" />
        </label>

        <label class="space-y-1.5">
          <span class="text-[11px] font-semibold text-text-muted">高度值</span>
          <input
            :value="resolveSizeInput(modelValue.placement.height_value)"
            :disabled="modelValue.placement.height_mode === 'auto'"
            type="text"
            inputmode="numeric"
            class="h-9 w-full rounded-xl border border-border bg-canvas px-3 text-sm font-medium text-text-emphasis outline-none transition focus:border-border-focus focus:bg-surface disabled:text-text-faint"
            @input="updatePlacementNumberField('height_value', ($event.target as HTMLInputElement).value)"
            @blur="normalizePlacementNumberField('height_value')"
          >
        </label>

        <label class="space-y-1.5">
          <span class="text-[11px] font-semibold text-text-muted">水平对齐</span>
          <UiSelect :model-value="modelValue.placement.horizontal_align" :options="alignmentSelectOptions" @update:model-value="value => updatePlacementField('horizontal_align', String(value))" />
        </label>

        <label class="space-y-1.5">
          <span class="text-[11px] font-semibold text-text-muted">垂直对齐</span>
          <UiSelect :model-value="modelValue.placement.vertical_align" :options="verticalAlignmentSelectOptions" @update:model-value="value => updatePlacementField('vertical_align', String(value))" />
        </label>

        <label class="col-span-2 space-y-1.5">
          <span class="text-[11px] font-semibold text-text-muted">页面留白</span>
          <input
            :value="String(modelValue.placement.padding)"
            type="text"
            inputmode="numeric"
            class="h-9 w-full rounded-xl border border-border bg-canvas px-3 text-sm font-medium text-text-emphasis outline-none transition focus:border-border-focus focus:bg-surface"
            @input="updatePlacementNumberField('padding', ($event.target as HTMLInputElement).value)"
            @blur="normalizePlacementNumberField('padding')"
          >
        </label>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  AlignHorizontalJustifyCenter,
  AlignHorizontalJustifyEnd,
  AlignHorizontalJustifyStart,
  AlignVerticalJustifyCenter,
  AlignVerticalJustifyEnd,
  AlignVerticalJustifyStart,
  ChevronDown,
} from '@lucide/vue'

import { UiButton, UiDropdownMenu, UiIconButton, UiSelect } from '@/components/ui'
import type { DropdownMenuEntry } from '@/components/ui'
import type { ComponentPreviewAlignment, ComponentPreviewOptions, ComponentPreviewSizeMode } from '@/types/api'
import {
  cloneComponentPreviewOptions,
  normalizeComponentPreviewOptions,
} from './preview-config'

const props = withDefaults(defineProps<{
  modelValue: ComponentPreviewOptions
  embedded?: boolean
  inline?: boolean
}>(), {
  embedded: false,
  inline: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: ComponentPreviewOptions]
  'reset-defaults': []
}>()


const sizeModeOptions: Array<{
  value: ComponentPreviewSizeMode
  label: string
}> = [
  { value: 'percent', label: '%' },
  { value: 'fixed', label: 'px' },
  { value: 'auto', label: 'auto' },
]
const sizeModeSelectOptions = [
  { value: 'percent', label: '百分比' },
  { value: 'fixed', label: '固定像素' },
  { value: 'auto', label: '自适应' },
]
const alignmentSelectOptions = [
  { value: 'start', label: '左侧' },
  { value: 'center', label: '居中' },
  { value: 'end', label: '右侧' },
]
const verticalAlignmentSelectOptions = [
  { value: 'start', label: '顶部' },
  { value: 'center', label: '居中' },
  { value: 'end', label: '底部' },
]
/**
 * 宽度模式菜单项，带选中指示。
 */
const widthModeMenuItems = computed<DropdownMenuEntry[]>(() =>
  sizeModeOptions.map(opt => ({
    label: opt.label,
    value: opt.value,
    active: props.modelValue.placement.width_mode === opt.value,
  })),
)

/**
 * 高度模式菜单项，带选中指示。
 */
const heightModeMenuItems = computed<DropdownMenuEntry[]>(() =>
  sizeModeOptions.map(opt => ({
    label: opt.label,
    value: opt.value,
    active: props.modelValue.placement.height_mode === opt.value,
  })),
)

const horizontalAlignOptions: Array<{
  value: ComponentPreviewAlignment
  label: string
  icon: unknown
}> = [
  { value: 'start', label: '左对齐', icon: AlignHorizontalJustifyStart },
  { value: 'center', label: '水平居中', icon: AlignHorizontalJustifyCenter },
  { value: 'end', label: '右对齐', icon: AlignHorizontalJustifyEnd },
]

const verticalAlignOptions: Array<{
  value: ComponentPreviewAlignment
  label: string
  icon: unknown
}> = [
  { value: 'start', label: '顶部对齐', icon: AlignVerticalJustifyStart },
  { value: 'center', label: '垂直居中', icon: AlignVerticalJustifyCenter },
  { value: 'end', label: '底部对齐', icon: AlignVerticalJustifyEnd },
]


/**
 * 更新占位枚举字段，并重新归一化占位值。
 * @param field 字段名
 * @param value 用户选择值
 */
function updatePlacementField(field: keyof ComponentPreviewOptions['placement'], value: string) {
  const nextOptions = cloneComponentPreviewOptions(props.modelValue)
  ;(nextOptions.placement as unknown as Record<string, unknown>)[field] = value
  emit('update:modelValue', normalizeComponentPreviewOptions(nextOptions))
}



/**
 * 更新占位数值字段，空值仅保留当前状态，避免输入中途跳动。
 * @param field 字段名
 * @param value 原始输入
 */
function updatePlacementNumberField(field: 'width_value' | 'height_value' | 'padding', value: string) {
  const parsedValue = Number(value)
  if (String(value).trim() === '' || !Number.isFinite(parsedValue)) {
    return
  }
  const nextOptions = cloneComponentPreviewOptions(props.modelValue)
  ;(nextOptions.placement as unknown as Record<string, unknown>)[field] = parsedValue
  emit('update:modelValue', normalizeComponentPreviewOptions(nextOptions))
}

/**
 * 失焦时强制归一化占位数值。
 * @param field 字段名
 */
function normalizePlacementNumberField(field: 'width_value' | 'height_value' | 'padding') {
  void field
  const nextOptions = normalizeComponentPreviewOptions(props.modelValue)
  emit('update:modelValue', nextOptions)
}

/**
 * 将可空尺寸展示为输入框字符串。
 * @param value 尺寸值
 * @returns 输入框文本
 */
function resolveSizeInput(value: number | null) {
  return value === null ? '' : String(value)
}

/**
 * 内联模式下展示尺寸输入；auto 模式只展示占位，不重复显示 auto 文本。
 * @param mode 尺寸模式
 * @param value 当前尺寸值
 * @returns 输入框展示值
 */
function resolveInlineSizeInput(mode: ComponentPreviewSizeMode, value: number | null) {
  return mode === 'auto' ? '' : resolveSizeInput(value)
}

/**
 * 解析尺寸模式显示标签。
 * @param mode 尺寸模式
 * @returns 下拉触发器文案
 */
function resolveSizeModeLabel(mode: ComponentPreviewSizeMode) {
  return sizeModeOptions.find(option => option.value === mode)?.label || '%'
}

</script>


