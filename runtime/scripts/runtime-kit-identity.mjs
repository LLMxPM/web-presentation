/** 文件功能：从 Kit 清单投影执行身份，剔除目录文案并保留预览 Schema、引擎策略和未知字段。 */

/** 只忽略已确认不参与执行的目录字段；新增未知字段默认进入身份，避免漏失效缓存。 */
export function projectRuntimeKitExecutionManifest(manifest) {
  const identity = structuredClone(manifest)
  for (const entry of identity.exports || []) {
    delete entry.category
    delete entry.description
    if (!entry.capability || typeof entry.capability !== 'object') continue
    for (const key of ['enabled', 'previewable', 'display_name', 'summary', 'tags', 'usage', 'returns', 'return_example', 'constraints', 'audiences']) {
      delete entry.capability[key]
    }
    if (!Object.keys(entry.capability).length) delete entry.capability
  }
  return identity
}
