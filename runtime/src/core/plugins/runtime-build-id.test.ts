/** 文件用途：验证发布身份覆盖源码/锁文件、可重复构建及缺失身份时的启动拒绝。 */
// @vitest-environment node
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { computeRuntimeBuildId } from '../../../scripts/write-runtime-build-id.mjs'

const image = vi.hoisted(() => ({ buildId: undefined as string | undefined }))
vi.mock('node:fs', async importOriginal => {
  const fs = await importOriginal<typeof import('node:fs')>()
  return {
    ...fs,
    readFileSync: (...args: Parameters<typeof fs.readFileSync>) => {
      if (String(args[0]).endsWith('/.runtime-build-id')) {
        if (image.buildId === undefined) throw new Error('测试镜像缺发布身份')
        return image.buildId
      }
      return fs.readFileSync(...args)
    },
  }
})

const fixtures: string[] = []

/** 构造两种构建目录都能消费的最小 Runtime 发布输入，不读取工作区私有配置。 */
function fixture() {
  const root = mkdtempSync(join(tmpdir(), 'wp-build-id-'))
  fixtures.push(root)
  for (const dir of ['src', 'public', 'scripts']) mkdirSync(join(root, dir))
  for (const path of ['src/main.ts', 'public/config.yaml', 'scripts/build.mjs', 'package.json', 'vite.config.ts',
    'index.html', 'postcss.config.js', 'tailwind.config.js', 'tsconfig.json']) {
    writeFileSync(join(root, path), `same-input:${path}`)
  }
  const lock = join(root, 'lock.yaml')
  writeFileSync(lock, 'same-lock')
  return { root, lock }
}

beforeEach(() => {
  vi.resetModules()
  vi.stubEnv('RUNTIME_BUILD_ID', '')
  vi.stubEnv('RUNTIME_RELEASE_ID_REQUIRED', 'false')
  image.buildId = undefined
})

afterEach(() => {
  vi.unstubAllEnvs()
  for (const root of fixtures.splice(0)) rmSync(root, { recursive: true, force: true })
})

describe('Runtime 发布身份', () => {
  it('相同发布输入在不同目录重复构建得到同一身份，测试文件不影响发布', () => {
    const first = fixture()
    const second = fixture()
    writeFileSync(join(second.root, 'src/extra.test.ts'), 'test-only')
    const id = computeRuntimeBuildId(first.root, first.lock)
    expect(id).toMatch(/^sha256-[0-9a-f]{64}$/)
    expect(computeRuntimeBuildId(second.root, second.lock)).toBe(id)
  })

  it('源码、模块路径或锁文件变化都会改变发布身份', () => {
    const { root, lock } = fixture()
    const original = computeRuntimeBuildId(root, lock)
    writeFileSync(join(root, 'src/main.ts'), 'changed-source')
    const changed = computeRuntimeBuildId(root, lock)
    expect(changed).not.toBe(original)
    writeFileSync(lock, 'changed-lock')
    const changedLock = computeRuntimeBuildId(root, lock)
    expect(changedLock).not.toBe(changed)
    writeFileSync(join(root, 'src/extra.ts'), 'new-module')
    const extraModule = computeRuntimeBuildId(root, lock)
    expect(extraModule).not.toBe(changedLock)
    writeFileSync(join(root, 'tailwind.config.js'), 'changed-style-config')
    expect(computeRuntimeBuildId(root, lock)).not.toBe(extraModule)
  })

  it('镜像默认使用内置身份，同版副本实例名不同也不会改变版本指纹', async () => {
    image.buildId = 'sha256-built-image\n'
    const identity = await import('./runtime-version-identity')
    expect(identity.resolveRuntimeBuildId()).toBe('sha256-built-image')
    const before = identity.formatRuntimeVersionFingerprint()
    vi.stubEnv('RUNTIME_INSTANCE_ID', 'replica-two')
    expect(identity.formatRuntimeVersionFingerprint()).toBe(before)
    vi.stubEnv('RUNTIME_BUILD_ID', 'release-override')
    expect(identity.resolveRuntimeBuildId()).toBe('release-override')
  })

  it('本地可用 dev，交付镜像缺身份必须拒绝而不能静默退回 dev', async () => {
    const identity = await import('./runtime-version-identity')
    expect(identity.resolveRuntimeBuildId()).toBe('dev')
    vi.stubEnv('RUNTIME_RELEASE_ID_REQUIRED', 'true')
    expect(() => identity.resolveRuntimeBuildId()).toThrow('缺少构建身份')
  })
})
