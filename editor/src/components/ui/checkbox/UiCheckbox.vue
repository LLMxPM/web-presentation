<!-- 文件功能：基于 Reka UI 提供支持半选状态的复选框。 -->
<template>
  <CheckboxRoot :model-value="modelValue" :disabled="disabled" class="flex h-4 w-4 shrink-0 items-center justify-center rounded border border-slate-300 bg-white text-white outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 disabled:cursor-not-allowed disabled:opacity-50 data-[state=checked]:border-indigo-600 data-[state=checked]:bg-indigo-600" @update:model-value="emit('update:modelValue', $event)">
    <CheckboxIndicator><Check v-if="modelValue !== 'indeterminate'" class="h-3 w-3" /><Minus v-else class="h-3 w-3" /></CheckboxIndicator>
  </CheckboxRoot>
</template>
<script setup lang="ts">
import { Check, Minus } from '@lucide/vue'
import { CheckboxIndicator, CheckboxRoot } from 'reka-ui'
defineProps<{ modelValue: boolean | 'indeterminate'; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean | 'indeterminate'] }>()
</script>
