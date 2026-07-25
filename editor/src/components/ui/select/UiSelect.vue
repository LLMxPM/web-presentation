<!-- 文件功能：基于 Reka UI 提供键盘可操作的标准单选/多选选择器。 -->
<template>
  <SelectRoot :model-value="modelValue" :multiple="multiple" :disabled="disabled" @update:model-value="emit('update:modelValue', $event as SelectModelValue)">
    <SelectTrigger class="flex h-8 w-full items-center justify-between gap-2 rounded-md border border-slate-300 bg-white px-2 text-left text-sm text-slate-700 outline-none hover:border-slate-400 focus-visible:ring-2 focus-visible:ring-indigo-500 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400" :class="triggerClass"><SelectValue :placeholder="placeholder" /><ChevronDown class="h-4 w-4 shrink-0 text-slate-400" /></SelectTrigger>
    <SelectPortal><SelectContent position="popper" :side-offset="6" class="z-dropdown max-h-72 min-w-[var(--reka-select-trigger-width)] overflow-hidden rounded-lg border border-slate-200 bg-white p-1 shadow-lg">
      <SelectViewport class="max-h-72 overflow-y-auto"><SelectItem v-for="option in options" :key="String(option.value)" :value="option.value" :disabled="option.disabled" class="relative flex cursor-default select-none items-center rounded-md py-1.5 pl-7 pr-2 text-sm text-slate-700 outline-none data-[highlighted]:bg-slate-100 data-[state=checked]:font-medium data-[disabled]:opacity-40"><span class="absolute left-2 flex h-3.5 w-3.5 items-center justify-center"><SelectItemIndicator><Check class="h-3.5 w-3.5 text-indigo-600" /></SelectItemIndicator></span><SelectItemText>{{ option.label }}</SelectItemText></SelectItem></SelectViewport>
    </SelectContent></SelectPortal>
  </SelectRoot>
</template>
<script setup lang="ts">
import { Check, ChevronDown } from '@lucide/vue'
import { SelectContent, SelectItem, SelectItemIndicator, SelectItemText, SelectPortal, SelectRoot, SelectTrigger, SelectValue, SelectViewport } from 'reka-ui'
import type { SelectModelValue, SelectOption } from '../select'

withDefaults(defineProps<{ modelValue: SelectModelValue; options: SelectOption[]; multiple?: boolean; disabled?: boolean; placeholder?: string; triggerClass?: string }>(), { multiple: false, disabled: false, placeholder: '请选择' })
const emit = defineEmits<{ 'update:modelValue': [value: SelectModelValue] }>()
</script>
