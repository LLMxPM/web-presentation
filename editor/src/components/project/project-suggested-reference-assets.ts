/**
 * 文件功能：提供项目建议资源弹窗可选择和上传的内容资源类型常量。
 */
import type { AssetType } from '@/types/api'

export type ProjectSuggestedReferenceAssetTabKey = 'all' | AssetType

export const PROJECT_SUGGESTED_REFERENCE_ASSET_TYPES: AssetType[] = [
  'image',
  'video',
  'drawio',
  'mermaid',
  'chart',
  'formula',
]
