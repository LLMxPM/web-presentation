/**
 * 文件用途：协调 HTML border-collapse 表格的共享单元格边框，避免 PPT 中出现双线。
 */

import type { PptxTableRowLike } from '@/core/services/pptx/PPTXDomConverter.types'
import type { PptxDomTableCellEntry, PptxDomTableModel } from '@/core/services/pptx/PPTXDomTable.types'

/**
 * PPTX 折叠表格边框协调器。
 */
export class PPTXDomTableBorders {
  /**
   * 按 CSS 折叠边框核心优先级统一相邻单元格边界。
   */
  reconcile(tableRows: PptxTableRowLike[], model: PptxDomTableModel): void {
    const cellOptions = new Map<PptxDomTableCellEntry, Record<string, unknown>>()
    model.rows.forEach((row, rowIndex) => {
      row.cells.forEach((entry, cellIndex) => {
        const options = tableRows[rowIndex]?.[cellIndex]?.options
        if (options) {
          cellOptions.set(entry, options)
        }
      })
    })

    model.cells.forEach(entry => {
      const rightNeighbor = model.cells.find(candidate => {
        return candidate.columnIndex === entry.columnIndex + entry.colspan &&
          this.rangesOverlap(entry.rowIndex, entry.rowspan, candidate.rowIndex, candidate.rowspan)
      })
      if (rightNeighbor) {
        this.reconcileSharedBorder(cellOptions.get(entry), 1, cellOptions.get(rightNeighbor), 3)
      }

      const bottomNeighbor = model.cells.find(candidate => {
        return candidate.rowIndex === entry.rowIndex + entry.rowspan &&
          this.rangesOverlap(entry.columnIndex, entry.colspan, candidate.columnIndex, candidate.colspan)
      })
      if (bottomNeighbor) {
        this.reconcileSharedBorder(cellOptions.get(entry), 2, cellOptions.get(bottomNeighbor), 0)
      }
    })
  }

  /**
   * 统一两个相邻单元格的共享边框，宽边、实线优先。
   */
  private reconcileSharedBorder(
    firstOptions: Record<string, unknown> | undefined,
    firstSide: number,
    secondOptions: Record<string, unknown> | undefined,
    secondSide: number,
  ): void {
    const firstBorders = firstOptions?.border as Array<Record<string, unknown>> | undefined
    const secondBorders = secondOptions?.border as Array<Record<string, unknown>> | undefined
    if (!firstBorders || !secondBorders) {
      return
    }
    const selected = this.selectStrongerBorder(firstBorders[firstSide], secondBorders[secondSide])
    firstBorders[firstSide] = { ...selected }
    secondBorders[secondSide] = { ...selected }
  }

  /**
   * 选择 CSS collapsed border 中视觉优先级更高的一侧。
   */
  private selectStrongerBorder(
    first: Record<string, unknown>,
    second: Record<string, unknown>,
  ): Record<string, unknown> {
    const score = (border: Record<string, unknown>): number => {
      const typeScore = border.type === 'solid' ? 2 : border.type === 'dash' ? 1 : 0
      return Number(border.pt || 0) * 10 + typeScore
    }
    return score(second) > score(first) ? second : first
  }

  /**
   * 判断两个半开区间是否相交。
   */
  private rangesOverlap(firstStart: number, firstSpan: number, secondStart: number, secondSpan: number): boolean {
    return firstStart < secondStart + secondSpan && secondStart < firstStart + firstSpan
  }
}
