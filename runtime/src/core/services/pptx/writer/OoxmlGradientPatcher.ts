/**
 * 文件用途：负责对 PptxGenJS 生成的 PPTX zip 字节进行 OOXML 后处理，将渐变形状的单色兜底填充替换为原生 <a:gradFill>。
 */

import { strFromU8, strToU8, unzipSync, zipSync } from 'fflate'
import type { PptxGradientFillInstruction } from '@/core/services/pptx/PPTXDomConverter.types'

/**
 * 将 PPTX zip 内指定形状的填充替换为 OOXML 原生线性渐变。
 * @param data 原始 PPTX zip 字节数组
 * @param gradientFills 收集到的渐变填充指令列表
 * @returns 修补后的 PPTX zip 字节数组
 */
export function patchGradientFills(
  data: Uint8Array,
  gradientFills: PptxGradientFillInstruction[],
): Uint8Array {
  if (gradientFills.length === 0) {
    return data
  }

  const files = unzipSync(data)
  const fillsByPage = new Map<number, PptxGradientFillInstruction[]>()
  for (const instruction of gradientFills) {
    const pageFills = fillsByPage.get(instruction.pageIndex) ?? []
    pageFills.push(instruction)
    fillsByPage.set(instruction.pageIndex, pageFills)
  }

  for (const [pageIndex, pageFills] of fillsByPage) {
    const slidePath = `ppt/slides/slide${pageIndex}.xml`
    const slideFile = files[slidePath]
    if (!slideFile) {
      continue
    }

    let slideXml = strFromU8(slideFile)
    for (const instruction of pageFills) {
      slideXml = patchGradientFillInSlideXml(slideXml, instruction)
    }
    files[slidePath] = strToU8(slideXml)
  }

  return zipSync(files, { level: 6 })
}

/**
 * 替换单个 slide XML 内目标形状的 fill 节点为 <a:gradFill>。
 * @param slideXml slide XML 原始文本
 * @param instruction 渐变填充指令
 * @returns 替换后的 slide XML 文本
 */
export function patchGradientFillInSlideXml(
  slideXml: string,
  instruction: PptxGradientFillInstruction,
): string {
  const objectName = escapeRegExp(escapeXmlAttribute(instruction.objectName))
  const shapeRegex = new RegExp(
    `(<p:sp>[\\s\\S]*?<p:cNvPr[^>]*\\bname="${objectName}"[^>]*>[\\s\\S]*?<p:spPr[^>]*>[\\s\\S]*?)(<a:solidFill>[\\s\\S]*?<\\/a:solidFill>|<a:noFill\\s*\\/>)`,
  )

  return slideXml.replace(shapeRegex, `$1${buildGradientFillXml(instruction)}`)
}

/**
 * 构造 OOXML 线性渐变填充片段（<a:gradFill>）。
 * @param instruction 渐变填充指令
 * @returns OOXML <a:gradFill> 字符串
 */
export function buildGradientFillXml(instruction: PptxGradientFillInstruction): string {
  const stopsXml = instruction.stops
    .map(stop => {
      const position = Math.round(Math.max(0, Math.min(1, stop.position)) * 100000)
      const alpha = Math.round(Math.max(0, Math.min(1, stop.color.alpha)) * 100000)
      return `<a:gs pos="${position}"><a:srgbClr val="${stop.color.hex}"><a:alpha val="${alpha}"/></a:srgbClr></a:gs>`
    })
    .join('')
  const pptDegrees = typeof instruction.angle === 'number'
    ? ((instruction.angle - 90) % 360 + 360) % 360
    : gradientDirectionToPptAngle(instruction.direction)
  const angle = Math.round(pptDegrees * 60000)
  return `<a:gradFill rotWithShape="1"><a:gsLst>${stopsXml}</a:gsLst><a:lin ang="${angle}" scaled="0"/></a:gradFill>`
}

/**
 * 将 CSS 线性渐变方向映射为 PowerPoint OOXML 角度（单位：度）。
 * @param direction CSS 目标方向
 * @returns 角度值（0 / 90 / 180 / 270）
 */
export function gradientDirectionToPptAngle(direction: PptxGradientFillInstruction['direction']): number {
  switch (direction) {
    case 'left':
      return 180
    case 'bottom':
      return 90
    case 'top':
      return 270
    case 'right':
    default:
      return 0
  }
}

/**
 * 转义正则表达式特殊字符。
 * @param value 原始文本
 */
function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * 转义 XML 属性值中的特殊字符。
 * @param value 原始属性值
 */
function escapeXmlAttribute(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}
