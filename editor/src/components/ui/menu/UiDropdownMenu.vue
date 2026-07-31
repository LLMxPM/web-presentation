<!-- 文件功能：基于 Reka UI 提供统一的更多操作下拉菜单，支持图标、分隔线、危险项和选中指示。 -->
<template>
  <DropdownMenuRoot @update:open="emit('update:open', $event)">
    <DropdownMenuTrigger as-child><slot name="trigger" /></DropdownMenuTrigger>
    <DropdownMenuPortal>
      <DropdownMenuContent
        :side="side"
        :align="align"
        :side-offset="sideOffset"
        class="z-dropdown min-w-36 rounded-lg border border-border bg-surface p-1 shadow-lg outline-none"
        :class="contentClass"
      >
        <slot>
          <template v-for="(entry, index) in items" :key="entry.separator ? `sep-${index}` : entry.value">
            <DropdownMenuSeparator v-if="entry.separator" class="my-1 h-px bg-surface-muted" />
            <DropdownMenuItem
              v-else
              :disabled="entry.disabled"
              class="flex cursor-default items-center gap-2 rounded-md px-2 py-1.5 text-sm outline-none data-[highlighted]:bg-surface-muted data-[highlighted]:text-text-strong data-[disabled]:opacity-40"
              :class="entry.danger ? 'text-danger data-[highlighted]:text-danger-strong' : 'text-text-emphasis'"
              @select="emit('select', entry.value!)"
            >
              <component :is="entry.icon" v-if="entry.icon" class="h-4 w-4 shrink-0 opacity-70" />
              <span class="min-w-0 flex-1">
                <span class="block truncate">{{ entry.label }}</span>
                <span v-if="entry.description" class="block truncate text-[11px] opacity-60">{{ entry.description }}</span>
              </span>
              <Check v-if="entry.active" class="h-3.5 w-3.5 shrink-0 opacity-60" />
            </DropdownMenuItem>
          </template>
        </slot>
      </DropdownMenuContent>
    </DropdownMenuPortal>
  </DropdownMenuRoot>
</template>

<script setup lang="ts">
import type { Component } from 'vue'
import { Check } from '@lucide/vue'
import {
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuPortal,
  DropdownMenuRoot,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from 'reka-ui'

/**
 * 菜单项或分隔线条目定义。separator 为 true 时渲染分隔线，其余字段忽略。
 */
export interface DropdownMenuEntry {
  label?: string
  value?: string
  disabled?: boolean
  danger?: boolean
  icon?: Component
  active?: boolean
  description?: string
  separator?: boolean
}

withDefaults(
  defineProps<{
    items?: DropdownMenuEntry[]
    side?: 'top' | 'right' | 'bottom' | 'left'
    align?: 'start' | 'center' | 'end'
    sideOffset?: number
    contentClass?: string
  }>(),
  { items: () => [], side: 'bottom', align: 'end', sideOffset: 6 },
)
const emit = defineEmits<{ select: [value: string]; 'update:open': [value: boolean] }>()
</script>
