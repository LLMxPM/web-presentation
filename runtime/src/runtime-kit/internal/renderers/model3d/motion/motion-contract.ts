/**
 * 文件功能：定义 ModelViewer 与编排适配器之间的模型动作句柄契约。
 *
 * 句柄挂在模型根元素上，跨 realm 只依赖固定字符串属性名；句柄只暴露动作摘要、
 * 指定时刻姿态应用与状态证明，不暴露 Three.js 场景、Mixer 或 Object3D。
 */
import type { ModelMotionTransformState } from '@/core/motion/types'

/** 模型根元素上的动作句柄属性名；改名等同破坏 WP06 契约。 */
export const MODEL_MOTION_HANDLE_KEY = '__runtimeModelMotionHandleV1'

export interface ModelAnimationSummary {
  index: number
  name: string | null
  durationMs: number
  channelCount: number
}

export interface ModelMotionApplyRequest {
  clipIndex: number
  clipName?: string
  clipDurationMs: number
  /** 片段内绝对时间（毫秒），已包含裁切与重复换算。 */
  clipTimeMs: number
  /** 实例整体包装变换；不修改片段内部骨骼。 */
  transform: Required<ModelMotionTransformState>
}

export interface ModelMotionStateDetails {
  clipIndex: number
  clipName: string | null
  clipTimeMs: number
  clipDurationMs: number
  actionTimeMs: number
  actionWeight: number
  transform: Required<ModelMotionTransformState>
}

export interface ModelMotionHandle {
  listAnimations(): ModelAnimationSummary[]
  /** 同步应用姿态并显式绘制；未就绪或索引失效时抛错。 */
  applyAt(request: ModelMotionApplyRequest): ModelMotionStateDetails
}

/** 从模型根元素读取动作句柄；句柄来自 iframe realm 时按鸭子类型校验。 */
export function readModelMotionHandle(element: Element): ModelMotionHandle | null {
  const candidate = (element as unknown as Record<string, unknown>)[MODEL_MOTION_HANDLE_KEY]
  if (!candidate || typeof candidate !== 'object') return null
  const record = candidate as { listAnimations?: unknown; applyAt?: unknown }
  if (typeof record.listAnimations !== 'function' || typeof record.applyAt !== 'function') return null
  return candidate as ModelMotionHandle
}

/** 由模型动作状态计算静态帧身份键；无动作时返回空串，保持旧缓存键兼容。 */
export function buildModelMotionStateKey(
  clipIndex: number,
  clipTimeMs: number,
  transform: Required<ModelMotionTransformState>,
): string {
  return JSON.stringify([
    clipIndex,
    Math.round(clipTimeMs * 1000) / 1000,
    transform.x,
    transform.y,
    transform.z,
    transform.scale,
    transform.rotationY,
  ])
}
