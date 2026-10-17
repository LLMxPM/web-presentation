/**
 * 文件功能：全量测试编排入口。先做 E2E 依赖与 IPv4/IPv6 端口预检，可选停服/装浏览器，再执行 pnpm run test:all。
 *
 * 依据 scripts/testing/run-full-tests.mjs：
 * - test:all = backend + editor gate + runtime gate + contracts + render-contracts + renderer + python-workspace + e2e:all；
 * - test:all 自动注入 TESTING_START_* 与 AI_TEST_MODE=mock，要求端口空闲，并在 E2E 阶段重置/播种 _e2e 数据；
 * - 任一阶段失败即中止；本脚本只做预检与收尾提示，不复制测试编排。
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

const TEST_ALL_STEPS = [
  'test:backend',
  'test:editor:gate',
  'test:runtime:gate',
  'test:contracts',
  'test:render-contracts',
  'test:renderer',
  'test:python-workspace',
  'test:e2e:all',
]

if (import.meta.url === pathToFileURL(process.argv[1] || '').href) {
  main().catch((error) => {
    console.error(`[full-test] 失败：${error instanceof Error ? error.message : String(error)}`)
    process.exitCode = 1
  })
}

/** 预检依赖与端口，必要时停服/装浏览器，然后执行仓库全量测试入口。 */
export async function main(argv = process.argv.slice(2), { preflight = preflightE2e, run = runCommandSync, status = readStatus } = {}) {
  const options = parseWorkflowArgs(argv)
  if (options.help) {
    printHelp()
    return
  }

  console.log(`[full-test] 仓库：${REPO_ROOT}${options.dryRun ? '（dry-run）' : ''}`)
  const prepareEnv = buildPrepareEnv()
  await preflight(options, { logPrefix: '[full-test]' })

  if (options.dryRun) {
    console.log('[full-test] dry-run 完成：未停止服务、未安装浏览器、未运行测试')
    console.log('[full-test] 将执行：pnpm run test:all')
    console.log(`  阶段：${TEST_ALL_STEPS.join(' → ')}`)
    console.log('  注意：test:all 的 E2E 阶段会重置并播种 _e2e 数据，并在结束后保留 E2E 服务。')
    return
  }

  console.log('[full-test] 即将执行 pnpm run test:all')
  console.log(`  阶段：${TEST_ALL_STEPS.join(' → ')}`)
  console.log('  注意：E2E 阶段会重置并播种 _e2e 数据；任一阶段失败会中止后续阶段。')
  const code = run('pnpm', ['run', 'test:all'], { cwd: REPO_ROOT, env: prepareEnv })
  printResult(code, status)
  if (code !== 0) process.exitCode = code
}

/** 输出结果与收尾提示；状态读取失败不覆盖测试退出码。 */
function printResult(code, read) {
  if (code === 0) {
    console.log('[full-test] 全量测试全部通过')
  } else {
    console.log(`[full-test] 全量测试失败（退出码 ${code}）；请查看失败阶段与 test-results/e2e/ 产物。`)
  }

  let status
  try {
    status = read()
  } catch (error) {
    console.log(`[full-test] 无法读取收尾状态：${error instanceof Error ? error.message : String(error)}`)
    return
  }

  const services = status.services || {}
  const lines = ['backend', 'editor', 'runtime', 'renderer'].map((key) => {
    const service = services[key]
    return `${key}=${service?.status || 'unknown'}`
  })
  console.log(`[full-test] 当前服务：${lines.join(', ')}`)

  const readiness = services.backend?.e2eReadiness
  if (readiness && typeof readiness === 'object' && readiness.test_mode) {
    console.log(
      `[full-test] E2E 指纹：test_mode=${readiness.test_mode}, database=${readiness.database_profile}, ` +
        `redis=${readiness.redis_profile}, seed_version=${readiness.seed_version}, ` +
        `smoke_data_ready=${readiness.smoke_data_ready}`,
    )
  }

  if (['backend', 'editor', 'runtime', 'renderer'].some((key) => services[key]?.status === 'up')) {
    console.log('[full-test] 测试服务仍在运行；恢复开发环境先执行 stop.mjs，再按 SKILL.md 2.3 启动。')
  }
}

/** 打印用法与执行边界。 */
function printHelp() {
  console.log(`用法：node full-test.mjs [选项]

执行主仓全量测试 pnpm run test:all；默认会运行测试并在 E2E 阶段重置数据。仅 --dry-run 只检查。

选项：
  --stop-services     停止占用端口的本仓服务（调用 stop.mjs）
  --start-infra       本机 E2E 依赖不可达时启动 compose.infra.yml
  --install-browsers  安装 Node 与 Renderer 的 Playwright Chromium
  --dry-run           只检查并输出计划，不停止、不安装、不运行测试
  -h, --help          显示帮助

test:all 阶段：
  ${TEST_ALL_STEPS.join(' → ')}

注意：
  - test:all 自动设置 TESTING_START_* 与 AI_TEST_MODE=mock，不需要手工注入。
  - E2E 阶段会重置并播种 _e2e 数据，并在结束后保留 E2E 服务。
  - test:all 不包含 repository、docker-context、compose-images、gateway、cli-skill、generated、
    pg-claim、runtime-state-parity、lite drill 与 test:render-e2e，需按改动补跑。
  - 全量测试耗时较长，请使用足够的命令超时；不要把 test:all 与其它测试并行执行。`)
}
