/** 文件功能：验证全量门禁并发上限、通道顺序、失败收敛与 E2E 独占阶段。 */
import { expect, it, vi } from 'vitest'
import { resolveTestBudget, runTestPlan, TEST_LANES, FINAL_TEST_STEP } from '../../../scripts/testing/full-test-plan.mjs'
import { main as fullTest } from '../../../.agents/skills/dev-start-test/scripts/full-test.mjs'

/** 手动释放异步阶段，以确定性检查并发调度，不依赖定时器或真实进程。 */
function deferred() {
  let resolve!: (code: number) => void
  const promise = new Promise<number>(done => { resolve = done })
  return { promise, resolve }
}

it('默认最多两个通道，低核机器串行，支持显式串行与 worker 上限', () => {
  expect(resolveTestBudget({}, 16)).toEqual({ concurrency: 2, workers: 4 })
  expect(resolveTestBudget({}, 2)).toEqual({ concurrency: 1, workers: 1 })
  expect(resolveTestBudget({ TEST_ALL_CONCURRENCY: '1', VITEST_MAX_WORKERS: '2' }, 16))
    .toEqual({ concurrency: 1, workers: 2 })
  for (const value of ['0', '3', 'NaN']) expect(() => resolveTestBudget({ TEST_ALL_CONCURRENCY: value })).toThrow()
  expect(() => resolveTestBudget({ VITEST_MAX_WORKERS: 'bad' })).toThrow()
})

it('完整计划仍包含原有八个门禁且不重复', () => {
  const steps = [...TEST_LANES.flat(), FINAL_TEST_STEP]
  expect(new Set(steps).size).toBe(8)
  expect(steps).toEqual(expect.arrayContaining([
    'test:backend', 'test:editor:gate', 'test:runtime:gate', 'test:contracts',
    'test:render-contracts', 'test:renderer', 'test:python-workspace', 'test:e2e:all',
  ]))
})

it('非法并发预算在停服预检之前拒绝', async () => {
  vi.stubEnv('TEST_ALL_CONCURRENCY', '3')
  const preflight = vi.fn()
  const log = vi.spyOn(console, 'log').mockImplementation(() => {})
  try {
    await expect(fullTest(['--stop-services'], { preflight })).rejects.toThrow('TEST_ALL_CONCURRENCY')
    expect(preflight).not.toHaveBeenCalled()
  } finally {
    vi.unstubAllEnvs()
    log.mockRestore()
  }
})

it('通道内顺序固定，E2E 等待两个通道完成', async () => {
  const first = deferred()
  const second = deferred()
  const started: string[] = []
  const run = vi.fn(async (step: string) => {
    started.push(step)
    if (step === 'python') return first.promise
    if (step === 'frontend') return second.promise
    return 0
  })
  const pending = runTestPlan({ run, lanes: [['python', 'renderer'], ['frontend', 'contracts']], finalStep: 'e2e' })
  expect(started).toEqual(['python', 'frontend'])
  first.resolve(0)
  await vi.waitFor(() => expect(started).toContain('renderer'))
  expect(started).not.toContain('e2e')
  second.resolve(0)
  const report = await pending
  expect(started).toEqual(['python', 'frontend', 'renderer', 'contracts', 'e2e'])
  expect(report.code).toBe(0)
})

it('失败后等待已启动阶段，停止派发两侧剩余阶段与 E2E，保留退出码', async () => {
  const active = deferred()
  const run = vi.fn((step: string) => step === 'backend' ? Promise.resolve(7) : active.promise)
  const pending = runTestPlan({ run, lanes: [['backend', 'renderer'], ['editor', 'runtime']], finalStep: 'e2e' })
  await vi.waitFor(() => expect(run).toHaveBeenCalledTimes(2))
  active.resolve(0)
  const report = await pending
  expect(report.code).toBe(7)
  expect(report.results.map(result => result.step)).toEqual(['backend', 'editor'])
  expect(run).toHaveBeenCalledTimes(2)
})

it('串行模式不重叠，执行异常会阻止 E2E', async () => {
  const run = vi.fn(async (step: string) => { if (step === 'c') throw new Error('spawn failed'); return 0 })
  const error = vi.spyOn(console, 'error').mockImplementation(() => {})
  try {
    const report = await runTestPlan({ run, concurrency: 1, lanes: [['a', 'b'], ['c', 'd']], finalStep: 'e2e' })
    expect(run.mock.calls.flat()).toEqual(['a', 'b', 'c'])
    expect(report.code).toBe(1)
  } finally { error.mockRestore() }
})
