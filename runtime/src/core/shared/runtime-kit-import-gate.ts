/**
 * 文件用途：Runtime Kit 导入白名单门禁——构建端与预览端共用的第二道闸。
 *
 * Backend 写路径已按 manifest 校验；本模块在 Runtime 构建/预览解析时再次强制：
 * 拒绝 `internal/`、未版本化路径，以及不在白名单中的 `@runtime-kit` 导入。
 * 白名单优先取 Backend `module_resolver.runtime_kit_exports`（写路径已验证的快照），
 * 缺省时回落到本地 Runtime Kit manifest。
 */

export interface RuntimeKitExportEntry {
  kind?: string
  name?: string
  import_path: string
  category?: string
  description?: string
}

export interface RuntimeKitImportGateOptions {
  /** Backend 下发的 runtime_kit_exports 快照；优先于本地 manifest。 */
  runtimeKitExports?: RuntimeKitExportEntry[]
  /** 本地 manifest exports；无 Backend 快照时使用。 */
  localManifestExports?: RuntimeKitExportEntry[]
  /** 期望的 manifest 版本；提供时与本地版本比对，不一致则拒绝。 */
  expectedManifestVersion?: string
  /** 本地 manifest 版本。 */
  localManifestVersion?: string
}

export type RuntimeKitImportDecision =
  | { allowed: true; importPath: string; reason?: undefined }
  | { allowed: false; importPath: string; reason: string }

const RUNTIME_KIT_ALIAS = '@runtime-kit'
const VERSIONED_SUFFIX_PATTERN = /\.v\d+(?:\.[A-Za-z0-9]+)?$/
/** 永远不得通过 `@runtime-kit` 暴露给页面/组件源码的路径片段。 */
const FORBIDDEN_PATH_FRAGMENTS = [
  '/internal/',
  '/runtime-shell/',
  '/component-preview',
  '/PDF',
]

/**
 * 把 `@runtime-kit/...` 导入路径规范化；非 kit 导入返回空串。
 */
export function normalizeRuntimeKitImportPath(rawPath: string): string {
  const normalized = String(rawPath || '').trim().replace(/\\/g, '/')
  if (!normalized.startsWith(`${RUNTIME_KIT_ALIAS}/`)) {
    return ''
  }
  return normalized
}

/**
 * 判断 import_path 是否带 `.vN` 版本后缀（与 Backend runtime_module_policy 同规则）。
 */
export function isVersionedRuntimeKitImportPath(importPath: string): boolean {
  return VERSIONED_SUFFIX_PATTERN.test(String(importPath || '').trim())
}

/**
 * 从导出条目收集合法 `@runtime-kit/...` import_path 集合。
 */
export function collectRuntimeKitAllowedImportPaths(
  exports: RuntimeKitExportEntry[] | undefined,
): Set<string> {
  const allowed = new Set<string>()
  for (const item of exports || []) {
    const path = normalizeRuntimeKitImportPath(item?.import_path || '')
    if (path) {
      allowed.add(path)
    }
  }
  return allowed
}

/**
 * 构建 Runtime Kit 导入门禁。返回对单条 import 的裁决函数。
 */
export function createRuntimeKitImportGate(options: RuntimeKitImportGateOptions = {}) {
  const {
    runtimeKitExports,
    localManifestExports,
    expectedManifestVersion,
    localManifestVersion,
  } = options

  const usingBackendSnapshot = Array.isArray(runtimeKitExports) && runtimeKitExports.length > 0
  const allowedPaths = collectRuntimeKitAllowedImportPaths(
    usingBackendSnapshot ? runtimeKitExports : localManifestExports,
  )

  // Backend 快照与本地 manifest 版本必须一致，否则白名单可能对不上实际文件。
  const versionMismatch = Boolean(
    expectedManifestVersion
    && localManifestVersion
    && expectedManifestVersion !== localManifestVersion,
  )

  function decide(rawImportPath: string): RuntimeKitImportDecision {
    const importPath = normalizeRuntimeKitImportPath(rawImportPath)
    if (!importPath) {
      return { allowed: true, importPath: String(rawImportPath || '') }
    }

    if (versionMismatch) {
      return {
        allowed: false,
        importPath,
        reason: `Runtime Kit manifest 版本不匹配：期望 ${expectedManifestVersion}，本地 ${localManifestVersion}`,
      }
    }

    for (const fragment of FORBIDDEN_PATH_FRAGMENTS) {
      if (importPath.includes(fragment)) {
        return {
          allowed: false,
          importPath,
          reason: `Runtime Kit 不允许导入内部路径：${importPath}`,
        }
      }
    }

    if (!isVersionedRuntimeKitImportPath(importPath)) {
      return {
        allowed: false,
        importPath,
        reason: `Runtime Kit 导入必须带 .vN 版本后缀：${importPath}`,
      }
    }

    if (!allowedPaths.has(importPath)) {
      return {
        allowed: false,
        importPath,
        reason: `Runtime Kit 导入不在公开白名单中：${importPath}`,
      }
    }

    return { allowed: true, importPath }
  }

  return {
    decide,
    allowedPaths,
    usingBackendSnapshot,
    versionMismatch,
  }
}

/**
 * 便捷断言：不允许时抛出带错误码的 Error，供 Vite resolveId / load 钩子使用。
 */
export function assertRuntimeKitImportAllowed(
  rawImportPath: string,
  gate: ReturnType<typeof createRuntimeKitImportGate>,
): string {
  const decision = gate.decide(rawImportPath)
  if (decision.allowed === false) {
    const error = new Error(decision.reason)
    ;(error as Error & { code?: string }).code = 'RUNTIME_LOCAL_IMPORT_FORBIDDEN'
    throw error
  }
  return decision.importPath
}

/**
 * 从 Backend module_resolver 构建收紧后的 Runtime Kit 门禁。
 * 消费 `runtime_kit_exports` 快照，与写路径校验边界保持一致。
 */
export function createRuntimeKitGateFromModuleResolver(moduleResolver?: {
  runtime_kit_exports?: RuntimeKitExportEntry[]
}): ReturnType<typeof createRuntimeKitImportGate> {
  const options: RuntimeKitImportGateOptions = {}
  if (moduleResolver?.runtime_kit_exports?.length) {
    options.runtimeKitExports = moduleResolver.runtime_kit_exports
  }
  return createRuntimeKitImportGate(options)
}
