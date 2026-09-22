/**
 * 文件用途：验证 Runtime 构建 worker 的子进程隔离、错误识别与超时处理。
 */

import { mkdir, mkdtemp, readFile, rm, symlink, writeFile } from 'fs/promises'
import os from 'os'
import { join, resolve } from 'path'

import { describe, expect, it } from 'vitest'

import {
  RuntimeDiagnosticsWorker,
  createRuntimeDiagnosticsWorkerScript,
  createRuntimeBuildWorkerScript,
  isRuntimeBuildWorkerOomFailure,
  normalizeDiagnosticsWorkerTimeoutMs,
  normalizeWorkerMaxOldSpaceMb,
  normalizeWorkerTimeoutMs,
  runRuntimeViteBuildInWorker,
} from './runtime-build-worker'

describe('runtime build worker', () => {
  it('应生成包含 Vite 构建配置的 worker 脚本', () => {
    const source = createRuntimeBuildWorkerScript()

    expect(source).toContain("import { build as viteBuild } from 'vite'")
    expect(source).toContain('tailwindcss(resolve(tempRoot, "tailwind.config.js"))')
    expect(source).toContain('__RUNTIME_BACKEND_BUILD__')
    expect(source).toContain('input.mode === "diagnostics"')
  })

  it('应按默认值和显式值解析 worker 资源限制', () => {
    const originalMaxOldSpaceMb = process.env.RUNTIME_BUILD_WORKER_MAX_OLD_SPACE_MB
    const originalTimeoutMs = process.env.RUNTIME_BUILD_WORKER_TIMEOUT_MS
    const originalDiagnosticsTimeoutMs = process.env.RUNTIME_DIAGNOSTICS_WORKER_TIMEOUT_MS
    try {
      delete process.env.RUNTIME_BUILD_WORKER_MAX_OLD_SPACE_MB
      delete process.env.RUNTIME_BUILD_WORKER_TIMEOUT_MS
      delete process.env.RUNTIME_DIAGNOSTICS_WORKER_TIMEOUT_MS

      expect(normalizeWorkerMaxOldSpaceMb()).toBe(1024)
      expect(normalizeWorkerMaxOldSpaceMb(4096)).toBe(4096)
      expect(normalizeWorkerTimeoutMs()).toBe(600000)
      expect(normalizeDiagnosticsWorkerTimeoutMs()).toBe(120000)
      expect(normalizeWorkerTimeoutMs(1000)).toBe(1000)

      process.env.RUNTIME_BUILD_WORKER_MAX_OLD_SPACE_MB = '6144'
      process.env.RUNTIME_BUILD_WORKER_TIMEOUT_MS = '300000'
      expect(normalizeWorkerMaxOldSpaceMb()).toBe(6144)
      expect(normalizeWorkerTimeoutMs()).toBe(300000)
    } finally {
      restoreEnvValue('RUNTIME_BUILD_WORKER_MAX_OLD_SPACE_MB', originalMaxOldSpaceMb)
      restoreEnvValue('RUNTIME_BUILD_WORKER_TIMEOUT_MS', originalTimeoutMs)
      restoreEnvValue('RUNTIME_DIAGNOSTICS_WORKER_TIMEOUT_MS', originalDiagnosticsTimeoutMs)
    }
  })

  it('应识别 Node/V8 OOM 退出特征', () => {
    expect(isRuntimeBuildWorkerOomFailure('FATAL ERROR: JavaScript heap out of memory', null)).toBe(true)
    expect(isRuntimeBuildWorkerOomFailure('Ineffective mark-compacts near heap limit', null)).toBe(true)
    expect(isRuntimeBuildWorkerOomFailure('', 134)).toBe(true)
    expect(isRuntimeBuildWorkerOomFailure('normal failure', 1)).toBe(false)
  })

  it('worker 成功写出结果时应正常返回', async () => {
    const tempRoot = await createWorkerFixture()
    try {
      await expect(runRuntimeViteBuildInWorker({
        tempRoot,
        base: './',
        mode: 'diagnostics',
        workerScriptSource: createResultScript('{ success: true }'),
      })).resolves.toBeUndefined()
    } finally {
      await rm(tempRoot, { recursive: true, force: true })
    }
  })

  it('worker 写出 Vite 错误时应保留插件、文件与行列信息', async () => {
    const tempRoot = await createWorkerFixture()
    try {
      await expect(runRuntimeViteBuildInWorker({
        tempRoot,
        base: './',
        mode: 'diagnostics',
        workerScriptSource: createResultScript(`{
          success: false,
          error: {
            name: 'RollupError',
            message: '编译失败',
            plugin: 'vite:vue',
            code: 'PLUGIN_ERROR',
            id: 'src/views/Page.vue?vue&type=script',
            loc: { file: 'src/views/Page.vue', line: 2, column: 3 }
          }
        }`, 1),
      })).rejects.toMatchObject({
        name: 'RollupError',
        message: '编译失败',
        plugin: 'vite:vue',
        code: 'PLUGIN_ERROR',
        id: 'src/views/Page.vue?vue&type=script',
        loc: { file: 'src/views/Page.vue', line: 2, column: 3 },
      })
    } finally {
      await rm(tempRoot, { recursive: true, force: true })
    }
  })

  it('worker 非零退出且无结构化结果时应返回 worker failed 错误', async () => {
    const tempRoot = await createWorkerFixture()
    try {
      await expect(runRuntimeViteBuildInWorker({
        tempRoot,
        base: './',
        mode: 'project',
        outDir: join(tempRoot, 'dist'),
        workerScriptSource: 'process.exit(7)',
      })).rejects.toMatchObject({
        code: 'RUNTIME_BUILD_WORKER_FAILED',
        statusCode: 500,
      })
    } finally {
      await rm(tempRoot, { recursive: true, force: true })
    }
  })

  it('worker OOM stderr 应转为 OOM 错误码', async () => {
    const tempRoot = await createWorkerFixture()
    try {
      await expect(runRuntimeViteBuildInWorker({
        tempRoot,
        base: './',
        mode: 'diagnostics',
        workerScriptSource: [
          "console.error('FATAL ERROR: Ineffective mark-compacts near heap limit Allocation failed - JavaScript heap out of memory')",
          'process.exit(134)',
        ].join('\n'),
      })).rejects.toMatchObject({
        code: 'RUNTIME_BUILD_WORKER_OOM',
        statusCode: 500,
      })
    } finally {
      await rm(tempRoot, { recursive: true, force: true })
    }
  })

  it('worker 超时应终止并返回 timeout 错误码', async () => {
    const tempRoot = await createWorkerFixture()
    try {
      await expect(runRuntimeViteBuildInWorker({
        tempRoot,
        base: './',
        mode: 'diagnostics',
        timeoutMs: 20,
        workerScriptSource: 'setInterval(() => {}, 1000)',
      })).rejects.toMatchObject({
        code: 'RUNTIME_BUILD_WORKER_TIMEOUT',
        statusCode: 504,
      })
    } finally {
      await rm(tempRoot, { recursive: true, force: true })
    }
  })

  it('应生成通过 IPC 接收多次任务的长期诊断 worker 脚本', () => {
    const source = createRuntimeDiagnosticsWorkerScript()

    expect(source).toContain('process.on("message"')
    expect(source).toContain('process.send?.({ taskId: input.taskId, success: true')
    expect(source).toContain('plugins: [vue()]')
  })

  it('长期诊断 worker 应复用同一进程并在达到任务上限后轮换', async () => {
    const tempRoot = await createWorkerFixture()
    const pidLogPath = join(tempRoot, 'worker-pids.log').replace(/\\/g, '\\\\')
    const worker = new RuntimeDiagnosticsWorker({
      tempRoot,
      maxTasks: 2,
      timeoutMs: 1000,
      workerScriptSource: createPersistentResultScript(pidLogPath),
    })
    try {
      await worker.run()
      await worker.run()
      await worker.run()
      const pids = (await readFile(join(tempRoot, 'worker-pids.log'), 'utf-8')).trim().split('\n')

      expect(pids).toHaveLength(3)
      expect(pids[0]).toBe(pids[1])
      expect(pids[2]).not.toBe(pids[1])
    } finally {
      await worker.close()
      await rm(tempRoot, { recursive: true, force: true })
    }
  })

  it('长期诊断 worker 崩溃时应返回基础设施错误并可关闭', async () => {
    const tempRoot = await createWorkerFixture()
    const worker = new RuntimeDiagnosticsWorker({
      tempRoot,
      timeoutMs: 1000,
      workerScriptSource: 'process.on("message", () => process.exit(9))',
    })
    try {
      await expect(worker.run()).rejects.toMatchObject({
        code: 'RUNTIME_DIAGNOSTICS_WORKER_FAILED',
        statusCode: 500,
      })
    } finally {
      await worker.close()
      await rm(tempRoot, { recursive: true, force: true })
    }
  })

  it('关闭后的常驻 worker 不得重新启动 child', async () => {
    const tempRoot = await createWorkerFixture()
    const worker = new RuntimeDiagnosticsWorker({ tempRoot })
    try {
      await worker.close()
      await expect(worker.run()).rejects.toMatchObject({
        code: 'RUNTIME_DIAGNOSTICS_WORKER_CLOSED',
        statusCode: 503,
      })
    } finally {
      await worker.close()
      await rm(tempRoot, { recursive: true, force: true })
    }
  })

  it('常驻 worker 的 OOM 退出应保留可重试错误码', async () => {
    const tempRoot = await createWorkerFixture()
    const worker = new RuntimeDiagnosticsWorker({
      tempRoot,
      timeoutMs: 1000,
      workerScriptSource: [
        'process.on("message", () => {',
        '  process.stderr.write("FATAL ERROR: JavaScript heap out of memory", () => process.exit(134))',
        '})',
      ].join('\n'),
    })
    try {
      await expect(worker.run()).rejects.toMatchObject({
        code: 'RUNTIME_BUILD_WORKER_OOM',
        statusCode: 500,
      })
    } finally {
      await worker.close()
      await rm(tempRoot, { recursive: true, force: true })
    }
  })

  it('常驻 worker 超时后应等待旧 child 退出，再允许下一次任务启动', async () => {
    const tempRoot = await createWorkerFixture()
    const lifecycleLogPath = join(tempRoot, 'worker-lifecycle.log').replace(/\\/g, '\\\\')
    const invocationPath = join(tempRoot, 'worker-invocation.txt').replace(/\\/g, '\\\\')
    const worker = new RuntimeDiagnosticsWorker({
      tempRoot,
      timeoutMs: 200,
      workerScriptSource: createTimeoutRecoveryScript(lifecycleLogPath, invocationPath),
    })
    try {
      await expect(worker.run()).rejects.toMatchObject({
        code: 'RUNTIME_BUILD_WORKER_TIMEOUT',
        statusCode: 504,
      })
      await expect(worker.run()).resolves.toBeUndefined()

      if (process.platform !== 'win32') {
        const lifecycle = (await readFile(join(tempRoot, 'worker-lifecycle.log'), 'utf-8'))
          .trim()
          .split('\n')
          .map(line => line.split(':')[0])
        expect(lifecycle).toEqual(['start', 'term', 'exit', 'start'])
      }
    } finally {
      await worker.close()
      await rm(tempRoot, { recursive: true, force: true })
    }
  })

  it('生成的长期 worker 应能连续执行真实 Vite 诊断构建', async () => {
    const tempRoot = await createWorkerFixture()
    await createMinimalViteFixture(tempRoot)
    const worker = new RuntimeDiagnosticsWorker({
      tempRoot,
      timeoutMs: 30000,
      maxTasks: 5,
    })
    try {
      await expect(worker.run()).resolves.toBeUndefined()
      await expect(worker.run()).resolves.toBeUndefined()
    } finally {
      await worker.close()
      await rm(tempRoot, { recursive: true, force: true })
    }
  })
})

