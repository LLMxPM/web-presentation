/**
 * 文件用途：验证 Runtime 服务端 JSON 日志输出与脱敏行为。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import { logRuntimeServer } from './runtime-logger'

describe('runtime-logger', () => {
  const originalFormat = process.env.RUNTIME_LOG_FORMAT
  const originalLevel = process.env.RUNTIME_LOG_LEVEL

  afterEach(() => {
    process.env.RUNTIME_LOG_FORMAT = originalFormat
    process.env.RUNTIME_LOG_LEVEL = originalLevel
    vi.restoreAllMocks()
  })

  it('should emit json line with contract fields', () => {
    process.env.RUNTIME_LOG_FORMAT = 'json'
    process.env.RUNTIME_LOG_LEVEL = 'debug'
    const infoSpy = vi.spyOn(console, 'info').mockImplementation(() => {})

    logRuntimeServer('info', 'runtime.test', '测试日志', {
      module: 'runtime.test',
      request_id: 'req-runtime',
      artifact_id: 'artifact-1',
      token: 'hidden-token',
    })

    expect(infoSpy).toHaveBeenCalledTimes(1)
    const payload = JSON.parse(String(infoSpy.mock.calls[0][0]))
    expect(payload.service).toBe('runtime')
    expect(payload.module).toBe('runtime.test')
    expect(payload.event).toBe('runtime.test')
    expect(payload.request_id).toBe('req-runtime')
    expect(payload.artifact_id).toBe('artifact-1')
    expect(payload.token).toBe('[redacted]')
  })

  it('should strip ansi control characters from json fields', () => {
    process.env.RUNTIME_LOG_FORMAT = 'json'
    process.env.RUNTIME_LOG_LEVEL = 'info'
    const infoSpy = vi.spyOn(console, 'info').mockImplementation(() => {})

    logRuntimeServer('info', 'runtime.ansi', '\u001b[36mready\u001b[0m', {
      module: 'runtime.test',
    })

    const payload = JSON.parse(String(infoSpy.mock.calls[0][0]))
    expect(payload.message).toBe('ready')
  })
})
