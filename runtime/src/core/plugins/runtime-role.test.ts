/**
 * 文件用途：验证 Runtime 角色解析、插件面裁剪与按类别执行预算的优先级。
 */

import { afterEach, describe, expect, it } from 'vitest'

import {
  getRuntimeRole,
  resolveLightToolTimeoutMs,
  resolveRuntimeKindBudget,
  resolveRuntimeRole,
  resolveRuntimeRoleSurface,
} from './runtime-role'

describe('runtime role resolution', () => {
  it('空值应默认 all，非法值应抛错', () => {
    expect(resolveRuntimeRole(undefined)).toBe('all')
    expect(resolveRuntimeRole('')).toBe('all')
    expect(resolveRuntimeRole(' PREVIEW ')).toBe('preview')
    expect(() => resolveRuntimeRole('worker')).toThrow(/非法 RUNTIME_ROLE/)
  })

  it('getRuntimeRole 应读取 RUNTIME_ROLE 环境变量', () => {
    expect(getRuntimeRole({ RUNTIME_ROLE: 'check' })).toBe('check')
    expect(getRuntimeRole({})).toBe('all')
  })
})

describe('runtime role surface', () => {
  it('preview 不得开放构建、诊断与轻量工具入口', () => {
    const surface = resolveRuntimeRoleSurface('preview')
    expect(surface).toMatchObject({
      health: true,
      preview: true,
      projectBuild: false,
      checkDiagnostics: false,
      lightTools: false,
    })
  })

  it('build 只开放整项目构建入口', () => {
    expect(resolveRuntimeRoleSurface('build')).toMatchObject({
      preview: false,
      projectBuild: true,
      checkDiagnostics: false,
      lightTools: false,
    })
  })

  it('check 开放诊断与轻量工具但不开预览和构建', () => {
    expect(resolveRuntimeRoleSurface('check')).toMatchObject({
      preview: false,
      projectBuild: false,
      checkDiagnostics: true,
      lightTools: true,
    })
  })

  it('all 保持现状全开', () => {
    const surface = resolveRuntimeRoleSurface('all')
    expect(surface.preview && surface.projectBuild && surface.checkDiagnostics && surface.lightTools).toBe(true)
  })
})

describe('runtime kind budget', () => {
  const originalEnv = { ...process.env }

  afterEach(() => {
    for (const key of Object.keys(process.env)) {
      if (!(key in originalEnv)) {
        delete process.env[key]
      }
    }
    Object.assign(process.env, originalEnv)
  })

  it('类别专用变量应优先于角色级与共享变量', () => {
    const env: NodeJS.ProcessEnv = {
      RUNTIME_VITE_DIAGNOSTICS_CONCURRENCY: '3',
      RUNTIME_CHECK_VITE_TASK_CONCURRENCY: '2',
      RUNTIME_VITE_TASK_CONCURRENCY: '1',
    }
    expect(resolveRuntimeKindBudget('diagnostics', 'check', env).concurrency).toBe(3)
  })

  it('角色级变量应覆盖共享变量', () => {
    const env: NodeJS.ProcessEnv = {
      RUNTIME_BUILD_VITE_TASK_CONCURRENCY: '2',
      RUNTIME_VITE_TASK_CONCURRENCY: '1',
    }
    expect(resolveRuntimeKindBudget('project', 'build', env).concurrency).toBe(2)
    expect(resolveRuntimeKindBudget('project', 'all', env).concurrency).toBe(1)
  })

  it('轻量工具应使用独立 RUNTIME_LIGHT_TOOL_* 预算，默认并发 2', () => {
    expect(resolveRuntimeKindBudget('light', 'check', {}).concurrency).toBe(2)
    expect(resolveRuntimeKindBudget('light', 'check', { RUNTIME_LIGHT_TOOL_CONCURRENCY: '4' }).concurrency).toBe(4)
    expect(resolveLightToolTimeoutMs({ RUNTIME_LIGHT_TOOL_TIMEOUT_MS: '2500' })).toBe(2500)
    expect(resolveLightToolTimeoutMs({})).toBeGreaterThan(0)
  })
})
