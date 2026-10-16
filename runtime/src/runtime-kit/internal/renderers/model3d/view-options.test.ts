/**
 * 文件用途：验证 ModelViewOptions 校验/规范化与 Backend 共享正反例完全一致，并覆盖颜色解析。
 *
 * @vitest-environment jsdom
 */

import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import {
  DEFAULT_MODEL_BACKGROUND,
  DEFAULT_MODEL_CAMERA_FOV,
  buildModelViewIdentityKey,
  normalizeModelViewOptions,
  parseBackgroundColor,
  validateModelViewOptions,
} from './view-options'

interface SharedCases {
  valid: Array<Record<string, unknown>>
  invalid: Array<{ reason: string; value: unknown }>
}

/** 与 Backend 共享的正反例文件路径（runtime/../backend/app/core）。 */
const SHARED_CASES_PATH = resolve(
  dirname(fileURLToPath(import.meta.url)),
  '../../../../../../backend/app/core/model_view_options.v1.cases.json',
)

const sharedCases = JSON.parse(readFileSync(SHARED_CASES_PATH, 'utf8')) as SharedCases

describe('normalizeModelViewOptions 共享正反例', () => {
  it('valid 用例应全部通过且无错误', () => {
    for (const item of sharedCases.valid) {
      const result = normalizeModelViewOptions(item)
      expect(result.errors, `valid 用例被拒绝：${JSON.stringify(item)}`).toEqual([])
      expect(result.ok, `valid 用例被拒绝：${JSON.stringify(item)}`).toBe(true)
    }
  })

  it('invalid 用例应全部拒绝且错误有界', () => {
    for (const item of sharedCases.invalid) {
      const result = normalizeModelViewOptions(item.value)
      expect(result.ok, `invalid 用例被放行：${item.reason}`).toBe(false)
      expect(result.errors.length, `${item.reason} 应给出错误`).toBeGreaterThan(0)
      expect(
        result.errors.join(' ').length,
        `${item.reason} 的错误应保持有界`,
      ).toBeLessThanOrEqual(200)
    }
  })

  it('validateModelViewOptions 对非对象输入给出明确错误', () => {
    expect(validateModelViewOptions(null)).toEqual(['展示参数必须是对象。'])
    expect(validateModelViewOptions([])).toEqual(['展示参数必须是对象。'])
  })

  it('缺省字段应回落到契约默认值', () => {
    const result = normalizeModelViewOptions({ name: 'product' })
    expect(result.ok).toBe(true)
    expect(result.options.sceneIndex).toBeNull()
    expect(result.options.cameraIndex).toBeNull()
    expect(result.options.cameraPosition).toBeNull()
    expect(result.options.cameraTarget).toBeNull()
    expect(result.options.cameraFov).toBe(DEFAULT_MODEL_CAMERA_FOV)
    expect(result.options.background).toBe(DEFAULT_MODEL_BACKGROUND)
    expect(result.options.lighting).toBe('auto')
    expect(result.options.interactive).toBe(false)
  })

  it('显式相机与场景索引应被规范化保留', () => {
    const result = normalizeModelViewOptions({
      name: ' product ',
      sceneIndex: 2,
      cameraPosition: [0, 1, 4],
      cameraTarget: [0, 0, 0],
      cameraFov: 60,
      interactive: true,
      lighting: 'source',
    })
    expect(result.ok).toBe(true)
    expect(result.options.name).toBe('product')
    expect(result.options.sceneIndex).toBe(2)
    expect(result.options.cameraPosition).toEqual([0, 1, 4])
    expect(result.options.cameraFov).toBe(60)
    expect(result.options.interactive).toBe(true)
    expect(result.options.lighting).toBe('source')
  })
})

describe('buildModelViewIdentityKey 视角身份键', () => {
  /**
   * 规范化并构建视角键的便捷入口。
   * @param payload 展示参数
   */
  function keyOf(payload: Record<string, unknown>): string {
    const result = normalizeModelViewOptions(payload)
    expect(result.ok).toBe(true)
    return buildModelViewIdentityKey(result.options)
  }

  it('相同展示参数应产出相同键（字段顺序固定）', () => {
    const first = keyOf({ name: 'product', sceneIndex: 0, background: '#112233' })
    const second = keyOf({ name: 'product', sceneIndex: 0, background: '#112233' })

    expect(first).toBe(second)
  })

  it('资源名不参与视角键（资源身份由缓存键的其他部分承载）', () => {
    expect(keyOf({ name: 'product-a' })).toBe(keyOf({ name: 'product-b' }))
  })

  it.each([
    ['场景', { name: 'product' }, { name: 'product', sceneIndex: 1 }],
    ['相机索引', { name: 'product' }, { name: 'product', cameraIndex: 1 }],
    ['显式相机', { name: 'product' }, { name: 'product', cameraPosition: [0, 1, 4], cameraTarget: [0, 0, 0] }],
    ['相机目标', { name: 'product', cameraPosition: [0, 1, 4], cameraTarget: [0, 0, 0] }, { name: 'product', cameraPosition: [0, 1, 4], cameraTarget: [0, 1, 0] }],
    ['视场角', { name: 'product', cameraPosition: [0, 1, 4], cameraTarget: [0, 0, 0], cameraFov: 45 }, { name: 'product', cameraPosition: [0, 1, 4], cameraTarget: [0, 0, 0], cameraFov: 60 }],
    ['背景策略', { name: 'product' }, { name: 'product', background: '#000000' }],
    ['光照策略', { name: 'product' }, { name: 'product', lighting: 'source' }],
  ])('%s 不同应产出不同键，避免不同视角共用静态帧', (_label, left, right) => {
    expect(keyOf(left)).not.toBe(keyOf(right))
  })

  it('交互开关不参与视角键（不改变静态帧像素）', () => {
    expect(keyOf({ name: 'product' })).toBe(keyOf({ name: 'product', interactive: true }))
  })
})

describe('parseBackgroundColor 颜色解析', () => {
  it('transparent 应返回 null', () => {
    expect(parseBackgroundColor('transparent')).toBeNull()
    expect(parseBackgroundColor('TRANSPARENT')).toBeNull()
    expect(parseBackgroundColor('')).toBeNull()
  })

  it('应解析 #RGB、#RRGGBB、#RRGGBBAA 为 0..1 分量', () => {
    expect(parseBackgroundColor('#fff')).toEqual({ r: 1, g: 1, b: 1, a: 1 })
    expect(parseBackgroundColor('#000')).toEqual({ r: 0, g: 0, b: 0, a: 1 })

    const six = parseBackgroundColor('#0f0f10')
    expect(six).not.toBeNull()
    expect(six?.r).toBeCloseTo(15 / 255, 6)
    expect(six?.g).toBeCloseTo(15 / 255, 6)
    expect(six?.b).toBeCloseTo(16 / 255, 6)
    expect(six?.a).toBe(1)

    const eight = parseBackgroundColor('#11223344')
    expect(eight).not.toBeNull()
    expect(eight?.r).toBeCloseTo(17 / 255, 6)
    expect(eight?.g).toBeCloseTo(34 / 255, 6)
    expect(eight?.b).toBeCloseTo(51 / 255, 6)
    expect(eight?.a).toBeCloseTo(68 / 255, 6)
  })

  it('非法颜色应返回 null', () => {
    expect(parseBackgroundColor('red')).toBeNull()
    expect(parseBackgroundColor('rgb(0,0,0)')).toBeNull()
    expect(parseBackgroundColor('#12345')).toBeNull()
    expect(parseBackgroundColor('#gggggg')).toBeNull()
  })
})
