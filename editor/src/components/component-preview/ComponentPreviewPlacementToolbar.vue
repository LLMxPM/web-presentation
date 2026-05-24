<!-- 文件功能：提供组件预览占位控制，支持设置组件在页面中的宽高、对齐与留白。 -->
<template>
  <section :class="embedded ? '' : 'rounded-2xl border border-slate-200 bg-white/90 p-4 shadow-sm shadow-slate-200/60'">
    <div v-if="inline" class="flex min-w-max items-end gap-2">
      <div class="space-y-1">
        <span class="block text-[11px] font-semibold text-slate-500">宽度</span>
        <div class="inline-flex h-9 items-center overflow-hidden rounded-xl border border-slate-200 bg-white">
          <input
            :value="resolveInlineSizeInput(modelValue.placement.width_mode, modelValue.placement.width_value)"
            :disabled="modelValue.placement.width_mode === 'auto'"
            type="text"
            inputmode="numeric"
            class="h-full w-16 bg-transparent px-2 text-center text-xs font-semibold tabular-nums text-slate-700 outline-none transition focus:bg-slate-50 disabled:bg-slate-50 disabled:text-slate-300"
            :placeholder="modelValue.placement.width_mode === 'auto' ? '—' : '值'"
            @input="updatePlacementNumberField('width_value', ($event.target as HTMLInputElement).value)"
            @blur="normalizePlacementNumberField('width_value')"
          >
          <button
            type="button"
            class="inline-flex h-full w-[58px] items-center justify-center gap-1 border-l border-slate-100 bg-slate-50/70 px-2 text-xs font-bold text-slate-600 transition hover:bg-slate-100 hover:text-slate-800"
            title="宽度单位"
            @click.stop="openSizeModeDropdown('width_mode', $event)"
          >
            <span>{{ resolveSizeModeLabel(modelValue.placement.width_mode) }}</span>
            <ChevronDown class="h-3 w-3 text-slate-400" />
          </button>
        </div>
      </div>

      <div class="space-y-1">
        <span class="block text-[11px] font-semibold text-slate-500">高度</span>
        <div class="inline-flex h-9 items-center overflow-hidden rounded-xl border border-slate-200 bg-white">
          <input
            :value="resolveInlineSizeInput(modelValue.placement.height_mode, modelValue.placement.height_value)"
            :disabled="modelValue.placement.height_mode === 'auto'"
            type="text"
            inputmode="numeric"
            class="h-full w-16 bg-transparent px-2 text-center text-xs font-semibold tabular-nums text-slate-700 outline-none transition focus:bg-slate-50 disabled:bg-slate-50 disabled:text-slate-300"
            :placeholder="modelValue.placement.height_mode === 'auto' ? '—' : '值'"
            @input="updatePlacementNumberField('height_value', ($event.target as HTMLInputElement).value)"
            @blur="normalizePlacementNumberField('height_value')"
          >
          <button
            type="button"
            class="inline-flex h-full w-[58px] items-center justify-center gap-1 border-l border-slate-100 bg-slate-50/70 px-2 text-xs font-bold text-slate-600 transition hover:bg-slate-100 hover:text-slate-800"
            title="高度单位"
            @click.stop="openSizeModeDropdown('height_mode', $event)"
          >
            <span>{{ resolveSizeModeLabel(modelValue.placement.height_mode) }}</span>
            <ChevronDown class="h-3 w-3 text-slate-400" />
          </button>
        </div>
      </div>

      <div class="space-y-1">
        <span class="block text-[11px] font-semibold text-slate-500">水平</span>
        <div class="inline-flex h-9 overflow-hidden rounded-xl border border-slate-200 bg-white p-0.5">
          <button
            v-for="option in horizontalAlignOptions"
            :key="option.value"
            type="button"
            class="flex h-8 w-8 items-center justify-center rounded-lg transition-colors"
            :class="modelValue.placement.horizontal_align === option.value
              ? 'bg-indigo-50 text-indigo-600'
              : 'text-slate-400 hover:bg-slate-50 hover:text-slate-700'"
            :title="option.label"
            :aria-label="option.label"
            @click="updatePlacementField('horizontal_align', option.value)"
          >
            <component :is="option.icon" class="h-4 w-4" />
          </button>
        </div>
      </div>

      <div class="space-y-1">
        <span class="block text-[11px] font-semibold text-slate-500">垂直</span>
        <div class="inline-flex h-9 overflow-hidden rounded-xl border border-slate-200 bg-white p-0.5">
          <button
            v-for="option in verticalAlignOptions"
            :key="option.value"
            type="button"
            class="flex h-8 w-8 items-center justify-center rounded-lg transition-colors"
            :class="modelValue.placement.vertical_align === option.value
              ? 'bg-indigo-50 text-indigo-600'
              : 'text-slate-400 hover:bg-slate-50 hover:text-slate-700'"
            :title="option.label"
            :aria-label="option.label"
            @click="updatePlacementField('vertical_align', option.value)"
          >
            <component :is="option.icon" class="h-4 w-4" />
          </button>
        </div>
      </div>

      <div class="space-y-1">
        <span class="block text-[11px] font-semibold text-slate-500">留白</span>
        <label class="inline-flex h-9 items-center overflow-hidden rounded-xl border border-slate-200 bg-white">
          <input
            :value="String(modelValue.placement.padding)"
            type="text"
            inputmode="numeric"
            class="h-full w-14 bg-transparent px-2 text-center text-xs font-semibold tabular-nums text-slate-700 outline-none transition focus:bg-slate-50"
            @input="updatePlacementNumberField('padding', ($event.target as HTMLInputElement).value)"
            @blur="normalizePlacementNumberField('padding')"
          >
          <span class="w-8 border-l border-slate-100 text-center text-[10px] font-bold text-slate-400">px</span>
        </label>
      </div>

      <BaseButton
        variant="ghost"
        size="sm"
        custom-class="!h-9 !px-2.5 !text-xs !text-slate-500"
        @click="emit('reset-defaults')"
      >
        默认
      </BaseButton>
    </div>

    <Teleport to="body">
      <Transition name="size-mode-fade">
        <div
          v-if="sizeModeDropdownVisible"
          class="fixed z-[1800] overflow-hidden rounded-xl border border-slate-200 bg-white p-1 shadow-xl shadow-slate-900/10"
          :style="sizeModeDropdownStyle"
          @mousedown.stop
        >
          <button
            v-for="option in sizeModeOptions"
            :key="`mode-dropdown-${option.value}`"
            type="button"
            class="flex h-8 w-full items-center justify-between rounded-lg px-3 text-left text-xs font-bold transition-colors"
            :class="isSizeModeOptionActive(option.value)
              ? 'bg-indigo-50 text-indigo-600'
              : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'"
            @click="selectSizeModeOption(option.value)"
          >
            <span>{{ option.label }}</span>
            <span
              v-if="isSizeModeOptionActive(option.value)"
              class="h-1.5 w-1.5 rounded-full bg-indigo-500"
            />
          </button>
        </div>
      </Transition>
    </Teleport>

    <div v-if="!inline" class="space-y-4">
      <div class="flex items-center justify-between gap-2">
        <h4 v-if="!embedded" class="text-sm font-bold text-slate-800">组件占位</h4>
        <BaseButton
          variant="ghost"
          size="sm"
          :custom-class="embedded ? '!h-8 !justify-start !px-0 !text-xs' : ''"
          @click="emit('reset-defaults')"
        >
          恢复默认
        </BaseButton>
      </div>

      <div class="grid grid-cols-2 gap-2">
        <label class="space-y-1.5">
          <span class="text-[11px] font-semibold text-slate-500">宽度模式</span>
          <select
            :value="modelValue.placement.width_mode"
            class="h-9 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm font-medium text-slate-700 outline-none transition focus:border-indigo-500 focus:bg-white"
            @change="updatePlacementField('width_mode', ($event.target as HTMLSelectElement).value)"
          >
            <option value="percent">百分比</option>
            <option value="fixed">固定像素</option>
            <option value="auto">自适应</option>
          </select>
        </label>

        <label class="space-y-1.5">
          <span class="text-[11px] font-semibold text-slate-500">宽度值</span>
          <input
            :value="resolveSizeInput(modelValue.placement.width_value)"
            :disabled="modelValue.placement.width_mode === 'auto'"
            type="text"
            inputmode="numeric"
            class="h-9 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm font-medium text-slate-700 outline-none transition focus:border-indigo-500 focus:bg-white disabled:text-slate-300"
            @input="updatePlacementNumberField('width_value', ($event.target as HTMLInputElement).value)"
            @blur="normalizePlacementNumberField('width_value')"
          >
        </label>

        <label class="space-y-1.5">
          <span class="text-[11px] font-semibold text-slate-500">高度模式</span>
          <select
            :value="modelValue.placement.height_mode"
            class="h-9 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm font-medium text-slate-700 outline-none transition focus:border-indigo-500 focus:bg-white"
            @change="updatePlacementField('height_mode', ($event.target as HTMLSelectElement).value)"
          >
            <option value="auto">自适应</option>
            <option value="percent">百分比</option>
            <option value="fixed">固定像素</option>
          </select>
        </label>

        <label class="space-y-1.5">
          <span class="text-[11px] font-semibold text-slate-500">高度值</span>
          <input
            :value="resolveSizeInput(modelValue.placement.height_value)"
            :disabled="modelValue.placement.height_mode === 'auto'"
            type="text"
            inputmode="numeric"
            class="h-9 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm font-medium text-slate-700 outline-none transition focus:border-indigo-500 focus:bg-white disabled:text-slate-300"
            @input="updatePlacementNumberField('height_value', ($event.target as HTMLInputElement).value)"
            @blur="normalizePlacementNumberField('height_value')"
          >
        </label>

        <label class="space-y-1.5">
          <span class="text-[11px] font-semibold text-slate-500">水平对齐</span>
          <select
            :value="modelValue.placement.horizontal_align"
            class="h-9 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm font-medium text-slate-700 outline-none transition focus:border-indigo-500 focus:bg-white"
            @change="updatePlacementField('horizontal_align', ($event.target as HTMLSelectElement).value)"
          >
            <option value="start">左侧</option>
            <option value="center">居中</option>
            <option value="end">右侧</option>
          </select>
        </label>

        <label class="space-y-1.5">
          <span class="text-[11px] font-semibold text-slate-500">垂直对齐</span>
          <select
            :value="modelValue.placement.vertical_align"
            class="h-9 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm font-medium text-slate-700 outline-none transition focus:border-indigo-500 focus:bg-white"
            @change="updatePlacementField('vertical_align', ($event.target as HTMLSelectElement).value)"
          >
            <option value="start">顶部</option>
            <option value="center">居中</option>
            <option value="end">底部</option>
          </select>
        </label>

        <label class="col-span-2 space-y-1.5">
          <span class="text-[11px] font-semibold text-slate-500">页面留白</span>
          <input
            :value="String(modelValue.placement.padding)"
            type="text"
            inputmode="numeric"
            class="h-9 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm font-medium text-slate-700 outline-none transition focus:border-indigo-500 focus:bg-white"
            @input="updatePlacementNumberField('padding', ($event.target as HTMLInputElement).value)"
            @blur="normalizePlacementNumberField('padding')"
          >
        </label>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import {
  AlignHorizontalJustifyCenter,
  AlignHorizontalJustifyEnd,
  AlignHorizontalJustifyStart,
  AlignVerticalJustifyCenter,
  AlignVerticalJustifyEnd,
  AlignVerticalJustifyStart,
  ChevronDown,
} from '@lucide/vue'

