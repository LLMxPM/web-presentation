/**
 * 文件用途：严格校验 Runtime 可视化编辑 apply 请求外壳，并调用原子源码改写核心。
 */

import { applyVisualEditOperations, type ApplyVisualEditOperationsResult } from '../apply/apply-operations'
import { VisualEditApplyError } from '../apply/errors'
import { validateVisualEditOperations } from '../apply/validate-operations'
import type { VisualEditOperation } from '../protocol'
import { validateAnalyzeRequest } from './analyze-request'

const APPLY_REQUEST_FIELDS = new Set(['protocolVersion', 'modulePath', 'sourceHash', 'source', 'operations'])

interface VisualEditApplyRequest {
  protocolVersion: 1
  modulePath: string
  sourceHash: string
  source: string
  operations: VisualEditOperation[]
}

/**
 * 校验请求并执行整批操作；返回字段与 Backend RuntimePageVisualEditApplyResponse camelCase 对齐。
 */
export function applyVisualEditRequest(payload: unknown): ApplyVisualEditOperationsResult {
  const request = validateApplyRequest(payload)
  return applyVisualEditOperations(
    request.source,
    request.modulePath,
    request.sourceHash,
    request.operations,
  )
}

/**
 * 校验 apply 顶层字段、规范源码身份和操作数组。
 */
function validateApplyRequest(payload: unknown): VisualEditApplyRequest {
  if (!isRecord(payload)) {
    throw new VisualEditApplyError(400, 'PAGE_VISUAL_EDIT_REQUEST_INVALID', 'apply 请求必须是 JSON 对象。')
  }
  const unexpectedFields = Object.keys(payload).filter(key => !APPLY_REQUEST_FIELDS.has(key))
  const missingFields = [...APPLY_REQUEST_FIELDS].filter(
    key => !Object.prototype.hasOwnProperty.call(payload, key),
  )
  if (unexpectedFields.length > 0 || missingFields.length > 0) {
    throw new VisualEditApplyError(400, 'PAGE_VISUAL_EDIT_REQUEST_INVALID', 'apply 请求包含额外字段或缺少必需字段。')
  }

  const sourceEnvelope = validateAnalyzeRequest({
    protocolVersion: payload.protocolVersion,
    modulePath: payload.modulePath,
    sourceHash: payload.sourceHash,
    source: payload.source,
  })
  return {
    ...sourceEnvelope,
    operations: validateVisualEditOperations(payload.operations),
  }
}

/**
 * 判断未知值是否为对象。
 */
function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}
