/**
 * 文件功能：定义 Editor 页面预览状态、Runtime iframe ready/error 消息与时间轴控制协议。
 */

export type RuntimePreviewStatus = 'idle' | 'generating' | 'loading' | 'slow' | 'ready' | 'error'

export const PAGE_PREVIEW_READY_EVENT = 'page-preview:ready'
export const PAGE_PREVIEW_ERROR_EVENT = 'page-preview:error'

export const PREVIEW_MOTION_REQUEST_TYPE = 'runtime-preview-motion'
export const PREVIEW_MOTION_STATE_TYPE = 'runtime-preview-motion-state'
export const PREVIEW_MOTION_PROTOCOL_VERSION = 1

export type PreviewMotionAction =
  | 'sync'
  | 'unsync'
  | 'play'
  | 'pause'
  | 'restart'
  | 'seek'
  | 'set-visual-mode'

export type PreviewMotionVisualMode = 'full' | 'reduced'

/** Runtime 回传的当前页时间轴状态；无时间轴时 hasTimeline 为 false。 */
export interface PreviewMotionState {
  hasTimeline: boolean
  timelineId: string | null
  planDigest: string | null
  intent: 'stopped' | 'playing' | 'paused' | null
  phase: 'idle' | 'preparing' | 'ready' | 'seeking' | 'buffering' | 'blocked' | 'completed' | 'error' | 'disposed' | null
  positionMs: number
  durationMs: number
  posterTimeMs: number
  visualMode: PreviewMotionVisualMode
  revision: number
  errorCode: string | null
  errorMessage: string
}

export interface PreviewMotionStateMessage {
  type: typeof PREVIEW_MOTION_STATE_TYPE
  version: number
  requestId?: string
  state: PreviewMotionState
}

export interface PagePreviewReadyMessage {
  type: typeof PAGE_PREVIEW_READY_EVENT
  payload: {
    version: 1
    artifactId: string
  }
}

export interface PagePreviewErrorMessage {
  type: typeof PAGE_PREVIEW_ERROR_EVENT
  payload: {
    version: 1
    artifactId: string
    message: string
    code?: string
  }
}

