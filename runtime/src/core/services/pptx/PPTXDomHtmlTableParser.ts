/**
 * 文件用途：把原生 HTML table 解析为稳定的二维表格模型，并识别需要截图降级的复杂内容。
 */

import type { PPTXDomConverterLayout } from '@/core/services/pptx/PPTXDomConverterLayout'
import type {
  PptxDomTableCellEntry,
  PptxDomTableModel,
  PptxDomTableRowEntry,
} from '@/core/services/pptx/PPTXDomTable.types'

const COMPLEX_CELL_CONTENT_SELECTOR = [
  'table',
  'img',
  'svg',
  'canvas',
  'video',
  'audio',
  'iframe',
  'object',
  'embed',
  'ul',
  'ol',
  'button',
  'input',
  'select',
  'textarea',
].join(',')
const MAX_TABLE_TRACK_COUNT = 256

/**
 * 原生 HTML 表格解析器。
 */
export class PPTXDomHtmlTableParser {
  constructor(private readonly layout: PPTXDomConverterLayout) {}

  /**
   * 判断候选元素是否为原生 HTML table。
   * @param element 候选 DOM 元素
   */
  isHtmlTable(element: Element): element is HTMLTableElement {
    return element instanceof HTMLTableElement
  }

  /**
   * 返回无法安全导出为 PPT 原生表格的原因；空值表示可以转换。
   * @param table 原生表格
   */
  resolveUnsupportedReason(table: HTMLTableElement): string | null {
    const nestedTable = table.querySelector('table')
    if (nestedTable) {
      return 'HTML 表格包含嵌套表格，已降级为局部截图'
    }

    const complexContent = table.querySelector(COMPLEX_CELL_CONTENT_SELECTOR)
    if (complexContent) {
      return `HTML 表格包含 ${complexContent.tagName.toLowerCase()} 等复杂单元格内容，已降级为局部截图`
    }

    const model = this.parse(table)
    if (model.rowCount > MAX_TABLE_TRACK_COUNT || model.columnCount > MAX_TABLE_TRACK_COUNT) {
      return `HTML 表格超过 ${MAX_TABLE_TRACK_COUNT} 行或列的导出上限，已降级为局部截图`
    }
    if (model.cells.length > 0 && this.hasUncoveredCoordinate(model)) {
      return 'HTML 表格行列结构不规则，已降级为局部截图'
    }

    return null
  }

  /**
   * 按浏览器表格行顺序解析 rowspan/colspan 占位关系。
   * @param table 原生表格
   */
  parse(table: HTMLTableElement): PptxDomTableModel {
    const visibleRows = Array.from(table.rows)
      .filter(row => this.layout.isVisibleElement(row))
    const occupied = new Set<string>()
    const rows: PptxDomTableRowEntry[] = []
    const cells: PptxDomTableCellEntry[] = []
    let columnCount = 0

    visibleRows.forEach((row, rowIndex) => {
      let columnIndex = 0
      const rowCells: PptxDomTableCellEntry[] = []

      Array.from(row.cells)
        .filter(cell => cell.closest('table') === table && this.layout.isVisibleElement(cell))
        .forEach(cell => {
          while (occupied.has(this.buildCoordinateKey(rowIndex, columnIndex))) {
            columnIndex += 1
          }

          const rowspan = Math.min(
            this.resolveSpan(cell.getAttribute('rowspan'), visibleRows.length - rowIndex),
            visibleRows.length - rowIndex,
          )
          const colspan = this.resolveSpan(cell.getAttribute('colspan'), 1)
          const entry: PptxDomTableCellEntry = {
            element: cell,
            rowIndex,
            columnIndex,
            rowspan,
            colspan,
          }
          rowCells.push(entry)
          cells.push(entry)
          this.markOccupiedCells(occupied, entry)
          columnIndex += colspan
          columnCount = Math.max(columnCount, columnIndex)
        })

      rows.push({ element: row, rowIndex, cells: rowCells })
    })

    cells.forEach(cell => {
      columnCount = Math.max(columnCount, cell.columnIndex + cell.colspan)
    })

    return {
      source: 'html',
      element: table,
      rows,
      cells,
      rowCount: rows.length,
      columnCount,
      borderCollapse: window.getComputedStyle(table).borderCollapse === 'collapse',
    }
  }

  /**
   * 解析 HTML span 属性；rowspan=0 按剩余全部行处理。
   * @param rawValue 属性原值
   * @param zeroFallback 属性为 0 时的回退跨度
   */
  private resolveSpan(rawValue: string | null, zeroFallback: number): number {
    if (rawValue === null || rawValue.trim() === '') {
      return 1
    }
    const parsed = Number(rawValue)
    if (!Number.isInteger(parsed) || parsed < 0) {
      return 1
    }
    return parsed === 0 ? Math.max(1, zeroFallback) : parsed
  }

  /**
   * 判断矩形逻辑网格中是否存在未被任何单元格覆盖的空洞。
   */
  private hasUncoveredCoordinate(model: PptxDomTableModel): boolean {
    for (let rowIndex = 0; rowIndex < model.rowCount; rowIndex += 1) {
      for (let columnIndex = 0; columnIndex < model.columnCount; columnIndex += 1) {
        const covered = model.cells.some(cell => {
          return rowIndex >= cell.rowIndex && rowIndex < cell.rowIndex + cell.rowspan &&
            columnIndex >= cell.columnIndex && columnIndex < cell.columnIndex + cell.colspan
        })
        if (!covered) {
          return true
        }
      }
    }
    return false
  }

  /**
   * 标记一个单元格占据的全部逻辑坐标。
   * @param occupied 已占用坐标集合
   * @param entry 单元格条目
   */
  private markOccupiedCells(occupied: Set<string>, entry: PptxDomTableCellEntry): void {
    for (let rowOffset = 0; rowOffset < entry.rowspan; rowOffset += 1) {
      for (let columnOffset = 0; columnOffset < entry.colspan; columnOffset += 1) {
        occupied.add(this.buildCoordinateKey(entry.rowIndex + rowOffset, entry.columnIndex + columnOffset))
      }
    }
  }

  /**
   * 构造逻辑单元格坐标键。
   */
  private buildCoordinateKey(rowIndex: number, columnIndex: number): string {
    return `${rowIndex},${columnIndex}`
  }
}
