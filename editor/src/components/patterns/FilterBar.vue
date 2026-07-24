<!-- 文件功能：提供查询、筛选和筛选结果操作的标准表单容器。 -->
<template>
  <form
    class="flex min-w-0 items-end gap-2 overflow-x-auto rounded-[var(--ui-radius-lg)] border border-[rgb(var(--ui-border))] bg-[rgb(var(--ui-surface-muted))] p-2 [scrollbar-width:thin]"
    :aria-label="label"
    @submit.prevent="emit('submit')"
    @reset.prevent="emit('reset')"
  >
    <div class="flex min-w-0 flex-1 items-end gap-2"><slot /></div>
    <div v-if="$slots.actions" class="ml-auto flex shrink-0 items-center gap-1.5"><slot name="actions" /></div>
  </form>
</template>

<script setup lang="ts">
const emit = defineEmits<{
  /** 筛选控件提交时触发，由业务层执行查询。 */
  submit: []
  /** 用户请求清除筛选条件时触发。 */
  reset: []
}>()

withDefaults(defineProps<{
  /** 标识当前筛选范围，避免多个表单缺少语义名称。 */
  label?: string
}>(), {
  label: '筛选条件',
})
</script>
