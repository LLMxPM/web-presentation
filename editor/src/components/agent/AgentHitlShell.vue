<!-- 文件功能：提供智能体 HITL 覆盖输入区的统一外壳，封装标题、键盘忽略和提交按钮样式。 -->
<template>
  <section
    class="rounded-ui-md border border-border bg-surface px-3 py-2.5 outline-none focus-visible:ring-2 focus-visible:ring-border-focus"
    tabindex="0"
    @keydown.esc.stop.prevent="emitIgnore"
    @keydown.enter.exact.stop.prevent="emitSubmit"
  >
    <div class="flex items-start justify-between gap-3">
      <div class="min-w-0">
        <p class="text-sm font-semibold leading-5 text-text">{{ title }}</p>
        <p v-if="subtitle" class="mt-0.5 text-xs leading-5 text-text-muted">{{ subtitle }}</p>
      </div>
      <UiBadge v-if="badge" tone="info" class="shrink-0">
        {{ badge }}
      </UiBadge>
    </div>

    <div class="mt-2">
      <slot />
    </div>

    <div class="mt-2 flex items-center justify-between gap-2">
      <div class="flex min-w-0 items-center gap-1.5">
        <slot name="footer-left" />
      </div>
      <div class="flex shrink-0 items-center gap-2">
        <UiButton
          type="button"
          variant="ghost"
          size="sm"
          :disabled="loading"
          @click="emitIgnore"
        >
          {{ ignoreLabel }}
          <kbd class="rounded-ui-sm bg-surface-muted px-1.5 py-0.5 text-xs font-medium text-text-muted">ESC</kbd>
        </UiButton>
        <UiButton
          variant="primary"
          size="sm"
          :loading="loading"
          :disabled="!canSubmit"
          @click="emitSubmit"
        >
          {{ submitLabel }}
          <CornerDownLeft class="h-3 w-3" />
        </UiButton>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { CornerDownLeft } from '@lucide/vue'

import { UiBadge, UiButton } from '@/components/ui'

const props = withDefaults(defineProps<{
  title: string
  subtitle?: string
  badge?: string
  canSubmit?: boolean
  loading?: boolean
  submitLabel?: string
  ignoreLabel?: string
}>(), {
  subtitle: '',
  badge: '',
  canSubmit: true,
  loading: false,
  submitLabel: '提交',
  ignoreLabel: '忽略',
})

const emit = defineEmits<{
  ignore: []
  submit: []
}>()

/**
 * 执行忽略动作；父组件负责把它映射为拒绝工具或取消提问。
 */
function emitIgnore() {
  if (props.loading) {
    return
  }
  emit('ignore')
}

/**
 * 执行提交动作；当当前表单不完整时不会向父层抛出事件。
 */
function emitSubmit() {
  if (props.loading || !props.canSubmit) {
    return
  }
  emit('submit')
}
</script>
