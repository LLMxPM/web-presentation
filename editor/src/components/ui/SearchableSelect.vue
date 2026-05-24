<!-- 文件功能：提供支持搜索、单选/多选和浮层定位的通用下拉选择组件。 -->
<template>
  <div ref="rootRef" class="relative">
    <div
      ref="triggerRef"
      class="w-full rounded-xl border border-slate-200 bg-white text-sm transition"
      :class="[triggerContainerClass, disabled ? 'cursor-not-allowed bg-slate-50 text-slate-400' : 'cursor-pointer hover:border-slate-300']"
    >
      <div class="flex items-center gap-2" :class="size === 'compact' ? 'h-full' : ''">
        <button
          type="button"
          class="min-w-0 flex-1 text-left"
          :disabled="disabled"
          @click="toggleDropdown"
        >
          <div v-if="!selectedOptions.length" class="truncate text-slate-400">
            {{ placeholder }}
          </div>
          <div v-else-if="multiple" class="flex flex-wrap gap-1">
            <span
              v-for="option in visibleSelectedOptions"
              :key="`selected-${String(option.value)}`"
              class="inline-flex max-w-full items-center rounded-full bg-indigo-50 px-2 py-1 text-[11px] font-semibold text-indigo-700"
            >
              <span class="truncate">{{ option.label }}</span>
            </span>
            <span
              v-if="hiddenSelectedCount > 0"
              class="inline-flex items-center rounded-full bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-500"
            >
              +{{ hiddenSelectedCount }}
            </span>
          </div>
          <div v-else class="min-w-0">
            <div class="truncate font-medium text-slate-700">{{ selectedOptions[0]?.label }}</div>
            <div
              v-if="showSingleDescription && selectedOptions[0]?.description"
              class="truncate text-[11px] text-slate-400"
            >
              {{ selectedOptions[0]?.description }}
            </div>
          </div>
        </button>

        <button
          v-if="clearable && selectedOptions.length > 0 && !disabled"
          type="button"
          class="rounded-md p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
          title="清空选择"
          @click.stop="clearSelection"
        >
          <X class="h-4 w-4" />
        </button>
        <button
          type="button"
          class="rounded-md p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
          :disabled="disabled"
          :title="open ? '收起选项' : '展开选项'"
          @click="toggleDropdown"
        >
          <ChevronDown class="h-4 w-4 transition-transform duration-200" :class="open ? 'rotate-180' : ''" />
        </button>
      </div>
    </div>

    <Teleport to="body">
      <Transition name="select-fade">
        <div
          v-if="open"
          ref="dropdownRef"
          class="fixed z-[1600] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl"
          :style="dropdownStyle"
        >
          <div class="border-b border-slate-100 px-3 py-3">
            <label v-if="searchable" class="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3">
              <Search class="h-4 w-4 text-slate-400" />
              <input
                ref="searchInputRef"
                v-model="searchKeyword"
                type="text"
                class="h-10 min-w-0 flex-1 bg-transparent text-sm text-slate-700 outline-none placeholder:text-slate-400"
                :placeholder="searchPlaceholder"
                @keydown.esc.prevent="closeDropdown"
              >
            </label>

            <div
              v-if="multiple && selectedOptions.length > 0"
              class="mt-2 flex items-center justify-between gap-3 text-[11px] text-slate-500"
            >
              <span>已选 {{ selectedOptions.length }} 项</span>
              <button type="button" class="font-semibold text-indigo-600 hover:text-indigo-700" @click="clearSelection">
                清空
              </button>
            </div>
          </div>

          <div class="overflow-y-auto" :style="{ maxHeight: `${optionsPanelMaxHeight}px` }">
            <button
              v-for="option in filteredOptions"
              :key="String(option.value)"
              type="button"
              class="flex w-full items-center gap-3 px-4 py-3 text-left transition"
              :class="resolveOptionClass(option)"
              :disabled="option.disabled"
              @click="handleOptionSelect(option)"
            >
              <div class="flex h-5 w-5 shrink-0 items-center justify-center rounded-md border"
                :class="isOptionSelected(option.value)
                  ? 'border-indigo-500 bg-indigo-500 text-white'
                  : 'border-slate-200 bg-white text-transparent'"
              >
                <Check class="h-3.5 w-3.5" />
              </div>
              <div class="min-w-0 flex-1">
                <div class="truncate text-sm font-medium">{{ option.label }}</div>
                <div v-if="option.description" class="truncate text-[11px] text-slate-400">
                  {{ option.description }}
                </div>
              </div>
            </button>

            <div v-if="filteredOptions.length === 0" class="px-4 py-8 text-center text-sm text-slate-400">
              {{ emptyText }}
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { Check, ChevronDown, Search, X } from '@lucide/vue'

