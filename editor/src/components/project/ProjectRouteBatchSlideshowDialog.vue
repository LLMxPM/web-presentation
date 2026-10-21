<!-- 文件功能：批量设置选中页面或本章的放映覆盖，支持保持原样、恢复继承与统一覆盖。 -->
<template>
  <UiDialog
    :open="open"
    title="批量放映设置"
    size="compact"
    width="600px"
    body-preset="dense"
    :panel-style="{ height: 'auto' }"
    @update:open="emit('update:open', $event)"
  >
    <div class="grid gap-4">
      <p class="text-sm leading-6 text-text-muted">
        将应用到 {{ pageCount }} 个页面<template v-if="itemCount > pageCount">（含分组展开，共 {{ itemCount }} 项）</template>。
        隐藏页也会保存设置，但不会参与放映。覆盖值默认取项目默认，可在下方调整。
      </p>

      <section class="rounded-ui-lg border border-border p-3">
        <h4 class="text-sm font-semibold text-text-emphasis">翻页动画</h4>
        <div class="mt-2">
          <UiSegmentedControl v-model="transitionAction" :options="actionOptions" aria-label="翻页动画处理方式" />
        </div>
        <p v-if="transitionAction === 'inherit'" class="mt-2 text-xs text-text-disabled">将清除这些页面的动画覆盖，恢复项目默认。</p>
        <div v-if="transitionAction === 'override'" class="mt-3 grid grid-cols-2 gap-3">
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
              />
            </template>
          </UiFormField>
        </div>
      </section>

      <section class="rounded-ui-lg border border-border p-3">
        <h4 class="text-sm font-semibold text-text-emphasis">翻页方式</h4>
        <div class="mt-2">
          <UiSegmentedControl v-model="advanceAction" :options="actionOptions" aria-label="翻页方式处理方式" />
        </div>
        <p v-if="advanceAction === 'inherit'" class="mt-2 text-xs text-text-disabled">将清除这些页面的翻页覆盖，恢复项目默认。</p>
        <div v-if="advanceAction === 'override'" class="mt-3 grid grid-cols-2 gap-3">
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
        <div v-if="advanceAction === 'override' && advanceMode === 'media_end'" class="mt-3 grid grid-cols-2 gap-3">
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
        <p v-if="mediaEndUnavailable" class="mt-2 text-xs font-medium text-warning-strong" role="status">
          当前服务端未开放媒体结束模式，请改用其它翻页方式后保存。
        </p>
      </section>
    </div>

    <template #footer>
      <UiButton variant="ghost" @click="emit('update:open', false)">取消</UiButton>
      <UiButton variant="primary" :disabled="!canApply" @click="handleApply">应用</UiButton>
    </template>
  </UiDialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { UiButton, UiDialog, UiFormField, UiInput, UiSegmentedControl, UiSelect } from '@/components/ui'
import type { SlideshowCapabilities, SlideshowSettings } from '@/types/api'
import type { SlideshowBatchPatch } from '@/utils/project-route-slideshow'
import type { SlideshowAdvanceMode, SlideshowEffect } from './project-slideshow-values'
import {
  ADVANCE_DELAY_MAX_MS,
  ADVANCE_DELAY_MIN_MS,
  MEDIA_TIMEOUT_MAX_MS,
  MEDIA_TIMEOUT_MIN_MS,
  TIMELINE_TIMEOUT_MAX_MS,
  TIMELINE_TIMEOUT_MIN_MS,
  TRANSITION_DURATION_MAX_MS,
  TRANSITION_DURATION_MIN_MS,
  TRANSITION_EFFECT_OPTIONS,
  buildAdvanceModeOptions,
  formatMillisecondsAsSeconds,
  isMediaEndAdvanceAvailable,
  isTimelineEndAdvanceAvailable,
  parseSecondsToMilliseconds,
} from './project-slideshow-values'

type BatchAction = 'keep' | 'inherit' | 'override'

const props = withDefaults(defineProps<{
  open: boolean
  itemCount: number
  pageCount: number
  defaults: SlideshowSettings
  capabilities?: SlideshowCapabilities | null
}>(), {
  capabilities: null,
})

