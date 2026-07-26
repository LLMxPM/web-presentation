<!-- 文件功能：基于 Reka UI 提供键盘可操作的标准单选/多选选择器。 -->
<template>
  <SelectRoot :model-value="modelValue" :multiple="multiple" :disabled="disabled" @update:model-value="emit('update:modelValue', $event as SelectModelValue)">
    <SelectTrigger
      v-bind="$attrs"
      class="flex h-8 w-full items-center justify-between gap-2 rounded-md border border-border-strong bg-surface px-2 text-left text-sm text-text-emphasis outline-none hover:border-border-strong focus-visible:ring-2 focus-visible:ring-border-focus disabled:cursor-not-allowed disabled:bg-canvas disabled:text-text-disabled"
      :class="triggerClass"
    >
      <span class="min-w-0 flex-1 truncate"><SelectValue :placeholder="placeholder" /></span>
      <ChevronDown class="h-4 w-4 shrink-0 text-text-disabled" />
    </SelectTrigger>
    <SelectPortal><SelectContent position="popper" :side-offset="6" class="z-dropdown max-h-72 min-w-[var(--reka-select-trigger-width)] max-w-[var(--reka-select-content-available-width)] overflow-hidden rounded-lg border border-border bg-surface p-1 shadow-lg">
      <SelectViewport class="max-h-72 overflow-y-auto"><SelectItem v-for="option in options" :key="String(option.value)" :value="option.value" :disabled="option.disabled" class="relative flex cursor-default select-none items-center rounded-md py-1.5 pl-7 pr-2 text-sm text-text-emphasis outline-none data-[highlighted]:bg-surface-muted data-[state=checked]:font-medium data-[disabled]:opacity-40"><span class="absolute left-2 flex h-3.5 w-3.5 items-center justify-center"><SelectItemIndicator><Check class="h-3.5 w-3.5 text-accent" /></SelectItemIndicator></span><span class="min-w-0 truncate" :title="option.label"><SelectItemText>{{ option.label }}</SelectItemText></span></SelectItem></SelectViewport>
    </SelectContent></SelectPortal>
  </SelectRoot>
</template>
<script setup lang="ts">
import { Check, ChevronDown } from '@lucide/vue'
import { SelectContent, SelectItem, SelectItemIndicator, SelectItemText, SelectPortal, SelectRoot, SelectTrigger, SelectValue, SelectViewport } from 'reka-ui'
import type { SelectModelValue, SelectOption } from '../select'

defineOptions({ inheritAttrs: false })

withDefaults(defineProps<{ modelValue: SelectModelValue; options: SelectOption[]; multiple?: boolean; disabled?: boolean; placeholder?: string; triggerClass?: string }>(), { multiple: false, disabled: false, placeholder: '请选择' })
const emit = defineEmits<{ 'update:modelValue': [value: SelectModelValue] }>()
</script>
