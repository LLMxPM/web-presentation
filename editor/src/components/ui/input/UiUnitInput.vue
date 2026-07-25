<!-- 文件功能：提供数值与固定单位分离展示的文本输入，并维持带单位字符串的数据契约。 -->
<template>
  <div :class="rootClass">
    <input
      :id="inputId"
      ref="inputRef"
      :value="draftValue"
      type="text"
      :inputmode="integer ? 'numeric' : 'decimal'"
      :placeholder="placeholder"
      :disabled="disabled"
      :required="required"
      :aria-invalid="invalid || undefined"
      :aria-describedby="describedBy"
      :class="inputClass"
      v-bind="$attrs"
      @focus="focused = true"
      @input="handleInput"
      @blur="commitValue"
    >
    <span :class="unitClass" aria-hidden="true">{{ unit }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

defineOptions({ inheritAttrs: false })

const props = withDefaults(defineProps<{
  /** 对外保留的带单位值，例如 20px。 */
  modelValue?: string | number
  /** 固定展示并拼接到输出值末尾的单位。 */
  unit: string
  min?: number
  max?: number
  integer?: boolean
  fallback?: number
  appearance?: 'default' | 'bare'
  placeholder?: string
  disabled?: boolean
  required?: boolean
  invalid?: boolean
  inputId?: string
  describedBy?: string
}>(), {
  modelValue: '',
  min: Number.NEGATIVE_INFINITY,
  max: Number.POSITIVE_INFINITY,
  integer: false,
  fallback: 0,
  appearance: 'default',
  placeholder: '',
  disabled: false,
  required: false,
  invalid: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  blur: [event: FocusEvent]
}>()

const inputRef = ref<HTMLInputElement | null>(null)
const focused = ref(false)
const draftValue = ref(extractNumericText(props.modelValue))

const rootClass = computed(() => [
  'flex w-full items-stretch overflow-hidden',
  props.appearance === 'default'
    ? 'h-[var(--ui-control-h-md)] rounded-[var(--ui-radius-md)] border bg-[rgb(var(--ui-surface))] transition-colors duration-150 focus-within:border-[rgb(var(--ui-border-focus))] focus-within:ring-2 focus-within:ring-[rgb(var(--ui-border-focus))]/25 hover:border-[rgb(var(--ui-border-strong))]'
    : 'h-full bg-transparent',
  {
    'border-[rgb(var(--ui-danger))] focus-within:border-[rgb(var(--ui-danger))] focus-within:ring-[rgb(var(--ui-danger))]/20': props.invalid,
    'cursor-not-allowed bg-[rgb(var(--ui-surface-muted))]': props.disabled,
  },
])

const inputClass = computed(() => [
  'block h-full min-w-0 flex-1 bg-transparent px-2.5 text-sm text-[rgb(var(--ui-text))] outline-none',
  'placeholder:text-[rgb(var(--ui-text-muted))] disabled:cursor-not-allowed disabled:text-[rgb(var(--ui-text-disabled))]',
  props.appearance === 'bare' ? 'px-1 text-center text-xs font-semibold tabular-nums' : '',
])

const unitClass = computed(() => [
  'flex shrink-0 select-none items-center border-l border-[rgb(var(--ui-border))] text-[rgb(var(--ui-text-muted))]',
  props.appearance === 'bare' ? 'px-2 text-xs' : 'bg-[rgb(var(--ui-surface-muted))] px-2.5 text-sm',
])

watch(
  () => props.modelValue,
  (value) => {
    if (!focused.value) {
      draftValue.value = extractNumericText(value)
    }
  },
)

/**
 * 从带单位值中提取可编辑的数值部分。
 * @param value 外部传入值
 */
function extractNumericText(value: string | number): string {
  const rawValue = String(value ?? '').trim()
  if (!rawValue) {
    return ''
  }
  const escapedUnit = props.unit.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return rawValue.replace(new RegExp(`${escapedUnit}$`, 'i'), '').trim()
}

/**
 * 接收输入草稿；合法且位于范围内时立即同步带单位值。
 * @param event 原生输入事件
 */
function handleInput(event: Event): void {
  const value = (event.target as HTMLInputElement).value
  const numericPattern = props.integer ? /^\d*$/ : /^\d*(?:\.\d*)?$/
  if (!numericPattern.test(value)) {
    if (inputRef.value) {
      inputRef.value.value = draftValue.value
    }
    return
  }
  draftValue.value = value
  const parsedValue = Number(value)
  if (value !== '' && Number.isFinite(parsedValue) && parsedValue >= props.min && parsedValue <= props.max) {
    emit('update:modelValue', `${value}${props.unit}`)
  }
}

/**
 * 失焦时补齐空值、整数和范围约束，并输出稳定的带单位值。
 * @param event 原生失焦事件
 */
function commitValue(event: FocusEvent): void {
  focused.value = false
  const parsedValue = Number(draftValue.value)
  const fallbackValue = Number(extractNumericText(props.modelValue))
  const safeFallback = Number.isFinite(fallbackValue) ? fallbackValue : props.fallback
  const sourceValue = draftValue.value !== '' && Number.isFinite(parsedValue) ? parsedValue : safeFallback
  const boundedValue = Math.min(props.max, Math.max(props.min, sourceValue))
  const normalizedValue = props.integer ? Math.round(boundedValue) : boundedValue
  draftValue.value = String(normalizedValue)
  emit('update:modelValue', `${normalizedValue}${props.unit}`)
  emit('blur', event)
}
</script>
