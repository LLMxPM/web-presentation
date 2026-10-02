<!-- 文件功能：设置与管理中心的统一页面头部组件，承载页面标题、说明文本、状态徽标与右侧操作按钮槽位。 -->
<template>
  <header class="settings-page-header flex flex-wrap items-start justify-between gap-4 border-b border-border pb-5 mb-6">
    <div class="min-w-0 flex-1 space-y-1">
      <div class="flex items-center gap-2.5">
        <h1 class="truncate text-2xl font-bold tracking-tight text-text-strong">{{ title }}</h1>
        <UiBadge v-if="badge" :tone="badgeTone || 'neutral'" size="sm">
          {{ badge }}
        </UiBadge>
        <slot name="meta" />
      </div>
      <p v-if="description" class="text-sm text-text-muted leading-relaxed">
        {{ description }}
      </p>
    </div>

    <div v-if="$slots.actions" class="flex shrink-0 items-center gap-3">
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
