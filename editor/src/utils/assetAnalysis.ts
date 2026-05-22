/**
 * 文件功能：统一封装图标资产分析元数据的展示文案与能力判断，供资源面板和主题编辑复用。
 */

import type { AssetAnalysisMetadata } from '@/types/api'

/**
 * 判断图标是否支持默认描边宽度。
 * @param analysis 资产分析元数据
 */
export function isStrokeWidthEditable(analysis: AssetAnalysisMetadata | null | undefined): boolean {
  return Boolean(analysis?.icon.stroke_width_editable)
}

/**
 * 归一化渲染模式文案。
 * @param analysis 资产分析元数据
 */
export function getRenderModeLabel(analysis: AssetAnalysisMetadata | null | undefined): string {
  if (!analysis) return '未分析'
  return analysis.icon.render_mode === 'inline_svg' ? '内联 SVG' : '图片'
}

/**
 * 归一化图标风格文案。
 * @param analysis 资产分析元数据
 */
export function getIconStyleLabel(analysis: AssetAnalysisMetadata | null | undefined): string {
  if (!analysis) return '未分析'
  const styleMap: Record<string, string> = {
    stroke: '描边',
    fill: '填充',
    mixed: '混合',
    complex: '复杂',
    unknown: '未知',
  }
  return styleMap[analysis.icon.style] || '未知'
}

/**
 * 归一化分析状态文案。
 * @param analysis 资产分析元数据
 */
export function getAnalysisStatusLabel(analysis: AssetAnalysisMetadata | null | undefined): string {
  if (!analysis) return '未分析'
  const statusMap: Record<string, string> = {
    analyzed: '已分析',
    unsupported: '不支持',
    error: '分析失败',
  }
  return statusMap[analysis.icon.analysis_status] || '未分析'
}

/**
 * 生成主题选择器使用的简短能力摘要。
 * @param analysis 资产分析元数据
 */
export function getIconCapabilitySummary(analysis: AssetAnalysisMetadata | null | undefined): string {
  if (!analysis) {
    return '未分析，默认描边宽度不会生效'
  }
  const supportText = analysis.icon.stroke_width_editable ? '支持描边宽度' : '不支持描边宽度'
  return `${getRenderModeLabel(analysis)} / ${getIconStyleLabel(analysis)} / ${supportText}`
}
