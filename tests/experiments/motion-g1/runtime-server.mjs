// 文件功能：为 motion-g1 夹具启动开发服务器，或构建并预览真实的 Vite 生产产物。
import { createRequire } from 'node:module'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { readFile } from 'node:fs/promises'

/** 启动开发服务器或真正的 production build/preview，并在两种模式下提供相同媒体 fixture。 */
export async function startMotionRuntimeServer({ mode, source, root, scratch }) {
  const require = createRequire(resolve(root, 'runtime/package.json'))
  const vite = await import(pathToFileURL(require.resolve('vite')).href)
  const vuePlugin = (await import(pathToFileURL(require.resolve('@vitejs/plugin-vue')).href)).default
  const dist = resolve(scratch, 'production-dist')
  const fixturePlugin = createFixturePlugin(scratch)
  const aliases = {
    '@': resolve(root, 'runtime/src'),
    vue: require.resolve('vue/dist/vue.runtime.esm-bundler.js'),
    gsap: resolve(root, 'runtime/node_modules/gsap/index.js'),
    three: resolve(root, 'runtime/node_modules/three'),
  }

  if (mode === 'production') {
    const config = {
      configFile: false,
      root: source,
      mode: 'production',
      logLevel: 'error',
      resolve: { alias: aliases },
      plugins: [vuePlugin(), fixturePlugin],
      build: {
        outDir: dist,
        emptyOutDir: true,
        sourcemap: false,
        reportCompressedSize: false,
      },
    }
    await vite.build(config)
    const server = await vite.preview({
      configFile: false,
      root: source,
      logLevel: 'error',
      plugins: [fixturePlugin],
      build: { outDir: dist },
      preview: { host: '127.0.0.1', port: 0 },
    })
    const url = server.resolvedUrls?.local?.[0]
    if (!url) {
      await server.close()
      throw new Error('Vite production preview 未返回本地地址')
    }
    return { url, close: () => server.close() }
  }

  const server = await vite.createServer({
    configFile: false,
    root: source,
    logLevel: 'error',
    resolve: { alias: aliases },
    plugins: [vuePlugin(), fixturePlugin],
    server: { host: '127.0.0.1', port: 0, fs: { allow: [root] } },
  })
  await server.listen()
  const url = server.resolvedUrls?.local?.[0]
  if (!url) {
    await server.close()
    throw new Error('Vite development server 未返回本地地址')
  }
  return { url, close: () => server.close() }
}

/** 将本地媒体文件以浏览器可用的 Range/HEAD 接口提供给 dev 与 preview。 */
function createFixturePlugin(scratch) {
  const handleRequest = async (req, res, next) => {
    const url = req.url ?? ''
    if (!url.startsWith('/fixtures/')) return next()
    const [pathname, search] = url.split('?')
    const files = {
      '/fixtures/clock.webm': resolve(scratch, 'clock.webm'),
      '/fixtures/tone.wav': resolve(scratch, 'tone.wav'),
      '/fixtures/spin.glb': resolve(scratch, 'spin.glb'),
    }
    const file = files[pathname]
    if (!file) return next()
    const bytes = await readFile(file)
    if (pathname.endsWith('.webm') && search === 'slow=1') return streamSlowly(res, bytes)
    if (pathname.endsWith('.wav') && search === 'slow=1') return streamSlowly(res, bytes, 'audio/wav')
    res.setHeader('Content-Type', pathname.endsWith('.webm') ? 'video/webm'
      : pathname.endsWith('.wav') ? 'audio/wav' : 'model/gltf-binary')
    res.setHeader('Accept-Ranges', 'bytes')
    res.setHeader('Cache-Control', 'no-store')
    const range = req.headers.range?.match(/^bytes=(\d+)-(\d*)$/)
    const start = range ? Number(range[1]) : 0
    const end = range?.[2] ? Math.min(bytes.length - 1, Number(range[2])) : bytes.length - 1
    if (start > end) {
      res.writeHead(416, { 'Content-Range': `bytes */${bytes.length}` })
      res.end()
      return
    }
    if (range) {
      res.statusCode = 206
      res.setHeader('Content-Range', `bytes ${start}-${end}/${bytes.length}`)
    }
    res.setHeader('Content-Length', end - start + 1)
    res.end(req.method === 'HEAD' ? undefined : bytes.subarray(start, end + 1))
  }
  return {
    name: 'motion-g1-fixtures',
    configureServer(server) {
      server.middlewares.use(handleRequest)
    },
    configurePreviewServer(server) {
      server.middlewares.use(handleRequest)
    },
  }
}

/** 对受控缓冲场景分块返回媒体，触发浏览器真实 waiting 状态。 */
async function streamSlowly(res, bytes, contentType = 'video/webm') {
  res.setHeader('Content-Type', contentType)
  res.setHeader('Content-Length', bytes.length)
  for (let offset = 0; offset < bytes.length; offset += 4096) {
    if (res.destroyed) return
    res.write(bytes.subarray(offset, offset + 4096))
    await new Promise(resolveDelay => setTimeout(resolveDelay, 120))
  }
  res.end()
}
