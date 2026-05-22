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
})

function createPreviewResponse(): PreviewArtifactResponse {
  return {
    preview_url: 'http://localhost/preview/component',
    artifact_id: 'artifact-1',
    preview_kind: 'component',
    entry_descriptor: {
      entry_type: 'component_host',
    },
    viewport_width: 1920,
    viewport_height: 1080,
  }
}
