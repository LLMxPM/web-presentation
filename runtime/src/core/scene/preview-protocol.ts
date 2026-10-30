/** 文件功能：定义正式单页 Scene 预览协议，只允许显式播放、停止与事件状态订阅。 */
import type { SceneIssue, ScenePhase } from './types'

export const PREVIEW_SCENE_REQUEST_TYPE = 'runtime-preview-scene'
export const PREVIEW_SCENE_STATE_TYPE = 'runtime-preview-scene-state'
export const PREVIEW_SCENE_PROTOCOL_VERSION = 1
export type PreviewSceneAction = 'sync' | 'unsync' | 'play' | 'stop'
export interface PreviewSceneCommand {
  type: typeof PREVIEW_SCENE_REQUEST_TYPE
  version: typeof PREVIEW_SCENE_PROTOCOL_VERSION
  action: PreviewSceneAction
  requestId?: string
}
export interface PreviewSceneState {
  hasScene: boolean
  generation: number | null
  phase: ScenePhase | null
  hasBlocking: boolean
  blockedTaskIds: string[]
  issue: SceneIssue | null
}

/** 旧动作、旧版本和附带定位字段明确拒绝，不做降级解释。 */
export function parsePreviewSceneCommand(value: unknown): PreviewSceneCommand | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const record = value as Record<string, unknown>
  if (record.type !== PREVIEW_SCENE_REQUEST_TYPE || record.version !== PREVIEW_SCENE_PROTOCOL_VERSION
    || typeof record.action !== 'string' || !['sync', 'unsync', 'play', 'stop'].includes(record.action)
    || Object.keys(record).some(key => !['type', 'version', 'action', 'requestId'].includes(key))
    || (record.requestId !== undefined && (typeof record.requestId !== 'string' || record.requestId.length > 128))) return null
  return { type: PREVIEW_SCENE_REQUEST_TYPE, version: PREVIEW_SCENE_PROTOCOL_VERSION, action: record.action as PreviewSceneAction,
    ...(record.requestId ? { requestId: record.requestId as string } : {}) }
}
