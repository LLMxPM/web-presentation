/**
 * 文件用途：验证 Runtime Vite 配置中的自定义 logger 会输出 JSON Lines。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  buildRuntimeServePlugins,
  createRuntimeViteLogger,
  resolveRuntimeServerAllowedHosts,
  resolveRuntimeServerBasePath,
} from './vite.config'
import { resolveRuntimeRoleSurface } from './src/core/plugins/runtime-role'

describe('runtime vite role plugin selection', () => {
  const options = { standalonePreviewEnabled: true }

  it('preview 角色不得注册构建、诊断与轻量工具插件', () => {
    const names = buildRuntimeServePlugins(resolveRuntimeRoleSurface('preview'), options).map(plugin => plugin.name)
    expect(names).toContain('runtime-health')
    expect(names).toContain('runtime-saas-preview')
    expect(names.some(name => name.includes('build-runner'))).toBe(false)
    expect(names.some(name => name.includes('visual-edit'))).toBe(false)
    expect(names.some(name => name.includes('asset-render-hint'))).toBe(false)
  })

  it('build 角色只注册构建入口，check 角色注册诊断与轻量工具', () => {
    const buildNames = buildRuntimeServePlugins(resolveRuntimeRoleSurface('build'), options).map(plugin => plugin.name)
    expect(buildNames).toContain('runtime-build-runner')
    expect(buildNames).not.toContain('runtime-saas-preview')

    const checkNames = buildRuntimeServePlugins(resolveRuntimeRoleSurface('check'), options).map(plugin => plugin.name)
    expect(checkNames).toContain('runtime-build-runner')
    expect(checkNames).toContain('runtime-visual-edit')
    expect(checkNames).toContain('runtime-asset-render-hint-measurer')
    expect(checkNames).not.toContain('runtime-saas-preview')
  })

  it('all 角色保持全量插件注册', () => {
    const names = buildRuntimeServePlugins(resolveRuntimeRoleSurface('all'), options).map(plugin => plugin.name)
    expect(names).toEqual(expect.arrayContaining([
      'runtime-health',
      'runtime-build-runner',
      'runtime-visual-edit',
      'runtime-asset-render-hint-measurer',
      'runtime-saas-preview',
    ]))
  })
})

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

  it('should keep loopback and docker service navigation hosts', () => {
    expect(
      resolveRuntimeServerAllowedHosts('', [
        'runtime',
        'localhost',
        '127.0.0.1',
        'http://platform-lite:7373',
      ]),
    ).toEqual(['runtime', 'localhost', '127.0.0.1', 'platform-lite'])
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
