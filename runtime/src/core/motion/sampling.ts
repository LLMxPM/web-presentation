/**
 * 文件功能：定义确定性状态采样结果与摘要计算。
 *
 * 采样摘要进入截图/检查身份：相同计划、时间与视觉模式必须得到相同摘要；
 * 事件历史、会话 ID 与墙上时间不参与。
 */
import { digestMotionPayload, stableMotionStringify } from './compile'
import type { CompiledMotionPlan, MotionStateProof, MotionVisualMode } from './types'

export interface MotionSampleResult {
  timelineId: string
  planDigest: string
  sampledTimeMs: number
  visualMode: MotionVisualMode
  stateDigest: string
  proofs: MotionStateProof[]
}

/**
 * 汇总适配器状态证明并计算稳定摘要。proofs 按 trackId 排序，避免准备顺序影响结果。
 */
export function deriveSampledState(
  plan: CompiledMotionPlan,
  sampledTimeMs: number,
  visualMode: MotionVisualMode,
  proofs: MotionStateProof[],
): MotionSampleResult {
  const sortedProofs = [...proofs].sort((left, right) => left.trackId.localeCompare(right.trackId))
  const payload = {
    planDigest: plan.planDigest,
    sampledTimeMs,
    visualMode,
    states: sortedProofs.map(proof => ({
      trackId: proof.trackId,
      type: proof.type,
      positionMs: proof.positionMs,
      digest: proof.digest,
    })),
  }
  return {
    timelineId: plan.timelineId,
    planDigest: plan.planDigest,
    sampledTimeMs,
    visualMode,
    stateDigest: digestMotionPayload(payload),
    proofs: sortedProofs,
  }
}

/**
 * 计算单个适配器状态证明的摘要；details 必须是有界、可序列化的状态描述。
 */
export function digestMotionStateProof(
  trackId: string,
  type: MotionStateProof['type'],
  positionMs: number,
  details: Record<string, unknown>,
): string {
  return digestMotionPayload({ trackId, type, positionMs, details: stableMotionStringify(details) })
}
