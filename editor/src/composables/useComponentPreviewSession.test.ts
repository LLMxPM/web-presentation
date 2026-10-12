/**
 * 文件功能：验证组件预览会话对 Runtime iframe ready/error 消息的状态同步。
 */
import { defineComponent, h, nextTick, onMounted } from 'vue'
import { render, screen, waitFor } from '@testing-library/vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useComponentPreviewSession } from '@/composables/useComponentPreviewSession'
import { COMPONENT_PREVIEW_ERROR_EVENT, COMPONENT_PREVIEW_READY_EVENT, buildInitialComponentPreviewState } from '@/types/component-preview'
import type { PreviewArtifactResponse } from '@/types/api'

describe('useComponentPreviewSession', () => {
  afterEach(() => vi.useRealTimers())

  it('组件 iframe 应在 8 秒进入慢加载、30 秒超时，并允许迟到 ready 恢复', async () => {
    vi.useFakeTimers()
    render(defineComponent({
      name: 'ComponentPreviewSessionTimeoutTestHost',
      setup() {
        const session = useComponentPreviewSession()
        onMounted(() => {
          void session.runPreview(() => Promise.resolve(createPreviewResponse()))
        })
        return () => h('div', [
          h('iframe', { ref: session.previewFrameRef }),
          h('span', { 'data-testid': 'status' }, session.previewStatus.value),
          h('span', { 'data-testid': 'error' }, session.previewErrorMessage.value),
        ])
      },
    }))
    await Promise.resolve()
    await nextTick()

    expect(screen.getByTestId('status')).toHaveTextContent('loading')
    vi.advanceTimersByTime(8000)
    await nextTick()
    expect(screen.getByTestId('status')).toHaveTextContent('slow')

    vi.advanceTimersByTime(22000)
    await nextTick()
    expect(screen.getByTestId('status')).toHaveTextContent('error')
    expect(screen.getByTestId('error')).toHaveTextContent('超过 30 秒')

    window.dispatchEvent(new MessageEvent('message', {
      origin: 'http://localhost',
      source: document.querySelector('iframe')?.contentWindow,
      data: {
        type: COMPONENT_PREVIEW_READY_EVENT,
        payload: {
          version: 1,
          artifactId: 'artifact-1',
          schema: null,
          defaultState: buildInitialComponentPreviewState(null),
          componentMeta: { code: 'demo', displayName: 'Demo' },
        },
      },
    }))
    await nextTick()

    expect(screen.getByTestId('status')).toHaveTextContent('ready')
    expect(screen.getByTestId('error').textContent).toBe('')
  })

  it('收到 Runtime 错误事件后应结束 loading 并记录错误信息', async () => {
    render(defineComponent({
      name: 'ComponentPreviewSessionErrorTestHost',
      setup() {
        const session = useComponentPreviewSession()
        onMounted(() => {
          void session.runPreview(() => Promise.resolve(createPreviewResponse()))
        })

        return () => h('div', [
          h('iframe', { ref: session.previewFrameRef }),
          h('span', { 'data-testid': 'loading' }, session.previewLoading.value ? 'loading' : 'idle'),
          h('span', { 'data-testid': 'error' }, session.previewErrorMessage.value),
        ])
      },
    }))

    await waitFor(() => {
      expect(screen.getByTestId('loading')).toHaveTextContent('loading')
    })

    window.dispatchEvent(new MessageEvent('message', {
      origin: 'http://localhost',
      source: document.querySelector('iframe')?.contentWindow,
      data: {
        type: COMPONENT_PREVIEW_ERROR_EVENT,
        payload: {
          version: 1,
          artifactId: 'artifact-1',
          message: 'Element is missing end tag.',
        },
      },
    }))

    await waitFor(() => {
      expect(screen.getByTestId('loading')).toHaveTextContent('idle')
      expect(screen.getByTestId('error')).toHaveTextContent('Element is missing end tag.')
    })
  })

  it('旧预览请求慢返回时不应覆盖最新草稿预览地址', async () => {
    const firstPreview = createDeferred<PreviewArtifactResponse>()
    const latestPreview = createDeferred<PreviewArtifactResponse>()

    render(defineComponent({
      name: 'ComponentPreviewSessionRaceTestHost',
      setup() {
        const session = useComponentPreviewSession()
        onMounted(() => {
          void session.runPreview(() => firstPreview.promise)
          void session.runPreview(() => latestPreview.promise)
        })

        return () => h('span', { 'data-testid': 'frame-url' }, session.previewFrameUrl.value)
      },
    }))

    latestPreview.resolve(createPreviewResponse('artifact-latest', 'http://localhost/preview/latest'))

    await waitFor(() => {
      expect(screen.getByTestId('frame-url')).toHaveTextContent('http://localhost/preview/latest')
    })

    firstPreview.resolve(createPreviewResponse('artifact-old', 'http://localhost/preview/old'))

    await waitFor(() => {
      expect(screen.getByTestId('frame-url')).toHaveTextContent('http://localhost/preview/latest')
    })
  })

  it('旧预览请求失败时不应覆盖最新草稿预览状态', async () => {
    const firstPreview = createDeferred<PreviewArtifactResponse>()
    const latestPreview = createDeferred<PreviewArtifactResponse>()

    render(defineComponent({
      name: 'ComponentPreviewSessionStaleErrorTestHost',
      setup() {
        const session = useComponentPreviewSession()
        onMounted(() => {
          void session.runPreview(() => firstPreview.promise)
          void session.runPreview(() => latestPreview.promise)
        })

        return () => h('div', [
          h('span', { 'data-testid': 'frame-url' }, session.previewFrameUrl.value),
          h('span', { 'data-testid': 'error' }, session.previewErrorMessage.value),
        ])
      },
    }))

    latestPreview.resolve(createPreviewResponse('artifact-latest', 'http://localhost/preview/latest'))

    await waitFor(() => {
      expect(screen.getByTestId('frame-url')).toHaveTextContent('http://localhost/preview/latest')
    })

    firstPreview.reject(new Error('old preview failed'))

    await waitFor(() => {
      expect(screen.getByTestId('frame-url')).toHaveTextContent('http://localhost/preview/latest')
      expect(screen.getByTestId('error').textContent).toBe('')
    })
  })

  it('失效恢复复用原 loader，忽略其它窗口，并在新 artifact 再失败时停止自动重试', async () => {
    let session!: ReturnType<typeof useComponentPreviewSession>
    let calls = 0
    const loader = vi.fn(async () => createPreviewResponse(`artifact-${++calls}`))
    render(defineComponent({
      setup() {
        session = useComponentPreviewSession()
        onMounted(() => { void session.runPreview(loader) })
        return () => h('iframe', { ref: session.previewFrameRef })
      },
    }))
    await waitFor(() => expect(session.previewArtifactId.value).toBe('artifact-1'))
    const frame = document.querySelector('iframe') as HTMLIFrameElement
    const dispatchError = (artifactId: string, source: MessageEventSource | null = frame.contentWindow) => {
      window.dispatchEvent(new MessageEvent('message', {
        origin: 'http://localhost', source,
        data: { type: COMPONENT_PREVIEW_ERROR_EVENT, payload: {
          version: 1, artifactId, code: 'PREVIEW_CONTEXT_INVALID', message: '预览链接已失效',
        } },
      }))
    }
    dispatchError('artifact-1', window)
    await nextTick()
    expect(loader).toHaveBeenCalledTimes(1)
    dispatchError('artifact-1')
    await waitFor(() => expect(session.previewArtifactId.value).toBe('artifact-2'))
    dispatchError('artifact-2')
    await nextTick()
    expect(loader).toHaveBeenCalledTimes(2)
    expect(session.previewStatus.value).toBe('error')
    expect(session.previewErrorMessage.value).toBe('预览链接已失效')
  })
})

function createPreviewResponse(
  artifactId = 'artifact-1',
  previewUrl = 'http://localhost/preview/component',
): PreviewArtifactResponse {
  return {
    preview_url: previewUrl,
    artifact_id: artifactId,
    preview_kind: 'component',
    entry_descriptor: {
      entry_type: 'component_host',
    },
    viewport_width: 1920,
    viewport_height: 1080,
  }
}

function createDeferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}
