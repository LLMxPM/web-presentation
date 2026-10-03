/**
 * 文件用途：验证 Runtime 诊断的基础设施错误语义、惰性工作区预热边界、
 * 归档流式上传与 build 角色启动/就绪判定。
 */

import { EventEmitter } from 'node:events'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { describe, expect, it, vi } from 'vitest'

import runtimeBuildRunner, {
  RuntimeBuildError,
  createBuildBackendClient,
  isRuntimeDiagnosticsInfrastructureError,
  readRuntimeBuildWorkerCredential,
} from './runtime-build-runner'
import {
  RuntimeBuildWorkerProcessError,
  RuntimeBuildWorkerViteError,
} from './runtime-build-worker'
import { collectRuntimeReadiness } from './runtime-health'
import {
  RuntimeDiagnosticsWorkspaceError,
  RuntimeDiagnosticsWorkspacePool,
} from './runtime-diagnostics-workspace-pool'
import { RuntimeTaskDeadlineError } from './runtime-task-deadline'
import { RuntimeViteTaskSchedulerError } from './runtime-vite-task-scheduler'

describe('runtime diagnostics infrastructure errors', () => {
  it('应把 worker、队列、网络与服务端错误保留为可重试基础设施错误', () => {
    expect(isRuntimeDiagnosticsInfrastructureError(new RuntimeBuildWorkerProcessError(
      504,
      'RUNTIME_BUILD_WORKER_TIMEOUT',
      'timeout',
    ))).toBe(true)
    expect(isRuntimeDiagnosticsInfrastructureError(new RuntimeViteTaskSchedulerError(
      429,
      'RUNTIME_VITE_QUEUE_TIMEOUT',
      'queue timeout',
    ))).toBe(true)
    expect(isRuntimeDiagnosticsInfrastructureError(new RuntimeBuildError(
      502,
      'RUNTIME_BACKEND_REQUEST_FAILED',
      'network failed',
    ))).toBe(true)
    expect(isRuntimeDiagnosticsInfrastructureError(Object.assign(new Error('disk full'), {
      code: 'ENOSPC',
    }))).toBe(true)
    expect(isRuntimeDiagnosticsInfrastructureError(new RuntimeTaskDeadlineError('diagnostics', 120))).toBe(true)
  })

  it('应继续把源码 Vite 错误和确定性校验错误作为结构化诊断', () => {
    expect(isRuntimeDiagnosticsInfrastructureError(new RuntimeBuildWorkerViteError({
      code: 'PLUGIN_ERROR',
      message: 'Vue SFC 编译失败',
    }))).toBe(false)
    expect(isRuntimeDiagnosticsInfrastructureError(new RuntimeBuildError(
      409,
      'BUILD_SOURCE_ABSOLUTE_ASSET_PATH_FORBIDDEN',
      '源码引用非法资源路径',
    ))).toBe(false)
    expect(isRuntimeDiagnosticsInfrastructureError(new RuntimeDiagnosticsWorkspaceError(
      409,
      'RUNTIME_DIAGNOSTICS_MODULE_PATH_FORBIDDEN',
      '模块路径非法',
    ))).toBe(false)
  })

  it('configureServer 不得在后台直接预热工作区，以免与正式构建并发复制 Runtime', () => {
    const warmupSpy = vi.spyOn(RuntimeDiagnosticsWorkspacePool.prototype, 'warmup')
    const httpServer = new EventEmitter()
    const plugin = runtimeBuildRunner()
    const internals = plugin as unknown as {
      configResolved: (config: { root: string }) => void
      configureServer: (server: {
        httpServer: EventEmitter
        middlewares: { use: ReturnType<typeof vi.fn> }
      }) => void
    }
    try {
      internals.configResolved({ root: process.cwd() })
      internals.configureServer({
        httpServer,
        middlewares: { use: vi.fn() },
      })

      expect(warmupSpy).not.toHaveBeenCalled()
    } finally {
      httpServer.emit('close')
      warmupSpy.mockRestore()
    }
  })
})

