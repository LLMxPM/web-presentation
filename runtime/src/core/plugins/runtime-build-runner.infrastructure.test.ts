/**
 * 文件用途：验证 Runtime 诊断的基础设施错误语义与惰性工作区预热边界。
 */

import { EventEmitter } from 'node:events'

import { describe, expect, it, vi } from 'vitest'

import runtimeBuildRunner, {
  RuntimeBuildError,
  createBuildBackendClient,
  isRuntimeDiagnosticsInfrastructureError,
} from './runtime-build-runner'
import {
  RuntimeBuildWorkerProcessError,
  RuntimeBuildWorkerViteError,
} from './runtime-build-worker'
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
