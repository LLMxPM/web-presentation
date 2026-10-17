<!-- 文件功能：项目默认放映配置表单，编辑翻页效果、动画时长、停留时间、循环与自动开始。 -->
<template>
  <div class="grid gap-4">
    <fieldset class="min-w-0">
      <legend class="text-sm font-semibold text-text-emphasis">翻页动画</legend>
      <p class="mt-0.5 text-xs text-text-disabled">进入目标页时的整页效果；翻回上一页时 push 方向自动反转。</p>

      <div class="mt-3 grid grid-cols-2 gap-3">
        <UiFormField label="动画效果">
          <template #default="field">
            <UiSelect
              :model-value="draft.effect"
              :options="effectOptions"
              :id="field.inputId"
              :aria-describedby="field.describedBy"
              @update:model-value="updateEffect"
            />
          </template>
        </UiFormField>
        <UiFormField label="动画时长（秒）">
          <template #default="field">
            <UiInput
              :model-value="draft.durationSeconds"
              inputmode="decimal"
              placeholder="0.4"
              :disabled="draft.effect === 'none'"
              :input-id="field.inputId"
              :described-by="field.describedBy"
              @update:model-value="updateDuration"
            />
          </template>
        </UiFormField>
      </div>
    </fieldset>

    <fieldset class="min-w-0 border-t border-border pt-3">
      <legend class="text-sm font-semibold text-text-emphasis">翻页方式</legend>
      <p class="mt-0.5 text-xs text-text-disabled">动画结束后开始计时；手动模式保留停留时长但不自动翻页。</p>

      <div class="mt-3 grid grid-cols-2 gap-3">
        <UiFormField label="翻页模式">
          <template #default="field">
            <UiSelect
              :model-value="draft.advanceMode"
              :options="advanceModeOptions"
              :id="field.inputId"
              :aria-describedby="field.describedBy"
              @update:model-value="updateAdvanceMode"
            />
          </template>
        </UiFormField>
        <UiFormField label="停留时长（秒）">
          <template #default="field">
            <UiInput
              :model-value="draft.delaySeconds"
              inputmode="decimal"
              placeholder="5"
              :input-id="field.inputId"
              :described-by="field.describedBy"
              @update:model-value="updateDelay"
            />
          </template>
        </UiFormField>
      </div>

      <div class="mt-3 grid gap-2 sm:grid-cols-2">
        <label class="flex items-center gap-2 text-sm text-text">
          <UiCheckbox :model-value="draft.loop" @update:model-value="updateLoop" />
          循环放映（末页后回到第一页）
        </label>
        <label class="flex items-center gap-2 text-sm text-text">
          <UiCheckbox :model-value="draft.autoStart" @update:model-value="updateAutoStart" />
          预览时自动开始
        </label>
      </div>
      <p class="mt-2 text-xs text-text-disabled">
        自动开始需放映入口支持，部分浏览器会要求先点击页面后才允许播放或翻页。
      </p>
    </fieldset>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

import { UiCheckbox, UiFormField, UiInput, UiSelect } from '@/components/ui'
import type { SlideshowDraft } from './project-slideshow-values'
import { formatMillisecondsAsSeconds } from './project-slideshow-values'

const props = defineProps<{
  draft: SlideshowDraft
}>()

const emit = defineEmits<{
  'update:draft': [value: SlideshowDraft]
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

// 切到“无动画”时保留上一段有效时长，切回其它效果时恢复，避免用户反复重填。
const lastDurationSeconds = ref(props.draft.effect === 'none' ? '0.4' : props.draft.durationSeconds)

watch(
  () => props.draft.durationSeconds,
  value => {
    if (props.draft.effect !== 'none' && Number.parseFloat(value) > 0) {
      lastDurationSeconds.value = value
    }
  },
)

/**
 * 合并草稿字段并回传完整草稿，避免父组件维护多份状态。
 */
function patchDraft(patch: Partial<SlideshowDraft>): void {
  emit('update:draft', { ...props.draft, ...patch })
}

/**
 * 切换动画效果；无动画固定 0 秒，其它效果恢复上次时长。
 */
function updateEffect(value: unknown): void {
  if (value === 'none') {
    patchDraft({ effect: 'none', durationSeconds: '0' })
    return
  }
  const effect = value === 'push' ? 'push' : 'fade'
  const restored = formatMillisecondsAsSeconds(Math.round(Number.parseFloat(lastDurationSeconds.value || '0.4') * 1000))
  patchDraft({ effect, durationSeconds: restored === '0' ? '0.4' : restored })
}

function updateDuration(value: string | number): void {
  patchDraft({ durationSeconds: String(value) })
}

function updateAdvanceMode(value: unknown): void {
  patchDraft({ advanceMode: value === 'timer' ? 'timer' : 'manual' })
}

function updateDelay(value: string | number): void {
  patchDraft({ delaySeconds: String(value) })
}

function updateLoop(value: boolean | 'indeterminate'): void {
  patchDraft({ loop: value === true })
}

function updateAutoStart(value: boolean | 'indeterminate'): void {
  patchDraft({ autoStart: value === true })
}
</script>
