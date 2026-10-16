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
