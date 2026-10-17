<!-- 文件功能：编辑单个叶子路由的放映覆盖，支持按组继承项目默认值或显式设置。 -->
<template>
  <UiDialog :open="open" :title="title" size="compact" width="560px" body-preset="dense" @update:open="emit('update:open', $event)">
    <div class="grid gap-4">
      <section class="rounded-lg border border-border p-3">
        <label class="flex items-center gap-2 text-sm font-semibold text-text-emphasis">
          <UiCheckbox :model-value="overrideTransition" @update:model-value="toggleTransition" />
          覆盖翻页动画
        </label>
        <p class="mt-1 text-xs text-text-disabled">
          未勾选时继承项目默认：{{ effectLabel(defaults.transition.effect) }} {{ formatMillisecondsAsSeconds(defaults.transition.duration_ms) }} 秒。
        </p>
        <div v-if="overrideTransition" class="mt-3 grid grid-cols-2 gap-3">
          <UiFormField label="动画效果">
            <template #default="field">
              <UiSelect
                :model-value="effect"
                :options="effectOptions"
                :id="field.inputId"
                @update:model-value="updateEffect"
              />
            </template>
          </UiFormField>
          <UiFormField label="动画时长（秒）">
            <template #default="field">
              <UiInput
                :model-value="durationSeconds"
                inputmode="decimal"
                placeholder="0.4"
                :disabled="effect === 'none'"
                :input-id="field.inputId"
                @update:model-value="durationSeconds = String($event)"
              />
            </template>
          </UiFormField>
        </div>
      </section>

      <section class="rounded-lg border border-border p-3">
        <label class="flex items-center gap-2 text-sm font-semibold text-text-emphasis">
          <UiCheckbox :model-value="overrideAdvance" @update:model-value="toggleAdvance" />
          覆盖翻页方式
        </label>
        <p class="mt-1 text-xs text-text-disabled">
          未勾选时继承项目默认：{{ advanceModeLabel(defaults.advance.mode) }}，停留 {{ formatMillisecondsAsSeconds(defaults.advance.delay_ms) }} 秒。
        </p>
        <div v-if="overrideAdvance" class="mt-3 grid grid-cols-2 gap-3">
          <UiFormField label="翻页模式">
            <template #default="field">
              <UiSelect
                :model-value="advanceMode"
                :options="advanceModeOptions"
                :id="field.inputId"
                @update:model-value="updateAdvanceMode"
              />
            </template>
          </UiFormField>
          <UiFormField label="停留时长（秒）">
            <template #default="field">
              <UiInput
                :model-value="delaySeconds"
                inputmode="decimal"
                placeholder="5"
                :input-id="field.inputId"
                @update:model-value="delaySeconds = String($event)"
              />
            </template>
          </UiFormField>
        </div>
      </section>
    </div>

    <template #footer>
      <div class="flex w-full items-center justify-between gap-2">
        <UiButton variant="ghost" @click="clearOverrides">恢复继承</UiButton>
        <div class="flex gap-2">
          <UiButton variant="ghost" @click="emit('update:open', false)">取消</UiButton>
          <UiButton variant="primary" @click="handleSave">应用</UiButton>
        </div>
      </div>
    </template>
  </UiDialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

import { UiButton, UiCheckbox, UiDialog, UiFormField, UiInput, UiSelect } from '@/components/ui'
import type { SlideshowAdvance, SlideshowSettings, SlideshowTransition } from '@/types/api'
import type { SlideshowAdvanceMode, SlideshowEffect } from './project-slideshow-values'
import { formatMillisecondsAsSeconds, parseSecondsToMilliseconds } from './project-slideshow-values'

const props = defineProps<{
  open: boolean
  title: string
  transition: SlideshowTransition | null
  advance: SlideshowAdvance | null
  defaults: SlideshowSettings
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  save: [value: { transition: SlideshowTransition | null; advance: SlideshowAdvance | null }]
}>()

const effectOptions = [
  { label: '淡入淡出', value: 'fade' },
  { label: '推入', value: 'push' },
  { label: '无动画', value: 'none' },
]
const advanceModeOptions = [
  { label: '手动翻页', value: 'manual' },
  { label: '定时翻页', value: 'timer' },
]

const overrideTransition = ref(false)
const overrideAdvance = ref(false)
const effect = ref<SlideshowEffect>('fade')
const durationSeconds = ref('0.4')
const advanceMode = ref<SlideshowAdvanceMode>('manual')
const delaySeconds = ref('5')

watch(
  () => [props.open, props.transition, props.advance] as const,
  ([open, transition, advance]) => {
    if (!open) {
      return
    }
    overrideTransition.value = transition !== null
    overrideAdvance.value = advance !== null
    effect.value = transition?.effect ?? props.defaults.transition.effect
    durationSeconds.value = formatMillisecondsAsSeconds(transition?.duration_ms ?? props.defaults.transition.duration_ms)
    advanceMode.value = advance?.mode ?? props.defaults.advance.mode
    delaySeconds.value = formatMillisecondsAsSeconds(advance?.delay_ms ?? props.defaults.advance.delay_ms)
  },
  { immediate: true },
)

/** 切换动画覆盖状态；关闭时回填项目默认值便于再次打开。 */
function toggleTransition(value: boolean): void {
  overrideTransition.value = value === true
  if (!overrideTransition.value) {
    effect.value = props.defaults.transition.effect
    durationSeconds.value = formatMillisecondsAsSeconds(props.defaults.transition.duration_ms)
  }
}

/** 切换翻页覆盖状态。 */
function toggleAdvance(value: boolean): void {
  overrideAdvance.value = value === true
  if (!overrideAdvance.value) {
    advanceMode.value = props.defaults.advance.mode
    delaySeconds.value = formatMillisecondsAsSeconds(props.defaults.advance.delay_ms)
  }
}

function updateEffect(value: unknown): void {
  effect.value = value === 'none' ? 'none' : value === 'push' ? 'push' : 'fade'
  if (effect.value === 'none') {
    durationSeconds.value = '0'
  } else if (Number.parseFloat(durationSeconds.value) <= 0) {
    durationSeconds.value = '0.4'
  }
}

function updateAdvanceMode(value: unknown): void {
  advanceMode.value = value === 'timer' ? 'timer' : 'manual'
}

/** 清除两组覆盖，等价于路由写请求显式提交 null。 */
function clearOverrides(): void {
  overrideTransition.value = false
  overrideAdvance.value = false
  emit('save', { transition: null, advance: null })
  emit('update:open', false)
}

/** 按覆盖开关收集值并收敛毫秒范围。 */
function handleSave(): void {
  const transition = overrideTransition.value
    ? {
        effect: effect.value,
        duration_ms: effect.value === 'none'
          ? 0
          : clamp(parseSecondsToMilliseconds(durationSeconds.value), 100, 2000, props.defaults.transition.duration_ms),
      }
    : null
  const advance = overrideAdvance.value
    ? {
        mode: advanceMode.value,
        delay_ms: clamp(parseSecondsToMilliseconds(delaySeconds.value), 1000, 3_600_000, props.defaults.advance.delay_ms),
      }
    : null
  emit('save', { transition, advance })
  emit('update:open', false)
}

function clamp(value: number | null, min: number, max: number, fallback: number): number {
  if (value === null) {
    return fallback
  }
  return Math.min(max, Math.max(min, value))
}

function effectLabel(value: SlideshowEffect): string {
  return effectOptions.find(option => option.value === value)?.label ?? value
}

function advanceModeLabel(value: SlideshowAdvanceMode): string {
  return advanceModeOptions.find(option => option.value === value)?.label ?? value
}
</script>
