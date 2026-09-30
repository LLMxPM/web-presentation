/** 文件用途：按 Runtime 源码、配置与根锁文件生成可复现的镜像发布身份。 */
import { createHash } from 'node:crypto'
import { existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

/** 收集全部交付输入；Tailwind 也扫描测试源码，不能把这些文件排除在身份之外。 */
function collect(root, relative) {
  return readdirSync(join(root, relative), { withFileTypes: true }).flatMap(entry => {
    const path = `${relative}/${entry.name}`
    if (entry.isDirectory()) return collect(root, path)
    return [path]
  })
}

/** 对文件路径与内容同时取 hash，增加/删除模块或依赖锁变化都会改变身份。 */
export function computeRuntimeBuildId(runtimeRoot, lockPath) {
  const hash = createHash('sha256')
  const files = [
    ...['src', 'public', 'scripts', 'api'].filter(dir => existsSync(join(runtimeRoot, dir)))
      .flatMap(dir => collect(runtimeRoot, dir)),
    'package.json', 'vite.config.ts', 'index.html', 'postcss.config.js', 'tailwind.config.js', 'tsconfig.json',
  ].sort()
  for (const path of files) {
    const content = readFileSync(join(runtimeRoot, path))
    hash.update(`${path}\0${content.length}\0`).update(content)
  }
  hash.update('pnpm-lock.yaml\0').update(readFileSync(lockPath))
  return `sha256-${hash.digest('hex')}`
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
  writeFileSync(join(root, '.runtime-build-id'), computeRuntimeBuildId(root, join(root, '..', 'pnpm-lock.yaml')) + '\n')
}
