/**
 * 文件用途：Vite 构建配置，启用 Vue 支持与 SaaS 只读预览插件。
 */

import { resolve } from 'path'
import { defineConfig, loadEnv, type Logger, type LogErrorOptions } from 'vite'
import vue from '@vitejs/plugin-vue'

import runtimeHealth from './src/core/plugins/runtime-health'
import runtimeAssetRenderHintMeasurer from './src/core/plugins/runtime-asset-render-hint-measurer'
import runtimeBuildRunner from './src/core/plugins/runtime-build-runner'
import runtimeSaaSPreview from './src/core/plugins/runtime-saas-preview'
import runtimeStandalonePreviewGate, {
  resolveStandalonePreviewEnabled,
} from './src/core/plugins/runtime-standalone-preview-gate'
import runtimeVisualEdit from './src/core/plugins/runtime-visual-edit'
import { logRuntimeServer } from './src/core/utils/runtime-logger'

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, __dirname, '')
  const standalonePreviewEnabled = resolveStandalonePreviewEnabled(env.RUNTIME_STANDALONE_PREVIEW_ENABLED)
  const runtimeServerHost = resolveRuntimeServerHost(env.RUNTIME_SERVER_HOST)
  const runtimeServerPort = resolveRuntimeServerPort(env.RUNTIME_SERVER_PORT)
  const runtimeServerBase = command === 'serve'
    ? resolveRuntimeServerBasePath(env.RUNTIME_SERVER_BASE_PATH, env.RUNTIME_PUBLIC_BASE_URL)
    : './'
  const runtimeAllowedHosts = resolveRuntimeServerAllowedHosts(env.RUNTIME_SERVER_ALLOWED_HOSTS, [
    'runtime',
    env.RUNTIME_PUBLIC_BASE_URL,
    env.BACKEND_PUBLIC_BASE_URL,
  ])

  return {
    define: {
      __RUNTIME_BACKEND_BUILD__: 'false',
    },
    base: runtimeServerBase,
    server: {
      host: runtimeServerHost,
      port: runtimeServerPort,
      strictPort: true,
      cors: true,
      allowedHosts: runtimeAllowedHosts,
    },
    customLogger: createRuntimeViteLogger(),
    plugins: [
      runtimeHealth(),
      runtimeStandalonePreviewGate({
        enabled: standalonePreviewEnabled,
      }),
      vue(),
      runtimeBuildRunner({
        jwksUrl: env.RUNTIME_PREVIEW_JWKS_URL,
        backendApiBaseUrl: env.RUNTIME_BACKEND_API_BASE_URL,
      }),
      runtimeAssetRenderHintMeasurer({
        jwksUrl: env.RUNTIME_PREVIEW_JWKS_URL,
        serviceAudience: env.RUNTIME_SERVICE_TOKEN_AUDIENCE,
      }),
      runtimeVisualEdit({
        jwksUrl: env.RUNTIME_PREVIEW_JWKS_URL,
        serviceAudience: env.RUNTIME_SERVICE_TOKEN_AUDIENCE,
      }),
      runtimeSaaSPreview({
        jwksUrl: env.RUNTIME_PREVIEW_JWKS_URL,
        backendApiBaseUrl: env.RUNTIME_BACKEND_API_BASE_URL,
        previewAudience: env.RUNTIME_PREVIEW_TOKEN_AUDIENCE,
      })
    ],
    resolve: {
      alias: {
        '@': resolve(__dirname, 'src'),
        '@runtime-kit': resolve(__dirname, 'src/runtime-kit'),
        '@components': resolve(__dirname, 'src/components'),
        '@views': resolve(__dirname, 'src/views'),
        '@utils': resolve(__dirname, 'src/utils'),
        '@types': resolve(__dirname, 'src/types'),
        '@styles': resolve(__dirname, 'src/styles')
      }
    },
    css: {
      modules: {
        localsConvention: 'camelCase'
      }
    },
    assetsInclude: ['**/*.drawio'],
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.ts'],
    },
    build: {
      outDir: 'dist',
      sourcemap: false,
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (id.includes('/node_modules/vue/') || id.includes('/node_modules/vue-router/')) {
              return 'vendor'
            }
            return undefined
          }
        }
      }
    },
  }
})

/**
 * 解析 Runtime dev server 监听地址；本地开发默认仅绑定回环地址，容器镜像通过环境变量覆盖为 0.0.0.0。
 * @param rawHost 环境变量原始地址
 * @returns Vite server.host 配置值
 */
export function resolveRuntimeServerHost(rawHost?: string | null): string {
  const normalized = String(rawHost || '').trim()
  return normalized || '127.0.0.1'
}

/**
 * 解析 Runtime dev server 监听端口。
 * @param rawPort 环境变量原始端口
 * @returns Vite server.port 配置值
 */
export function resolveRuntimeServerPort(rawPort?: string | null): number {
  const parsed = Number(String(rawPort || '').trim())
  if (Number.isInteger(parsed) && parsed > 0 && parsed <= 65535) {
    return parsed
  }
  return 7373
}

