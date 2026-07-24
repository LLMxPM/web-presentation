/**
 * 文件功能：验证组件预览弹窗已收口到统一 UiDialog 规格，并保留关闭与焦点行为。
 */
import { defineComponent, nextTick, ref } from 'vue'
import { fireEvent, render, screen } from '@testing-library/vue'
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

  it('按 Esc 应关闭弹窗并将焦点还给打开按钮', async () => {
    const DialogHarness = defineComponent({
      components: { ComponentPreviewDialog },
      template: `
        <button type="button" data-testid="preview-trigger" @click="open = true">打开预览</button>
        <ComponentPreviewDialog v-model="open"><div>预览内容</div></ComponentPreviewDialog>
      `,
      setup() {
        return { open: ref(false) }
      },
    })
    render(DialogHarness)

    const trigger = screen.getByTestId('preview-trigger')
    trigger.focus()
    await fireEvent.click(trigger)
    await nextTick()

    await fireEvent.keyDown(window, { key: 'Escape' })
    await nextTick()
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(trigger).toHaveFocus()
    expect(document.body.querySelector('[data-dialog-size="workbench"]')).not.toBeInTheDocument()
  })
})
