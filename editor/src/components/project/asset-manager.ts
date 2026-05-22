/**
 * 文件功能：提供资源管理面板的上传格式过滤、文本资源模板与文件构造辅助函数。
 */
import type { AssetResponse, AssetType } from '@/types/api'
import { getAnalysisStatusLabel, getIconStyleLabel, getRenderModeLabel, isStrokeWidthEditable } from '@/utils/assetAnalysis'

export const ASSET_GROUPS: { key: string; label: string; types: { label: string; value: AssetType }[] }[] = [
  {
    key: 'foundation',
    label: '图标资源',
    types: [
      { label: '图标', value: 'icon' },
    ],
  },
  {
    key: 'content',
    label: '内容资源',
    types: [
      { label: '图片', value: 'image' },
      { label: '视频', value: 'video' },
      { label: 'DrawIO', value: 'drawio' },
      { label: 'Mermaid', value: 'mermaid' },
      { label: '图表', value: 'chart' },
      { label: '公式', value: 'formula' },
    ],
  },
]

export const ASSET_ALLOWED_EXTENSIONS: Record<AssetType, string[]> = {
  icon: ['.svg', '.png', '.jpg', '.jpeg', '.webp', '.gif'],
  font: ['.woff2', '.woff', '.ttf', '.otf'],
  image: ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg'],
  video: ['.mp4', '.webm', '.ogg', '.ogv', '.mov', '.m4v'],
  drawio: ['.drawio', '.xml'],
  mermaid: ['.mmd', '.mermaid', '.txt'],
  chart: ['.json', '.yaml', '.yml'],
  formula: ['.tex', '.txt'],
}

const ASSET_ACCEPT_MIME_TYPES: Record<AssetType, string[]> = {
  icon: ['image/svg+xml', 'image/png', 'image/jpeg', 'image/webp', 'image/gif'],
  font: ['font/woff2', 'font/woff', 'font/ttf', 'font/otf'],
  image: ['image/png', 'image/jpeg', 'image/webp', 'image/gif', 'image/svg+xml'],
  video: ['video/mp4', 'video/webm', 'video/ogg', 'video/quicktime'],
  drawio: ['application/xml', 'text/xml', 'text/plain'],
  mermaid: ['text/plain'],
  chart: ['application/json', 'text/yaml', 'text/plain'],
  formula: ['text/plain'],
}

export const ASSET_UPLOAD_ACCEPT: Record<AssetType, string> = {
  icon: [...ASSET_ALLOWED_EXTENSIONS.icon, ...ASSET_ACCEPT_MIME_TYPES.icon].join(','),
  font: [...ASSET_ALLOWED_EXTENSIONS.font, ...ASSET_ACCEPT_MIME_TYPES.font].join(','),
  image: [...ASSET_ALLOWED_EXTENSIONS.image, ...ASSET_ACCEPT_MIME_TYPES.image].join(','),
  video: [...ASSET_ALLOWED_EXTENSIONS.video, ...ASSET_ACCEPT_MIME_TYPES.video].join(','),
  drawio: [...ASSET_ALLOWED_EXTENSIONS.drawio, ...ASSET_ACCEPT_MIME_TYPES.drawio].join(','),
  mermaid: [...ASSET_ALLOWED_EXTENSIONS.mermaid, ...ASSET_ACCEPT_MIME_TYPES.mermaid].join(','),
  chart: [...ASSET_ALLOWED_EXTENSIONS.chart, ...ASSET_ACCEPT_MIME_TYPES.chart].join(','),
  formula: [...ASSET_ALLOWED_EXTENSIONS.formula, ...ASSET_ACCEPT_MIME_TYPES.formula].join(','),
}

export const TEXT_CREATABLE_ASSET_TYPES: AssetType[] = ['icon', 'image', 'drawio', 'mermaid', 'chart', 'formula']

const TEXT_ASSET_DEFAULTS: Record<AssetType, { fileName: string; contentType: string; content: string }> = {
  icon: { fileName: 'icon.svg', contentType: 'image/svg+xml', content: '<svg></svg>' },
  font: { fileName: 'font.woff2', contentType: 'font/woff2', content: '' },
  image: { fileName: 'image.svg', contentType: 'image/svg+xml', content: '<svg></svg>' },
  video: { fileName: 'video.mp4', contentType: 'video/mp4', content: '' },
  drawio: {
    fileName: 'diagram.drawio',
    contentType: 'text/plain',
    content: '<mxfile><diagram name="Page-1"></diagram></mxfile>',
  },
  mermaid: {
    fileName: 'diagram.mmd',
    contentType: 'text/plain',
    content: 'flowchart TD\n  A[开始] --> B[结束]',
  },
  chart: {
    fileName: 'chart.json',
    contentType: 'application/json',
    content: '{\n  "title": { "text": "示例图表" },\n  "series": []\n}',
  },
  formula: {
    fileName: 'formula.tex',
    contentType: 'text/plain',
    content: 'E = mc^2',
  },
}

/**
 * 获取指定资源类型的文本创建默认值。
 * @param assetType 当前选择的资源类型
 * @returns 默认文件名、MIME 类型和文本内容
 */
export function getTextAssetDefaults(assetType: AssetType) {
  return TEXT_ASSET_DEFAULTS[assetType]
}

/**
 * 根据文本表单构造可复用现有上传接口的 File。
 * @param fileName 文件展示名
 * @param content 文本内容
 * @param assetType 当前资源类型
 * @returns 浏览器 File 对象
 */
export function buildTextAssetFile(fileName: string, content: string, assetType: AssetType): File {
  const defaults = getTextAssetDefaults(assetType)
  return new File([content], fileName, { type: defaults.contentType })
}

/**
 * 判断文件扩展名是否符合资源类型限制。
 * @param file 待上传或替换的浏览器文件对象
 * @param assetType 当前资源类型
 * @returns 扩展名命中允许列表时返回 true
 */
export function isAcceptedAssetFile(file: File, assetType: AssetType): boolean {
  const fileName = file.name.trim().toLowerCase()
  return ASSET_ALLOWED_EXTENSIONS[assetType].some(ext => fileName.endsWith(ext))
}

/**
 * 生成面向用户的扩展名限制文案。
 * @param assetType 当前资源类型
 * @returns 中文逗号分隔的扩展名列表
 */
export function getAcceptedAssetExtensionText(assetType: AssetType): string {
  return ASSET_ALLOWED_EXTENSIONS[assetType].join('、')
}

/**
 * 生成图标卡片上的紧凑状态文案，避免卡片正文展示完整分析细节。
 * @param asset 当前资源
 * @returns 图标渲染能力的短标签
 */
export function getCompactIconLabel(asset: AssetResponse) {
  return isStrokeWidthEditable(asset.analysis_metadata) ? '可调描边' : getIconStyleLabel(asset.analysis_metadata)
}

/**
 * 生成图标状态的悬停说明，保留完整分析信息供需要时查看。
 * @param asset 当前资源
 * @returns 图标分析摘要
 */
export function getIconSummaryTitle(asset: AssetResponse) {
  return [
    getAnalysisStatusLabel(asset.analysis_metadata),
    getRenderModeLabel(asset.analysis_metadata),
    getIconStyleLabel(asset.analysis_metadata),
    isStrokeWidthEditable(asset.analysis_metadata) ? '支持描边宽度' : '不支持描边宽度',
  ].join(' / ')
}