import BaseButton from '@/components/ui/BaseButton.vue'
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

type SizeModeField = 'width_mode' | 'height_mode'

const sizeModeOptions: Array<{
  value: ComponentPreviewSizeMode
  label: string
}> = [
  { value: 'percent', label: '%' },
  { value: 'fixed', label: 'px' },
  { value: 'auto', label: 'auto' },
]
const sizeModeDropdownVisible = ref(false)
const sizeModeDropdownField = ref<SizeModeField | null>(null)
const sizeModeDropdownStyle = ref<Record<string, string>>({})

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

onMounted(() => {
  document.addEventListener('mousedown', closeSizeModeDropdown)
  window.addEventListener('resize', closeSizeModeDropdown)
  document.addEventListener('scroll', closeSizeModeDropdown, true)
})

onUnmounted(() => {
  document.removeEventListener('mousedown', closeSizeModeDropdown)
  window.removeEventListener('resize', closeSizeModeDropdown)
  document.removeEventListener('scroll', closeSizeModeDropdown, true)
})

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
 * 打开尺寸单位下拉，并根据触发按钮计算浮层位置。
 * @param field 当前编辑的尺寸模式字段
 * @param event 点击事件
 */
function openSizeModeDropdown(field: SizeModeField, event: MouseEvent) {
  const trigger = event.currentTarget as HTMLElement | null
  if (!trigger) {
    return
  }
  if (sizeModeDropdownVisible.value && sizeModeDropdownField.value === field) {
    closeSizeModeDropdown()
    return
  }

  const rect = trigger.getBoundingClientRect()
  const margin = 8
  const panelWidth = Math.max(rect.width + 22, 84)
  const left = Math.min(rect.left, window.innerWidth - panelWidth - margin)
  sizeModeDropdownField.value = field
  sizeModeDropdownStyle.value = {
    top: `${rect.bottom + 6}px`,
    left: `${Math.max(margin, left)}px`,
    width: `${panelWidth}px`,
  }
  sizeModeDropdownVisible.value = true
}

