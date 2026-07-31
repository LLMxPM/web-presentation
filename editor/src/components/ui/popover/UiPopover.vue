<!-- 文件功能：基于 Reka UI 提供统一的临时设置浮层。 -->
<template>
  <PopoverRoot :open="open" @update:open="emit('update:open', $event)">
    <PopoverTrigger as-child><slot name="trigger" /></PopoverTrigger>
    <PopoverPortal><PopoverContent :side="side" :align="align" :side-offset="sideOffset" class="z-popover rounded-lg border border-border bg-surface p-3 shadow-lg outline-none" :class="contentClass"><slot /></PopoverContent></PopoverPortal>
  </PopoverRoot>
</template>
<script setup lang="ts">
import { PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger } from 'reka-ui'
withDefaults(defineProps<{ open: boolean; side?: 'top' | 'right' | 'bottom' | 'left'; align?: 'start' | 'center' | 'end'; sideOffset?: number; contentClass?: string }>(), { side: 'bottom', align: 'start', sideOffset: 6 })
const emit = defineEmits<{ 'update:open': [value: boolean] }>()
</script>
