// @vitest-environment jsdom

/**
 * 文件用途：验证 OOXML 渐变填充修补器对线性渐变角度、颜色停靠点和 zip 内 slide XML 替换的正确性。
 */

import { strFromU8, strToU8, unzipSync, zipSync } from 'fflate'
import { describe, expect, it } from 'vitest'
import {
  buildGradientFillXml,
  gradientDirectionToPptAngle,
  patchGradientFillInSlideXml,
  patchGradientFills,
} from './OoxmlGradientPatcher'

describe('OoxmlGradientPatcher', () => {
  it('应将 CSS 线性渐变方向正确映射为 PowerPoint OOXML 角度', () => {
    expect(gradientDirectionToPptAngle('right')).toBe(0)
    expect(gradientDirectionToPptAngle('bottom')).toBe(90)
    expect(gradientDirectionToPptAngle('left')).toBe(180)
    expect(gradientDirectionToPptAngle('top')).toBe(270)
  })

  it('应根据渐变指令构造包含 stops 与角度的 <a:gradFill> XML', () => {
    const xml = buildGradientFillXml({
      pageIndex: 1,
      objectName: 'pptx-gradient-p1-1-div',
      direction: 'bottom',
      stops: [
        { position: 0, color: { hex: '1E3A8A', alpha: 1 } },
        { position: 1, color: { hex: '3B82F6', alpha: 0.5 } },
      ],
    })

    expect(xml).toBe(
      '<a:gradFill rotWithShape="1">' +
      '<a:gsLst>' +
      '<a:gs pos="0"><a:srgbClr val="1E3A8A"><a:alpha val="100000"/></a:srgbClr></a:gs>' +
      '<a:gs pos="100000"><a:srgbClr val="3B82F6"><a:alpha val="50000"/></a:srgbClr></a:gs>' +
      '</a:gsLst>' +
      '<a:lin ang="5400000" scaled="0"/>' +
      '</a:gradFill>',
    )
  })

  it('应只替换目标对象名对应的 <a:solidFill> 并保留其他形状不变', () => {
    const slideXml = [
      '<p:spTree>',
      '<p:sp><p:nvSpPr><p:cNvPr id="2" name="pptx-gradient-p1-1-card"/></p:nvSpPr><p:spPr><a:prstGeom prst="roundRect"/><a:solidFill><a:srgbClr val="2563EB"/></a:solidFill></p:spPr></p:sp>',
      '<p:sp><p:nvSpPr><p:cNvPr id="3" name="normal-shape"/></p:nvSpPr><p:spPr><a:prstGeom prst="rect"/><a:solidFill><a:srgbClr val="0F172A"/></a:solidFill></p:spPr></p:sp>',
      '</p:spTree>',
    ].join('')

    const patched = patchGradientFillInSlideXml(slideXml, {
      pageIndex: 1,
      objectName: 'pptx-gradient-p1-1-card',
      direction: 'right',
      stops: [
        { position: 0, color: { hex: '2563EB', alpha: 1 } },
        { position: 1, color: { hex: '7C3AED', alpha: 1 } },
      ],
    })

    expect(patched).toContain('<a:gradFill rotWithShape="1">')
    expect(patched).toContain('name="normal-shape"/></p:nvSpPr><p:spPr><a:prstGeom prst="rect"/><a:solidFill><a:srgbClr val="0F172A"/></a:solidFill>')
  })

  it('应对 zip 包中的对应 slideN.xml 执行批量渐变修补', () => {
    const rawZip = zipSync({
      'ppt/slides/slide1.xml': strToU8(
        '<p:sp><p:nvSpPr><p:cNvPr id="2" name="grad-1"/></p:nvSpPr><p:spPr><a:noFill/></p:spPr></p:sp>',
      ),
    })

    const patchedZip = patchGradientFills(rawZip, [
      {
        pageIndex: 1,
        objectName: 'grad-1',
        direction: 'left',
        stops: [
          { position: 0, color: { hex: '111827', alpha: 1 } },
          { position: 1, color: { hex: '4B5563', alpha: 1 } },
        ],
      },
    ])

    const files = unzipSync(patchedZip)
    const slide1Xml = strFromU8(files['ppt/slides/slide1.xml'])
    expect(slide1Xml).toContain('<a:gradFill rotWithShape="1">')
    expect(slide1Xml).toContain('<a:lin ang="10800000" scaled="0"/>')
  })
})
