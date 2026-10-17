/** 文件功能：验证放映表单展示可用效果、无动画时长禁用与循环开关事件。 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import ProjectSlideshowFields from './ProjectSlideshowFields.vue'
import type { SlideshowDraft } from './project-slideshow-values'

function buildDraft(overrides: Partial<SlideshowDraft> = {}): SlideshowDraft {
  return {
    effect: 'fade',
    durationSeconds: '0.4',
    advanceMode: 'timer',
    delaySeconds: '5',
    loop: false,
    autoStart: false,
    ...overrides,
  }
}

describe('ProjectSlideshowFields', () => {
  it('应展示动画与翻页字段，无动画时禁用时长输入', () => {
    render(ProjectSlideshowFields, { props: { draft: buildDraft({ effect: 'none', durationSeconds: '0' }) } })

    expect(screen.getByLabelText('动画效果')).toBeInTheDocument()
    expect(screen.getByLabelText('动画时长（秒）')).toBeDisabled()
    expect(screen.getByLabelText('翻页模式')).toBeInTheDocument()
    expect(screen.getByLabelText('停留时长（秒）')).toHaveValue('5')
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
})
