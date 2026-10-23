<!-- 文件功能：在页面结构检查器中编辑单个叶子路由的动画与翻页覆盖，保留按组继承语义。 -->
<template>
  <div class="grid gap-4">
    <fieldset class="min-w-0 rounded-ui-lg border border-border p-3">
      <label class="flex items-center gap-2 text-sm font-semibold text-text-emphasis">
        <UiCheckbox :model-value="overrideTransition" @update:model-value="toggleTransition" />
        覆盖翻页动画
      </label>
      <p v-if="!overrideTransition" class="mt-1 text-xs text-text-disabled">{{ inheritedTransitionSummary }}</p>
      <div v-else class="mt-3 grid grid-cols-2 gap-3">
        <UiFormField label="动画效果">
          <template #default="field">
            <UiSelect
              :model-value="effect"
              :options="TRANSITION_EFFECT_OPTIONS"
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
              @change="commitTransition"
              @blur="commitTransition"
            />
          </template>
        </UiFormField>
      </div>
    </fieldset>

    <fieldset class="min-w-0 rounded-ui-lg border border-border p-3">
      <label class="flex items-center gap-2 text-sm font-semibold text-text-emphasis">
        <UiCheckbox :model-value="overrideAdvance" @update:model-value="toggleAdvance" />
        覆盖翻页方式
      </label>
      <p v-if="!overrideAdvance" class="mt-1 text-xs text-text-disabled">{{ inheritedAdvanceSummary }}</p>
      <div v-else class="mt-3 grid grid-cols-2 gap-3">
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
              @change="commitAdvance"
              @blur="commitAdvance"
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
              @change="commitAdvance"
              @blur="commitAdvance"
            />
          </template>
        </UiFormField>
      </div>
      <template v-if="overrideAdvance && advanceMode === 'media_end'">
        <p class="mt-2 text-xs text-text-disabled">
          播放当前页的非循环音视频，全部结束后翻页；没有可等待媒体时按停留时长翻页。循环背景媒体不参与等待。
          切换到手动模式时媒体继续播放，但不会自动翻页。
        </p>
        <p class="mt-1 text-xs text-text-disabled">
          若浏览器阻止自动播放，放映窗口会显示受阻提示，可点“重试”恢复或使用“下一页”继续。
        </p>
      </template>
      <div v-if="overrideAdvance && advanceMode === 'timeline_end'" class="mt-3 grid grid-cols-2 gap-3">
        <UiFormField label="时间轴等待上限（秒）">
          <template #default="field">
            <UiInput
              :model-value="timelineTimeoutSeconds"
              inputmode="decimal"
              placeholder="300"
              :input-id="field.inputId"
              @update:model-value="timelineTimeoutSeconds = String($event)"
              @change="commitAdvance"
              @blur="commitAdvance"
            />
          </template>
        </UiFormField>
      </div>
      <template v-if="overrideAdvance && advanceMode === 'timeline_end'">
        <p class="mt-2 text-xs text-text-disabled">
          等待当前页时间轴自然结束；页面没有可用时间轴时显示错误，可重试或手动翻页。
          时间轴被浏览器阻止时显示受阻；播放失败或超过等待上限时显示错误，可在放映控制条重试或手动翻页。
        </p>
        <p v-if="timelineEndUnavailable" class="mt-1 text-xs font-medium text-warning-strong" role="status">
          当前服务端未开放页内时间轴结束模式，请改用其它翻页方式后保存。
        </p>
      </template>
      <p v-if="mediaEndUnavailable" class="mt-2 text-xs font-medium text-warning-strong" role="status">
        当前服务端未开放媒体结束模式，请改用其它翻页方式后保存。
      </p>
    </fieldset>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { UiCheckbox, UiFormField, UiInput, UiSelect } from '@/components/ui'
import type {
  SlideshowAdvance,
  SlideshowCapabilities,
  SlideshowSettings,
  SlideshowTransition,
} from '@/types/api'
import type { SlideshowAdvanceMode, SlideshowEffect } from './project-slideshow-values'
import {
  ADVANCE_MODE_LABELS,
  ADVANCE_DELAY_MAX_MS,
  ADVANCE_DELAY_MIN_MS,
  MEDIA_TIMEOUT_MAX_MS,
  MEDIA_TIMEOUT_MIN_MS,
  TIMELINE_TIMEOUT_MAX_MS,
  TIMELINE_TIMEOUT_MIN_MS,
  TRANSITION_DURATION_MAX_MS,
  TRANSITION_DURATION_MIN_MS,
  TRANSITION_EFFECT_LABELS,
  TRANSITION_EFFECT_OPTIONS,
  buildAdvanceModeOptions,
  formatMillisecondsAsSeconds,
  isMediaEndAdvanceAvailable,
  isTimelineEndAdvanceAvailable,
  parseSecondsToMilliseconds,
} from './project-slideshow-values'

