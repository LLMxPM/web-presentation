/** 文件功能：按实例注册静态 PNG 采集句柄，重绘与读回始终处于同一同步任务。 */
import type * as ThreeNamespace from 'three'
import { MODEL_STATIC_FRAME_HANDLE_KEY, type ModelStaticFrameCapture, type ModelStaticFrameHandle, type ModelStaticFrameIdentity } from '@/core/shared/model-static-frame-contract'
import { buildModelCameraViewKey } from './camera-state'
/** 不暴露 renderer；只提供有身份的 PNG 与同引用注销。 */
export function createModelStaticFrameController(options: {
  root(): HTMLElement | null; resolveContext(): { canvas: HTMLCanvasElement; scene: ThreeNamespace.Scene; camera: ThreeNamespace.Camera } | null
  resource(): { name: string; src: string; viewKey: string }; renderFrame(): void
}) {
let registeredStaticFrameHandle: ModelStaticFrameHandle | null = null
/**
 * 读取当前实例的静态帧身份；未就绪时返回 null。
 * 身份包含资源名/资源地址、视角键与帧像素尺寸，供导出侧缓存分区。
 * @returns 实例身份；不可采集时返回 null
 */
function describeStaticFrame(): ModelStaticFrameIdentity | null {
  const context = options.resolveContext()
  if (!context) {
    return null
  }
  if (!options.resource().src) {
    return null
  }
  return {
    resourceName: options.resource().name,
    resourceSrc: options.resource().src,
    viewKey: buildModelCameraViewKey(options.resource().viewKey, context.camera),
    frameWidth: context.canvas.width,
    frameHeight: context.canvas.height,
  }
}

/**
 * 采集当前静态帧：同步重绘后立即读回 PNG，不改变视角、不启用交互。
 * 关键约束：renderer 使用 preserveDrawingBuffer: false，必须 render 与 toDataURL 处于同一同步任务。
 * @returns PNG dataURL 与采集时刻身份；尚未就绪或采集失败时返回 null
 */
function captureStaticFrame(): ModelStaticFrameCapture | null {
  const context = options.resolveContext()
  if (!context) {
    return null
  }
  try {
    options.renderFrame()
    const dataUrl = context.canvas.toDataURL('image/png')
    if (!dataUrl.startsWith('data:image/png')) {
      return null
    }
    const identity = describeStaticFrame()
    if (!identity) {
      return null
    }
    return { ...identity, dataUrl }
  } catch {
    return null
  }
}

/**
 * 向根元素注册静态帧采集句柄，供 PDF/PPTX 导出在采集前读取当前帧。
 * 卸载时必须按同一引用注销，避免残留悬空句柄。
 */
function installStaticFrameHandle(): void {
  const root = options.root()
  if (!root) {
    return
  }
  const handle: ModelStaticFrameHandle = {
    describe: describeStaticFrame,
    capture: captureStaticFrame,
  }
  ;(root as unknown as Record<string, unknown>)[MODEL_STATIC_FRAME_HANDLE_KEY] = handle
  registeredStaticFrameHandle = handle
}

/**
 * 注销根元素上的静态帧采集句柄；仅移除本实例注册的引用。
 */
function uninstallStaticFrameHandle(): void {
  const root = options.root()
  if (root) {
    const record = root as unknown as Record<string, unknown>
    if (record[MODEL_STATIC_FRAME_HANDLE_KEY] === registeredStaticFrameHandle) {
      delete record[MODEL_STATIC_FRAME_HANDLE_KEY]
    }
  }
  registeredStaticFrameHandle = null
}

return { captureStaticFrame, installStaticFrameHandle, uninstallStaticFrameHandle }
}
