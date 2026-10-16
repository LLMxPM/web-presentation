/**
 * 文件用途：为 PDF / PPTX 导出提供三维模型静态帧的统一准备与清理流程。
 *
 * 背景：ModelViewer 的 WebGL 渲染器使用 preserveDrawingBuffer: false，
 * 任何经过 clone / snapdom 的采集路径都可能拿到空白帧。本模块在 DOM 采集前，
 * 让每个模型实例同步重绘并立即读回 PNG，插入同尺寸覆盖图并隐藏 canvas，
 * 使克隆与 snapdom 看到的是普通 `<img>`，采集结束后按 handle 恢复原状。
 *
 * 关键约束：
 * - 每个实例独立采集：句柄由各自的 ModelViewer 注册，不以资源 hash 直接共用图片；
 * - 覆盖图与缓存条目按实例视角分区：相同资源不同视角（场景/相机/position/target/fov/背景/光照）
 *   或不同视口尺寸/DPR 时必须重新采集；
 * - prepare / cleanup 必须配对，cleanup 幂等，成功或异常都不得残留覆盖 DOM；
 * - 不依赖全局 preserveDrawingBuffer 设置，重绘与读回在同一同步任务内完成。
 */

import {
  MODEL_STATIC_FRAME_IMG_ATTR,
  MODEL_STATIC_FRAME_VERSION,
  readModelStaticFrameHandle,
  type ModelStaticFrameCapture,
  type ModelStaticFrameHandle,
  type ModelStaticFrameIdentity,
} from '@/core/shared/model-static-frame-contract'
import {
  RUNTIME_KIT_EXPORT_DOM_VERSION,
  RUNTIME_KIT_MEDIA_ATTR,
  RUNTIME_KIT_MEDIA_KIND_ATTR,
} from '@/core/services/pptx/PPTXRuntimeKitExportDom'

/** 模型根节点选择器：显式媒体契约 + model3d 类型。 */
export const MODEL3D_MEDIA_SELECTOR = `[${RUNTIME_KIT_MEDIA_ATTR}="${RUNTIME_KIT_EXPORT_DOM_VERSION}"][${RUNTIME_KIT_MEDIA_KIND_ATTR}="model3d"]`

/** 静态帧缓存默认容量；超出时按 LRU 淘汰最久未使用的条目。 */
export const DEFAULT_MODEL_STATIC_FRAME_CACHE_CAPACITY = 8

/** 已 prepare 的模型根集合：保证同一元素不被重复准备，避免叠加多层覆盖图。 */
const preparedModelRoots = new WeakSet<Element>()

/**
 * 构建静态帧缓存键。
 * 键组成与需求字段一一对应：
 * - 资源身份：resourceName + resourceSrc（同名不同版本不共用）；
 * - 实例视角参数与背景策略：viewKey（ModelViewer 从规范化展示参数派生）；
 * - 视口尺寸 + DPR/scale：frameWidth × frameHeight（画布缓冲区像素 = 视口 CSS 尺寸 × 已收敛 DPR）。
 * @param identity 实例帧身份
 * @returns 稳定的字符串键
 */
export function buildModelStaticFrameCacheKey(identity: ModelStaticFrameIdentity): string {
  return JSON.stringify([
    identity.resourceName,
    identity.resourceSrc,
    identity.viewKey,
    identity.frameWidth,
    identity.frameHeight,
  ])
}

/**
 * 任务级静态帧缓存：键为实例身份，值为 PNG dataURL。
 *
 * 释放语义：条目只持有字符串，`clear()` 后即整体释放；默认容量有界，
 * 也不会跨任务复用票据不同的资源地址，因此不会把旧任务的帧带进新任务。
 */
export class ModelStaticFrameCache {
  private readonly entries = new Map<string, string>()
  private readonly capacity: number

  constructor(capacity: number = DEFAULT_MODEL_STATIC_FRAME_CACHE_CAPACITY) {
    const normalized = Number(capacity)
    this.capacity = Number.isFinite(normalized) && normalized > 0
      ? Math.floor(normalized)
      : DEFAULT_MODEL_STATIC_FRAME_CACHE_CAPACITY
  }

  /**
   * 读取缓存帧并刷新 LRU 位置。
   * @param key 缓存键
   * @returns PNG dataURL；未命中时返回 null
   */
  get(key: string): string | null {
    const dataUrl = this.entries.get(key)
    if (dataUrl === undefined) {
      return null
    }
    this.entries.delete(key)
    this.entries.set(key, dataUrl)
    return dataUrl
  }

