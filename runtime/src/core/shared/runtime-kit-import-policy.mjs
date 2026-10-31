/** 文件功能：预览、构建和诊断共用的纯 JavaScript Kit 导入策略，Worker 直接嵌入本文件源码。 */

/** 折叠路径中的点段，保留盘符；不依赖宿主操作系统的路径规则。 */
function normalizeKitPath(path) {
  const parts = []
  for (const part of path.split('/')) {
    if (!part || part === '.') continue
    if (part === '..') parts.pop()
    else parts.push(part)
  }
  return `${path.startsWith('/') ? '/' : ''}${parts.join('/')}`
}

/** 将已展开或逻辑路径还原到 src；用于识别穿出 Kit 后进入其它私有目录的导入。 */
export function normalizeRuntimeLocalModulePath(rawPath, runtimeRoot = '', importer = '') {
  const source = String(rawPath || '').trim().replace(/\\/g, '/')
  let path = source.replace(/^\/@fs\//, '')
  if (path.startsWith('@runtime-kit/')) path = `src/runtime-kit/${path.slice('@runtime-kit/'.length)}`
  else if (path.startsWith('@/')) path = `src/${path.slice(2)}`
  if (path.startsWith('./') || path.startsWith('../')) {
    const parent = String(importer).replace(/\\/g, '/').split(/[?#]/, 1)[0]
    path = `${parent.slice(0, parent.lastIndexOf('/') + 1)}${path}`
  }
  path = normalizeKitPath(path)
  const root = normalizeKitPath(String(runtimeRoot).replace(/\\/g, '/')).replace(/\/$/, '')
  const prefix = `${root}/`
  const windowsPath = /^[A-Za-z]:/.test(root)
  if (root && (windowsPath ? path.toLowerCase().startsWith(prefix.toLowerCase()) : path.startsWith(prefix))) {
    path = path.slice(prefix.length)
    if (windowsPath && path.slice(0, 4).toLowerCase() === 'src/') path = `src/${path.slice(4)}`
  }
  if (path.startsWith('/src/')) path = path.slice(1)
  return path.startsWith('src/') ? path : ''
}

/** 把 alias、Vite 绝对路径和相对路径统一还原为 Kit 地址；其它模块返回空串。 */
export function normalizeRuntimeKitImportPath(rawPath, runtimeRoot = '', importer = '') {
  const source = String(rawPath || '').trim().replace(/\\/g, '/')
  const path = normalizeRuntimeLocalModulePath(source, runtimeRoot, importer)
  if (path.startsWith('src/runtime-kit/')) return `@runtime-kit/${path.slice('src/runtime-kit/'.length)}`
  // 原始 Kit alias 穿出自身目录时保持拒绝语义，不能退化成普通包导入。
  return source === '@runtime-kit' || source.startsWith('@runtime-kit/') ? '@runtime-kit' : ''
}

/** 与 Backend 一致，只接受带整数版本后缀的公开入口。 */
export function isVersionedRuntimeKitImportPath(path) {
  return /\.v\d+(?:\.[A-Za-z0-9]+)?$/.test(String(path || '').trim())
}

/** 从声明中收集 Kit 地址；显式空数组保持为空，不扩大权限。 */
export function collectRuntimeKitAllowedImportPaths(entries) {
  return new Set((entries || []).map(item => normalizeRuntimeKitImportPath(item?.import_path)).filter(Boolean))
}

/** 创建只读裁决器；Backend 快照可收紧本地清单，空白名单与无法核实的版本均拒绝。 */
export function createRuntimeKitImportGate(options = {}) {
  const usingBackendSnapshot = Array.isArray(options.runtimeKitExports)
  const localPaths = collectRuntimeKitAllowedImportPaths(options.localManifestExports)
  const allowedPaths = usingBackendSnapshot
    ? collectRuntimeKitAllowedImportPaths(options.runtimeKitExports)
    : localPaths
  if (usingBackendSnapshot && Array.isArray(options.localManifestExports)) {
    for (const path of allowedPaths) if (!localPaths.has(path)) allowedPaths.delete(path)
  }
  const versionMismatch = Boolean(options.expectedManifestVersion
    && options.expectedManifestVersion !== options.localManifestVersion)

  /** 在 alias 展开后仍按同一入口检查，返回统一错误原因供各执行面投影。 */
  function decide(rawPath, importer = '') {
    const importPath = normalizeRuntimeKitImportPath(rawPath, options.runtimeRoot, importer)
    if (!importPath) {
      const local = normalizeRuntimeLocalModulePath(rawPath, options.runtimeRoot, importer)
      if (local && !['src/views/', 'src/workspace-components/', 'src/examples/local/views/'].some(prefix => local.startsWith(prefix))) {
        return { allowed: false, importPath: String(rawPath), reason: `创作源码不允许导入 Runtime 私有模块：${local}` }
      }
      return { allowed: true, importPath: String(rawPath || '') }
    }
    let reason
    if (versionMismatch) {
      reason = `Runtime Kit manifest 版本不匹配：期望 ${options.expectedManifestVersion}，本地 ${options.localManifestVersion || 'unknown'}`
    } else if (['/internal/', '/runtime-shell/', '/component-preview', '/PDF'].some(part => importPath.includes(part))) {
      reason = `Runtime Kit 不允许导入内部路径：${importPath}`
    } else if (!isVersionedRuntimeKitImportPath(importPath)) {
      reason = `Runtime Kit 导入必须带 .vN 版本后缀：${importPath}`
    } else if (!allowedPaths.has(importPath)) {
      reason = `Runtime Kit 导入不在公开白名单中：${importPath}`
    }
    return reason ? { allowed: false, importPath, reason } : { allowed: true, importPath }
  }
  return { decide, allowedPaths, usingBackendSnapshot, versionMismatch }
}
