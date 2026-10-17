/**
 * 文件功能：准备主仓 E2E 测试环境，按依赖检查、端口检查、可选停服/装浏览器、执行仓库 prepare、指纹校验的顺序编排。
 *
 * 依据 SKILL.md 第 4 节与 docs/developer/testing/strategy.md：
 * - 端口检查同时覆盖 127.0.0.1 与 ::1，避免 Vite 只绑 ::1 时被误判为空闲；
 * - 不自动杀进程：只有显式 --stop-services 才调用 stop.mjs 停止占用端口的本仓服务；
 * - prepare 会重置并播种 E2E 数据库，TESTING_REUSE_BACKEND 不能与数据重置混用；
 * - 依赖按 E2E_DATABASE_URL/E2E_REDIS_URL（默认本机 _e2e 库与 Redis DB 15）探测；仅本机 5432/6379 不可达且显式 --start-infra 时启动 compose；
 * - 结束后校验 Backend E2E 指纹与 Editor/Runtime/Renderer 状态，失败即退出 1。
 */
import process from 'node:process'
import { pathToFileURL } from 'node:url'

import { runCommandSync } from '../../../../scripts/testing/process-utils.mjs'
import {
  readStatus,
  REPO_ROOT,
} from './lib/e2e-env.mjs'
import { preflightE2e } from './lib/e2e-preflight.mjs'
import { buildPrepareEnv, parseWorkflowArgs } from './lib/workflow-options.mjs'

if (import.meta.url === pathToFileURL(process.argv[1] || '').href) {
  main().catch((error) => {
    console.error(`[prepare-e2e] 失败：${error instanceof Error ? error.message : String(error)}`)
    process.exitCode = 1
  })
}

/** 按检查 → 停服 → 可选安装 → prepare → 指纹校验的顺序准备 E2E 环境。 */
export async function main(argv = process.argv.slice(2), { preflight = preflightE2e, run = runCommandSync, status = readStatus } = {}) {
  const options = parseWorkflowArgs(argv)
  if (options.help) {
    printHelp()
    return
  }

  console.log(`[prepare-e2e] 仓库：${REPO_ROOT}${options.dryRun ? '（dry-run）' : ''}`)
  const prepareEnv = buildPrepareEnv()
  await preflight(options, { logPrefix: '[prepare-e2e]' })

  if (options.dryRun) {
    console.log('[prepare-e2e] dry-run 完成：未停止服务、未安装浏览器、未启动依赖、未重置数据')
    console.log('[prepare-e2e] 实际执行：node .agents/skills/dev-start-test/scripts/prepare-e2e.mjs --stop-services')
    return
  }

  console.log('[prepare-e2e] 重置并播种 E2E 数据，然后启动/确认 E2E 服务...')
  const prepareCode = run('pnpm', ['run', 'test:e2e:prepare'], {
    env: prepareEnv,
    cwd: REPO_ROOT,
  })
  if (prepareCode !== 0) throw new Error(`pnpm run test:e2e:prepare 退出码 ${prepareCode}`)

  console.log('[prepare-e2e] 校验 E2E 指纹与服务状态...')
  const report = status()
  const problems = validateE2eStatus(report)
  if (problems.length > 0) {
    throw new Error(`E2E 环境校验失败：${problems.join('；')}`)
  }

  printReady(report)
}

/** 校验 Backend 指纹与其余服务就绪状态。 */
function validateE2eStatus(status) {
  const problems = []
  const readiness = status.services?.backend?.e2eReadiness

  if (status.services?.backend?.status !== 'up') problems.push('Backend 未就绪')
  if (!readiness || typeof readiness !== 'object') {
    problems.push('Backend 未返回 E2E 就绪指纹')
    return problems
  }
  if (readiness.test_mode !== 'mock') problems.push(`test_mode=${readiness.test_mode}（期望 mock）`)
  if (readiness.database_profile !== 'e2e') problems.push(`database_profile=${readiness.database_profile}（期望 e2e）`)
  if (readiness.redis_profile !== 'e2e') problems.push(`redis_profile=${readiness.redis_profile}（期望 e2e）`)
  if (typeof readiness.seed_version !== 'number') problems.push('seed_version 缺失')
  if (readiness.smoke_data_ready !== true) problems.push('smoke_data_ready 不是 true')

  for (const key of ['editor', 'runtime', 'renderer']) {
    if (status.services?.[key]?.status !== 'up') problems.push(`${key} 未就绪`)
  }
  if (status.services?.runtime?.ready !== true) problems.push('Runtime build worker 未就绪')
  return problems
}

/** 输出 E2E 就绪摘要与下一步命令。 */
function printReady(status) {
  const readiness = status.services.backend.e2eReadiness
  console.log('[prepare-e2e] E2E 环境就绪')
  console.log(
    `  Backend: ${status.services.backend.url}（test_mode=${readiness.test_mode}, ` +
      `database=${readiness.database_profile}, redis=${readiness.redis_profile}, ` +
      `seed_version=${readiness.seed_version}, smoke_data_ready=${readiness.smoke_data_ready}）`,
  )
  console.log(
    `  Editor: ${status.services.editor.url}  Runtime: ${status.services.runtime.url}  ` +
      `Renderer: ${status.services.renderer.url}`,
  )
  console.log('  下一步：pnpm run test:e2e:run（auth + smoke）')
  console.log('  全部 project：pnpm exec playwright test --config tests/config/playwright.config.ts')
  console.log(
    '  注意：当前运行的是 E2E 服务（AI_TEST_MODE=mock + _e2e 数据库）；' +
      '恢复开发环境请先执行 stop.mjs，再按 SKILL.md 2.3 启动。',
  )
}

/** 打印用法与执行边界。 */
function printHelp() {
  console.log(`用法：node prepare-e2e.mjs [选项]

准备主仓 E2E 环境；默认会重置/播种 E2E 数据并启动服务，端口占用时拒绝。仅 --dry-run 只检查。

选项：
  --stop-services     停止占用端口的本仓开发服务（调用 stop.mjs）
  --start-infra       依赖不可达且指向本机 5432/6379 时启动 compose.infra.yml
  --install-browsers  安装 Node 与 Renderer 的 Playwright Chromium
  --dry-run           只检查并输出计划，不停止、不安装、不重置数据
  -h, --help          显示帮助

执行顺序：
  1. 检查 E2E_DATABASE_URL/E2E_REDIS_URL（未设置时为本机 _e2e 库与 Redis DB 15）；
  2. 检查 8000/5173/7373/7400 的 IPv4 与 IPv6 监听；
  3. 可选停止本仓服务、安装浏览器；
  4. 执行 pnpm run test:e2e:prepare（重置并播种 _e2e 数据、启动 E2E 服务）；
  5. 校验 Backend E2E 指纹与 Editor/Runtime/Renderer 状态。

注意：TESTING_REUSE_BACKEND=true、非 mock 模式或禁用自启的配置会在停服/重置前被拒绝。`)
}
