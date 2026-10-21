/**
 * 文件功能：为静态截图/导出提供无播放副作用的指定时刻采样与状态回执。
 *
 * 只通过页面注册的窄句柄工作；没有时间轴的旧页面返回 skipped，
 * 显式指定时间轴但目标缺失时明确失败，不猜测其他时刻。
 */

import { MOTION_ERROR_SNAPSHOT_UNAVAILABLE, MotionError } from './errors'
import { findPageMotionHandle, type PageMotionHandle } from './page-motion-contract'
import { updateRenderReadyHost } from '@/core/utils/render-ready'
import type { MotionVisualMode } from './types'

export const CAPTURE_MOTION_BRIDGE_VERSION = 'motion-snapshot.v1'
const MAX_CAPTURE_TIME_MS = 3_600_000

export interface CaptureMotionSnapshot {
  timelineId?: string
  atMs?: number
  atLabel?: string
  offsetMs?: number
  visualMode?: MotionVisualMode
}

export interface CaptureMotionReceipt {
  status: 'applied' | 'skipped' | 'degraded'
  timelineId?: string
  planDigest?: string
  sampledTimeMs?: number
  stateDigest?: string
  visualMode?: MotionVisualMode
  message?: string
}

/** 解析目标时间：atMs 优先，其次标签+偏移，缺省使用计划 poster。 */
export function resolveCaptureMotionTime(handle: PageMotionHandle, request?: CaptureMotionSnapshot | null): number {
  const plan = handle.plan
  let target: number
  if (request?.atMs !== undefined) {
    target = request.atMs
  } else if (request?.atLabel !== undefined) {
    const labelTime = plan.labels[request.atLabel]
    if (labelTime === undefined) {
      throw new MotionError(MOTION_ERROR_SNAPSHOT_UNAVAILABLE, `时间轴不存在标签 ${request.atLabel}。`)
    }
    target = labelTime + (request.offsetMs ?? 0)
  } else {
    target = plan.posterTimeMs
  }
  if (!Number.isFinite(target) || target < 0 || target > plan.durationMs || target > MAX_CAPTURE_TIME_MS) {
    throw new MotionError(MOTION_ERROR_SNAPSHOT_UNAVAILABLE, '指定的采样时间超出时间轴范围。')
  }
  return Math.round(target)
}

/**
 * 采样并固化当前页时间轴。捕获页会被丢弃，因此不恢复播放或样式。
 * @param request 选择器；缺省表示默认 poster
 * @returns 有界状态回执
 */
export async function applyCaptureMotionSnapshot(
  request?: CaptureMotionSnapshot | null,
): Promise<CaptureMotionReceipt> {
  const handle = findPageMotionHandle(document)
  if (!handle) {
    if (request?.timelineId) {
      throw new MotionError(MOTION_ERROR_SNAPSHOT_UNAVAILABLE, `页面不存在时间轴 ${request.timelineId}。`)
    }
    return { status: 'skipped', message: '页面未注册时间轴，保留静态默认呈现。' }
  }
  if (request?.timelineId && request.timelineId !== handle.plan.timelineId) {
    throw new MotionError(
      MOTION_ERROR_SNAPSHOT_UNAVAILABLE,
      `页面时间轴 ${handle.plan.timelineId} 与请求 ${request.timelineId} 不一致。`,
    )
  }
  const visualMode = request?.visualMode ?? 'full'
  const sampledTimeMs = resolveCaptureMotionTime(handle, request)
  handle.pause()
  handle.setMuted(true)
  let sampled
  try {
    sampled = await handle.sampleAt(sampledTimeMs, visualMode)
  } catch (error) {
    if (error instanceof MotionError) throw error
    throw new MotionError(MOTION_ERROR_SNAPSHOT_UNAVAILABLE, '页面时间轴采样失败。', { cause: error })
  }
  const receipt: CaptureMotionReceipt = {
    status: 'applied',
    timelineId: sampled.timelineId,
    planDigest: sampled.planDigest,
    sampledTimeMs: sampled.sampledTimeMs,
    stateDigest: sampled.stateDigest,
    visualMode: sampled.visualMode,
  }
  updateRenderReadyHost({ motion: receipt })
  return receipt
}

/** 安装跨执行器的捕获桥；重复安装覆盖为最新实现。 */
export function installCaptureMotionBridge(): void {
  if (typeof window === 'undefined') return
  window.__RUNTIME_APPLY_MOTION_SNAPSHOT__ = async (request?: unknown) =>
    applyCaptureMotionSnapshot(normalizeCaptureRequest(request))
}

/** 把外部传入的选择器收敛为内部字段，拒绝未知类型而不是忽略。 */
function normalizeCaptureRequest(value: unknown): CaptureMotionSnapshot | null {
  if (value == null) return null
  if (typeof value !== 'object' || Array.isArray(value)) {
    throw new MotionError(MOTION_ERROR_SNAPSHOT_UNAVAILABLE, '时间轴采样请求必须是对象。')
  }
  const record = value as Record<string, unknown>
  const request: CaptureMotionSnapshot = {}
  if (record.timelineId !== undefined) request.timelineId = asNonEmptyString(record.timelineId, 'timelineId')
  if (record.atMs !== undefined) request.atMs = asFiniteNumber(record.atMs, 'atMs')
  if (record.atLabel !== undefined) request.atLabel = asNonEmptyString(record.atLabel, 'atLabel')
  if (record.offsetMs !== undefined) request.offsetMs = asFiniteNumber(record.offsetMs, 'offsetMs')
  if (record.visualMode !== undefined) {
    if (record.visualMode !== 'full' && record.visualMode !== 'reduced') {
      throw new MotionError(MOTION_ERROR_SNAPSHOT_UNAVAILABLE, 'visualMode 必须为 full 或 reduced。')
    }
    request.visualMode = record.visualMode
  }
  return request
}

function asFiniteNumber(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new MotionError(MOTION_ERROR_SNAPSHOT_UNAVAILABLE, `${field} 必须是有限数字。`)
  }
  return value
}

function asNonEmptyString(value: unknown, field: string): string {
  if (typeof value !== 'string' || !value) {
    throw new MotionError(MOTION_ERROR_SNAPSHOT_UNAVAILABLE, `${field} 必须是非空字符串。`)
  }
  return value
}
