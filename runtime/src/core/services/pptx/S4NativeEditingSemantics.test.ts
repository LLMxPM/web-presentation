/**
 * 文件用途：PPTX 导出 S4 阶段专项测试（原生列表、显式组合与图表数据契约）。
 */

import { describe, expect, it, vi } from 'vitest'
import { ListParagraphParser } from './extractors/ListParagraphParser'
import { extractNormalizedChartData } from './extractors/EchartsDataExtractor'
import { parseRuntimeKitChartPayload } from './PPTXRuntimeKitExportDom'
import { patchGroupInSlideXml, type PptxGroupInstruction } from './writer/OoxmlGroupPatcher'
import { convert, createSlideMock } from './PPTXDomConverter.test-support'

describe('S4 原生编辑语义（Native Editing Semantics）', () => {
  describe('工作包 1：原生列表（Native Lists）', () => {
    const listParser = new ListParagraphParser()
    const dummyResolver = (_el: HTMLElement, _style: CSSStyleDeclaration, text: string) => ({
      color: '000000',
      bold: _el.tagName.toLowerCase() === 'strong',
      text,
    })

    it('应正确解析无序列表（ul/li）并生成 bullet 与换段选项', () => {
      const ul = document.createElement('ul')
      ul.innerHTML = '<li>第一项</li><li>第二项<strong>重点</strong></li>'
      document.body.appendChild(ul)

      expect(listParser.isListRootElement(ul)).toBe(true)
      expect(listParser.isNativeListCompatible(ul)).toBe(true)

      const result = listParser.parseList(ul, dummyResolver)
      expect(result).not.toBeNull()
      expect(result!.itemCount).toBe(2)

      const runs = result!.runs
      // 第一个 li
      expect(runs[0].text).toBe('第一项')
      expect(runs[0].options?.bullet).toBe(true)
      expect(runs[0].options?.indentLevel).toBe(0)
      expect(runs[0].options?.breakLine).toBeUndefined()

      // 第二个 li（含富文本 strong）
      expect(runs[1].text).toBe('第二项')
      expect(runs[1].options?.bullet).toBe(true)
      expect(runs[1].options?.breakLine).toBe(true)

      expect(runs[2].text).toBe('重点')
      expect(runs[2].options?.bold).toBe(true)

      ul.remove()
    })

    it('应正确解析有序列表（ol/li）并支持 start 属性与分级缩进', () => {
      const ol = document.createElement('ol')
      ol.setAttribute('start', '5')
      ol.innerHTML = `
        <li>项目五</li>
        <li>
          项目六
          <ol>
            <li>子项目 6.1</li>
          </ol>
        </li>
      `
      document.body.appendChild(ol)

      expect(listParser.isListRootElement(ol)).toBe(true)
      const result = listParser.parseList(ol, dummyResolver)
      expect(result).not.toBeNull()

      const runs = result!.runs
      // 顶层第一项：序号从 5 开始
      expect(runs[0].text).toBe('项目五')
      expect(runs[0].options?.bullet).toEqual({ type: 'number', numberStart: 5 })
      expect(runs[0].options?.indentLevel).toBe(0)

      // 顶层第二项：序号为 6
      expect(runs[1].text).toBe('项目六')
      expect(runs[1].options?.bullet).toEqual({ type: 'number', numberStart: 6 })
      expect(runs[1].options?.indentLevel).toBe(0)
      expect(runs[1].options?.breakLine).toBe(true)

      // 嵌套子项：indentLevel = 1，序号为 1
      expect(runs[2].text).toBe('子项目 6.1')
      expect(runs[2].options?.bullet).toEqual({ type: 'number', numberStart: 1 })
      expect(runs[2].options?.indentLevel).toBe(1)
      expect(runs[2].options?.breakLine).toBe(true)

      ol.remove()
    })

    it('当 li 内包含表格或媒体等复杂子节点时应判定为不兼容，由常规 DOM 展开', () => {
      const ul = document.createElement('ul')
      ul.innerHTML = '<li>普通项</li><li><table><tr><td>表格</td></tr></table></li>'
      document.body.appendChild(ul)

      expect(listParser.isNativeListCompatible(ul)).toBe(false)
      expect(listParser.parseList(ul, dummyResolver)).toBeNull()

      ul.remove()
    })
  })

  describe('工作包 2：显式组合 (Group Shapes)', () => {
    it('OoxmlGroupPatcher 应将 slide XML 中的成员图元移入原生 p:grpSp 包装', () => {
      const fakeSlideXml = `
        <p:spTree>
          <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
          <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>
          <p:sp><p:nvSpPr><p:cNvPr id="2" name="card-1:shape:背景"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="914400" y="914400"/><a:ext cx="3657600" cy="1828800"/></a:xfrm></p:spPr></p:sp>
          <p:sp><p:nvSpPr><p:cNvPr id="3" name="card-1:text:标题"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="1000000" y="1000000"/><a:ext cx="2000000" cy="500000"/></a:xfrm></p:spPr></p:sp>
        </p:spTree>
      `.trim()

      const instruction: PptxGroupInstruction = {
        pageIndex: 1,
        groupId: 'card-1',
        groupName: '卡片容器',
        x: 1,
        y: 1,
        w: 4,
        h: 2,
        memberObjectNames: ['card-1:shape:背景', 'card-1:text:标题'],
      }

      const patchedXml = patchGroupInSlideXml(fakeSlideXml, instruction, 999)

      // 验证生成了 p:grpSp 且包含对应的 ID 和名称
      expect(patchedXml).toContain('<p:grpSp>')
      expect(patchedXml).toContain('<p:cNvPr id="999" name="卡片容器"/>')
      // 验证组外框 EMU 换算（1 inch = 914400 EMU, 4 inch = 3657600 EMU）
      expect(patchedXml).toContain('<a:off x="914400" y="914400"/><a:ext cx="3657600" cy="1828800"/>')
      // 验证两个成员都在 p:grpSp 内部
      expect(patchedXml).toContain('name="card-1:shape:背景"')
      expect(patchedXml).toContain('name="card-1:text:标题"')
      // 验证成员没有重复留在原位
      const matchesShapeBg = patchedXml.match(/name="card-1:shape:背景"/g)
      expect(matchesShapeBg?.length).toBe(1)
    })

    it('少于 2 个成员的组不应触发包装', () => {
      const fakeSlideXml = '<p:spTree><p:sp><p:nvSpPr><p:cNvPr id="2" name="single:text:单项"/></p:nvSpPr></p:sp></p:spTree>'
      const instruction: PptxGroupInstruction = {
        pageIndex: 1,
        groupId: 'single',
        groupName: '单个',
        x: 1,
        y: 1,
        w: 1,
        h: 1,
        memberObjectNames: ['single:text:单项'],
      }

      const result = patchGroupInSlideXml(fakeSlideXml, instruction, 100)
      expect(result).toBe(fakeSlideXml)
      expect(result).not.toContain('<p:grpSp>')
    })
  })

  describe('工作包 3：图表数据契约与原生图表导出 (Native Charts)', () => {
    it('EchartsDataExtractor 应成功提取简单柱状图与折线图数据', () => {
      const barOption = {
        title: { text: '季度营收' },
        xAxis: { data: ['Q1', 'Q2', 'Q3', 'Q4'] },
        series: [
          { name: '2025', type: 'bar', data: [100, 150, 200, 250] },
          { name: '2026', type: 'bar', data: [120, 180, 240, 300] },
        ],
      }

      const payload = extractNormalizedChartData(barOption)
      expect(payload).not.toBeNull()
      expect(payload?.version).toBe('v1')
      expect(payload?.chartType).toBe('bar')
      expect(payload?.title).toBe('季度营收')
      expect(payload?.categories).toEqual(['Q1', 'Q2', 'Q3', 'Q4'])
      expect(payload?.series).toHaveLength(2)
      expect(payload?.series[0].values).toEqual([100, 150, 200, 250])
    })

    it('EchartsDataExtractor 应识别环形图（doughnut）与 holeSize', () => {
      const doughnutOption = {
        title: { text: '占比分布' },
        series: [
          {
            name: '份额',
            type: 'pie',
            radius: ['45%', '70%'],
            data: [
              { name: '产品 A', value: 40 },
              { name: '产品 B', value: 60 },
            ],
          },
        ],
      }

      const payload = extractNormalizedChartData(doughnutOption)
      expect(payload).not.toBeNull()
      expect(payload?.chartType).toBe('doughnut')
      expect(payload?.categories).toEqual(['产品 A', '产品 B'])
      expect(payload?.series[0].values).toEqual([40, 60])
      expect(payload?.options?.holeSize).toBe(45)
    })

    it('复杂图表（双 Y 轴或 dataset transform）应返回 null 触发安全降级', () => {
      const complexOption = {
        yAxis: [{ type: 'value' }, { type: 'value' }], // 双 Y 轴
        series: [{ type: 'bar', data: [10, 20] }],
      }
      expect(extractNormalizedChartData(complexOption)).toBeNull()

      const datasetOption = {
        dataset: { source: [['A', 1], ['B', 2]] },
        series: [{ type: 'bar' }],
      }
      expect(extractNormalizedChartData(datasetOption)).toBeNull()
    })

    it('DOM 契约解析器 parseRuntimeKitChartPayload 应验证版本与数据有效性', () => {
      const div = document.createElement('div')
      div.setAttribute('data-runtime-kit-chart', 'v1')
      div.setAttribute(
        'data-runtime-kit-chart-data',
        JSON.stringify({
          version: 'v1',
          chartType: 'pie',
          categories: ['甲', '乙'],
          series: [{ name: '占比', values: [30, 70] }],
        }),
      )

      const parsed = parseRuntimeKitChartPayload(div)
      expect(parsed).not.toBeNull()
      expect(parsed?.chartType).toBe('pie')

      // 版本不匹配时返回 null
      div.setAttribute('data-runtime-kit-chart', 'v2')
      expect(parseRuntimeKitChartPayload(div)).toBeNull()
    })

    it('PPTXDomConverter 应将带图表契约的节点导出为 slide.addChart 原生图表', async () => {
      document.body.innerHTML = '<div id="page"></div>'
      const page = document.getElementById('page')!
      const chartDiv = document.createElement('div')
      chartDiv.setAttribute('data-runtime-kit-media', 'v1')
      chartDiv.setAttribute('data-runtime-kit-media-kind', 'chart')
      chartDiv.setAttribute('data-runtime-kit-chart', 'v1')
      chartDiv.setAttribute(
        'data-runtime-kit-chart-data',
        JSON.stringify({
          version: 'v1',
          chartType: 'bar',
          categories: ['一月', '二月'],
          series: [{ name: '销量', values: [50, 80] }],
        }),
      )
      page.appendChild(chartDiv)

      const createRect = (left: number, top: number, width: number, height: number) => ({
        x: left,
        y: top,
        left,
        top,
        width,
        height,
        right: left + width,
        bottom: top + height,
        toJSON: () => ({}),
      })

      vi.spyOn(page, 'getBoundingClientRect').mockReturnValue(createRect(0, 0, 1920, 1080))
      vi.spyOn(chartDiv, 'getBoundingClientRect').mockReturnValue(createRect(100, 100, 600, 400))

      const mockSlide = createSlideMock()
      const report = await convert(mockSlide)

      expect(mockSlide.addChart).toHaveBeenCalledTimes(1)
      expect(mockSlide.addChart).toHaveBeenCalledWith(
        'bar',
        [
          {
            name: '销量',
            labels: ['一月', '二月'],
            values: [50, 80],
          },
        ],
        expect.objectContaining({
          showLegend: true,
        }),
      )

      const chartItem = report.items.find(item => item.sourceType === 'chart')
      expect(chartItem).toBeDefined()
      expect(chartItem?.result).toBe('editable-shape')
      expect(chartItem?.editable).toBe(true)
    })
  })
})
