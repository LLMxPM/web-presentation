<!-- 文件功能：提供单行、多行、密码输入及前后缀、清除和错误状态。 -->
<template>
  <div
    class="relative w-full"
    :class="textareaMode === 'fill' && type === 'textarea' ? 'flex min-h-0 flex-1 flex-col' : undefined"
  >
    <span v-if="$slots.prefix" class="pointer-events-none absolute inset-y-0 left-2 flex items-center text-[rgb(var(--ui-text-muted))]">
      <slot name="prefix" />
    </span>
    <textarea
      v-if="type === 'textarea'"
      :id="inputId"
      :value="modelValue"
      :rows="rows"
      :disabled="disabled"
      :required="required"
      :aria-invalid="invalid || undefined"
      :aria-describedby="describedBy"
      :class="controlClass"
      v-bind="$attrs"
      @input="handleInput"
    />
    <input
      v-else
      :id="inputId"
      :type="resolvedType"
      :value="modelValue"
      :disabled="disabled"
      :required="required"
      :aria-invalid="invalid || undefined"
      :aria-describedby="describedBy"
      :class="controlClass"
      v-bind="$attrs"
      @input="handleInput"
    >
    <span v-if="$slots.suffix" class="pointer-events-none absolute inset-y-0 right-2 flex items-center text-[rgb(var(--ui-text-muted))]">
      <slot name="suffix" />
    </span>
    <button
      v-if="clearable && modelValue !== '' && !disabled"
      type="button"
      class="absolute inset-y-0 right-1 inline-flex w-8 items-center justify-center rounded-[var(--ui-radius-sm)] text-[rgb(var(--ui-text-muted))] hover:text-[rgb(var(--ui-text))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgb(var(--ui-border-focus))]"
      aria-label="清除输入内容"
      @click="clearValue"
    >
      <span aria-hidden="true">×</span>
    </button>
    <button
      v-if="passwordToggle && type === 'password'"
      type="button"
      class="absolute inset-y-0 right-1 inline-flex w-8 items-center justify-center rounded-[var(--ui-radius-sm)] text-[rgb(var(--ui-text-muted))] hover:text-[rgb(var(--ui-text))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgb(var(--ui-border-focus))]"
      :aria-label="showPassword ? '隐藏密码' : '显示密码'"
      @click="showPassword = !showPassword"
    >
      <component :is="showPassword ? EyeOff : Eye" class="h-4 w-4" aria-hidden="true" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, useSlots } from 'vue'
import { Eye, EyeOff } from '@lucide/vue'

defineOptions({ inheritAttrs: false })

const props = withDefaults(defineProps<{
  /** 受控输入值；所有原生输入统一以字符串回传。 */
  modelValue?: string | number
  /** 原生输入类型，textarea 用于兼容迁移期多行输入。 */
  type?: string
  /** 多行输入布局；fill 会填满父级剩余高度，并在内容超出时内部滚动。 */
  textareaMode?: 'fixed' | 'fill'
  rows?: number
  disabled?: boolean
  required?: boolean
  invalid?: boolean
  inputId?: string
  describedBy?: string
  clearable?: boolean
  /** 密码显隐属于兼容能力；新页面可自行组合后缀按钮。 */
  passwordToggle?: boolean
}>(), {
  modelValue: '',
  type: 'text',
  textareaMode: 'fixed',
  rows: 3,
  disabled: false,
  required: false,
  invalid: false,
  clearable: false,
  passwordToggle: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  clear: []
}>()

const slots = useSlots()
const showPassword = ref(false)
const resolvedType = computed(() => props.type === 'password' && props.passwordToggle && showPassword.value ? 'text' : props.type)
const hasPrefix = computed(() => Boolean(slots.prefix))
const hasSuffix = computed(() => Boolean(slots.suffix))
const controlClass = computed(() => [
  'block w-full rounded-[var(--ui-radius-md)] border bg-[rgb(var(--ui-surface))] px-2.5 text-sm text-[rgb(var(--ui-text))] outline-none transition-colors duration-150',
  'placeholder:text-[rgb(var(--ui-text-muted))] hover:border-[rgb(var(--ui-border-strong))] focus:border-[rgb(var(--ui-border-focus))] focus:ring-2 focus:ring-[rgb(var(--ui-border-focus))]/25 disabled:cursor-not-allowed disabled:bg-[rgb(var(--ui-surface-muted))] disabled:text-[rgb(var(--ui-text-disabled))]',
  props.type === 'textarea'
    ? props.textareaMode === 'fill'
      ? 'h-full min-h-0 flex-1 overflow-y-auto py-2 resize-none'
      : 'min-h-20 py-2 resize-y'
    : 'h-[var(--ui-control-h-md)]',
  {
    'border-[rgb(var(--ui-danger))] focus:border-[rgb(var(--ui-danger))] focus:ring-[rgb(var(--ui-danger))]/20': props.invalid,
    'pl-8': hasPrefix.value,
    'pr-9': hasSuffix.value || props.clearable || (props.passwordToggle && props.type === 'password'),
  },
])

/** 将浏览器输入事件转换为统一 v-model 更新。 */
function handleInput(event: Event) {
  emit('update:modelValue', (event.target as HTMLInputElement | HTMLTextAreaElement).value)
}

/** 清空值并通知调用方，用于搜索框等可清除输入。 */
function clearValue() {
  emit('update:modelValue', '')
  emit('clear')
}
</script>
