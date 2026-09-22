// @vitest-environment jsdom

/**
 * 文件用途：验证 PPTX DOM 转换器对可编辑文本、形状、表格和 SVG 的转换逻辑。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { convert, createSlideMock } from './PPTXDomConverter.test-support'

describe('PPTXDomConverter', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    delete window.__RUNTIME_PREVIEW_CONTEXT__
    delete window.__RUNTIME_PREVIEW_TOKEN__
    delete window.__RUNTIME_PRELOADED_CONFIG__
    delete window.__RUNTIME_PUBLIC_BASE_URL__
  })

  it('应将标题、正文、关键数字和简单形状转换为可编辑对象', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px; background: #ffffff;">
        <section style="width: 800px; height: 320px; background: rgb(248, 250, 252); border: 1px solid rgb(203, 213, 225); border-radius: 12px;">
          <h1 style="width: 600px; height: 64px; font-size: 40px; font-weight: 700; color: rgb(15, 23, 42);">业务增长概览</h1>
          <p style="width: 620px; height: 48px; font-size: 20px; color: rgb(71, 85, 105);">核心指标保持稳定增长</p>
          <strong style="display: block; width: 260px; height: 72px; font-size: 56px; font-weight: 700; color: rgb(37, 99, 235);">128%</strong>
          <div style="width: 500px; height: 2px; background: rgb(15, 23, 42);"></div>
        </section>
      </div>
    `

    const report = await convert(slide)

    expect(slide.addText).toHaveBeenCalledTimes(3)
    expect(slide.addText).toHaveBeenCalledWith('业务增长概览', expect.objectContaining({ fontSize: 20 }))
    expect(slide.addText).toHaveBeenCalledWith('核心指标保持稳定增长', expect.objectContaining({ fontSize: 10 }))
    expect(slide.addText).toHaveBeenCalledWith('128%', expect.objectContaining({ fontSize: 28 }))
    expect(slide.addShape).toHaveBeenCalledWith('roundRect', expect.objectContaining({
      fill: expect.objectContaining({ color: 'F8FAFC' }),
      line: expect.objectContaining({ color: 'CBD5E1' }),
    }))
    expect(slide.addShape).toHaveBeenCalledWith('rect', expect.objectContaining({
      fill: expect.objectContaining({ color: '0F172A' }),
    }))
    expect(report.items.filter(item => item.result === 'editable-text')).toHaveLength(3)
    expect(report.items.filter(item => item.result === 'editable-shape')).toHaveLength(2)
    expect(report.items.map(item => item.sourceType)).toEqual(expect.arrayContaining(['title', 'body', 'number', 'shape']))
  })

  it('应为纯背景细线保留非零 PPT 盒模型', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px; background: #0f172a;">
        <div style="display: flex; align-items: center; width: 900px; height: 80px;">
          <div style="width: 120px; height: 48px;"></div>
          <div style="width: 1px; height: 48px; background-color: rgba(255, 255, 255, 0.5);"></div>
          <span style="display: inline-block; width: 520px; height: 48px; font-size: 32px; color: #ffffff;">警用装备智能管理平台建设方案</span>
        </div>
        <div style="position: absolute; left: 160px; top: 120px; width: 48px; height: 1px; background-color: rgba(255, 255, 255, 0.5);"></div>
      </div>
    `

    await convert(slide)

    const rectOptions = slide.addShape.mock.calls
      .filter(([shapeName, options]) => {
        return shapeName === 'rect' && (options as Record<string, Record<string, unknown>>)?.fill?.color === 'FFFFFF'
      })
      .map(([, options]) => options as Record<string, unknown>)
    expect(rectOptions).toHaveLength(2)
    rectOptions.forEach(options => {
      expect(options.w).toBeGreaterThan(0)
      expect(options.h).toBeGreaterThan(0)
      expect(options.fill).toEqual(expect.objectContaining({
        color: 'FFFFFF',
        transparency: 50,
      }))
      expect(options.line).toEqual(expect.objectContaining({ transparency: 100 }))
    })
  })

  it('应将普通块级文本的 Tailwind 左侧 padding 映射为 PPT 文本框左边距', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div style="width: 800px; height: 160px;">
          <div class="pl-6" style="width: 800px; height: 40px; color: #0f172a; font-size: 16px;">
            <span style="color: #7c3aed;">"model"</span>: <span style="color: #16a34a;">"xxx"</span>,
          </div>
          <div class="pl-12" style="width: 800px; height: 40px; color: #0f172a; font-size: 16px;">
            { <span style="color: #7c3aed;">"role"</span>: <span style="color: #16a34a;">"system"</span> }
          </div>
        </div>
      </div>
    `

    await convert(slide)
    const firstLevelCall = slide.addText.mock.calls.find(([text]) => {
      return Array.isArray(text) && text.some(run => run.text === '"model"')
    })
    const secondLevelCall = slide.addText.mock.calls.find(([text]) => {
      return Array.isArray(text) && text.some(run => run.text === '"role"')
    })
    const firstLevelRuns = firstLevelCall?.[0]

    expect(firstLevelRuns).toEqual(expect.arrayContaining([
      expect.objectContaining({ text: '"model"', options: expect.objectContaining({ color: '7C3AED' }) }),
      expect.objectContaining({ text: '"xxx"', options: expect.objectContaining({ color: '16A34A' }) }),
    ]))
    expect(firstLevelCall?.[1]).toEqual(expect.objectContaining({ margin: [12, 0, 0, 0] }))
    expect(secondLevelCall?.[1]).toEqual(expect.objectContaining({ margin: [24, 0, 0, 0] }))
  })

  it('应保留富文本的嵌套样式、NBSP 和显式换行', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <p style="width: 800px; height: 80px; color: #334155; font-size: 16px;">
          前缀 <strong style="font-weight: 700;"><span style="color: #dc2626;">重点</span></strong>&nbsp;尾部<br>
          <span style="color: #2563eb;">下一行</span>
        </p>
      </div>
    `

    await convert(slide)
    const richTextCall = slide.addText.mock.calls.find(([text]) => Array.isArray(text))
    const runs = richTextCall?.[0]

    expect(runs).toEqual(expect.arrayContaining([
      expect.objectContaining({ text: '重点', options: expect.objectContaining({ color: 'DC2626', bold: true }) }),
      expect.objectContaining({ text: '下一行', options: expect.objectContaining({ color: '2563EB', softBreakBefore: true }) }),
    ]))
    expect(Array.isArray(runs) ? runs.map(run => run.text).join('') : '').toContain('\u00A0尾部')
  })

  it('带视觉盒的 inline 子元素不应合并进富文本 run', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div style="width: 600px; height: 48px; color: #334155; font-size: 16px;">
          状态
          <span style="display: inline-block; width: 80px; height: 28px; padding: 4px 12px; background: #dbeafe; border-radius: 14px; color: #1d4ed8;">运行中</span>
        </div>
      </div>
    `

    await convert(slide)

    expect(slide.addText.mock.calls.some(([text]) => Array.isArray(text))).toBe(false)
    expect(slide.addText).toHaveBeenCalledWith('运行中', expect.objectContaining({ shape: 'roundRect' }))
  })

  it('应按 PptxGenJS 文本框实际顺序导出非对称文本 padding', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div
          style="width: 800px; height: 80px; padding: 8px 12px 16px 20px; font-size: 16px;"
        >非对称内边距</div>
      </div>
    `

    await convert(slide)

    expect(slide.addText).toHaveBeenCalledWith('非对称内边距', expect.objectContaining({
      margin: [10, 6, 8, 4],
    }))
  })

  it('应导出页面缩放后测量宽度不足 1px 的背景竖线', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px; background: #0f172a;">
        <div id="divider" class="h-10 w-px bg-white/50" style="width: 1px; height: 40px; background-color: rgba(255, 255, 255, 0.5);"></div>
      </div>
    `
    const page = document.getElementById('page') as HTMLElement
    const divider = document.getElementById('divider') as HTMLElement
    vi.spyOn(page, 'getBoundingClientRect').mockReturnValue({
      x: 0,
      y: 0,
      left: 0,
      top: 0,
      right: 960,
      bottom: 540,
      width: 960,
      height: 540,
      toJSON: () => ({}),
    } as DOMRect)
    vi.spyOn(divider, 'getBoundingClientRect').mockReturnValue({
      x: 80,
      y: 120,
      left: 80,
      top: 120,
      right: 80.5,
      bottom: 140,
      width: 0.5,
      height: 20,
      toJSON: () => ({}),
    } as DOMRect)

    await convert(slide)

    expect(slide.addShape).toHaveBeenCalledWith('rect', expect.objectContaining({
      w: expect.any(Number),
      h: expect.any(Number),
      fill: expect.objectContaining({
        color: 'FFFFFF',
        transparency: 50,
      }),
    }))
  })

  it('应将 Runtime Kit 表格导出为 PPT 原生可编辑表格', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px; background: #ffffff;">
        <div
          data-runtime-kit-table="v1"
          role="table"
          aria-rowcount="2"
          aria-colcount="2"
          style="position: absolute; left: 100px; top: 80px; width: 400px; height: 160px; font-size: 16px;"
        >
          <div role="row" style="display: contents;">
            <div
              data-runtime-kit-table-cell="v1"
              data-row-index="0"
              data-column-index="0"
              role="columnheader"
              style="width: 140px; height: 64px; color: #0f172a; background: #f1f5f9; font-weight: 600; padding: 8px 12px; border: 1px solid #cbd5e1;"
            >指标</div>
            <div
              data-runtime-kit-table-cell="v1"
              data-row-index="0"
              data-column-index="1"
              role="columnheader"
              style="width: 260px; height: 64px; color: #2563eb; background: #dbeafe; font-size: 20px; font-weight: 700; text-align: right; vertical-align: middle; padding: 8px 12px; border: 2px dashed #0f172a;"
            >收入</div>
          </div>
          <div role="row" style="display: contents;">
            <div
              data-runtime-kit-table-cell="v1"
              data-row-index="1"
              data-column-index="0"
              role="rowheader"
              style="width: 140px; height: 96px; color: #475569; background: #ffffff; padding: 8px 12px; border: 1px solid #cbd5e1;"
            >Q2</div>
            <div
              data-runtime-kit-table-cell="v1"
              data-row-index="1"
              data-column-index="1"
              role="cell"
              style="width: 260px; height: 96px; color: #111827; background: #ffffff; padding: 8px 12px; border: 1px solid #cbd5e1;"
            >128 万</div>
          </div>
        </div>
      </div>
    `

    const report = await convert(slide)
    const tableRows = slide.addTable.mock.calls[0]?.[0] as Array<Array<{ text: string, options: Record<string, unknown> }>>
    const tableOptions = slide.addTable.mock.calls[0]?.[1] as Record<string, unknown>
    const headerCellOptions = tableRows[0][1].options

    expect(slide.addTable).toHaveBeenCalledTimes(1)
    expect(slide.addText).not.toHaveBeenCalled()
    expect(tableRows[0][1].text).toBe('收入')
    expect(tableRows[1][1].text).toBe('128 万')
    expect(tableOptions).toEqual(expect.objectContaining({
      autoPage: false,
      fit: 'shrink',
    }))
    expect(tableOptions.rowH as number[]).toHaveLength(2)
    expect(tableOptions.colW as number[]).toHaveLength(2)
    expect((tableOptions.rowH as number[])[0]).toBeCloseTo((64 / 1080) * 7.5, 4)
    expect((tableOptions.rowH as number[])[1]).toBeCloseTo((96 / 1080) * 7.5, 4)
    expect((tableOptions.colW as number[])[0]).toBeCloseTo((140 / 1920) * 13.333, 4)
    expect((tableOptions.colW as number[])[1]).toBeCloseTo((260 / 1920) * 13.333, 4)
    expect(headerCellOptions).toEqual(expect.objectContaining({
      fontSize: 10,
      bold: true,
      color: '2563EB',
      align: 'right',
      valign: 'middle',
      fit: 'shrink',
      fill: expect.objectContaining({ color: 'DBEAFE' }),
      margin: [4, 6, 4, 6],
    }))
    expect(headerCellOptions.border).toEqual([
      expect.objectContaining({ type: 'dash', color: '0F172A', pt: 1 }),
      expect.objectContaining({ type: 'dash', color: '0F172A', pt: 1 }),
      expect.objectContaining({ type: 'dash', color: '0F172A', pt: 1 }),
      expect.objectContaining({ type: 'dash', color: '0F172A', pt: 1 }),
    ])
    expect(report.items).toEqual(expect.arrayContaining([
      expect.objectContaining({
        sourceType: 'table',
        result: 'editable-table',
        editable: true,
      }),
    ]))
  })

  it('应将 Runtime Kit 表格单元格四边边框导出到 PPT 表格', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div data-runtime-kit-table="v1" role="table" aria-rowcount="2" aria-colcount="2" style="width: 400px; height: 160px;">
          <div role="row" style="display: contents;">
            <div
              data-runtime-kit-table-cell="v1"
              data-row-index="0"
              data-column-index="0"
              role="cell"
              style="width: 200px; height: 80px; border-top: 3px solid #111111; border-right: none; border-bottom: 1px dashed #222222; border-left: none;"
            >四边控制</div>
            <div
              data-runtime-kit-table-cell="v1"
              data-row-index="0"
              data-column-index="1"
              role="cell"
              style="width: 200px; height: 80px; border: none;"
            >无边框</div>
          </div>
          <div role="row" style="display: contents;">
            <div data-runtime-kit-table-cell="v1" data-row-index="1" data-column-index="0" role="cell" style="width: 200px; height: 80px; border: none;">A</div>
            <div data-runtime-kit-table-cell="v1" data-row-index="1" data-column-index="1" role="cell" style="width: 200px; height: 80px; border: none;">B</div>
          </div>
        </div>
      </div>
    `

    await convert(slide)
    const tableRows = slide.addTable.mock.calls[0]?.[0] as Array<Array<{ text: string, options: Record<string, unknown> }>>
    const controlledBorder = tableRows[0][0].options.border
    const noBorderOptions = tableRows[0][1].options

    expect(controlledBorder).toEqual([
      expect.objectContaining({ type: 'solid', color: '111111', pt: 1.5 }),
      expect.objectContaining({ type: 'none', color: 'FFFFFF', pt: 0 }),
      expect.objectContaining({ type: 'dash', color: '222222', pt: 0.5 }),
      expect.objectContaining({ type: 'none', color: 'FFFFFF', pt: 0 }),
    ])
    expect(noBorderOptions.border).toEqual([
      expect.objectContaining({ type: 'none', color: 'FFFFFF', pt: 0 }),
      expect.objectContaining({ type: 'none', color: 'FFFFFF', pt: 0 }),
      expect.objectContaining({ type: 'none', color: 'FFFFFF', pt: 0 }),
      expect.objectContaining({ type: 'none', color: 'FFFFFF', pt: 0 }),
    ])
  })

  it('应将原生 HTML 表格导出为 PPT 原生可编辑表格', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px; background: #ffffff;">
        <table style="width: 400px; height: 160px; border-collapse: collapse; font-size: 16px; font-family: 'Web Presentation Sans', sans-serif;">
          <thead>
            <tr style="width: 400px; height: 64px; background: #f1f5f9;">
              <th style="width: 140px; height: 64px; padding: 8px 12px; color: #0f172a; border: 1px solid #cbd5e1;">指标</th>
              <th style="width: 260px; height: 64px; padding: 8px 12px; color: #2563eb; background: #dbeafe; border: 1px solid #cbd5e1; text-align: right;">收入</th>
            </tr>
          </thead>
          <tbody>
            <tr style="width: 400px; height: 96px;">
              <td style="width: 140px; height: 96px; padding: 8px 12px; border: 1px solid #cbd5e1;">Q2</td>
              <td style="width: 260px; height: 96px; padding: 8px 12px; border: 1px solid #cbd5e1;">128 万</td>
            </tr>
          </tbody>
        </table>
      </div>
    `

    const report = await convert(slide)
    const tableRows = slide.addTable.mock.calls[0]?.[0] as Array<Array<{ text: string, options: Record<string, unknown> }>>
    const tableOptions = slide.addTable.mock.calls[0]?.[1] as Record<string, unknown>

    expect(slide.addTable).toHaveBeenCalledTimes(1)
    expect(slide.addText).not.toHaveBeenCalled()
    expect(tableRows.map(row => row.map(cell => cell.text))).toEqual([
      ['指标', '收入'],
      ['Q2', '128 万'],
    ])
    expect(tableRows[0][1].options).toEqual(expect.objectContaining({
      fontFace: 'Microsoft YaHei',
      color: '2563EB',
      fill: expect.objectContaining({ color: 'DBEAFE' }),
      align: 'right',
      margin: [4, 6, 4, 6],
    }))
    expect(tableRows[0][0].options.fill).toEqual(expect.objectContaining({ color: 'F1F5F9' }))
    expect(tableOptions.rowH as number[]).toHaveLength(2)
    expect(tableOptions.colW as number[]).toHaveLength(2)
    expect((tableOptions.rowH as number[]).reduce((sum, value) => sum + value, 0)).toBeCloseTo(160 / 1080 * 7.5, 4)
    expect((tableOptions.colW as number[]).reduce((sum, value) => sum + value, 0)).toBeCloseTo(400 / 1920 * 13.333, 4)
    expect(report.items).toEqual(expect.arrayContaining([
      expect.objectContaining({
        sourceType: 'table',
        result: 'editable-table',
        reason: 'HTML 表格导出为 PPT 原生表格',
      }),
    ]))
  })

  it('应解析 HTML 表格的 rowspan 和 colspan', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <table style="width: 600px; height: 180px; border-collapse: collapse;">
          <tbody>
            <tr style="width: 600px; height: 90px;">
              <th rowspan="2" style="width: 180px; height: 180px; border: 1px solid #94a3b8;">区域</th>
              <th colspan="2" style="width: 420px; height: 90px; border: 1px solid #94a3b8;">季度收入</th>
            </tr>
            <tr style="width: 600px; height: 90px;">
              <td style="width: 200px; height: 90px; border: 1px solid #94a3b8;">Q1</td>
              <td style="width: 220px; height: 90px; border: 1px solid #94a3b8;">Q2</td>
            </tr>
          </tbody>
        </table>
      </div>
    `

    await convert(slide)
    const tableRows = slide.addTable.mock.calls[0]?.[0] as Array<Array<{ text: string, options: Record<string, unknown> }>>
    const tableOptions = slide.addTable.mock.calls[0]?.[1] as Record<string, unknown>

    expect(tableRows[0]).toHaveLength(2)
    expect(tableRows[0][0]).toEqual(expect.objectContaining({
      text: '区域',
      options: expect.objectContaining({ rowspan: 2 }),
    }))
    expect(tableRows[0][1]).toEqual(expect.objectContaining({
      text: '季度收入',
      options: expect.objectContaining({ colspan: 2 }),
    }))
    expect(tableRows[1].map(cell => cell.text)).toEqual(['Q1', 'Q2'])
    expect(tableOptions.colW as number[]).toHaveLength(3)
  })

  it('应按折叠边框优先级统一 HTML 相邻单元格边界', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <table style="width: 400px; height: 80px; border-collapse: collapse;">
          <tbody>
            <tr style="width: 400px; height: 80px;">
              <td style="width: 200px; height: 80px; border-right: 1px solid #ef4444;">A</td>
              <td style="width: 200px; height: 80px; border-left: 3px dashed #2563eb;">B</td>
            </tr>
          </tbody>
        </table>
      </div>
    `

    await convert(slide)
    const tableRows = slide.addTable.mock.calls[0]?.[0] as Array<Array<{ options: Record<string, unknown> }>>
    const firstBorders = tableRows[0][0].options.border as Array<Record<string, unknown>>
    const secondBorders = tableRows[0][1].options.border as Array<Record<string, unknown>>

    expect(firstBorders[1]).toEqual(expect.objectContaining({ type: 'dash', color: '2563EB', pt: 1.5 }))
    expect(secondBorders[3]).toEqual(firstBorders[1])
  })

  it('HTML 表格包含复杂单元格内容时应整表截图', async () => {
    const slide = createSlideMock()
    const captureElementAsPng = vi.fn(async () => 'data:image/png;base64,table')
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <table id="complex-table" style="width: 400px; height: 120px;">
          <tbody>
            <tr style="width: 400px; height: 120px;">
              <td style="width: 400px; height: 120px;"><img src="data:image/png;base64,test" alt="图标">图文内容</td>
            </tr>
          </tbody>
        </table>
      </div>
    `

    const report = await convert(slide, captureElementAsPng)

    expect(slide.addTable).not.toHaveBeenCalled()
    expect(slide.addText).not.toHaveBeenCalled()
    expect(captureElementAsPng).toHaveBeenCalledWith(document.getElementById('complex-table'))
    expect(report.items).toEqual(expect.arrayContaining([
      expect.objectContaining({
        sourceType: 'table',
        result: 'screenshot',
        reason: expect.stringContaining('复杂单元格内容'),
      }),
    ]))
  })

  it('HTML 表格存在未覆盖的行列空洞时应整表截图', async () => {
    const slide = createSlideMock()
    const captureElementAsPng = vi.fn(async () => 'data:image/png;base64,table')
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <table id="irregular-table" style="width: 400px; height: 160px;">
          <tbody>
            <tr style="width: 400px; height: 80px;">
              <td style="width: 200px; height: 80px;">A</td>
              <td style="width: 200px; height: 80px;">B</td>
            </tr>
            <tr style="width: 400px; height: 80px;">
              <td style="width: 200px; height: 80px;">C</td>
            </tr>
          </tbody>
        </table>
      </div>
    `

    const report = await convert(slide, captureElementAsPng)

    expect(slide.addTable).not.toHaveBeenCalled()
    expect(captureElementAsPng).toHaveBeenCalledWith(document.getElementById('irregular-table'))
    expect(report.items).toEqual(expect.arrayContaining([
      expect.objectContaining({
        sourceType: 'table',
        result: 'screenshot',
        reason: 'HTML 表格行列结构不规则，已降级为局部截图',
      }),
    ]))
  })

  it('应将多级 div/span 展开为按层级排列的多个组合对象', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px; background: #ffffff;">
        <div id="card" style="width: 700px; height: 360px; background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 16px;">
          <span id="badge" style="display: inline-block; width: 96px; height: 36px; background: #dbeafe; border-radius: 18px; color: #1d4ed8; font-size: 18px; font-weight: 700;">Q2</span>
          <div id="metric" style="width: 320px; height: 120px;">
            <span style="display: inline-block; width: 120px; height: 32px; font-size: 20px; color: #334155;">Revenue</span>
            <strong style="display: inline-block; width: 180px; height: 72px; font-size: 56px; color: #16a34a;">128%</strong>
          </div>
        </div>
      </div>
    `

    const report = await convert(slide)
    const events = slide.__events

    expect(events[0]).toEqual(expect.objectContaining({ kind: 'shape', shapeName: 'roundRect' }))
    expect(events.some(event => event.kind === 'text' && event.text === 'Q2')).toBe(true)
    expect(events.some(event => event.kind === 'text' && event.text === 'Revenue')).toBe(true)
    expect(events.some(event => event.kind === 'text' && event.text === '128%')).toBe(true)
    expect(events.some(event => event.kind === 'text' && event.text === 'Q2 Revenue 128%')).toBe(false)

    const cardShape = report.items.find(item => item.label.includes('div#card') && item.result === 'editable-shape')
    const badgeShape = report.items.find(item => item.label.includes('span#badge') && item.result === 'editable-shape')
    const numberText = report.items.find(item => item.label === '128%')

    expect(cardShape?.groupId).toBeTruthy()
    expect(badgeShape?.groupId).toBeTruthy()
    expect(badgeShape?.parentGroupId).toBe(cardShape?.groupId)
    expect(numberText).toEqual(expect.objectContaining({
      sourceType: 'number',
      groupId: expect.any(String),
      parentGroupId: cardShape?.groupId,
    }))
    expect(String((events[0].options as Record<string, unknown>).objectName)).toContain(cardShape?.groupId)
  })

  it('应导出 flex 列表项中 span 后的直属文本节点', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px; background: #ffffff;">
        <ul style="width: 720px; height: 120px;">
          <li class="flex items-start text-secondary" style="width: 720px; height: 32px; font-size: 20px; color: #475569;">
            <span class="text-primary mr-2" style="display: inline-block; width: 16px; height: 24px; color: #2563eb;">•</span>
            多用户登录、会话和平台用户管理
          </li>
        </ul>
      </div>
    `

    const listItem = document.querySelector('li') as HTMLElement
    const bullet = listItem.querySelector('span') as HTMLElement
    const bodyTextNode = Array.from(listItem.childNodes).find((node): node is Text => {
      return node.nodeType === Node.TEXT_NODE && /多用户登录/.test(node.textContent || '')
    }) as Text
    const createRect = (left: number, top: number, width: number, height: number) => ({
      x: left,
      y: top,
      left,
      top,
      right: left + width,
      bottom: top + height,
      width,
      height,
      toJSON: () => ({}),
    })

    vi.spyOn(listItem, 'getBoundingClientRect').mockReturnValue(createRect(100, 120, 720, 32))
    vi.spyOn(bullet, 'getBoundingClientRect').mockReturnValue(createRect(100, 120, 16, 24))
    vi.spyOn(document, 'createRange').mockImplementation(() => {
      let currentNode: Node | null = null
      const textRect = createRect(124, 120, 300, 24)
      return {
        selectNodeContents: (node: Node) => {
          currentNode = node
        },
        getClientRects: () => currentNode === bodyTextNode ? [textRect] : [],
        getBoundingClientRect: () => currentNode === bodyTextNode ? textRect : createRect(0, 0, 0, 0),
      } as unknown as Range
    })

    const report = await convert(slide)

    expect(slide.addText).toHaveBeenCalledWith('•', expect.objectContaining({
      color: '2563EB',
    }))
    expect(slide.addText).toHaveBeenCalledWith('多用户登录、会话和平台用户管理', expect.objectContaining({
      color: '475569',
    }))
    expect(slide.addText).not.toHaveBeenCalledWith('• 多用户登录、会话和平台用户管理', expect.any(Object))
    expect(report.items).toEqual(expect.arrayContaining([
      expect.objectContaining({
        label: '•',
        result: 'editable-text',
      }),
      expect.objectContaining({
        label: '多用户登录、会话和平台用户管理',
        sourceType: 'body',
        result: 'editable-text',
        reason: '直属文本节点转为 PPT text',
      }),
    ]))
  })

  it('应对直属文本节点中的长英文 token 追加更积极的宽度保护', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px; background: #ffffff;">
        <ul style="width: 720px; height: 120px;">
          <li class="flex items-start text-secondary" style="width: 720px; height: 32px; font-size: 20px; color: #475569;">
            <span class="text-accent1 mr-2" style="display: inline-block; width: 16px; height: 24px; color: #0f766e;">•</span>
            runtime-kit.manifest.json 是 Backend 校验的单一事实源
          </li>
        </ul>
      </div>
    `

    const listItem = document.querySelector('li') as HTMLElement
    const bullet = listItem.querySelector('span') as HTMLElement
    const bodyTextNode = Array.from(listItem.childNodes).find((node): node is Text => {
      return node.nodeType === Node.TEXT_NODE && /runtime-kit\.manifest\.json/.test(node.textContent || '')
    }) as Text
    const createRect = (left: number, top: number, width: number, height: number) => ({
      x: left,
      y: top,
      left,
      top,
      right: left + width,
      bottom: top + height,
      width,
      height,
      toJSON: () => ({}),
    })

    vi.spyOn(listItem, 'getBoundingClientRect').mockReturnValue(createRect(100, 120, 720, 32))
    vi.spyOn(bullet, 'getBoundingClientRect').mockReturnValue(createRect(100, 120, 16, 24))
    vi.spyOn(document, 'createRange').mockImplementation(() => {
      let currentNode: Node | null = null
      const textRect = createRect(124, 120, 240, 24)
      return {
        selectNodeContents: (node: Node) => {
          currentNode = node
        },
        getClientRects: () => currentNode === bodyTextNode ? [textRect] : [],
        getBoundingClientRect: () => currentNode === bodyTextNode ? textRect : createRect(0, 0, 0, 0),
      } as unknown as Range
    })

    await convert(slide)
    const bodyTextCall = slide.addText.mock.calls.find(([text]) => text === 'runtime-kit.manifest.json 是 Backend 校验的单一事实源')?.[1] as Record<string, unknown>
    const originalTextWidth = (240 / 1920) * 13.333

    expect(bodyTextCall).toEqual(expect.objectContaining({
      color: '475569',
    }))
    expect(bodyTextCall?.w as number).toBeGreaterThan(originalTextWidth + 0.15)
  })

  it('应对斜杠分隔的中英混排直属文本追加通用宽度保护', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px; background: #ffffff;">
        <ul style="width: 720px; height: 120px;">
          <li class="flex items-start text-secondary" style="width: 720px; height: 32px; font-size: 20px; color: #475569;">
            <span class="text-accent2 mr-2" style="display: inline-block; width: 16px; height: 24px; color: #7c3aed;">•</span>
            通过 Docker / Docker Compose / GitHub Actions 负责服务编排
          </li>
        </ul>
      </div>
    `

    const listItem = document.querySelector('li') as HTMLElement
    const bullet = listItem.querySelector('span') as HTMLElement
    const bodyTextNode = Array.from(listItem.childNodes).find((node): node is Text => {
      return node.nodeType === Node.TEXT_NODE && /Docker Compose/.test(node.textContent || '')
    }) as Text
    const createRect = (left: number, top: number, width: number, height: number) => ({
      x: left,
      y: top,
      left,
      top,
      right: left + width,
      bottom: top + height,
      width,
      height,
      toJSON: () => ({}),
    })

    vi.spyOn(listItem, 'getBoundingClientRect').mockReturnValue(createRect(100, 120, 720, 32))
    vi.spyOn(bullet, 'getBoundingClientRect').mockReturnValue(createRect(100, 120, 16, 24))
    vi.spyOn(document, 'createRange').mockImplementation(() => {
      let currentNode: Node | null = null
      const textRect = createRect(124, 120, 240, 24)
      return {
        selectNodeContents: (node: Node) => {
          currentNode = node
        },
        getClientRects: () => currentNode === bodyTextNode ? [textRect] : [],
        getBoundingClientRect: () => currentNode === bodyTextNode ? textRect : createRect(0, 0, 0, 0),
      } as unknown as Range
    })

    await convert(slide)
    const bodyTextCall = slide.addText.mock.calls.find(([text]) => text === '通过 Docker / Docker Compose / GitHub Actions 负责服务编排')?.[1] as Record<string, unknown>
    const originalTextWidth = (240 / 1920) * 13.333

    expect(bodyTextCall).toEqual(expect.objectContaining({
      color: '475569',
    }))
    expect(bodyTextCall?.w as number).toBeGreaterThan(originalTextWidth + 0.14)
  })

  it('应对块级长英文 token 文本追加通用宽度保护', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <p style="position: absolute; left: 120px; top: 80px; width: 240px; height: 24px; font-size: 20px; color: #475569;">
          runtime-kit.manifest.json 是 Backend 校验的单一事实源
        </p>
      </div>
    `

    await convert(slide)
    const textCall = slide.addText.mock.calls.find(([text]) => text === 'runtime-kit.manifest.json 是 Backend 校验的单一事实源')?.[1] as Record<string, unknown>
    const originalTextWidth = (240 / 1920) * 13.333

    expect(textCall).toEqual(expect.objectContaining({
      color: '475569',
    }))
    expect(textCall?.w as number).toBeGreaterThan(originalTextWidth + 0.15)
  })

  it('应让 flex 图标卡片中的正文段落占用祖先剩余宽度', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px; background: #ffffff;">
        <div class="flex items-start" style="width: 560px; height: 80px;">
          <div class="w-8 h-8 bg-secondary/10 rounded-lg flex items-center justify-center mr-4 mt-1" style="width: 32px; height: 32px; margin-right: 16px; margin-top: 4px;">
            <span class="text-secondary font-bold" style="display: inline-block; width: 12px; height: 20px; color: #475569; font-weight: 700;">2</span>
          </div>
          <div>
            <p class="text-lg text-secondary" style="font-size: 20px; color: #475569;">
              确认子仓库 Docker Release 已推送 web-runtime-vue:sha-12位提交
            </p>
          </div>
        </div>
      </div>
    `

    const row = document.querySelector('.flex.items-start') as HTMLElement
    const iconBox = row.children[0] as HTMLElement
    const textWrapper = row.children[1] as HTMLElement
    const paragraph = textWrapper.querySelector('p') as HTMLElement
    const createRect = (left: number, top: number, width: number, height: number) => ({
      x: left,
      y: top,
      left,
      top,
      right: left + width,
      bottom: top + height,
      width,
      height,
      toJSON: () => ({}),
    })

    vi.spyOn(row, 'getBoundingClientRect').mockReturnValue(createRect(100, 120, 560, 80))
    vi.spyOn(iconBox, 'getBoundingClientRect').mockReturnValue(createRect(100, 124, 32, 32))
    vi.spyOn(textWrapper, 'getBoundingClientRect').mockReturnValue(createRect(148, 120, 240, 48))
    vi.spyOn(paragraph, 'getBoundingClientRect').mockReturnValue(createRect(148, 120, 240, 24))

    await convert(slide)
    const textCall = slide.addText.mock.calls.find(([text]) => text === '确认子仓库 Docker Release 已推送 web-runtime-vue:sha-12位提交')?.[1] as Record<string, unknown>
    const paragraphOriginalWidth = (240 / 1920) * 13.333
    const rowRemainingWidth = ((100 + 560 - 148) / 1920) * 13.333

    expect(textCall).toEqual(expect.objectContaining({
      color: '475569',
    }))
    expect(textCall?.w as number).toBeGreaterThan(paragraphOriginalWidth + 0.6)
    expect(textCall?.w as number).toBeGreaterThan(rowRemainingWidth - 0.05)
  })

  it('不应将显式宽度约束的段落错误扩展到祖先剩余宽度', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px; background: #ffffff;">
        <div class="flex items-start" style="width: 560px; height: 80px;">
          <div class="w-8 h-8 bg-secondary/10 rounded-lg flex items-center justify-center mr-4 mt-1" style="width: 32px; height: 32px; margin-right: 16px; margin-top: 4px;">
            <span class="text-secondary font-bold" style="display: inline-block; width: 12px; height: 20px; color: #475569; font-weight: 700;">2</span>
          </div>
          <div style="width: 240px; height: 48px;">
            <p class="text-lg text-secondary" style="width: 240px; height: 24px; font-size: 20px; color: #475569;">
              确认子仓库 Docker Release 已推送 web-runtime-vue:sha-12位提交
            </p>
          </div>
        </div>
      </div>
    `

    const row = document.querySelector('.flex.items-start') as HTMLElement
    const iconBox = row.children[0] as HTMLElement
    const textWrapper = row.children[1] as HTMLElement
    const paragraph = textWrapper.querySelector('p') as HTMLElement
    const createRect = (left: number, top: number, width: number, height: number) => ({
      x: left,
      y: top,
      left,
      top,
      right: left + width,
      bottom: top + height,
      width,
      height,
      toJSON: () => ({}),
    })

    vi.spyOn(row, 'getBoundingClientRect').mockReturnValue(createRect(100, 120, 560, 80))
    vi.spyOn(iconBox, 'getBoundingClientRect').mockReturnValue(createRect(100, 124, 32, 32))
    vi.spyOn(textWrapper, 'getBoundingClientRect').mockReturnValue(createRect(148, 120, 240, 48))
    vi.spyOn(paragraph, 'getBoundingClientRect').mockReturnValue(createRect(148, 120, 240, 24))

    await convert(slide)
    const textCall = slide.addText.mock.calls.find(([text]) => text === '确认子仓库 Docker Release 已推送 web-runtime-vue:sha-12位提交')?.[1] as Record<string, unknown>
    const rowRemainingWidth = ((100 + 560 - 148) / 1920) * 13.333

    expect(textCall).toEqual(expect.objectContaining({
      color: '475569',
    }))
    expect(textCall?.w as number).toBeLessThan(rowRemainingWidth - 0.2)
  })

  it('应按设计画布计算字体大小，避免缩放预览导致字号放大', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <h1 style="width: 600px; height: 64px; font-size: 40px;">缩放页标题</h1>
      </div>
    `
    const pageElement = document.getElementById('page') as HTMLElement
    vi.spyOn(pageElement, 'getBoundingClientRect').mockReturnValue({
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      right: 960,
      bottom: 540,
      width: 960,
      height: 540,
      toJSON: () => ({}),
    })

    await convert(slide)

    expect(slide.addText).toHaveBeenCalledWith('缩放页标题', expect.objectContaining({
      fontSize: 20,
    }))
  })

  it('应将所有 PPT 文本框设置为不自动调整', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <p style="width: 360px; height: 32px; font-size: 16px;">普通文本</p>
        <span class="rounded-full px-3 py-1" style="display: inline-block; width: 96px; height: 24px; background: #bfdbfe; border-radius: 9999px; font-size: 12px;">徽标文本</span>
      </div>
    `

    await convert(slide)

    expect(slide.addText).toHaveBeenCalledWith('普通文本', expect.objectContaining({
      fit: 'none',
    }))
    expect(slide.addText).toHaveBeenCalledWith('徽标文本', expect.objectContaining({
      fit: 'none',
      shape: 'roundRect',
    }))
  })

  it('应给文本框增加宽度冗余以避免末字换行', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <p style="position: absolute; left: 120px; top: 40px; width: 360px; height: 32px; font-size: 16px;">左对齐文本</p>
        <p style="position: absolute; left: 120px; top: 90px; width: 360px; height: 32px; font-size: 16px; text-align: center;">居中文本</p>
        <p style="position: absolute; left: 120px; top: 140px; width: 360px; height: 32px; font-size: 16px; text-align: right;">右对齐文本</p>
        <span class="rounded-full px-3 py-1" style="position: absolute; left: 120px; top: 190px; display: inline-block; width: 96px; height: 24px; background: #bfdbfe; border-radius: 9999px; font-size: 12px;">徽标</span>
      </div>
    `

    await convert(slide)
    const inchPerPx = 13.333 / 1920
    const originalX = 120 * inchPerPx
    const originalWidth = 360 * inchPerPx
    const originalBadgeWidth = 96 * inchPerPx
    const leftCall = slide.addText.mock.calls.find(([text]) => text === '左对齐文本')?.[1]
    const centerCall = slide.addText.mock.calls.find(([text]) => text === '居中文本')?.[1]
    const rightCall = slide.addText.mock.calls.find(([text]) => text === '右对齐文本')?.[1]
    const badgeCall = slide.addText.mock.calls.find(([text]) => text === '徽标')?.[1]

    expect(leftCall?.w as number).toBeGreaterThan(originalWidth)
    expect(leftCall?.x as number).toBeCloseTo(originalX, 3)
    expect(centerCall?.w as number).toBeGreaterThan(originalWidth)
    expect((centerCall?.x as number) + (centerCall?.w as number) / 2).toBeCloseTo(originalX + originalWidth / 2, 3)
    expect(rightCall?.w as number).toBeGreaterThan(originalWidth)
    expect((rightCall?.x as number) + (rightCall?.w as number)).toBeCloseTo(originalX + originalWidth, 3)
    expect(badgeCall).toEqual(expect.objectContaining({
      shape: 'roundRect',
      align: 'center',
    }))
    expect(badgeCall?.w as number).toBeGreaterThan(originalBadgeWidth)
    expect((badgeCall?.x as number) + (badgeCall?.w as number) / 2).toBeCloseTo(originalX + originalBadgeWidth / 2, 3)
  })

  it('flex 行中的块级 rounded-full 胶囊应使用增强宽度保护', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div class="flex items-center justify-between" style="display: flex; align-items: center; justify-content: space-between; width: 520px; height: 64px;">
          <div class="text-xl font-semibold text-secondary" style="font-size: 20px; line-height: 28px;">形式一 · 已知首项与末项</div>
          <div id="badge" class="rounded-full bg-accent1 px-4 py-2 text-lg text-invert" style="background: #2563eb; border-radius: 9999px; padding: 8px 16px; font-size: 18px; line-height: 28px; color: #ffffff;">首末相加</div>
        </div>
      </div>
    `

    const badge = document.getElementById('badge') as HTMLElement
    const createRect = (left: number, top: number, width: number, height: number) => ({
      x: left,
      y: top,
      left,
      top,
      right: left + width,
      bottom: top + height,
      width,
      height,
      toJSON: () => ({}),
    })
    vi.spyOn(badge, 'getBoundingClientRect').mockReturnValue(createRect(0, 0, 128, 44))

    await convert(slide)

    const badgeOptions = slide.addText.mock.calls.find(([text]) => text === '首末相加')?.[1] as Record<string, unknown>
    const originalWidth = (128 / 1920) * 13.333

    expect(badgeOptions).toEqual(expect.objectContaining({ shape: 'roundRect' }))
    expect(Number(badgeOptions.w)).toBeGreaterThan(originalWidth + 0.09)
  })

  it('flex 行中的内容宽度 rounded-rect 文本形状应使用增强宽度保护', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div id="row" class="flex items-center gap-4" style="display: flex; align-items: center; column-gap: 16px; width: 640px; height: 100px;">
          <div class="flex h-14 w-14 items-center justify-center rounded-2xl bg-accent2 text-2xl font-bold text-invert" style="display: flex; align-items: center; justify-content: center; width: 56px; height: 56px; background: #16a34a; border-radius: 16px; font-size: 24px; line-height: 32px; font-weight: 700; color: #ffffff;">3</div>
          <div id="card" class="rounded-2xl border border-border bg-background-subtle px-6 py-5 text-[25px] font-semibold" style="background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 16px; padding: 20px 24px; font-size: 25px; line-height: 30px; font-weight: 600;">对应相加，提炼一般式</div>
        </div>
      </div>
    `

    const card = document.getElementById('card') as HTMLElement
    const createRect = (left: number, top: number, width: number, height: number) => ({
      x: left,
      y: top,
      left,
      top,
      right: left + width,
      bottom: top + height,
      width,
      height,
      toJSON: () => ({}),
    })
    vi.spyOn(card, 'getBoundingClientRect').mockReturnValue(createRect(72, 10, 300, 80))

    await convert(slide)

    const cardOptions = slide.addText.mock.calls.find(([text]) => text === '对应相加，提炼一般式')?.[1] as Record<string, unknown>
    const originalWidth = (300 / 1920) * 13.333

    expect(cardOptions).toEqual(expect.objectContaining({ shape: 'roundRect' }))
    expect(Number(cardOptions.w)).toBeGreaterThan(originalWidth + 0.1)
  })

  it('应按实际圆角半径导出 roundRect，避免普通圆角全部变成 full', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <section style="width: 800px; height: 320px; background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 12px;"></section>
        <span style="display: inline-block; width: 96px; height: 24px; padding: 4px 12px; background: #bfdbfe; border-radius: 9999px; font-size: 12px;">徽标</span>
      </div>
    `

    await convert(slide)

    const cardShapeOptions = slide.addShape.mock.calls.find(([shapeName]) => shapeName === 'roundRect')?.[1] as Record<string, unknown>
    const badgeTextOptions = slide.addText.mock.calls.find(([text]) => text === '徽标')?.[1] as Record<string, unknown>
    const expectedRadiusIn = 12 * (13.333 / 1920)

    expect(Number(cardShapeOptions.rectRadius)).toBeCloseTo(expectedRadiusIn, 4)
    expect(Number(badgeTextOptions.rectRadius)).toBeCloseTo(expectedRadiusIn, 4)
  })

  it('应将 rounded-full 正圆导出为原生 ellipse', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div
          class="rounded-full"
          style="width: 96px; height: 96px; background: #2563eb; border-radius: 9999px;"
        ></div>
        <span
          class="rounded-full px-3 py-1"
          style="display: inline-block; width: 96px; height: 24px; padding: 4px 12px; background: #bfdbfe; border-radius: 9999px; font-size: 12px;"
        >徽标</span>
      </div>
    `

    await convert(slide)

    expect(slide.addShape).toHaveBeenCalledWith('ellipse', expect.objectContaining({
      fill: expect.objectContaining({ color: '2563EB' }),
    }))
    expect(slide.addText).toHaveBeenCalledWith('徽标', expect.objectContaining({
      shape: 'roundRect',
    }))
  })

  it('含文本的 rounded-full 正圆不应被宽度保护拉伸为椭圆', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <span
          class="rounded-full p-2"
          style="position: absolute; left: 120px; top: 80px; display: inline-block; width: 40px; height: 40px; padding: 8px; background: #2563eb; border-radius: 9999px; color: #ffffff; font-size: 16px;"
        >1</span>
      </div>
    `

    await convert(slide)
    const circleOptions = slide.addText.mock.calls.find(([text]) => text === '1')?.[1] as Record<string, unknown>
    const expectedCenterX = ((120 + 20) / 1920) * 13.333
    const expectedCenterY = ((80 + 20) / 1080) * 7.5

    expect(circleOptions.shape).toBe('ellipse')
    expect(Number(circleOptions.w)).toBeCloseTo(Number(circleOptions.h), 4)
    expect(Number(circleOptions.x) + Number(circleOptions.w) / 2).toBeCloseTo(expectedCenterX, 3)
    expect(Number(circleOptions.y) + Number(circleOptions.h) / 2).toBeCloseTo(expectedCenterY, 3)
  })

  it('明确固定尺寸的普通圆角正方形不应被宽度保护拉伸', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <span
          class="w-10 h-10 rounded-lg"
          style="position: absolute; left: 180px; top: 120px; display: inline-block; width: 40px; height: 40px; background: #f1f5f9; border: 1px solid #94a3b8; border-radius: 8px; color: #0f172a; font-size: 16px;"
        >A</span>
      </div>
    `

    await convert(slide)
    const squareOptions = slide.addText.mock.calls.find(([text]) => text === 'A')?.[1] as Record<string, unknown>
    const expectedRadiusIn = 8 * (13.333 / 1920)

    expect(squareOptions.shape).toBe('roundRect')
    expect(Number(squareOptions.rectRadius)).toBeCloseTo(expectedRadiusIn, 4)
    expect(Number(squareOptions.w)).toBeCloseTo(Number(squareOptions.h), 4)
  })

  it('应将纯 translate 定位的环形节点保持为可编辑对象', async () => {
    const slide = createSlideMock()
    const captureElementAsPng = vi.fn(async () => 'data:image/png;base64,capture')
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div style="position: relative; width: 420px; height: 420px;">
          <div
            class="absolute flex flex-col items-center gap-1"
            style="position: absolute; left: 50%; top: 8%; transform: translate(-50%, -50%); width: 180px; height: 86px; display: flex; flex-direction: column; align-items: center;"
          >
            <div
              class="rounded-full"
              style="width: 56px; height: 56px; background: rgba(124, 58, 237, 0.1); border: 2px solid rgba(124, 58, 237, 0.3); border-radius: 9999px; display: flex; align-items: center; justify-content: center;"
            >
              <span style="display: inline-block; width: 36px; height: 22px; color: #7c3aed; font-size: 16px; font-weight: 700;">创作</span>
            </div>
            <span style="display: block; width: 120px; height: 22px; color: #64748b; font-size: 14px;">AI 生成和改写</span>
          </div>
        </div>
      </div>
    `

    await convert(slide, captureElementAsPng)

    expect(captureElementAsPng).not.toHaveBeenCalled()
    expect(slide.addImage).not.toHaveBeenCalled()
    expect(slide.addShape).toHaveBeenCalledWith('ellipse', expect.objectContaining({
      fill: expect.objectContaining({ color: '7C3AED' }),
    }))
    expect(slide.addText).toHaveBeenCalledWith('创作', expect.objectContaining({
      color: '7C3AED',
    }))
    expect(slide.addText).toHaveBeenCalledWith('AI 生成和改写', expect.objectContaining({
      color: '64748B',
    }))
  })

  it('应对内容宽度驱动的反色 inline 文本追加更积极的宽度保护', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div id="card" class="bg-background-invert-100 border border-border p-4 rounded" style="width: 420px; height: 56px; padding: 16px; background: #1e293b; border: 1px solid #334155; border-radius: 4px;">
          <span id="label" class="text-invert-100" style="color: #f8fafc;">反色背景 100 (bg-background-invert-100)</span>
        </div>
      </div>
    `

    const pageElement = document.getElementById('page') as HTMLElement
    const cardElement = document.getElementById('card') as HTMLElement
    const labelElement = document.getElementById('label') as HTMLElement
    vi.spyOn(pageElement, 'getBoundingClientRect').mockReturnValue({
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      right: 1920,
      bottom: 1080,
      width: 1920,
      height: 1080,
      toJSON: () => ({}),
    })
    vi.spyOn(cardElement, 'getBoundingClientRect').mockReturnValue({
      x: 100,
      y: 80,
      top: 80,
      left: 100,
      right: 520,
      bottom: 136,
      width: 420,
      height: 56,
      toJSON: () => ({}),
    })
    vi.spyOn(labelElement, 'getBoundingClientRect').mockReturnValue({
      x: 116,
      y: 96,
      top: 96,
      left: 116,
      right: 356,
      bottom: 120,
      width: 240,
      height: 24,
      toJSON: () => ({}),
    })

    await convert(slide)

    const labelOptions = slide.addText.mock.calls.find(([text]) => text === '反色背景 100 (bg-background-invert-100)')?.[1] as Record<string, unknown>
    const inchPerPx = 13.333 / 1920
    const originalX = 116 * inchPerPx
    const originalWidth = 240 * inchPerPx

    expect(labelOptions?.w as number).toBeGreaterThan(originalWidth + 0.17)
    expect(labelOptions?.x as number).toBeCloseTo(originalX, 3)
  })

  it('应将 CSS 系统字体别名映射为 PPT 可识别字体', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <p style="width: 360px; height: 32px; font-size: 16px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;">主题能力</p>
        <p style="width: 360px; height: 32px; font-size: 16px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;">Runtime badge</p>
        <p style="width: 360px; height: 32px; font-size: 16px; font-family: '思源黑体', -apple-system, sans-serif;">主题字体</p>
        <p style="width: 360px; height: 32px; font-size: 16px; font-family: 'Web Presentation Sans', sans-serif;">平台默认字体</p>
        <code style="display: block; width: 360px; height: 32px; font-size: 16px; font-family: 'Web Presentation Mono', monospace;">const runtime = true</code>
      </div>
    `

    await convert(slide)

    expect(slide.addText).toHaveBeenCalledWith('主题能力', expect.objectContaining({
      fontFace: 'Microsoft YaHei',
    }))
    expect(slide.addText).toHaveBeenCalledWith('Runtime badge', expect.objectContaining({
      fontFace: 'Segoe UI',
    }))
    expect(slide.addText).toHaveBeenCalledWith('主题字体', expect.objectContaining({
      fontFace: '思源黑体',
    }))
    expect(slide.addText).toHaveBeenCalledWith('平台默认字体', expect.objectContaining({
      fontFace: 'Microsoft YaHei',
    }))
    expect(slide.addText).toHaveBeenCalledWith('const runtime = true', expect.objectContaining({
      fontFace: 'Consolas',
    }))
  })

  it('应还原 flex 布局中的左右居中和上下居中', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div style="display: flex; justify-content: center; align-items: center; width: 480px; height: 160px; font-size: 32px;">居中文本</div>
      </div>
    `

    await convert(slide)

    expect(slide.addText).toHaveBeenCalledWith('居中文本', expect.objectContaining({
      align: 'center',
      valign: 'middle',
    }))
  })

  it('应识别 Tailwind text-center 类名并让子文本继承居中', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div class="text-center" style="width: 560px; height: 180px;">
          <strong style="display: block; width: 320px; height: 72px; color: #2563eb; font-size: 36px;">类名居中</strong>
        </div>
      </div>
    `

    await convert(slide)

    expect(slide.addText).toHaveBeenCalledWith('类名居中', expect.objectContaining({
      align: 'center',
    }))
  })

  it('应识别 Tailwind items-center 和 justify-between 类名', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div class="flex items-center justify-between" style="width: 560px; height: 180px;">
          <span style="display: block; width: 160px; height: 48px; color: #0f172a; font-size: 24px;">左侧</span>
          <strong style="display: block; width: 160px; height: 48px; color: #2563eb; font-size: 24px;">右侧</strong>
        </div>
      </div>
    `

    await convert(slide)

    expect(slide.addText).toHaveBeenCalledWith('左侧', expect.objectContaining({
      align: 'left',
      valign: 'middle',
    }))
    expect(slide.addText).toHaveBeenCalledWith('右侧', expect.objectContaining({
      align: 'left',
      valign: 'middle',
    }))
  })

  it('应在 flex justify-between 测量缺失时按右侧位置导出代码标签', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div class="flex items-center justify-between bg-background-invert p-3 rounded border" style="width: 500px; height: 60px; background: #0f172a; border: 1px solid #334155; border-radius: 4px;">
          <span class="text-invert" style="display: block; width: 120px; height: 24px;">Invert 默认</span>
          <code class="text-invert text-xs px-2 py-1 rounded" style="display: block; width: 80px; height: 20px;">text-invert</code>
        </div>
      </div>
    `

    await convert(slide)
    const spanOptions = slide.addText.mock.calls.find(([text]) => text === 'Invert 默认')?.[1] as Record<string, unknown>
    const codeOptions = slide.addText.mock.calls.find(([text]) => text === 'text-invert')?.[1] as Record<string, unknown>
    const expectedCodeX = (408 / 1920) * 13.333
    const expectedCodeW = (80 / 1920) * 13.333

    expect(codeOptions).toEqual(expect.objectContaining({
      shape: 'rect',
      align: 'center',
      valign: 'middle',
      margin: [3, 3, 1.5, 1.5],
    }))
    expect(codeOptions.isTextBox).toBeUndefined()
    expect(slide.addText).not.toHaveBeenCalledWith('Invert 默认 text-invert', expect.any(Object))
    expect(Number(codeOptions.x)).toBeCloseTo(expectedCodeX, 4)
    expect(Number(codeOptions.w)).toBeCloseTo(expectedCodeW, 4)
    expect(Number(codeOptions.x)).toBeGreaterThan(Number(spanOptions.x))
  })

  it('不应把 flex 容器里的 absolute 顶部装饰条重算到页面中间', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div
          class="relative h-full w-full bg-background flex flex-col items-center justify-center"
          style="position: relative; display: flex; flex-direction: column; align-items: center; justify-content: center; width: 1920px; height: 1080px; background: #ffffff;"
        >
          <div
            class="absolute top-0 left-0 right-0 h-2 bg-background-invert"
            style="position: absolute; top: 0; left: 0; width: 1920px; height: 8px; background: #111827;"
          ></div>
          <div style="width: 360px; height: 96px;">
            <h1 style="width: 360px; height: 56px; font-size: 32px; color: #0f172a;">Attention Is All You Need</h1>
          </div>
          <div
            class="absolute bottom-0 left-0 right-0 h-2 bg-background-invert"
            style="position: absolute; left: 0; bottom: 0; width: 1920px; height: 8px; background: #111827;"
          ></div>
        </div>
      </div>
    `

    await convert(slide)
    const stripCalls = slide.addShape.mock.calls.filter(([, options]) => {
      const fill = (options as { fill?: { color?: unknown } }).fill
      return fill?.color === '111827'
    })
    const topStripOptions = stripCalls[0]?.[1] as Record<string, unknown>

    expect(stripCalls.length).toBeGreaterThanOrEqual(2)
    expect(Number(topStripOptions.y)).toBeCloseTo(0, 4)
    expect(Number(topStripOptions.h)).toBeCloseTo((8 / 1080) * 7.5, 4)
  })

  it('absolute 子元素不应参与 flex 子项分布兜底计算', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div class="flex items-center justify-between" style="display: flex; align-items: center; justify-content: space-between; position: relative; width: 500px; height: 60px;">
          <div style="position: absolute; left: 0; top: 0; width: 500px; height: 8px; background: #111827;"></div>
          <span style="display: block; width: 120px; height: 24px; color: #0f172a; font-size: 16px;">左侧</span>
          <code style="display: block; width: 80px; height: 20px; color: #2563eb; font-size: 12px;">右侧</code>
        </div>
      </div>
    `

    await convert(slide)
    const leftOptions = slide.addText.mock.calls.find(([text]) => text === '左侧')?.[1] as Record<string, unknown>
    const rightOptions = slide.addText.mock.calls.find(([text]) => text === '右侧')?.[1] as Record<string, unknown>
    const expectedRightX = (420 / 1920) * 13.333

    expect(Number(leftOptions.x)).toBeCloseTo(0, 4)
    expect(Number(rightOptions.x)).toBeCloseTo(expectedRightX, 4)
    expect(Number(rightOptions.x)).toBeGreaterThan(Number(leftOptions.x))
  })

  it('应将圆角徽标导出为带文本和内边距的 PPT 形状', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div class="flex items-center justify-between" style="width: 560px; height: 180px;">
          <span class="rounded-full px-3 py-1" style="display: inline-block; width: 96px; height: 24px; background: #bfdbfe; border-radius: 9999px; color: #1e40af; font-size: 12px;">主题能力</span>
          <a style="display: inline-block; width: 96px; height: 24px; color: #2563eb; font-size: 14px;">查看展示</a>
        </div>
      </div>
    `

    const report = await convert(slide)
    const badgeCall = slide.addText.mock.calls.find(([text]) => text === '主题能力')?.[1]

    expect(badgeCall).toEqual(expect.objectContaining({
      shape: 'roundRect',
      fill: expect.objectContaining({ color: 'BFDBFE' }),
      margin: [4.5, 4.5, 1.5, 1.5],
      align: 'center',
      valign: 'middle',
    }))
    expect(slide.addShape).not.toHaveBeenCalledWith('roundRect', expect.objectContaining({
      fill: expect.objectContaining({ color: 'BFDBFE' }),
    }))
    expect(report.items).toEqual(expect.arrayContaining([
      expect.objectContaining({
        label: '主题能力',
        result: 'editable-text',
        reason: '带背景文本转为 PPT text shape',
      }),
      expect.objectContaining({
        label: expect.stringContaining('span.rounded-full.px-3.py-1'),
        result: 'editable-shape',
        reason: '背景、边框和圆角由 PPT 文本形状绘制',
      }),
    ]))
  })

  it('应保持卡片描述段落居左且不受资源徽标居中影响', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <article class="overflow-hidden rounded-lg border border-border bg-background-subtle" style="width: 720px; height: 260px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;">
          <div class="p-5 bg-accent5-100" style="width: 720px; height: 160px; padding: 20px; background: #fef3c7;">
            <div class="mb-3 flex items-center" style="display: flex; align-items: center; width: 680px; height: 32px;">
              <span class="app-icon inline-flex items-center justify-center mr-2 size-5" style="display: inline-flex; width: 20px; height: 20px;"></span>
              <h3 class="font-heading text-lg font-semibold text-accent5-800" style="width: 240px; height: 28px; font-size: 18px; font-weight: 600;">LaTeX 公式</h3>
            </div>
            <p class="font-body text-sm leading-relaxed text-accent5-700" style="width: 680px; height: 40px; font-size: 14px; color: #854d0e;">展示公式文本资源的块级和行内排版能力。</p>
          </div>
          <div class="p-4" style="width: 720px; height: 80px; padding: 16px;">
            <div class="flex items-center justify-between gap-3" style="display: flex; align-items: center; justify-content: space-between; width: 688px; height: 28px;">
              <span class="rounded-full px-3 py-1 text-xs font-medium bg-accent5-200 text-accent5-800" style="display: inline-block; width: 96px; height: 24px; padding: 4px 12px; background: #fde68a; border-radius: 9999px; font-size: 12px;">资源渲染</span>
              <a class="whitespace-nowrap text-sm font-medium text-link" style="display: inline-block; width: 96px; height: 24px; font-size: 14px;">查看展示</a>
            </div>
          </div>
        </article>
      </div>
    `

    await convert(slide)
    const descriptionCall = slide.addText.mock.calls.find(([text]) => text === '展示公式文本资源的块级和行内排版能力。')?.[1]
    const badgeCall = slide.addText.mock.calls.find(([text]) => text === '资源渲染')?.[1]
    const originalBadgeWidth = (96 / 1920) * 13.333

    expect(descriptionCall).toEqual(expect.objectContaining({
      align: 'left',
    }))
    expect(badgeCall).toEqual(expect.objectContaining({
      shape: 'roundRect',
      align: 'center',
      valign: 'middle',
    }))
    expect(badgeCall?.w as number).toBeGreaterThan(originalBadgeWidth)
  })

  it('应将 line-height 等于高度的单行文本识别为上下居中', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <p style="width: 360px; height: 64px; line-height: 64px; text-align: center; font-size: 24px;">单行居中</p>
      </div>
    `

    await convert(slide)

    expect(slide.addText).toHaveBeenCalledWith('单行居中', expect.objectContaining({
      align: 'center',
      valign: 'middle',
    }))
  })

  it('应还原 table-cell 的居左居下和垂直居中', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div style="display: table-cell; width: 420px; height: 180px; vertical-align: bottom; text-align: left; font-size: 24px;">左下文本</div>
        <div style="display: table-cell; width: 420px; height: 180px; vertical-align: middle; text-align: right; font-size: 24px;">右中文本</div>
      </div>
    `

    await convert(slide)

    expect(slide.addText).toHaveBeenCalledWith('左下文本', expect.objectContaining({
      align: 'left',
      valign: 'bottom',
    }))
    expect(slide.addText).toHaveBeenCalledWith('右中文本', expect.objectContaining({
      align: 'right',
      valign: 'middle',
    }))
  })

  it('应还原 column flex 的右下对齐', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div style="display: flex; flex-direction: column; justify-content: flex-end; align-items: flex-end; width: 480px; height: 160px; font-size: 28px;">右下文本</div>
      </div>
    `

    await convert(slide)

    expect(slide.addText).toHaveBeenCalledWith('右下文本', expect.objectContaining({
      align: 'right',
      valign: 'bottom',
    }))
  })

  it('应让拆分出的子文本继承父级垂直布局对齐，水平仍按文本自身对齐', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div style="display: flex; justify-content: center; align-items: flex-end; width: 560px; height: 180px;">
          <strong style="display: block; width: 320px; height: 72px; color: #2563eb; font-size: 36px;">继承居中</strong>
        </div>
      </div>
    `

    await convert(slide)

    expect(slide.addText).toHaveBeenCalledWith('继承居中', expect.objectContaining({
      align: 'left',
      valign: 'bottom',
    }))
  })

  it('应让子文本显式对齐覆盖父级继承对齐', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div style="display: flex; justify-content: center; align-items: center; width: 560px; height: 180px;">
          <span style="display: block; width: 320px; height: 72px; text-align: right; vertical-align: bottom; font-size: 28px;">覆盖对齐</span>
        </div>
      </div>
    `

    await convert(slide)

    expect(slide.addText).toHaveBeenCalledWith('覆盖对齐', expect.objectContaining({
      align: 'right',
      valign: 'bottom',
    }))
  })

  it('应将 Mermaid SVG 转为 SVG 图片块', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div class="mermaid-viewer" style="width: 640px; height: 360px;">
          <svg viewBox="0 0 100 50"><rect width="100" height="50" fill="#fff" /></svg>
        </div>
      </div>
    `

    const report = await convert(slide)

    expect(slide.addImage).toHaveBeenCalledWith(expect.objectContaining({
      data: expect.stringMatching(/^data:image\/svg\+xml;base64,/),
    }))
    expect(report.items[0]).toEqual(expect.objectContaining({
      sourceType: 'mermaid',
      result: 'svg',
      editable: false,
    }))
  })

  it('应将含 foreignObject 的 Mermaid 图表降级为局部截图，避免 PowerPoint 丢字', async () => {
    const slide = createSlideMock()
    const captureElementAsPng = vi.fn(async () => 'data:image/png;base64,capture')
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div class="mermaid-viewer" style="width: 640px; height: 360px;">
          <svg viewBox="0 0 100 50">
            <foreignObject x="0" y="0" width="100" height="50">
              <div xmlns="http://www.w3.org/1999/xhtml">流程标题</div>
            </foreignObject>
          </svg>
        </div>
      </div>
    `

    const report = await convert(slide, captureElementAsPng)
    const addImageCall = slide.addImage.mock.calls[0]?.[0] as Record<string, string>

    expect(captureElementAsPng).toHaveBeenCalledTimes(1)
    expect(addImageCall.data).toBe('data:image/png;base64,capture')
    expect(report.items[0]).toEqual(expect.objectContaining({
      sourceType: 'mermaid',
      result: 'screenshot',
      reason: 'SVG 含 PowerPoint 不兼容的 foreignObject 文本，降级为局部截图',
    }))
  })

  it('应将含 foreignObject 的 Draw.io 图表降级为局部截图，避免 PowerPoint 丢字', async () => {
    const slide = createSlideMock()
    const captureElementAsPng = vi.fn(async () => 'data:image/png;base64,capture')
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <div class="drawio-viewer" style="width: 640px; height: 360px;">
          <svg viewBox="0 0 100 50">
            <foreignObject x="0" y="0" width="100" height="50">
              <div xmlns="http://www.w3.org/1999/xhtml">节点标签</div>
            </foreignObject>
          </svg>
        </div>
      </div>
    `

    const report = await convert(slide, captureElementAsPng)
    const addImageCall = slide.addImage.mock.calls[0]?.[0] as Record<string, string>

    expect(captureElementAsPng).toHaveBeenCalledTimes(1)
    expect(addImageCall.data).toBe('data:image/png;base64,capture')
    expect(report.items[0]).toEqual(expect.objectContaining({
      sourceType: 'drawio',
      result: 'screenshot',
      reason: 'SVG 含 PowerPoint 不兼容的 foreignObject 文本，降级为局部截图',
    }))
  })

  it('应按 LaTeX 实际 SVG 盒子导出，避免被外层 viewer 拉伸', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <section class="latex-viewer" style="width: 420px; height: 180px; display: flex; align-items: center; justify-content: center;">
          <div class="latex-viewer__content">
            <mjx-container>
              <svg viewBox="0 0 160 40"></svg>
            </mjx-container>
          </div>
        </section>
      </div>
    `

    const pageElement = document.getElementById('page') as HTMLElement
    const viewerElement = document.querySelector('.latex-viewer') as HTMLElement
    const svgElement = viewerElement.querySelector('svg') as SVGSVGElement
    const createRect = (left: number, top: number, width: number, height: number) => ({
      x: left,
      y: top,
      left,
      top,
      right: left + width,
      bottom: top + height,
      width,
      height,
      toJSON: () => ({}),
    })

    vi.spyOn(pageElement, 'getBoundingClientRect').mockReturnValue(createRect(0, 0, 1920, 1080))
    vi.spyOn(viewerElement, 'getBoundingClientRect').mockReturnValue(createRect(120, 160, 420, 180))
    vi.spyOn(svgElement, 'getBoundingClientRect').mockReturnValue(createRect(250, 230, 160, 40))

    await convert(slide)
    const imageOptions = slide.addImage.mock.calls[0]?.[0] as {
      x: number
      y: number
      w: number
      h: number
      data: string
    }
    const inchPerPx = 13.333 / 1920

    expect(imageOptions.data).toMatch(/^data:image\/svg\+xml;base64,/)
    expect(imageOptions.x).toBeCloseTo(250 * inchPerPx, 4)
    expect(imageOptions.y).toBeCloseTo(230 * (7.5 / 1080), 4)
    expect(imageOptions.w).toBeCloseTo(160 * inchPerPx, 4)
    expect(imageOptions.h).toBeCloseTo(40 * (7.5 / 1080), 4)
  })

  it('应导出 LaTeX viewer 中的全部 MathJax SVG，而不是只导出第一段公式', async () => {
    const slide = createSlideMock()
    document.body.innerHTML = `
      <div id="page" style="width: 1920px; height: 1080px;">
        <section class="latex-viewer" style="width: 640px; height: 420px;">
          <div class="latex-viewer__content">
            <mjx-container><svg id="formula-a" viewBox="0 0 300 48"></svg></mjx-container>
            <mjx-container><svg id="formula-b" viewBox="0 0 280 48"></svg></mjx-container>
            <mjx-container><svg id="formula-c" viewBox="0 0 320 48"></svg></mjx-container>
          </div>
        </section>
      </div>
    `

    const pageElement = document.getElementById('page') as HTMLElement
    const viewerElement = document.querySelector('.latex-viewer') as HTMLElement
    const svgElements = Array.from(viewerElement.querySelectorAll('svg')) as SVGSVGElement[]
    const createRect = (left: number, top: number, width: number, height: number) => ({
      x: left,
      y: top,
      left,
      top,
      right: left + width,
      bottom: top + height,
      width,
      height,
      toJSON: () => ({}),
    })

    vi.spyOn(pageElement, 'getBoundingClientRect').mockReturnValue(createRect(0, 0, 1920, 1080))
    vi.spyOn(viewerElement, 'getBoundingClientRect').mockReturnValue(createRect(120, 160, 640, 420))
    vi.spyOn(svgElements[0], 'getBoundingClientRect').mockReturnValue(createRect(180, 190, 300, 48))
    vi.spyOn(svgElements[1], 'getBoundingClientRect').mockReturnValue(createRect(190, 260, 280, 48))
    vi.spyOn(svgElements[2], 'getBoundingClientRect').mockReturnValue(createRect(170, 330, 320, 48))

    const report = await convert(slide)
    const imageCalls = slide.addImage.mock.calls.map(call => call[0] as {
      x: number
      y: number
      w: number
      h: number
      data: string
    })
    const inchPerPx = 13.333 / 1920

    expect(imageCalls).toHaveLength(3)
    expect(imageCalls.every(options => /^data:image\/svg\+xml;base64,/.test(options.data))).toBe(true)
    expect(imageCalls.map(options => Math.round(options.y / (7.5 / 1080)))).toEqual([190, 260, 330])
    expect(imageCalls.map(options => Math.round(options.w / inchPerPx))).toEqual([300, 280, 320])
    expect(report.items.filter(item => item.sourceType === 'formula' && item.result === 'svg')).toHaveLength(3)
  })

})
