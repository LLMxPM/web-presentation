<!--
  文件用途：DataTable — 使用 CSS Grid 渲染 PPT 风格表格，并为 PPTX 原生表格导出提供稳定 DOM 标记。
-->
<template>
  <div
    v-bind="rootAttrs"
    role="table"
    data-runtime-kit-table="v1"
    class="runtime-data-table"
    :class="rootClassName"
    :style="[forwardedStyle, tableStyle]"
    :aria-rowcount="rowCount"
    :aria-colcount="columnCount"
  >
    <div
      v-for="row in renderedRows"
      :key="row.key"
      role="row"
      class="runtime-data-table__row-proxy"
      :aria-rowindex="row.rowIndex + 1"
    >
      <div
        v-for="cell in row.cells"
        :key="cell.key"
        data-runtime-kit-table-cell="v1"
        class="runtime-data-table__cell"
        :class="cell.className"
        :style="cell.style"
        role="cell"
        :aria-rowindex="cell.rowIndex + 1"
        :aria-colindex="cell.columnIndex + 1"
        :data-row-index="cell.rowIndex"
        :data-column-index="cell.columnIndex"
      >
        <span class="runtime-data-table__cell-text">{{ cell.text }}</span>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
export type RuntimeTableCellValue = string | number
export type RuntimeTableBorderStyle = 'solid' | 'dashed' | 'dotted' | 'none'
export type RuntimeTableBorderSide = 'top' | 'right' | 'bottom' | 'left'
export type RuntimeTableStyleRecord = Record<string, string | number>

export interface RuntimeTableBorderLine {
  /** 边框颜色，支持普通 CSS 颜色值 */
  color?: string
  /** 边框宽度，数字按 px 处理 */
  width?: number | string
  /** 边框线型 */
  style?: RuntimeTableBorderStyle
}

export type RuntimeTableBorderToken = RuntimeTableBorderLine | 'none'

export interface RuntimeTableBorderBox {
  /** 区域内所有单元格四边 */
  all?: RuntimeTableBorderToken
  /** 区域外框 */
  outer?: RuntimeTableBorderToken
  /** 区域内部横线和竖线 */
  inner?: RuntimeTableBorderToken
  /** 区域内部横线 */
  innerHorizontal?: RuntimeTableBorderToken
  /** 区域内部竖线 */
  innerVertical?: RuntimeTableBorderToken
  /** 区域上边框 */
  top?: RuntimeTableBorderToken
  /** 区域右边框 */
  right?: RuntimeTableBorderToken
  /** 区域下边框 */
  bottom?: RuntimeTableBorderToken
  /** 区域左边框 */
  left?: RuntimeTableBorderToken
}

export type RuntimeTableBorder = RuntimeTableBorderToken | RuntimeTableBorderBox

export interface RuntimeTableCellStyle {
  /** 单元格 Tailwind 类或普通 class */
  class?: string
  /** 单元格内联样式 */
  style?: RuntimeTableStyleRecord
  /** 区域边框；行列样式中可控制外框、内部线和四边 */
  border?: RuntimeTableBorder
  /** 列宽，仅 styles.columns 生效 */
  width?: number | string
  /** 行高，仅 styles.rows 生效 */
  height?: number | string
}

export interface RuntimeTableCellObject {
  /** 单元格文本 */
  text: RuntimeTableCellValue
  /** 单元格 Tailwind 类或普通 class */
  class?: string
  /** 单元格内联样式 */
  style?: RuntimeTableStyleRecord
  /** 单元格边框，可统一设置或单独控制四边 */
  border?: RuntimeTableBorder
}

export type RuntimeTableCellInput = RuntimeTableCellValue | RuntimeTableCellObject

export interface RuntimeTableStyleLayers {
  /** 整个表格区域样式，当前用于控制全表内外边框 */
  table?: {
    border?: RuntimeTableBorder
  }
  /** 全部单元格默认样式 */
  cell?: RuntimeTableCellStyle
  /** 指定行样式，key 为 0 基行索引 */
  rows?: Record<number, RuntimeTableCellStyle>
  /** 指定列样式，key 为 0 基列索引 */
  columns?: Record<number, RuntimeTableCellStyle>
  /** 指定单元格样式，key 为 "行索引,列索引" */
  cells?: Record<string, RuntimeTableCellStyle>
}

