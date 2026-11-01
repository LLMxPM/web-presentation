/**
 * 文件功能：同步一次 Python workspace，受控并行执行独立门禁，最后单独准备并运行 E2E，记录逐阶段耗时。
 */
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

import { runCommandSync } from './process-utils.mjs'
import { FINAL_TEST_STEP, resolveTestBudget, runTestPlan, TEST_LANES } from './full-test-plan.mjs'

const repoRoot = fileURLToPath(new URL('../../', import.meta.url))
const reportDir = path.join(repoRoot, 'test-results/full')

/** 执行一个阶段并将完整日志写入独立文件，避免并发输出混杂；失败时打印末尾诊断。 */
function runStage(step, env) {
  const logPath = path.join(reportDir, `${step.replaceAll(':', '-')}.log`)
  const fd = fs.openSync(logPath, 'w')
  console.log(`[testing] 开始 ${step}；日志：${logPath}`)
  const started = Date.now()
  return new Promise(resolve => {
    const child = spawn('pnpm', ['run', step], {
      cwd: repoRoot, env, shell: process.platform === 'win32', windowsHide: true,
      stdio: ['inherit', fd, fd],
    })
    let spawnError
    child.on('error', error => { spawnError = error })
    child.on('close', code => {
      fs.closeSync(fd)
      const exitCode = code ?? 1
      console.log(`[testing] ${step} ${exitCode === 0 ? '通过' : '失败'}（${((Date.now() - started) / 1000).toFixed(1)}s）`)
      if (spawnError) console.error(spawnError.message)
      if (exitCode !== 0) console.error(fs.readFileSync(logPath, 'utf8').split(/\r?\n/).slice(-70).join('\n'))
      resolve(exitCode)
    })
  })
}

/** 完成预检后启动受控并发；不重复同步/裁剪共享虚拟环境，E2E 不与编译或单测争用资源。 */
async function main() {
  const started = Date.now()
  const budget = resolveTestBudget()
  const portCheck = runCommandSync(process.execPath, [path.join(repoRoot, 'scripts/dev/assert-ports-free.mjs')])
  if (portCheck !== 0) return portCheck
  const syncCode = runCommandSync('uv', ['sync', '--all-packages', '--all-groups', '--all-extras', '--locked'], { cwd: repoRoot })
  if (syncCode !== 0) return syncCode
  const env = {
    ...process.env, UV_NO_SYNC: 'true', VITEST_MAX_WORKERS: String(budget.workers),
    AI_TEST_MODE: process.env.AI_TEST_MODE || 'mock',
  }
  for (const key of ['BACKEND', 'EDITOR', 'RUNTIME', 'RENDERER']) env[`TESTING_START_${key}`] ||= 'true'
  fs.mkdirSync(reportDir, { recursive: true })
  console.log(`[testing] 并发通道 ${budget.concurrency}，Vitest workers ${budget.workers}；E2E 最后独立运行。`)
  const report = await runTestPlan({ run: step => runStage(step, env), concurrency: budget.concurrency })
  const completed = new Set(report.results.map(result => result.step))
  const skipped = [...TEST_LANES.flat(), FINAL_TEST_STEP].filter(step => !completed.has(step))
  fs.writeFileSync(path.join(reportDir, 'results.json'), JSON.stringify({
    ...report, budget, durationMs: Date.now() - started, skipped,
  }, null, 2))
  if (skipped.length) console.error(`[testing] 未运行：${skipped.join(', ')}`)
  console.log(`[testing] 全量测试${report.code === 0 ? '全部通过' : '失败'}；逐阶段结果：test-results/full/results.json`)
  return report.code
}

main().then(code => { process.exitCode = code }).catch(error => {
  console.error(`[testing] ${error.message}`)
  process.exitCode = 1
})
