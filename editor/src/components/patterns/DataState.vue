<!-- 文件功能：统一列表与工作区的加载、空、错误及正常数据状态呈现。 -->
<template>
  <div v-if="state !== 'ready'" class="flex min-h-32 flex-col items-center justify-center gap-2 rounded-[var(--ui-radius-lg)] border border-dashed border-[rgb(var(--ui-border))] bg-[rgb(var(--ui-surface-muted))] px-4 py-6 text-center" :role="state === 'error' ? 'alert' : 'status'" :aria-live="state === 'error' ? 'assertive' : 'polite'">
    <div v-if="state === 'loading'" class="h-5 w-5 animate-spin rounded-full border-2 border-[rgb(var(--ui-border-strong))] border-t-[rgb(var(--ui-accent))]" aria-hidden="true" />
    <p class="text-sm font-medium text-[rgb(var(--ui-text))]">{{ resolvedTitle }}</p>
    <p v-if="resolvedDescription" class="max-w-md text-sm text-[rgb(var(--ui-text-secondary))]">{{ resolvedDescription }}</p>
    <slot :name="state" />
    <UiButton v-if="state === 'error' && retryable" variant="secondary" size="sm" @click="emit('retry')">重试</UiButton>
  </div>
  <slot v-else />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { UiButton } from '@/components/ui'

type DataStateKind = 'loading' | 'empty' | 'error' | 'ready'

const props = withDefaults(defineProps<{
  /** 当前数据生命周期状态；ready 时直接渲染默认插槽。 */
  state: DataStateKind
  /** 覆盖当前状态默认标题。 */
  title?: string
  /** 覆盖当前状态默认说明。 */
  description?: string
  /** 错误状态下是否提供默认重试动作。 */
  retryable?: boolean
}>(), {
  retryable: true,
})

const emit = defineEmits<{
  /** 用户点击错误态重试按钮时触发。 */
  retry: []
}>()

const stateCopy: Record<Exclude<DataStateKind, 'ready'>, { title: string; description: string }> = {
  loading: { title: '正在加载', description: '请稍候，数据即将显示。' },
  empty: { title: '暂无数据', description: '调整筛选条件，或创建第一项内容。' },
  error: { title: '加载失败', description: '暂时无法获取数据，请稍后重试。' },
}
const resolvedTitle = computed(() => props.title ?? (props.state === 'ready' ? '' : stateCopy[props.state].title))
const resolvedDescription = computed(() => props.description ?? (props.state === 'ready' ? '' : stateCopy[props.state].description))
</script>
