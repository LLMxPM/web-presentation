// @vitest-environment jsdom
/** 文件功能：验证普通和放大预览经 iframe 执行 Scene 播放/停止，有限完成仍允许清理 ambient。 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import PageDetailPreviewPanel from './PageDetailPreviewPanel.vue'
import type { PreviewSceneState } from '@/types/runtime-preview'

const frameApi = vi.hoisted(() => ({ emitState: null as null | ((state: PreviewSceneState) => void), play: vi.fn(), stop: vi.fn() }))
vi.mock('@/components/runtime-preview/RuntimePreviewFrame.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return { default: defineComponent({ emits: ['scene-state', 'ready', 'error', 'retry', 'renew'], setup(_props, { emit, expose }) {
    frameApi.emitState = state => emit('scene-state', state)
    expose({ playScene: frameApi.play, stopScene: frameApi.stop })
    return () => h('div', { 'data-testid': 'runtime-frame-stub' })
  } }) }
})
afterEach(() => { frameApi.play.mockClear(); frameApi.stop.mockClear(); frameApi.emitState = null })
const props = { previewEnabled: true, previewUrl: 'http://runtime.example/preview', previewFrameUrl: 'http://runtime.example/preview', previewArtifactId: 'artifact-1',
  previewStatus: 'ready' as const, previewStatusMessage: '', previewViewport: { width: 1280, height: 720 }, pageTitle: '封面', previewDisplayFileName: 'cover.vue', speakerNotesPanelOpen: false }

/** 完整原子状态，不以位置字段推算播放进度。 */
function state(phase: PreviewSceneState['phase'] = 'idle'): PreviewSceneState {
  return { hasScene: true, generation: phase === 'idle' ? null : 1, phase, hasBlocking: true, blockedTaskIds: [], issue: null }
}

describe('PageDetailPreviewPanel Scene 控制', () => {
  it('无声明时隐藏控制，声明挂载后只提供播放和停止', async () => {
    render(PageDetailPreviewPanel, { props })
    frameApi.emitState?.({ ...state(), hasScene: false })
    expect(screen.queryByTestId('preview-scene-controls')).toBeNull()
    frameApi.emitState?.(state())
    await waitFor(() => expect(screen.getByRole('button', { name: '播放页内 Scene' })).toBeEnabled())
    await fireEvent.click(screen.getByRole('button', { name: '播放页内 Scene' }))
    expect(frameApi.play).toHaveBeenCalledOnce()
    frameApi.emitState?.(state('running'))
    await waitFor(() => expect(screen.getByRole('button', { name: '播放页内 Scene' })).toBeDisabled())
    await fireEvent.click(screen.getByRole('button', { name: '停止页内 Scene' }))
    expect(frameApi.stop).toHaveBeenCalledOnce()
    expect(screen.queryByRole('slider')).toBeNull()
    expect(screen.queryByRole('button', { name: /暂停|重播/ })).toBeNull()
  })

  it('有限任务完成后仍可停止 ambient，停止后允许显式播放新会话', async () => {
    render(PageDetailPreviewPanel, { props }); frameApi.emitState?.(state('completed'))
    await waitFor(() => expect(screen.getByText('有限任务已完成')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: '停止页内 Scene' })).toBeEnabled()
    expect(screen.getByRole('button', { name: '播放页内 Scene' })).toBeDisabled()
    frameApi.emitState?.(state('stopped'))
    await waitFor(() => expect(screen.getByRole('button', { name: '播放页内 Scene' })).toBeEnabled())
  })

  it('受阻与失败显示有界原因，失败后可以重新准备', async () => {
    render(PageDetailPreviewPanel, { props }); frameApi.emitState?.({ ...state('failed'), issue: { code: 'SCENE_TASK_FAILED', message: '页面播放失败' } })
    await waitFor(() => expect(screen.getByText('页面播放失败')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: '播放页内 Scene' })).toBeEnabled()
  })

  it('放大前停止原画布，弹窗内有独立的播放和停止入口', async () => {
    render(PageDetailPreviewPanel, { props }); frameApi.emitState?.(state('running'))
    await fireEvent.click(screen.getByRole('button', { name: '放大查看' }))
    expect(frameApi.stop).toHaveBeenCalledOnce()
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument())
    frameApi.emitState?.(state())
    const dialog = within(screen.getByRole('dialog'))
    await waitFor(() => expect(dialog.getByRole('button', { name: '播放页内 Scene' })).toBeEnabled())
    await fireEvent.click(dialog.getByRole('button', { name: '播放页内 Scene' }))
    expect(frameApi.play).toHaveBeenCalledOnce()
  })
})
