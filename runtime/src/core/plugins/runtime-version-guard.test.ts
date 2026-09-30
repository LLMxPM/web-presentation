/** 文件用途：用真实隔离 Vite 服务验证版本在模块/CSS/Vite 子请求和 HMR Upgrade 中传播。 */
// @vitest-environment node
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { connect } from 'node:net'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import { createServer, type ViteDevServer } from 'vite'
import runtimeVersionGuard from './runtime-version-guard'
import { assertRuntimeVersionPath, withRuntimeVersionBase } from './runtime-version-identity'

describe('真实 Vite 版本路径', () => {
  let server: ViteDevServer
  let root: string
  let origin: string
  const identity = '1.0.0+release-a'
  const base = `${withRuntimeVersionBase('/runtime', identity)}/`

  beforeAll(async () => {
    root = await mkdtemp(join(tmpdir(), 'wp-version-'))
    await Promise.all([
      writeFile(join(root, 'main.js'), 'import "./style.css"; import { value } from "./dep.js"; console.log(value)'),
      writeFile(join(root, 'dep.js'), 'export const value = "same-release"'),
      writeFile(join(root, 'style.css'), 'body { color: red }'),
      writeFile(join(root, 'font.js'), 'export const url = new URL("./font.svg", import.meta.url).href'),
      writeFile(join(root, 'font.svg'), '<svg xmlns="http://www.w3.org/2000/svg"><text>asset</text></svg>'),
    ])
    server = await createServer({
      configFile: false, root, base, plugins: [runtimeVersionGuard(identity)],
      build: { assetsInlineLimit: 0 },
      server: { host: '127.0.0.1', port: 0 }, logLevel: 'silent',
    })
    await server.listen()
    const address = server.httpServer!.address() as { port: number }
    origin = `http://127.0.0.1:${address.port}`
  })

  afterAll(async () => {
    await server?.close()
    if (root) await rm(root, { recursive: true, force: true })
  })

  it('转换后的嵌套 import 与 CSS 仍带发布版本，同版副本可消费相同 URL', async () => {
    const response = await fetch(`${origin}${base}main.js`)
    expect(response.status).toBe(200)
    const js = await response.text()
    expect(js).toContain(`${base}dep.js`)
    expect(js).toContain(`${base}style.css`)
    for (const path of ['dep.js', 'style.css', '@vite/client']) {
      const child = await fetch(`${origin}${base}${path}`)
      expect(child.status).toBe(200)
      expect(child.headers.get('x-runtime-version-fingerprint')).toBe(identity)
    }
    expect(() => assertRuntimeVersionPath(`${base}dep.js`, identity)).not.toThrow()
  })

  it('其它版本的模块、CSS、Vite 与预览端点在转换前统一返回 409', async () => {
    const wrong = withRuntimeVersionBase('/runtime', '1.0.0+release-b')
    for (const path of ['main.js', 'style.css', '@vite/client', '__preview-tailwind.css', '__preview']) {
      const response = await fetch(`${origin}${wrong}/${path}`)
      expect(response.status).toBe(409)
      expect(await response.json()).toMatchObject({ code: 'PREVIEW_VERSION_SKEW' })
    }
  })

  it('Vite 转换 new URL 静态资源时不会再次编码版本路径，字体/图片仍可读取', async () => {
    const source = await (await fetch(`${origin}${base}font.js`)).text()
    expect(source).toContain(`${base}font.svg`)
    const path = source.match(/new URL\(\s*['"]([^'"\n]+font\.svg)['"]/)?.[1]
    expect(path).toBe(`${base}font.svg`)
    expect(path).not.toContain('%25')
    expect((await fetch(origin + path!)).status).toBe(200)
  })

  it('跨版本 HMR Upgrade 不得先完成 WebSocket 握手', async () => {
    const address = server.httpServer!.address() as { port: number }
    const result = await new Promise<string>((resolve, reject) => {
      const socket = connect(address.port, '127.0.0.1')
      let data = ''
      socket.setTimeout(3000, () => { socket.destroy(); reject(new Error('Upgrade 未有界拒绝')) })
      socket.on('error', reject)
      socket.on('data', chunk => { data += chunk.toString() })
      socket.on('close', () => resolve(data))
      socket.on('connect', () => socket.write(
        `GET ${withRuntimeVersionBase('/runtime', '1.0.0+wrong')}/ HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Protocol: vite-hmr\r\n\r\n`,
      ))
    })
    expect(result).toContain('409 Conflict')
    expect(result).not.toContain('101 Switching')
  })
})
