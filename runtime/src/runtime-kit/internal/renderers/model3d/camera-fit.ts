/**
 * 文件用途：三维查看器的纯函数取景数学。
 *
 * 负责两类计算，全部为纯函数、不依赖 Three.js，便于在 jsdom 下直接单测：
 * 1. 自动取景：给定场景包围球与相机参数，计算相机位置、裁剪面与长宽比适配；
 * 2. 显式相机与源相机的容器长宽比适配：透视相机只更新 aspect；正交相机按源视锥
 *    （left/right/top/bottom，必要时回退 xmag/ymag）等比扩展，保持投影类型与居中，不缩放改写源几何。
 */

/** 三维向量（仅用于纯函数入参/出参，不绑定 Three.js 类型）。 */
export interface Vec3 {
  x: number
  y: number
  z: number
}

/** 场景包围球。 */
export interface BoundingSphere {
  center: Vec3
  radius: number
}

/** 正交相机视锥（源相机单位）。 */
export interface OrthoFrustum {
  left: number
  right: number
  top: number
  bottom: number
}

export interface AutoFitCameraView {
  /** 相机位置。 */
  position: Vec3
  /** 相机看向的目标点（包围球中心）。 */
  target: Vec3
  /** 近裁剪面。 */
  near: number
  /** 远裁剪面。 */
  far: number
  /** 相机到目标的距离。 */
  distance: number
}

export interface AutoFitCameraParams {
  /** 场景包围球。 */
  sphere: BoundingSphere
  /** 垂直视场角（度）。 */
  fovDeg: number
  /** 容器宽高比；非法时按 1 处理。 */
  aspect: number
  /** 观察方向（相机相对目标的方位）；缺省为 +Z 正视图。 */
  direction?: Vec3
  /** 额外留白比例，缺省 0.1。 */
  paddingRatio?: number
  /** 覆盖近裁剪面；缺省按距离与半径推导。 */
  near?: number
  /** 覆盖远裁剪面；缺省按距离与半径推导。 */
  far?: number
}

/** 默认观察方向：+Z 正视图。 */
export const DEFAULT_FIT_DIRECTION: Vec3 = { x: 0, y: 0, z: 1 }

/** 容器宽高比合法范围，避免极端比例产生非有限距离。 */
export const MIN_CAMERA_ASPECT = 1e-4
export const MAX_CAMERA_ASPECT = 1e4

/** 空场景（无有效包围球）时使用的最小半径，保证相机不落在原点。 */
export const EMPTY_SCENE_RADIUS = 1

/** 默认留白比例。 */
export const DEFAULT_FIT_PADDING_RATIO = 0.1

const DEG_TO_RAD = Math.PI / 180

/**
 * 将宽高比收敛到合法范围；非法、非有限或非正值按 1 处理。
 * @param value 原始宽高比
 * @returns 收敛后的宽高比
 */
function sanitizeAspect(value: unknown): number {
  const numeric = Number(value)
  if (!Number.isFinite(numeric) || numeric <= 0) {
    return 1
  }
  return Math.min(Math.max(numeric, MIN_CAMERA_ASPECT), MAX_CAMERA_ASPECT)
}

/**
 * 规范化容器宽高比；非法或非正值按 1 处理。
 * @param width 容器宽度
 * @param height 容器高度
 * @returns 收敛后的宽高比
 */
export function resolveCameraAspect(width: number, height: number): number {
  const normalizedWidth = Number(width)
  const normalizedHeight = Number(height)
  if (!Number.isFinite(normalizedWidth) || !Number.isFinite(normalizedHeight) || normalizedHeight <= 0) {
    return 1
  }
  return sanitizeAspect(normalizedWidth / normalizedHeight)
}

/**
 * 将方向向量归一化；非法或零向量回退到默认观察方向。
 * @param direction 原始方向
 * @returns 归一化后的方向
 */
