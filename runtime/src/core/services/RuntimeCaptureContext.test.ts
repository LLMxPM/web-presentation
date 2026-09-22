// @vitest-environment jsdom

/**
 * 文件用途：验证 Runtime 独立捕获地址保留页面查询参数，并覆盖捕获运行标记。
 */

import { describe, expect, it } from 'vitest'

import { resolveRuntimeCaptureRoute } from './RuntimeCaptureContext'

describe('resolveRuntimeCaptureRoute', () => {
  it('应保留页面查询参数并覆盖 Runtime 捕获标记', () => {
    const result = resolveRuntimeCaptureRoute(
      '/sales?period=2026&runtimeMode=display&runtimeCapture=0',
      'https://runtime.example/preview#/origin',
    )
    const query = new URLSearchParams(result.hash.split('?')[1])

    expect(result.path).toBe('/sales')
    expect(query.get('period')).toBe('2026')
    expect(query.get('runtimeMode')).toBe('normal')
    expect(query.get('runtimeCapture')).toBe('1')
  })
})
