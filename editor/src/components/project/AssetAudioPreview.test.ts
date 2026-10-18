/**
 * 文件功能：验证音频资源试听组件不会自动播放，并在切换资源或卸载时停止播放。
 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AssetAudioPreview from '@/components/project/AssetAudioPreview.vue'
import type { AssetResponse } from '@/types/api'

const pauseMock = vi.fn()

describe('AssetAudioPreview', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.defineProperty(HTMLMediaElement.prototype, 'pause', { configurable: true, value: pauseMock })
  })

  it('应使用原生控件且不自动播放，并在元数据载入后展示时长', async () => {
    const { container } = render(AssetAudioPreview, { props: { asset: createAudioAsset() } })
    const audio = container.querySelector('audio') as HTMLAudioElement

    expect(audio).toHaveAttribute('controls')
    expect(audio).not.toHaveAttribute('autoplay')
    expect(audio).toHaveAttribute('preload', 'metadata')
    expect(audio).toHaveAttribute('src', 'https://backend.example.com/public/assets/7/voice-hash')

    Object.defineProperty(audio, 'duration', { configurable: true, value: 65 })
    await fireEvent(audio, new Event('loadedmetadata'))

    expect(screen.getByText('1:05')).toBeInTheDocument()
    expect(screen.getByText('MP3')).toBeInTheDocument()
  })

  it('切换资源和卸载组件时应停止播放并重置进度', async () => {
    const { container, rerender, unmount } = render(AssetAudioPreview, { props: { asset: createAudioAsset() } })
    const firstAudio = container.querySelector('audio') as HTMLAudioElement
    firstAudio.currentTime = 12

    await rerender({ asset: createAudioAsset({ id: 22, file_hash: 'music-hash', url: 'https://backend.example.com/public/assets/7/music-hash' }) })

    expect(pauseMock).toHaveBeenCalled()
    expect(firstAudio.currentTime).toBe(0)

    const activeAudio = container.querySelector('audio') as HTMLAudioElement
    activeAudio.currentTime = 8
    unmount()
    expect(activeAudio.currentTime).toBe(0)
  })

  it('加载失败时应展示可理解的错误提示', async () => {
    const { container } = render(AssetAudioPreview, { props: { asset: createAudioAsset() } })
    await fireEvent(container.querySelector('audio')!, new Event('error'))

    expect(screen.getByRole('alert')).toHaveTextContent('无法加载音频元数据')
  })
})

/** 创建可复用的音频资源测试数据。 */
function createAudioAsset(overrides: Partial<AssetResponse> = {}): AssetResponse {
  return {
    id: 21,
    workspace_id: 7,
    name: 'page_voice',
    file_name: 'voice-hash.mp3',
    original_name: 'page_voice.mp3',
    description: null,
    file_size: 1024,
    file_hash: 'voice-hash',
    content_type: 'audio/mpeg',
    asset_type: 'audio',
    asset_role: 'content',
    render_type: 'audio',
    tags: [],
    analysis_metadata: null,
    render_metadata: null,
    status: 'active',
    archived_at: null,
    archive_reason: null,
    source_asset_id: null,
    history_kind: null,
    content_editable: false,
    url: 'https://backend.example.com/public/assets/7/voice-hash',
    font_config: null,
    rename_block_reason: null,
    delete_block_reason: null,
    archive_block_reason: null,
    archive_warning_reasons: [],
    created_at: '2026-10-18T10:00:00+08:00',
    updated_at: '2026-10-18T10:00:00+08:00',
    ...overrides,
  }
}