  /**
   * 写入缓存帧，超容量时淘汰最久未使用的条目。
   * @param key 缓存键
   * @param dataUrl PNG dataURL
   */
  set(key: string, dataUrl: string): void {
    this.entries.delete(key)
    this.entries.set(key, dataUrl)
    while (this.entries.size > this.capacity) {
      const oldest = this.entries.keys().next()
      if (oldest.done) {
        break
      }
      this.entries.delete(oldest.value)
    }
  }

  /** 清空全部条目，供任务结束与测试隔离使用。 */
  clear(): void {
    this.entries.clear()
  }

  /** 当前条目数，供测试与诊断使用。 */
  get size(): number {
    return this.entries.size
  }
}

let defaultModelStaticFrameCache: ModelStaticFrameCache | null = null

/**
 * 读取模块级默认缓存；调用方未指定任务缓存时使用。
 * @returns 默认缓存实例
 */
export function resolveDefaultModelStaticFrameCache(): ModelStaticFrameCache {
  if (!defaultModelStaticFrameCache) {
    defaultModelStaticFrameCache = new ModelStaticFrameCache()
  }
  return defaultModelStaticFrameCache
}

/** 清空默认缓存，供测试隔离与长生命周期页面主动释放。 */
export function clearDefaultModelStaticFrameCache(): void {
  defaultModelStaticFrameCache?.clear()
}

export interface ModelStaticFramePrepareOptions {
  /**
   * 任务级缓存：同一导出任务内复用同视角的帧。
   * 传 null 可显式禁用缓存；缺省使用模块级默认缓存。
   */
  cache?: ModelStaticFrameCache | null
}

export interface ModelStaticFramesHandle {
  /** 本次 prepare 实际创建的覆盖层数量，供诊断与测试断言。 */
  readonly preparedCount: number
  /** 移除本 handle 创建的覆盖层并恢复 canvas；幂等，重复调用无副作用。 */
  cleanup(): void
}

interface PreparedOverlayEntry {
  root: Element
  overlay: HTMLImageElement
  canvasStates: Array<{ element: HTMLCanvasElement; visibility: string }>
}

/**
 * 为根节点内的全部三维模型实例准备静态帧覆盖图。
 *
 * 流程：查找 model3d 根节点 → 读取实例采集句柄 → 命中缓存或同步重绘读回 PNG →
 * 插入同尺寸覆盖 `<img>` 并隐藏 canvas。任何一步失败（未就绪、无句柄、采集失败）
 * 都跳过该实例，保留 canvas 交由既有截图路径兜底。
 * @param root 查询根节点（页面节点、截图沙箱或模型根自身）
 * @param options 准备选项
 * @returns 清理句柄；必须由调用方在 finally 中 cleanup
 */
export function prepareModelStaticFrames(
  root: HTMLElement,
  options: ModelStaticFramePrepareOptions = {},
): ModelStaticFramesHandle {
  const cache = options.cache === undefined ? resolveDefaultModelStaticFrameCache() : options.cache
  const entries: PreparedOverlayEntry[] = []

  for (const target of collectModelRoots(root)) {
    if (preparedModelRoots.has(target)) {
      // 已由外层流程准备：本 handle 不接管，cleanup 不得移除他人创建的覆盖层。
      continue
    }
    const handle = readModelStaticFrameHandle(target)
    if (!handle) {
      continue
    }
    const entry = prepareSingleModelRoot(target, handle, cache)
    if (entry) {
      entries.push(entry)
    }
  }

  let cleaned = false
  return {
    preparedCount: entries.length,
    cleanup: () => {
      if (cleaned) {
        return
      }
      cleaned = true
      for (const entry of entries) {
        releasePreparedOverlay(entry)
      }
    },
  }
}

/**
 * 清理句柄对应的覆盖层；空句柄安全跳过。
 * @param handle prepare 返回的句柄
 */
export function cleanupModelStaticFrames(
  handle: ModelStaticFramesHandle | null | undefined,
): void {
  handle?.cleanup()
}

/**
 * 收集根节点内所有 model3d 媒体根（含根自身命中）。
 * @param root 查询根节点
 * @returns 模型根元素列表，按 DOM 顺序
 */
function collectModelRoots(root: HTMLElement): Element[] {
  const roots: Element[] = []
  if (root.matches(MODEL3D_MEDIA_SELECTOR)) {
    roots.push(root)
  }
  roots.push(...Array.from(root.querySelectorAll(MODEL3D_MEDIA_SELECTOR)))
  return roots
}

/**
 * 为单个模型根准备覆盖图；未就绪或采集失败时返回 null。
 * @param target 模型根元素
 * @param handle 实例采集句柄
 * @param cache 静态帧缓存；null 表示禁用
 * @returns 覆盖层记录；未准备时返回 null
 */