/**
 * 解析 Runtime 对外挂载路径；同域网关部署通常为 /runtime/，独立域名或本地开发保持相对根路径。
 * @param rawBasePath 显式配置的挂载路径
 * @param runtimePublicBaseUrl Runtime 浏览器可访问地址，可从其中提取路径部分
 * @returns Vite base 配置值
 */
export function resolveRuntimeServerBasePath(
  rawBasePath?: string | null,
  runtimePublicBaseUrl?: string | null,
): string {
  const explicitBasePath = normalizeRuntimeServerBasePath(rawBasePath)
  if (explicitBasePath) {
    return explicitBasePath
  }

  const publicUrlPath = extractRuntimePublicUrlPath(runtimePublicBaseUrl)
  if (publicUrlPath) {
    return publicUrlPath
  }

  return './'
}

function extractRuntimePublicUrlPath(runtimePublicBaseUrl?: string | null): string {
  const normalized = String(runtimePublicBaseUrl || '').trim()
  if (!normalized) {
    return ''
  }

  try {
    return normalizeRuntimeServerBasePath(new URL(normalized).pathname)
  } catch {
    return normalizeRuntimeServerBasePath(normalized.startsWith('/') ? normalized : '')
  }
}

function normalizeRuntimeServerBasePath(rawBasePath?: string | null): string {
  const normalized = String(rawBasePath || '').trim()
  if (!normalized || normalized === '.' || normalized === './') {
    return ''
  }
  if (normalized === '/') {
    return '/'
  }

  const stripped = normalized
    .replace(/^\.\//, '')
    .replace(/^\/+|\/+$/g, '')

  return stripped ? `/${stripped}/` : ''
}

/**
 * 解析 Vite Host 白名单；容器部署默认允许 Compose 服务名 runtime，并支持追加公网域名。
 * @param rawHosts 逗号、分号或空白分隔的额外主机名，也可传入完整 URL
 * @param defaultHosts 默认允许的主机名或 URL
 * @returns 去重后的 Vite server.allowedHosts 列表
 */
export function resolveRuntimeServerAllowedHosts(
  rawHosts?: string | null,
  defaultHosts: Array<string | null | undefined> = ['runtime'],
): string[] {
  const allowedHosts: string[] = []

  for (const host of defaultHosts) {
    appendAllowedHost(allowedHosts, host)
  }

  for (const host of String(rawHosts || '').split(/[\s,;]+/)) {
    appendAllowedHost(allowedHosts, host)
  }

  return allowedHosts
}

function appendAllowedHost(allowedHosts: string[], rawHost?: string | null): void {
  const host = normalizeAllowedHost(rawHost)
  if (!host || allowedHosts.includes(host)) {
    return
  }
  allowedHosts.push(host)
}

function normalizeAllowedHost(rawHost?: string | null): string {
  const normalized = String(rawHost || '').trim()
  if (!normalized) {
    return ''
  }
  if (normalized.startsWith('.')) {
    return normalized.toLowerCase()
  }

  try {
    return new URL(normalized).hostname.toLowerCase()
  } catch {
    const hostWithoutPort = normalized.replace(/^\[([^\]]+)\](?::\d+)?$/, '$1').split(':')[0] || ''
    return hostWithoutPort.toLowerCase()
  }
}

/**
 * 创建 Vite 自定义日志器，把 Vite banner、优化器和错误日志也纳入 Runtime JSON Lines 契约。
 * @returns Vite Logger 实例
 */
export function createRuntimeViteLogger(): Logger {
  const warnedMessages = new Set<string>()
  const loggedErrors = new WeakSet<Error>()
  const logger: Logger = {
    hasWarned: false,
    info(message: string) {
      emitViteLog('info', 'vite.info', message)
    },
    warn(message: string) {
      logger.hasWarned = true
      emitViteLog('warn', 'vite.warn', message)
    },
    warnOnce(message: string, options?: LogOptions) {
      if (warnedMessages.has(message)) {
        return
      }
      warnedMessages.add(message)
      logger.warn(message, options)
    },
    error(message: string, options?: LogErrorOptions) {
      const error = options?.error instanceof Error ? options.error : null
      if (error) {
        loggedErrors.add(error)
      }
      emitViteLog('error', 'vite.error', message, error ? { error } : {})
    },
    clearScreen() {
      // 容器日志不清屏，避免破坏 JSON Lines 可读性。
    },
    hasErrorLogged(error: Error) {
      return loggedErrors.has(error)
    },
  }
  return logger
}

function emitViteLog(
  level: 'info' | 'warn' | 'error',
  event: string,
  message: string,
  context: Record<string, unknown> = {},
): void {
  const normalizedMessage = String(message || '').trim()
  if (!normalizedMessage) {
    return
  }
  logRuntimeServer(level, event, normalizedMessage, {
    module: 'runtime.vite',
    ...context,
  })
}