export interface DataTableProps {
  /** 完整二维表格数据 */
  rows: RuntimeTableCellInput[][]
  /** 表格宽度；数字按 px 处理，默认填满父容器 */
  width?: number | string
  /** 表格高度；数字按 px 处理，默认填满父容器 */
  height?: number | string
  /** 表格外层圆角、背景、边框和基础字体类 */
  class?: string | string[] | Record<string, boolean>
  /** 分层样式配置 */
  styles?: RuntimeTableStyleLayers
}
</script>

<script setup lang="ts">
import { computed, type CSSProperties, useAttrs, type StyleValue } from 'vue'
import clsx from 'clsx'
import { twMerge } from 'tailwind-merge'

defineOptions({
  inheritAttrs: false,
})

interface MergedCellStyle {
  className: string
  style: CSSProperties
  borderSides: RuntimeTableBorderSides
}

interface RenderedCell {
  key: string
  rowIndex: number
  columnIndex: number
  text: string
  className: string
  style: CSSProperties
}

interface RenderedRow {
  key: string
  rowIndex: number
  cells: RenderedCell[]
}

const DEFAULT_TABLE_BORDER: RuntimeTableBorder = {
  outer: {
    color: '#e2e8f0',
    width: 1,
    style: 'solid',
  },
  inner: {
    color: '#e2e8f0',
    width: 1,
    style: 'solid',
  },
}

type RuntimeTableBorderScope = 'table' | 'row' | 'column' | 'cell'
type RuntimeTableBorderSides = Partial<Record<RuntimeTableBorderSide, RuntimeTableBorderLine>>

interface RuntimeTableBorderContext {
  scope: RuntimeTableBorderScope
  rowIndex: number
  columnIndex: number
  rowStart: number
  rowEnd: number
  columnStart: number
  columnEnd: number
}

const props = withDefaults(defineProps<DataTableProps>(), {
  width: '100%',
  height: '100%',
  class: '',
  styles: () => ({}),
})
const attrs = useAttrs()

const rowCount = computed(() => props.rows.length)
const columnCount = computed(() => {
  return props.rows.reduce((maxCount, row) => Math.max(maxCount, row.length), 0)
})
const rootAttrs = computed(() => {
  const { class: _class, style: _style, ...restAttrs } = attrs
  return restAttrs
})
const forwardedStyle = computed<StyleValue | undefined>(() => attrs.style as StyleValue | undefined)
const rootClassName = computed(() => mergeClass(attrs.class, props.class))

const tableStyle = computed<CSSProperties>(() => ({
  width: normalizeCssSize(props.width) || '100%',
  height: normalizeCssSize(props.height) || '100%',
  gridTemplateColumns: buildTrackTemplate(columnCount.value, index => props.styles.columns?.[index]?.width),
  gridTemplateRows: buildTrackTemplate(rowCount.value, index => props.styles.rows?.[index]?.height),
}))

const renderedRows = computed<RenderedRow[]>(() => {
  const rows: RenderedRow[] = []

  for (let rowIndex = 0; rowIndex < rowCount.value; rowIndex += 1) {
    const cells: RenderedCell[] = []
    for (let columnIndex = 0; columnIndex < columnCount.value; columnIndex += 1) {
      const sourceCell = props.rows[rowIndex]?.[columnIndex] ?? ''
      const mergedStyle = resolveCellStyle(sourceCell, rowIndex, columnIndex)
      cells.push({
        key: `${rowIndex}-${columnIndex}`,
        rowIndex,
        columnIndex,
        text: normalizeCellText(sourceCell),
        className: mergedStyle.className,
        style: {
          gridColumn: columnIndex + 1,
          gridRow: rowIndex + 1,
          ...mergedStyle.style,
          ...buildBorderStyle(mergedStyle.borderSides),
        },
      })
    }
    rows.push({
      key: `row-${rowIndex}`,
      rowIndex,
      cells,
    })
  }

  return rows
})

