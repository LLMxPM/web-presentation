// 文件功能：最终原型的独立类型检查、开发加载与可切换裁剪依赖源的 Vite 配置。
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'
import { resolve } from 'node:path'
import { mkdir, writeFile } from 'node:fs/promises'
import { execFileSync } from 'node:child_process'

/** 对当前候选及固定适配层严格检查，其他未完成候选不影响评分。 */
export async function typecheck(root, candidate, output) {
  const source = resolve(root, 'tests/experiments/motion-final'), runtime = resolve(root, 'runtime/node_modules')
  const modules = resolve(root, '.tmp/motion-authoring/deps/node_modules'), require = createRequire(resolve(root, 'runtime/package.json'))
  await mkdir(output, { recursive: true }); const tsconfig = resolve(output, 'tsconfig.json')
  await writeFile(tsconfig, JSON.stringify({ compilerOptions: {
    target: 'ES2022', module: 'ESNext', moduleResolution: 'Bundler', strict: true, skipLibCheck: true, noEmit: true, allowJs: true, checkJs: false,
    lib: ['ES2022', 'DOM', 'DOM.Iterable'], baseUrl: root, types: [`${runtime}/vite/client`],
    paths: { 'three': [`${runtime}/@types/three/index.d.ts`], 'three/addons/*': [`${runtime}/@types/three/examples/jsm/*`], '*': [`${modules}/*`, `${runtime}/*`] },
  }, include: [resolve(source, candidate === 'reference' ? 'reference.vue' : `candidates/${candidate}.vue`), `${source}/*.ts`] }))
  try { execFileSync(process.execPath, [require.resolve('vue-tsc/bin/vue-tsc.js'), '--project', tsconfig, '--noEmit'], { cwd: root, encoding: 'utf8', stdio: 'pipe', windowsHide: true }); return { status: 'passed' } }
  catch (error) { return { status: 'failed', output: String(error.stdout ?? error.message).replaceAll(root, '<repo>') } }
}

/** 依赖源可切到真正 pnpm --prod 安装目录；核心库与构建器都从该目录显式解析。 */
export async function viteConfig(root, productionDirectory) {
  const source = resolve(root, 'tests/experiments/motion-final')
  const modules = productionDirectory ? resolve(productionDirectory, 'node_modules') : resolve(root, '.tmp/motion-authoring/deps/node_modules')
  const runtime = productionDirectory ? modules : resolve(root, 'runtime/node_modules')
  const require = createRequire(resolve(productionDirectory ?? resolve(root, 'runtime'), 'package.json'))
  const vite = await import(pathToFileURL(require.resolve('vite')).href), { default: vue } = await import(pathToFileURL(require.resolve('@vitejs/plugin-vue')).href)
  const config = { configFile: false, root: source, logLevel: 'error', plugins: [vue()], resolve: { dedupe: ['vue', 'three'], alias: [
    { find: /^vue$/, replacement: resolve(modules, 'vue/dist/vue.runtime.esm-bundler.js') },
    { find: /^gsap$/, replacement: resolve(modules, 'gsap/index.js') },
    { find: /^three$/, replacement: resolve(runtime, 'three/build/three.module.js') },
    { find: /^three\/addons\//, replacement: `${runtime.replaceAll('\\', '/')}/three/examples/jsm/` },
  ] }, optimizeDeps: { noDiscovery: true, include: [] }, server: { host: '127.0.0.1', port: 0, fs: { allow: [root] } } }
  return { vite, config, tools: { vite: require.resolve('vite'), plugin: require.resolve('@vitejs/plugin-vue') } }
}

/** 仅启动本次研究端口，调用方负责 finally 关闭。 */
export async function serveVite(root, productionDirectory) {
  const { vite, config, tools } = await viteConfig(root, productionDirectory), server = await vite.createServer(config)
  await server.listen(); return { server, url: server.resolvedUrls.local[0], tools }
}
