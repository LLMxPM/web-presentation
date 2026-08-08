/**
 * 文件功能：本地全量测试编排入口。先校验端口与 E2E 依赖，再注入测试环境变量，最后按序执行各阶段。
 *
 * 依据 docs/developer/testing/strategy.md 的 test:all 语义：
 * - 全量 = Backend 全部 marker + Editor gate + Runtime gate + 根仓 contracts + 全部 E2E project；
 * - 脚本自动设置 TESTING_START_* 与 AI_TEST_MODE=mock 并自启服务，无需手动设置环境变量；
 * - 端口被占用时立即失败并给出提示，不进入任何测试阶段；
 * - 任一阶段失败即中止后续阶段，退出码透传。
 */
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

import { runCommandSync } from './process-utils.mjs'

const TEST_STEPS = ['test:backend', 'test:editor:gate', 'test:runtime:gate', 'test:contracts', 'test:e2e:all']

function main() {
  const scriptsDir = path.dirname(fileURLToPath(import.meta.url))
  const portCheck = runCommandSync(process.execPath, [path.join(scriptsDir, 'assert-ports-free.mjs')])
  if (portCheck !== 0) {
    process.exit(portCheck)
  }

  process.env.TESTING_START_BACKEND ||= 'true'
  process.env.TESTING_START_EDITOR ||= 'true'
  process.env.TESTING_START_RUNTIME ||= 'true'
  process.env.AI_TEST_MODE ||= 'mock'

  for (const step of TEST_STEPS) {
    const code = runCommandSync('pnpm', ['run', step])
    if (code !== 0) {
      console.error(`[testing] 全量测试在 ${step} 失败（exit ${code}），后续步骤已跳过。`)
      process.exit(code)
    }
  }
  console.log('[testing] 全量测试全部通过')
}

main()
