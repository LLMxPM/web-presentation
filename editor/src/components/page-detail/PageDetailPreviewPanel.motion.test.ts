// @vitest-environment jsdom
/**
 * 文件功能：验证页面预览控制条只在存在时间轴时出现，并透传播放、重播、定位与降动效命令。
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { describe, expect, it, vi } from 'vitest'

import PageDetailPreviewPanel from './PageDetailPreviewPanel.vue'
import type { PreviewMotionState } from '@/types/runtime-preview'

const frameApi = vi.hoisted(() => ({
  emitState: null as null | ((state: PreviewMotionState) => void),
  playMotion: vi.fn(),
  pauseMotion: vi.fn(),
  restartMotion: vi.fn(),
  seekMotion: vi.fn(),
  setMotionVisualMode: vi.fn(),
  syncMotion: vi.fn(),
}))

vi.mock('@/components/runtime-preview/RuntimePreviewFrame.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return {
    default: defineComponent({
      name: 'RuntimePreviewFrameStub',
      emits: ['motion-state', 'ready', 'error', 'retry', 'renew'],
      setup(_props, { emit, expose }) {
        frameApi.emitState = state => emit('motion-state', state)
        expose({
          playMotion: frameApi.playMotion,
          pauseMotion: frameApi.pauseMotion,
          restartMotion: frameApi.restartMotion,
          seekMotion: frameApi.seekMotion,
          setMotionVisualMode: frameApi.setMotionVisualMode,
          syncMotion: frameApi.syncMotion,
        })
        return () => h('div', { 'data-testid': 'runtime-frame-stub' })
      },
    }),
  }
})

const baseProps = {
  previewEnabled: true,
  previewUrl: 'http://runtime.example/preview?page=1',
  previewFrameUrl: 'http://runtime.example/preview?page=1',
  previewArtifactId: 'artifact-1',
  previewStatus: 'ready' as const,
  previewStatusMessage: '',
  previewViewport: { width: 1280, height: 720 },
  pageTitle: '封面',
  previewDisplayFileName: 'cover.vue',
  speakerNotesPanelOpen: false,
}

function motionState(overrides: Partial<PreviewMotionState> = {}): PreviewMotionState {
  return {
    hasTimeline: true,
    timelineId: 'intro',
    planDigest: 'plan-1',
    intent: 'stopped',
    phase: 'ready',
    positionMs: 250,
    durationMs: 1200,
    posterTimeMs: 250,
    visualMode: 'reduced',
    revision: 2,
    errorCode: null,
    errorMessage: '',
    ...overrides,
  }
}

describe('PageDetailPreviewPanel 时间轴控制', () => {
  it('无时间轴时不展示控制条', async () => {
    render(PageDetailPreviewPanel, { props: baseProps })
    frameApi.emitState?.(motionState({ hasTimeline: false }))
    await waitFor(() => expect(screen.queryByTestId('preview-motion-controls')).toBeNull())
  })

  it('播放、重播、定位和降动效命令透传 Runtime 预览帧', async () => {
    render(PageDetailPreviewPanel, { props: baseProps })
    frameApi.emitState?.(motionState())
    await waitFor(() => expect(screen.getByTestId('preview-motion-controls')).toBeInTheDocument())
    expect(screen.getByText('00:00 / 00:01')).toBeInTheDocument()

    await fireEvent.click(screen.getByRole('button', { name: '播放页内时间轴' }))
    expect(frameApi.playMotion).toHaveBeenCalledTimes(1)

    await fireEvent.click(screen.getByRole('button', { name: '从起点重播页内时间轴' }))
    expect(frameApi.restartMotion).toHaveBeenCalledTimes(1)

    const slider = screen.getByLabelText('页内时间轴位置') as HTMLInputElement
    await fireEvent.update(slider, '600')
    await waitFor(() => expect(frameApi.seekMotion).toHaveBeenCalledWith(600))

    await fireEvent.click(screen.getByRole('button', { name: '降动效' }))
    expect(frameApi.setMotionVisualMode).toHaveBeenCalledWith('full')

    frameApi.emitState?.(motionState({ intent: 'playing', positionMs: 800 }))
    await waitFor(() => expect(screen.getByRole('button', { name: '暂停页内时间轴' })).toBeInTheDocument())
    expect(screen.getByText('00:01 / 00:01')).toBeInTheDocument()
  })
})
