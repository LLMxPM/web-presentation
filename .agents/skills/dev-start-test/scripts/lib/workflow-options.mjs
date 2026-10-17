/** 文件功能：解析开发测试包装器参数，并在任何停服或数据重置之前校验 E2E 自启环境。 */
const START_KEYS = ['BACKEND', 'EDITOR', 'RUNTIME', 'RENDERER'].map((key) => `TESTING_START_${key}`)

/** 解析共同的布尔开关；未知参数直接拒绝，避免拼写错误扩大操作范围。 */
export function parseWorkflowArgs(argv) {
  const options = { stopServices: false, startInfra: false, installBrowsers: false, dryRun: false, help: false }
  const flags = {
    '--stop-services': 'stopServices', '--start-infra': 'startInfra',
    '--install-browsers': 'installBrowsers', '--dry-run': 'dryRun', '--help': 'help', '-h': 'help',
  }
  for (const arg of argv) {
    if (!Object.hasOwn(flags, arg)) throw new Error(`未知参数：${arg}（使用 --help 查看用法）`)
    options[flags[arg]] = true
  }
  return options
}

/** 固定四项服务自启与 mock；冲突配置在任何副作用之前报错，不修改调用方环境。 */
export function buildPrepareEnv(systemEnv = process.env) {
  const env = { ...systemEnv }
  for (const key of START_KEYS) {
    const value = String(env[key] || '').trim()
    if (value && value.toLowerCase() !== 'true') {
      throw new Error(`${key}=${value} 与 E2E 自启冲突；请移除该变量或设为 true。`)
    }
    env[key] = 'true'
  }
  const mode = String(env.AI_TEST_MODE || '').trim()
  if (mode && mode !== 'mock') throw new Error('AI_TEST_MODE 必须为 mock；请先移除冲突配置。')
  const reuse = String(env.TESTING_REUSE_BACKEND || '').trim().toLowerCase()
  if (reuse && reuse !== 'false') {
    throw new Error('TESTING_REUSE_BACKEND 与 E2E 数据重置冲突；复用环境请直接运行 Playwright。')
  }
  delete env.TESTING_REUSE_BACKEND
  env.AI_TEST_MODE = 'mock'
  return env
}
