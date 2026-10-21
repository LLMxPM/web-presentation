// 文件功能：生成实际 pnpm --prod 安装用的最小研究执行包，明确保留 Vite/插件为执行依赖。
import { readFile, writeFile, mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
const directory = resolve('.tmp/motion-final/production'), dependencies = {}
for (const name of ['gsap', 'vue']) dependencies[name] = JSON.parse(await readFile(resolve('.tmp/motion-authoring/deps/node_modules', name, 'package.json'), 'utf8')).version
for (const name of ['three', 'vite', '@vitejs/plugin-vue', 'typescript']) dependencies[name] = JSON.parse(await readFile(resolve('runtime/node_modules', name, 'package.json'), 'utf8')).version
const devDependencies = {}
for (const name of ['vue-tsc']) devDependencies[name] = JSON.parse(await readFile(resolve('runtime/node_modules', name, 'package.json'), 'utf8')).version
await mkdir(directory, { recursive: true })
await writeFile(resolve(directory, 'package.json'), `${JSON.stringify({ name: 'wp-motion-g0-production-probe', private: true, type: 'module', dependencies, devDependencies }, null, 2)}\n`)
console.log(JSON.stringify({ directory, dependencies, excludedFromProduction: Object.keys(devDependencies) }))
