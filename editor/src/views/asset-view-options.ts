/**
 * 文件功能：资源管理页的视图类型、筛选与表单静态选项，供 AssetsView 与测试共用。
 */
import type { AssetType } from '@/types/api'

export type AssetView = 'active' | 'archived' | 'history'
export type DetailTab = 'basic' | 'content' | 'references'
export type BackfillableAssetType = 'image' | 'video' | 'drawio' | 'mermaid' | 'formula'

export const BACKFILLABLE_ASSET_TYPES: BackfillableAssetType[] = [
  'image',
  'video',
  'drawio',
  'mermaid',
  'formula',
]

export interface AssetReferenceItem {
  kind: string
  id: number
  component_id?: number
  name?: string
  version_no?: number
}

export const VIEW_TABS: Array<{ value: AssetView; label: string }> = [
  { value: 'active', label: '启用' },
  { value: 'archived', label: '已归档' },
  { value: 'history', label: '历史' },
]

export const DETAIL_TABS: Array<{ value: DetailTab; label: string }> = [
  { value: 'basic', label: '基础信息' },
  { value: 'content', label: '内容编辑' },
  { value: 'references', label: '引用检查' },
]

export const ASSET_TYPE_OPTIONS: Array<{ value: AssetType; label: string }> = [
  { value: 'icon', label: '图标' },
  { value: 'image', label: '图片' },
  { value: 'video', label: '视频' },
  { value: 'drawio', label: 'Draw.io' },
  { value: 'mermaid', label: 'Mermaid' },
  { value: 'chart', label: 'Chart' },
  { value: 'formula', label: 'Formula' },
]

export const ASSET_SORT_OPTIONS = [
  { value: 'updated_at:desc', label: '最近更新' },
  { value: 'created_at:desc', label: '最近创建' },
  { value: 'name:asc', label: '名称升序' },
  { value: 'file_size:desc', label: '文件较大优先' },
]

export const ASSET_TYPE_SEGMENT_OPTIONS: Array<{ value: AssetType | ''; label: string }> = [
  { value: '', label: '全部' },
  ...ASSET_TYPE_OPTIONS,
]

export const CREATABLE_ASSET_TYPES = ASSET_TYPE_OPTIONS.filter(item =>
  ['icon', 'image', 'drawio', 'mermaid', 'chart', 'formula'].includes(item.value),
)

export const REFERENCE_GROUP_LABELS: Record<string, string> = {
  page: '页面',
  component: '组件草稿',
  component_version: '组件版本',
  theme: '主题',
  font: '字体配置',
}
