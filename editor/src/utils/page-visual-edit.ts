/**
 * 文件功能：提供页面可视化编辑组件标签与 Backend previewSchema 的严格匹配规则。
 */

import type {
  PageVisualEditComponentPropField,
  PageVisualEditComponentSchema,
  PageVisualEditNode,
} from '@/types/page-visual-edit'

/**
 * 按组件本地导入名匹配 schema；只接受精确名称或标准 kebab-case 到 PascalCase 的确定转换。
 */
export function resolvePageVisualEditComponentSchema(
  node: PageVisualEditNode | null,
  schemas: Record<string, PageVisualEditComponentSchema>,
): PageVisualEditComponentSchema | null {
  if (!node || node.kind !== 'component') return null
  const exact = /^[A-Z][A-Za-z0-9]*$/.test(node.tag) ? schemas[node.tag] : null
  if (exact) return exact
  if (!/^[a-z][a-z0-9]*(?:-[a-z0-9]+)+$/.test(node.tag)) return null
  const pascalName = node.tag
    .split('-')
    .map(segment => `${segment.slice(0, 1).toUpperCase()}${segment.slice(1)}`)
    .join('')
  return schemas[pascalName] ?? null
}

/**
 * 匹配组件 prop schema；先使用精确名称，再仅执行标准 kebab-case 到 camelCase 转换。
 */
export function resolvePageVisualEditComponentPropField(
  schema: PageVisualEditComponentSchema | null,
  bindingName: string | null | undefined,
): PageVisualEditComponentPropField | null {
  if (!schema?.props || !bindingName) return null
  const exact = schema.props[bindingName]
  if (exact) return exact
  if (!/^[a-z][a-z0-9]*(?:-[a-z0-9]+)+$/.test(bindingName)) return null
  const [first = '', ...remaining] = bindingName.split('-')
  const camelName = first + remaining
    .map(segment => `${segment.slice(0, 1).toUpperCase()}${segment.slice(1)}`)
    .join('')
  return schema.props[camelName] ?? null
}
