/** 文件功能：验证路由分组继承、覆盖初始化及完成后零停留提交。 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { expect, it } from 'vitest'
import ProjectRouteSlideshowForm from './ProjectRouteSlideshowForm.vue'
import { DEFAULT_SLIDESHOW_SETTINGS } from './project-slideshow-values'
import { sceneCapabilities, slideshowFormStubs } from '@/test/slideshow-helpers'

it('动画覆盖以项目默认初始化，取消明确提交 null 而不修改翻页组', async () => {
  const { emitted } = render(ProjectRouteSlideshowForm, { props: { defaults: DEFAULT_SLIDESHOW_SETTINGS, transition: null, advance: null }, global: { stubs: slideshowFormStubs } })
  await fireEvent.click(screen.getByLabelText('覆盖翻页动画'))
  expect(emitted('update:transition')!.at(-1)![0]).toEqual({ effect: 'fade', duration_ms: 400 })
  await fireEvent.click(screen.getByLabelText('覆盖翻页动画'))
  expect(emitted('update:transition')!.at(-1)![0]).toBeNull(); expect(emitted('update:advance')).toBeUndefined()
})

it('实际完成模式编辑完成后停留，零值不会被回退成默认值', async () => {
  const { emitted } = render(ProjectRouteSlideshowForm, { props: { defaults: DEFAULT_SLIDESHOW_SETTINGS, transition: null, advance: { mode: 'scene_end', delay_ms: 5000, completion_delay_ms: 450 }, capabilities: sceneCapabilities }, global: { stubs: slideshowFormStubs } })
  await fireEvent.update(screen.getByLabelText('完成后停留（秒）'), '0')
  await fireEvent.blur(screen.getByLabelText('完成后停留（秒）'))
  expect(emitted('update:advance')!.at(-1)![0]).toEqual({ mode: 'scene_end', delay_ms: 5000, completion_delay_ms: 0 })
  expect(emitted('update:transition')).toBeUndefined()
})
