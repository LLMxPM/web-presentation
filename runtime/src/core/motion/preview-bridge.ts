/**
 * 文件功能：为 Editor 单页预览提供受控时间轴状态与播放命令桥。
 *
 * 只接受父窗口的 postMessage；命令作用于当前页面已注册的窄句柄，
 * 不暴露 transport、适配器或媒体元素，也不创建第二套播放时钟。
 */

import {
  findPageMotionHandle,
  PAGE_MOTION_LIFECYCLE_EVENT,
} from './page-motion-contract'
import type { MotionTransportSnapshot, MotionVisualMode } from './types'

export const PREVIEW_MOTION_PROTOCOL_VERSION = 1
export const PREVIEW_MOTION_REQUEST_TYPE = 'runtime-preview-motion'
export const PREVIEW_MOTION_STATE_TYPE = 'runtime-preview-motion-state'
const BROADCAST_INTERVAL_MS = 250

export type PreviewMotionAction =
  | 'sync'
  | 'unsync'
  | 'play'
  | 'pause'
  | 'restart'
  | 'seek'
  | 'set-visual-mode'

export interface PreviewMotionCommand {
  type: typeof PREVIEW_MOTION_REQUEST_TYPE
  version: number
  requestId?: string
  action: PreviewMotionAction
  positionMs?: number
  visualMode?: MotionVisualMode
}

export interface PreviewMotionState {
  hasTimeline: boolean
  timelineId: string | null
  planDigest: string | null
  intent: MotionTransportSnapshot['intent'] | null
  phase: MotionTransportSnapshot['phase'] | null
  positionMs: number
  durationMs: number
  posterTimeMs: number
  visualMode: MotionVisualMode
  revision: number
  errorCode: string | null
  errorMessage: string
}

const EMPTY_STATE: PreviewMotionState = {
  hasTimeline: false,
  timelineId: null,
  planDigest: null,
  intent: null,
  phase: null,
  positionMs: 0,
  durationMs: 0,
  posterTimeMs: 0,
  visualMode: 'full',
  revision: 0,
  errorCode: null,
  errorMessage: '',
}

/** 读取当前页时间轴的公开状态；无时间轴时返回稳定的空状态。 */
export function readPreviewMotionState(): PreviewMotionState {
  const handle = findPageMotionHandle(document)
  if (!handle) return { ...EMPTY_STATE }
  const snapshot = handle.getSnapshot()
  return {
    hasTimeline: true,
    timelineId: snapshot.timelineId,
    planDigest: snapshot.planDigest,
    intent: snapshot.intent,
    phase: snapshot.phase,
    positionMs: snapshot.positionMs,
    durationMs: snapshot.durationMs,
    posterTimeMs: handle.plan.posterTimeMs,
    visualMode: handle.visualMode,
    revision: snapshot.revision,
    errorCode: snapshot.errorCode,
    errorMessage: snapshot.errorMessage,
  }
}

/**
 * 执行一条预览命令；没有时间轴时返回 false，不伪造成功。
 * 播放前统一准备；停止态或完成态从起点重播，暂停态继续。
 */
export async function executePreviewMotionCommand(command: PreviewMotionCommand): Promise<boolean> {
  if (command.action === 'sync' || command.action === 'unsync') return true
  const handle = findPageMotionHandle(document)
  if (!handle) return false
  switch (command.action) {
    case 'play': {
      await handle.prepare()
      const snapshot = handle.getSnapshot()
      if (snapshot.intent === 'paused') {
        await handle.resume()
      } else if (snapshot.intent === 'stopped' || snapshot.phase === 'completed') {
        await handle.restart()
      } else {
        await handle.play()
      }
      return true
    }
    case 'pause':
      return handle.pause()
    case 'restart':
      await handle.prepare()
      return handle.restart()
    case 'seek':
      if (typeof command.positionMs !== 'number' || !Number.isFinite(command.positionMs)) return false
      await handle.prepare()
      await handle.seek(command.positionMs)
      return true
    case 'set-visual-mode':
      if (command.visualMode !== 'full' && command.visualMode !== 'reduced') return false
      handle.setVisualMode(command.visualMode)
      return true
    default:
      return false
  }
}

/** 校验父窗口消息形状；未知动作或越界参数直接忽略。 */
export function parsePreviewMotionCommand(value: unknown): PreviewMotionCommand | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const record = value as Record<string, unknown>
  if (record.type !== PREVIEW_MOTION_REQUEST_TYPE || record.version !== PREVIEW_MOTION_PROTOCOL_VERSION) return null
  const action = record.action
  if (
    action !== 'sync'
    && action !== 'unsync'
    && action !== 'play'
    && action !== 'pause'
    && action !== 'restart'
    && action !== 'seek'
    && action !== 'set-visual-mode'
  ) {
    return null
  }
  const command: PreviewMotionCommand = {
    type: PREVIEW_MOTION_REQUEST_TYPE,
    version: PREVIEW_MOTION_PROTOCOL_VERSION,
    action,
  }
  if (typeof record.requestId === 'string' && record.requestId) command.requestId = record.requestId
  if (action === 'seek') {
    if (typeof record.positionMs !== 'number' || !Number.isFinite(record.positionMs)) return null
    command.positionMs = record.positionMs
  }
  if (action === 'set-visual-mode') {
    if (record.visualMode !== 'full' && record.visualMode !== 'reduced') return null
    command.visualMode = record.visualMode
  }
  return command
}

/**
 * 安装预览控制桥；仅嵌入在父窗口时生效。
 * @returns 清理函数，重复调用无副作用
 */
export function installPreviewMotionBridge(): () => void {
  if (typeof window === 'undefined' || window.parent === window) {
    return () => {}
  }
  let parentOrigin: string | null = null
  let timer: number | null = null

  const publish = (requestId?: string): void => {
    if (!parentOrigin) return
    const payload: Record<string, unknown> = {
      type: PREVIEW_MOTION_STATE_TYPE,
      version: PREVIEW_MOTION_PROTOCOL_VERSION,
      state: readPreviewMotionState(),
    }
    if (requestId) payload.requestId = requestId
    window.parent.postMessage(payload, parentOrigin)
  }

  const stopTimer = (): void => {
    if (timer !== null) window.clearInterval(timer)
    timer = null
  }

  const handleMessage = (event: MessageEvent<unknown>): void => {
    if (event.source !== window.parent) return
    if (!event.origin || event.origin === 'null') return
    const command = parsePreviewMotionCommand(event.data)
    if (!command) return
    if (command.action === 'sync') {
      parentOrigin = event.origin
      if (timer === null) timer = window.setInterval(() => publish(), BROADCAST_INTERVAL_MS)
      publish(command.requestId)
      return
    }
    if (parentOrigin !== event.origin) return
    if (command.action === 'unsync') {
      parentOrigin = null
      stopTimer()
      return
    }
    executePreviewMotionCommand(command)
      .catch(() => false)
      .then(() => publish(command.requestId))
  }

  const handleLifecycle = (): void => publish()

  window.addEventListener('message', handleMessage)
  window.addEventListener(PAGE_MOTION_LIFECYCLE_EVENT, handleLifecycle)
  return () => {
    window.removeEventListener('message', handleMessage)
    window.removeEventListener(PAGE_MOTION_LIFECYCLE_EVENT, handleLifecycle)
    parentOrigin = null
    stopTimer()
  }
}
