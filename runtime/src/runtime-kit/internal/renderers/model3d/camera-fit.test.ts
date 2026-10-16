/**
 * 文件用途：验证三维查看器的自动取景数学与相机长宽比适配（纯函数，不依赖 WebGL）。
 *
 * @vitest-environment jsdom
 */

import { describe, expect, it } from 'vitest'

import {
  DEFAULT_FIT_DIRECTION,
  EMPTY_SCENE_RADIUS,
  adaptOrthographicFrustum,
  computeAutoFitCamera,
  computeFitDistance,
  isUsableBoundingSphere,
  normalizeDirection,
  resolveCameraAspect,
  resolveClippingPlanes,
  resolveOrthographicSourceFrustum,
} from './camera-fit'

const FOV_45 = 45
const HALF_FOV_RAD = ((FOV_45 * Math.PI) / 180) / 2

describe('computeFitDistance 自动取景距离', () => {
  it('宽容器下应受垂直视场角限制', () => {
    const distance = computeFitDistance(1, FOV_45, 2, 0)
    expect(distance).toBeCloseTo(1 / Math.sin(HALF_FOV_RAD), 6)
  })

  it('窄容器下应受水平视场角限制且距离更远', () => {
    const wide = computeFitDistance(1, FOV_45, 2, 0)
    const narrow = computeFitDistance(1, FOV_45, 0.5, 0)
    const horizontalHalf = Math.atan(Math.tan(HALF_FOV_RAD) * 0.5)
    expect(narrow).toBeCloseTo(1 / Math.sin(horizontalHalf), 6)
    expect(narrow).toBeGreaterThan(wide)
  })

  it('留白比例应线性放大距离', () => {
    const base = computeFitDistance(2, 60, 1.5, 0)
    const padded = computeFitDistance(2, 60, 1.5, 0.1)
    expect(padded).toBeCloseTo(base * 1.1, 6)
  })

  it('非法宽高比应按 1 处理', () => {
    expect(computeFitDistance(1, FOV_45, Number.POSITIVE_INFINITY, 0))
      .toBeCloseTo(computeFitDistance(1, FOV_45, 1, 0), 6)
  })
})

describe('computeAutoFitCamera 自动取景相机', () => {
  it('应沿默认方向放置相机并看向包围球中心', () => {
    const view = computeAutoFitCamera({
      sphere: { center: { x: 1, y: 2, z: 3 }, radius: 1 },
      fovDeg: FOV_45,
      aspect: 2,
      paddingRatio: 0,
    })
    const distance = 1 / Math.sin(HALF_FOV_RAD)
    expect(view.target).toEqual({ x: 1, y: 2, z: 3 })
    expect(view.position.x).toBeCloseTo(1 + DEFAULT_FIT_DIRECTION.x * distance, 6)
    expect(view.position.y).toBeCloseTo(2 + DEFAULT_FIT_DIRECTION.y * distance, 6)
    expect(view.position.z).toBeCloseTo(3 + DEFAULT_FIT_DIRECTION.z * distance, 6)
    expect(view.near).toBeGreaterThan(0)
    expect(view.far).toBeGreaterThan(view.near)
  })

  it('空场景应使用最小半径并保持有限裁剪面', () => {
    const view = computeAutoFitCamera({
      sphere: { center: { x: 0, y: 0, z: 0 }, radius: 0 },
      fovDeg: FOV_45,
      aspect: 1,
      paddingRatio: 0,
    })
    expect(view.distance).toBeCloseTo(computeFitDistance(EMPTY_SCENE_RADIUS, FOV_45, 1, 0), 6)
    expect(Number.isFinite(view.position.z)).toBe(true)
    expect(view.near).toBeGreaterThan(0)
    expect(view.far).toBeGreaterThan(view.near)
  })

  it('极端尺寸仍应产生有限且有序的裁剪面', () => {
    const view = computeAutoFitCamera({
      sphere: { center: { x: 1e6, y: -1e6, z: 1e6 }, radius: 1e9 },
      fovDeg: FOV_45,
      aspect: 1.78,
      paddingRatio: 0.1,
    })
    expect(Number.isFinite(view.distance)).toBe(true)
    expect(Math.abs(view.position.x)).toBeLessThan(Number.MAX_VALUE)
    expect(view.near).toBeGreaterThan(0)
    expect(view.far).toBeGreaterThan(view.near)
  })
})