const props = withDefaults(defineProps<{
  transition: SlideshowTransition | null
  advance: SlideshowAdvance | null
  defaults: SlideshowSettings
  capabilities?: SlideshowCapabilities | null
}>(), {
  capabilities: null,
})

const emit = defineEmits<{
  'update:transition': [value: SlideshowTransition | null]
  'update:advance': [value: SlideshowAdvance | null]
}>()

const overrideTransition = ref(false)
const overrideAdvance = ref(false)
const effect = ref<SlideshowEffect>('fade')
const durationSeconds = ref('0.4')
const advanceMode = ref<SlideshowAdvanceMode>('manual')
const delaySeconds = ref('5')
const mediaTimeoutSeconds = ref('300')
const timelineTimeoutSeconds = ref('300')
const lastDurationSeconds = ref('0.4')

const advanceModeOptions = computed(() => buildAdvanceModeOptions(props.capabilities))
const mediaEndAvailable = computed(() => isMediaEndAdvanceAvailable(props.capabilities))
const timelineEndAvailable = computed(() => isTimelineEndAdvanceAvailable(props.capabilities))
const mediaEndUnavailable = computed(() => {
  return props.capabilities != null && overrideAdvance.value && advanceMode.value === 'media_end' && !mediaEndAvailable.value
})
const timelineEndUnavailable = computed(() => {
  return props.capabilities != null && overrideAdvance.value && advanceMode.value === 'timeline_end' && !timelineEndAvailable.value
})
const inheritedTransitionSummary = computed(() => {
  const transition = props.defaults.transition
  if (transition.effect === 'none') {
    return '继承项目默认：无动画。'
  }
  return `继承项目默认：${TRANSITION_EFFECT_LABELS[transition.effect]} ${formatMillisecondsAsSeconds(transition.duration_ms)} 秒。`
})
const inheritedAdvanceSummary = computed(() => {
  const advance = props.defaults.advance
  const mode = ADVANCE_MODE_LABELS[advance.mode]
  const delay = formatMillisecondsAsSeconds(advance.delay_ms)
  if (advance.mode === 'media_end') {
    const timeout = formatMillisecondsAsSeconds(advance.media_timeout_ms ?? 300000)
    return `继承项目默认：${mode}，无媒体时停留 ${delay} 秒，等待上限 ${timeout} 秒。`
  }
  if (advance.mode === 'timeline_end') {
    const timeout = formatMillisecondsAsSeconds(advance.timeline_timeout_ms ?? 300000)
    return `继承项目默认：${mode}，无时间轴时显示错误，等待上限 ${timeout} 秒。`
  }
  return `继承项目默认：${mode}，停留 ${delay} 秒。`
})

watch(
  () => [props.transition, props.advance, props.defaults] as const,
  ([transition, advance]) => {
    overrideTransition.value = transition !== null
    overrideAdvance.value = advance !== null
    effect.value = transition?.effect ?? props.defaults.transition.effect
    durationSeconds.value = formatMillisecondsAsSeconds(transition?.duration_ms ?? props.defaults.transition.duration_ms)
    if (effect.value !== 'none' && Number.parseFloat(durationSeconds.value) > 0) {
      lastDurationSeconds.value = durationSeconds.value
    }
    advanceMode.value = advance?.mode ?? props.defaults.advance.mode
    delaySeconds.value = formatMillisecondsAsSeconds(advance?.delay_ms ?? props.defaults.advance.delay_ms)
    mediaTimeoutSeconds.value = formatMillisecondsAsSeconds(
      advance?.media_timeout_ms ?? props.defaults.advance.media_timeout_ms ?? 300000,
    )
    timelineTimeoutSeconds.value = formatMillisecondsAsSeconds(
      advance?.timeline_timeout_ms ?? props.defaults.advance.timeline_timeout_ms ?? 300000,
    )
  },
  { immediate: true, deep: true },
)

/** 切换动画覆盖；开启时以当前生效值初始化并立即写入，关闭时显式提交 null。 */
function toggleTransition(value: boolean | 'indeterminate'): void {
  overrideTransition.value = value === true
  if (overrideTransition.value) {
    effect.value = props.transition?.effect ?? props.defaults.transition.effect
    durationSeconds.value = formatMillisecondsAsSeconds(
      props.transition?.duration_ms ?? props.defaults.transition.duration_ms,
    )
    lastDurationSeconds.value = effect.value === 'none' ? '0.4' : durationSeconds.value
    commitTransition()
    return
  }
  effect.value = props.defaults.transition.effect
  durationSeconds.value = formatMillisecondsAsSeconds(props.defaults.transition.duration_ms)
  emit('update:transition', null)
}

