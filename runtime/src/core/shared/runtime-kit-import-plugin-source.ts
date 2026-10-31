/** 文件功能：把共享 Kit 策略原样嵌入构建和诊断 Worker，避免维护第二份判断实现。 */
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createSceneImportPolicySource } from './scene-authoring-policy'

/** 读取纯 JS 策略并去掉模块导出；生成片段要求 Worker 顶层提供 readFile/resolve。 */
export function createRuntimeKitImportGatePluginSource(): string {
  const sourcePath = resolve(dirname(fileURLToPath(import.meta.url)), 'runtime-kit-import-policy.mjs')
  const policy = readFileSync(sourcePath, 'utf8')
    .replace(/^export /gm, '')
  return [
    policy,
    createSceneImportPolicySource(),
    'async function loadLocalRuntimeKitManifest(tempRoot) {',
    '  try {',
    '    return JSON.parse(await readFile(resolve(tempRoot, "src/runtime-kit/manifest/runtime-kit.manifest.json"), "utf8"))',
    '  } catch { return { exports: [] } }',
    '}',
    '/** 只限制创作模块；Runtime 内部实现可继续引用私有模块。 */',
    'function createRuntimeKitImportGatePlugin(allowedImports, tempRoot, expectedManifestVersion) {',
    '  let gatePromise',
    '  function ensureGate() {',
    '    return gatePromise ||= loadLocalRuntimeKitManifest(tempRoot).then(manifest => createRuntimeKitImportGate({',
    '      runtimeKitExports: allowedImports?.map(import_path => ({ import_path })),',
    '      localManifestExports: manifest.exports || [],',
    '      expectedManifestVersion, localManifestVersion: manifest.version, runtimeRoot: tempRoot,',
    '    }))',
    '  }',
    '  return {',
    '    name: "runtime-kit-import-gate", enforce: "pre",',
    '    async buildStart() { await ensureGate() },',
    '    async resolveId(source, importer) {',
    '      if (!sceneAuthoredModule.test(normalizeSceneImport(importer))) return null',
    '      if (rejectSceneImport(source, importer)) {',
    '        throw Object.assign(new Error(sceneImportMessage), { code: "SCENE_GSAP_IMPORT_FORBIDDEN" })',
    '      }',
    '      const decision = (await ensureGate()).decide(source, importer)',
    '      if (!decision.allowed) {',
    '        throw Object.assign(new Error(decision.reason), { code: "RUNTIME_LOCAL_IMPORT_FORBIDDEN" })',
    '      }',
    '      return null',
    '    },',
    '  }',
    '}',
  ].join('\n')
}
