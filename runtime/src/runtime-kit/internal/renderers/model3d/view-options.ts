/**
 * 文件用途：实现 AssetModel.v1 实例展示参数（ModelViewOptions）的纯函数校验与规范化。
 *
 * 校验规则与 Backend 的 `backend/app/core/model_view_options.py` 以及共享正反例
 * `backend/app/core/model_view_options.v1.cases.json` 保持一致：同一组用例在两端必须给出
 * 相同结论（valid 全部通过、invalid 全部拒绝）。本模块不依赖 Three.js，可在 jsdom 下直接单测。
 */

import type { ModelViewOptions, ModelViewVector3 } from '@/core/shared/model-view-options.generated'

/** 三维资源无法渲染时的默认兜底文案。 */
export const DEFAULT_MODEL_FALLBACK_MESSAGE = '三维资源无法渲染，请检查资源名称或文件内容。'

/** 显式透视相机的默认垂直视场角（度）。 */
export const DEFAULT_MODEL_CAMERA_FOV = 45

/** 背景色默认透明。 */
export const DEFAULT_MODEL_BACKGROUND = 'transparent'

/** 光照来源默认自动（仅源场景无光照时补默认灯光）。 */
export const DEFAULT_MODEL_LIGHTING: ModelViewLighting = 'auto'

export type ModelViewLighting = 'auto' | 'source'

/** 规范化后的背景色，分量取值 0..1。 */
export interface ModelBackgroundColor {
  r: number
  g: number
  b: number
  a: number
}

/** 未知字段被忽略，供宿主按 Vue attrs 处理。 */
export interface ModelViewOptionsPayload {
  name?: unknown
  sceneIndex?: unknown
  cameraIndex?: unknown
  cameraPosition?: unknown
  cameraTarget?: unknown
  cameraFov?: unknown
  background?: unknown
  lighting?: unknown
  interactive?: unknown
  fallback?: unknown
  class?: unknown
}

/** 规范化后的内部展示参数，供渲染器直接消费。 */
export interface NormalizedModelViewOptions {
  name: string
  sceneIndex: number | null
  cameraIndex: number | null
  cameraPosition: ModelViewVector3 | null
  cameraTarget: ModelViewVector3 | null
  cameraFov: number
  background: string
  lighting: ModelViewLighting
  interactive: boolean
  fallback: string
}

export interface NormalizeModelViewOptionsResult {
  ok: boolean
  errors: string[]
  options: NormalizedModelViewOptions
}

const BACKGROUND_TRANSPARENT = 'transparent'
const HEX_COLOR_PATTERN = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/

/**
 * 判断值是否为有限数值（拒绝布尔与 NaN/Infinity），与 Backend `_is_finite_number` 一致。
 * @param value 待判断的值
 * @returns 是否为有限数值
 */
function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

/**
 * 判断值是否为非负整数（拒绝布尔、小数与负数），与 Backend `_is_non_negative_integer` 一致。
 * @param value 待判断的值
 * @returns 是否为非负整数
 */
function isNonNegativeInteger(value: unknown): boolean {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0
}

/**
 * 校验并规范化三元数组，非法时写入有界错误信息。
 * @param value 待校验的值
 * @param fieldName 字段名，用于错误信息
 * @param errors 错误收集数组
 * @returns 合法的三元数值数组；非法时返回 null
 */
function validateVector3(value: unknown, fieldName: string, errors: string[]): ModelViewVector3 | null {
  if (!Array.isArray(value) || value.length !== 3) {
    errors.push(`${fieldName} 必须是恰好包含 3 个数的数组。`)
    return null
  }
  if (!value.every(item => isFiniteNumber(item))) {
    errors.push(`${fieldName} 的元素必须是有限数值。`)
    return null
  }
  return [value[0], value[1], value[2]]
}

/**
 * 字段是否被视为“已提供”：undefined 与 null 都视为缺省，与 Backend 的 None 语义一致。
 * @param value 字段值
 * @returns 是否已提供
 */
function isProvided(value: unknown): boolean {
  return value !== undefined && value !== null
}

