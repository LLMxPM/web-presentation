// 文件功能：把两个候选分别构建为无开发服务器、无 node_modules 依赖的静态实验包并测量体积。
import { createRequire } from 'node:module'
import { pathToFileURL, fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { readFile, writeFile, mkdir } from 'node:fs/promises'
import { gzipSync } from 'node:zlib'

/** 从既有 workspace 定位依赖，GSAP 仅来自隔离实验目录；不安装生产依赖。 */
export async function buildCandidates(root, output) {
  const require = createRequire(resolve(root, 'runtime/package.json'))
  const { build } = await import(pathToFileURL(require.resolve('vite')).href)
  const threeRoot = dirname(dirname(require.resolve('three')))
  const gsap = resolve(output, 'deps/node_modules/gsap/index.js')
  const source = dirname(fileURLToPath(import.meta.url)), sizes = {}
  for (const name of ['waapi', 'gsap']) {
    const directory = resolve(output, name)
    await mkdir(directory, { recursive: true })
    /** 每次构建使用全新配置，避免 Vite 解析时写回 output 后污染下一次体积测量。 */
    const config = (entry, outDir, fileName) => ({
      configFile: false, root: source, logLevel: 'warn',
      resolve: { alias: [
        { find: '@candidate', replacement: resolve(source, `dom-${name}.mjs`) },
        { find: /^three$/, replacement: resolve(threeRoot, 'build/three.module.js') },
        { find: /^three\/addons\//, replacement: `${threeRoot.replaceAll('\\', '/')}/examples/jsm/` },
        { find: /^gsap$/, replacement: gsap },
      ] },
      build: { outDir, emptyOutDir: false, minify: true, lib: { entry: resolve(source, entry), formats: ['es'], fileName: () => fileName } },
    })
    await build(config('scene.mjs', directory, 'scene.js'))
    const scene = await readFile(resolve(directory, 'scene.js'))
    await writeFile(resolve(directory, 'index.html'), '<!doctype html><html><meta charset="utf-8"><title>WP01</title><body><script type="module" src="./scene.js"></script></body></html>')
    await build(config(`dom-${name}.mjs`, resolve(directory, 'adapter-only'), 'adapter.js'))
    const adapter = await readFile(resolve(directory, 'adapter-only/adapter.js'))
    sizes[name] = { sceneBytes: scene.length, sceneGzipBytes: gzipSync(scene).length, adapterBytes: adapter.length, adapterGzipBytes: gzipSync(adapter).length }
  }
  return sizes
}
