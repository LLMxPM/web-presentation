/** 文件功能：复用已准备的独立 E2E 服务，运行页面校验附图与真实 CLI/AI 队列验收，不重置数据。 */
import { buildE2eBackendEnv } from './e2e-database-env.mjs'
import { runCommandSync } from './process-utils.mjs'

const env = buildE2eBackendEnv({ PAGE_MUTATION_CAPTURE_SCREENSHOT: 'true' })
process.exitCode = runCommandSync('uv', ['run', '--project', 'backend', 'python', 'scripts/testing/validation_screenshot_drill.py', ...process.argv.slice(2)], { env })
