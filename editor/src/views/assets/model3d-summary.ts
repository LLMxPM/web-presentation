/**
 * 文件功能：把三维资源动画分析摘要整理为可展示的动作标签、时长与不支持原因。
 */

import type { AssetModel3dAnimationSummary } from '@/types/api.generated'

export interface ModelAnimationSummary {
  index: number
  label: string
  durationText: string
  signature: string
  supported: boolean
  issues: string[]
}

export interface ModelAnimationOverview {
  analyzed: boolean
  text: string
  details: ModelAnimationSummary[]
}

/** 把毫秒时长格式化为秒，未知时长保持显式说明。 */
function formatDuration(durationMs: number | null | undefined): string {
  if (typeof durationMs !== 'number' || !Number.isFinite(durationMs) || durationMs <= 0) {
    return '时长未知'
  }
  return `${(durationMs / 1000).toFixed(2).replace(/\.?0+$/, '')} 秒`
}

/** 摘要只展示有界字段，不携带通道列表或原始采样数据。 */
export function summarizeModelAnimations(
  animations: AssetModel3dAnimationSummary[] | null | undefined,
  analysisVersion: number | null | undefined,
): ModelAnimationOverview {
  const analyzed = typeof analysisVersion === 'number' && analysisVersion > 0
  const details = (animations ?? []).map((item): ModelAnimationSummary => {
    const issues: string[] = []
    if (!analyzed) {
      issues.push('动作分析版本缺失，暂不可执行')
    } else if (item.supported === false) {
      issues.push(...(item.unsupported_reasons?.length ? item.unsupported_reasons : ['当前分析不支持该动作']))
    }
    return {
      index: item.index,
      label: item.name ? `#${item.index} ${item.name}` : `#${item.index}`,
      durationText: formatDuration(item.duration_ms),
      signature: item.signature ? item.signature.slice(0, 8) : '',
      supported: analyzed && item.supported !== false,
      issues,
    }
  })
  if (!details.length) {
    return { analyzed, text: analyzed ? '无动画' : '动画未分析', details }
  }
  return {
    analyzed,
    text: details.map(item => item.label).join('、'),
    details,
  }
}
