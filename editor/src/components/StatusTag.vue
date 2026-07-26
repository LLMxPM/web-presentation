<!-- 文件功能：根据后台状态值渲染统一的状态标签（Tailwind 版）。 -->
<template>
  <span
    :class="[
      'inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold ring-1 ring-inset',
      status === 'active' ? 'bg-success-muted text-success-strong ring-success/20' : '',
      status === 'archived' ? 'bg-surface-muted text-text-secondary ring-slate-500/10' : ''
    ]"
  >
    {{ label }}
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { RecordStatus } from '@/types/api'

const props = defineProps<{
  status: RecordStatus
}>()

/**
 * 将后台状态枚举映射为更易读的中文标签。
 */
const label = computed(() => {
  if (props.status === 'active') return '启用'
  return '归档'
})
</script>
