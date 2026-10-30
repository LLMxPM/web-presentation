/**
 * 文件功能：定义 Editor 页面预览状态、Runtime iframe ready/error 消息与 Scene 播放协议。
 */

export type RuntimePreviewStatus = 'idle' | 'generating' | 'loading' | 'slow' | 'ready' | 'error'

export const PAGE_PREVIEW_READY_EVENT = 'page-preview:ready'
export const PAGE_PREVIEW_ERROR_EVENT = 'page-preview:error'

export const PREVIEW_SCENE_REQUEST_TYPE = 'runtime-preview-scene'
export const PREVIEW_SCENE_STATE_TYPE = 'runtime-preview-scene-state'
export const PREVIEW_SCENE_PROTOCOL_VERSION = 1
export type PreviewSceneAction = 'sync' | 'unsync' | 'play' | 'stop'
export type PreviewScenePhase = 'idle' | 'preparing' | 'ready' | 'running' | 'blocked' | 'completed' | 'failed' | 'stopped'
export interface PreviewSceneState {
  hasScene: boolean
  generation: number | null
  phase: PreviewScenePhase | null
  hasBlocking: boolean
  blockedTaskIds: string[]
  issue: { code: string; message: string; taskId?: string } | null
}
export interface PreviewSceneStateMessage {
  type: typeof PREVIEW_SCENE_STATE_TYPE
  version: number
  requestId?: string
  state: PreviewSceneState
}

/** 验证完整有界 Scene 状态；拒绝旧时间轴字段、任意对象和非法 generation。 */
export function isPreviewSceneState(value: unknown): value is PreviewSceneState {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const state = value as Record<string, unknown>
  if (Object.keys(state).some(key => !['hasScene', 'generation', 'phase', 'hasBlocking', 'blockedTaskIds', 'issue'].includes(key))) return false
  if (typeof state.hasScene !== 'boolean' || typeof state.hasBlocking !== 'boolean'
    || !(state.generation === null || Number.isSafeInteger(state.generation) && Number(state.generation) > 0)
    || !(state.phase === null || ['idle', 'preparing', 'ready', 'running', 'blocked', 'completed', 'failed', 'stopped'].includes(String(state.phase)))
    || !Array.isArray(state.blockedTaskIds) || state.blockedTaskIds.length > 128
    || state.blockedTaskIds.some(id => typeof id !== 'string' || id.length > 128)) return false
  if (state.issue === null) return true
  if (!state.issue || typeof state.issue !== 'object' || Array.isArray(state.issue)) return false
  const issue = state.issue as Record<string, unknown>
  if (Object.keys(issue).some(key => !['code', 'message', 'taskId'].includes(key))) return false
  return typeof issue.code === 'string' && issue.code.length <= 128 && typeof issue.message === 'string' && issue.message.length <= 240
    && (issue.taskId === undefined || typeof issue.taskId === 'string' && issue.taskId.length <= 128)
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

