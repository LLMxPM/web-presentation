<!-- 文件功能：提供一级页面标题、说明、上下文与主要操作的一致布局。 -->
<template>
  <header class="rounded-lg border border-slate-200 bg-white/95 px-3.5 py-2 shadow-sm">
    <div class="flex min-w-0 items-center gap-3">
      <div class="min-w-0 flex-1 space-y-1">
        <div v-if="$slots.eyebrow" class="text-xs text-[rgb(var(--ui-text-muted))]"><slot name="eyebrow" /></div>
        <div class="flex min-w-0 items-center gap-2">
          <component
            :is="icon"
            v-if="icon"
            aria-hidden="true"
            class="size-5 shrink-0 text-[rgb(var(--ui-primary))]"
          />
          <h1 class="truncate text-title-md font-semibold text-[rgb(var(--ui-text))]">{{ title }}</h1>
          <UiPopover v-if="description" v-model:open="isDescriptionOpen">
            <template #trigger>
              <button
                type="button"
                class="flex size-5 shrink-0 items-center justify-center rounded-full text-[rgb(var(--ui-text-muted))] transition-colors hover:bg-slate-100 hover:text-[rgb(var(--ui-text-secondary))]"
              >
                <Info :size="16" />
              </button>
            </template>
            <div class="max-w-xs text-sm text-[rgb(var(--ui-text-secondary))]">{{ description }}</div>
          </UiPopover>
          <slot name="meta" />
        </div>
        <div v-if="$slots.default" class="text-sm text-[rgb(var(--ui-text-secondary))]"><slot /></div>
      </div>
      <div v-if="$slots.actions" class="flex max-w-[58%] shrink-0 items-center gap-1.5 overflow-x-auto pb-0.5 [scrollbar-width:thin]"><slot name="actions" /></div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { ref, type Component } from 'vue'
import { Info } from '@lucide/vue'
import { UiPopover } from '@/components/ui'

defineProps<{
  /** 页面主标题，用于建立稳定的信息层级。 */
  title: string
  /** 页面标题左侧的语义图标。 */
  icon?: Component
  /** 标题下的简短范围说明；点击信息图标可在浮层中查看。 */
  description?: string
}>()

const isDescriptionOpen = ref(false)
</script>
