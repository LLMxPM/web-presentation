<!-- 文件功能：复用 schema 4 项目、单页与批量放映字段，区分定时停留和实际完成后的停留。 -->
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { UiCheckbox, UiFormField, UiInput, UiSelect } from '@/components/ui'
import type { SlideshowCapabilities } from '@/types/api'
import { TRANSITION_EFFECT_OPTIONS, buildAdvanceModeOptions, isSceneEndAdvanceAvailable, type SlideshowDraft } from './project-slideshow-values'

const props = withDefaults(defineProps<{ draft: SlideshowDraft; capabilities?: SlideshowCapabilities | null; section?: 'all' | 'transition' | 'advance'; showLoop?: boolean }>(), { capabilities: null, section: 'all', showLoop: true })
const emit = defineEmits<{ 'update:draft': [value: SlideshowDraft]; commit: [] }>()
const advanceOptions = computed(() => buildAdvanceModeOptions(props.capabilities))
const sceneUnavailable = computed(() => props.capabilities != null && props.draft.advanceMode === 'scene_end' && !isSceneEndAdvanceAvailable(props.capabilities))
const lastDuration = ref(props.draft.effect === 'none' ? '0.4' : props.draft.durationSeconds)
watch(() => props.draft.durationSeconds, value => { if (props.draft.effect !== 'none' && Number(value) > 0) lastDuration.value = value })

/** 回传完整草稿，项目保存与路由覆盖复用同一转换入口。 */
function patch(value: Partial<SlideshowDraft>): void { emit('update:draft', { ...props.draft, ...value }) }
/** 切回动画恢复上次有效时长，无动画固定为零。 */
function effect(value: unknown): void {
  patch({ effect: value === 'none' ? 'none' : value === 'push' ? 'push' : 'fade', durationSeconds: value === 'none' ? '0' : lastDuration.value || '0.4' }); emit('commit')
}
/** 不把未知模式静默转换成可保存配置，只有当前服务声明的模式可选。 */
function advance(value: unknown): void {
  if (!advanceOptions.value.some(option => option.value === value)) return
  patch({ advanceMode: value as SlideshowDraft['advanceMode'] }); emit('commit')
}
</script>
<template>
  <div class="grid gap-4">
    <fieldset v-if="section !== 'advance'" class="min-w-0">
      <legend class="text-sm font-semibold text-text-emphasis">翻页动画</legend>
      <div class="mt-3 grid grid-cols-2 gap-3">
        <UiFormField label="动画效果"><template #default="field"><UiSelect :id="field.inputId" :model-value="draft.effect" :options="TRANSITION_EFFECT_OPTIONS" @update:model-value="effect" /></template></UiFormField>
        <UiFormField label="动画时长（秒）"><template #default="field"><UiInput :input-id="field.inputId" :model-value="draft.durationSeconds" inputmode="decimal" placeholder="0.4" :disabled="draft.effect === 'none'" @update:model-value="patch({ durationSeconds: String($event) })" @blur="emit('commit')" @change="emit('commit')" /></template></UiFormField>
      </div>
    </fieldset>
    <fieldset v-if="section !== 'transition'" class="min-w-0">
      <legend class="text-sm font-semibold text-text-emphasis">翻页方式</legend>
      <div class="mt-3 grid grid-cols-2 gap-3">
        <UiFormField label="翻页模式"><template #default="field"><UiSelect :id="field.inputId" :model-value="draft.advanceMode" :options="advanceOptions" @update:model-value="advance" /></template></UiFormField>
        <UiFormField v-if="draft.advanceMode === 'timer'" label="停留时长（秒）"><template #default="field"><UiInput :input-id="field.inputId" :model-value="draft.delaySeconds" inputmode="decimal" placeholder="5" @update:model-value="patch({ delaySeconds: String($event) })" @blur="emit('commit')" @change="emit('commit')" /></template></UiFormField>
        <UiFormField v-if="draft.advanceMode === 'scene_end'" label="完成后停留（秒）"><template #default="field"><UiInput :input-id="field.inputId" :model-value="draft.completionDelaySeconds" inputmode="decimal" placeholder="0.3" @update:model-value="patch({ completionDelaySeconds: String($event) })" @blur="emit('commit')" @change="emit('commit')" /></template></UiFormField>
      </div>
      <p v-if="draft.advanceMode === 'timer'" class="mt-2 text-xs text-text-muted">过渡与资源就绪后计时，到点翻页并停止本页未完成的播放。</p>
      <p v-if="draft.advanceMode === 'scene_end'" class="mt-2 text-xs text-text-muted">本页有限动画、旁白和视频完成后再停留；循环装饰不参与等待。没有完成目标时会提示配置错误。</p>
      <p v-if="sceneUnavailable" class="mt-2 text-xs text-warning-strong" role="status">当前服务端未声明本页完成模式，请检查服务版本。</p>
      <label v-if="showLoop" class="mt-3 flex items-center gap-2 text-sm text-text"><UiCheckbox :model-value="draft.loop" @update:model-value="patch({ loop: $event === true })" />到达末页后循环放映</label>
    </fieldset>
  </div>
</template>