/**
 * 构建 grid 轨道模板，未指定尺寸的行列均分剩余空间。
 * @param count 轨道数量
 * @param resolveSize 指定索引的尺寸解析函数
 * @returns CSS grid-template-* 值
 */
function buildTrackTemplate(count: number, resolveSize: (index: number) => number | string | undefined): string {
  if (count <= 0) {
    return ''
  }
  return Array.from({ length: count }, (_, index) => {
    return normalizeCssSize(resolveSize(index)) || 'minmax(0, 1fr)'
  }).join(' ')
}

/**
 * 按既定优先级合并单元格样式层。
 * @param sourceCell 单元格原始输入
 * @param rowIndex 0 基行索引
 * @param columnIndex 0 基列索引
 * @returns 可直接绑定到单元格的 class、style 和 border
 */
function resolveCellStyle(
  sourceCell: RuntimeTableCellInput,
  rowIndex: number,
  columnIndex: number,
): MergedCellStyle {
  const layers = [
    props.styles.cell,
    props.styles.columns?.[columnIndex],
    props.styles.rows?.[rowIndex],
    isCellObject(sourceCell) ? sourceCell : undefined,
    props.styles.cells?.[`${rowIndex},${columnIndex}`],
  ].filter((layer): layer is RuntimeTableCellStyle | RuntimeTableCellObject => Boolean(layer))

  return layers.reduce<MergedCellStyle>((merged, layer) => ({
    className: mergeClass(merged.className, layer.class),
    style: {
      ...merged.style,
      ...sanitizeCellStyle(layer.style),
    },
    borderSides: merged.borderSides,
  }), {
    className: '',
    style: {},
    borderSides: resolveBorderSides(sourceCell, rowIndex, columnIndex),
  })
}

/**
 * 按区域语义解析当前单元格最终四边边框。
 * @param sourceCell 单元格原始输入
 * @param rowIndex 0 基行索引
 * @param columnIndex 0 基列索引
 * @returns 当前单元格四边边框配置
 */
function resolveBorderSides(
  sourceCell: RuntimeTableCellInput,
  rowIndex: number,
  columnIndex: number,
): RuntimeTableBorderSides {
  const borders: RuntimeTableBorderSides = {}
  const hasExplicitTableBorder = Boolean(props.styles.table?.border)
  const layerInputs = [
    { scope: 'table' as const, border: hasExplicitTableBorder ? undefined : DEFAULT_TABLE_BORDER },
    { scope: 'table' as const, border: props.styles.table?.border },
    { scope: 'cell' as const, border: props.styles.cell?.border },
    { scope: 'column' as const, border: props.styles.columns?.[columnIndex]?.border },
    { scope: 'row' as const, border: props.styles.rows?.[rowIndex]?.border },
    { scope: 'cell' as const, border: isCellObject(sourceCell) ? sourceCell.border : undefined },
    { scope: 'cell' as const, border: props.styles.cells?.[`${rowIndex},${columnIndex}`]?.border },
  ]

  layerInputs.forEach(layer => {
    applyBorderLayer(borders, layer.border, buildBorderContext(layer.scope, rowIndex, columnIndex))
  })

  return borders
}

/**
 * 按边框作用域构建区域范围。
 * @param scope 边框作用域
 * @param rowIndex 当前单元格行索引
 * @param columnIndex 当前单元格列索引
 */
function buildBorderContext(
  scope: RuntimeTableBorderScope,
  rowIndex: number,
  columnIndex: number,
): RuntimeTableBorderContext {
  if (scope === 'row') {
    return {
      scope,
      rowIndex,
      columnIndex,
      rowStart: rowIndex,
      rowEnd: rowIndex,
      columnStart: 0,
      columnEnd: columnCount.value - 1,
    }
  }
  if (scope === 'column') {
    return {
      scope,
      rowIndex,
      columnIndex,
      rowStart: 0,
      rowEnd: rowCount.value - 1,
      columnStart: columnIndex,
      columnEnd: columnIndex,
    }
  }
  if (scope === 'cell') {
    return {
      scope,
      rowIndex,
      columnIndex,
      rowStart: rowIndex,
      rowEnd: rowIndex,
      columnStart: columnIndex,
      columnEnd: columnIndex,
    }
  }
  return {
    scope,
    rowIndex,
    columnIndex,
    rowStart: 0,
    rowEnd: rowCount.value - 1,
    columnStart: 0,
    columnEnd: columnCount.value - 1,
  }
}

