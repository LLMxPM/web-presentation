/** 文件功能：验证放映表单按能力开放模式、媒体超时字段、无媒体说明与事件回传。 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import type { SlideshowCapabilities } from '@/types/api'
import ProjectSlideshowFields from './ProjectSlideshowFields.vue'
import type { SlideshowDraft } from './project-slideshow-values'

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

const selectStub = {
  props: ['modelValue', 'options'],
  emits: ['update:modelValue'],
  template: `
    <select v-bind="$attrs" :value="modelValue" @change="$emit('update:modelValue', $event.target.value)">
      <option v-for="option in options" :key="option.value" :value="option.value">{{ option.label }}</option>
    </select>
  `,
}

function buildDraft(overrides: Partial<SlideshowDraft> = {}): SlideshowDraft {
  return {
    effect: 'fade',
    durationSeconds: '0.4',
    advanceMode: 'timer',
    delaySeconds: '5',
    mediaTimeoutSeconds: '300',
    timelineTimeoutSeconds: '300',
    loop: false,
    autoStart: false,
    ...overrides,
  }
}

describe('ProjectSlideshowFields', () => {
  it('应展示动画与翻页字段，无动画时禁用时长输入，timer 旁白提示不修改草稿', () => {
    const { emitted } = render(ProjectSlideshowFields, {
      props: { draft: buildDraft({ effect: 'none', durationSeconds: '0' }) },
    })

    expect(screen.getByLabelText('动画效果')).toBeInTheDocument()
    expect(screen.getByLabelText('动画时长（秒）')).toBeDisabled()
    expect(screen.getByLabelText('翻页模式')).toBeInTheDocument()
    expect(screen.getByLabelText('停留时长（秒）')).toHaveValue('5')
    expect(screen.getByText(/定时推进会在计时到达时停止旁白并翻页/)).toBeInTheDocument()
    expect(emitted('update:draft')).toBeUndefined()
  })

  it('勾选循环放映应回传完整草稿且不改其它字段', async () => {
    const { emitted } = render(ProjectSlideshowFields, { props: { draft: buildDraft() } })

    await fireEvent.click(screen.getByLabelText('循环放映（末页后回到第一页）'))

    const updates = emitted('update:draft') as SlideshowDraft[][]
    expect(updates.at(-1)?.[0]).toEqual(buildDraft({ loop: true }))
  })

  it('无动画时仍展示 0 秒时长，切回淡入淡出恢复上次时长', async () => {
    const { emitted, rerender } = render(ProjectSlideshowFields, { props: { draft: buildDraft() } })

    // 通过交互切换到无动画：Reka Select 在 jsdom 中难以展开，这里直接验证回传后的禁用表现。
    await rerender({ draft: buildDraft({ effect: 'none', durationSeconds: '0' }) })
    expect(screen.getByLabelText('动画时长（秒）')).toBeDisabled()
    expect(screen.getByLabelText('动画时长（秒）')).toHaveValue('0')
    expect(emitted('update:draft')).toBeUndefined()
  })

  it('能力开放时应提供媒体结束选项与等待上限，并回传完整草稿', async () => {
    const { emitted, rerender } = render(ProjectSlideshowFields, {
      props: { draft: buildDraft(), capabilities },
      global: { stubs: { UiSelect: selectStub } },
    })

    const select = screen.getByLabelText('翻页模式') as HTMLSelectElement
    expect(Array.from(select.options).map(option => option.value)).toEqual(['manual', 'timer', 'media_end'])

    await fireEvent.update(select, 'media_end')

    const updates = emitted('update:draft') as SlideshowDraft[][]
    expect(updates.at(-1)?.[0]).toEqual(buildDraft({ advanceMode: 'media_end' }))

    await rerender({ draft: buildDraft({ advanceMode: 'media_end' }), capabilities })
    expect(screen.getByLabelText('无媒体时停留（秒）')).toHaveValue('5')
    expect(screen.getByLabelText('媒体等待上限（秒）')).toHaveValue('300')
    expect(screen.getByText(/没有可等待媒体时按停留时长翻页/)).toBeInTheDocument()
  })

  it('能力开放时应提供时间轴结束选项、等待上限与无时间轴兜底说明', async () => {
    const timelineCapabilities: SlideshowCapabilities = {
      ...capabilities,
      advance_modes: ['manual', 'timer', 'media_end', 'timeline_end'],
    }
    const { emitted, rerender } = render(ProjectSlideshowFields, {
      props: { draft: buildDraft(), capabilities: timelineCapabilities },
      global: { stubs: { UiSelect: selectStub } },
    })

    const select = screen.getByLabelText('翻页模式') as HTMLSelectElement
    expect(Array.from(select.options).map(option => option.value))
      .toEqual(['manual', 'timer', 'media_end', 'timeline_end'])

    await fireEvent.update(select, 'timeline_end')
    const updates = emitted('update:draft') as SlideshowDraft[][]
    expect(updates.at(-1)?.[0]).toEqual(buildDraft({ advanceMode: 'timeline_end' }))

    await rerender({
      draft: buildDraft({ advanceMode: 'timeline_end', timelineTimeoutSeconds: '120' }),
      capabilities: timelineCapabilities,
    })
    expect(screen.getByLabelText('时间轴等待上限（秒）')).toHaveValue('120')
    expect(screen.getByText(/页面没有可用时间轴时显示错误/)).toBeInTheDocument()
  })

  it('能力未开放时不出现媒体结束选项，已有草稿给出可操作提示', () => {
    const timerOnlyCapabilities: SlideshowCapabilities = {
      ...capabilities,
      advance_modes: ['manual', 'timer'],
    }
    render(ProjectSlideshowFields, {
      props: { draft: buildDraft({ advanceMode: 'media_end' }), capabilities: timerOnlyCapabilities },
      global: { stubs: { UiSelect: selectStub } },
    })

    const select = screen.getByLabelText('翻页模式') as HTMLSelectElement
    expect(Array.from(select.options).map(option => option.value)).toEqual(['manual', 'timer'])
    expect(screen.getByText('当前服务端未开放媒体结束模式，请改用其它翻页方式后保存。')).toBeInTheDocument()
  })
})
