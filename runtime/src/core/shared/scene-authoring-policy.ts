/** 文件功能：限定页面与工作空间组件通过 Scene 门面使用 GSAP，供预览和构建检查共享导入规则。 */
export const SCENE_AUTHORING_POLICY_VERSION = 'page-scene-authoring.v1'
export const SCENE_GSAP_IMPORT_MESSAGE = '页面与组件请通过 usePageScene.v1 创建视觉序列；不支持直接导入 GSAP 或插件。'
const FORBIDDEN = /^(?:gsap(?:-trial)?(?:\/|$)|@gsap(?:\/|$))/i
const AUTHORED = /(?:^|\/)src\/(?:views|workspace-components|examples\/local\/views)\//

/** 统一路径分隔符与查询后缀，避免插件通过 Vite 查询参数绕过规则。 */
function normalize(source: string): string {
  return source.trim().replace(/\\/g, '/').split(/[?#]/, 1)[0] ?? ''
}

/** 所有 GSAP 包入口由受管门面代持，平台内部实现不受此导入规则限制。 */
export function isForbiddenSceneImport(source: string): boolean { return FORBIDDEN.test(normalize(source)) }

/** 只限制用户模块及本地创作样例，允许 Runtime Kit 自身依赖 GSAP。 */
export function isAuthoredSceneModule(importer: string): boolean { return AUTHORED.test(normalize(importer)) }

/** Worker 不能导入宿主 TS；从同一正则生成纯 JS，避免诊断与构建各自复制策略。 */
export function createSceneImportPolicySource(): string {
  return [
    `const sceneForbiddenImport = new RegExp(${JSON.stringify(FORBIDDEN.source)}, 'i')`,
    `const sceneAuthoredModule = new RegExp(${JSON.stringify(AUTHORED.source)})`,
    `const sceneImportMessage = ${JSON.stringify(SCENE_GSAP_IMPORT_MESSAGE)}`,
    `function normalizeSceneImport(source) { return String(source || '').trim().replace(/\\\\/g, '/').split(/[?#]/, 1)[0] || '' }`,
    'function rejectSceneImport(source, importer) { return sceneAuthoredModule.test(normalizeSceneImport(importer)) && sceneForbiddenImport.test(normalizeSceneImport(source)) }',
  ].join('\n')
}
