/**
 * 文件用途：为 Runtime dev server 提供轻量健康检查端点，供容器探针和编排层判断进程存活。
 */

import type { ServerResponse } from 'http'
import type { Plugin, ViteDevServer } from 'vite'

export const RUNTIME_HEALTH_PATH = '/__runtime_healthz'

/**
 * 创建 Runtime 健康检查插件。
 * @returns Vite 插件
 */
export default function runtimeHealth(): Plugin {
  return {
    name: 'runtime-health',
    apply: 'serve',
    enforce: 'pre',

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
 * 输出健康检查响应。
 * @param res Node 响应对象
 */
export function sendRuntimeHealthResponse(
  res: Pick<ServerResponse, 'statusCode' | 'setHeader' | 'end'>,
): void {
  res.statusCode = 200
  res.setHeader('Cache-Control', 'no-store')
  res.setHeader('Content-Type', 'application/json; charset=utf-8')
  res.end(JSON.stringify({ status: 'ok' }))
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
