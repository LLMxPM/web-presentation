/**
 * 文件功能：验证组件预览会话对 Runtime iframe ready/error 消息的状态同步。
 */
import { defineComponent, h, onMounted } from 'vue'
import { render, screen, waitFor } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import { useComponentPreviewSession } from '@/composables/useComponentPreviewSession'
import { COMPONENT_PREVIEW_ERROR_EVENT } from '@/types/component-preview'
import type { PreviewArtifactResponse } from '@/types/api'

describe('useComponentPreviewSession', () => {
  it('收到 Runtime 错误事件后应结束 loading 并记录错误信息', async () => {
    render(defineComponent({
      name: 'ComponentPreviewSessionErrorTestHost',
      setup() {
        const session = useComponentPreviewSession()
        onMounted(() => {
          void session.runPreview(() => Promise.resolve(createPreviewResponse()))
        })

        return () => h('div', [
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
