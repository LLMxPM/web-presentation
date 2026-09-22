/**
 * 文件用途：封装 Runtime Kit DataTable 与原生 HTML table 到 PPTX 原生表格的导出逻辑。
 */

import type {
  PptxExportReportItem,
  PptxReportItemResult,
  PptxReportSourceType,
} from '@/core/types/pptx-export'
import type { ParsedColor } from '@/core/services/pptx/PPTXCssParser'
import type {
  BorderInfo,
  PptxPageConvertOptions,
  PptxTableCellLike,
  PptxTableRowLike,
  VisitContext,
} from '@/core/services/pptx/PPTXDomConverter.types'
import type { PPTXDomConverterLayout } from '@/core/services/pptx/PPTXDomConverterLayout'
import { PPTXDomHtmlTableParser } from '@/core/services/pptx/PPTXDomHtmlTableParser'
import { PPTXDomTableBorders } from '@/core/services/pptx/PPTXDomTableBorders'
import { PPTXDomTableGeometry } from '@/core/services/pptx/PPTXDomTableGeometry'
import type {
  PptxDomTableCellEntry,
  PptxDomTableModel,
  PptxDomTableRowEntry,
} from '@/core/services/pptx/PPTXDomTable.types'

export interface PptxDomTableExportHost {
  options: PptxPageConvertOptions
  buildPptObjectMeta: (
    context: VisitContext,
    role: string,
    label: string,
    includeAltText?: boolean,
  ) => Record<string, unknown>
  addReportItem: (
    sourceType: PptxReportSourceType,
    result: PptxReportItemResult,
    editable: boolean,
    label: string,
    reason?: string,
    context?: VisitContext,
  ) => PptxExportReportItem
  addSkippedItem: (sourceType: PptxReportSourceType, label: string, reason: string, context?: VisitContext) => void
}

/**
 * Runtime Kit 与原生 HTML 表格导出 helper。
 */
export class PPTXDomConverterTable {
  private readonly htmlParser: PPTXDomHtmlTableParser
  private readonly geometry: PPTXDomTableGeometry
  private readonly borders = new PPTXDomTableBorders()

  constructor(private readonly layout: PPTXDomConverterLayout) {
    this.htmlParser = new PPTXDomHtmlTableParser(layout)
    this.geometry = new PPTXDomTableGeometry(layout)
  }

  /**
   * 判断元素是否为可导出的 Runtime Kit DataTable 或原生 HTML table 根节点。
   * @param element 候选元素
   */
  isTableElement(element: Element): boolean {
    return this.isRuntimeKitTable(element) || this.htmlParser.isHtmlTable(element)
  }

  /**
   * 返回表格需要截图降级的原因；空值表示可以转换为 PPT 原生表格。
   * @param element 候选表格
   */
  resolveUnsupportedReason(element: Element): string | null {
    return this.htmlParser.isHtmlTable(element)
      ? this.htmlParser.resolveUnsupportedReason(element)
      : null
  }

  /**
   * 将 Runtime Kit 或原生 HTML 表格导出为 PPT 原生表格。
   * @param host 导出宿主能力
   * @param element 表格根节点
   * @param context 当前组合上下文
   */
  addTableElement(host: PptxDomTableExportHost, element: HTMLElement, context: VisitContext): boolean {
    const box = this.layout.getPptxBox(element)
    const label = this.layout.buildElementLabel(element)
    if (!box) {
      host.addSkippedItem('table', label, '表格尺寸无效，无法导出为 PPT 原生表格', context)
      return true
    }

    const model = this.buildTableModel(element)
    if (model.rowCount <= 0 || model.columnCount <= 0 || model.cells.length <= 0) {
      host.addSkippedItem('table', label, '表格没有有效单元格，已跳过', context)
      return true
    }

    const tableRows = this.buildTableRows(model, context)
    if (model.borderCollapse) {
      this.borders.reconcile(tableRows, model)
    }
    host.options.slide.addTable(tableRows, {
      ...box,
      rowH: this.geometry.resolveRowHeights(model, box),
      colW: this.geometry.resolveColumnWidths(model, box),
      autoPage: false,
      fit: 'shrink',
      margin: 0,
      ...host.buildPptObjectMeta(context, 'table', label),
    })
    const sourceLabel = model.source === 'html' ? 'HTML' : 'Runtime Kit'
    host.addReportItem('table', 'editable-table', true, label, `${sourceLabel} 表格导出为 PPT 原生表格`, context)
    return true
  }

