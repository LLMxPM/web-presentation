/** 文件功能：验证复杂 UI Primitive 的可访问状态与基础交互契约。 */
import { defineComponent, nextTick, ref } from 'vue'
import { fireEvent, render, screen } from '@testing-library/vue'
import { afterEach, describe, expect, it } from 'vitest'

import UiCheckbox from './checkbox/UiCheckbox.vue'
import UiDialog from './dialog/UiDialog.vue'
import UiRadioGroup from './radio/UiRadioGroup.vue'
import UiSegmentedControl from './segmented/UiSegmentedControl.vue'
import UiTabs from './tabs/UiTabs.vue'

afterEach(() => {
  document.body.innerHTML = ''
})

describe('UiDialog', () => {
  it('遮罩点击和 Esc 应请求关闭受控弹窗', async () => {
    const view = render(UiDialog, { props: { open: true, title: '编辑信息' }, slots: { default: '内容' } })

    await fireEvent.click(screen.getByRole('button', { name: '关闭编辑信息' }))
    expect(view.emitted()['update:open']).toEqual([[false]])

    await fireEvent.keyDown(window, { key: 'Escape' })
    expect(view.emitted()['update:open']).toContainEqual([false])
  })

  it('打开时应圈定焦点，关闭后恢复到原触发元素', async () => {
    const DialogHarness = defineComponent({
      components: { UiDialog },
      template: `
        <button type="button" data-testid="dialog-trigger" @click="open = true">打开</button>
        <UiDialog :open="open" title="焦点测试" @update:open="open = $event">内容</UiDialog>
      `,
      setup() {
        return { open: ref(false) }
      },
    })
    render(DialogHarness)

    const trigger = screen.getByTestId('dialog-trigger')
    trigger.focus()
    await fireEvent.click(trigger)
    await nextTick()

    expect(screen.getByRole('button', { name: '关闭焦点测试' })).toHaveFocus()

    await fireEvent.click(screen.getByRole('button', { name: '关闭焦点测试' }))
    await nextTick()
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(trigger).toHaveFocus()
  })

  it('workbench 面板应使用壳层间距限制视口尺寸', () => {
    render(UiDialog, { props: { open: true, size: 'workbench' }, slots: { default: '内容' } })

    const shell = document.body.querySelector('.dialog-shell')
    const panel = document.body.querySelector('.dialog-panel')

    expect(shell).toHaveAttribute('data-dialog-size', 'workbench')
    expect(panel).toHaveStyle({
      width: 'min(1520px, calc(100dvw - (var(--dialog-shell-gap) * 2)))',
      height: 'min(calc(100dvh - (var(--dialog-shell-gap) * 2)), calc(100dvh - (var(--dialog-shell-gap) * 2)))',
    })
  })
})

describe('UiCheckbox', () => {
  it('应回传复选和半选状态', async () => {
    const view = render(UiCheckbox, { props: { modelValue: false } })
    await fireEvent.click(screen.getByRole('checkbox'))
    expect(view.emitted()['update:modelValue']).toEqual([[true]])
  })
})

describe('UiRadioGroup', () => {
  it('应使用 radio 语义并回传用户通过键盘选中的值', async () => {
    const view = render(UiRadioGroup, {
      props: {
        modelValue: 'draft',
        options: [{ label: '草稿', value: 'draft' }, { label: '已发布', value: 'published' }],
      },
      attrs: { 'aria-label': '发布状态' },
    })

    const draft = screen.getByRole('radio', { name: '草稿' })
    draft.focus()
    await new Promise(resolve => setTimeout(resolve, 0))
    await fireEvent.keyDown(draft, { key: 'ArrowDown' })
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(view.emitted()['update:modelValue']).toEqual([['published']])
    expect(screen.getByRole('radiogroup', { name: '发布状态' })).toBeTruthy()
  })
})

describe('UiSegmentedControl', () => {
  it('应使用 radio 语义、支持禁用选项并回传新分段值', async () => {
    const view = render(UiSegmentedControl, {
      props: {
        modelValue: 'all',
        options: [{ label: '全部', value: 'all' }, { label: '图片', value: 'image' }, { label: '文件', value: 'file', disabled: true }],
      },
      attrs: { 'aria-label': '资源范围' },
    })

    await fireEvent.click(screen.getByRole('radio', { name: '图片' }))

    expect(view.emitted()['update:modelValue']).toEqual([['image']])
    expect(screen.getByRole('radio', { name: '文件' })).toHaveAttribute('data-disabled')
  })
})

describe('UiTabs', () => {
  it('应由键盘与点击行为更新激活标签', async () => {
    const view = render(UiTabs, {
      props: { modelValue: 'basic', items: [{ label: '基础', value: 'basic' }, { label: '高级', value: 'advanced' }] },
      slots: { basic: '基础内容', advanced: '高级内容' },
    })

    await fireEvent.mouseDown(screen.getByRole('tab', { name: '高级' }), { button: 0 })
    expect(view.emitted()['update:modelValue']).toEqual([['advanced']])
  })
})
