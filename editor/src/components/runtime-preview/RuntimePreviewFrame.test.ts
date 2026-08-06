/**
 * 文件功能：验证 Runtime 页面预览画布的状态遮罩、重试和 iframe 消息边界校验。
 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import RuntimePreviewFrame from '@/components/runtime-preview/RuntimePreviewFrame.vue'
import { PAGE_PREVIEW_READY_EVENT } from '@/types/runtime-preview'

describe('RuntimePreviewFrame', () => {
  it('慢加载与错误状态应覆盖旧 iframe 并允许重试', async () => {
    const { emitted, rerender } = render(RuntimePreviewFrame, {
      props: createProps('slow'),
    })

    expect(screen.getByTestId('page-preview-status-overlay')).toHaveTextContent('网络较慢，仍在加载')
    expect(document.querySelector('iframe')).not.toBeNull()

    await rerender(createProps('error', '页面预览加载超过 30 秒'))
    await fireEvent.click(screen.getByRole('button', { name: '重新生成预览' }))
    expect(emitted().retry).toHaveLength(1)
  })

  it('仅接受当前 iframe、origin、协议版本与 artifact 全部匹配的 ready', async () => {
    const { emitted } = render(RuntimePreviewFrame, {
      props: createProps('loading'),
    })
    const iframe = document.querySelector('iframe') as HTMLIFrameElement
    const validMessage = {
      type: PAGE_PREVIEW_READY_EVENT,
      payload: { version: 1, artifactId: 'artifact-page-1' },
    }

    dispatchPreviewMessage(validMessage, 'http://wrong.example', iframe.contentWindow)
    dispatchPreviewMessage({ ...validMessage, payload: { version: 2, artifactId: 'artifact-page-1' } }, 'http://runtime.example', iframe.contentWindow)
    dispatchPreviewMessage({ ...validMessage, payload: { version: 1, artifactId: 'old-artifact' } }, 'http://runtime.example', iframe.contentWindow)
    dispatchPreviewMessage(validMessage, 'http://runtime.example', window)
    expect(emitted().ready).toBeUndefined()

    dispatchPreviewMessage(validMessage, 'http://runtime.example', iframe.contentWindow)
    expect(emitted().ready).toHaveLength(1)
  })
})

/** 构造页面预览画布的完整测试入参。 */
function createProps(status: 'slow' | 'error' | 'loading', statusMessage = '') {
  return {
    frameUrl: 'http://runtime.example/preview?page=1',
    title: 'runtime-preview',
    artifactId: 'artifact-page-1',
    status,
    statusMessage,
  }
}

/** 派发带可控来源窗口与 origin 的 iframe 消息。 */
function dispatchPreviewMessage(data: unknown, origin: string, source: MessageEventSource | null): void {
  window.dispatchEvent(new MessageEvent('message', { data, origin, source }))
}
