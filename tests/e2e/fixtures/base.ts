/**
 * 文件功能：扩展 Playwright 基础 fixture，在失败时附加 API 摘要与 AI run 只读诊断。
 */
import { execFile } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { promisify } from 'node:util'

import { expect, test as playwrightTest, type Request, type Response } from '@playwright/test'

const execFileAsync = promisify(execFile)
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
const defaultE2eDatabaseUrl = 'postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/web_presentation_e2e'

/** 诊断优先沿用显式 E2E URL；仅当通用 URL 明确指向 E2E 库时才复用。 */
function resolveE2eDatabaseUrl(): string {
  if (process.env.E2E_DATABASE_URL) return process.env.E2E_DATABASE_URL
  if (process.env.DATABASE_URL?.toLowerCase().includes('_e2e')) return process.env.DATABASE_URL
  return defaultE2eDatabaseUrl
}

interface ApiFailure {
  method: string
  path: string
  status?: number
  error?: string
  response?: string
}

interface DiagnosticsState {
  apiFailures: ApiFailure[]
  runIds: Set<string>
  sessionIds: Set<string>
  pending: Set<Promise<void>>
}

/** 仅保留路径，避免查询参数中的临时令牌进入诊断附件。 */
function safePath(rawUrl: string): string {
  try {
    return new URL(rawUrl).pathname
  } catch {
    return '<invalid-url>'
  }
}

/** 截断并脱敏 Backend 错误响应，不保存认证信息或完整用户内容。 */
function sanitizeResponseBody(body: string): string {
  const truncated = body.slice(0, 4_000)
  return truncated
    .replace(/("(?:api[_-]?key|password|secret|token|authorization|cookie)"\s*:\s*)"[^"]*"/gi, '$1"<redacted>"')
    .replace(/(bearer\s+)[a-z0-9._~+/=-]+/gi, '$1<redacted>')
}

/** 从 AI run 请求中提取不可变标识，不保留提示词正文。 */
function captureAiIdentifiers(request: Request, state: DiagnosticsState): void {
  const pathName = safePath(request.url())
  const match = pathName.match(/\/api\/ai\/sessions\/([^/]+)\/runs\/stream$/)
  if (!match || request.method() !== 'POST') {
    return
  }
  state.sessionIds.add(decodeURIComponent(match[1]))
  try {
    const payload = request.postDataJSON() as { run_id?: unknown }
    const runId = String(payload.run_id || '').trim()
    if (runId) state.runIds.add(runId)
  } catch {
    // 请求体异常由真实 API 与页面断言负责；诊断 fixture 不改变测试结果。
  }
}

/** 异步读取失败 API 响应摘要，并确保 teardown 等待读取任务完成。 */
function captureApiResponse(response: Response, state: DiagnosticsState): void {
  if (!safePath(response.url()).startsWith('/api/') || response.status() < 400) {
    return
  }
  let task: Promise<void>
  task = response.text()
    .then(body => {
      state.apiFailures.push({
        method: response.request().method(),
        path: safePath(response.url()),
        status: response.status(),
        response: sanitizeResponseBody(body),
      })
    })
    .catch(error => {
      state.apiFailures.push({
        method: response.request().method(),
        path: safePath(response.url()),
        status: response.status(),
        error: String(error),
      })
    })
    .finally(() => state.pending.delete(task))
  state.pending.add(task)
}

/** 调用仓库只读诊断 CLI；失败时返回错误文本，不覆盖原测试失败。 */
async function diagnoseAiRun(runId: string): Promise<string> {
  try {
    const { stdout, stderr } = await execFileAsync(
      'uv',
      ['run', '--project', 'backend', 'python', '-m', 'app.scripts.diagnose_ai_run', '--run-id', runId, '--format', 'summary'],
      {
        cwd: repoRoot,
        env: {
          ...process.env,
          DATABASE_URL: resolveE2eDatabaseUrl(),
        },
        timeout: 30_000,
        maxBuffer: 1_000_000,
        windowsHide: true,
      },
    )
    return [stdout, stderr].filter(Boolean).join('\n').trim()
  } catch (error) {
    return `AI run ${runId} 诊断失败：${String(error)}`
  }
}

/** 自动诊断 fixture：所有 project 生效，仅在用例失败时生成附件。 */
export const test = playwrightTest.extend<{ e2eDiagnostics: void }>({
  e2eDiagnostics: [async ({ page }, use, testInfo) => {
    const state: DiagnosticsState = {
      apiFailures: [],
      runIds: new Set(),
      sessionIds: new Set(),
      pending: new Set(),
    }
    const onRequest = (request: Request) => captureAiIdentifiers(request, state)
    const onRequestFailed = (request: Request) => {
      if (!safePath(request.url()).startsWith('/api/')) return
      state.apiFailures.push({
        method: request.method(),
        path: safePath(request.url()),
        error: request.failure()?.errorText || 'request failed',
      })
    }
    const onResponse = (response: Response) => captureApiResponse(response, state)
    page.on('request', onRequest)
    page.on('requestfailed', onRequestFailed)
    page.on('response', onResponse)

    await use()

    page.off('request', onRequest)
    page.off('requestfailed', onRequestFailed)
    page.off('response', onResponse)
    await Promise.allSettled([...state.pending])
    if (testInfo.status === testInfo.expectedStatus) return

    if (state.apiFailures.length) {
      await testInfo.attach('api-failure-summary', {
        contentType: 'application/json',
        body: JSON.stringify(state.apiFailures, null, 2),
      })
    }
    for (const runId of state.runIds) {
      await testInfo.attach(`ai-run-${runId}-diagnostics`, {
        contentType: 'text/plain',
        body: await diagnoseAiRun(runId),
      })
    }
    if (!state.runIds.size && state.sessionIds.size) {
      await testInfo.attach('ai-session-identifiers', {
        contentType: 'text/plain',
        body: [...state.sessionIds].join('\n'),
      })
    }
  }, { auto: true }],
})

export { expect } from '@playwright/test'
