/**
 * 文件用途：验证 Runtime Vite 配置中的自定义 logger 会输出 JSON Lines。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  createRuntimeViteLogger,
  resolveRuntimeServerAllowedHosts,
  resolveRuntimeServerBasePath,
} from './vite.config'

describe('runtime vite logger', () => {
  const originalFormat = process.env.RUNTIME_LOG_FORMAT
  const originalLevel = process.env.RUNTIME_LOG_LEVEL

  afterEach(() => {
    process.env.RUNTIME_LOG_FORMAT = originalFormat
    process.env.RUNTIME_LOG_LEVEL = originalLevel
    vi.restoreAllMocks()
  })

  it('should route vite info logs through runtime json logger', () => {
    process.env.RUNTIME_LOG_FORMAT = 'json'
    process.env.RUNTIME_LOG_LEVEL = 'info'
    const infoSpy = vi.spyOn(console, 'info').mockImplementation(() => {})

    createRuntimeViteLogger().info('\u001b[36mVITE ready\u001b[0m')

    expect(infoSpy).toHaveBeenCalledTimes(1)
    const payload = JSON.parse(String(infoSpy.mock.calls[0][0]))
    expect(payload.service).toBe('runtime')
    expect(payload.module).toBe('runtime.vite')
    expect(payload.event).toBe('vite.info')
    expect(payload.message).toBe('VITE ready')
  })
})

describe('runtime vite allowed hosts', () => {
  it('should allow docker compose runtime service host by default', () => {
    expect(resolveRuntimeServerAllowedHosts()).toEqual(['runtime'])
  })

  it('should merge public URLs and explicit hostnames without duplicates', () => {
    expect(
      resolveRuntimeServerAllowedHosts('runtime, extra.example.com; .preview.example.com', [
        'runtime',
        'https://presentation.example.com/runtime',
      ]),
    ).toEqual(['runtime', 'presentation.example.com', 'extra.example.com', '.preview.example.com'])
  })
})

describe('runtime vite base path', () => {
  it('should keep local development relative when no public path is configured', () => {
    expect(resolveRuntimeServerBasePath()).toBe('./')
  })

  it('should derive same-origin gateway mount path from runtime public URL', () => {
    expect(resolveRuntimeServerBasePath('', 'https://presentation.example.com/runtime')).toBe('/runtime/')
  })

  it('should prefer explicit base path for split runtime domain deployments', () => {
    expect(resolveRuntimeServerBasePath('/', 'https://presentation.example.com/runtime')).toBe('/')
  })
})
