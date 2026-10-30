/** 文件功能：为放映配置组合测试提供 schema 4 真实 DTO 夹具与原生表单交互替身。 */
import type { SlideshowCapabilities } from '@/types/api'
export const sceneCapabilities: SlideshowCapabilities = { schema_version: 4, transition_effects: ['none', 'fade', 'push'], advance_modes: ['manual', 'timer', 'scene_end'],
  single_window_auto_play: true, presenter_auto_play: true, capture_auto_play: false,
  transition_duration_ms: { min: 100, max: 2000, none: 0 }, delay_ms: { min: 1000, max: 3600000 }, completion_delay_ms: { min: 0, max: 3600000 },
  audio: { schema_version: 1, audio_assets: true, page_narration: true, audio_cues: true } }
export const slideshowFormStubs = {
  UiSelect: { props: ['modelValue', 'options'], emits: ['update:modelValue'], template: '<select :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value)"><option v-for="item in options" :key="item.value" :value="item.value">{{ item.label }}</option></select>' },
  UiInput: { props: ['modelValue', 'disabled'], emits: ['update:modelValue', 'blur', 'change'], template: '<input :value="modelValue" :disabled="disabled" @input="$emit(\'update:modelValue\', $event.target.value)" @blur="$emit(\'blur\')" @change="$emit(\'change\')">' },
  UiFormField: { props: ['label'], template: '<label><span>{{ label }}</span><slot inputId="field" /></label>' },
  UiCheckbox: { props: ['modelValue'], emits: ['update:modelValue'], template: '<input type="checkbox" :checked="modelValue" @change="$emit(\'update:modelValue\', $event.target.checked)">' },
  UiDialog: { props: ['open'], emits: ['update:open'], template: '<section v-if="open" role="dialog"><slot /><slot name="footer" /></section>' },
  UiSegmentedControl: { props: ['modelValue', 'options'], emits: ['update:modelValue'], template: '<div role="group"><button v-for="item in options" :key="item.value" type="button" @click="$emit(\'update:modelValue\', item.value)">{{ item.label }}</button></div>' },
}
