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
          未勾选时继承项目默认：{{ inheritedAdvanceSummary }}。
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
          <UiFormField :label="advanceMode === 'media_end' ? '无媒体时停留（秒）' : '停留时长（秒）'">
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
        <div v-if="overrideAdvance && advanceMode === 'media_end'" class="mt-3 grid grid-cols-2 gap-3">
          <UiFormField label="媒体等待上限（秒）">
            <template #default="field">
              <UiInput
                :model-value="mediaTimeoutSeconds"
                inputmode="decimal"
                placeholder="300"
                :input-id="field.inputId"
                @update:model-value="mediaTimeoutSeconds = String($event)"
              />
            </template>
          </UiFormField>
        </div>
        <template v-if="overrideAdvance && advanceMode === 'media_end'">
          <p class="mt-2 text-xs text-text-disabled">
            播放当前页的非循环音视频，全部结束后翻页；没有可等待媒体时按停留时长翻页。循环背景媒体不参与等待。
          </p>
          <p class="mt-1 text-xs text-text-disabled">
            若浏览器阻止自动播放，放映窗口会显示受阻提示，可点“重试”恢复或使用“下一页”继续。
          </p>
        </template>
        <p v-if="mediaEndUnavailable" class="mt-2 text-xs font-medium text-warning-strong" role="status">
          当前服务端未开放媒体结束模式，请改用其它翻页方式后保存。
        </p>
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
import { computed, ref, watch } from 'vue'

import { UiButton, UiCheckbox, UiDialog, UiFormField, UiInput, UiSelect } from '@/components/ui'
import type {
  SlideshowAdvance,
  SlideshowCapabilities,
  SlideshowSettings,
  SlideshowTransition,
} from '@/types/api'
import type { SlideshowAdvanceMode, SlideshowEffect } from './project-slideshow-values'
import {
  ADVANCE_MODE_LABELS,
  buildAdvanceModeOptions,
  formatMillisecondsAsSeconds,
  isMediaEndAdvanceAvailable,
  parseSecondsToMilliseconds,
} from './project-slideshow-values'

const props = withDefaults(defineProps<{
  open: boolean
  title: string
  transition: SlideshowTransition | null
  advance: SlideshowAdvance | null
  defaults: SlideshowSettings
  capabilities?: SlideshowCapabilities | null
}>(), {
  capabilities: null,
})

const emit = defineEmits<{
  'update:open': [value: boolean]
  save: [value: { transition: SlideshowTransition | null; advance: SlideshowAdvance | null }]
}>()

const effectOptions = [
  { label: '淡入淡出', value: 'fade' },
  { label: '推入', value: 'push' },
  { label: '无动画', value: 'none' },
]
const mediaEndAvailable = computed(() => isMediaEndAdvanceAvailable(props.capabilities))
const advanceModeOptions = computed(() => buildAdvanceModeOptions(props.capabilities))
const effectiveAdvanceMode = computed<SlideshowAdvanceMode>(() => {
  return overrideAdvance.value ? advanceMode.value : props.defaults.advance.mode
})
const mediaEndUnavailable = computed(() => {
  return props.capabilities != null && effectiveAdvanceMode.value === 'media_end' && !mediaEndAvailable.value
})
const inheritedAdvanceSummary = computed(() => {
  const advance = props.defaults.advance
  const mode = advanceModeLabel(advance.mode)
  const delay = formatMillisecondsAsSeconds(advance.delay_ms)
  if (advance.mode === 'media_end') {
    const timeout = formatMillisecondsAsSeconds(advance.media_timeout_ms ?? 300000)
    return `${mode}，无媒体时停留 ${delay} 秒，等待上限 ${timeout} 秒`
  }
  return `${mode}，停留 ${delay} 秒`
})

const overrideTransition = ref(false)
const overrideAdvance = ref(false)
const effect = ref<SlideshowEffect>('fade')
const durationSeconds = ref('0.4')
const advanceMode = ref<SlideshowAdvanceMode>('manual')
const delaySeconds = ref('5')
const mediaTimeoutSeconds = ref('300')

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
    mediaTimeoutSeconds.value = formatMillisecondsAsSeconds(
      advance?.media_timeout_ms ?? props.defaults.advance.media_timeout_ms ?? 300000,
    )
  },
  { immediate: true },
)

/** 切换动画覆盖状态；关闭时回填项目默认值便于再次打开。 */
function toggleTransition(value: boolean | 'indeterminate'): void {
  overrideTransition.value = value === true
  if (!overrideTransition.value) {
    effect.value = props.defaults.transition.effect
    durationSeconds.value = formatMillisecondsAsSeconds(props.defaults.transition.duration_ms)
  }
}

/** 切换翻页覆盖状态。 */
function toggleAdvance(value: boolean | 'indeterminate'): void {
  overrideAdvance.value = value === true
  if (!overrideAdvance.value) {
    advanceMode.value = props.defaults.advance.mode
    delaySeconds.value = formatMillisecondsAsSeconds(props.defaults.advance.delay_ms)
    mediaTimeoutSeconds.value = formatMillisecondsAsSeconds(props.defaults.advance.media_timeout_ms ?? 300000)
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
  const mode = value === 'timer' || value === 'media_end' ? value : 'manual'
  if (mode === 'media_end' && !mediaEndAvailable.value) {
    return
  }
  advanceMode.value = mode
  if (mode === 'media_end' && !mediaTimeoutSeconds.value) {
    mediaTimeoutSeconds.value = formatMillisecondsAsSeconds(
      props.advance?.media_timeout_ms ?? props.defaults.advance.media_timeout_ms ?? 300000,
    )
  }
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
        media_timeout_ms: clamp(
          parseSecondsToMilliseconds(mediaTimeoutSeconds.value),
          1000,
          3_600_000,
          props.advance?.media_timeout_ms ?? props.defaults.advance.media_timeout_ms ?? 300000,
        ),
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
  return ADVANCE_MODE_LABELS[value] ?? value
}
</script>