/** 切换翻页覆盖；开启时以当前生效值初始化并立即写入，关闭时显式提交 null。 */
function toggleAdvance(value: boolean | 'indeterminate'): void {
  overrideAdvance.value = value === true
  if (overrideAdvance.value) {
    advanceMode.value = props.advance?.mode ?? props.defaults.advance.mode
    delaySeconds.value = formatMillisecondsAsSeconds(props.advance?.delay_ms ?? props.defaults.advance.delay_ms)
    mediaTimeoutSeconds.value = formatMillisecondsAsSeconds(
      props.advance?.media_timeout_ms ?? props.defaults.advance.media_timeout_ms ?? 300000,
    )
    timelineTimeoutSeconds.value = formatMillisecondsAsSeconds(
      props.advance?.timeline_timeout_ms ?? props.defaults.advance.timeline_timeout_ms ?? 300000,
    )
    commitAdvance()
    return
  }
  advanceMode.value = props.defaults.advance.mode
  delaySeconds.value = formatMillisecondsAsSeconds(props.defaults.advance.delay_ms)
  mediaTimeoutSeconds.value = formatMillisecondsAsSeconds(props.defaults.advance.media_timeout_ms ?? 300000)
  timelineTimeoutSeconds.value = formatMillisecondsAsSeconds(props.defaults.advance.timeline_timeout_ms ?? 300000)
  emit('update:advance', null)
}

/** 切换动画效果；无动画固定 0 秒，其它效果恢复上一次有效时长。 */
function updateEffect(value: unknown): void {
  if (effect.value !== 'none' && Number.parseFloat(durationSeconds.value) > 0) {
    lastDurationSeconds.value = durationSeconds.value
  }
  effect.value = value === 'none' ? 'none' : value === 'push' ? 'push' : 'fade'
  if (effect.value === 'none') {
    durationSeconds.value = '0'
  } else {
    const restored = Number.parseFloat(lastDurationSeconds.value || '0.4')
    durationSeconds.value = formatMillisecondsAsSeconds(
      Math.round((Number.isFinite(restored) && restored > 0 ? restored : 0.4) * 1000),
    )
  }
  commitTransition()
}

/** 切换翻页模式；媒体结束不可用时保持当前选择。 */
function updateAdvanceMode(value: unknown): void {
  const mode = value === 'timer' || value === 'media_end' || value === 'timeline_end' ? value : 'manual'
  if (mode === 'media_end' && !mediaEndAvailable.value) {
    return
  }
  if (mode === 'timeline_end' && !timelineEndAvailable.value) {
    return
  }
  advanceMode.value = mode
  commitAdvance()
}

/** 收敛并提交动画覆盖。 */
function commitTransition(): void {
  if (!overrideTransition.value) {
    return
  }
  if (effect.value !== 'none' && Number.parseFloat(durationSeconds.value) > 0) {
    lastDurationSeconds.value = durationSeconds.value
  }
  const durationMs = effect.value === 'none'
    ? 0
    : clamp(
      parseSecondsToMilliseconds(durationSeconds.value),
      TRANSITION_DURATION_MIN_MS,
      TRANSITION_DURATION_MAX_MS,
      props.defaults.transition.duration_ms,
    )
  emit('update:transition', {
    effect: effect.value,
    duration_ms: durationMs,
  })
}

/** 收敛并提交翻页覆盖。 */
function commitAdvance(): void {
  if (!overrideAdvance.value) {
    return
  }
  emit('update:advance', {
    mode: advanceMode.value,
    delay_ms: clamp(
      parseSecondsToMilliseconds(delaySeconds.value),
      ADVANCE_DELAY_MIN_MS,
      ADVANCE_DELAY_MAX_MS,
      props.defaults.advance.delay_ms,
    ),
    media_timeout_ms: clamp(
      parseSecondsToMilliseconds(mediaTimeoutSeconds.value),
      MEDIA_TIMEOUT_MIN_MS,
      MEDIA_TIMEOUT_MAX_MS,
      props.advance?.media_timeout_ms ?? props.defaults.advance.media_timeout_ms ?? 300000,
    ),
    timeline_timeout_ms: clamp(
      parseSecondsToMilliseconds(timelineTimeoutSeconds.value),
      TIMELINE_TIMEOUT_MIN_MS,
      TIMELINE_TIMEOUT_MAX_MS,
      props.advance?.timeline_timeout_ms ?? props.defaults.advance.timeline_timeout_ms ?? 300000,
    ),
  })
}

/** 将毫秒值收敛到允许范围；非法输入使用兜底值。 */
function clamp(value: number | null, min: number, max: number, fallback: number): number {
  if (value === null) {
    return fallback
  }
  return Math.min(max, Math.max(min, value))
}
</script>