/**
 * 创建 worker 测试临时目录。
 * @returns 临时目录
 */
async function createWorkerFixture(): Promise<string> {
  return mkdtemp(join(os.tmpdir(), 'runtime-build-worker-test-'))
}

/**
 * 创建写出结构化结果的测试 worker 脚本。
 * @param resultExpression 结果对象表达式
 * @param exitCode 退出码
 * @returns ESM 脚本文本
 */
function createResultScript(resultExpression: string, exitCode = 0): string {
  return [
    "import { writeFile } from 'node:fs/promises'",
    `await writeFile(process.argv[3], JSON.stringify(${resultExpression}), 'utf-8')`,
    `process.exitCode = ${exitCode}`,
    '',
  ].join('\n')
}

/**
 * 创建记录 PID 并成功回复 IPC 的长期 worker 测试脚本。
 */
function createPersistentResultScript(pidLogPath: string): string {
  return [
    "import { appendFile } from 'node:fs/promises'",
    'process.on("message", async input => {',
    `  await appendFile('${pidLogPath}', String(process.pid) + '\\n', 'utf-8')`,
    '  process.send?.({ taskId: input.taskId, success: true, rssBytes: 1 })',
    '})',
    '',
  ].join('\n')
}

/**
 * 创建首个任务超时、收到终止信号后延迟退出、第二个任务成功的 IPC worker。
 */
