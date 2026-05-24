<!-- 文件功能：提供弹窗、抽屉与预览浮层统一使用的关闭图标按钮。 -->
<template>
  <button
    type="button"
    :aria-label="label"
    :title="label"
    :class="[
      'inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/40 disabled:pointer-events-none disabled:opacity-50',
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
    ? 'bg-white/10 text-white ring-1 ring-white/15 backdrop-blur hover:bg-white/20 hover:text-white'
    : 'bg-transparent text-slate-400 hover:bg-slate-100 hover:text-slate-700'
))
</script>
