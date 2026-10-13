/**
 * 文件用途：封装 PptxGenJS 演示文稿实例创建、OOXML 渐变后处理与浏览器文件下载。
 */

import PptxGenJS from 'pptxgenjs'
import { strFromU8, strToU8, unzipSync, zipSync } from 'fflate'
import type {
  PptxGradientFillInstruction,
  PptxShapeTypes,
} from '@/core/services/pptx/PPTXDomConverter.types'
import { patchGradientFillInSlideXml } from '@/core/services/pptx/writer/OoxmlGradientPatcher'
import { patchGroupInSlideXml, type PptxGroupInstruction } from '@/core/services/pptx/writer/OoxmlGroupPatcher'
import { nextSlideShapeId } from './OoxmlShapeNodes'
import { patchThemeColors, promoteSharedSlideBackground } from './OoxmlPresentationTheme'
import type { PptxPresentationTheme } from '../theme/PptxThemeResolver'

const PPTX_LAYOUT_NAME = 'RUNTIME_PPTX_LAYOUT'

/**
 * PPTX 幻灯片物理尺寸（单位：英寸）。
 */
export interface PptxSlideLayout {
  widthIn: number
  heightIn: number
}

/**
 * PPTX 文档写入器，隔离 PptxGenJS、fflate 与浏览器 Blob 下载细节。
 */
export class PptxPackageWriter {
  private readonly themes = new WeakMap<PptxGenJS, PptxPresentationTheme>()
  /**
   * 按设计画布宽高比计算 PPTX 幻灯片物理尺寸（长边固定 13.333 英寸）。
   * @param pageWidthPx 设计画布宽度（px）
   * @param pageHeightPx 设计画布高度（px）
   * @returns 幻灯片宽高（inch）
   */
  resolveSlideLayout(pageWidthPx = 1920, pageHeightPx = 1080): PptxSlideLayout {
    const safeWidth = Number(pageWidthPx) || 1920
    const safeHeight = Number(pageHeightPx) || 1080
    const aspectRatio = safeWidth / safeHeight
    const longEdge = 13.333

    if (aspectRatio >= 1) {
      return {
        widthIn: longEdge,
        heightIn: longEdge / aspectRatio,
      }
    }

    return {
      widthIn: longEdge * aspectRatio,
      heightIn: longEdge,
    }
  }

  /**
   * 创建配置好布局与中文字体主题的 PptxGenJS 实例。
   * @param title 演示文稿标题
   * @param layout 幻灯片物理尺寸
   * @returns PptxGenJS 实例
   */
  createPresentation(
    title = 'Runtime 导出',
    layout?: PptxSlideLayout,
    theme?: import('@/core/services/pptx/theme/PptxThemeResolver').PptxPresentationTheme,
    masterProps?: Record<string, unknown>,
  ): PptxGenJS {
    const pptx = new PptxGenJS()
    const resolvedLayout = layout ?? this.resolveSlideLayout()

    pptx.defineLayout({
      name: PPTX_LAYOUT_NAME,
      width: resolvedLayout.widthIn,
      height: resolvedLayout.heightIn,
    })
    pptx.layout = PPTX_LAYOUT_NAME
    pptx.author = 'web-runtime-vue'
    pptx.company = 'web-runtime-vue'
    pptx.subject = 'Runtime editable PPTX export'
    pptx.title = title
    pptx.theme = {
      headFontFace: theme?.headFontFace || 'Microsoft YaHei',
      bodyFontFace: theme?.bodyFontFace || 'Microsoft YaHei',
    }
    if (theme) this.themes.set(pptx, { ...theme, colors: { ...theme.colors } })

    if (masterProps && typeof pptx.defineSlideMaster === 'function') {
      pptx.defineSlideMaster(masterProps as unknown as Parameters<typeof pptx.defineSlideMaster>[0])
    }

    return pptx
  }

  /**
   * 从 PptxGenJS 实例提取形状类型字典。
   * @param pptx PptxGenJS 实例
   * @returns 标准形状枚举映射
   */
  getShapeTypes(pptx: Pick<PptxGenJS, 'ShapeType'>): PptxShapeTypes {
    return {
      rect: pptx.ShapeType.rect,
      roundRect: pptx.ShapeType.roundRect,
      ellipse: pptx.ShapeType.ellipse,
      line: pptx.ShapeType.line,
    }
  }

  /**
   * 生成 PPTX 二进制字节（含 OOXML 线性渐变修补），不触发浏览器下载。
   * @param pptx PptxGenJS 实例
   * @param gradientFills 渐变填充指令列表
   * @returns PPTX 字节数组
   */
  async generatePresentationBytes(
    pptx: PptxGenJS,
    gradientFills: PptxGradientFillInstruction[] = [],
    groupInstructions: PptxGroupInstruction[] = [],
  ): Promise<Uint8Array> {
    // 后处理共用一次解包和一次压缩，避免按渐变、组合、主题分别重复处理整个文件。
    const rawPptx = await pptx.write({ outputType: 'uint8array', compression: false }) as Uint8Array
    const files = unzipSync(rawPptx)
    for (const instruction of gradientFills) {
      const path = `ppt/slides/slide${instruction.pageIndex}.xml`
      if (!files[path]) throw new Error(`PPTX 渐变目标页不存在：${instruction.pageIndex}`)
      files[path] = strToU8(patchGradientFillInSlideXml(strFromU8(files[path]), instruction))
    }
    for (const instruction of groupInstructions) {
      const path = `ppt/slides/slide${instruction.pageIndex}.xml`
      if (!files[path]) throw new Error(`PPTX 组合目标页不存在：${instruction.pageIndex}`)
      const xml = strFromU8(files[path])
      files[path] = strToU8(patchGroupInSlideXml(xml, instruction, nextSlideShapeId(xml)))
    }
    const theme = this.themes.get(pptx)
    if (theme) {
      for (const path of Object.keys(files).filter(name => /^ppt\/theme\/theme\d+\.xml$/.test(name))) {
        files[path] = strToU8(patchThemeColors(strFromU8(files[path]), theme))
      }
    }
    promoteSharedSlideBackground(files)
    return zipSync(files, { level: 6 })
  }

  /**
   * 写出 PPTX 文件并触发下载；若存在线性渐变或组合指令则先修补 OOXML。
   * @param pptx PptxGenJS 实例
   * @param filename 导出文件名
   * @param gradientFills 渐变填充指令列表
   * @param groupInstructions 组合图元指令列表
   */
  async writePresentationFile(
    pptx: PptxGenJS,
    filename: string,
    gradientFills: PptxGradientFillInstruction[] = [],
    groupInstructions: PptxGroupInstruction[] = [],
  ): Promise<void> {
    const data = await this.generatePresentationBytes(pptx, gradientFills, groupInstructions)
    this.savePptxBlob(filename, data)
  }

  /**
   * 在浏览器中触发 PPTX 二进制数据下载。
   * @param filename 下载文件名
   * @param data PPTX 字节数组
   */
  savePptxBlob(filename: string, data: Uint8Array): void {
    const arrayBuffer = new ArrayBuffer(data.byteLength)
    new Uint8Array(arrayBuffer).set(data)
    const blob = new Blob([arrayBuffer], {
      type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.style.display = 'none'
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.setTimeout(() => window.URL.revokeObjectURL(url), 100)
  }
}
