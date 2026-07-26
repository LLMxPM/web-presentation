/**
 * 文件功能：验证全局确认宿主在普通页面与嵌套模态中可交互，并正确管理焦点和请求队列。
 */
import { defineComponent, nextTick, ref } from 'vue'
import { fireEvent, render, screen } from '@testing-library/vue'
import { afterEach, describe, expect, it } from 'vitest'

import UiButton from '@/components/ui/button/UiButton.vue'
import UiConfirmHost from '@/components/ui/dialog/UiConfirmHost.vue'
import UiDialog from '@/components/ui/dialog/UiDialog.vue'
import { cancelAllConfirmRequests } from '@/utils/confirm'
import { createConfirm } from '@/utils/message'

afterEach(() => {
  cancelAllConfirmRequests()
  document.body.innerHTML = ''
})

describe('UiConfirmHost', () => {
  it('应允许操作嵌套在外层 UiDialog 上方的确认框，并在关闭后恢复焦点', async () => {
    renderConfirmHarness()

    await fireEvent.click(screen.getByRole('button', { name: '打开外层弹窗' }))
    const trigger = screen.getByRole('button', { name: '请求删除' })
    trigger.focus()
    await fireEvent.click(trigger)
    await nextTick()

    expect(screen.getByText('删除后无法恢复。')).toBeInTheDocument()
    expect(document.body.querySelectorAll('.dialog-shell')).toHaveLength(2)

    await fireEvent.click(screen.getByRole('button', { name: '取消' }))
    await nextTick()
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(screen.queryByText('删除后无法恢复。')).not.toBeInTheDocument()
    expect(screen.getByText('外层内容')).toBeInTheDocument()
    expect(trigger).toHaveFocus()
    expect(screen.getByTestId('confirm-result')).toHaveTextContent('false')
  })

  it('Esc 应只取消顶部确认框并保留外层弹窗', async () => {
    renderConfirmHarness()

    await fireEvent.click(screen.getByRole('button', { name: '打开外层弹窗' }))
    await fireEvent.click(screen.getByRole('button', { name: '请求删除' }))
    await nextTick()
    await fireEvent.keyDown(window, { key: 'Escape' })
    await nextTick()

    expect(screen.queryByText('删除后无法恢复。')).not.toBeInTheDocument()
    expect(screen.getByText('外层内容')).toBeInTheDocument()
    expect(screen.getByTestId('confirm-result')).toHaveTextContent('false')
  })

  it('并发请求应按触发顺序展示并分别结算 Promise', async () => {
    render(UiConfirmHost)

    const firstResult = createConfirm('第一个请求', '确认一')
    const secondResult = createConfirm('第二个请求', '确认二')
    await nextTick()

    expect(screen.getByText('第一个请求')).toBeInTheDocument()
    expect(screen.queryByText('第二个请求')).not.toBeInTheDocument()

    await fireEvent.click(screen.getByRole('button', { name: '确定' }))
    expect(await firstResult).toBe(true)
    await nextTick()

    expect(screen.getByText('第二个请求')).toBeInTheDocument()
    await fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(await secondResult).toBe(false)
  })
})

/**
 * 构建外层模态和全局确认宿主共存的受控场景。
 */
function renderConfirmHarness() {
  const Harness = defineComponent({
    components: { UiButton, UiConfirmHost, UiDialog },
    template: `
      <button type="button" @click="outerOpen = true">打开外层弹窗</button>
      <output data-testid="confirm-result">{{ String(confirmResult) }}</output>
      <UiDialog :open="outerOpen" title="外层弹窗" @update:open="outerOpen = $event">
        <p>外层内容</p>
        <UiButton variant="danger" @click="requestDelete">请求删除</UiButton>
      </UiDialog>
      <UiConfirmHost />
    `,
    setup() {
      const outerOpen = ref(false)
      const confirmResult = ref<boolean | null>(null)

      /**
       * 从外层模态触发危险确认，并记录异步结果供断言。
       */
      async function requestDelete(): Promise<void> {
        confirmResult.value = await createConfirm(
          '删除后无法恢复。',
          '删除项目',
          { dangerous: true },
        )
      }

      return { confirmResult, outerOpen, requestDelete }
    },
  })

  return render(Harness)
}
