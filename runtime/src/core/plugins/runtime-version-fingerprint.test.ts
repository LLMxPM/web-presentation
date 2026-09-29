/**
 * 文件用途：验证 Runtime 版本指纹强制语义：期望指纹不匹配时拒绝预览入口。
 */

import { describe, expect, it } from 'vitest'

import {
  assertExpectedRuntimeFingerprint,
  buildRuntimeVersionFingerprint,
  formatRuntimeVersionFingerprint,
} from './runtime-health'

describe('runtime version fingerprint enforcement', () => {
  it('本副本指纹应包含 kit 版本与 build_id，并可格式化为稳定字符串', () => {
    const fingerprint = buildRuntimeVersionFingerprint()
    expect(fingerprint.runtime_kit_version.length).toBeGreaterThan(0)
    expect(typeof fingerprint.build_id).toBe('string')
    expect(formatRuntimeVersionFingerprint()).toContain(fingerprint.runtime_kit_version)
  })

  it('无期望头或指纹一致时放行', () => {
    const local = formatRuntimeVersionFingerprint()
    expect(() => assertExpectedRuntimeFingerprint({}, local)).not.toThrow()
    expect(() =>
      assertExpectedRuntimeFingerprint(
        { 'x-expected-runtime-version-fingerprint': local },
        local,
      ),
    ).not.toThrow()
  })

  it('期望指纹不匹配时必须拒绝，避免 HTML/模块跨版本混用', () => {
    try {
      assertExpectedRuntimeFingerprint(
        { 'x-expected-runtime-version-fingerprint': '1.0.0+b1' },
        '1.0.1+b2',
      )
      throw new Error('应当拒绝版本偏斜')
    } catch (error) {
      expect((error as { code?: string }).code).toBe('PREVIEW_VERSION_SKEW')
      expect((error as { statusCode?: number }).statusCode).toBe(409)
    }
  })
})
