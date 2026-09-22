/**
 * 文件用途：严格校验 Runtime 可视化编辑分析请求，并调用纯 SFC 分析器生成 v1 响应。
 */

import { createHash } from 'node:crypto'

import { instrumentVisualEditSfc } from '../instrumentation/instrument-sfc'
import { PAGE_VISUAL_EDIT_PROTOCOL_VERSION, type VisualEditSfcManifest } from '../protocol'
import { analyzeVisualEditSfc } from '../source/analyze-sfc'

export const PAGE_VISUAL_EDIT_MAX_SOURCE_LENGTH = 5_000_000
export const PAGE_VISUAL_EDIT_MAX_REQUEST_BYTES = 20_100_000

const PAGE_MODULE_PATH_PATTERN = /^src\/views\/(?:[A-Za-z0-9_-][A-Za-z0-9_.-]*\/)*[A-Za-z0-9_-][A-Za-z0-9_.-]*\.vue$/
const SOURCE_HASH_PATTERN = /^[0-9a-f]{64}$/
const ANALYZE_REQUEST_FIELDS = new Set(['protocolVersion', 'modulePath', 'sourceHash', 'source'])

export interface VisualEditAnalyzeRequest {
  protocolVersion: 1
  modulePath: string
  sourceHash: string
  source: string
}

export interface VisualEditAnalyzeResponse {
  protocolVersion: 1
  manifest: VisualEditSfcManifest
  instrumentedSource: string
}

/**
 * 校验未知 JSON 对象并执行 SFC 分析。源码 hash 必须与 UTF-8 源码内容完全一致。
 * @param payload 未受信任的内部请求体
 * @returns canonical v1 分析响应
 */
export function analyzeVisualEditRequest(payload: unknown): VisualEditAnalyzeResponse {
  const request = validateAnalyzeRequest(payload)
  const manifest = analyzeVisualEditSfc(request.source, { modulePath: request.modulePath })
  return {
    protocolVersion: PAGE_VISUAL_EDIT_PROTOCOL_VERSION,
    manifest,
    instrumentedSource: instrumentVisualEditSfc(request.source, manifest),
  }
}

/**
 * 对分析请求执行协议版本、字段、路径、长度和 hash 校验。
 */
export function validateAnalyzeRequest(payload: unknown): VisualEditAnalyzeRequest {
  if (!isRecord(payload)) {
    throw new VisualEditAnalyzeError(400, 'PAGE_VISUAL_EDIT_REQUEST_INVALID', '分析请求必须是 JSON 对象。')
  }
  const unexpectedFields = Object.keys(payload).filter(key => !ANALYZE_REQUEST_FIELDS.has(key))
  if (unexpectedFields.length > 0) {
    throw new VisualEditAnalyzeError(
      400,
      'PAGE_VISUAL_EDIT_REQUEST_INVALID',
      `分析请求包含未声明字段：${unexpectedFields.join(', ')}。`,
    )
  }
  if (payload.protocolVersion !== PAGE_VISUAL_EDIT_PROTOCOL_VERSION) {
    throw new VisualEditAnalyzeError(409, 'PAGE_VISUAL_EDIT_PROTOCOL_MISMATCH', '仅支持可视化编辑协议 v1。')
  }
  if (typeof payload.modulePath !== 'string' || !PAGE_MODULE_PATH_PATTERN.test(payload.modulePath)) {
    throw new VisualEditAnalyzeError(
      422,
      'PAGE_VISUAL_EDIT_MODULE_PATH_INVALID',
      'modulePath 必须是 src/views/*.vue 下的页面模块。',
    )
  }
  if (typeof payload.source !== 'string' || payload.source.length === 0) {
    throw new VisualEditAnalyzeError(422, 'PAGE_VISUAL_EDIT_SOURCE_EMPTY', 'Vue SFC 源码不能为空。')
  }
  if (payload.source.length > PAGE_VISUAL_EDIT_MAX_SOURCE_LENGTH) {
    throw new VisualEditAnalyzeError(413, 'PAGE_VISUAL_EDIT_SOURCE_TOO_LARGE', 'Vue SFC 源码超过大小上限。')
  }
  if (typeof payload.sourceHash !== 'string' || !SOURCE_HASH_PATTERN.test(payload.sourceHash)) {
    throw new VisualEditAnalyzeError(422, 'PAGE_VISUAL_EDIT_SOURCE_HASH_INVALID', 'sourceHash 必须是小写 SHA-256。')
  }
  const actualHash = createHash('sha256').update(payload.source).digest('hex')
  if (payload.sourceHash !== actualHash) {
    throw new VisualEditAnalyzeError(422, 'PAGE_VISUAL_EDIT_SOURCE_HASH_MISMATCH', 'sourceHash 与 Vue SFC 源码不一致。')
  }
  return payload as unknown as VisualEditAnalyzeRequest
}

/**
 * 判断未知值是否为普通对象。
 */
function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}

/**
 * 分析请求校验错误，携带稳定 HTTP 状态和业务错误码。
 */
export class VisualEditAnalyzeError extends Error {
  statusCode: number
  code: string

  constructor(statusCode: number, code: string, message: string, cause?: unknown) {
    super(message, { cause })
    this.name = 'VisualEditAnalyzeError'
    this.statusCode = statusCode
    this.code = code
  }
}
