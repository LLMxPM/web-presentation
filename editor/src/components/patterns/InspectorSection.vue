<!-- 文件功能：提供属性检查器中可折叠的稳定属性分组。 -->
<template>
  <section class="overflow-hidden rounded-[var(--ui-radius-lg)] border border-[rgb(var(--ui-border))] bg-[rgb(var(--ui-surface))]">
    <div class="flex min-h-[var(--ui-control-h-md)] items-center gap-2 bg-[rgb(var(--ui-surface-muted))] px-3 py-2">
      <UiButton
        v-if="collapsible"
        :id="headingId"
        type="button"
        variant="ghost"
        content-align="start"
        class="h-auto min-w-0 flex-1 p-0 text-left text-sm font-semibold text-[rgb(var(--ui-text))]"
        :aria-controls="contentId"
        :aria-expanded="resolvedOpen"
        @click="toggle"
      >
        <ChevronDown v-if="resolvedOpen" aria-hidden="true" class="h-4 w-4 shrink-0 text-[rgb(var(--ui-text-muted))]" />
        <ChevronRight v-else aria-hidden="true" class="h-4 w-4 shrink-0 text-[rgb(var(--ui-text-muted))]" />
        <span class="min-w-0 truncate">{{ title }}</span>
      </UiButton>
      <h3 v-else :id="headingId" class="min-w-0 flex-1 truncate text-sm font-semibold text-[rgb(var(--ui-text))]">{{ title }}</h3>
      <slot name="actions" />
    </div>
    <div v-show="resolvedOpen" :id="contentId" class="space-y-2 border-t border-[rgb(var(--ui-border))] bg-[rgb(var(--ui-surface))] px-3 pb-3 pt-3" role="region" :aria-labelledby="headingId">
      <p v-if="description" class="text-xs text-[rgb(var(--ui-text-muted))]">{{ description }}</p>
      <slot />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'
import { ChevronDown, ChevronRight } from '@lucide/vue'
import { UiButton } from '@/components/ui'

const props = withDefaults(defineProps<{
  /** 属性分组标题。 */
  title: string
  /** 分组的简短使用说明。 */
  description?: string
  /** 受控展开状态；未传入时由组件维护状态。 */
  open?: boolean
  /** 是否允许用户折叠该分组。 */
  collapsible?: boolean
}>(), {
  open: undefined,
  collapsible: true,
})

const emit = defineEmits<{
  /** 展开状态变化时回传，支持受控模式。 */
  'update:open': [open: boolean]
}>()

const headingId = useId()
const contentId = useId()
const localOpen = ref(true)
const resolvedOpen = computed(() => props.open ?? localOpen.value)

watch(() => props.open, value => {
  if (value !== undefined) localOpen.value = value
})

/** 切换分组可见性；不可折叠分组不产生状态变化。 */
function toggle() {
  if (!props.collapsible) return
  const nextOpen = !resolvedOpen.value
  localOpen.value = nextOpen
  emit('update:open', nextOpen)
}
</script>