  /**
   * 构造统一表格中间模型。
   * @param tableElement 表格根节点
   */
  private buildTableModel(tableElement: HTMLElement): PptxDomTableModel {
    if (this.htmlParser.isHtmlTable(tableElement)) {
      return this.htmlParser.parse(tableElement)
    }

    const cells = this.collectRuntimeKitCells(tableElement)
    const rowCount = this.resolveRuntimeKitRowCount(tableElement, cells)
    const columnCount = this.resolveRuntimeKitColumnCount(tableElement, cells)
    const rows: PptxDomTableRowEntry[] = Array.from({ length: rowCount }, (_, rowIndex) => ({
      element: null,
      rowIndex,
      cells: cells.filter(cell => cell.rowIndex === rowIndex),
    }))
    return {
      source: 'runtime-kit',
      element: tableElement,
      rows,
      cells,
      rowCount,
      columnCount,
      borderCollapse: false,
    }
  }

  /**
   * 判断元素是否为 Runtime Kit DataTable 根节点。
   */
  private isRuntimeKitTable(element: Element): boolean {
    return element instanceof HTMLElement && element.getAttribute('data-runtime-kit-table') === 'v1'
  }

  /**
   * 收集 Runtime Kit 表格中带行列索引的单元格节点。
   * @param tableElement DataTable 根节点
   */
  private collectRuntimeKitCells(tableElement: HTMLElement): PptxDomTableCellEntry[] {
    return Array.from(tableElement.querySelectorAll('[data-runtime-kit-table-cell="v1"]'))
      .filter((cell): cell is HTMLElement => cell instanceof HTMLElement)
      .map(cell => ({
        element: cell,
        rowIndex: Number(cell.dataset.rowIndex),
        columnIndex: Number(cell.dataset.columnIndex),
        rowspan: 1,
        colspan: 1,
      }))
      .filter(entry => Number.isInteger(entry.rowIndex) && entry.rowIndex >= 0 && Number.isInteger(entry.columnIndex) && entry.columnIndex >= 0)
      .sort((left, right) => {
        return left.rowIndex === right.rowIndex
          ? left.columnIndex - right.columnIndex
          : left.rowIndex - right.rowIndex
      })
  }

  /**
   * 构造 pptxgenjs addTable 所需二维行数据。
   * @param entries 单元格条目
   * @param rowCount 行数
   * @param columnCount 列数
   * @param context 当前文本继承上下文
   */
  private buildTableRows(model: PptxDomTableModel, context: VisitContext): PptxTableRowLike[] {
    return model.rows.map(row => {
      if (model.source === 'html') {
        return row.cells.map(entry => this.buildTableCell(entry, context))
      }

      const cellsByColumn = new Map(row.cells.map(entry => [entry.columnIndex, entry]))
      return Array.from({ length: model.columnCount }, (_, columnIndex) => {
        const entry = cellsByColumn.get(columnIndex)
        return entry
          ? this.buildTableCell(entry, context)
          : { text: '', options: { fit: 'shrink' } }
      })
    })
  }

  /**
   * 构造单个 PPT 表格单元格。
   * @param element 单元格 DOM
   * @param context 当前文本继承上下文
   */
  private buildTableCell(entry: PptxDomTableCellEntry, context: VisitContext): PptxTableCellLike {
    const { element } = entry
    const text = this.layout.normalizeText(element.textContent || '')
    const style = window.getComputedStyle(element)
    return {
      text,
      options: {
        ...this.buildTextOptions(element, style, text, context),
        ...this.buildCellVisualOptions(element, style),
        margin: this.buildCellMargin(element, style),
        fit: 'shrink',
        ...(entry.rowspan > 1 ? { rowspan: entry.rowspan } : {}),
        ...(entry.colspan > 1 ? { colspan: entry.colspan } : {}),
      },
    }
  }

  /**
   * 构造单元格文字样式。
   * @param element 单元格 DOM
   * @param style 计算样式
   * @param text 单元格文本
   * @param context 当前文本继承上下文
   */
  private buildTextOptions(
    element: HTMLElement,
    style: CSSStyleDeclaration,
    text: string,
    context: VisitContext,
  ): Record<string, unknown> {
    const color = this.applyOpacity(this.layout.parseCssColor(style.color, element), this.layout.parseOpacity(style.opacity))
    return {
      fontFace: this.layout.normalizeFontFace(style.fontFamily, text),
      fontSize: Math.max(1, this.layout.cssPxToPt(this.layout.parseCssPixel(style.fontSize) || 16)),
      color: color?.hex || '000000',
      transparency: this.layout.alphaToTransparency(color?.alpha ?? 1),
      bold: this.layout.isBoldFont(style.fontWeight),
      italic: style.fontStyle === 'italic',
      underline: style.textDecorationLine.includes('underline'),
      align: this.layout.resolveTextHorizontalAlign(element, style, context),
      valign: this.layout.resolveTextVerticalAlign(element, style, text, context),
    }
  }

