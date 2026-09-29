/**
 * 文件用途：验证 Runtime Kit 导入白名单门禁——第二道闸拒绝 internal/、未版本化与非白名单路径。
 */

import { describe, expect, it } from 'vitest'

import manifest from '../../runtime-kit/manifest/runtime-kit.manifest.json'
import {
  assertRuntimeKitImportAllowed,
  collectRuntimeKitAllowedImportPaths,
  createRuntimeKitImportGate,
  createRuntimeKitGateFromModuleResolver,
  isVersionedRuntimeKitImportPath,
  normalizeRuntimeKitImportPath,
} from './runtime-kit-import-gate'

describe('runtime-kit-import-gate', () => {
  it('应拒绝 internal、runtime-shell 与未版本化路径', () => {
    const gate = createRuntimeKitImportGate({
      localManifestExports: manifest.exports.map(item => ({ import_path: item.import_path })),
    })

    expect(gate.decide('@runtime-kit/internal/renderers/latex.v1').allowed).toBe(false)
    expect(gate.decide('@runtime-kit/internal/components/viewport/ScaledCanvasViewport.vue').allowed).toBe(false)
    expect(gate.decide('@runtime-kit/runtime-shell/layouts/ResponsiveLayout.vue').allowed).toBe(false)
    expect(gate.decide('@runtime-kit/public/components/primitives/Icon.vue').allowed).toBe(false)
  })

  it('应放行 manifest 白名单中的版本化公开导入', () => {
    const gate = createRuntimeKitImportGate({
      localManifestExports: manifest.exports.map(item => ({ import_path: item.import_path })),
    })

    expect(gate.decide('@runtime-kit/public/components/primitives/Icon.v1.vue').allowed).toBe(true)
    expect(gate.decide('@runtime-kit/public/components/assets/AssetImage.v1.vue').allowed).toBe(true)
  })

  it('应拒绝不在 Backend runtime_kit_exports 快照中的导入', () => {
    const gate = createRuntimeKitImportGate({
      runtimeKitExports: [
        { import_path: '@runtime-kit/public/components/primitives/Icon.v1.vue' },
      ],
    })

    expect(gate.decide('@runtime-kit/public/components/primitives/Icon.v1.vue').allowed).toBe(true)
    expect(gate.decide('@runtime-kit/public/components/assets/AssetImage.v1.vue').allowed).toBe(false)
    expect(gate.usingBackendSnapshot).toBe(true)
  })

  it('manifest 版本不匹配时应拒绝全部 kit 导入', () => {
    const gate = createRuntimeKitImportGate({
      expectedManifestVersion: '2.0.0',
      localManifestVersion: '1.0.0',
      localManifestExports: manifest.exports.map(item => ({ import_path: item.import_path })),
    })

    const decision = gate.decide('@runtime-kit/public/components/primitives/Icon.v1.vue')
    expect(decision.allowed).toBe(false)
    if (decision.allowed === false) {
      expect(decision.reason).toContain('版本不匹配')
    }
  })

  it('非 kit 导入应直接放行', () => {
    const gate = createRuntimeKitImportGate({})
    expect(gate.decide('@/views/Home.vue').allowed).toBe(true)
    expect(gate.decide('./local.vue').allowed).toBe(true)
  })

  it('assertRuntimeKitImportAllowed 对违规导入抛出 RUNTIME_LOCAL_IMPORT_FORBIDDEN', () => {
    const gate = createRuntimeKitImportGate({
      localManifestExports: manifest.exports.map(item => ({ import_path: item.import_path })),
    })

    expect(() => assertRuntimeKitImportAllowed('@runtime-kit/internal/foo.v1', gate)).toThrow(/不允许导入内部路径/)
    try {
      assertRuntimeKitImportAllowed('@runtime-kit/internal/foo.v1', gate)
    } catch (error) {
      expect((error as Error & { code?: string }).code).toBe('RUNTIME_LOCAL_IMPORT_FORBIDDEN')
    }
  })

  it('工具函数应正确归一化与判定版本后缀', () => {
    expect(normalizeRuntimeKitImportPath('@runtime-kit/public/a.v1.ts')).toBe('@runtime-kit/public/a.v1.ts')
    expect(normalizeRuntimeKitImportPath('  @runtime-kit\\public\\a.v1.ts  ')).toBe('@runtime-kit/public/a.v1.ts')
    expect(normalizeRuntimeKitImportPath('@/views/x.vue')).toBe('')
    expect(isVersionedRuntimeKitImportPath('@runtime-kit/public/a.v1.ts')).toBe(true)
    expect(isVersionedRuntimeKitImportPath('@runtime-kit/public/a.v2.vue')).toBe(true)
    expect(isVersionedRuntimeKitImportPath('@runtime-kit/public/a.ts')).toBe(false)
  })

  it('collectRuntimeKitAllowedImportPaths 只收集合法 kit 路径', () => {
    const paths = collectRuntimeKitAllowedImportPaths([
      { import_path: '@runtime-kit/public/a.v1.ts' },
      { import_path: '@/not-kit' },
      { import_path: '' },
    ])
    expect([...paths]).toEqual(['@runtime-kit/public/a.v1.ts'])
  })

  it('createRuntimeKitGateFromModuleResolver 消费 runtime_kit_exports', () => {
    const gate = createRuntimeKitGateFromModuleResolver({
      runtime_kit_exports: [
        { kind: 'component', name: 'Icon.v1', import_path: '@runtime-kit/public/components/primitives/Icon.v1.vue', category: 'runtime' },
      ],
    })

    expect(gate.usingBackendSnapshot).toBe(true)
    expect(gate.decide('@runtime-kit/public/components/primitives/Icon.v1.vue').allowed).toBe(true)
    expect(gate.decide('@runtime-kit/public/components/assets/AssetImage.v1.vue').allowed).toBe(false)
  })
})
