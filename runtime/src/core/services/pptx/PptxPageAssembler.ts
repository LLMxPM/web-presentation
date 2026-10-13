/** 文件用途：先提取完整单页 IR，再提交幻灯片；仅在提取阶段失败时允许整页截图容错。 */

import type PptxGenJS from 'pptxgenjs'
import type { PageInfo } from '@/core/types/export-common'
import type { PptxExportReportPage } from '@/core/types/pptx-export'
import type { PPTXDomConverter } from './PPTXDomConverter'
import type { PptxSlideExtractOptions } from './ir/PptxSlideIR.types'
import type { PptxGradientFillInstruction } from './PPTXDomConverter.types'
import type { PptxGroupInstruction } from './writer/OoxmlGroupPatcher'
import { projectSlideIRToSlide } from './writer/PptxSlideProjector'
import { throwIfExportAborted } from '@/core/services/export/ExportCancellation'

/** 标记可进入页面容错的提取错误；投射和打包错误不属于此类型。 */
export class PptxPageExtractionError extends Error {
  constructor(cause: unknown) {
    super(cause instanceof Error ? cause.message : String(cause), { cause })
  }
}

/** 提取成功后才创建 slide，确保失败页不会留下空白页或部分图元。 */
export async function appendEditablePptxPage(
  pptx: PptxGenJS,
  converter: PPTXDomConverter,
  options: PptxSlideExtractOptions,
  gradientFills: PptxGradientFillInstruction[],
  groups?: PptxGroupInstruction[],
): Promise<PptxExportReportPage> {
  let ir
  try {
    ir = await converter.extractSlideIR(options)
  } catch (error) {
    throwIfExportAborted(options.signal)
    throw new PptxPageExtractionError(error)
  }
  throwIfExportAborted(options.signal)
  projectSlideIRToSlide(ir, pptx.addSlide(), fill => gradientFills.push(fill), group => groups?.push(group))
  return ir.report
}

/** 先取得全页图片再提交单张幻灯片；页码和备注沿用原页面。 */
export async function appendRasterizedPptxPage(
  pptx: PptxGenJS,
  options: PptxSlideExtractOptions,
  page: PageInfo,
  cause: unknown,
): Promise<PptxExportReportPage> {
  const data = await options.captureElementAsPng(options.pageElement)
  throwIfExportAborted(options.signal)
  const slide = pptx.addSlide()
  if (options.speakerNotes) slide.addNotes(options.speakerNotes)
  slide.addImage({ data, x: 0, y: 0, w: options.slideWidthIn, h: options.slideHeightIn })
  options.resourceSession?.recordScreenshot()
  options.resourceSession?.recordRasterizedPage(options.pageIndex)
  return {
    pageIndex: options.pageIndex,
    pageTitle: options.pageTitle,
    pageRoute: options.pageRoute,
    items: [{
      pageIndex: options.pageIndex,
      pageTitle: options.pageTitle,
      pageRoute: options.pageRoute,
      sourceType: 'unknown',
      result: 'screenshot',
      editable: false,
      label: page.title || options.pageTitle,
      reason: `页面提取失败，已通过整页截图容错交付：${cause instanceof Error ? cause.message : String(cause)}`,
      severity: 'warning',
      code: 'PAGE_CONVERSION_FALLBACK',
      fallbackScope: 'page',
    }],
  }
}
