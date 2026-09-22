/**
 * 文件用途：根据浏览器实测尺寸计算 PPTX 表格行高、列宽，并校正轨道总尺寸。
 */

import type { ElementBox } from '@/core/services/pptx/PPTXDomConverter.types'
import type { PPTXDomConverterLayout } from '@/core/services/pptx/PPTXDomConverterLayout'
import type { PptxDomTableCellEntry, PptxDomTableModel } from '@/core/services/pptx/PPTXDomTable.types'

/**
 * PPTX 表格几何计算器。
 */
export class PPTXDomTableGeometry {
  constructor(private readonly layout: PPTXDomConverterLayout) {}

  /**
   * 根据浏览器实际布局解析每行高度，并校正总高与表格外框一致。
   */
  resolveRowHeights(model: PptxDomTableModel, box: ElementBox): number[] {
    const measuredPixels = model.rows.map(row => {
      if (row.element) {
        return this.layout.measureElementPixels(row.element).height
      }
      return row.cells
        .filter(cell => cell.rowspan === 1)
        .reduce((height, cell) => Math.max(height, this.layout.measureElementPixels(cell.element).height), 0)
    })
    this.applySpanningMeasurements(measuredPixels, model.cells, 'row')
    return this.normalizeTrackSizes(measuredPixels, box.h, this.layout.inchPerPxY())
  }

  /**
   * 根据浏览器实际布局解析每列宽度，并校正总宽与表格外框一致。
   */
  resolveColumnWidths(model: PptxDomTableModel, box: ElementBox): number[] {
    const measuredPixels = Array.from({ length: model.columnCount }, (_, columnIndex) => {
      return model.cells
        .filter(cell => cell.columnIndex === columnIndex && cell.colspan === 1)
        .reduce((width, cell) => Math.max(width, this.layout.measureElementPixels(cell.element).width), 0)
    })
    this.applySpanningMeasurements(measuredPixels, model.cells, 'column')
    return this.normalizeTrackSizes(measuredPixels, box.w, this.layout.inchPerPxX())
  }

  /**
   * 使用跨行或跨列单元格为无法直接测量的轨道提供均分候选尺寸。
   */
  private applySpanningMeasurements(
    tracks: number[],
    cells: PptxDomTableCellEntry[],
    axis: 'row' | 'column',
  ): void {
    cells.forEach(cell => {
      const start = axis === 'row' ? cell.rowIndex : cell.columnIndex
      const span = axis === 'row' ? cell.rowspan : cell.colspan
      if (span <= 1) {
        return
      }
      const measured = this.layout.measureElementPixels(cell.element)
      const candidate = (axis === 'row' ? measured.height : measured.width) / span
      for (let offset = 0; offset < span && start + offset < tracks.length; offset += 1) {
        if (tracks[start + offset] <= 0) {
          tracks[start + offset] = candidate
        }
      }
    })
  }

  /**
   * 将像素轨道转换为英寸，并确保舍入后总尺寸与表格外框一致。
   */
  private normalizeTrackSizes(measuredPixels: number[], targetInches: number, inchPerPixel: number): number[] {
    if (measuredPixels.length === 0) {
      return []
    }
    const positiveSizes = measuredPixels.filter(value => value > 0)
    const fallbackPixels = positiveSizes.length > 0
      ? positiveSizes.reduce((sum, value) => sum + value, 0) / positiveSizes.length
      : 1
    const normalizedPixels = measuredPixels.map(value => value > 0 ? value : fallbackPixels)
    const measuredInches = normalizedPixels.map(value => value * inchPerPixel)
    const measuredTotal = measuredInches.reduce((sum, value) => sum + value, 0)
    const scale = measuredTotal > 0 ? targetInches / measuredTotal : 1
    const result = measuredInches.map(value => this.layout.roundInch(value * scale))
    const previousTotal = result.slice(0, -1).reduce((sum, value) => sum + value, 0)
    result[result.length - 1] = this.layout.roundInch(Math.max(0.001, targetInches - previousTotal))
    return result
  }
}