export function normalizeDirection(direction?: Vec3): Vec3 {
  const source = direction ?? DEFAULT_FIT_DIRECTION
  const length = Math.hypot(source.x, source.y, source.z)
  if (!Number.isFinite(length) || length <= 0) {
    return { ...DEFAULT_FIT_DIRECTION }
  }
  return { x: source.x / length, y: source.y / length, z: source.z / length }
}

/**
 * 计算完整容纳包围球所需的相机距离（同时适配垂直与水平视场角，取更严格的一侧）。
 * @param radius 包围球半径
 * @param fovDeg 垂直视场角（度）
 * @param aspect 容器宽高比
 * @param paddingRatio 额外留白比例
 * @returns 相机到球心的距离；输入非法时按最小半径处理
 */
export function computeFitDistance(
  radius: number,
  fovDeg: number,
  aspect: number,
  paddingRatio = DEFAULT_FIT_PADDING_RATIO,
): number {
  const safeRadius = Number.isFinite(radius) && radius > 0 ? radius : EMPTY_SCENE_RADIUS
  const safeFov = Number.isFinite(fovDeg) && fovDeg > 0 && fovDeg < 180 ? fovDeg : 45
  const safeAspect = sanitizeAspect(aspect)
  const safePadding = Number.isFinite(paddingRatio) && paddingRatio > 0 ? paddingRatio : 0

  const verticalHalf = (safeFov * DEG_TO_RAD) / 2
  const horizontalHalf = Math.atan(Math.tan(verticalHalf) * safeAspect)
  const limitingHalf = Math.min(verticalHalf, horizontalHalf)
  const distance = safeRadius / Math.sin(limitingHalf)
  return distance * (1 + safePadding)
}

/**
 * 由相机距离与包围球推导近远裁剪面，保证 near>0 且 far>near，兼容极端尺寸。
 * @param distance 相机到目标距离
 * @param radius 包围球半径
 * @param nearOverride 覆盖近裁剪面
 * @param farOverride 覆盖远裁剪面
 * @returns 近远裁剪面
 */
export function resolveClippingPlanes(
  distance: number,
  radius: number,
  nearOverride?: number,
  farOverride?: number,
): { near: number; far: number } {
  const safeDistance = Number.isFinite(distance) && distance > 0 ? distance : EMPTY_SCENE_RADIUS
  const safeRadius = Number.isFinite(radius) && radius > 0 ? radius : EMPTY_SCENE_RADIUS

  const derivedNear = Math.max((safeDistance - safeRadius) * 0.5, safeDistance * 1e-4, 1e-4)
  const derivedFar = Math.max(safeDistance + safeRadius * 2, derivedNear * 10)

  const near = Number.isFinite(nearOverride) && (nearOverride as number) > 0 ? (nearOverride as number) : derivedNear
  const farCandidate = Number.isFinite(farOverride) && (farOverride as number) > 0 ? (farOverride as number) : derivedFar
  const far = Math.max(farCandidate, near * 1.001)

  return { near, far }
}

/**
 * 判断包围球是否可用于自动取景（中心有限、半径为正）。
 * @param sphere 包围球
 * @returns 是否可用
 */
export function isUsableBoundingSphere(sphere: BoundingSphere | null | undefined): boolean {
  if (!sphere) {
    return false
  }
  return Number.isFinite(sphere.center.x)
    && Number.isFinite(sphere.center.y)
    && Number.isFinite(sphere.center.z)
    && Number.isFinite(sphere.radius)
    && sphere.radius > 0
}

/**
 * 计算自动取景相机位置与裁剪面，兼容空场景与极端尺寸。
 * @param params 自动取景参数
 * @returns 相机位置、目标与裁剪面
 */
