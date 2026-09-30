/** 文件功能：真实 Vue/Vite 首次请求仅为样式子模块时也能恢复虚拟 SFC 描述符。 */
// @vitest-environment node
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import vue from '@vitejs/plugin-vue'
import { describe, expect, it } from 'vitest'
import { createServer, type ViteDevServer } from 'vite'
import { prepareRemoteSfcSubrequest } from './runtime-remote-sfc'

describe('无主模块缓存的远程 SFC 子请求', () => {
  it('首次 scoped CSS 请求先加载主模块，Vue loader 不会读取虚拟文件系统路径', async () => {
    const root = await mkdtemp(join(tmpdir(), 'wp-sfc-child-'))
    let server: ViteDevServer | undefined
    let mainLoads = 0
    try {
      server = await createServer({
        configFile: false, root, logLevel: 'silent', optimizeDeps: { noDiscovery: true },
        server: { host: '127.0.0.1', port: 0 },
        plugins: [vue(), {
          name: 'fixture-remote-sfc',
          configureServer(value) {
            value.middlewares.use(async (req, _res, next) => {
              // 测试票据仅服务固定 fixture；生产入口在恢复描述符前执行实际 RS256 验签。
              try { await prepareRemoteSfcSubrequest(value, req.url || '/'); next() } catch (error) { next(error) }
            })
          },
          resolveId(id) { if (id.startsWith('/@runtime-preview/')) return id },
          load(id) {
            if (id.startsWith('/@runtime-preview/') && !id.includes('type=style')) {
              mainLoads++
              return '<script>export default {}</script><style scoped>.probe { color: red }</style>'
            }
          },
        }],
      })
      await server.listen()
      const origin = `http://127.0.0.1:${(server.httpServer!.address() as { port: number }).port}`
      const response = await fetch(origin + '/@runtime-preview/fixture/src/Page.vue?vue&type=style&index=0&scoped=test&lang.css&ctx=fixture')
      expect(response.status).toBe(200)
      expect(await response.text()).toContain('color: red')
      expect(mainLoads).toBe(1)
    } finally {
      await server?.close()
      await rm(root, { recursive: true, force: true })
    }
  })
})
