/** 文件功能：维护全量测试的资源分组、受控并发与失败后停止派发的规则。 */
import { availableParallelism } from 'node:os'

// 同一虚拟环境中的 Python 入口串行；前端编译与测试也只占一个通道。
export const TEST_LANES = [
  ['test:backend', 'test:render-contracts', 'test:renderer', 'test:python-workspace'],
  ['test:editor:gate', 'test:runtime:gate', 'test:contracts'],
]
export const FINAL_TEST_STEP = 'test:e2e:all'
export const TEST_PLAN_DESCRIPTION = TEST_LANES.map(lane => `(${lane.join(' → ')})`).join(' ∥ ') + ` → ${FINAL_TEST_STEP}`

/** 只允许一或两个通道；限制 Vitest worker，给 Python 和系统保留计算资源。 */
export function resolveTestBudget(env = process.env, cpuCount = availableParallelism()) {
  const concurrency = Number(env.TEST_ALL_CONCURRENCY || (cpuCount >= 4 ? 2 : 1))
  if (![1, 2].includes(concurrency)) throw new Error('TEST_ALL_CONCURRENCY 必须为 1 或 2')
  const workers = Number(env.VITEST_MAX_WORKERS || Math.max(1, Math.min(4, cpuCount - 1)))
  if (!Number.isSafeInteger(workers) || workers < 1) throw new Error('VITEST_MAX_WORKERS 必须为正整数')
  return { concurrency, workers }
}

/** 并发执行独立通道；失败后等待已启动阶段结束，跳过所有未启动阶段和 E2E。 */
export async function runTestPlan({ run, concurrency = 2, lanes = TEST_LANES, finalStep = FINAL_TEST_STEP }) {
  const results = []
  let failureCode = 0
  let nextLane = 0
  /** 每个通道保持顺序，并在每次派发前检查其它通道的失败。 */
  async function drainLanes() {
    while (!failureCode && nextLane < lanes.length) {
      const lane = lanes[nextLane++]
      for (const step of lane) {
        if (failureCode) break
        const started = Date.now()
        let code
        try {
          code = await run(step)
        } catch (error) {
          console.error(`[testing] ${step} 执行异常：${String(error)}`)
          code = 1
        }
        results.push({ step, code, durationMs: Date.now() - started })
        if (code !== 0) failureCode ||= code
      }
    }
  }
  await Promise.all(Array.from({ length: concurrency }, drainLanes))
  if (!failureCode && finalStep) {
    lanes = [[finalStep]]
    nextLane = 0
    await drainLanes()
  }
  return { code: failureCode, results }
}
