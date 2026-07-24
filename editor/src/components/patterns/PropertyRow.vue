<!-- 文件功能：提供属性检查器标签、说明、必填标记与控件区域的对齐行。 -->
<template>
  <div class="grid grid-cols-[minmax(5rem,auto)_minmax(0,1fr)] items-start gap-x-3 gap-y-1 py-1.5">
    <div class="pt-1">
      <slot name="label">
        <label v-if="forId" :for="forId" class="text-sm text-[rgb(var(--ui-text-secondary))]">
          {{ label }}<span v-if="required" class="ml-0.5 text-[rgb(var(--ui-danger))]" aria-hidden="true">*</span>
        </label>
        <span v-else class="text-sm text-[rgb(var(--ui-text-secondary))]">
          {{ label }}<span v-if="required" class="ml-0.5 text-[rgb(var(--ui-danger))]" aria-hidden="true">*</span>
        </span>
      </slot>
    </div>
    <div class="min-w-0"><slot /></div>
    <p v-if="description || $slots.description" class="col-start-2 text-xs text-[rgb(var(--ui-text-muted))]">
      <slot name="description">{{ description }}</slot>
    </p>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  /** 属性名称；需要复杂标签时可使用 label 插槽。 */
  label: string
  /** 关联的控件 id；传入后渲染原生 label。 */
  forId?: string
  /** 是否展示视觉必填标记，校验规则仍由业务表单负责。 */
  required?: boolean
  /** 控件下方的辅助说明。 */
  description?: string
}>()
</script>
