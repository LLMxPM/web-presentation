<!-- 文件功能：渲染一组语义化 Tailwind 字段，并提供单字段恢复原值能力。 -->
<template>
  <div class="divide-y divide-border">
    <div
      v-for="group in props.groups"
      :key="group.key"
      class="grid gap-2 py-3 first:pt-0 last:pb-0"
    >
      <div class="flex min-w-0 items-start justify-between gap-2">
        <div class="min-w-0">
          <label
            class="block text-xs font-semibold text-text"
            :for="tailwindSelectId(group.key)"
          >
            {{ group.label }}
          </label>
          <p
            v-if="isGroupChanged(group)"
            class="mt-0.5 text-[11px] leading-4 text-text-muted"
          >
            {{ tailwindClassLabel(group, group.baselineClass) }}
            <span aria-hidden="true">→</span>
            {{ tailwindClassLabel(group, group.selectedClass) }}
          </p>
        </div>
        <UiButton
          v-if="isGroupChanged(group)"
          type="button"
          variant="ghost"
          size="xs"
          class="shrink-0"
          :aria-label="`恢复${group.label}原值`"
          @click="restoreGroup(group)"
        >
          恢复原值
        </UiButton>
      </div>
      <UiSelect
        :id="tailwindSelectId(group.key)"
        :aria-label="group.label"
        :model-value="group.selectedClass || emptyTailwindClassValue"
        :options="tailwindOptions(group)"
        @update:model-value="value => changeGroup(group.key, value)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { UiButton, UiSelect } from '@/components/ui'
import {
  tailwindClassLabel,
  type PageVisualEditTailwindGroupView,
} from '@/components/page-detail/visual-edit/page-visual-edit-tailwind-view'
import type { SelectModelValue } from '@/components/ui/select'

const props = defineProps<{
  bindingId: string
  groups: PageVisualEditTailwindGroupView[]
}>()

const emit = defineEmits<{
  change: [payload: { group: string; className: string }]
}>()

const emptyTailwindClassValue = '__tailwind-none__'

/** 判断一个字段是否偏离当前页面版本中的原值。 */
function isGroupChanged(group: PageVisualEditTailwindGroupView): boolean {
  return group.baselineClass !== undefined && group.selectedClass !== group.baselineClass
}

/** 把选择器值转换为现有 set_tailwind_tokens 所需的 class 值。 */
function changeGroup(groupKey: string, value: SelectModelValue): void {
  emit('change', {
    group: groupKey,
    className: value === emptyTailwindClassValue ? '' : String(value ?? ''),
  })
}

/** 恢复单个 Tailwind 互斥组，草稿层会自动移除与原值相同的变更。 */
function restoreGroup(group: PageVisualEditTailwindGroupView): void {
  emit('change', { group: group.key, className: group.baselineClass ?? '' })
}

/** 生成 Tailwind 组选择器的稳定 DOM id。 */
function tailwindSelectId(groupKey: string): string {
  return `tailwind-${safeDomId(props.bindingId)}-${safeDomId(groupKey)}`
}

/** 将目录选项映射为纯业务文案，不在主流程暴露 class token。 */
function tailwindOptions(
  group: PageVisualEditTailwindGroupView,
): Array<{ value: string; label: string }> {
  return [
    { value: emptyTailwindClassValue, label: '不设置' },
    ...group.options.map(option => ({ value: option.class_name, label: option.label })),
  ]
}

/** DOM id 只保留安全字符，避免绑定 id 中的分隔符影响 label 关联。 */
function safeDomId(value: string): string {
  return value.replace(/[^a-zA-Z0-9_-]/g, '-')
}
</script>
