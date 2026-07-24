<!-- 文件功能：提供批量选择状态下的固定操作条与清除选择入口。 -->
<template>
  <div
    v-if="visible"
    class="flex min-h-[var(--ui-control-h-md)] flex-wrap items-center gap-2 rounded-[var(--ui-radius-lg)] border border-[rgb(var(--ui-accent-muted))] bg-[rgb(var(--ui-accent-muted))] px-2"
    role="toolbar"
    :aria-label="label"
  >
    <span class="text-sm font-medium text-[rgb(var(--ui-text))]">已选择 {{ count }} 项</span>
    <div class="flex min-w-0 flex-1 flex-wrap items-center gap-2"><slot /></div>
    <UiButton
      v-if="clearable"
      type="button"
      variant="ghost"
      size="xs"
      class="ml-auto px-0 text-xs text-[rgb(var(--ui-text-secondary))] underline-offset-2 hover:text-[rgb(var(--ui-text))] hover:underline"
      @click="emit('clear')"
    >
      清除选择
    </UiButton>
  </div>
</template>

<script setup lang="ts">
import { UiButton } from '@/components/ui'
const emit = defineEmits<{
  /** 用户清除当前批量选择时触发。 */
  clear: []
}>()

withDefaults(defineProps<{
  /** 当前选中实体数。 */
  count: number
  /** 是否显示工具栏，通常由 count 大于零决定。 */
  visible?: boolean
  /** 是否提供默认的清除选择按钮。 */
  clearable?: boolean
  /** 工具栏的辅助技术名称。 */
  label?: string
}>(), {
  visible: true,
  clearable: true,
  label: '批量操作',
})
</script>