const emit = defineEmits<{
  'update:open': [value: boolean]
  apply: [value: SlideshowBatchPatch]
}>()

const actionOptions = [
  { label: '不修改', value: 'keep' },
  { label: '恢复继承', value: 'inherit' },
  { label: '设置覆盖', value: 'override' },
]
const transitionAction = ref<BatchAction>('keep')
const advanceAction = ref<BatchAction>('keep')
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
  return props.capabilities != null && advanceAction.value === 'override' && advanceMode.value === 'media_end' && !mediaEndAvailable.value
})
const canApply = computed(() => transitionAction.value !== 'keep' || advanceAction.value !== 'keep')

watch(
  () => props.open,
  open => {
    if (!open) {
      return
    }
    transitionAction.value = 'keep'
    advanceAction.value = 'keep'
    effect.value = props.defaults.transition.effect
    durationSeconds.value = formatMillisecondsAsSeconds(props.defaults.transition.duration_ms)
    lastDurationSeconds.value = effect.value === 'none' ? '0.4' : durationSeconds.value
    advanceMode.value = props.defaults.advance.mode
    delaySeconds.value = formatMillisecondsAsSeconds(props.defaults.advance.delay_ms)
    mediaTimeoutSeconds.value = formatMillisecondsAsSeconds(props.defaults.advance.media_timeout_ms ?? 300000)
    timelineTimeoutSeconds.value = formatMillisecondsAsSeconds(props.defaults.advance.timeline_timeout_ms ?? 300000)
  },
  { immediate: true },
)

/** 无动画固定 0 秒，其它效果恢复上一次有效时长。 */
function updateEffect(value: unknown): void {
  if (effect.value !== 'none' && Number.parseFloat(durationSeconds.value) > 0) {
    lastDurationSeconds.value = durationSeconds.value
  }
  effect.value = value === 'none' ? 'none' : value === 'push' ? 'push' : 'fade'
  if (effect.value === 'none') {
    durationSeconds.value = '0'
    return
  }
  const restored = Number.parseFloat(lastDurationSeconds.value || '0.4')
  durationSeconds.value = formatMillisecondsAsSeconds(
    Math.round((Number.isFinite(restored) && restored > 0 ? restored : 0.4) * 1000),
  )
}

/** 媒体结束不可用时保持当前选择。 */
function updateAdvanceMode(value: unknown): void {
  const mode = value === 'timer' || value === 'media_end' || value === 'timeline_end' ? value : 'manual'
  if (mode === 'media_end' && !mediaEndAvailable.value) {
    return
  }
  if (mode === 'timeline_end' && !timelineEndAvailable.value) {
    return
  }
  advanceMode.value = mode
}

/** 组装批量 patch；未选择的组不写入，确保保持原样。 */
function handleApply(): void {
  const patch: SlideshowBatchPatch = {}
  if (transitionAction.value !== 'keep') {
    patch.transition = transitionAction.value === 'inherit'
      ? null
      : {
        effect: effect.value,
        duration_ms: effect.value === 'none'
          ? 0
          : clamp(
            parseSecondsToMilliseconds(durationSeconds.value),
            TRANSITION_DURATION_MIN_MS,
            TRANSITION_DURATION_MAX_MS,
            props.defaults.transition.duration_ms,
          ),
      }
  }
  if (advanceAction.value !== 'keep') {
    patch.advance = advanceAction.value === 'inherit'
      ? null
      : {
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
          props.defaults.advance.media_timeout_ms ?? 300000,
        ),
        timeline_timeout_ms: clamp(
          parseSecondsToMilliseconds(timelineTimeoutSeconds.value),
          TIMELINE_TIMEOUT_MIN_MS,
          TIMELINE_TIMEOUT_MAX_MS,
          props.defaults.advance.timeline_timeout_ms ?? 300000,
        ),
      }
  }
  emit('apply', patch)
  emit('update:open', false)
}

/** 将毫秒值收敛到允许范围；非法输入使用兜底值。 */
function clamp(value: number | null, min: number, max: number, fallback: number): number {
  if (value === null) {
    return fallback
  }
  return Math.min(max, Math.max(min, value))
}
</script>