export function computeAutoFitCamera(params: AutoFitCameraParams): AutoFitCameraView {
  const center = params.sphere?.center ?? { x: 0, y: 0, z: 0 }
  const safeCenter: Vec3 = {
    x: Number.isFinite(center.x) ? center.x : 0,
    y: Number.isFinite(center.y) ? center.y : 0,
    z: Number.isFinite(center.z) ? center.z : 0,
  }
  const radius = isUsableBoundingSphere(params.sphere) ? params.sphere.radius : EMPTY_SCENE_RADIUS
  const direction = normalizeDirection(params.direction)
  const distance = computeFitDistance(radius, params.fovDeg, params.aspect, params.paddingRatio)
  const { near, far } = resolveClippingPlanes(distance, radius, params.near, params.far)

  return {
    position: {
      x: safeCenter.x + direction.x * distance,
      y: safeCenter.y + direction.y * distance,
      z: safeCenter.z + direction.z * distance,
    },
    target: safeCenter,
    near,
    far,
    distance,
  }
}

/**
 * 适配源正交相机视锥到目标容器宽高比，等比扩展较短的一边并保持居中。
 *
 * 不改写源几何，只调整投影范围；源视锥宽高非法时回退到 xmag/ymag。
 * @param frustum 源视锥
 * @param containerAspect 容器宽高比
 * @param fallbackSpan 视锥宽高非法时的兜底跨度
 * @returns 适配后的视锥
 */
export function adaptOrthographicFrustum(
  frustum: OrthoFrustum,
  containerAspect: number,
  fallbackSpan = 2,
): OrthoFrustum {
  const aspect = sanitizeAspect(containerAspect)
  const safeSpan = Number.isFinite(fallbackSpan) && fallbackSpan > 0 ? fallbackSpan : 2

  const rawWidth = Math.abs(frustum.right - frustum.left)
  const rawHeight = Math.abs(frustum.top - frustum.bottom)
  const width = Number.isFinite(rawWidth) && rawWidth > 0 ? rawWidth : safeSpan
  const height = Number.isFinite(rawHeight) && rawHeight > 0 ? rawHeight : safeSpan

  const centerX = (frustum.left + frustum.right) / 2
  const centerY = (frustum.top + frustum.bottom) / 2
  const safeCenterX = Number.isFinite(centerX) ? centerX : 0
  const safeCenterY = Number.isFinite(centerY) ? centerY : 0

  let halfWidth = width / 2
  let halfHeight = height / 2
  if (width / height > aspect) {
    // 源视锥更宽：保持宽度，纵向扩展以匹配容器比例。
    halfHeight = halfWidth / aspect
  } else {
    // 源视锥更高：保持高度，横向扩展。
    halfWidth = halfHeight * aspect
  }

  return {
    left: safeCenterX - halfWidth,
    right: safeCenterX + halfWidth,
    top: safeCenterY + halfHeight,
    bottom: safeCenterY - halfHeight,
  }
}

/**
 * 解析源正交相机的等效视锥：优先生效 left/right/top/bottom，其次回退 xmag/ymag（对称视锥）。
 * @param camera 源相机视锥参数
 * @returns 用于适配的视锥
 */
export function resolveOrthographicSourceFrustum(camera: OrthoFrustum & { xmag?: number; ymag?: number }): OrthoFrustum {
  const rawWidth = Math.abs(camera.right - camera.left)
  const rawHeight = Math.abs(camera.top - camera.bottom)
  if (Number.isFinite(rawWidth) && rawWidth > 0 && Number.isFinite(rawHeight) && rawHeight > 0) {
    return { left: camera.left, right: camera.right, top: camera.top, bottom: camera.bottom }
  }

  const xmag = Number.isFinite(camera.xmag) && (camera.xmag as number) > 0 ? (camera.xmag as number) : 2
  const ymag = Number.isFinite(camera.ymag) && (camera.ymag as number) > 0 ? (camera.ymag as number) : 2
  return { left: -xmag / 2, right: xmag / 2, top: ymag / 2, bottom: -ymag / 2 }
}
