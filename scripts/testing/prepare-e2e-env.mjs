/**
 * 文件功能：E2E 环境准备编排入口。未显式设置 TESTING_* 时自动校验端口并注入自启环境变量，再重置/播种数据并确认服务。
 *
 * 依据 docs/developer/testing/strategy.md 的 test:e2e:prepare 语义：
 * - 未设置任何 TESTING_START_* 或 TESTING_REUSE_BACKEND 时进入自启模式：校验 8000/5173/7373 空闲与本地 E2E 依赖，
 *   注入 TESTING_START_*=true 与 AI_TEST_MODE=mock，由脚本启动服务；端口被占用时立即报错并给出提示；
 * - 已设置任一 TESTING_START_* 或 TESTING_REUSE_BACKEND 时视为用户显式控制，跳过端口校验，直接复用或按变量启动；
 * - 数据重置与 smoke 播种通过 backend 脚本在 E2E 数据库上执行，不触碰开发库。
 */
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

import { runCommandSync } from './process-utils.mjs'

const SELF_START_KEYS = ['TESTING_START_BACKEND', 'TESTING_START_EDITOR', 'TESTING_START_RUNTIME', 'TESTING_REUSE_BACKEND']

function main() {
  const scriptsDir = path.dirname(fileURLToPath(import.meta.url))
  const userControlled = SELF_START_KEYS.some((key) => String(process.env[key] || '').trim() !== '')

  if (!userControlled) {
    const portCheck = runCommandSync(process.execPath, [path.join(scriptsDir, 'assert-ports-free.mjs')])
    if (portCheck !== 0) {
      process.exit(portCheck)
    }
    process.env.TESTING_START_BACKEND ||= 'true'
    process.env.TESTING_START_EDITOR ||= 'true'
    process.env.TESTING_START_RUNTIME ||= 'true'
    process.env.AI_TEST_MODE ||= 'mock'
  }

  for (const script of ['reset-test-data.mjs', 'seed-smoke-data.mjs', 'ensure-services.mjs']) {
    const code = runCommandSync(process.execPath, [path.join(scriptsDir, script)])
    if (code !== 0) {
      process.exit(code)
    }
  }
  console.log('[testing] E2E 环境已就绪')
}

main()
