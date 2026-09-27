/**
 * 文件用途：为 Runtime dev server 提供健康检查与容量快照端点，供容器探针和编排层判断进程存活与负载压力。
 * 存活探针（/__runtime_healthz）只回答「进程还在」，就绪探针（/__runtime_readyz）额外回答
 * 「本角色声明的执行面是否真的可用」——build 角色凭证缺失时不得再被编排层当成健康副本。
 * 健康体携带版本指纹（runtime_kit_version / build_id），供滚动发布排空时核对副本版本。
 */

import type { ServerResponse } from 'http'
import type { Plugin, ViteDevServer } from 'vite'

import runtimeKitManifest from '../../runtime-kit/manifest/runtime-kit.manifest.json'
import {
  collectRuntimeCapacity,
  startRuntimeEventLoopLagMonitor,
} from './runtime-capacity'
import { getRuntimeRole } from './runtime-role'

export const RUNTIME_HEALTH_PATH = '/__runtime_healthz'
export const RUNTIME_READINESS_PATH = '/__runtime_readyz'

/** Runtime 版本指纹：排空与路由核对用，不含业务数据。 */
export interface RuntimeVersionFingerprint {
  /** Runtime Kit 公开清单版本（同一预览不得混用不同 Runtime Kit 版本）。 */
  runtime_kit_version: string
  /** 部署构建标识（RUNTIME_BUILD_ID），未注入时为空串。 */
  build_id: string
}

/** 单项就绪检查结果；detail 只输出本进程可见的配置事实，不含凭证内容。 */
export interface RuntimeReadinessCheck {
  ready: boolean
  detail?: string
}

/** 就绪探针：由角色插件注册，返回布尔或带原因的结构。 */
export type RuntimeReadinessProbe = () => boolean | RuntimeReadinessCheck

/** 就绪汇总：全部检查通过才 ready，任一未就绪都会让探针返回 503。 */
export interface RuntimeReadinessSummary {
  ready: boolean
  checks: Record<string, RuntimeReadinessCheck>
}

const readinessProbes = new Map<string, RuntimeReadinessProbe>()

/**
 * 创建 Runtime 健康检查插件。
 * @returns Vite 插件
 */
export default function runtimeHealth(): Plugin {
  return {
    name: 'runtime-health',
    apply: 'serve',
    enforce: 'pre',

    configResolved() {
      startRuntimeEventLoopLagMonitor()
    },

    configureServer(server: ViteDevServer) {
      server.middlewares.use((req, res, next) => {
        const pathname = getRequestPathname(req.url || '/')
        if (pathname === RUNTIME_HEALTH_PATH) {
          return sendRuntimeHealthResponse(res)
        }
        if (pathname === RUNTIME_READINESS_PATH) {
          return sendRuntimeReadinessResponse(res)
        }
        return next()
      })
    },
  }
}

/**
 * 输出存活探针响应，包含存活状态与进程/角色容量快照。
 * @param res Node 响应对象
 */
export function sendRuntimeHealthResponse(
  res: Pick<ServerResponse, 'statusCode' | 'setHeader' | 'end'>,
): void {
  sendRuntimeProbeResponse(res, 200, buildRuntimeHealthPayload())
}

/**
 * 输出就绪探针响应；任一角色检查未通过时返回 503，让编排层停止依赖该副本。
 * @param res Node 响应对象
 */
export function sendRuntimeReadinessResponse(
  res: Pick<ServerResponse, 'statusCode' | 'setHeader' | 'end'>,
): void {
  const readiness = collectRuntimeReadiness()
  sendRuntimeProbeResponse(
    res,
    readiness.ready ? 200 : 503,
    buildRuntimeReadinessPayload(readiness),
  )
}

/**
 * 注册角色级就绪探针。
 * @param name 检查名，重复注册会覆盖
 * @param probe 返回就绪状态与可选原因
 * @returns 取消注册函数
 */
export function registerRuntimeReadinessProbe(
  name: string,
  probe: RuntimeReadinessProbe,
): () => void {
  readinessProbes.set(name, probe)
  return () => {
    if (readinessProbes.get(name) === probe) {
      readinessProbes.delete(name)
    }
  }
}

/**
 * 汇总全部就绪探针；探针自身抛错按未就绪处理，避免坏检查伪装成健康。
 * @returns 就绪汇总
 */
export function collectRuntimeReadiness(): RuntimeReadinessSummary {
  const checks: Record<string, RuntimeReadinessCheck> = {}
  let ready = true
  for (const [name, probe] of readinessProbes) {
    let check: RuntimeReadinessCheck
    try {
      const result = probe()
      check = typeof result === 'boolean' ? { ready: result } : result
    } catch (error) {
      check = {
        ready: false,
        detail: error instanceof Error ? error.message : String(error),
      }
    }
    checks[name] = check
    ready = ready && check.ready
  }
  return { ready, checks }
}

/**
 * 构建健康检查返回体。
 * @returns 健康与容量结构（含运行角色与版本指纹）
 */
export function buildRuntimeHealthPayload(): Record<string, unknown> {
  return {
    status: 'ok',
    role: getRuntimeRole(),
    ...buildRuntimeVersionFingerprint(),
    ...collectRuntimeCapacity(),
  }
}

/**
 * 构建就绪检查返回体。
 * @param readiness 就绪汇总
 * @returns 就绪结构（含运行角色与版本指纹）
 */
export function buildRuntimeReadinessPayload(
  readiness: RuntimeReadinessSummary = collectRuntimeReadiness(),
): Record<string, unknown> {
  return {
    status: readiness.ready ? 'ok' : 'unavailable',
    role: getRuntimeRole(),
    ...buildRuntimeVersionFingerprint(),
    checks: readiness.checks,
  }
}

/**
 * 读取当前进程版本指纹，供滚动发布时核对新旧副本与排空目标。
 * runtime_kit_version 来自 Runtime Kit 清单；build_id 来自部署注入的 RUNTIME_BUILD_ID。
 * @returns 版本指纹对象
 */
export function buildRuntimeVersionFingerprint(): RuntimeVersionFingerprint {
  return {
    runtime_kit_version: String(runtimeKitManifest.version || ''),
    build_id: String(process.env.RUNTIME_BUILD_ID || ''),
  }
}

/**
 * 输出探针响应：一律 no-store，避免中间层缓存把已恢复的副本继续判死。
 * @param res Node 响应对象
 * @param statusCode HTTP 状态码
 * @param payload 返回体
 */
function sendRuntimeProbeResponse(
  res: Pick<ServerResponse, 'statusCode' | 'setHeader' | 'end'>,
  statusCode: number,
  payload: Record<string, unknown>,
): void {
  res.statusCode = statusCode
  res.setHeader('Cache-Control', 'no-store')
  res.setHeader('Content-Type', 'application/json; charset=utf-8')
  res.end(JSON.stringify(payload))
}

/**
 * 解析请求路径，避免 query 影响健康检查路径匹配。
 * @param rawUrl 原始请求 URL
 * @returns pathname
 */
function getRequestPathname(rawUrl: string): string {
  try {
    return new URL(rawUrl, 'http://runtime.local').pathname || '/'
  } catch {
    return '/'
  }
}
