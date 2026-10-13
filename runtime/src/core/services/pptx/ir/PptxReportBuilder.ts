/**
 * 文件用途：提供 PPTX 导出诊断报告（PptxExportReport / PptxExportReportPage）的构建与聚合工具。
 */

import type {
  PptxExportReport,
  PptxExportReportItem,
  PptxExportReportPage,
  PptxReportItemResult,
  PptxReportSourceType,
} from '@/core/types/pptx-export'
import type { VisitContext } from '@/core/services/pptx/PPTXDomConverter.types'

/**
 * 创建空的 PPTX 导出汇总报告。
 * @returns 初始化计数为 0 的汇总报告
 */
export function createEmptyPptxReport(): PptxExportReport {
  return {
    summary: {
      editableText: 0,
      editableShape: 0,
      editableTable: 0,
      imageBlock: 0,
      svgBlock: 0,
      screenshotBlock: 0,
      skipped: 0,
    },
    pages: [],
  }
}

/**
 * 创建空的单页 PPTX 导出报告。
 * @param pageIndex 页码（从 1 开始）
 * @param pageTitle 页面标题
 * @param pageRoute 页面路由
 * @returns 空的单页报告对象
 */
export function createEmptyPptxReportPage(
  pageIndex: number,
  pageTitle: string,
  pageRoute: string,
): PptxExportReportPage {
  return {
    pageIndex,
    pageTitle,
    pageRoute,
    items: [],
  }
}

/**
 * 向单页报告追加一条转换记录。
 * @param reportPage 目标单页报告
 * @param sourceType 源元素类型
 * @param result 转换结果类别
 * @param editable 是否可编辑
 * @param label 元素摘要标签
 * @param reason 补充说明或降级原因
 * @param context 遍历组合上下文
 * @returns 新增的报告条目
 */
export function appendPptxReportItem(
  reportPage: PptxExportReportPage,
  sourceType: PptxReportSourceType,
  result: PptxReportItemResult,
  editable: boolean,
  label: string,
  reason?: string,
  context?: VisitContext,
  extra?: Partial<PptxExportReportItem>,
): PptxExportReportItem {
  const item: PptxExportReportItem = {
    pageIndex: reportPage.pageIndex,
    pageTitle: reportPage.pageTitle,
    pageRoute: reportPage.pageRoute,
    sourceType,
    result,
    editable,
    label,
    reason,
    groupId: context?.groupId,
    parentGroupId: context?.parentGroupId,
    groupDepth: context?.groupId ? context.groupDepth : undefined,
    groupLabel: context?.groupLabel,
    severity: result === 'skipped' ? 'warning' : 'info',
    ...extra,
  }
  reportPage.items.push(item)
  return item
}

/**
 * 将单页报告合并至总报告并累加各项分类统计。
 * @param report 总报告
 * @param pageReport 单页报告
 */
export function mergePptxReportPage(
  report: PptxExportReport,
  pageReport: PptxExportReportPage,
): void {
  report.pages.push(pageReport)

  for (const item of pageReport.items) {
    switch (item.result) {
      case 'editable-text':
        report.summary.editableText += 1
        break
      case 'editable-shape':
        report.summary.editableShape += 1
        break
      case 'editable-table':
        report.summary.editableTable += 1
        break
      case 'image':
        report.summary.imageBlock += 1
        break
      case 'svg':
        report.summary.svgBlock += 1
        break
      case 'screenshot':
        report.summary.screenshotBlock += 1
        break
      case 'skipped':
        report.summary.skipped += 1
        break
    }
  }
}
