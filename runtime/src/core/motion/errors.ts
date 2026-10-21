/**
 * 文件功能：定义页内编排的统一错误码、定位字段与有界错误对象。
 *
 * 错误码进入检查 envelope、Backend 任务与模型返回；不得在此新增第二套顶层返回格式。
 */

export const MOTION_ERROR_SCHEMA_INVALID = 'TIMELINE_SCHEMA_INVALID'
export const MOTION_ERROR_TARGET_INVALID = 'TIMELINE_TARGET_INVALID'
export const MOTION_ERROR_DEPENDENCY_CYCLE = 'TIMELINE_DEPENDENCY_CYCLE'
export const MOTION_ERROR_PROPERTY_CONFLICT = 'TIMELINE_PROPERTY_CONFLICT'
export const MOTION_ERROR_DURATION_UNRESOLVED = 'TIMELINE_DURATION_UNRESOLVED'
export const MOTION_ERROR_MEDIA_BLOCKED = 'TIMELINE_MEDIA_BLOCKED'
export const MOTION_ERROR_BUFFER_TIMEOUT = 'TIMELINE_BUFFER_TIMEOUT'
export const MOTION_ERROR_MODEL_REFERENCE_STALE = 'MODEL_ANIMATION_REFERENCE_STALE'
export const MOTION_ERROR_SNAPSHOT_UNAVAILABLE = 'TIMELINE_SNAPSHOT_UNAVAILABLE'
export const MOTION_ERROR_UNSUPPORTED = 'TIMELINE_UNSUPPORTED'

export type MotionErrorCode =
  | typeof MOTION_ERROR_SCHEMA_INVALID
  | typeof MOTION_ERROR_TARGET_INVALID
  | typeof MOTION_ERROR_DEPENDENCY_CYCLE
  | typeof MOTION_ERROR_PROPERTY_CONFLICT
  | typeof MOTION_ERROR_DURATION_UNRESOLVED
  | typeof MOTION_ERROR_MEDIA_BLOCKED
  | typeof MOTION_ERROR_BUFFER_TIMEOUT
  | typeof MOTION_ERROR_MODEL_REFERENCE_STALE
  | typeof MOTION_ERROR_SNAPSHOT_UNAVAILABLE
  | typeof MOTION_ERROR_UNSUPPORTED

const MAX_MOTION_MESSAGE_LENGTH = 240

/**
 * 编排契约或运行错误；fieldPath/trackId 用于把错误定位到具体字段或轨道。
 */
export class MotionError extends Error {
  readonly code: MotionErrorCode
  readonly fieldPath: string | null
  readonly trackId: string | null

  constructor(
    code: MotionErrorCode,
    message: string,
    options: { fieldPath?: string; trackId?: string; cause?: unknown } = {},
  ) {
    super(boundMotionMessage(message))
    this.name = 'MotionError'
    this.code = code
    this.fieldPath = options.fieldPath ?? null
    this.trackId = options.trackId ?? null
    if (options.cause !== undefined) {
      ;(this as Error & { cause?: unknown }).cause = options.cause
    }
  }

  /** 输出可进入诊断与模型返回的有界结构，不包含内部对象引用。 */
  toDiagnostic(): { code: MotionErrorCode; message: string; fieldPath: string | null; trackId: string | null } {
    return {
      code: this.code,
      message: this.message,
      fieldPath: this.fieldPath,
      trackId: this.trackId,
    }
  }
}

/**
 * 判断是否为编排错误；跨 realm 时按 code 与 name 识别，不依赖 instanceof。
 */
export function isMotionError(value: unknown): value is MotionError {
  return value instanceof MotionError
    || Boolean(
      value
      && typeof value === 'object'
      && (value as { name?: unknown }).name === 'MotionError'
      && typeof (value as { code?: unknown }).code === 'string',
    )
}

/**
 * 把未知错误收敛为编排错误；已带定位的错误保持原样。
 */
export function toMotionError(
  value: unknown,
  fallbackCode: MotionErrorCode = MOTION_ERROR_SCHEMA_INVALID,
  fallbackMessage = '编排定义无效。',
): MotionError {
  if (isMotionError(value)) {
    return value
  }
  const message = value instanceof Error ? value.message : String(value || fallbackMessage)
  return new MotionError(fallbackCode, message || fallbackMessage, { cause: value })
}

/**
 * 截断错误消息，避免页面源码或资源地址把超长文本带入任务与模型上下文。
 */
export function boundMotionMessage(message: string): string {
  const text = String(message || '').trim() || '编排执行失败。'
  return text.length > MAX_MOTION_MESSAGE_LENGTH ? `${text.slice(0, MAX_MOTION_MESSAGE_LENGTH - 3)}...` : text
}