function createTimeoutRecoveryScript(lifecycleLogPath: string, invocationPath: string): string {
  return [
    "import { appendFileSync, existsSync, readFileSync, writeFileSync } from 'node:fs'",
    'function nextInvocation() {',
    `  const path = '${invocationPath}'`,
    '  const current = existsSync(path) ? Number(readFileSync(path, "utf-8")) || 0 : 0',
    '  const next = current + 1',
    '  writeFileSync(path, String(next), "utf-8")',
    '  return next',
    '}',
    'process.on("SIGTERM", () => {',
    `  appendFileSync('${lifecycleLogPath}', 'term:' + process.pid + '\\n', 'utf-8')`,
    '  setTimeout(() => {',
    `    appendFileSync('${lifecycleLogPath}', 'exit:' + process.pid + '\\n', 'utf-8')`,
    '    process.exit(0)',
    '  }, 80)',
    '})',
    'process.on("message", input => {',
    '  const invocation = nextInvocation()',
    `  appendFileSync('${lifecycleLogPath}', 'start:' + process.pid + '\\n', 'utf-8')`,
    '  if (invocation > 1) {',
    '    process.send?.({ taskId: input.taskId, success: true, rssBytes: 1 })',
    '  }',
    '})',
    '',
  ].join('\n')
}

/**
 * 创建可由真实 Vite 构建的最小工作区，并复用当前项目依赖目录。
 */
async function createMinimalViteFixture(tempRoot: string): Promise<void> {
  await mkdir(resolve(tempRoot, 'src'), { recursive: true })
  await writeFile(
    resolve(tempRoot, 'index.html'),
    '<div id="app"></div><script type="module" src="/src/main.js"></script>',
    'utf-8',
  )
  await writeFile(resolve(tempRoot, 'src/main.js'), 'console.log("runtime worker fixture")\n', 'utf-8')
  await writeFile(resolve(tempRoot, 'tailwind.config.js'), 'export default { content: [], theme: {}, plugins: [] }\n', 'utf-8')
  await symlink(
    resolve(process.cwd(), 'node_modules'),
    resolve(tempRoot, 'node_modules'),
    process.platform === 'win32' ? 'junction' : 'dir',
  )
}

/**
 * 恢复测试期间修改过的环境变量。
 * @param key 环境变量名
 * @param value 原始值
 */
function restoreEnvValue(key: string, value: string | undefined): void {
  if (value === undefined) {
    delete process.env[key]
    return
  }
  process.env[key] = value
}
