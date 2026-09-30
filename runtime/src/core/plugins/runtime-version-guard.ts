/** 文件用途：在 Vite/base/模块处理前拒绝混版 HTTP 与 HMR WebSocket 请求。 */
import type { Plugin } from 'vite'
import { assertRuntimeVersionPath, formatRuntimeVersionFingerprint } from './runtime-version-identity'

/** 根据版本路径检查所有资源和 Upgrade；不缓存票据，也不依赖粘性会话。 */
export default function runtimeVersionGuard(fingerprint = formatRuntimeVersionFingerprint()): Plugin {
  return {
    name: 'runtime-version-guard', apply: 'serve', enforce: 'pre',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        res.setHeader('x-runtime-version-fingerprint', fingerprint)
        try {
          assertRuntimeVersionPath(req.url || '/', fingerprint)
          next()
        } catch {
          res.statusCode = 409
          res.setHeader('Content-Type', 'application/json; charset=utf-8')
          res.setHeader('Cache-Control', 'no-store')
          res.end(JSON.stringify({ code: 'PREVIEW_VERSION_SKEW', message: '预览资源版本不匹配，请刷新预览。' }))
        }
      })
      // 必须早于 Vite 的 Upgrade listener，失配不能升级成功后才关闭。
      server.httpServer?.prependListener('upgrade', (req, socket) => {
        try {
          assertRuntimeVersionPath(req.url || '/', fingerprint)
        } catch {
          socket.write('HTTP/1.1 409 Conflict\r\nConnection: close\r\nContent-Length: 0\r\n\r\n')
          socket.destroy()
        }
      })
    },
  }
}
