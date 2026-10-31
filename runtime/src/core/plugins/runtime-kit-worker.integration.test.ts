/** 文件功能：以真实子进程构建验证项目、单次诊断和常驻诊断的 Kit 门禁及任务间快照隔离。 */
// @vitest-environment node
import { mkdir, mkdtemp, rm, symlink, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import type { RuntimeModuleResolverConfig } from '../shared/runtime-preview'
import { RuntimeDiagnosticsWorker, runRuntimeViteBuildInWorker } from './runtime-build-worker'

const allowed = '@runtime-kit/public/utils/allowed.v1'
const other = '@runtime-kit/public/utils/other.v1'
let tempRoot: string
let persistent: RuntimeDiagnosticsWorker

/** 写入仅本测试拥有的隔离工作区，不加载或重置业务数据。 */
async function writeFixture(path: string, content: string) {
  const target = resolve(tempRoot, path)
  await mkdir(dirname(target), { recursive: true })
  await writeFile(target, content, 'utf8')
}

/** 清单与 Backend 快照均保留完整入口信息，文案不参与导入裁决。 */
function moduleResolver(paths = [allowed], version = '1.0.0'): RuntimeModuleResolverConfig {
  return {
    runtime_kit_manifest_version: version,
    runtime_kit_exports: paths.map(import_path => ({ kind: 'util', name: 'fixture.v1', category: 'test', import_path })),
  }
}

beforeAll(async () => {
  tempRoot = await mkdtemp(join(tmpdir(), 'runtime-kit-gate-'))
  await writeFixture('index.html', '<script type="module" src="/src/views/Page.ts"></script>')
  await writeFixture('tailwind.config.js', 'export default { content: [], theme: {}, plugins: [] }')
  await writeFixture('src/runtime-kit/public/utils/allowed.v1.ts', 'export const value = 1')
  await writeFixture('src/runtime-kit/public/utils/other.v1.ts', 'export const value = 2')
  await writeFixture('src/runtime-kit/internal/private.ts', 'export const value = 3')
  await writeFixture('src/core/trusted.ts', "export { value } from '@runtime-kit/internal/private'")
  await writeFixture('src/runtime-kit/manifest/runtime-kit.manifest.json', JSON.stringify({
    version: '1.0.0', exports: [allowed, other].map(import_path => ({ import_path })),
  }))
  await symlink(resolve(process.cwd(), 'node_modules'), join(tempRoot, 'node_modules'), process.platform === 'win32' ? 'junction' : 'dir')
  persistent = new RuntimeDiagnosticsWorker({ tempRoot, timeoutMs: 30_000 })
})

afterAll(async () => {
  await persistent?.close()
  if (tempRoot) await rm(tempRoot, { recursive: true, force: true })
})

describe.each(['project', 'diagnostics', 'persistent'] as const)('真实 %s Worker Kit 门禁', mode => {
  /** 将同一快照送入不同执行面，验证 IPC 与非复用子进程没有丢失权限或版本。 */
  async function compile(source: string, resolver?: RuntimeModuleResolverConfig, entry = 'src/views/Page.ts') {
    await writeFixture('index.html', `<script type="module" src="/${entry}"></script>`)
    await writeFixture('src/views/Page.ts', `import { value } from '${source}'; console.log(value)`)
    if (mode === 'persistent') return persistent.run('./', 30_000, resolver)
    return runRuntimeViteBuildInWorker({
      tempRoot, base: './', mode, outDir: join(tempRoot, 'dist'), timeoutMs: 30_000,
      runtimeKitAllowedImports: resolver?.runtime_kit_exports?.map(item => item.import_path),
      runtimeKitManifestVersion: resolver?.runtime_kit_manifest_version,
      signal: new AbortController().signal,
    })
  }

  it('放行公开入口和可信 Runtime 内部依赖', async () => {
    await expect(compile(allowed, moduleResolver())).resolves.toBeUndefined()
    await expect(compile(allowed, moduleResolver(), 'src/core/trusted.ts')).resolves.toBeUndefined()
  }, 30_000)

  it.each([
    '@runtime-kit/internal/private', '@/runtime-kit/internal/private', '../runtime-kit/internal/private',
    '@runtime-kit/public/utils/allowed', other, '@runtime-kit/../core/trusted', '@/core/trusted',
  ])('拒绝 alias 和相对路径绕过：%s', async source => {
    await expect(compile(source, moduleResolver())).rejects.toMatchObject({ code: 'RUNTIME_LOCAL_IMPORT_FORBIDDEN' })
  }, 30_000)

  it('显式空快照和错误版本均拒绝，后续任务能恢复合法快照', async () => {
    await expect(compile(allowed, moduleResolver([]))).rejects.toMatchObject({ code: 'RUNTIME_LOCAL_IMPORT_FORBIDDEN' })
    await expect(compile(allowed, moduleResolver([allowed], 'other'))).rejects.toMatchObject({ code: 'RUNTIME_LOCAL_IMPORT_FORBIDDEN' })
    await expect(compile(allowed, moduleResolver())).resolves.toBeUndefined()
  }, 30_000)
})

it('本地清单丢失时，即使有 Backend 快照也不能放行；缺省快照只在本地清单有效时回退', async () => {
  await writeFixture('index.html', '<script type="module" src="/src/views/Page.ts"></script>')
  await writeFixture('src/views/Page.ts', `import { value } from '${allowed}'; console.log(value)`)
  await expect(persistent.run()).resolves.toBeUndefined()
  await writeFixture('src/runtime-kit/manifest/runtime-kit.manifest.json', 'invalid-json')
  await expect(persistent.run('./', 30_000, moduleResolver()))
    .rejects.toMatchObject({ code: 'RUNTIME_LOCAL_IMPORT_FORBIDDEN' })
}, 30_000)