/**
 * 校验展示参数并返回有界错误列表；空列表表示通过。
 *
 * 与 Backend 校验实现逐条对齐：相机选择互斥、成对约束、有限数值、背景色格式与枚举取值。
 * 未知字段被忽略，供宿主按 Vue attrs 处理。
 * @param payload 原始展示参数对象
 * @returns 有界错误列表
 */
export function validateModelViewOptions(payload: unknown): string[] {
  const errors: string[] = []
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return ['展示参数必须是对象。']
  }

  const record = payload as ModelViewOptionsPayload

  const name = record.name
  if (typeof name !== 'string' || !name.trim()) {
    errors.push('name 必须是必填的非空字符串。')
  }

  const sceneIndex = record.sceneIndex
  if (isProvided(sceneIndex) && !isNonNegativeInteger(sceneIndex)) {
    errors.push('sceneIndex 必须是非负整数。')
  }

  const cameraIndex = record.cameraIndex
  if (isProvided(cameraIndex) && !isNonNegativeInteger(cameraIndex)) {
    errors.push('cameraIndex 必须是非负整数。')
  }

  const hasPosition = isProvided(record.cameraPosition)
  const hasTarget = isProvided(record.cameraTarget)
  if (hasPosition !== hasTarget) {
    errors.push('cameraPosition 与 cameraTarget 必须成对提供。')
  }

  const position = hasPosition ? validateVector3(record.cameraPosition, 'cameraPosition', errors) : null
  const target = hasTarget ? validateVector3(record.cameraTarget, 'cameraTarget', errors) : null
  if (position && target && position[0] === target[0] && position[1] === target[1] && position[2] === target[2]) {
    errors.push('cameraPosition 与 cameraTarget 不能重合。')
  }

  if (isProvided(cameraIndex) && hasPosition) {
    errors.push('cameraIndex 与显式 cameraPosition/cameraTarget 互斥，只能二选一。')
  }

  const cameraFov = record.cameraFov
  if (isProvided(cameraFov)) {
    if (!isFiniteNumber(cameraFov)) {
      errors.push('cameraFov 必须是有限数值。')
    } else if (!(cameraFov > 0 && cameraFov < 180)) {
      errors.push('cameraFov 必须大于 0 且小于 180。')
    } else if (!(hasPosition && hasTarget)) {
      errors.push('cameraFov 仅能与显式 cameraPosition/cameraTarget 一起使用。')
    }
  }

  const background = record.background
  if (isProvided(background)) {
    if (typeof background !== 'string') {
      errors.push('background 必须是字符串。')
    } else {
      const trimmed = background.trim()
      if (trimmed.toLowerCase() !== BACKGROUND_TRANSPARENT && !HEX_COLOR_PATTERN.test(trimmed)) {
        errors.push('background 只接受 transparent 或 #RGB/#RRGGBB/#RRGGBBAA 颜色。')
      }
    }
  }

  const lighting = record.lighting
  if (isProvided(lighting) && lighting !== 'auto' && lighting !== 'source') {
    errors.push('lighting 只接受 auto 或 source。')
  }

  const interactive = record.interactive
  if (isProvided(interactive) && typeof interactive !== 'boolean') {
    errors.push('interactive 必须是布尔值。')
  }

  for (const fieldName of ['fallback', 'class'] as const) {
    const fieldValue = record[fieldName]
    if (isProvided(fieldValue) && typeof fieldValue !== 'string') {
      errors.push(`${fieldName} 必须是字符串。`)
    }
  }

  return errors
}

/**
 * 解析背景色为 0..1 分量；transparent 或无法解析时返回 null。
 *
 * 输入应为已通过校验的颜色字符串；未通过校验的输入一律返回 null，由调用方按错误态处理。
 * @param value 颜色字符串
 * @returns 颜色分量对象；透明或非法时返回 null
 */
