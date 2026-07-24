<!-- 文件功能：基于 Reka UI 提供统一的更多操作下拉菜单。 -->
<template>
  <DropdownMenuRoot @update:open="emit('update:open', $event)">
    <DropdownMenuTrigger as-child><slot name="trigger" /></DropdownMenuTrigger>
    <DropdownMenuPortal><DropdownMenuContent :side="side" :align="align" :side-offset="sideOffset" class="z-[900] min-w-36 rounded-lg border border-slate-200 bg-white p-1 shadow-lg outline-none" :class="contentClass">
      <slot>
        <DropdownMenuItem v-for="item in items" :key="item.value" :disabled="item.disabled" class="flex cursor-default items-center gap-2 rounded-md px-2 py-1.5 text-sm text-slate-700 outline-none data-[highlighted]:bg-slate-100 data-[highlighted]:text-slate-900 data-[disabled]:opacity-40" :class="item.danger ? 'text-red-600 data-[highlighted]:text-red-700' : ''" @select="emit('select', item.value)">{{ item.label }}</DropdownMenuItem>
      </slot>
    </DropdownMenuContent></DropdownMenuPortal>
  </DropdownMenuRoot>
</template>
<script setup lang="ts">
import { DropdownMenuContent, DropdownMenuItem, DropdownMenuPortal, DropdownMenuRoot, DropdownMenuTrigger } from 'reka-ui'

withDefaults(defineProps<{ items?: Array<{ label: string; value: string; disabled?: boolean; danger?: boolean }>; side?: 'top' | 'right' | 'bottom' | 'left'; align?: 'start' | 'center' | 'end'; sideOffset?: number; contentClass?: string }>(), { items: () => [], side: 'bottom', align: 'end', sideOffset: 6 })
const emit = defineEmits<{ select: [value: string]; 'update:open': [value: boolean] }>()
</script>
