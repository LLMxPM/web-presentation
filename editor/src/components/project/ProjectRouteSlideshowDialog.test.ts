/** 文件功能：验证路由放映设置弹窗的继承/覆盖提交与恢复继承行为。 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import ProjectRouteSlideshowDialog from './ProjectRouteSlideshowDialog.vue'
import type { SlideshowSettings } from '@/types/api'

const defaults: SlideshowSettings = {
  transition: { effect: 'fade', duration_ms: 400 },
  advance: { mode: 'manual', delay_ms: 5000 },
  loop: false,
  auto_start: false,
}

const dialogStub = {
  UiDialog: { template: '<div><slot /><slot name="footer" /></div>' },
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
})