import type { SelectModelValue, SelectOption, SelectPrimitive } from './select'

const props = withDefaults(defineProps<{
  modelValue: SelectModelValue
  options: SelectOption[]
  multiple?: boolean
  searchable?: boolean
  placeholder?: string
  searchPlaceholder?: string
  emptyText?: string
  clearable?: boolean
  disabled?: boolean
  maxVisibleTags?: number
  size?: 'default' | 'compact'
}>(), {
  multiple: false,
  searchable: true,
  placeholder: '请选择',
  searchPlaceholder: '搜索选项',
  emptyText: '没有匹配的选项。',
  clearable: false,
  disabled: false,
  maxVisibleTags: 3,
  size: 'default',
})

const emit = defineEmits<{
  'update:modelValue': [value: SelectModelValue]
}>()

const rootRef = ref<HTMLElement | null>(null)
const triggerRef = ref<HTMLElement | null>(null)
const dropdownRef = ref<HTMLElement | null>(null)
const searchInputRef = ref<HTMLInputElement | null>(null)

const open = ref(false)
const searchKeyword = ref('')
const panelMaxHeight = ref(348)
const optionsPanelMaxHeight = ref(280)
const dropdownStyle = ref<Record<string, string>>({})

const normalizedSelectedValues = computed<SelectPrimitive[]>(() => {
  if (props.multiple) {
    return Array.isArray(props.modelValue) ? props.modelValue : []
  }
  if (Array.isArray(props.modelValue) || props.modelValue == null) {
    return []
  }
  return [props.modelValue]
})

const selectedOptions = computed(() => normalizedSelectedValues.value
  .map(value => props.options.find(option => option.value === value))
  .filter((option): option is SelectOption => Boolean(option)))

const visibleSelectedOptions = computed(() => selectedOptions.value.slice(0, props.maxVisibleTags))
const hiddenSelectedCount = computed(() => Math.max(0, selectedOptions.value.length - visibleSelectedOptions.value.length))
const triggerContainerClass = computed(() => (
  props.size === 'compact'
    ? 'h-9 px-3 py-0'
    : 'min-h-10 px-3 py-2'
))
const showSingleDescription = computed(() => props.size !== 'compact')

