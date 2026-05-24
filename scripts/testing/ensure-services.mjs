/**
 * 文件功能：检测或启动 backend/editor/runtime 服务，并等待平台级测试所需端口可用。
 */
import { spawnPersistentBackground, waitForHttpReady } from './process-utils.mjs'
import { resolveServiceUrls } from './service-env.mjs'
import { buildE2eBackendEnv } from './e2e-database-env.mjs'
import path from 'node:path'

const urls = resolveServiceUrls()

async function main() {
  const shouldStartBackend = String(process.env.TESTING_START_BACKEND || '').toLowerCase() === 'true'
  const shouldStartEditor = String(process.env.TESTING_START_EDITOR || '').toLowerCase() === 'true'
  const shouldStartRuntime = String(process.env.TESTING_START_RUNTIME || '').toLowerCase() === 'true'
  const shouldReuseBackend = String(process.env.TESTING_REUSE_BACKEND || '').toLowerCase() === 'true'

  await ensureServiceReady({
    label: 'backend',
    url: urls.backend,
    shouldStart: shouldStartBackend,
    allowReuse: shouldReuseBackend || !shouldStartBackend,
    start: () =>
      spawnPersistentBackground('uv', ['run', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000'], {
        cwd: path.join(process.cwd(), 'backend'),
        env: buildE2eBackendEnv({
          AI_TEST_MODE: process.env.AI_TEST_MODE || 'mock',
        }),
      }),
  })
  await ensureServiceReady({
    label: 'editor',
    url: urls.editor,
    shouldStart: shouldStartEditor,
    start: () =>
      spawnPersistentBackground('pnpm', ['--dir', 'editor', 'dev', '--host', '127.0.0.1', '--port', '5173'], {
        cwd: process.cwd(),
        env: process.env,
      }),
  })
  await ensureServiceReady({
    label: 'runtime',
    url: urls.runtime,
    shouldStart: shouldStartRuntime,
    start: () =>
      spawnPersistentBackground('pnpm', ['--dir', 'runtime', 'dev', '--host', '127.0.0.1', '--port', '7373'], {
        cwd: process.cwd(),
        env: process.env,
      }),
  })
  console.log('[testing] backend/editor/runtime are ready')
}

async function ensureServiceReady({ label, url, shouldStart, allowReuse = true, start }) {
  try {
    await waitForHttpReady(url, { timeoutMs: 4_000, intervalMs: 1_000 })
    if (!allowReuse) {
      throw new Error(`${label} is already reachable at ${url}. Refusing to reuse it unless TESTING_REUSE_BACKEND=true.`)
    }
    console.log(`[testing] reuse running ${label}: ${url}`)
    return
  } catch (error) {
    if (!allowReuse && error instanceof Error && error.message.includes('Refusing to reuse')) {
      throw error
    }
    if (!shouldStart) {
      throw new Error(`${label} is not reachable at ${url}. Set TESTING_START_${label.toUpperCase()}=true to start it automatically.`)
    }
  }

  console.log(`[testing] starting ${label}: ${url}`)
  start()
  await waitForHttpReady(url)
}

main().catch((error) => {
  console.error('[testing] failed to ensure services', error)
  process.exitCode = 1
})
