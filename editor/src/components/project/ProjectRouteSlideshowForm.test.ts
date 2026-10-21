/**
 * 文件功能：验证检查器内逐页放映表单的继承初始化、覆盖提交与媒体能力提示。
 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import type { SlideshowCapabilities, SlideshowSettings } from '@/types/api'
import ProjectRouteSlideshowForm from './ProjectRouteSlideshowForm.vue'

const defaults: SlideshowSettings = {
  transition: { effect: 'fade', duration_ms: 400 },
  advance: { mode: 'timer', delay_ms: 5000, media_timeout_ms: 300000, timeline_timeout_ms: 300000 },
  loop: false,
  auto_start: false,
}

const capabilities: SlideshowCapabilities = {
  schema_version: 2,
  transition_effects: ['none', 'fade', 'push'],
  advance_modes: ['manual', 'timer', 'media_end'],
  single_window_auto_play: true,
  presenter_auto_play: false,
  capture_auto_play: false,
  transition_duration_ms: { min: 100, max: 2000, none: 0 },
  delay_ms: { min: 1000, max: 3600000 },
  media_timeout_ms: { min: 1000, max: 3600000 },
  timeline_timeout_ms: { min: 1000, max: 3600000 },
}

const formStubs = {
  UiCheckbox: {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<button type="button" role="checkbox" :aria-checked="modelValue" @click="$emit(\'update:modelValue\', !modelValue)"><slot /></button>',
  },
  UiFormField: {
    props: ['label'],
    template: '<label><span>{{ label }}</span><slot inputId="field" :describedBy="undefined" /></label>',
  },
  UiSelect: {
    props: ['modelValue', 'options'],
    emits: ['update:modelValue'],
    template: `
      <select :value="modelValue" @change="$emit('update:modelValue', $event.target.value)">
        <option v-for="option in options" :key="option.value" :value="option.value">{{ option.label }}</option>
      </select>
    `,
  },
  UiInput: {
    props: ['modelValue'],
    emits: ['update:modelValue', 'change', 'blur'],
    template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" @change="$emit(\'change\')" @blur="$emit(\'blur\')">',
  },
}

describe('ProjectRouteSlideshowForm', () => {
  it('勾选覆盖动画时应以生效值初始化，取消时提交 null', async () => {
    const { emitted } = render(ProjectRouteSlideshowForm, {
      props: {
        transition: null,
        advance: null,
        defaults,
      },
      global: { stubs: formStubs },
    })

    await fireEvent.click(screen.getByRole('checkbox', { name: '覆盖翻页动画' }))

    expect((emitted('update:transition') as Array<[unknown]>).at(-1)?.[0])
      .toEqual({ effect: 'fade', duration_ms: 400 })

    await fireEvent.click(screen.getByRole('checkbox', { name: '覆盖翻页动画' }))
    expect((emitted('update:transition') as Array<[unknown]>).at(-1)?.[0]).toBeNull()
  })

  it('媒体结束覆盖应展示等待上限并按修改后的停留时间提交', async () => {
    const { emitted } = render(ProjectRouteSlideshowForm, {
      props: {
        transition: null,
        advance: { mode: 'media_end', delay_ms: 6000, media_timeout_ms: 120000 },
        defaults,
        capabilities,
      },
      global: { stubs: formStubs },
    })

    expect(screen.getByDisplayValue('6')).toBeInTheDocument()
    expect(screen.getByDisplayValue('120')).toBeInTheDocument()
    expect(screen.getByText(/循环背景媒体不参与等待/)).toBeInTheDocument()

    const delayInput = screen.getByDisplayValue('6')
    await fireEvent.update(delayInput, '7')
    await fireEvent.blur(delayInput)

    const advanceEmits = emitted('update:advance') as Array<[unknown]>
    expect(advanceEmits.at(-1)?.[0]).toEqual({
      mode: 'media_end',
      delay_ms: 7000,
      media_timeout_ms: 120000,
      timeline_timeout_ms: 300000,
    })
  })

  it('时间轴结束覆盖应展示继承说明与等待上限并提交完整配置', async () => {
    const timelineCapabilities: SlideshowCapabilities = {
      ...capabilities,
      advance_modes: ['manual', 'timer', 'media_end', 'timeline_end'],
    }
    const { emitted } = render(ProjectRouteSlideshowForm, {
      props: {
        transition: null,
        advance: { mode: 'timeline_end', delay_ms: 5000, timeline_timeout_ms: 180000 },
        defaults,
        capabilities: timelineCapabilities,
      },
      global: { stubs: formStubs },
    })

    expect(screen.getByDisplayValue('180')).toBeInTheDocument()
    expect(screen.getByText(/页面没有可用时间轴时按停留时长翻页/)).toBeInTheDocument()

    const timeoutInput = screen.getByDisplayValue('180')
    await fireEvent.update(timeoutInput, '240')
    await fireEvent.blur(timeoutInput)

    const advanceEmits = emitted('update:advance') as Array<[unknown]>
    expect(advanceEmits.at(-1)?.[0]).toEqual({
      mode: 'timeline_end',
      delay_ms: 5000,
      media_timeout_ms: 300000,
      timeline_timeout_ms: 240000,
    })
  })

  it('无覆盖时应展示项目默认摘要', () => {
    render(ProjectRouteSlideshowForm, {
      props: {
        transition: null,
        advance: null,
        defaults,
      },
      global: { stubs: formStubs },
    })

    expect(screen.getByText('继承项目默认：淡入淡出 0.4 秒。')).toBeInTheDocument()
    expect(screen.getByText('继承项目默认：定时翻页，停留 5 秒。')).toBeInTheDocument()
  })

  it('能力未开放媒体结束时应给出提示', () => {
    render(ProjectRouteSlideshowForm, {
      props: {
        transition: null,
        advance: { mode: 'media_end', delay_ms: 6000, media_timeout_ms: 120000 },
        defaults,
        capabilities: { ...capabilities, advance_modes: ['manual', 'timer'] },
      },
      global: { stubs: formStubs },
    })

    expect(screen.getByText('当前服务端未开放媒体结束模式，请改用其它翻页方式后保存。')).toBeInTheDocument()
  })
})
