/**
 * 文件功能：验证 Runtime 资源预览创建与背景模式查询参数传递。
 */
import { defineComponent, h } from 'vue'
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AssetPreviewFrame from './AssetPreviewFrame.vue'

const { createAssetPreviewArtifactMock } = vi.hoisted(() => ({
  createAssetPreviewArtifactMock: vi.fn(),
}))

vi.mock('@/api/preview', () => ({
  createAssetPreviewArtifact: (...args: unknown[]) => createAssetPreviewArtifactMock(...args),
}))

describe('AssetPreviewFrame', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    createAssetPreviewArtifactMock.mockResolvedValue({
      preview_url: 'http://localhost:4173/__asset-preview?artifact_id=artifact-1',
    })
  })

  it('应复用预览 artifact，并通过 iframe 查询参数切换背景', async () => {
    render(AssetPreviewFrame, {
      props: {
        workspaceId: 7,
        asset: {
          id: 3,
          name: 'white_logo',
          file_hash: 'hash-white-logo',
        },
      },
      global: {
        stubs: {
          RuntimePreviewFrame: defineComponent({
            name: 'RuntimePreviewFrame',
            props: {
              frameUrl: String,
            },
            setup(props) {
              return () => h('div', {
                'data-testid': 'runtime-preview-frame',
                'data-frame-url': props.frameUrl,
              })
            },
          }),
        },
      },
    })

    await waitFor(() => {
      expect(createAssetPreviewArtifactMock).toHaveBeenCalledTimes(1)
      expect(screen.getByTestId('runtime-preview-frame').getAttribute('data-frame-url')).toContain('preview_background=checker')
    })

    await fireEvent.click(screen.getByRole('radio', { name: '深色' }))
    expect(screen.getByTestId('runtime-preview-frame').getAttribute('data-frame-url')).toContain('preview_background=dark')
    expect(createAssetPreviewArtifactMock).toHaveBeenCalledTimes(1)
  })
})
