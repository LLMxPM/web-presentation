/**
 * 文件用途：定义 Runtime Kit 与原生 HTML 表格共享的 PPTX 转换中间模型。
 */

export type PptxDomTableSource = 'runtime-kit' | 'html'

export interface PptxDomTableCellEntry {
  element: HTMLElement
  rowIndex: number
  columnIndex: number
  rowspan: number
  colspan: number
}

export interface PptxDomTableRowEntry {
  element: HTMLElement | null
  rowIndex: number
  cells: PptxDomTableCellEntry[]
}

export interface PptxDomTableModel {
  source: PptxDomTableSource
  element: HTMLElement
  rows: PptxDomTableRowEntry[]
  cells: PptxDomTableCellEntry[]
  rowCount: number
  columnCount: number
  borderCollapse: boolean
}
