/**
 * 文件功能：验证 Runtime 页面预览画布的状态遮罩、重试和 iframe 消息边界校验。
 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import RuntimePreviewFrame from '@/components/runtime-preview/RuntimePreviewFrame.vue'
import { PAGE_PREVIEW_ERROR_EVENT, PAGE_PREVIEW_READY_EVENT, PREVIEW_MOTION_STATE_TYPE } from '@/types/runtime-preview'

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
    expect(iframe).toHaveAttribute('referrerpolicy', 'origin')
    expect(iframe).toHaveAttribute('allow', 'autoplay; fullscreen')
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

  it('失效错误立即透传 code 并只自动重建一次，新 artifact 失败保留手动重试', async () => {
    const { emitted, rerender } = render(RuntimePreviewFrame, {
      props: { ...createProps('loading'), status: 'idle', autoRecover: true },
    })
    const iframe = document.querySelector('iframe') as HTMLIFrameElement
    const error = {
      type: PAGE_PREVIEW_ERROR_EVENT,
      payload: { version: 1, artifactId: 'artifact-page-1', code: 'PREVIEW_CONTEXT_INVALID', message: '预览链接已失效' },
    }
    dispatchPreviewMessage(error, 'http://wrong.example', iframe.contentWindow)
    dispatchPreviewMessage(error, 'http://runtime.example', window)
    expect(emitted().error).toBeUndefined()
    dispatchPreviewMessage(error, 'http://runtime.example', iframe.contentWindow)
    await Promise.resolve()
    expect(emitted().error).toEqual([['预览链接已失效', 'PREVIEW_CONTEXT_INVALID']])
    expect(emitted().retry).toHaveLength(1)
    await rerender({ ...createProps('loading'), status: 'idle', autoRecover: true, artifactId: 'artifact-new', frameUrl: 'http://runtime.example/preview/new' })
    dispatchPreviewMessage({ ...error, payload: { ...error.payload, artifactId: 'artifact-new' } }, 'http://runtime.example', iframe.contentWindow)
    await Promise.resolve()
    expect(emitted().retry).toHaveLength(1)
    await fireEvent.click(screen.getByRole('button', { name: '重新生成预览' }))
    expect(emitted().retry).toHaveLength(2)
  })

  it('仅接受当前 iframe 与 origin 的时间轴状态并透传', async () => {
    const { emitted } = render(RuntimePreviewFrame, {
      props: createProps('loading'),
    })
    const iframe = document.querySelector('iframe') as HTMLIFrameElement
    const state = {
      hasTimeline: true,
      timelineId: 'intro',
      planDigest: 'plan-1',
      intent: 'playing',
      phase: 'ready',
      positionMs: 640,
      durationMs: 1200,
      posterTimeMs: 250,
      visualMode: 'reduced',
      revision: 3,
      errorCode: null,
      errorMessage: '',
    }
    const message = { type: PREVIEW_MOTION_STATE_TYPE, version: 1, state }

    dispatchPreviewMessage(message, 'http://wrong.example', iframe.contentWindow)
    dispatchPreviewMessage(message, 'http://runtime.example', window)
    dispatchPreviewMessage({ ...message, version: 2 }, 'http://runtime.example', iframe.contentWindow)
    dispatchPreviewMessage({ ...message, state: { hasTimeline: true } }, 'http://runtime.example', iframe.contentWindow)
    expect(emitted()['motion-state']).toBeUndefined()

    dispatchPreviewMessage(message, 'http://runtime.example', iframe.contentWindow)
    expect(emitted()['motion-state']).toEqual([[state]])
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
