/**
 * 文件功能：验证组件预览弹窗已收口到统一 BaseDialog 规格。
 */
import { fireEvent, render } from '@testing-library/vue'
import { afterEach, describe, expect, it } from 'vitest'

import ComponentPreviewDialog from './ComponentPreviewDialog.vue'

afterEach(() => {
  document.body.innerHTML = ''
})

describe('ComponentPreviewDialog', () => {
  it('应默认使用工作台级尺寸和沉浸式 body preset', () => {
    render(ComponentPreviewDialog, {
      props: {
        modelValue: true,
      },
      slots: {
        default: '<div>预览内容</div>',
      },
    })

    const shell = document.body.querySelector('[data-dialog-size="workbench"]')
    expect(shell).toHaveAttribute('data-dialog-body-preset', 'immersive')
  })

  it('显示关闭按钮时应能关闭弹窗', async () => {
    const view = render(ComponentPreviewDialog, {
      props: {
        modelValue: true,
        showCloseButton: true,
        closeLabel: '关闭组件预览',
      },
      slots: {
        default: '<div>预览内容</div>',
      },
    })

    const closeButton = document.body.querySelector('.dialog-panel .absolute.right-3')
    expect(closeButton).toBeInstanceOf(HTMLButtonElement)
    await fireEvent.click(closeButton as HTMLButtonElement)
    expect(view.emitted()['update:modelValue']).toEqual([[false]])
  })
})
