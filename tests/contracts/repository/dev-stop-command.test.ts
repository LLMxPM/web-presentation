/** 文件功能：隔离验证停服入口的 dry-run、未知占用整批拒绝和显式 force 执行及端口复核。 */
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { main } from '../../../.agents/skills/dev-start-test/scripts/stop.mjs'
import { REPO_ROOT } from '../../../.agents/skills/dev-start-test/scripts/lib/service-targets.mjs'

const initialExitCode = process.exitCode

beforeEach(() => {
  process.exitCode = undefined
  vi.stubEnv('BACKEND_BASE_URL', 'http://127.0.0.1:18000')
  vi.stubEnv('EDITOR_BASE_URL', 'http://127.0.0.1:15173')
  vi.spyOn(console, 'log').mockImplementation(() => {})
})

afterEach(() => {
  process.exitCode = initialExitCode
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})

it('dry-run 即使包含 force 也不停止任何进程', async () => {
  const stop = vi.fn()
  const read = vi.fn(() => ({ listeners: [{ port: 18000, pid: 9500 }], processes: new Map() }))
  await main(['--services', 'backend', '--dry-run', '--force'], { read, stop })
  expect(stop).not.toHaveBeenCalled()
  expect(read).toHaveBeenCalledOnce()
})

it('未知占用会阻止已知服务被部分停止', async () => {
  const stop = vi.fn()
  const owned = { pid: 9501, ppid: 0, name: 'node.exe', commandLine: `node "${REPO_ROOT}/editor/vite.js"` }
  const read = vi.fn(() => ({
    listeners: [{ port: 18000, pid: 9501 }, { port: 15173, pid: 9502 }],
    processes: new Map([[owned.pid, owned]]),
  }))
  await main(['--services', 'backend,editor'], { read, stop })
  expect(stop).not.toHaveBeenCalled()
  expect(process.exitCode).toBe(1)
})

it('force 在进程表不可读时执行监听 PID，并确认端口释放', async () => {
  const stop = vi.fn().mockResolvedValue(undefined)
  const read = vi.fn()
    .mockReturnValueOnce({ listeners: [{ port: 18000, pid: 9503 }], processes: new Map() })
    .mockReturnValue({ listeners: [], processes: new Map() })
  await main(['--services', 'backend', '--force'], { read, stop })
  expect(stop).toHaveBeenCalledWith(9503, expect.any(Map))
  expect(read).toHaveBeenCalledTimes(2)
  expect(process.exitCode).toBeUndefined()
})

it('E2E 停服使用测试覆盖端口，空服务列表在系统查询前拒绝', async () => {
  vi.stubEnv('E2E_API_BASE_URL', 'http://127.0.0.1:28000')
  const read = vi.fn(() => ({ listeners: [], processes: new Map() }))
  await main(['--services', 'backend', '--e2e', '--dry-run'], { read })
  expect(read).toHaveBeenCalledWith([28000])
  read.mockClear()
  await expect(main(['--services='], { read })).rejects.toThrow('不能为空')
  expect(read).not.toHaveBeenCalled()
})