function prepareSingleModelRoot(
  target: Element,
  handle: ModelStaticFrameHandle,
  cache: ModelStaticFrameCache | null,
): PreparedOverlayEntry | null {
  const identity = readHandleIdentity(handle)
  if (!identity) {
    return null
  }

  let dataUrl = cache ? cache.get(buildModelStaticFrameCacheKey(identity)) : null
  if (!dataUrl) {
    const capture = captureStaticFrame(handle)
    if (!capture) {
      return null
    }
    dataUrl = capture.dataUrl
    cache?.set(buildModelStaticFrameCacheKey(capture), dataUrl)
  }

  const overlay = createStaticFrameOverlay(target, dataUrl)
  const canvasStates: PreparedOverlayEntry['canvasStates'] = []
  for (const canvas of Array.from(target.querySelectorAll('canvas'))) {
    canvasStates.push({ element: canvas, visibility: canvas.style.visibility })
    canvas.style.visibility = 'hidden'
  }

  target.appendChild(overlay)
  preparedModelRoots.add(target)
  return { root: target, overlay, canvasStates }
}

/**
 * 读取句柄当前身份并做形状校验；句柄异常时按未就绪处理。
 * @param handle 实例采集句柄
 * @returns 合法身份；未就绪或非法时返回 null
 */
function readHandleIdentity(handle: ModelStaticFrameHandle): ModelStaticFrameIdentity | null {
  let candidate: ModelStaticFrameIdentity | null = null
  try {
    candidate = handle.describe()
  } catch {
    return null
  }
  return normalizeIdentity(candidate)
}

/**
 * 校验身份字段：资源地址与视角键必须为非空字符串，帧像素尺寸必须大于 1。
 * @param candidate 候选身份
 * @returns 合法身份；非法时返回 null
 */
function normalizeIdentity(candidate: ModelStaticFrameIdentity | null): ModelStaticFrameIdentity | null {
  if (!candidate || typeof candidate !== 'object') {
    return null
  }
  const resourceName = String(candidate.resourceName || '').trim()
  const resourceSrc = String(candidate.resourceSrc || '').trim()
  const viewKey = String(candidate.viewKey || '')
  const frameWidth = Number(candidate.frameWidth)
  const frameHeight = Number(candidate.frameHeight)
  if (!resourceSrc || !viewKey || !Number.isFinite(frameWidth) || !Number.isFinite(frameHeight)) {
    return null
  }
  if (frameWidth <= 1 || frameHeight <= 1) {
    return null
  }
  return { resourceName, resourceSrc, viewKey, frameWidth, frameHeight }
}

/**
 * 同步采集当前帧；句柄异常或返回非法数据时按失败处理。
 * @param handle 实例采集句柄
 * @returns 采集结果；失败时返回 null
 */
function captureStaticFrame(handle: ModelStaticFrameHandle): ModelStaticFrameCapture | null {
  let capture: ModelStaticFrameCapture | null = null
  try {
    capture = handle.capture()
  } catch {
    return null
  }
  if (!capture || typeof capture.dataUrl !== 'string' || !capture.dataUrl.startsWith('data:image/png')) {
    return null
  }
  const identity = normalizeIdentity(capture)
  return identity ? { ...identity, dataUrl: capture.dataUrl } : null
}

/**
 * 创建覆盖图 `<img>`：与模型根同尺寸、绝对定位覆盖画布。
 * 说明：必须使用目标元素所属文档创建节点（离屏 iframe 场景跨 realm）。
 * @param target 模型根元素
 * @param dataUrl PNG dataURL
 * @returns 覆盖图元素
 */
function createStaticFrameOverlay(target: Element, dataUrl: string): HTMLImageElement {
  const documentRef = target.ownerDocument
  const overlay = documentRef.createElement('img')
  overlay.setAttribute(MODEL_STATIC_FRAME_IMG_ATTR, MODEL_STATIC_FRAME_VERSION)
  overlay.alt = ''
  overlay.style.position = 'absolute'
  overlay.style.top = '0'
  overlay.style.right = '0'
  overlay.style.bottom = '0'
  overlay.style.left = '0'
  overlay.style.width = '100%'
  overlay.style.height = '100%'
  overlay.style.display = 'block'
  overlay.style.zIndex = '2'
  overlay.src = dataUrl
  return overlay
}

/**
 * 移除覆盖图、恢复 canvas 可见性并归还幂等标记。
 * @param entry 覆盖层记录
 */
function releasePreparedOverlay(entry: PreparedOverlayEntry): void {
  entry.overlay.parentNode?.removeChild(entry.overlay)
  for (const state of entry.canvasStates) {
    state.element.style.visibility = state.visibility
  }
  preparedModelRoots.delete(entry.root)
}
