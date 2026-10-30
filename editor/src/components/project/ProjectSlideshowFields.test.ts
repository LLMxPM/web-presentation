/** 文件功能：验证新放映表单只展示当前模式的停留字段、能力提示与循环事件。 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { expect, it } from 'vitest'
import ProjectSlideshowFields from './ProjectSlideshowFields.vue'
import { createSlideshowDraft, type SlideshowDraft } from './project-slideshow-values'
import { sceneCapabilities, slideshowFormStubs } from '@/test/slideshow-helpers'

it('定时模式不展示旧预算与自动开始，有限完成模式只编辑结束停留', async () => {
  const draft = { ...createSlideshowDraft(), advanceMode: 'timer' as const }
  const { rerender, emitted } = render(ProjectSlideshowFields, { props: { draft, capabilities: sceneCapabilities }, global: { stubs: slideshowFormStubs } })
  expect(screen.getByLabelText('停留时长（秒）')).toHaveValue('5')
  expect(screen.queryByText('自动开始')).toBeNull(); expect(screen.queryByLabelText('媒体等待上限（秒）')).toBeNull()
  await fireEvent.update(screen.getByLabelText('翻页模式'), 'scene_end')
  const changed = (emitted('update:draft') as SlideshowDraft[][]).at(-1)![0]
  await rerender({ draft: changed, capabilities: sceneCapabilities })
  expect(screen.queryByLabelText('停留时长（秒）')).toBeNull()
  expect(screen.getByLabelText('完成后停留（秒）')).toHaveValue('0.3')
  expect(screen.getByText(/没有完成目标时会提示配置错误/)).toBeInTheDocument()
})

it('循环回传完整草稿，none 禁用动画时长；旧服务不显示 Scene 选项', async () => {
  const draft = { ...createSlideshowDraft(), effect: 'none' as const, durationSeconds: '0', advanceMode: 'scene_end' as const }
  const { emitted } = render(ProjectSlideshowFields, { props: { draft, capabilities: { ...sceneCapabilities, schema_version: 3 } }, global: { stubs: slideshowFormStubs } })
  expect(screen.getByLabelText('动画时长（秒）')).toBeDisabled()
  expect(screen.getByRole('status')).toHaveTextContent('服务版本')
  expect([...((screen.getByLabelText('翻页模式')) as HTMLSelectElement).options].map(item => item.value)).toEqual(['manual', 'timer'])
  await fireEvent.click(screen.getByLabelText('到达末页后循环放映'))
  expect((emitted('update:draft') as SlideshowDraft[][]).at(-1)![0]).toEqual({ ...draft, loop: true })
})
