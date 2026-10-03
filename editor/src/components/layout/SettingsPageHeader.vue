<!-- 文件功能：设置与管理中心的统一页面头部组件，承载页面标题、说明文本、状态徽标与右侧操作按钮槽位。 -->
<template>
  <header class="settings-page-header mb-4 flex min-w-0 items-start justify-between gap-3 border-b border-border pb-3">
    <div class="min-w-0 flex-1 space-y-0.5">
      <div class="flex min-w-0 items-center gap-2.5">
        <h1 class="min-w-0 truncate text-title-md tracking-tight text-text-strong">{{ title }}</h1>
        <UiBadge v-if="badge" :tone="badgeTone || 'neutral'" size="sm" class="shrink-0">
          {{ badge }}
        </UiBadge>
        <slot name="meta" />
      </div>
      <p v-if="description" class="text-sm text-text-muted leading-relaxed">
        {{ description }}
      </p>
    </div>

    <div v-if="$slots.actions" class="flex max-w-[60%] shrink-0 items-center gap-1.5 overflow-x-auto">
      <slot name="actions" />
    </div>
  </header>
</template>

<script setup lang="ts">
import { UiBadge } from '@/components/ui'

/**
 * 统一设置页标题栏参数。
 */
defineProps<{
  /** 页面一级标题 */
  title: string
  /** 页面辅助描述说明 */
  description?: string
  /** 可选的状态徽标文本 */
  badge?: string
  /** 可选的徽标色调 */
  badgeTone?: 'accent' | 'neutral' | 'success' | 'warning' | 'danger'
}>()
</script>
