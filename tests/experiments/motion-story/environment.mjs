// 文件功能：完整故事实验的隔离 Vite 与严格 Vue/TS 检查，沿用固定候选版本且不启动业务服务。
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'
import { resolve } from 'node:path'
import { mkdir, writeFile, readFile } from 'node:fs/promises'
import { execFileSync } from 'node:child_process'

/** 只将候选包解析到忽略目录；旧媒体/模型 MJS 辅助函数不作为已严格检查的 TypeScript 声明。 */
export async function prepare(root) {
  const output = resolve(root, '.tmp/motion-story'), source = resolve(root, 'tests/experiments/motion-story')
  const modules = resolve(root, '.tmp/motion-authoring/deps/node_modules'), runtimeModules = resolve(root, 'runtime/node_modules')
  await mkdir(output, { recursive: true })
  const require = createRequire(resolve(root, 'runtime/package.json'))
  const { createServer } = await import(pathToFileURL(require.resolve('vite')).href)
  const { default: vue } = await import(pathToFileURL(require.resolve('@vitejs/plugin-vue')).href)
  const tsconfig = resolve(output, 'tsconfig.json')
  await writeFile(tsconfig, JSON.stringify({
    compilerOptions: { target: 'ES2022', module: 'ESNext', moduleResolution: 'Bundler', strict: true, skipLibCheck: true, noEmit: true, allowJs: true, checkJs: false, lib: ['ES2022', 'DOM', 'DOM.Iterable'], baseUrl: root, paths: { 'three': [`${runtimeModules}/@types/three/index.d.ts`], 'three/addons/*': [`${runtimeModules}/@types/three/examples/jsm/*`], '*': [`${modules}/*`, `${runtimeModules}/*`] } },
    include: [`${source}/*.vue`, `${source}/*.ts`],
  }))
  try { execFileSync(process.execPath, [require.resolve('vue-tsc/bin/vue-tsc.js'), '--project', tsconfig, '--noEmit'], { cwd: root, encoding: 'utf8', stdio: 'pipe', windowsHide: true }) }
  catch (error) { throw new Error(`SFC_TYPECHECK_FAILED\n${error.stdout ?? error.message}`) }
  const versions = {}
  for (const name of ['animejs', 'gsap', 'vue']) versions[name] = JSON.parse(await readFile(resolve(modules, name, 'package.json'), 'utf8')).version
  versions.three = JSON.parse(await readFile(resolve(runtimeModules, 'three/package.json'), 'utf8')).version
  const server = await createServer({ configFile: false, root: source, logLevel: 'error', plugins: [vue()],
    resolve: { dedupe: ['vue', 'three'], alias: [
      { find: /^vue$/, replacement: resolve(modules, 'vue/dist/vue.runtime.esm-bundler.js') },
      { find: /^animejs$/, replacement: resolve(modules, 'animejs/dist/modules/index.js') },
      { find: /^gsap$/, replacement: resolve(modules, 'gsap/index.js') },
      { find: /^three$/, replacement: resolve(runtimeModules, 'three/build/three.module.js') },
      { find: /^three\/addons\//, replacement: `${runtimeModules.replaceAll('\\', '/')}/three/examples/jsm/` },
    ] },
    optimizeDeps: { noDiscovery: true, include: [] }, server: { host: '127.0.0.1', port: 0, fs: { allow: [root] } },
  })
  await server.listen()
  return { server, url: server.resolvedUrls.local[0], versions, output, source }
}
