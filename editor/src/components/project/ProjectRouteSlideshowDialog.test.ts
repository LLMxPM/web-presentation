/** 文件功能：验证路由放映设置弹窗的继承/覆盖提交、媒体字段与按能力开放模式。 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import ProjectRouteSlideshowDialog from './ProjectRouteSlideshowDialog.vue'
import type { SlideshowCapabilities, SlideshowSettings } from '@/types/api'

const defaults: SlideshowSettings = {
  transition: { effect: 'fade', duration_ms: 400 },
  advance: { mode: 'manual', delay_ms: 5000, media_timeout_ms: 300000 },
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

const dialogStub = {
  UiDialog: { template: '<div><slot /><slot name="footer" /></div>' },
  UiCheckbox: {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<button type="button" role="checkbox" :aria-checked="modelValue" @click="$emit(\'update:modelValue\', !modelValue)"><slot /></button>',
  },
  UiSelect: {
    props: ['modelValue', 'options'],
    emits: ['update:modelValue'],
    template: `
      <select v-bind="$attrs" :value="modelValue" @change="$emit('update:modelValue', $event.target.value)">
        <option v-for="option in options" :key="option.value" :value="option.value">{{ option.label }}</option>
      </select>
    `,
  },
}

describe('ProjectRouteSlideshowDialog', () => {
  it('恢复继承应提交两个 null 组', async () => {
    const { emitted } = render(ProjectRouteSlideshowDialog, {
      props: {
        open: true,
        title: '放映设置',
        transition: { effect: 'push', duration_ms: 600 },
        advance: null,
        defaults,
      },
      global: { stubs: dialogStub },
    })

    await fireEvent.click(screen.getByRole('button', { name: '恢复继承' }))

    expect(emitted('save')?.[0]?.[0]).toEqual({ transition: null, advance: null })
  })

  it('无覆盖时应提交 null，覆盖组按表单值提交', async () => {
    const { emitted } = render(ProjectRouteSlideshowDialog, {
      props: {
        open: true,
        title: '放映设置',
        transition: null,
        advance: null,
        defaults,
      },
      global: { stubs: dialogStub },
    })

    await fireEvent.click(screen.getByRole('button', { name: '应用' }))

    expect(emitted('save')?.[0]?.[0]).toEqual({ transition: null, advance: null })
  })

  it('媒体结束覆盖应提交完整 advance 对象和等待上限', async () => {
    const { emitted } = render(ProjectRouteSlideshowDialog, {
      props: {
        open: true,
        title: '放映设置',
        transition: null,
        advance: { mode: 'media_end', delay_ms: 6000, media_timeout_ms: 120000 },
        defaults,
        capabilities,
      },
      global: { stubs: dialogStub },
    })

    expect(screen.getByLabelText('媒体等待上限（秒）')).toHaveValue('120')
    expect(screen.getByLabelText('无媒体时停留（秒）')).toHaveValue('6')
    expect(screen.getByText(/循环背景媒体不参与等待/)).toBeInTheDocument()

    await fireEvent.click(screen.getByRole('button', { name: '应用' }))

    expect(emitted('save')?.[0]?.[0]).toEqual({
      transition: null,
      advance: { mode: 'media_end', delay_ms: 6000, media_timeout_ms: 120000 },
    })
  })

  it('继承媒体结束时摘要应展示等待上限，并提供覆盖选项', () => {
    render(ProjectRouteSlideshowDialog, {
      props: {
        open: true,
        title: '放映设置',
        transition: null,
        advance: null,
        defaults: {
          ...defaults,
          advance: { mode: 'media_end', delay_ms: 5000, media_timeout_ms: 90000 },
        },
        capabilities,
      },
      global: { stubs: dialogStub },
    })

    expect(screen.getByText('未勾选时继承项目默认：媒体结束，无媒体时停留 5 秒，等待上限 90 秒。')).toBeInTheDocument()
  })

  it('能力未开放时不提供媒体结束选项，并对已有覆盖给出提示', () => {
    const timerOnlyCapabilities: SlideshowCapabilities = {
      ...capabilities,
      advance_modes: ['manual', 'timer'],
    }
    render(ProjectRouteSlideshowDialog, {
      props: {
        open: true,
        title: '放映设置',
        transition: null,
        advance: { mode: 'media_end', delay_ms: 6000, media_timeout_ms: 120000 },
        defaults,
        capabilities: timerOnlyCapabilities,
      },
      global: { stubs: dialogStub },
    })

    const select = screen.getByLabelText('翻页模式') as HTMLSelectElement
    expect(Array.from(select.options).map(option => option.value)).toEqual(['manual', 'timer'])
    expect(screen.getByText('当前服务端未开放媒体结束模式，请改用其它翻页方式后保存。')).toBeInTheDocument()
  })
})
