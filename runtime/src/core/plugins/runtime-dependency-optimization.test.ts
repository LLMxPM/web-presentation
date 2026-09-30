/** 文件功能：验证清空缓存后的真实 Vite 冷启动仍产生同一依赖 URL，旧副本 URL 可直接消费。 */
// @vitest-environment node
import { mkdtemp, rm, symlink, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { resolve, join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { createServer, type ViteDevServer } from 'vite'
import { runtimeDependencyOptimization } from './runtime-dependency-optimization'
import runtimeVersionGuard from './runtime-version-guard'
import { withRuntimeVersionBase } from './runtime-version-identity'

describe('Runtime 显式依赖优化', () => {
  it('两个全新优化器的 Vue URL 相同且无需关闭 Vite 的陈旧依赖校验', async () => {
    const root = await mkdtemp(join(tmpdir(), 'wp-cold-deps-'))
    const cache = join(root, '.cache')
    const identity = '1.0.0+same-image'
    const base = `${withRuntimeVersionBase('/runtime', identity)}/`
    let server: ViteDevServer | undefined
    try {
      await symlink(resolve('node_modules'), join(root, 'node_modules'), process.platform === 'win32' ? 'junction' : 'dir')
      await writeFile(join(root, 'main.js'), 'import { createApp } from "vue"; export { createApp }')
      const urls: string[] = []
      for (let index = 0; index < 2; index++) {
        server = await createServer({
          configFile: false, root, base, cacheDir: cache, logLevel: 'silent',
          optimizeDeps: { ...runtimeDependencyOptimization(), include: ['vue'] },
          plugins: [runtimeVersionGuard(identity)], server: { host: '127.0.0.1', port: 0 },
        })
        await server.listen()
        const origin = `http://127.0.0.1:${(server.httpServer!.address() as { port: number }).port}`
        const source = await (await fetch(`${origin}${base}main.js`)).text()
        const url = source.match(/"([^"\n]+vue\.js\?v=[^"\n]+)"/)?.[1]
        expect(url).toBeTruthy()
        urls.push(url!)
        expect(server.config.optimizeDeps.ignoreOutdatedRequests).toBe(false)
        const response = await fetch(origin + urls[0])
        expect(response.status).toBe(200)
        expect(await response.text()).toContain('createApp')
        await server.close()
        server = undefined
        // 仅清除本测试创建的缓存；第二次启动不能复用首轮 metadata。
        await rm(cache, { recursive: true, force: true })
      }
      expect(urls[0]).toBe(urls[1])
    } finally {
      await server?.close()
      await rm(root, { recursive: true, force: true })
    }
  }, 30_000)
})