const filteredOptions = computed(() => {
  const keyword = searchKeyword.value.trim().toLowerCase()
  if (!keyword) {
    return props.options
  }
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

watch(() => props.disabled, (disabled) => {
  if (disabled) {
    closeDropdown()
  }
})

watch(open, async (visible) => {
  if (!visible) {
    searchKeyword.value = ''
    return
  }
  await nextTick()
  syncDropdownPosition()
  if (props.searchable) {
    searchInputRef.value?.focus()
  }
})

/**
 * 打开或关闭下拉面板，并在展开后同步浮层位置。
 */
function toggleDropdown() {
  if (props.disabled) {
    return
  }
  open.value = !open.value
}

/**
 * 关闭下拉面板，并清空本轮搜索关键字。
 */
function closeDropdown() {
  open.value = false
}

/**
 * 根据视口空间同步下拉浮层位置，避免弹层被对话框裁切。
 */
function syncDropdownPosition() {
  if (!open.value || !triggerRef.value) {
    return
  }

  const rect = triggerRef.value.getBoundingClientRect()
  const margin = 12
  const panelWidth = Math.max(rect.width, 280)
  const spaceBelow = window.innerHeight - rect.bottom - margin
  const spaceAbove = rect.top - margin
  const shouldOpenAbove = spaceBelow < 260 && spaceAbove > spaceBelow
  const availableHeight = Math.max(180, Math.min(360, shouldOpenAbove ? spaceAbove : spaceBelow))
  panelMaxHeight.value = availableHeight
  const top = shouldOpenAbove
    ? Math.max(margin, rect.top - panelMaxHeight.value - 8)
    : Math.min(window.innerHeight - margin - panelMaxHeight.value, rect.bottom + 8)
  const left = Math.min(rect.left, window.innerWidth - panelWidth - margin)

  optionsPanelMaxHeight.value = Math.max(140, panelMaxHeight.value - 68)
  dropdownStyle.value = {
    top: `${top}px`,
    left: `${Math.max(margin, left)}px`,
    width: `${panelWidth}px`,
    maxHeight: `${panelMaxHeight.value}px`,
  }
}

/**
 * 判断给定值是否已经处于选中态。
 * @param value 选项值
 */
function isOptionSelected(value: SelectPrimitive) {
  return normalizedSelectedValues.value.includes(value)
}

/**
 * 处理单个选项的点击逻辑，兼容单选和多选两种输出模型。
 * @param option 当前点击的选项
 */
function handleOptionSelect(option: SelectOption) {
  if (option.disabled) {
    return
  }

  if (!props.multiple) {
    emit('update:modelValue', option.value)
    closeDropdown()
    return
  }

  const nextValues = [...normalizedSelectedValues.value]
  const currentIndex = nextValues.findIndex(value => value === option.value)
  if (currentIndex >= 0) {
    nextValues.splice(currentIndex, 1)
  } else {
    nextValues.push(option.value)
  }
  emit('update:modelValue', nextValues)
}

/**
 * 清空当前选择，单选返回 null，多选返回空数组。
 */
function clearSelection() {
  emit('update:modelValue', props.multiple ? [] : null)
}

/**
 * 返回选项的行样式，统一处理 hover、禁用和激活态。
 * @param option 当前选项
 */
function resolveOptionClass(option: SelectOption) {
  if (option.disabled) {
    return 'cursor-not-allowed text-slate-300'
  }
  if (isOptionSelected(option.value)) {
    return 'bg-indigo-50 text-indigo-700'
  }
  return 'text-slate-700 hover:bg-slate-50'
}

/**
 * 监听全局点击，在点击组件外部时关闭浮层。
 * @param event 原始鼠标事件
 */
function handleDocumentPointerDown(event: MouseEvent) {
  if (!open.value) {
    return
  }
  const target = event.target as Node | null
  if (!target) {
    return
  }
  if (rootRef.value?.contains(target) || dropdownRef.value?.contains(target)) {
    return
  }
  closeDropdown()
}

/**
 * 响应全局键盘事件，支持 Escape 关闭当前面板。
 * @param event 键盘事件
 */
function handleWindowKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && open.value) {
    closeDropdown()
  }
}

/**
 * 在窗口尺寸或滚动容器变化时，重新计算浮层位置。
 */
function handleViewportChange() {
  syncDropdownPosition()
}

onMounted(() => {
  document.addEventListener('mousedown', handleDocumentPointerDown)
  window.addEventListener('keydown', handleWindowKeydown)
  window.addEventListener('resize', handleViewportChange)
  document.addEventListener('scroll', handleViewportChange, true)
})

onUnmounted(() => {
  document.removeEventListener('mousedown', handleDocumentPointerDown)
  window.removeEventListener('keydown', handleWindowKeydown)
  window.removeEventListener('resize', handleViewportChange)
  document.removeEventListener('scroll', handleViewportChange, true)
})
</script>

<style scoped>
.select-fade-enter-active,
.select-fade-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.select-fade-enter-from,
.select-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
