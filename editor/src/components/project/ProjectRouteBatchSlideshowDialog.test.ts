/** 文件功能：验证批量放映处理的保持/继承/覆盖原子语义与当前 DTO 完整值。 */
import { fireEvent, render, screen, within } from '@testing-library/vue'
import { expect, it } from 'vitest'
import ProjectRouteBatchSlideshowDialog from './ProjectRouteBatchSlideshowDialog.vue'
import { DEFAULT_SLIDESHOW_SETTINGS } from './project-slideshow-values'
import { sceneCapabilities, slideshowFormStubs } from '@/test/slideshow-helpers'

/** 每例挂载相同真实组合组件，只替换底层 UI 交互原语。 */
function mount() { return render(ProjectRouteBatchSlideshowDialog, { props: { open: true, pageCount: 3, itemCount: 4, defaults: DEFAULT_SLIDESHOW_SETTINGS, capabilities: sceneCapabilities }, global: { stubs: slideshowFormStubs } }) }

it('保持原样时不可应用，单组继承不带另一组字段', async () => {
  const { emitted } = mount()
  expect(screen.getByRole('button', { name: '应用到选中页面' })).toBeDisabled()
  await fireEvent.click(within(screen.getAllByRole('group')[0]).getByRole('button', { name: '恢复继承' }))
  await fireEvent.click(screen.getByRole('button', { name: '应用到选中页面' }))
  expect(emitted('apply')!.at(-1)![0]).toEqual({ transition: null })
})

it('覆盖翻页可选择实际完成和零停留，应用时提交完整且无旧字段', async () => {
  const { emitted } = mount()
  await fireEvent.click(within(screen.getAllByRole('group')[1]).getByRole('button', { name: '设置覆盖' }))
  await fireEvent.update(screen.getByLabelText('翻页模式'), 'scene_end')
  await fireEvent.update(screen.getByLabelText('完成后停留（秒）'), '0')
  await fireEvent.click(screen.getByRole('button', { name: '应用到选中页面' }))
  expect(emitted('apply')!.at(-1)![0]).toEqual({ advance: { mode: 'scene_end', delay_ms: 5000, completion_delay_ms: 0 } })
  expect(emitted('update:open')!.at(-1)![0]).toBe(false)
})