/**
 * 应用一层区域边框配置。
 * @param target 当前累计边框
 * @param border 边框输入
 * @param context 当前单元格在区域中的位置
 */
function applyBorderLayer(
  target: RuntimeTableBorderSides,
  border: RuntimeTableBorder | undefined,
  context: RuntimeTableBorderContext,
): void {
  if (!border) {
    return
  }

  if (isBorderLine(border)) {
    applyAllCellSides(target, border)
    return
  }

  if (border.all !== undefined) {
    applyAllCellSides(target, border.all)
  }
  if (border.outer !== undefined) {
    applyOuterRegionSides(target, border.outer, context)
  }
  if (border.inner !== undefined || border.innerHorizontal !== undefined) {
    applyInnerHorizontalSides(target, border.innerHorizontal ?? border.inner, context)
  }
  if (border.inner !== undefined || border.innerVertical !== undefined) {
    applyInnerVerticalSides(target, border.innerVertical ?? border.inner, context)
  }
  ;(['top', 'right', 'bottom', 'left'] as RuntimeTableBorderSide[]).forEach(side => {
    const token = border[side]
    if (token === undefined) {
      return
    }
    if (isCellBorderScope(context.scope) || isOnRegionSide(side, context)) {
      target[side] = normalizeBorderToken(token)
    }
  })
}

/**
 * 判断边框输入是否为旧版统一线条配置。
 * @param border 边框输入
 */
function isBorderLine(border: RuntimeTableBorder): border is RuntimeTableBorderToken {
  return typeof border === 'string' ||
    ['color', 'width', 'style'].some(key => Object.prototype.hasOwnProperty.call(border, key))
}

/**
 * 单元格作用域下 top/right/bottom/left 直接表示该单元格四边。
 * @param scope 边框作用域
 */
function isCellBorderScope(scope: RuntimeTableBorderScope): boolean {
  return scope === 'cell'
}

/**
 * 应用到单元格全部四边。
 * @param target 当前累计边框
 * @param token 边框线条或 none
 */
function applyAllCellSides(target: RuntimeTableBorderSides, token: RuntimeTableBorderToken): void {
  ;(['top', 'right', 'bottom', 'left'] as RuntimeTableBorderSide[]).forEach(side => {
    target[side] = normalizeBorderToken(token)
  })
}

/**
 * 应用区域外框。
 * @param target 当前累计边框
 * @param token 边框线条或 none
 * @param context 当前单元格在区域中的位置
 */
function applyOuterRegionSides(
  target: RuntimeTableBorderSides,
  token: RuntimeTableBorderToken,
  context: RuntimeTableBorderContext,
): void {
  ;(['top', 'right', 'bottom', 'left'] as RuntimeTableBorderSide[]).forEach(side => {
    if (isOnRegionSide(side, context)) {
      target[side] = normalizeBorderToken(token)
    }
  })
}

/**
 * 应用区域内部横线，只落在非末行单元格的 bottom 边，避免双线叠加。
 * @param target 当前累计边框
 * @param token 边框线条或 none
 * @param context 当前单元格在区域中的位置
 */
function applyInnerHorizontalSides(
  target: RuntimeTableBorderSides,
  token: RuntimeTableBorderToken | undefined,
  context: RuntimeTableBorderContext,
): void {
  if (!token || context.rowIndex >= context.rowEnd) {
    return
  }
  target.bottom = normalizeBorderToken(token)
}

/**
 * 应用区域内部竖线，只落在非末列单元格的 right 边，避免双线叠加。
 * @param target 当前累计边框
 * @param token 边框线条或 none
 * @param context 当前单元格在区域中的位置
 */