export function parseBackgroundColor(value: unknown): ModelBackgroundColor | null {
  const raw = typeof value === 'string' ? value.trim() : ''
  if (!raw || raw.toLowerCase() === BACKGROUND_TRANSPARENT) {
    return null
  }
  if (!HEX_COLOR_PATTERN.test(raw)) {
    return null
  }

  const hex = raw.slice(1)
  const expand = (segment: string): number => parseInt(segment, 16) / 255
  if (hex.length === 3) {
    return { r: expand(hex[0] + hex[0]), g: expand(hex[1] + hex[1]), b: expand(hex[2] + hex[2]), a: 1 }
  }
  if (hex.length === 6) {
    return {
      r: expand(hex.slice(0, 2)),
      g: expand(hex.slice(2, 4)),
      b: expand(hex.slice(4, 6)),
      a: 1,
    }
  }
  return {
    r: expand(hex.slice(0, 2)),
    g: expand(hex.slice(2, 4)),
    b: expand(hex.slice(4, 6)),
    a: expand(hex.slice(6, 8)),
  }
}

/**
 * 判断背景色是否为透明。
 * @param value 颜色字符串
 * @returns 是否透明
 */
export function isTransparentBackground(value: unknown): boolean {
  const raw = typeof value === 'string' ? value.trim().toLowerCase() : ''
  return !raw || raw === BACKGROUND_TRANSPARENT
}

/**
 * 将 props 解析/规范化为内部 ViewOptions，并给出有界错误列表。
 *
 * 即使校验失败也会返回尽力规范化后的 options，便于调用方在错误态展示诊断信息；
 * 调用方必须依据 `ok` 决定是否进入渲染流程。
 * @param payload 公开组件 props（可为任意未知对象）
 * @returns 校验结论、错误列表与规范化选项
 */
export function normalizeModelViewOptions(payload: unknown): NormalizeModelViewOptionsResult {
  const errors = validateModelViewOptions(payload)
  const record = (payload && typeof payload === 'object' ? payload : {}) as ModelViewOptionsPayload

  const options: NormalizedModelViewOptions = {
    name: typeof record.name === 'string' ? record.name.trim() : '',
    sceneIndex: isNonNegativeInteger(record.sceneIndex) ? (record.sceneIndex as number) : null,
    cameraIndex: isNonNegativeInteger(record.cameraIndex) ? (record.cameraIndex as number) : null,
    cameraPosition: Array.isArray(record.cameraPosition) && record.cameraPosition.length === 3
      && record.cameraPosition.every(item => isFiniteNumber(item))
      ? [record.cameraPosition[0] as number, record.cameraPosition[1] as number, record.cameraPosition[2] as number]
      : null,
    cameraTarget: Array.isArray(record.cameraTarget) && record.cameraTarget.length === 3
      && record.cameraTarget.every(item => isFiniteNumber(item))
      ? [record.cameraTarget[0] as number, record.cameraTarget[1] as number, record.cameraTarget[2] as number]
      : null,
    cameraFov: isFiniteNumber(record.cameraFov) ? record.cameraFov : DEFAULT_MODEL_CAMERA_FOV,
    background: typeof record.background === 'string' && record.background.trim()
      ? record.background.trim()
      : DEFAULT_MODEL_BACKGROUND,
    lighting: record.lighting === 'source' ? 'source' : DEFAULT_MODEL_LIGHTING,
    interactive: record.interactive === true,
    fallback: typeof record.fallback === 'string' && record.fallback.trim()
      ? record.fallback.trim()
      : DEFAULT_MODEL_FALLBACK_MESSAGE,
  }

  return { ok: errors.length === 0, errors, options }
}

/** 公开组件 props 与共享类型的兼容别名，供渲染器与单测引用。 */
export type AssetModelViewProps = ModelViewOptions

/**
 * 构建实例视角身份键，供导出静态帧缓存分区使用。
 *
 * 覆盖字段与需求一致：场景/相机选择、显式相机位置与目标、视场角、背景与光照策略。
 * 字段顺序固定且只含规范化后的展示参数，同一实例参数变化必须产出不同键，
 * 避免「相同资源不同视角共用同一帧」；与资源地址、视口尺寸的组合由缓存键构建方负责。
 * @param options 规范化后的展示参数
 * @returns 确定性视角键
 */
export function buildModelViewIdentityKey(options: NormalizedModelViewOptions): string {
  return JSON.stringify({
    sceneIndex: options.sceneIndex,
    cameraIndex: options.cameraIndex,
    cameraPosition: options.cameraPosition,
    cameraTarget: options.cameraTarget,
    cameraFov: options.cameraFov,
    background: options.background,
    lighting: options.lighting,
  })
}
