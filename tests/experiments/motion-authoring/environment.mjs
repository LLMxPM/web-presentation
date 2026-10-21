// 文件功能：为原生 SFC 调研准备隔离依赖解析、Vue 类型检查和随机端口 Vite，不采集性能指标。
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'
import { resolve } from 'node:path'
import { mkdir, writeFile, readFile } from 'node:fs/promises'
import { execFileSync } from 'node:child_process'

/** 使用已有工具链与忽略目录的候选包；不修改 workspace 清单或启动产品服务。 */
export async function prepare(root) {
  const output = resolve(root, '.tmp/motion-authoring'), source = resolve(root, 'tests/experiments/motion-authoring')
  const modules = resolve(output, 'deps/node_modules'), runtimeModules = resolve(root, 'runtime/node_modules')
  await mkdir(output, { recursive: true })
  const require = createRequire(resolve(root, 'runtime/package.json'))
  const { createServer } = await import(pathToFileURL(require.resolve('vite')).href)
  const { default: vue } = await import(pathToFileURL(require.resolve('@vitejs/plugin-vue')).href)
  const tsconfig = resolve(output, 'tsconfig.json')
  await writeFile(tsconfig, JSON.stringify({
    compilerOptions: { target: 'ES2022', module: 'ESNext', moduleResolution: 'Bundler', strict: true, skipLibCheck: true, noEmit: true, lib: ['ES2022', 'DOM', 'DOM.Iterable'], baseUrl: root, paths: { 'three': [`${runtimeModules}/@types/three/index.d.ts`], 'motion/three': [`${modules}/motion/dist/three.d.ts`], 'animejs/adapters/three': [`${modules}/animejs/dist/modules/adapters/three/index.d.ts`], '*': [`${modules}/*`, `${runtimeModules}/*`] } },
    include: [`${source}/*.vue`, `${source}/harness.ts`],
  }))
  execFileSync(process.execPath, [require.resolve('vue-tsc/bin/vue-tsc.js'), '--project', tsconfig, '--noEmit'], { cwd: root, encoding: 'utf8', stdio: 'pipe', windowsHide: true })
  const versions = {}
  for (const name of ['animejs', 'gsap', 'motion', 'motion-v', 'vue']) versions[name] = JSON.parse(await readFile(resolve(modules, name, 'package.json'), 'utf8')).version
  const server = await createServer({
    configFile: false, root: source, logLevel: 'error', plugins: [vue()],
    resolve: { dedupe: ['vue', 'three'], alias: [
      { find: /^vue$/, replacement: resolve(modules, 'vue/dist/vue.runtime.esm-bundler.js') },
      { find: /^animejs$/, replacement: resolve(modules, 'animejs/dist/modules/index.js') },
      { find: /^animejs\/adapters\/three$/, replacement: resolve(modules, 'animejs/dist/modules/adapters/three/index.js') },
      { find: /^three$/, replacement: resolve(runtimeModules, 'three/build/three.module.js') },
      { find: /^gsap$/, replacement: resolve(modules, 'gsap/index.js') },
      { find: /^motion-v$/, replacement: resolve(modules, 'motion-v/dist/es/index.mjs') },
      { find: /^motion$/, replacement: resolve(modules, 'motion/dist/es/index.mjs') },
      { find: /^motion\/three$/, replacement: resolve(modules, 'motion/dist/es/three.mjs') },
    ] },
    optimizeDeps: { noDiscovery: true, include: [] },
    server: { host: '127.0.0.1', port: 0, fs: { allow: [root] } },
  })
  await server.listen()
  return { server, url: server.resolvedUrls.local[0], versions, output, source }
}
