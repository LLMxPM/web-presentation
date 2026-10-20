/** 文件功能：隔离验证 E2E 配置冲突先拒绝、预检停服顺序、dry-run 边界与准备后的直接测试命令。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { buildPrepareEnv, parseWorkflowArgs } from '../../../.agents/skills/dev-start-test/scripts/lib/workflow-options.mjs'
import { preflightE2e } from '../../../.agents/skills/dev-start-test/scripts/lib/e2e-preflight.mjs'
import { main as prepare } from '../../../.agents/skills/dev-start-test/scripts/prepare-e2e.mjs'
import { main as fullTest } from '../../../.agents/skills/dev-start-test/scripts/full-test.mjs'

const initialExitCode = process.exitCode

beforeEach(() => {
  for (const key of ['BACKEND', 'EDITOR', 'RUNTIME', 'RENDERER']) vi.stubEnv(`TESTING_START_${key}`, '')
  vi.stubEnv('TESTING_REUSE_BACKEND', '')
  vi.stubEnv('AI_TEST_MODE', '')
  vi.spyOn(console, 'log').mockImplementation(() => {})
})

afterEach(() => {
  process.exitCode = initialExitCode
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})

describe('配置在副作用之前校验', () => {
  it('拒绝未知参数，继承的对象属性也不能作为选项', () => {
    expect(() => parseWorkflowArgs(['--stop-service'])).toThrow('未知参数')
    expect(() => parseWorkflowArgs(['toString'])).toThrow('未知参数')
  })

  it.each([
    ['TESTING_START_BACKEND', 'false'], ['TESTING_START_EDITOR', 'false'],
    ['TESTING_START_RUNTIME', 'false'], ['TESTING_START_RENDERER', 'no'],
    ['AI_TEST_MODE', 'real'], ['TESTING_REUSE_BACKEND', 'true'],
  ])('冲突 %s=%s 在两个入口的任何预检或执行前拒绝', async (key, value) => {
    vi.stubEnv(key, value)
    for (const main of [prepare, fullTest]) {
      const preflight = vi.fn()
      const run = vi.fn()
      await expect(main(['--stop-services', '--start-infra'], { preflight, run })).rejects.toThrow(key)
      expect(preflight).not.toHaveBeenCalled()
      expect(run).not.toHaveBeenCalled()
    }
  })

  it('补齐固定自启模式，不修改父环境，移除禁用的复用标志', () => {
    const inherited = { TESTING_START_BACKEND: ' TRUE ', TESTING_REUSE_BACKEND: 'false', CUSTOM_VALUE: 'preserved' }
    const env = buildPrepareEnv(inherited)
    for (const key of ['BACKEND', 'EDITOR', 'RUNTIME', 'RENDERER']) expect(env[`TESTING_START_${key}`]).toBe('true')
    expect(env.AI_TEST_MODE).toBe('mock')
    expect(env.TESTING_REUSE_BACKEND).toBeUndefined()
    expect(inherited.TESTING_START_BACKEND).toBe(' TRUE ')
    expect(env.CUSTOM_VALUE).toBe('preserved')
  })

  it('两个入口的 dry-run 都不调用准备或测试命令', async () => {
    for (const main of [prepare, fullTest]) {
      const preflight = vi.fn().mockResolvedValue(undefined)
      const run = vi.fn()
      const status = vi.fn()
      await main(['--dry-run'], { preflight, run, status })
      expect(preflight).toHaveBeenCalledWith(expect.objectContaining({ dryRun: true }), expect.any(Object))
      expect(run).not.toHaveBeenCalled()
      expect(status).not.toHaveBeenCalled()
    }
  })
})

describe('共享预检的操作顺序', () => {
  const occupied = [{ key: 'backend', label: 'Backend', port: 18000 }]

  /** 提供完全隔离的操作替身，收集预演和真实操作顺序。 */
  function operations() {
    const calls: string[] = []
    return {
      calls,
      ensureDependencies: vi.fn(async () => { calls.push('dependencies') }),
      ensurePreviewHost: vi.fn(async () => { calls.push('preview-host') }),
      findOccupied: vi.fn().mockResolvedValueOnce(occupied).mockImplementation(async () => { calls.push('verify-ports'); return [] }),
      stopOccupied: vi.fn((_targets, options) => { calls.push(options.dryRun ? 'plan' : 'stop') }),
      install: vi.fn(() => { calls.push('browsers') }),
    }
  }

  it('完整准备先预演，再停服，确认端口释放后才安装浏览器', async () => {
    const ops = operations()
    await preflightE2e({ stopServices: true, installBrowsers: true }, ops)
    expect(ops.calls).toEqual(['dependencies', 'preview-host', 'plan', 'stop', 'verify-ports', 'browsers'])
  })

  it('dry-run 只调用停服预演，浏览器安装也携带 dry-run', async () => {
    const ops = operations()
    await preflightE2e({ stopServices: true, installBrowsers: true, dryRun: true }, ops)
    expect(ops.stopOccupied).toHaveBeenCalledOnce()
    expect(ops.stopOccupied).toHaveBeenCalledWith(occupied, expect.objectContaining({ dryRun: true }))
    expect(ops.install).toHaveBeenCalledWith(expect.objectContaining({ dryRun: true }))
    expect(ops.calls).not.toContain('stop')
  })

  it('未允许停服或预演发现未知占用时，不停止服务或安装浏览器', async () => {
    const ops = operations()
    await expect(preflightE2e({ installBrowsers: true }, ops)).rejects.toThrow('端口已被占用')
    expect(ops.stopOccupied).not.toHaveBeenCalled()
    expect(ops.install).not.toHaveBeenCalled()
    const blocked = operations()
    blocked.stopOccupied.mockImplementation(() => { throw new Error('unknown PID') })
    await expect(preflightE2e({ stopServices: true, installBrowsers: true }, blocked)).rejects.toThrow('unknown PID')
    expect(blocked.stopOccupied).toHaveBeenCalledOnce()
    expect(blocked.stopOccupied).toHaveBeenCalledWith(occupied, expect.objectContaining({ dryRun: true }))
    expect(blocked.install).not.toHaveBeenCalled()
  })

  it('预览主机名检查在依赖探测之后、端口检查之前执行', async () => {
    const ops = operations()
    await preflightE2e({ stopServices: true }, ops)
    expect(ops.calls.indexOf('preview-host')).toBe(ops.calls.indexOf('dependencies') + 1)
    expect(ops.calls.indexOf('preview-host')).toBeLessThan(ops.calls.indexOf('plan'))
  })

  it('停止后端口未释放即终止后续操作', async () => {
    const ops = operations()
    ops.findOccupied.mockReset().mockResolvedValue(occupied)
    await expect(preflightE2e({ stopServices: true, installBrowsers: true }, ops)).rejects.toThrow('停止后端口仍被占用')
    expect(ops.install).not.toHaveBeenCalled()
  })
})