function applyInnerVerticalSides(
  target: RuntimeTableBorderSides,
  token: RuntimeTableBorderToken | undefined,
  context: RuntimeTableBorderContext,
): void {
  if (!token || context.columnIndex >= context.columnEnd) {
    return
  }
  target.right = normalizeBorderToken(token)
}

/**
 * 判断当前单元格是否位于区域指定外边。
 * @param side 边方向
 * @param context 当前单元格在区域中的位置
 */
function isOnRegionSide(
  side: RuntimeTableBorderSide,
  context: RuntimeTableBorderContext,
): boolean {
  if (side === 'top') return context.rowIndex === context.rowStart
  if (side === 'right') return context.columnIndex === context.columnEnd
  if (side === 'bottom') return context.rowIndex === context.rowEnd
  return context.columnIndex === context.columnStart
}

/**
 * 规范化边框 token，none 会转为 style=none。
 * @param token 边框线条或 none
 */
function normalizeBorderToken(token: RuntimeTableBorderToken): RuntimeTableBorderLine {
  if (token === 'none') {
    return { style: 'none' }
  }
  return token
}

/**
 * 移除单元格内联样式里的 width/height，避免和行列尺寸入口冲突。
 * @param style 原始内联样式
 * @returns 可用于单元格的内联样式
 */
function sanitizeCellStyle(style?: RuntimeTableStyleRecord): CSSProperties {
  const nextStyle: CSSProperties = {}
  Object.entries(style || {}).forEach(([key, value]) => {
    if (key === 'width' || key === 'height') {
      return
    }
    ;(nextStyle as Record<string, string | number>)[key] = value
  })
  return nextStyle
}

/**
 * 构建 CSS border 简写。
 * @param borders 单元格四边边框配置
 * @returns CSSProperties 片段
 */
function buildBorderStyle(borders: RuntimeTableBorderSides): CSSProperties {
  return {
    borderTop: buildCssBorderValue(borders.top),
    borderRight: buildCssBorderValue(borders.right),
    borderBottom: buildCssBorderValue(borders.bottom),
    borderLeft: buildCssBorderValue(borders.left),
  }
}

/**
 * 构造单边 CSS border 值。
 * @param border 单边边框配置
 */
function buildCssBorderValue(border?: RuntimeTableBorderLine): string {
  const borderStyle = border?.style || 'solid'
  if (!border || borderStyle === 'none') {
    return 'none'
  }
  return `${normalizeCssSize(border.width) || '1px'} ${borderStyle} ${border.color || '#e2e8f0'}`
}

/**
 * 将数字尺寸规范化为 px，字符串尺寸保持原样。
 * @param value 尺寸输入
 * @returns CSS 尺寸值
 */
function normalizeCssSize(value?: number | string): string {
  if (value === undefined || value === null || value === '') {
    return ''
  }
  return typeof value === 'number' ? `${value}px` : value
}

/**
 * 读取单元格展示文本。
 * @param cell 单元格输入
 */
function normalizeCellText(cell: RuntimeTableCellInput): string {
  return String(isCellObject(cell) ? cell.text : cell)
}

/**
 * 判断是否为对象形式单元格。
 * @param cell 单元格输入
 */
function isCellObject(cell: RuntimeTableCellInput): cell is RuntimeTableCellObject {
  return typeof cell === 'object' && cell !== null && 'text' in cell
}

/**
 * 合并并去重 Tailwind class，后传入的层级优先生效。
 * @param values class 输入列表
 */
function mergeClass(...values: unknown[]): string {
  return twMerge(clsx(values))
}
</script>

<style scoped>
.runtime-data-table {
  box-sizing: border-box;
  display: grid;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.runtime-data-table__row-proxy {
  display: contents;
}

.runtime-data-table__cell {
  box-sizing: border-box;
  display: flex;
  min-width: 0;
  min-height: 0;
  align-items: center;
  justify-content: flex-start;
  overflow: hidden;
  padding: 8px 10px;
  line-height: 1.25;
  text-align: left;
  white-space: normal;
}

.runtime-data-table__cell-text {
  display: block;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
  overflow-wrap: anywhere;
}
</style>
