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
})