it('成功 prepare 只重置一次，并提供不再 prepare 的全部 project 命令', async () => {
  const run = vi.fn(() => 0)
  const preflight = vi.fn().mockResolvedValue(undefined)
  const status = vi.fn(() => ({ services: {
    backend: { status: 'up', url: 'http://127.0.0.1:18000', e2eReadiness: {
      test_mode: 'mock', database_profile: 'e2e', redis_profile: 'e2e', seed_version: 1, smoke_data_ready: true,
    } },
    editor: { status: 'up' }, runtime: { status: 'up', ready: true }, renderer: { status: 'up' },
  } }))
  await prepare([], { preflight, run, status })
  expect(run).toHaveBeenCalledOnce()
  expect(run).toHaveBeenCalledWith('pnpm', ['run', 'test:e2e:prepare'], expect.objectContaining({ env: expect.objectContaining({ AI_TEST_MODE: 'mock' }) }))
  const logs = vi.mocked(console.log).mock.calls.flat().map(String)
  const next = logs.find((line) => line.includes('pnpm exec playwright test'))
  expect(next).toContain('--config tests/config/playwright.config.ts')
  expect(next).not.toContain('--project=')
  expect(logs.some((line) => line.includes('pnpm run test:e2e:all'))).toBe(false)
})

it('全量入口传入固定测试环境并保留失败退出码', async () => {
  const run = vi.fn(() => 7)
  await fullTest([], { preflight: vi.fn(), run, status: () => ({ services: {} }) })
  expect(run).toHaveBeenCalledWith('pnpm', ['run', 'test:all'], expect.objectContaining({ env: expect.objectContaining({ AI_TEST_MODE: 'mock', TESTING_START_BACKEND: 'true' }) }))
  expect(process.exitCode).toBe(7)
})