describe('runtime diagnostics module batch client', () => {
  it('应优先通过批量接口读取模块', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      modules: {
        'src/views/A.vue': '<template>A</template>',
        'src/views/B.vue': '<template>B</template>',
      },
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)
    try {
      const client = createBuildBackendClient({ backendApiBaseUrl: 'http://backend', serviceToken: 'token' })
      const modules = await client.fetchModuleSources('artifact-1', ['src/views/A.vue', 'src/views/B.vue'])

      expect(modules['src/views/A.vue']).toContain('A')
      expect(fetchMock).toHaveBeenCalledTimes(1)
      expect(fetchMock.mock.calls[0][1]?.method).toBe('POST')
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('旧 Backend 不支持批量接口时应回退逐模块读取', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response('', { status: 405 }))
      .mockResolvedValueOnce(new Response('<template>A</template>', { status: 200 }))
      .mockResolvedValueOnce(new Response('<template>B</template>', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    try {
      const client = createBuildBackendClient({ backendApiBaseUrl: 'http://backend', serviceToken: 'token' })
      const modules = await client.fetchModuleSources('artifact-1', ['src/views/A.vue', 'src/views/B.vue'])

      expect(Object.keys(modules)).toEqual(['src/views/A.vue', 'src/views/B.vue'])
      expect(fetchMock).toHaveBeenCalledTimes(3)
    } finally {
      vi.unstubAllGlobals()
    }
  })
})

describe('runtime build artifact streaming upload', () => {
  type CapturedUpload = {
    url: string
    init: RequestInit & { duplex?: string }
    body: Buffer
  }

  /**
   * 捕获 Runtime 上传归档时实际发出的请求：读取请求体流并返回 200。
   * @param captured 捕获结果容器
   * @param networkFailures 前若干次调用模拟连接被重置
   * @returns 供 vi.stubGlobal 使用的 fetch 实现
   */
  function captureUploadFetch(
    captured: CapturedUpload[],
    networkFailures: number,
  ): ReturnType<typeof vi.fn> {
    let remainingFailures = networkFailures
    return vi.fn(async (url: string, init: RequestInit & { duplex?: string }) => {
      if (remainingFailures > 0) {
        remainingFailures -= 1
        throw new TypeError('connection reset')
      }
      const body = Buffer.from(await new Response(init.body as BodyInit).arrayBuffer())
      captured.push({ url: String(url), init, body })
      return new Response(JSON.stringify({ artifact_entry_file: 'index.html' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    })
  }

  it('应以磁盘文件流作为请求体，归档元数据走请求头', async () => {
    const tempRoot = await mkdtemp(join(tmpdir(), 'wp-build-archive-'))
    try {
      const archivePath = join(tempRoot, 'artifact.zip')
      const content = Buffer.from('PK\u0003\u0004 streaming archive bytes')
      await writeFile(archivePath, content)
      const captured: CapturedUpload[] = []
      const fetchMock = captureUploadFetch(captured, 0)
      vi.stubGlobal('fetch', fetchMock)
      let uploadSummary: { artifact_entry_file?: string } = {}
      try {
        const client = createBuildBackendClient({ backendApiBaseUrl: 'http://backend', serviceToken: 'token' })
        uploadSummary = await client.uploadBuildArtifact({
          jobId: 'job-1',
          buildToken: 'build-token',
          archivePath,
          entryFile: 'index.html',
          sha256: 'archive-sha256',
          sizeBytes: content.byteLength,
        })
      } finally {
        vi.unstubAllGlobals()
      }

      expect(fetchMock).toHaveBeenCalledTimes(1)
      expect(captured).toHaveLength(1)
      expect(captured[0].url).toBe('http://backend/internal/runtime/build-jobs/job-1/artifact')
      // 整包不再进内存：请求体是文件流，而不是拼好的 FormData/Blob。
      expect(captured[0].init.body).toBeInstanceOf(ReadableStream)
      expect(captured[0].init.body).not.toBeInstanceOf(FormData)
      expect(captured[0].init.duplex).toBe('half')
      expect(captured[0].body.equals(content)).toBe(true)
      const headers = new Headers(captured[0].init.headers)
      expect(headers.get('authorization')).toBe('Bearer build-token')
      expect(headers.get('content-type')).toBe('application/zip')
      expect(headers.get('x-runtime-build-archive-entry-file')).toBe('index.html')
      expect(headers.get('x-runtime-build-archive-sha256')).toBe('archive-sha256')
      expect(headers.get('x-runtime-build-archive-size-bytes')).toBe(String(content.byteLength))
      expect(uploadSummary.artifact_entry_file).toBe('index.html')
    } finally {
      await rm(tempRoot, { recursive: true, force: true })
    }
  })

  it('网络重试时应重新打开归档文件，而不是重放已消费的流', async () => {
    const tempRoot = await mkdtemp(join(tmpdir(), 'wp-build-archive-'))
    try {
      const archivePath = join(tempRoot, 'artifact.zip')
      const content = Buffer.from('PK\u0003\u0004 retryable archive bytes')
      await writeFile(archivePath, content)
      const captured: CapturedUpload[] = []
      const fetchMock = captureUploadFetch(captured, 1)
      vi.stubGlobal('fetch', fetchMock)
      try {
        const client = createBuildBackendClient({ backendApiBaseUrl: 'http://backend', serviceToken: 'token' })
        await client.uploadBuildArtifact({
          jobId: 'job-1',
          buildToken: 'build-token',
          archivePath,
          entryFile: 'index.html',
          sha256: 'archive-sha256',
          sizeBytes: content.byteLength,
        })
      } finally {
        vi.unstubAllGlobals()
      }

      expect(fetchMock).toHaveBeenCalledTimes(2)
      expect(captured).toHaveLength(1)
      expect(captured[0].body.equals(content)).toBe(true)
    } finally {
      await rm(tempRoot, { recursive: true, force: true })
    }
  })
})

describe('runtime build worker readiness', () => {
  /** 以最小插件宿主挂载只开构建面的 runner；返回关闭函数。 */
  function mountBuildRunner(): { close: () => void } {
    const httpServer = new EventEmitter()
    const internals = runtimeBuildRunner({
      enableProjectEntry: true,
      enableDiagnosticsEntry: false,
    }) as unknown as {
      configResolved: (config: { root: string }) => void
      configureServer: (server: {
        httpServer: EventEmitter
        middlewares: { use: (handler: unknown) => void }
      }) => void
    }
    internals.configResolved({ root: process.cwd() })
    internals.configureServer({
      httpServer,
      middlewares: { use: () => {} },
    })
    return { close: () => httpServer.emit('close') }
  }

  it('RUNTIME_ROLE=build 且 worker 凭证不可读时应直接启动失败', () => {
    vi.stubEnv('RUNTIME_ROLE', 'build')
    vi.stubEnv('RUNTIME_BUILD_WORKER_CREDENTIAL', '')
    vi.stubEnv('RUNTIME_BUILD_WORKER_CREDENTIAL_FILE', '')
    vi.stubEnv('RUNTIME_BACKEND_API_BASE_URL', 'http://backend:8000')
    try {
      expect(() => mountBuildRunner()).toThrow(/RUNTIME_ROLE=build 但构建 Worker 无法启动/)
    } finally {
      vi.unstubAllEnvs()
    }
  })

  it('RUNTIME_ROLE=build 且 Backend 地址缺失时同样启动失败', () => {
    vi.stubEnv('RUNTIME_ROLE', 'build')
    vi.stubEnv('RUNTIME_BUILD_WORKER_CREDENTIAL', 'test-credential')
    vi.stubEnv('RUNTIME_BUILD_WORKER_CREDENTIAL_FILE', '')
    vi.stubEnv('RUNTIME_BACKEND_API_BASE_URL', '')
    try {
      expect(() => mountBuildRunner()).toThrow(/Backend API 地址缺失/)
    } finally {
      vi.unstubAllEnvs()
    }
  })

  it('非 build 角色缺凭证时仍可启动，但就绪探针必须报告未就绪', () => {
    vi.stubEnv('RUNTIME_ROLE', 'all')
    vi.stubEnv('RUNTIME_BUILD_WORKER_CREDENTIAL', '')
    vi.stubEnv('RUNTIME_BUILD_WORKER_CREDENTIAL_FILE', '')
    vi.stubEnv('RUNTIME_BACKEND_API_BASE_URL', '')
    const { close } = mountBuildRunner()
    try {
      const check = collectRuntimeReadiness().checks.buildWorker
      expect(check).toMatchObject({ ready: false })
      expect(check.detail).toContain('构建 Worker 领取循环未在运行')
    } finally {
      close()
      vi.unstubAllEnvs()
    }
  })

  it('Worker 启动后就绪，关闭服务器后回到未就绪', () => {
    vi.stubEnv('RUNTIME_ROLE', 'all')
    vi.stubEnv('RUNTIME_BUILD_WORKER_CREDENTIAL', 'test-credential')
    vi.stubEnv('RUNTIME_BUILD_WORKER_CREDENTIAL_FILE', '')
    vi.stubEnv('RUNTIME_BACKEND_API_BASE_URL', 'http://backend:8000')
    // 领取循环会立刻发起 claim：用离线替身避免测试打出真实请求。
    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new TypeError('offline')
    }))
    const { close } = mountBuildRunner()
    try {
      expect(collectRuntimeReadiness().checks.buildWorker).toEqual({ ready: true })
    } finally {
      close()
      vi.unstubAllEnvs()
      vi.unstubAllGlobals()
    }
    expect(collectRuntimeReadiness().checks.buildWorker).toMatchObject({ ready: false })
  })
})

describe('runtime build credential isolation (W01)', () => {
  const itPosix = process.platform === 'win32' ? it.skip : it

  itPosix('已配置子进程降权时，凭证文件对组/其他用户可读且收紧失败时必须 fail-closed', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'runtime-cred-loose-'))
    const credentialFile = join(dir, 'build_worker_credential')
    await writeFile(credentialFile, 'secret-value\n', { mode: 0o644 })
    vi.stubEnv('RUNTIME_BUILD_WORKER_CREDENTIAL_FILE', credentialFile)
    vi.stubEnv('RUNTIME_BUILD_WORKER_CREDENTIAL', '')
    vi.stubEnv('RUNTIME_BUILD_CHILD_UID', '10001')
    vi.stubEnv('RUNTIME_BUILD_CHILD_GID', '10001')
    const failingChmod = () => {
      throw Object.assign(new Error('EPERM: operation not permitted, chmod'), { code: 'EPERM' })
    }
    try {
      expect(() => readRuntimeBuildWorkerCredential({ chmodFn: failingChmod })).toThrow(RuntimeBuildError)
      try {
        readRuntimeBuildWorkerCredential({ chmodFn: failingChmod })
        expect.unreachable('应当抛出 RUNTIME_BUILD_CREDENTIAL_LOOSE_MODE')
      } catch (error) {
        expect(error).toMatchObject({ code: 'RUNTIME_BUILD_CREDENTIAL_LOOSE_MODE' })
      }
    } finally {
      vi.unstubAllEnvs()
      await rm(dir, { recursive: true, force: true })
    }
  })

  itPosix('未配置子进程降权时，宽松权限只告警不阻断（受限形态）', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'runtime-cred-warn-'))
    const credentialFile = join(dir, 'build_worker_credential')
    await writeFile(credentialFile, 'secret-value\n', { mode: 0o644 })
    vi.stubEnv('RUNTIME_BUILD_WORKER_CREDENTIAL_FILE', credentialFile)
    vi.stubEnv('RUNTIME_BUILD_WORKER_CREDENTIAL', '')
    vi.stubEnv('RUNTIME_BUILD_CHILD_UID', '')
    vi.stubEnv('RUNTIME_BUILD_CHILD_GID', '')
    try {
      expect(readRuntimeBuildWorkerCredential()).toBe('secret-value')
    } finally {
      vi.unstubAllEnvs()
      await rm(dir, { recursive: true, force: true })
    }
  })

  it('凭证 0400 且已配置降权时正常读取', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'runtime-cred-ok-'))
    const credentialFile = join(dir, 'build_worker_credential')
    await writeFile(credentialFile, 'secret-value\n', { mode: 0o600 })
    vi.stubEnv('RUNTIME_BUILD_WORKER_CREDENTIAL_FILE', credentialFile)
    vi.stubEnv('RUNTIME_BUILD_WORKER_CREDENTIAL', '')
    vi.stubEnv('RUNTIME_BUILD_CHILD_UID', '10001')
    vi.stubEnv('RUNTIME_BUILD_CHILD_GID', '10001')
    try {
      expect(readRuntimeBuildWorkerCredential()).toBe('secret-value')
    } finally {
      vi.unstubAllEnvs()
      await rm(dir, { recursive: true, force: true })
    }
  })

  itPosix('属主可写时自动把 0644 凭证收紧为 0400 并放行（M04-F1）', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'runtime-cred-heal-'))
    const credentialFile = join(dir, 'build_worker_credential')
    await writeFile(credentialFile, 'secret-value\n', { mode: 0o644 })
    vi.stubEnv('RUNTIME_BUILD_WORKER_CREDENTIAL_FILE', credentialFile)
    vi.stubEnv('RUNTIME_BUILD_WORKER_CREDENTIAL', '')
    vi.stubEnv('RUNTIME_BUILD_CHILD_UID', '10001')
    vi.stubEnv('RUNTIME_BUILD_CHILD_GID', '10001')
    try {
      expect(readRuntimeBuildWorkerCredential()).toBe('secret-value')
      const { statSync } = await import('fs')
      expect(statSync(credentialFile).mode & 0o077).toBe(0)
    } finally {
      vi.unstubAllEnvs()
      await rm(dir, { recursive: true, force: true })
    }
  })
})

