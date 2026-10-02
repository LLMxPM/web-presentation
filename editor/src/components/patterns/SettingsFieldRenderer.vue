<!-- 文件功能：统一配置字段渲染器，根据配置类型自动组装表单控件、描述文本与环境变量覆盖标识。 -->
<template>
  <div v-if="type === 'boolean'" class="flex items-center justify-between rounded-lg border border-border-muted p-4 bg-surface-muted/20">
    <div class="space-y-0.5">
      <div :id="booleanLabelId" class="text-sm font-semibold text-text">{{ label }}</div>
      <div v-if="description" class="text-xs text-text-muted">{{ description }}</div>
    </div>
    <div class="flex items-center gap-2">
      <UiBadge v-if="envOverridden" tone="accent">ENV 覆盖</UiBadge>
      <UiCheckbox
        :aria-labelledby="booleanLabelId"
        :model-value="Boolean(modelValue)"
        :disabled="disabled || envOverridden"
        @update:model-value="emit('update:modelValue', $event)"
      />
    </div>
  </div>

  <UiFormField v-else :label="label" :description="description" v-slot="field">
    <div class="flex items-center gap-2">
      <UiSelect
        v-if="type === 'select'"
        :model-value="(modelValue as any)"
        :options="options || []"
        :id="field.inputId"
        :aria-describedby="field.describedBy"
        :disabled="disabled || envOverridden"
        class="w-full"
        @update:model-value="emit('update:modelValue', $event)"
      />

      <UiInput
        v-else-if="type === 'number'"
        :model-value="(modelValue as any)"
        type="number"
        :input-id="field.inputId"
        :described-by="field.describedBy"
        :min="min"
        :max="max"
        :placeholder="placeholder"
        :disabled="disabled || envOverridden"
        @update:model-value="emit('update:modelValue', $event === '' ? '' : Number($event))"
      />

      <UiInput
        v-else-if="type === 'password'"
        :model-value="(modelValue as any)"
        type="password"
        :input-id="field.inputId"
        :described-by="field.describedBy"
        password-toggle
        :placeholder="placeholder"
        :disabled="disabled || envOverridden"
        @update:model-value="emit('update:modelValue', String($event))"
      />

      <UiInput
        v-else
        :input-id="field.inputId"
        :described-by="field.describedBy"
        :model-value="(modelValue as any)"
        :placeholder="placeholder"
        :disabled="disabled || envOverridden"
        @update:model-value="emit('update:modelValue', String($event))"
      />

      <UiBadge v-if="envOverridden" tone="accent">ENV 覆盖</UiBadge>
    </div>
  </UiFormField>
</template>

<script setup lang="ts">
import { useId } from 'vue'
import { UiBadge, UiCheckbox, UiFormField, UiInput, UiSelect } from '@/components/ui'
import type { SelectOption } from '@/components/ui/select'

const booleanLabelId = `setting-label-${useId()}`

/**
 * 设置字段渲染器输入属性。
 */
defineProps<{
  /** 表单字段标签 */
  label: string
  /** 辅助说明文案 */
  description?: string
  /** 控件渲染类型 */
  type?: 'text' | 'number' | 'password' | 'select' | 'boolean'
  /** 绑定的值 */
  modelValue?: string | number | boolean | null | unknown
  /** 下拉选项列表（当 type 为 select 时生效） */
  options?: SelectOption[]
  /** 是否已被系统环境变量覆盖（锁定为只读状态） */
  envOverridden?: boolean
  /** 是否整体禁用 */
  disabled?: boolean
  /** 占位符文本 */
  placeholder?: string
  /** 数字最小值 */
  min?: number
  /** 数字最大值 */
  max?: number
}>()

const emit = defineEmits<{
  'update:modelValue': [value: unknown]
}>()
</script>