  /**
   * 构造单元格背景和边框样式。
   * @param element 单元格 DOM
   * @param style 计算样式
   */
  private buildCellVisualOptions(element: HTMLElement, style: CSSStyleDeclaration): Record<string, unknown> {
    const elementOpacity = this.layout.parseOpacity(style.opacity)
    const fillColor = this.resolveCellBackgroundColor(element, elementOpacity)
    const borders = this.layout.getBorderInfos(element, style).map(border => ({
      ...border,
      color: this.applyOpacity(border.color, elementOpacity) || border.color,
    }))

    return {
      ...(fillColor ? {
        fill: {
          color: fillColor.hex,
          transparency: this.layout.alphaToTransparency(fillColor.alpha),
        },
      } : {}),
      border: this.buildTableBorderOptions(borders),
    }
  }

  /**
   * 按 td/th、tr、行组、table 顺序解析可见背景色，模拟 HTML 表格背景向单元格透出的效果。
   * @param element 单元格 DOM
   * @param cellOpacity 单元格透明度
   */
  private resolveCellBackgroundColor(element: HTMLElement, cellOpacity: number): ParsedColor | null {
    let current: HTMLElement | null = element
    while (current) {
      const style = window.getComputedStyle(current)
      const color = this.layout.parseCssColor(this.layout.resolveBackgroundColorValue(current, style), current)
      if (color && color.alpha > 0) {
        const effectiveOpacity = current === element
          ? cellOpacity
          : cellOpacity * this.layout.parseOpacity(style.opacity)
        return this.applyOpacity(color, effectiveOpacity)
      }
      if (current.tagName.toLowerCase() === 'table' || current.getAttribute('data-runtime-kit-table') === 'v1') {
        break
      }
      current = current.parentElement
    }
    return null
  }

  /**
   * 将 CSS 单元格边框映射为 pptxgenjs 表格边框数组。
   * @param borders 计算后的四边边框
   */
  private buildTableBorderOptions(borders: BorderInfo[]): Array<Record<string, unknown>> {
    const borderBySide = new Map(borders.map(border => [border.side, border]))
    return (['top', 'right', 'bottom', 'left'] as const).map(side => {
      const border = borderBySide.get(side)
      if (!border) {
        return {
          type: 'none',
          color: 'FFFFFF',
          pt: 0,
        }
      }
      return {
        type: border.style === 'dashed' || border.style === 'dotted' ? 'dash' : 'solid',
        color: border.color.hex,
        pt: border.widthPt,
      }
    })
  }

  /**
   * 将 CSS padding 转为 PPT 表格单元格 margin。
   * @param element 单元格 DOM
   * @param style 计算样式
   */
  private buildCellMargin(element: HTMLElement, style: CSSStyleDeclaration): number | [number, number, number, number] {
    const padding = this.layout.resolveElementPaddingPixels(element, style)
    const margin: [number, number, number, number] = [
      this.layout.cssPxToPt(padding.top),
      this.layout.cssPxToPt(padding.right),
      this.layout.cssPxToPt(padding.bottom),
      this.layout.cssPxToPt(padding.left),
    ]
    return margin.some(value => value > 0) ? margin : 0
  }

  /**
   * 解析 Runtime Kit 表格行数。
   * @param tableElement 表格根节点
   * @param entries Runtime Kit 单元格条目
   */
  private resolveRuntimeKitRowCount(tableElement: HTMLElement, entries: PptxDomTableCellEntry[]): number {
    const declaredRowCount = Number(tableElement.getAttribute('aria-rowcount'))
    if (Number.isInteger(declaredRowCount) && declaredRowCount > 0) {
      return declaredRowCount
    }
    return entries.reduce((maxIndex, entry) => Math.max(maxIndex, entry.rowIndex + 1), 0)
  }

  /**
   * 解析 Runtime Kit 表格列数。
   * @param tableElement 表格根节点
   * @param entries 单元格条目
   */
  private resolveRuntimeKitColumnCount(tableElement: HTMLElement, entries: PptxDomTableCellEntry[]): number {
    const declaredColumnCount = Number(tableElement.getAttribute('aria-colcount'))
    if (Number.isInteger(declaredColumnCount) && declaredColumnCount > 0) {
      return declaredColumnCount
    }
    return entries.reduce((maxIndex, entry) => Math.max(maxIndex, entry.columnIndex + 1), 0)
  }

  /**
   * 对颜色叠加元素 opacity。
   * @param color 原始颜色
   * @param opacity 元素透明度
   */
  private applyOpacity(color: ParsedColor | null, opacity: number): ParsedColor | null {
    if (!color) {
      return null
    }
    return {
      hex: color.hex,
      alpha: Math.max(0, Math.min(1, color.alpha * opacity)),
    }
  }
}
