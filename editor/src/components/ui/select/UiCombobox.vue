<!-- 文件功能：为可搜索选择场景提供 Reka UI 组合框的稳定组件入口，支持搜索过滤、描述、清空、compact 尺寸和多选标签。 -->
<template>
  <ComboboxRoot
    v-model:open="openState"
    :model-value="modelValue"
    :multiple="multiple"
    :disabled="disabled"
    :ignore-filter="true"
    :open-on-click="true"
    @update:model-value="handleValueUpdate"
  >
    <ComboboxAnchor
      class="flex w-full items-center rounded-ui-md border bg-white text-sm transition"
      :class="anchorClasses"
    >
      <!-- 多选标签区 -->
      <template v-if="multiple && selectedOptions.length > 0">
        <div class="flex min-w-0 flex-1 flex-wrap items-center gap-1">
          <span
            v-for="opt in visibleSelectedOptions"
            :key="String(opt.value)"
            class="inline-flex max-w-full items-center rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] font-semibold text-indigo-700"
          >
            <span class="truncate">{{ opt.label }}</span>
          </span>
          <span
            v-if="hiddenSelectedCount > 0"
            class="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-500"
          >
            +{{ hiddenSelectedCount }}
          </span>
          <ComboboxInput
            class="min-w-[60px] flex-1 bg-transparent text-sm outline-none placeholder:text-slate-400"
            :placeholder="searchPlaceholder"
            :model-value="searchKeyword"
            @update:model-value="searchKeyword = $event"
          />
        </div>
      </template>

      <!-- 单选展示区 -->
      <template v-else>
        <ComboboxInput
          class="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-slate-400"
          :placeholder="displayText || placeholder"
          :model-value="searchKeyword"
          :display-value="() => openState ? searchKeyword : (displayText || '')"
          @update:model-value="searchKeyword = $event"
        />
      </template>

      <!-- 清空按钮 -->
      <button
        v-if="clearable && hasSelection && !disabled"
        type="button"
        class="shrink-0 rounded p-0.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
        title="清空选择"
        @pointerdown.prevent="clearSelection"
      >
        <X class="h-3.5 w-3.5" />
      </button>

      <!-- 展开箭头 -->
      <ComboboxTrigger class="shrink-0 p-0.5 text-slate-400">
        <ChevronDown
          class="h-4 w-4 transition-transform duration-150"
          :class="openState ? 'rotate-180' : ''"
        />
      </ComboboxTrigger>
    </ComboboxAnchor>

    <ComboboxPortal>
      <ComboboxContent
        position="popper"
        :side-offset="4"
        class="z-dropdown max-h-72 min-w-[var(--reka-combobox-trigger-width)] overflow-hidden rounded-lg border border-slate-200 bg-white shadow-popover"
      >
        <ComboboxViewport class="max-h-72 overflow-y-auto p-1">
          <ComboboxEmpty class="px-3 py-6 text-center text-sm text-slate-400">
            {{ emptyText }}
          </ComboboxEmpty>
          <ComboboxItem
            v-for="option in filteredOptions"
            :key="String(option.value)"
            :value="option.value"
            :disabled="option.disabled"
            class="flex cursor-default items-center gap-2 rounded-md px-2 py-1.5 text-sm text-slate-700 outline-none data-[highlighted]:bg-slate-100 data-[disabled]:opacity-40"
          >
            <span
              v-if="multiple"
              class="flex h-4 w-4 shrink-0 items-center justify-center rounded border"
              :class="isSelected(option.value)
                ? 'border-indigo-500 bg-indigo-500 text-white'
                : 'border-slate-200 bg-white text-transparent'"
            >
              <Check class="h-3 w-3" />
            </span>
            <span
              v-else
              class="flex h-4 w-4 shrink-0 items-center justify-center text-indigo-600"
              :class="isSelected(option.value) ? 'visible' : 'invisible'"
            >
              <Check class="h-3.5 w-3.5" />
            </span>
            <div class="min-w-0 flex-1">
              <div class="truncate">{{ option.label }}</div>
              <div v-if="option.description" class="truncate text-[11px] text-slate-400">
                {{ option.description }}
              </div>
            </div>
          </ComboboxItem>
        </ComboboxViewport>
      </ComboboxContent>
    </ComboboxPortal>
  </ComboboxRoot>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Check, ChevronDown, X } from '@lucide/vue'
