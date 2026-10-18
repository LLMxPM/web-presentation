<!-- 文件功能：以只读摘要展示项目级放映默认值，供页面结构与项目设置共用。 -->
<template>
  <div class="flex min-w-0 flex-wrap items-center gap-1.5" :class="compact ? 'text-[11px]' : 'text-xs'">
    <span class="shrink-0 font-medium text-text-secondary">项目默认</span>
    <span class="rounded-full border border-border bg-surface px-2 py-0.5 text-text-emphasis">{{ transitionText }}</span>
    <span class="rounded-full border border-border bg-surface px-2 py-0.5 text-text-emphasis">{{ advanceText }}</span>
    <span class="rounded-full border border-border bg-surface px-2 py-0.5 text-text-emphasis">{{ loopText }}</span>
    <span v-if="settings.auto_start" class="rounded-full border border-border bg-surface px-2 py-0.5 text-text-emphasis">自动开始</span>
    <UiButton
      v-if="editable"
      variant="ghost"
      size="xs"
      class="shrink-0"
      @click="emit('edit')"
    >
      修改
    </UiButton>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import { UiButton } from '@/components/ui'
import type { SlideshowSettings } from '@/types/api'
import {
  ADVANCE_MODE_LABELS,
  TRANSITION_EFFECT_LABELS,
  formatMillisecondsAsSeconds,
} from './project-slideshow-values'

const props = withDefaults(defineProps<{
  settings: SlideshowSettings
  editable?: boolean
  compact?: boolean
}>(), {
  editable: false,
  compact: false,
})

const emit = defineEmits<{ edit: [] }>()

const transitionText = computed(() => {
  const transition = props.settings.transition
  if (transition.effect === 'none') {
    return TRANSITION_EFFECT_LABELS.none
  }
  return `${TRANSITION_EFFECT_LABELS[transition.effect]} ${formatMillisecondsAsSeconds(transition.duration_ms)}s`
})

const advanceText = computed(() => {
  const advance = props.settings.advance
  const label = ADVANCE_MODE_LABELS[advance.mode]
  if (advance.mode === 'manual') {
    return label
  }
  return `${label} ${formatMillisecondsAsSeconds(advance.delay_ms)}s`
})

const loopText = computed(() => props.settings.loop ? '循环开' : '循环关')
</script>
