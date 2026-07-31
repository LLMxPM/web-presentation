/**
 * 文件功能：注册页面可视化编辑的专用组件检查器，并按组件 schema 严格选择对应实现。
 */

import type { PageVisualEditComponentSchema } from '@/types/page-visual-edit'

export type PageVisualEditComponentInspectorKey = 'asset-image-v1'

/** AssetImage.v1 允许由图片框样式入口修改的 Tailwind 冲突组。 */
export const ASSET_IMAGE_STYLE_GROUP_KEYS = [
  'width',
  'height',
  'size',
  'padding',
  'padding-x',
  'padding-y',
  'background-color',
  'border-width',
  'border-style',
  'border-color',
  'radius',
] as const

/** AssetImage.v1 专用检查器认识且允许写回的内容 prop。 */
export const ASSET_IMAGE_PROP_NAMES = ['name', 'alt', 'fit', 'position'] as const

interface PageVisualEditComponentInspectorRegistration {
  key: PageVisualEditComponentInspectorKey
  source: PageVisualEditComponentSchema['source']
  componentCode: string
  versionNo: number
}

const componentInspectorRegistrations: PageVisualEditComponentInspectorRegistration[] = [
  {
    key: 'asset-image-v1',
    source: 'runtime_kit',
    componentCode: 'AssetImage',
    versionNo: 1,
  },
]

/**
 * 按来源、组件编码和钉住版本精确匹配专用检查器。
 * 标签名和 import path 不参与降级猜测，避免同名工作空间组件误用专用写回规则。
 */
export function resolvePageVisualEditComponentInspector(
  schema: PageVisualEditComponentSchema | null,
): PageVisualEditComponentInspectorKey | null {
  if (!schema) return null
  return componentInspectorRegistrations.find(registration => (
    registration.source === schema.source
    && registration.componentCode === schema.component_code
    && registration.versionNo === schema.version_no
  ))?.key ?? null
}
