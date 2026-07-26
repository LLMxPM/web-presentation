<!-- 文件功能：提供弹窗、抽屉与预览浮层统一使用的关闭图标按钮。 -->
<template>
  <button
    type="button"
    :aria-label="label"
    :title="label"
    :class="[
      'inline-flex h-[var(--ui-control-h-md)] w-[var(--ui-control-h-md)] shrink-0 items-center justify-center rounded-[var(--ui-radius-md)] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-border-focus/40 disabled:pointer-events-none disabled:opacity-50',
      toneClass,
    ]"
    @click.stop="emit('click', $event)"
  >
    <X class="h-4 w-4" />
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { X } from '@lucide/vue'

const props = withDefaults(defineProps<{
  label?: string
  tone?: 'default' | 'inverse'
}>(), {
  label: '关闭',
  tone: 'default',
})

const emit = defineEmits<{
  click: [event: MouseEvent]
}>()

const toneClass = computed(() => (
  props.tone === 'inverse'
    ? 'bg-surface/10 text-text-inverse ring-1 ring-surface/15 backdrop-blur hover:bg-surface/20 hover:text-text-inverse'
    : 'bg-transparent text-text-disabled hover:bg-surface-muted hover:text-text-emphasis'
))
</script>
