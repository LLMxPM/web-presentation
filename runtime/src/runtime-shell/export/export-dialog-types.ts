/**
 * 文件用途：定义导出弹窗与其子组件、运行器共用的导出方式与结果类型，避免组件反向依赖组合式模块。
 */

import type { ExportMethod, ExportResult } from '@/core/types/pdf-export'
import type { PptxExportResult } from '@/core/types/pptx-export'

/**
 * 弹窗支持的导出方式：PDF 的两种方式，加上可编辑 PPTX。
 * 由 ExportMethod 派生，新增 PDF 方式时运行器分派表会因缺键而编译失败，避免静默漏接。
 */
export type DialogExportMethod = ExportMethod | 'pptx-editable'

/** 弹窗展示的导出结果；PPTX 形态额外携带导出报告。 */
export type DialogExportResult = ExportResult | PptxExportResult

/**
 * 判断导出结果是否为 PPTX 形态。
 * @param result 导出结果，未产出时为 null
 * @returns 结果是否携带 PPTX 导出报告
 */
export function isPptxExportResult(result: DialogExportResult | null): result is PptxExportResult {
  return result?.method === 'pptx-editable'
}
