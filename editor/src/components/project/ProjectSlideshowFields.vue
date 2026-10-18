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
      <p class="mt-0.5 text-xs text-text-disabled">动画结束后开始计时；媒体结束模式等待当前页音视频播完。</p>

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
        <UiFormField :label="delayFieldLabel">
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

      <p v-if="draft.advanceMode === 'timer'" class="mt-2 text-xs text-text-disabled">
        若使用页面旁白，定时推进会在计时到达时停止旁白并翻页；旁白页面建议改用“媒体结束”。
      </p>

      <div v-if="draft.advanceMode === 'media_end'" class="mt-3 grid grid-cols-2 gap-3">
        <UiFormField label="媒体等待上限（秒）">
          <template #default="field">
            <UiInput
              :model-value="draft.mediaTimeoutSeconds ?? ''"
              inputmode="decimal"
              placeholder="300"
              :input-id="field.inputId"
              :described-by="field.describedBy"
              @update:model-value="updateMediaTimeout"
            />
          </template>
        </UiFormField>
      </div>

      <template v-if="draft.advanceMode === 'media_end'">
        <p class="mt-2 text-xs text-text-disabled">
          播放当前页的非循环音视频，全部结束后翻页；没有可等待媒体时按停留时长翻页。循环背景媒体不参与等待。
          切换到手动模式时媒体继续播放，但不会自动翻页。
        </p>
        <p class="mt-1 text-xs text-text-disabled">
          若浏览器阻止自动播放，放映窗口会显示受阻提示，可点“重试”恢复或使用“下一页”继续。
        </p>
        <p v-if="mediaEndUnavailable" class="mt-1 text-xs font-medium text-warning-strong" role="status">
          当前服务端未开放媒体结束模式，请改用其它翻页方式后保存。
        </p>
      </template>

      <div class="mt-3 grid gap-2 sm:grid-cols-2">
        <label class="flex items-center gap-2 text-sm text-text">
          <UiCheckbox :model-value="draft.loop" @update:model-value="updateLoop" />
          循环放映（末页后回到第一页）
        </label>
        <label class="flex items-center gap-2 text-sm text-text">
          <UiCheckbox :model-value="draft.autoStart" @update:model-value="updateAutoStart" />
          进入放映后自动推进
        </label>
      </div>
      <p class="mt-2 text-xs text-text-disabled">
        开启后进入全屏放映时按当前页翻页方式自动推进；关闭时进入手动模式，仍可在放映控制条随时切回自动。
        浏览器要求全屏由用户手势触发，请在 Runtime 窗口点击“进入放映”。
      </p>
    </fieldset>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { UiCheckbox, UiFormField, UiInput, UiSelect } from '@/components/ui'
import type { SlideshowCapabilities } from '@/types/api'
import type { SlideshowDraft } from './project-slideshow-values'
import {
  buildAdvanceModeOptions,
  formatMillisecondsAsSeconds,
  isMediaEndAdvanceAvailable,
} from './project-slideshow-values'

const props = withDefaults(defineProps<{
  draft: SlideshowDraft
  capabilities?: SlideshowCapabilities | null
}>(), {
  capabilities: null,
})

const emit = defineEmits<{
  'update:draft': [value: SlideshowDraft]
}>()

const effectOptions = [
  { label: '淡入淡出', value: 'fade' },
  { label: '推入', value: 'push' },
  { label: '无动画', value: 'none' },
]
const mediaEndAvailable = computed(() => isMediaEndAdvanceAvailable(props.capabilities))
const advanceModeOptions = computed(() => buildAdvanceModeOptions(props.capabilities))
const delayFieldLabel = computed(() => props.draft.advanceMode === 'media_end' ? '无媒体时停留（秒）' : '停留时长（秒）')
const mediaEndUnavailable = computed(() => {
  return props.capabilities != null && props.draft.advanceMode === 'media_end' && !mediaEndAvailable.value
})

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
  const mode = value === 'timer' || value === 'media_end' ? value : 'manual'
  if (mode === 'media_end' && !mediaEndAvailable.value) {
    return
  }
  patchDraft({
    advanceMode: mode,
    mediaTimeoutSeconds: mode === 'media_end' ? props.draft.mediaTimeoutSeconds ?? '300' : props.draft.mediaTimeoutSeconds,
  })
}

function updateDelay(value: string | number): void {
  patchDraft({ delaySeconds: String(value) })
}

function updateMediaTimeout(value: string | number): void {
  patchDraft({ mediaTimeoutSeconds: String(value) })
}

function updateLoop(value: boolean | 'indeterminate'): void {
  patchDraft({ loop: value === true })
}

function updateAutoStart(value: boolean | 'indeterminate'): void {
  patchDraft({ autoStart: value === true })
}
</script>
