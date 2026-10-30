/** 文件功能：对拍 Runtime 预览协议与 Editor 消费者，防止消息名、版本和状态字段漂移。 */
import { expect, it } from 'vitest'
import { PREVIEW_SCENE_PROTOCOL_VERSION as runtimeVersion, PREVIEW_SCENE_REQUEST_TYPE as runtimeRequest, PREVIEW_SCENE_STATE_TYPE as runtimeState,
  parsePreviewSceneCommand } from '../../../runtime/src/core/scene/preview-protocol'
import { PREVIEW_SCENE_PROTOCOL_VERSION, PREVIEW_SCENE_REQUEST_TYPE, PREVIEW_SCENE_STATE_TYPE, isPreviewSceneState } from '../../../editor/src/types/runtime-preview'

it('两端使用相同的 Scene 消息名和版本，只保留播放/停止/订阅', () => {
  expect([PREVIEW_SCENE_PROTOCOL_VERSION, PREVIEW_SCENE_REQUEST_TYPE, PREVIEW_SCENE_STATE_TYPE]).toEqual([runtimeVersion, runtimeRequest, runtimeState])
  for (const action of ['play', 'stop', 'sync', 'unsync']) expect(parsePreviewSceneCommand({ type: runtimeRequest, version: runtimeVersion, action })).not.toBeNull()
  for (const action of ['pause', 'seek', 'restart']) expect(parsePreviewSceneCommand({ type: runtimeRequest, version: runtimeVersion, action })).toBeNull()
})

it('Editor 接受新 Scene 原子状态，拒绝旧时间轴、非法编号和无界摘要', () => {
  const state = { hasScene: true, generation: 2, phase: 'running', hasBlocking: true, blockedTaskIds: [], issue: null }
  expect(isPreviewSceneState(state)).toBe(true)
  expect(isPreviewSceneState({ ...state, generation: -1 })).toBe(false)
  expect(isPreviewSceneState({ ...state, phase: 'seeking' })).toBe(false)
  expect(isPreviewSceneState({ ...state, positionMs: 100 })).toBe(false)
  expect(isPreviewSceneState({ ...state, issue: { code: 'SCENE_TASK_FAILED', message: 'x'.repeat(241) } })).toBe(false)
  expect(isPreviewSceneState({ hasTimeline: true, positionMs: 0, durationMs: 1000, visualMode: 'full' })).toBe(false)
})