describe('相机辅助函数', () => {
  it('resolveCameraAspect 应拒绝非法尺寸', () => {
    expect(resolveCameraAspect(400, 200)).toBe(2)
    expect(resolveCameraAspect(0, 0)).toBe(1)
    expect(resolveCameraAspect(400, Number.NaN)).toBe(1)
    expect(resolveCameraAspect(Number.POSITIVE_INFINITY, 200)).toBe(1)
    expect(resolveCameraAspect(1e9, 1)).toBe(1e4)
  })

  it('normalizeDirection 应对零向量回退默认方向', () => {
    expect(normalizeDirection({ x: 0, y: 0, z: 0 })).toEqual(DEFAULT_FIT_DIRECTION)
    const normalized = normalizeDirection({ x: 0, y: 0, z: 5 })
    expect(normalized).toEqual({ x: 0, y: 0, z: 1 })
  })

  it('isUsableBoundingSphere 应拒绝空/非法包围球', () => {
    expect(isUsableBoundingSphere(null)).toBe(false)
    expect(isUsableBoundingSphere({ center: { x: 0, y: 0, z: 0 }, radius: 0 })).toBe(false)
    expect(isUsableBoundingSphere({ center: { x: Number.NaN, y: 0, z: 0 }, radius: 1 })).toBe(false)
    expect(isUsableBoundingSphere({ center: { x: 0, y: 0, z: 0 }, radius: 1 })).toBe(true)
  })

  it('resolveClippingPlanes 应保证 near>0 且 far>near', () => {
    expect(resolveClippingPlanes(0, 0)).toEqual({ near: 1e-4, far: 3 })
    const explicit = resolveClippingPlanes(10, 1, 0.1, 100)
    expect(explicit).toEqual({ near: 0.1, far: 100 })
  })
})

describe('adaptOrthographicFrustum 正交相机适配', () => {
  it('源视锥更宽时应纵向扩展以匹配容器', () => {
    const adapted = adaptOrthographicFrustum({ left: -2, right: 2, top: 1, bottom: -1 }, 1)
    expect(adapted.left).toBeCloseTo(-2, 6)
    expect(adapted.right).toBeCloseTo(2, 6)
    expect(adapted.top).toBeCloseTo(2, 6)
    expect(adapted.bottom).toBeCloseTo(-2, 6)
  })

  it('源视锥更高时应横向扩展以匹配容器', () => {
    const adapted = adaptOrthographicFrustum({ left: -2, right: 2, top: 1, bottom: -1 }, 4)
    expect(adapted.left).toBeCloseTo(-4, 6)
    expect(adapted.right).toBeCloseTo(4, 6)
    expect(adapted.top).toBeCloseTo(1, 6)
    expect(adapted.bottom).toBeCloseTo(-1, 6)
  })

  it('应保持视锥中心不被平移', () => {
    const adapted = adaptOrthographicFrustum({ left: 8, right: 12, top: 4, bottom: 2 }, 1)
    expect((adapted.left + adapted.right) / 2).toBeCloseTo(10, 6)
    expect((adapted.top + adapted.bottom) / 2).toBeCloseTo(3, 6)
  })

  it('源视锥宽高非法时应回退到兜底跨度', () => {
    const adapted = adaptOrthographicFrustum({ left: 0, right: 0, top: 0, bottom: 0 }, 1, 2)
    expect(adapted.right - adapted.left).toBeCloseTo(2, 6)
    expect(adapted.top - adapted.bottom).toBeCloseTo(2, 6)
  })
})

describe('resolveOrthographicSourceFrustum 源视锥解析', () => {
  it('应优先使用 left/right/top/bottom', () => {
    const frustum = resolveOrthographicSourceFrustum({ left: -3, right: 3, top: 1.5, bottom: -1.5 })
    expect(frustum).toEqual({ left: -3, right: 3, top: 1.5, bottom: -1.5 })
  })

  it('视锥非法时应回退 xmag/ymag', () => {
    const frustum = resolveOrthographicSourceFrustum({ left: 0, right: 0, top: 0, bottom: 0, xmag: 6, ymag: 4 })
    expect(frustum).toEqual({ left: -3, right: 3, top: 2, bottom: -2 })
  })
})
