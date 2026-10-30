/** 文件功能：定义实例级模型 Scene 句柄，仅暴露数值副本、真实片段摘要与受管任务，不暴露 Three.js 对象。 */
import type { SceneTask } from '@/core/scene/types'

export const MODEL_SCENE_HANDLE_KEY = '__runtimeModelSceneHandleV1'
export interface ModelSceneClip { index: number; name: string | null; durationMs: number; channelCount: number; signature: string | null }
export interface ModelSceneTransform { x: number; y: number; z: number; scale: number; rotationY: number }
export interface ModelSceneCamera { x: number; y: number; z: number; targetX: number; targetY: number; targetZ: number; fov: number }
export interface ModelSceneAnimation extends Pick<SceneTask, 'id' | 'role' | 'startMs' | 'afterTrack' | 'offsetMs'> {
  clipIndex: number
  signature: string
  /** 额外重复次数；-1 只允许 ambient，速率只允许正向 0.01–16。 */
  repeat?: number
  rate?: number
}
export interface ModelSceneHandle {
  isReady(): boolean
  animations(): ModelSceneClip[]
  animation(options: ModelSceneAnimation): SceneTask
  readonly transform: ModelSceneTransform
  readonly camera: ModelSceneCamera
  /** 将页面修改的实例数值副本应用到私有包装节点与相机，并请求重绘。 */
  invalidate(): void
  /** 应在 Scene.onCleanup 登记；恢复本次加载的独立初始姿态与视角。 */
  reset(): void
}
export interface ModelSceneComponent { getHandle(): ModelSceneHandle | null }

/** 读取当前根的受限句柄，不能通过此 API 得到材质、几何或骨骼。 */
export function readModelSceneHandle(element: Element | null): ModelSceneHandle | null {
  const handle = element && (element as unknown as Record<string, unknown>)[MODEL_SCENE_HANDLE_KEY] as ModelSceneHandle | undefined
  return handle && typeof handle.animation === 'function' && typeof handle.isReady === 'function' && handle.isReady() ? handle : null
}
