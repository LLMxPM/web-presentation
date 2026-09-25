/**
 * 文件用途：为 Runtime dev server 提供健康检查与容量快照端点，供容器探针和编排层判断进程存活与负载压力。
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

/** Runtime 版本指纹：排空与路由核对用，不含业务数据。 */
export interface RuntimeVersionFingerprint {
  /** Runtime Kit 公开清单版本（同一预览不得混用不同 Runtime Kit 版本）。 */
  runtime_kit_version: string
  /** 部署构建标识（RUNTIME_BUILD_ID），未注入时为空串。 */
  build_id: string
}

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
        if (getRequestPathname(req.url || '/') !== RUNTIME_HEALTH_PATH) {
          return next()
        }
        sendRuntimeHealthResponse(res)
      })
    },
  }
}

/**
 * 输出健康检查响应，包含存活状态与进程/角色容量快照。
 * @param res Node 响应对象
 */
export function sendRuntimeHealthResponse(
  res: Pick<ServerResponse, 'statusCode' | 'setHeader' | 'end'>,
): void {
  res.statusCode = 200
  res.setHeader('Cache-Control', 'no-store')
  res.setHeader('Content-Type', 'application/json; charset=utf-8')
  res.end(JSON.stringify(buildRuntimeHealthPayload()))
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
