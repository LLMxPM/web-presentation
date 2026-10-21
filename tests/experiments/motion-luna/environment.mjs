// 文件功能：分别检查每个 Luna 候选，失败候选不能阻断其他候选的独立运行。
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'
import { resolve } from 'node:path'
import { mkdir, writeFile } from 'node:fs/promises'
import { execFileSync } from 'node:child_process'

/** 候选文件单独做严格检查；研发 SDK 复用现有依赖，绝不修改生产清单。 */
export async function prepare(root, candidate, output) {
  const source = resolve(root, 'tests/experiments/motion-luna')
  const modules = resolve(root, '.tmp/motion-authoring/deps/node_modules'), runtimeModules = resolve(root, 'runtime/node_modules')
  const require = createRequire(resolve(root, 'runtime/package.json'))
  await mkdir(output, { recursive: true })
  const tsconfig = resolve(output, 'tsconfig.json')
  await writeFile(tsconfig, JSON.stringify({ compilerOptions: {
    target: 'ES2022', module: 'ESNext', moduleResolution: 'Bundler', strict: true, skipLibCheck: true, noEmit: true,
    allowJs: true, checkJs: false, lib: ['ES2022', 'DOM', 'DOM.Iterable'], baseUrl: root,
    paths: { 'three': [`${runtimeModules}/@types/three/index.d.ts`], 'three/addons/*': [`${runtimeModules}/@types/three/examples/jsm/*`], '*': [`${modules}/*`, `${runtimeModules}/*`] },
  }, include: [resolve(source, 'candidates', `${candidate}.vue`), resolve(source, 'harness.ts')] }))
  try { execFileSync(process.execPath, [require.resolve('vue-tsc/bin/vue-tsc.js'), '--project', tsconfig, '--noEmit'], { cwd: root, encoding: 'utf8', stdio: 'pipe', windowsHide: true }) }
  catch (error) { return { typecheck: { status: 'failed', output: String(error.stdout ?? error.message).replaceAll(root, '<repo>') } } }
  const { createServer } = await import(pathToFileURL(require.resolve('vite')).href)
  const { default: vue } = await import(pathToFileURL(require.resolve('@vitejs/plugin-vue')).href)
  const server = await createServer({ configFile: false, root: source, logLevel: 'error', plugins: [vue()],
    resolve: { dedupe: ['vue', 'three'], alias: [
      { find: /^vue$/, replacement: resolve(modules, 'vue/dist/vue.runtime.esm-bundler.js') },
      { find: /^animejs$/, replacement: resolve(modules, 'animejs/dist/modules/index.js') },
      { find: /^gsap$/, replacement: resolve(modules, 'gsap/index.js') },
      { find: /^three$/, replacement: resolve(runtimeModules, 'three/build/three.module.js') },
      { find: /^three\/addons\//, replacement: `${runtimeModules.replaceAll('\\', '/')}/three/examples/jsm/` },
    ] }, optimizeDeps: { noDiscovery: true, include: [] }, server: { host: '127.0.0.1', port: 0, fs: { allow: [root] } },
  })
  await server.listen()
  return { typecheck: { status: 'passed' }, server, url: server.resolvedUrls.local[0] }
}