/**
 * 关闭当前展开的尺寸单位下拉。
 */
function closeSizeModeDropdown() {
  sizeModeDropdownVisible.value = false
  sizeModeDropdownField.value = null
}

/**
 * 选择尺寸单位，并同步到预览占位配置。
 * @param value 尺寸模式
 */
function selectSizeModeOption(value: ComponentPreviewSizeMode) {
  if (!sizeModeDropdownField.value) {
    return
  }
  updatePlacementField(sizeModeDropdownField.value, value)
  closeSizeModeDropdown()
}

/**
 * 判断浮层中的尺寸模式是否为当前字段选中项。
 * @param value 尺寸模式
 * @returns 是否选中
 */
function isSizeModeOptionActive(value: ComponentPreviewSizeMode) {
  if (sizeModeDropdownField.value === 'width_mode') {
    return props.modelValue.placement.width_mode === value
  }
  if (sizeModeDropdownField.value === 'height_mode') {
    return props.modelValue.placement.height_mode === value
  }
  return false
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

<style scoped>
.size-mode-fade-enter-active,
.size-mode-fade-leave-active {
  transition: opacity 0.12s ease, transform 0.12s ease;
}

.size-mode-fade-enter-from,
.size-mode-fade-leave-to {
  opacity: 0;
  transform: translateY(-3px);
}
</style>
