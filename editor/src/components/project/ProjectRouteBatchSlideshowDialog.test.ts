/**
 * 文件功能：验证批量放映设置的三态提交、整组覆盖与媒体等待字段。
 */
import { fireEvent, render, screen, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import type { SlideshowCapabilities, SlideshowSettings } from '@/types/api'
import ProjectRouteBatchSlideshowDialog from './ProjectRouteBatchSlideshowDialog.vue'

const defaults: SlideshowSettings = {
  transition: { effect: 'fade', duration_ms: 400 },
  advance: { mode: 'timer', delay_ms: 5000, media_timeout_ms: 300000 },
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
}

const batchStubs = {
  UiDialog: { template: '<div><slot /><slot name="footer" /></div>' },
  UiSegmentedControl: {
    props: ['modelValue', 'options'],
    emits: ['update:modelValue'],
    template: '<div role="group"><button v-for="option in options" :key="option.value" type="button" @click="$emit(\'update:modelValue\', option.value)">{{ option.label }}</button></div>',
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
    emits: ['update:modelValue'],
    template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)">',
  },
}

describe('ProjectRouteBatchSlideshowDialog', () => {
  it('未选择处理方式时应用按钮不可用', () => {
    render(ProjectRouteBatchSlideshowDialog, {
      props: {
        open: true,
        itemCount: 7,
        pageCount: 5,
        defaults,
        capabilities,
      },
      global: { stubs: batchStubs },
    })

    expect(screen.getByRole('button', { name: '应用' })).toBeDisabled()
    expect(screen.getByText(/共 7 项/)).toBeInTheDocument()
  })

  it('只恢复动画继承时不应写入翻页字段', async () => {
    const { emitted } = render(ProjectRouteBatchSlideshowDialog, {
      props: {
        open: true,
        itemCount: 1,
        pageCount: 3,
        defaults,
        capabilities,
      },
      global: { stubs: batchStubs },
    })

    const transitionGroup = screen.getAllByRole('group')[0]
    await fireEvent.click(within(transitionGroup).getByRole('button', { name: '恢复继承' }))
    await fireEvent.click(screen.getByRole('button', { name: '应用' }))

    expect((emitted('apply') as Array<[unknown]>).at(-1)?.[0]).toEqual({ transition: null })
  })

  it('同时设置两组覆盖时应提交完整对象', async () => {
    const { emitted } = render(ProjectRouteBatchSlideshowDialog, {
      props: {
        open: true,
        itemCount: 1,
        pageCount: 3,
        defaults,
        capabilities,
      },
      global: { stubs: batchStubs },
    })

    const groups = screen.getAllByRole('group')
    await fireEvent.click(within(groups[0]).getByRole('button', { name: '设置覆盖' }))
    await fireEvent.click(within(groups[1]).getByRole('button', { name: '设置覆盖' }))
    await fireEvent.click(screen.getByRole('button', { name: '应用' }))

    expect((emitted('apply') as Array<[unknown]>).at(-1)?.[0]).toEqual({
      transition: { effect: 'fade', duration_ms: 400 },
      advance: { mode: 'timer', delay_ms: 5000, media_timeout_ms: 300000 },
    })
  })

  it('媒体结束覆盖应保留等待上限并提交修改后的停留时间', async () => {
    const { emitted } = render(ProjectRouteBatchSlideshowDialog, {
      props: {
        open: true,
        itemCount: 1,
        pageCount: 3,
        defaults,
        capabilities,
      },
      global: { stubs: batchStubs },
    })

    const groups = screen.getAllByRole('group')
    await fireEvent.click(within(groups[1]).getByRole('button', { name: '设置覆盖' }))

    const modeSelect = screen.getByRole('combobox')
    await fireEvent.update(modeSelect, 'media_end')

    const delayInput = screen.getByDisplayValue('5')
    await fireEvent.update(delayInput, '6')

    await fireEvent.click(screen.getByRole('button', { name: '应用' }))

    expect((emitted('apply') as Array<[unknown]>).at(-1)?.[0]).toEqual({
      advance: { mode: 'media_end', delay_ms: 6000, media_timeout_ms: 300000 },
    })
  })
})
