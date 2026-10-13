/**
 * 文件用途：负责对 PPTX zip 进行 OOXML 组合后处理，将显式语义组的成员图元打包为原生 <p:grpSp>，保持绘制顺序并支持 PPT 拆组。
 */

import { strFromU8, strToU8, unzipSync, zipSync } from 'fflate'

/**
 * 幻灯片图元组合修补指令。
 */
export interface PptxGroupInstruction {
  /** 幻灯片页码（从 1 开始） */
  pageIndex: number
  /** 组稳定标识符 */
  groupId: string
  /** 组显示名称 */
  groupName: string
  /** 组外框 X 坐标（单位：inch） */
  x: number
  /** 组外框 Y 坐标（单位：inch） */
  y: number
  /** 组外框宽度（单位：inch） */
  w: number
  /** 组外框高度（单位：inch） */
  h: number
  /** 属于该组的成员图元 objectName 清单（按绘制顺序排列） */
  memberObjectNames: string[]
}

/** 1 英寸对应的 OpenXML EMU 长度单位。 */
const EMU_PER_INCH = 914400

/**
 * 将 PPTX zip 内指定页面的成员图元按指令封装为原生 <p:grpSp> 组合形状。
 * @param data 原始 PPTX zip 字节数组
 * @param groupInstructions 收集到的组装指令列表
 * @returns 修补后的 PPTX zip 字节数组
 */
export function patchGroups(
  data: Uint8Array,
  groupInstructions: PptxGroupInstruction[],
): Uint8Array {
  if (groupInstructions.length === 0) {
    return data
  }

  const files = unzipSync(data)
  const groupsByPage = new Map<number, PptxGroupInstruction[]>()
  for (const instruction of groupInstructions) {
    if (!instruction.memberObjectNames || instruction.memberObjectNames.length < 2) {
      // 少于 2 个成员的组无需在 OOXML 级别合成 <p:grpSp>
      continue
    }
    const pageGroups = groupsByPage.get(instruction.pageIndex) ?? []
    pageGroups.push(instruction)
    groupsByPage.set(instruction.pageIndex, pageGroups)
  }

  for (const [pageIndex, pageGroups] of groupsByPage) {
    const slidePath = `ppt/slides/slide${pageIndex}.xml`
    const slideFile = files[slidePath]
    if (!slideFile) {
      continue
    }

    let slideXml = strFromU8(slideFile)
    let nextId = 5000 + pageIndex * 100
    for (const instruction of pageGroups) {
      slideXml = patchGroupInSlideXml(slideXml, instruction, nextId++)
    }
    files[slidePath] = strToU8(slideXml)
  }

  return zipSync(files, { level: 6 })
}

/**
 * 在单个 slide XML 文本中，将属于指定组的形状节点提取并封装为 <p:grpSp>。
 * @param slideXml slide XML 原始文本
 * @param instruction 组合指令
 * @param groupShapeId 分配给组的唯一整数 ID
 * @returns 替换后的 slide XML 文本
 */
export function patchGroupInSlideXml(
  slideXml: string,
  instruction: PptxGroupInstruction,
  groupShapeId: number,
): string {
  if (!instruction.memberObjectNames || instruction.memberObjectNames.length === 0) {
    return slideXml
  }

  // 1. 查找每个 memberObjectName 对应的 XML 节点
  const matchedNodes: Array<{ name: string; fullXml: string; startIndex: number }> = []

  for (const memberName of instruction.memberObjectNames) {
    const escapedName = escapeRegExp(escapeXmlAttribute(memberName))
    // 匹配 <p:sp> 或 <p:pic> 包含该 name 属性的节点
    const shapeRegex = new RegExp(
      `<(p:(?:sp|pic))>[\\s\\S]*?<p:cNvPr[^>]*\\bname="${escapedName}"[^>]*>[\\s\\S]*?<\\/\\1>`,
      'g',
    )
    const match = shapeRegex.exec(slideXml)
    if (match) {
      matchedNodes.push({
        name: memberName,
        fullXml: match[0],
        startIndex: match.index,
      })
    }
  }

  // 若匹配到的成员少于 2 个，则不进行包装，保持原样
  if (matchedNodes.length < 2) {
    return slideXml
  }

  // 2. 按在 slideXml 中的出现顺序排序，确保在原位置保持 z-order
  matchedNodes.sort((a, b) => a.startIndex - b.startIndex)

  // 3. 构造 <p:grpSp> XML
  const offX = Math.round(instruction.x * EMU_PER_INCH)
  const offY = Math.round(instruction.y * EMU_PER_INCH)
  const extCX = Math.max(1, Math.round(instruction.w * EMU_PER_INCH))
  const extCY = Math.max(1, Math.round(instruction.h * EMU_PER_INCH))

  const groupName = escapeXmlAttribute(instruction.groupName || instruction.groupId)
  const innerShapesXml = matchedNodes.map(m => m.fullXml).join('')

  const grpSpXml = `<p:grpSp><p:nvGrpSpPr><p:cNvPr id="${groupShapeId}" name="${groupName}"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="${offX}" y="${offY}"/><a:ext cx="${extCX}" cy="${extCY}"/><a:chOff x="${offX}" y="${offY}"/><a:chExt cx="${extCX}" cy="${extCY}"/></a:xfrm></p:grpSpPr>${innerShapesXml}</p:grpSp>`

  // 4. 从 slideXml 中移除已匹配的节点，并将 grpSpXml 插入到第一个成员的原位置
  const firstNode = matchedNodes[0]
  let resultXml = slideXml

  // 先把第一个节点替换为 grpSpXml，其余节点替换为空
  for (let i = 0; i < matchedNodes.length; i++) {
    const node = matchedNodes[i]
    if (i === 0) {
      resultXml = resultXml.replace(node.fullXml, grpSpXml)
    } else {
      resultXml = resultXml.replace(node.fullXml, '')
    }
  }

  return resultXml
}

/**
 * 转义正则表达式特殊字符。
 */
function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * 转义 XML 属性值中的特殊字符。
 */
function escapeXmlAttribute(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}
