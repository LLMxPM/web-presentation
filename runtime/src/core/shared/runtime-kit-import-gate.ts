/** 文件功能：为预览侧提供共享 Kit 导入策略的类型化入口与 Backend 配置适配。 */
import localManifest from '../../runtime-kit/manifest/runtime-kit.manifest.json'
import * as policy from './runtime-kit-import-policy.mjs'

export interface RuntimeKitExportEntry {
  kind?: string
  name?: string
  import_path: string
  category?: string
  description?: string
}

export interface RuntimeKitImportGateOptions {
  /** Backend 快照；缺省回退本地，显式空数组拒绝所有 Kit 导入。 */
  runtimeKitExports?: RuntimeKitExportEntry[]
  localManifestExports?: RuntimeKitExportEntry[]
  expectedManifestVersion?: string
  localManifestVersion?: string
  /** Vite 根目录，用于还原 alias 展开后的绝对路径。 */
  runtimeRoot?: string
}

export type RuntimeKitImportDecision =
  | { allowed: true; importPath: string; reason?: undefined }
  | { allowed: false; importPath: string; reason: string }

export interface RuntimeKitImportGate {
  decide: (source: string, importer?: string) => RuntimeKitImportDecision
  allowedPaths: Set<string>
  usingBackendSnapshot: boolean
  versionMismatch: boolean
}

/** 识别当前 Runtime 的本地目录，避免 Kit alias 穿出后被当作普通导入放行。 */
export function normalizeRuntimeLocalModulePath(source: string, runtimeRoot?: string, importer?: string): string {
  return policy.normalizeRuntimeLocalModulePath(source, runtimeRoot, importer)
}

/** 将原始导入或展开后的路径还原为 Kit 地址，其它模块返回空串。 */
export function normalizeRuntimeKitImportPath(source: string, runtimeRoot?: string, importer?: string): string {
  return policy.normalizeRuntimeKitImportPath(source, runtimeRoot, importer)
}

/** 判断入口是否包含受支持的整数版本后缀。 */
export function isVersionedRuntimeKitImportPath(path: string): boolean {
  return policy.isVersionedRuntimeKitImportPath(path)
}

/** 收集公开入口；空输入保持为空，交由门禁拒绝。 */
export function collectRuntimeKitAllowedImportPaths(entries?: RuntimeKitExportEntry[]): Set<string> {
  return policy.collectRuntimeKitAllowedImportPaths(entries)
}

/** 创建与 Worker 同源的纯策略裁决器。 */
export function createRuntimeKitImportGate(options: RuntimeKitImportGateOptions = {}): RuntimeKitImportGate {
  return policy.createRuntimeKitImportGate(options)
}

/** 将统一拒绝结果转为 Vite 可携带的稳定错误码。 */
export function assertRuntimeKitImportAllowed(source: string, gate: RuntimeKitImportGate, importer?: string): string {
  const decision = gate.decide(source, importer)
  if (!decision.allowed) {
    throw Object.assign(new Error(decision.reason), { code: 'RUNTIME_LOCAL_IMPORT_FORBIDDEN' })
  }
  return decision.importPath
}

/** 使用 Backend 快照收紧真实本地清单，并核实其声明的版本。 */
export function createRuntimeKitGateFromModuleResolver(moduleResolver?: {
  runtime_kit_exports?: RuntimeKitExportEntry[]
  runtime_kit_manifest_version?: string
}, runtimeRoot?: string): RuntimeKitImportGate {
  return createRuntimeKitImportGate({
    runtimeKitExports: moduleResolver?.runtime_kit_exports,
    expectedManifestVersion: moduleResolver?.runtime_kit_manifest_version,
    localManifestExports: localManifest.exports,
    localManifestVersion: localManifest.version,
    runtimeRoot,
  })
}