import {
  ComboboxAnchor,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxPortal,
  ComboboxRoot,
  ComboboxTrigger,
  ComboboxViewport,
} from 'reka-ui'
import type { SelectModelValue, SelectOption, SelectPrimitive } from '../select'

const props = withDefaults(defineProps<{
  modelValue: SelectModelValue
  options: SelectOption[]
  multiple?: boolean
  disabled?: boolean
  placeholder?: string
  searchPlaceholder?: string
  emptyText?: string
  clearable?: boolean
  size?: 'default' | 'compact'
  maxVisibleTags?: number
}>(), {
  multiple: false,
  disabled: false,
  placeholder: '请选择',
  searchPlaceholder: '搜索选项',
  emptyText: '没有匹配的选项。',
  clearable: false,
  size: 'default',
  maxVisibleTags: 3,
})

const emit = defineEmits<{
  'update:modelValue': [value: SelectModelValue]
}>()

/** 面板展开状态。 */
const openState = ref(false)

/** 搜索输入关键字。 */
const searchKeyword = ref('')

/** 面板开关切换时清空搜索关键字，避免已选项文本参与下一次过滤。 */
watch(openState, () => {
  searchKeyword.value = ''
})

/** 标准化的已选值数组。 */
const normalizedValues = computed<SelectPrimitive[]>(() => {
  if (props.multiple) {
    return Array.isArray(props.modelValue) ? props.modelValue : []
  }
  if (Array.isArray(props.modelValue) || props.modelValue == null) {
    return []
  }
  return [props.modelValue]
})

/** 已选中的完整选项对象。 */
const selectedOptions = computed(() =>
  normalizedValues.value
    .map(v => props.options.find(o => o.value === v))
    .filter((o): o is SelectOption => Boolean(o)),
)

/** 可见标签（受 maxVisibleTags 限制）。 */
const visibleSelectedOptions = computed(() =>
  selectedOptions.value.slice(0, props.maxVisibleTags),
)

/** 折叠的标签数量。 */
const hiddenSelectedCount = computed(() =>
  Math.max(0, selectedOptions.value.length - props.maxVisibleTags),
)

/** 是否存在选中项。 */
const hasSelection = computed(() => normalizedValues.value.length > 0)

/** 单选时显示的文本。 */
const displayText = computed(() => {
  if (props.multiple || !hasSelection.value) return ''
  return selectedOptions.value[0]?.label ?? ''
})

/** 根据关键字搜索过滤选项，匹配 label/description/value/keywords。 */
const filteredOptions = computed(() => {
  const keyword = openState.value
    ? searchKeyword.value.trim().toLowerCase()
    : ''
  if (!keyword) return props.options
  return props.options.filter((option) => {
    const haystacks = [
      option.label,
      option.description ?? '',
      String(option.value),
      ...(option.keywords ?? []),
    ]
    return haystacks.some(item => item.toLowerCase().includes(keyword))
  })
})

/** Anchor 样式类，区分 compact 和 default 尺寸以及禁用态。 */
const anchorClasses = computed(() => {
  const sizeClass = props.size === 'compact'
    ? 'h-9 px-2 py-0 gap-1'
    : 'min-h-[40px] px-3 py-1.5 gap-2'
  const stateClass = props.disabled
    ? 'border-slate-200 bg-slate-50 text-slate-400 cursor-not-allowed'
    : 'border-slate-200 hover:border-slate-300 focus-within:border-indigo-400 focus-within:ring-2 focus-within:ring-indigo-500/20 cursor-pointer'
  return [sizeClass, stateClass]
})

/**
 * 判断给定值是否已选中。
 * @param value 选项值
 */
function isSelected(value: SelectPrimitive) {
  return normalizedValues.value.includes(value)
}

/**
 * 处理值变更事件，单选时关闭面板。
 * @param value 新选中的值
 */
function handleValueUpdate(value: unknown) {
  emit('update:modelValue', value as SelectModelValue)
  if (!props.multiple) {
    openState.value = false
  }
}

/** 清空选择，单选返回 null，多选返回空数组。 */
function clearSelection() {
  emit('update:modelValue', props.multiple ? [] : null)
}
</script>
