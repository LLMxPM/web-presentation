/**
 * 文件用途：从 ECharts option 中提取符合 PPTX 导出契约的归一化图表数据（支持柱状图、折线图、饼图和环形图）。
 * 遇到多坐标轴、函数 formatter、复杂 dataset 或不支持图表时返回 null，交由 SVG/截图安全降级。
 */

import type { PptxChartDataPayload, PptxChartType } from '@/core/services/pptx/PPTXRuntimeKitExportDom'
import { validateRuntimeKitChartPayload } from '@/core/services/pptx/PPTXRuntimeKitExportDom'

type OptionRecord = Record<string, unknown>

/**
 * 从 ECharts option 中安全提取归一化图表数据载荷。
 * @param option ECharts option 对象
 * @returns 归一化图表数据载荷；若不支持或结构复杂则返回 null
 */
export function extractNormalizedChartData(option: unknown): PptxChartDataPayload | null {
  if (!option || typeof option !== 'object' || Array.isArray(option)) {
    return null
  }

  const opt = option as OptionRecord
  if (hasFunctionOrCycle(opt)) return null

  // 1. 复杂特征排查：不支持 dataset transform、图形组件、极坐标系、日历坐标系
  if (opt.dataset || opt.graphic || opt.polar || opt.calendar || opt.radar || opt.geo) {
    return null
  }

  // 检查多坐标轴（如双 Y 轴）
  if (Array.isArray(opt.yAxis) && opt.yAxis.length > 1) {
    return null
  }
  if (Array.isArray(opt.xAxis) && opt.xAxis.length > 1) {
    return null
  }

  // 2. 检查 series
  const rawSeries = opt.series
  const seriesList = Array.isArray(rawSeries)
    ? (rawSeries as OptionRecord[])
    : rawSeries && typeof rawSeries === 'object'
      ? [rawSeries as OptionRecord]
      : []

  if (seriesList.length === 0) {
    return null
  }
  if (seriesList.some(series => !series || typeof series !== 'object' || series.stack || series.areaStyle ||
    series.smooth || series.roseType || series.coordinateSystem || series.xAxisIndex || series.yAxisIndex ||
    (series.itemStyle && typeof (series.itemStyle as OptionRecord).color === 'object'))) return null
  const axis = (value: unknown) => Array.isArray(value) ? value[0] : value
  const xAxis = axis(opt.xAxis) as OptionRecord | undefined
  const yAxis = axis(opt.yAxis) as OptionRecord | undefined
  // 目前原生适配只支持普通垂直类目图；水平、时间、对数和自定义轴范围保留原图。
  if ((xAxis?.type && xAxis.type !== 'category') || (yAxis?.type && yAxis.type !== 'value') ||
    xAxis?.min !== undefined || xAxis?.max !== undefined || yAxis?.min !== undefined || yAxis?.max !== undefined) return null

  // 确保所有 series 类型单一且受支持
  const firstType = String(seriesList[0].type || 'bar').toLowerCase()
  if (!['bar', 'line', 'pie'].includes(firstType)) {
    return null
  }
  const hasMixedTypes = seriesList.some(s => String(s.type || firstType).toLowerCase() !== firstType)
  if (hasMixedTypes) {
    return null
  }

  // 提取标题
  let titleText: string | undefined
  if (opt.title && typeof opt.title === 'object') {
    const titleObj = opt.title as OptionRecord
    if (typeof titleObj.text === 'string' && titleObj.text.trim()) {
      titleText = titleObj.text.trim()
    }
  }

  // 3. 处理 饼图 / 环形图
  if (firstType === 'pie') {
    if (seriesList.length > 1) {
      // 复合多饼图不支持
      return null
    }
    const pieSeries = seriesList[0]
    const dataItems = Array.isArray(pieSeries.data) ? pieSeries.data : []
    if (dataItems.length === 0) {
      return null
    }

    const categories: string[] = []
    const values: number[] = []

    for (let i = 0; i < dataItems.length; i++) {
      const item = dataItems[i]
      if (!item || typeof item !== 'object') {
        return null
      }
      const itemRecord = item as OptionRecord
      const name = String(itemRecord.name || `项 ${i + 1}`)
      if (typeof itemRecord.value !== 'number') return null
      const val = itemRecord.value
      if (!Number.isFinite(val)) {
        return null
      }
      categories.push(name)
      values.push(val)
    }

    // 判断是否为环形图 (doughnut)
    let chartType: PptxChartType = 'pie'
    let holeSize: number | undefined
    if (Array.isArray(pieSeries.radius) && pieSeries.radius.length >= 2) {
      const innerRadius = String(pieSeries.radius[0]).trim()
      const innerNum = Number.parseFloat(innerRadius)
      if (Number.isFinite(innerNum) && innerNum > 0) {
        chartType = 'doughnut'
        const outerRadius = String(pieSeries.radius[1]).trim()
        const outerNum = Number.parseFloat(outerRadius)
        if (!Number.isFinite(outerNum) || outerNum <= innerNum || innerRadius.endsWith('%') !== outerRadius.endsWith('%')) return null
        holeSize = Math.round(innerNum / outerNum * 100)
      }
    }

    return validateRuntimeKitChartPayload({
      version: 'v1',
      chartType,
      title: titleText,
      categories,
      series: [
        {
          name: String(pieSeries.name || '数值'),
          values,
        },
      ],
      options: {
        showLegend: opt.legend !== false,
        showTitle: Boolean(titleText),
        holeSize,
      },
    })
  }

  // 4. 处理 柱状图 (bar) 与 折线图 (line)
  const chartType: PptxChartType = firstType === 'line' ? 'line' : 'bar'

  // 提取类目轴 (x 轴或水平条形图的 y 轴)
  let rawCategories: unknown[] = []
  if (opt.xAxis && typeof opt.xAxis === 'object') {
    const xAxisObj = (Array.isArray(opt.xAxis) ? opt.xAxis[0] : opt.xAxis) as OptionRecord
    if (Array.isArray(xAxisObj.data)) {
      rawCategories = xAxisObj.data
    }
  } else if (opt.yAxis && typeof opt.yAxis === 'object') {
    const yAxisObj = (Array.isArray(opt.yAxis) ? opt.yAxis[0] : opt.yAxis) as OptionRecord
    if (Array.isArray(yAxisObj.data)) {
      rawCategories = yAxisObj.data
    }
  }

  const categories = rawCategories.map(cat => {
    if (cat && typeof cat === 'object' && 'value' in (cat as OptionRecord)) {
      return String((cat as OptionRecord).value)
    }
    return String(cat ?? '')
  })

  // 提取每个系列
  const normalizedSeries: Array<{ name: string; values: number[]; color?: string }> = []
  for (let sIdx = 0; sIdx < seriesList.length; sIdx++) {
    const s = seriesList[sIdx]
    const sName = String(s.name || `系列 ${sIdx + 1}`)
    const sData = Array.isArray(s.data) ? s.data : []
    const values: number[] = []

    for (const val of sData) {
      let numVal: number
      if (val && typeof val === 'object' && 'value' in (val as OptionRecord)) {
        if (typeof (val as OptionRecord).value !== 'number') return null
        numVal = (val as OptionRecord).value as number
      } else {
        if (typeof val !== 'number') return null
        numVal = val
      }
      if (!Number.isFinite(numVal)) {
        return null
      }
      values.push(numVal)
    }

    if (values.length === 0) {
      return null
    }

    let seriesColor: string | undefined
    if (s.itemStyle && typeof s.itemStyle === 'object') {
      const itemStyle = s.itemStyle as OptionRecord
      if (typeof itemStyle.color === 'string') {
        seriesColor = itemStyle.color
      }
    }

    normalizedSeries.push({
      name: sName,
      values,
      color: seriesColor,
    })
  }

  // 保证 categories 数量与 values 对齐；若 categories 为空，使用默认 1..N
  const maxLen = Math.max(...normalizedSeries.map(s => s.values.length))
  if (categories.length === 0) {
    for (let i = 1; i <= maxLen; i++) {
      categories.push(`类别 ${i}`)
    }
  }

  return validateRuntimeKitChartPayload({
    version: 'v1',
    chartType,
    title: titleText,
    categories,
    series: normalizedSeries,
    options: {
      showLegend: opt.legend !== false,
      showTitle: Boolean(titleText),
    },
  })
}

/** 函数回调和循环结构无法进入纯数据图表契约，保持原图导出。 */
function hasFunctionOrCycle(value: unknown, ancestors = new Set<object>()): boolean {
  if (typeof value === 'function') return true
  if (!value || typeof value !== 'object') return false
  if (ancestors.has(value) || ancestors.size >= 32) return true
  const next = new Set(ancestors).add(value)
  return Object.values(value).some(child => hasFunctionOrCycle(child, next))
}
