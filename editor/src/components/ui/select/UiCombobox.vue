<!-- 文件功能：为可搜索选择场景提供 Reka UI 组合框的稳定组件入口。 -->
<template>
  <ComboboxRoot :model-value="modelValue" :multiple="multiple" :disabled="disabled" :open="open" @update:model-value="emit('update:modelValue', $event as SelectModelValue)" @update:open="emit('update:open', $event)">
    <ComboboxAnchor class="flex h-8 w-full items-center rounded-md border border-slate-300 bg-white px-2 focus-within:ring-2 focus-within:ring-indigo-500" :class="anchorClass"><ComboboxInput class="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-slate-400" :placeholder="placeholder" /><ComboboxTrigger class="p-1 text-slate-400"><ChevronDown class="h-4 w-4" /></ComboboxTrigger></ComboboxAnchor>
    <ComboboxPortal><ComboboxContent class="z-[900] max-h-72 min-w-[var(--reka-combobox-trigger-width)] overflow-hidden rounded-lg border border-slate-200 bg-white p-1 shadow-lg"><ComboboxViewport class="max-h-72 overflow-y-auto"><ComboboxEmpty class="px-2 py-4 text-center text-sm text-slate-400">{{ emptyText }}</ComboboxEmpty><ComboboxItem v-for="option in options" :key="String(option.value)" :value="option.value" :disabled="option.disabled" class="flex cursor-default items-center gap-2 rounded-md px-2 py-1.5 text-sm text-slate-700 outline-none data-[highlighted]:bg-slate-100 data-[disabled]:opacity-40"><ComboboxItemIndicator><Check class="h-3.5 w-3.5 text-indigo-600" /></ComboboxItemIndicator>{{ option.label }}</ComboboxItem></ComboboxViewport></ComboboxContent></ComboboxPortal>
  </ComboboxRoot>
</template>
<script setup lang="ts">
import { Check, ChevronDown } from '@lucide/vue'
import { ComboboxAnchor, ComboboxContent, ComboboxEmpty, ComboboxInput, ComboboxItem, ComboboxItemIndicator, ComboboxPortal, ComboboxRoot, ComboboxTrigger, ComboboxViewport } from 'reka-ui'
import type { SelectModelValue, SelectOption } from '../select'

withDefaults(defineProps<{ modelValue: SelectModelValue; options: SelectOption[]; open?: boolean; multiple?: boolean; disabled?: boolean; placeholder?: string; emptyText?: string; anchorClass?: string }>(), { open: undefined, multiple: false, disabled: false, placeholder: '搜索或选择', emptyText: '没有匹配的选项。' })
const emit = defineEmits<{ 'update:modelValue': [value: SelectModelValue]; 'update:open': [value: boolean] }>()
</script>