describe('runtime build entry is pull-only', () => {
  type Middleware = (
    req: { method: string; url: string },
    res: { statusCode: number; setHeader: ReturnType<typeof vi.fn>; end: ReturnType<typeof vi.fn> },
    next: ReturnType<typeof vi.fn>,
  ) => void

  /** 以最小插件宿主收集 configureServer 注册的中间件。 */
  function mountRunner(options: Parameters<typeof runtimeBuildRunner>[0]): {
    middlewares: Middleware[]
    close: () => void
  } {
    const middlewares: Middleware[] = []
    const httpServer = new EventEmitter()
    const internals = runtimeBuildRunner(options) as unknown as {
      configResolved: (config: { root: string }) => void
      configureServer: (server: {
        httpServer: EventEmitter
        middlewares: { use: (handler: Middleware) => void }
      }) => void
    }
    internals.configResolved({ root: process.cwd() })
    internals.configureServer({
      httpServer,
      middlewares: { use: handler => middlewares.push(handler) },
    })
    return { middlewares, close: () => httpServer.emit('close') }
  }

  it('Worker 因凭证缺失未启动时，旧同步派发路径也不会被任何入口接管', () => {
    // 凭证与 Backend 地址双双缺失：构建没有可退回去的第二条执行路径。
    vi.stubEnv('RUNTIME_BUILD_WORKER_CREDENTIAL', '')
    vi.stubEnv('RUNTIME_BUILD_WORKER_CREDENTIAL_FILE', '')
    vi.stubEnv('RUNTIME_BACKEND_API_BASE_URL', '')

    const { middlewares, close } = mountRunner({
      enableProjectEntry: true,
      enableDiagnosticsEntry: false,
    })
    try {
      const res = { statusCode: 0, setHeader: vi.fn(), end: vi.fn() }
      const next = vi.fn()
      middlewares[0]({ method: 'POST', url: '/__runtime_internal/v1/builds/project' }, res, next)

      expect(next).toHaveBeenCalledTimes(1)
      expect(res.end).not.toHaveBeenCalled()
    } finally {
      close()
      vi.unstubAllEnvs()
    }
  })

  it('诊断入口仍只接受 POST，避免 GET 触发完整编译', () => {
    const { middlewares, close } = mountRunner({
      enableProjectEntry: false,
      enableDiagnosticsEntry: true,
    })
    try {
      const res = { statusCode: 0, setHeader: vi.fn(), end: vi.fn() }
      const next = vi.fn()
      middlewares[0]({ method: 'GET', url: '/__runtime_internal/v1/diagnostics/artifact' }, res, next)

      expect(res.statusCode).toBe(405)
      expect(next).not.toHaveBeenCalled()
    } finally {
      close()
    }
  })
})
