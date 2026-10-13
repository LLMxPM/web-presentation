/**
 * 文件用途：负责对 PPTX zip 进行 OOXML 组合后处理，将显式语义组的成员图元打包为原生 <p:grpSp>，保持绘制顺序并支持 PPT 拆组。
 */

import { strFromU8, strToU8, unzipSync, zipSync } from 'fflate'
import { escapeXmlAttribute, nextSlideShapeId, readSlideShapeNodes } from './OoxmlShapeNodes'

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
    for (const instruction of pageGroups) {
      slideXml = patchGroupInSlideXml(slideXml, instruction, nextSlideShapeId(slideXml))
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
  const names = new Set(instruction.memberObjectNames.map(escapeXmlAttribute))
  if (names.size < 2 || names.size !== instruction.memberObjectNames.length) return slideXml
  const nodes = readSlideShapeNodes(slideXml)
  const selected = nodes.map((node, index) => ({ ...node, index })).filter(node => node.name && names.has(node.name))
  // 名称必须唯一、全部命中且连续，不能因组合改变不属于本组的图元层级。
  if (selected.length !== names.size || new Set(selected.map(node => node.name)).size !== names.size) return slideXml
  if (selected.at(-1)!.index - selected[0].index + 1 !== selected.length) return slideXml
  if (![instruction.x, instruction.y, instruction.w, instruction.h].every(Number.isFinite) || instruction.w <= 0 || instruction.h <= 0) return slideXml

  const offX = Math.round(instruction.x * EMU_PER_INCH)
  const offY = Math.round(instruction.y * EMU_PER_INCH)
  const extCX = Math.max(1, Math.round(instruction.w * EMU_PER_INCH))
  const extCY = Math.max(1, Math.round(instruction.h * EMU_PER_INCH))
  const id = new RegExp(`<p:cNvPr\\b[^>]*\\bid="${groupShapeId}"`).test(slideXml) ? nextSlideShapeId(slideXml) : groupShapeId
  const name = escapeXmlAttribute(instruction.groupName || instruction.groupId)
  const group = `<p:grpSp><p:nvGrpSpPr><p:cNvPr id="${id}" name="${name}"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="${offX}" y="${offY}"/><a:ext cx="${extCX}" cy="${extCY}"/><a:chOff x="${offX}" y="${offY}"/><a:chExt cx="${extCX}" cy="${extCY}"/></a:xfrm></p:grpSpPr>${selected.map(node => node.xml).join('')}</p:grpSp>`
  return slideXml.slice(0, selected[0].start) + group + slideXml.slice(selected.at(-1)!.end)
}
