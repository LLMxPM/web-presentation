/**
 * 文件用途：封装 PPTX DOM 转换里的媒体、背景图、截图与 SVG/canvas 导出逻辑。
 */

import type {
  PptxExportReportItem,
  PptxReportItemResult,
  PptxReportSourceType,
} from '@/core/types/pptx-export'
import type { PPTXSvgSerializer } from '@/core/services/pptx/PPTXSvgSerializer'
import type {
  ElementBox,
  ImageSizingOptions,
  PptxPageConvertOptions,
  VisitContext,
} from '@/core/services/pptx/PPTXDomConverter.types'
import { MEDIA_SELECTORS } from '@/core/services/pptx/PPTXDomConverter.types'
import type { PPTXDomConverterLayout } from '@/core/services/pptx/PPTXDomConverterLayout'
import { PPTXImageDataResolver } from '@/core/services/pptx/PPTXImageDataResolver'
import { PPTXDomConverterTransform } from '@/core/services/pptx/PPTXDomConverterTransform'

const PPT_UNSAFE_SVG_REASON = 'SVG 含 PowerPoint 不兼容的 foreignObject 文本，降级为局部截图'
const PPT_UNSAFE_SVG_SOURCE_REASON = 'SVG 源文件含 PowerPoint 不兼容的 foreignObject 文本，降级为局部截图'

export interface PptxDomMediaExportHost {
  options: PptxPageConvertOptions
  buildPptObjectMeta: (
    context: VisitContext,
    role: string,
    label: string,
    includeAltText?: boolean,
  ) => Record<string, unknown>
  addReportItem: (
    sourceType: PptxReportSourceType,
    result: PptxReportItemResult,
    editable: boolean,
    label: string,
    reason?: string,
    context?: VisitContext,
  ) => PptxExportReportItem
  addSkippedItem: (
    sourceType: PptxReportSourceType,
    label: string,
    reason: string,
    context?: VisitContext,
  ) => void
}

interface IntrinsicImageSize {
  width: number
  height: number
}

interface ResolvedImageSizingOptions {
  w?: number
  h?: number
  sizing?: ImageSizingOptions
}

interface ResolvedSvgExportPayload {
  data: string
  boxElement: Element
  boxOverride?: ElementBox
}

/**
 * PPTX 媒体导出 helper。
 */
export class PPTXDomConverterMedia {
  private readonly imageDataResolver = new PPTXImageDataResolver()
  private readonly transform: PPTXDomConverterTransform

  constructor(
    private readonly layout: PPTXDomConverterLayout,
    private readonly svgSerializer: PPTXSvgSerializer,
  ) {
    this.transform = new PPTXDomConverterTransform(layout)
  }

  /**
   * 判断元素是否属于媒体或复杂渲染组件。
   * @param element 候选元素
   */
  isMediaElement(element: Element): boolean {
    const tagName = element.tagName.toLowerCase()
    return element.matches(MEDIA_SELECTORS) ||
      tagName === 'img' ||
      tagName === 'svg' ||
      tagName === 'canvas' ||
      tagName === 'video'
  }

  /**
   * 添加媒体、SVG、canvas、视频封面或局部截图。
   * @param host 导出宿主能力
   * @param element 媒体元素
   * @param context 当前组合上下文
   */
  async addMediaElement(host: PptxDomMediaExportHost, element: Element, context: VisitContext): Promise<void> {
    const sourceType = this.resolveMediaSourceType(element)
    const label = this.layout.buildElementLabel(element)

    if (sourceType === 'formula') {
      await this.addFormulaSvgBlocks(host, element, label, context)
      return
    }

    if (this.isSvgBasedSource(sourceType, element)) {
      const svg = this.findRenderableSvg(element)
      if (svg) {
        if (await this.addUnsupportedSvgScreenshot(host, element, svg, sourceType, context, PPT_UNSAFE_SVG_REASON)) {
          return
        }
        await this.addSvgBlock(host, svg, this.resolveSvgPlacementElement(sourceType, element, svg), sourceType, label, context)
        return
      }
      await this.addScreenshotBlock(host, element, sourceType, '未找到可序列化 SVG，降级为局部截图', context)
      return
    }

    if (sourceType === 'chart') {
      const svg = this.findRenderableSvg(element)
      if (svg) {
        if (await this.addUnsupportedSvgScreenshot(host, element, svg, sourceType, context, PPT_UNSAFE_SVG_REASON)) {
          return
        }
        await this.addSvgBlock(host, svg, this.resolveSvgPlacementElement(sourceType, element, svg), sourceType, label, context)
        return
      }

      const canvas = element.querySelector?.('canvas') ?? (element instanceof HTMLCanvasElement ? element : null)
      if (canvas instanceof HTMLCanvasElement && await this.addCanvasBlock(host, canvas, element, sourceType, label, context)) {
        return
      }

      await this.addScreenshotBlock(host, element, sourceType, 'ECharts 未提供 SVG 或 canvas，降级为局部截图', context)
      return
    }

    if (sourceType === 'canvas' && element instanceof HTMLCanvasElement) {
      if (!await this.addCanvasBlock(host, element, element, sourceType, label, context)) {
        host.addSkippedItem(sourceType, label, 'canvas 像素为空或无法读取', context)
      }
      return
    }

    if (sourceType === 'video') {
      await this.addVideoBlock(host, element, label, context)
      return
    }

    const image = element instanceof HTMLImageElement ? element : element.querySelector?.('img')
    if (image instanceof HTMLImageElement && await this.addImagePathBlock(host, image.currentSrc || image.src, element, sourceType, label, context)) {
      return
    }

    await this.addScreenshotBlock(host, element, sourceType, '未找到可直接导出的图片资源，降级为局部截图', context)
  }

  /**
   * 将简单 CSS background-image: url(...) 导出为 PPT 图片块。
   * @param host 导出宿主能力
   * @param element 背景图元素
   * @param context 当前组合上下文
   */
  async addBackgroundImageElement(
    host: PptxDomMediaExportHost,
    element: HTMLElement,
    context: VisitContext,
  ): Promise<boolean> {
    const style = window.getComputedStyle(element)
    const backgroundUrl = this.extractSingleBackgroundImageUrl(style.backgroundImage)
    if (!backgroundUrl) {
      return false
    }

    const label = this.layout.buildElementLabel(element)
    if (backgroundUrl.startsWith('data:image/')) {
      await this.addImageDataBlock(host, backgroundUrl, element, 'image', label, 'CSS 背景图导出为图片块', context, backgroundUrl)
      return true
    }

    return this.addImagePathBlock(host, backgroundUrl, element, 'image', label, context, 'CSS 背景图导出为图片块')
  }

  /**
   * 添加视频封面图；没有封面时尝试当前帧，最后降级为截图。
   * @param host 导出宿主能力
   * @param element 视频或视频容器
   * @param label 对象摘要
   * @param context 当前组合上下文
   */
  private async addVideoBlock(
    host: PptxDomMediaExportHost,
    element: Element,
    label: string,
    context: VisitContext,
  ): Promise<void> {
    const video = element instanceof HTMLVideoElement ? element : element.querySelector?.('video')
    if (!(video instanceof HTMLVideoElement)) {
      await this.addScreenshotBlock(host, element, 'video', '未找到 video 元素，降级为局部截图', context)
      return
    }

    const poster = video.getAttribute('poster') || video.poster
    if (poster && await this.addImagePathBlock(host, poster, element, 'video', label, context, '视频封面图导出为图片块')) {
      return
    }

    try {
      const canvas = document.createElement('canvas')
      const rect = this.layout.measureElementPixels(video)
      canvas.width = Math.max(1, Math.round(rect.width))
      canvas.height = Math.max(1, Math.round(rect.height))
      const canvasContext = canvas.getContext('2d')
      if (!canvasContext) {
        throw new Error('无法创建视频帧 canvas')
      }
      canvasContext.drawImage(video, 0, 0, canvas.width, canvas.height)
      await this.addImageDataBlock(host, canvas.toDataURL('image/png'), element, 'video', label, '视频当前帧导出为图片块', context)
    } catch {
      await this.addScreenshotBlock(host, element, 'video', '视频无封面且当前帧不可读取，降级为局部截图', context)
    }
  }

  /**
   * 判断当前媒体类型是否应优先导出为 SVG。
   * @param sourceType 源类型
   * @param element 源元素
   */
  private isSvgBasedSource(sourceType: PptxReportSourceType, element: Element): boolean {
    return sourceType === 'svg' ||
      sourceType === 'mermaid' ||
      sourceType === 'drawio' ||
      sourceType === 'formula' ||
      element.tagName.toLowerCase() === 'svg'
  }

  /**
   * 将 SVG 添加为 PPT 图片块。
   * @param host 导出宿主能力
   * @param svg SVG 元素
   * @param boxElement 用于在 slide 中定位和定尺寸的元素
   * @param sourceType 源类型
   * @param label 对象摘要
   * @param context 当前组合上下文
   */
  private addSvgBlock(
    host: PptxDomMediaExportHost,
    svg: SVGSVGElement,
    boxElement: Element,
    sourceType: PptxReportSourceType,
    label: string,
    context: VisitContext,
  ): Promise<void> {
    const exportPayload = this.resolveSvgExportPayload(svg, boxElement)
    return this.addImageDataBlock(
      host,
      exportPayload.data,
      exportPayload.boxElement,
      sourceType,
      label,
      'SVG 作为可移动缩放图片块',
      context,
      undefined,
      exportPayload.boxOverride,
    )
  }

  /**
   * 逐个导出 MathJax 生成的公式 SVG，避免多段公式只保留首段。
   * @param host 导出宿主能力
   * @param element LaTeX viewer 根元素
   * @param label 对象摘要
   * @param context 当前组合上下文
   */
  private async addFormulaSvgBlocks(
    host: PptxDomMediaExportHost,
    element: Element,
    label: string,
    context: VisitContext,
  ): Promise<void> {
    const svgs = this.findRenderableSvgs(element)
    if (svgs.length === 0) {
      await this.addScreenshotBlock(host, element, 'formula', '未找到可序列化 SVG，降级为局部截图', context)
      return
    }

    for (const svg of svgs) {
      if (await this.addUnsupportedSvgScreenshot(host, element, svg, 'formula', context, PPT_UNSAFE_SVG_REASON)) {
        continue
      }
      await this.addSvgBlock(host, svg, svg, 'formula', label, context)
    }
  }

  /**
   * 将 canvas 添加为 PNG 图片块。
   * @param host 导出宿主能力
   * @param canvas canvas 元素
   * @param element 源元素
   * @param sourceType 源类型
   * @param label 对象摘要
   * @param context 当前组合上下文
   */
  private addCanvasBlock(
    host: PptxDomMediaExportHost,
    canvas: HTMLCanvasElement,
    element: Element,
    sourceType: PptxReportSourceType,
    label: string,
    context: VisitContext,
  ): Promise<boolean> {
    if (canvas.width <= 0 || canvas.height <= 0) {
      return Promise.resolve(false)
    }

    try {
      return this.addImageDataBlock(host, canvas.toDataURL('image/png'), element, sourceType, label, 'canvas 导出为 PNG 图片块', context)
        .then(() => true)
    } catch {
      return Promise.resolve(false)
    }
  }

  /**
   * 按 URL 添加图片块。
   * @param host 导出宿主能力
   * @param path 图片 URL
   * @param element 源元素
   * @param sourceType 源类型
   * @param label 对象摘要
   * @param context 当前组合上下文
   * @param reason 报告原因
   */
  private async addImagePathBlock(
    host: PptxDomMediaExportHost,
    path: string,
    element: Element,
    sourceType: PptxReportSourceType,
    label: string,
    context: VisitContext,
    reason = '图片作为可移动缩放图片块',
  ): Promise<boolean> {
    if (!path) {
      return false
    }

    const svgSource = await this.svgSerializer.resolveSvgSource(path)
    if (svgSource) {
      if (this.svgSerializer.shouldRasterizeSourceForPpt(svgSource)) {
        const screenshotTarget = this.resolveScreenshotTarget(element)
        if (screenshotTarget) {
          await this.addScreenshotBlock(host, screenshotTarget, sourceType, PPT_UNSAFE_SVG_SOURCE_REASON, context)
          return true
        }
      }
      await this.addImageDataBlock(
        host,
        this.svgSerializer.svgSourceToDataUrl(svgSource),
        element,
        sourceType === 'image' ? 'svg' : sourceType,
        label,
        'SVG 源文件原样嵌入为可移动缩放图片块',
        context,
      )
      return true
    }

    const imageData = await this.imageDataResolver.resolve(path)
    if (imageData) {
      await this.addImageDataBlock(host, imageData, element, sourceType, label, reason, context, imageData)
      return true
    }

    if (this.imageDataResolver.shouldAvoidDeferredPath(path)) {
      await this.addScreenshotBlock(host, element, sourceType, `图片 URL 无法读取，降级为局部截图：${path}`, context)
      return true
    }

    const box = this.layout.getPptxBox(element, Boolean(context.rotationSteps?.length))
    if (!box) {
      host.addSkippedItem(sourceType, label, '图片元素尺寸无效', context)
      return true
    }

    const imageSizing = await this.buildImageSizing(element, box, path)
    host.options.slide.addImage({
      path,
      ...this.buildTransformedImageOptions(box, imageSizing, context),
      ...host.buildPptObjectMeta(context, 'image', label, true),
    })
    host.addReportItem(sourceType, 'image', false, label, reason, context)
    return true
  }

  /**
   * 按 data URL 添加图片块。
   * @param host 导出宿主能力
   * @param data 图片 data URL
   * @param element 源元素
   * @param sourceType 源类型
   * @param label 对象摘要
   * @param reason 报告原因
   * @param context 当前组合上下文
   */
  private addImageDataBlock(
    host: PptxDomMediaExportHost,
    data: string,
    element: Element,
    sourceType: PptxReportSourceType,
    label: string,
    reason: string,
    context: VisitContext,
    source?: string,
    boxOverride?: ElementBox,
  ): Promise<void> {
    const box = boxOverride ?? this.layout.getPptxBox(element, Boolean(context.rotationSteps?.length))
    if (!box) {
      host.addSkippedItem(sourceType, label, '图片块尺寸无效', context)
      return Promise.resolve()
    }

    return this.buildImageSizing(element, box, source || data).then(imageSizing => {
      host.options.slide.addImage({
        data,
        ...this.buildTransformedImageOptions(box, imageSizing, context),
        ...host.buildPptObjectMeta(context, data.startsWith('data:image/svg') ? 'svg' : 'image', label, true),
      })
      host.addReportItem(sourceType, data.startsWith('data:image/svg') ? 'svg' : 'image', false, label, reason, context)
    })
  }

  /**
   * 添加局部截图块。
   * @param host 导出宿主能力
   * @param element 目标元素
   * @param sourceType 源类型
   * @param reason 降级原因
   * @param context 当前组合上下文
   */
  async addScreenshotBlock(
    host: PptxDomMediaExportHost,
    element: Element,
    sourceType: PptxReportSourceType,
    reason: string,
    context: VisitContext,
  ): Promise<void> {
    if (!(element instanceof HTMLElement)) {
      host.addSkippedItem(sourceType, this.layout.buildElementLabel(element), '非 HTML 元素无法局部截图', context)
      return
    }

    const box = this.layout.getPptxBox(element, Boolean(context.rotationSteps?.length))
    const label = this.layout.buildElementLabel(element)
    if (!box) {
      host.addSkippedItem(sourceType, label, '截图元素尺寸无效', context)
      return
    }

    try {
      const data = await host.options.captureElementAsPng(element)
      host.options.slide.addImage({
        data,
        ...this.transform.applyToBox(box, context),
        ...host.buildPptObjectMeta(context, 'screenshot', label, true),
      })
      host.addReportItem(sourceType, 'screenshot', false, label, reason, context)
    } catch (error) {
      host.addSkippedItem(
        sourceType,
        label,
        `局部截图失败：${error instanceof Error ? error.message : '未知错误'}`,
        context,
      )
    }
  }

  /**
   * 先应用 object-fit 尺寸，再把图片盒模型映射到旋转后的中心位置。
   */
  private buildTransformedImageOptions(
    box: ElementBox,
    sizing: ResolvedImageSizingOptions,
    context: VisitContext,
  ): Record<string, unknown> {
    const sizedBox = {
      ...box,
      w: sizing.w ?? box.w,
      h: sizing.h ?? box.h,
    }
    return {
      ...this.transform.applyToBox(sizedBox, context),
      ...(sizing.sizing ? { sizing: sizing.sizing } : {}),
    }
  }

  /**
   * 根据图片元素样式构造 PPTX 图片缩放策略。
   * @param element 图片或图片容器
   * @param box PPTX 位置尺寸
   * @param source 图片源地址或 data URL
   */
  private async buildImageSizing(element: Element, box: ElementBox, source?: string): Promise<ResolvedImageSizingOptions> {
    const sizingMode = this.resolveImageSizingMode(element)
    if (!sizingMode) {
      return {}
    }

    const result: ResolvedImageSizingOptions = {
      sizing: {
        type: sizingMode,
        w: box.w,
        h: box.h,
      },
    }

    const intrinsicSize = await this.resolveIntrinsicImageSize(element, source)
    if (!intrinsicSize) {
      return result
    }

    const proxyBox = this.buildIntrinsicProxyBox(box, intrinsicSize)
    return {
      w: proxyBox.w,
      h: proxyBox.h,
      sizing: result.sizing,
    }
  }

  /**
   * 读取当前元素对应的 cover/contain 模式。
   * @param element 图片元素或背景图容器
   */
  private resolveImageSizingMode(element: Element): ImageSizingOptions['type'] | null {
    const image = element instanceof HTMLImageElement ? element : element.querySelector?.('img')
    if (image instanceof HTMLElement) {
      const style = window.getComputedStyle(image)
      if (style.objectFit === 'contain' || style.objectFit === 'cover') {
        return style.objectFit
      }
    }

    if (element instanceof HTMLElement) {
      const style = window.getComputedStyle(element)
      if (style.backgroundSize === 'contain' || style.backgroundSize === 'cover') {
        return style.backgroundSize
      }
    }

    return null
  }

  /**
   * 解析图片原始尺寸。
   * @param element 图片元素或背景图容器
   * @param source 图片源地址或 data URL
   */
  private async resolveIntrinsicImageSize(element: Element, source?: string): Promise<IntrinsicImageSize | null> {
    const image = element instanceof HTMLImageElement ? element : element.querySelector?.('img')
    if (image instanceof HTMLImageElement && image.naturalWidth > 0 && image.naturalHeight > 0) {
      return {
        width: image.naturalWidth,
        height: image.naturalHeight,
      }
    }

    if (!source) {
      return null
    }

    if (/^data:image\//i.test(source)) {
      return this.parseIntrinsicSizeFromDataUrl(source)
    }

    return this.loadImageSizeFromSource(source)
  }

  /**
   * 从 data URL 中直接解析图片尺寸，避免测试环境或跨域场景依赖 Image.onload。
   * @param source data URL
   */
  private parseIntrinsicSizeFromDataUrl(source: string): IntrinsicImageSize | null {
    const match = /^data:image\/([^;]+);base64,(.+)$/i.exec(source)
    if (!match) {
      return null
    }

    const subtype = String(match[1] || '').toLowerCase()
    const base64 = match[2] || ''
    const binary = (() => {
      try {
        return window.atob(base64)
      } catch {
        return ''
      }
    })()
    if (!binary) {
      return null
    }

    const bytes = Uint8Array.from(binary, char => char.charCodeAt(0))
    if (subtype === 'png') {
      return this.parsePngSize(bytes)
    }
    if (subtype === 'gif') {
      return this.parseGifSize(bytes)
    }
    if (subtype === 'jpeg' || subtype === 'jpg') {
      return this.parseJpegSize(bytes)
    }
    if (subtype === 'svg+xml') {
      return this.parseSvgSize(binary)
    }

    return null
  }

  /**
   * 使用脱离 DOM 的 Image 读取图片尺寸。
   * @param source 图片源地址或 data URL
   */
  private async loadImageSizeFromSource(source: string): Promise<IntrinsicImageSize | null> {
    return new Promise(resolve => {
      const image = new Image()
      const cleanup = () => {
        image.removeEventListener('load', handleLoad)
        image.removeEventListener('error', handleError)
      }
      const handleLoad = () => {
        cleanup()
        if (image.naturalWidth > 0 && image.naturalHeight > 0) {
          resolve({
            width: image.naturalWidth,
            height: image.naturalHeight,
          })
          return
        }
        resolve(null)
      }
      const handleError = () => {
        cleanup()
        resolve(null)
      }

      image.addEventListener('load', handleLoad, { once: true })
      image.addEventListener('error', handleError, { once: true })
      image.src = source

      if (image.complete && image.naturalWidth > 0 && image.naturalHeight > 0) {
        handleLoad()
      }
    })
  }

  /**
   * 解析 PNG IHDR 中的原始尺寸。
   * @param bytes PNG 字节
   */
  private parsePngSize(bytes: Uint8Array): IntrinsicImageSize | null {
    if (bytes.length < 24) {
      return null
    }

    const width = this.readUint32(bytes, 16)
    const height = this.readUint32(bytes, 20)
    if (width <= 0 || height <= 0) {
      return null
    }

    return { width, height }
  }

  /**
   * 解析 GIF 逻辑屏幕尺寸。
   * @param bytes GIF 字节
   */
  private parseGifSize(bytes: Uint8Array): IntrinsicImageSize | null {
    if (bytes.length < 10) {
      return null
    }

    const width = bytes[6] | (bytes[7] << 8)
    const height = bytes[8] | (bytes[9] << 8)
    if (width <= 0 || height <= 0) {
      return null
    }

    return { width, height }
  }

  /**
   * 解析 JPEG 首个 SOF 段中的原始尺寸。
   * @param bytes JPEG 字节
   */
  private parseJpegSize(bytes: Uint8Array): IntrinsicImageSize | null {
    if (bytes.length < 4 || bytes[0] !== 0xFF || bytes[1] !== 0xD8) {
      return null
    }

    let offset = 2
    while (offset + 8 < bytes.length) {
      if (bytes[offset] !== 0xFF) {
        offset += 1
        continue
      }

      const marker = bytes[offset + 1]
      offset += 2
      if (marker === 0xD8 || marker === 0xD9) {
        continue
      }

      if (offset + 2 > bytes.length) {
        return null
      }
      const segmentLength = (bytes[offset] << 8) | bytes[offset + 1]
      if (segmentLength < 2 || offset + segmentLength > bytes.length) {
        return null
      }

      if (
        (marker >= 0xC0 && marker <= 0xC3) ||
        (marker >= 0xC5 && marker <= 0xC7) ||
        (marker >= 0xC9 && marker <= 0xCB) ||
        (marker >= 0xCD && marker <= 0xCF)
      ) {
        if (offset + 7 > bytes.length) {
          return null
        }
        const height = (bytes[offset + 3] << 8) | bytes[offset + 4]
        const width = (bytes[offset + 5] << 8) | bytes[offset + 6]
        if (width <= 0 || height <= 0) {
          return null
        }
        return { width, height }
      }

      offset += segmentLength
    }

    return null
  }

  /**
   * 解析 SVG 文本中的宽高或 viewBox。
   * @param source SVG 文本
   */
  private parseSvgSize(source: string): IntrinsicImageSize | null {
    const normalized = String(source || '')
    const widthMatch = /\bwidth=["']([\d.]+)(?:px)?["']/i.exec(normalized)
    const heightMatch = /\bheight=["']([\d.]+)(?:px)?["']/i.exec(normalized)
    const width = widthMatch ? Number.parseFloat(widthMatch[1]) : 0
    const height = heightMatch ? Number.parseFloat(heightMatch[1]) : 0
    if (width > 0 && height > 0) {
      return { width, height }
    }

    const viewBoxMatch = /\bviewBox=["'][^"']*?([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)[^"']*["']/i.exec(normalized)
    if (!viewBoxMatch) {
      return null
    }

    const viewBoxWidth = Number.parseFloat(viewBoxMatch[3] || '0')
    const viewBoxHeight = Number.parseFloat(viewBoxMatch[4] || '0')
    if (viewBoxWidth <= 0 || viewBoxHeight <= 0) {
      return null
    }

    return {
      width: viewBoxWidth,
      height: viewBoxHeight,
    }
  }

  /**
   * 读取大端 32 位无符号整数。
   * @param bytes 原始字节
   * @param offset 起始偏移
   */
  private readUint32(bytes: Uint8Array, offset: number): number {
    return (
      (bytes[offset] << 24) |
      (bytes[offset + 1] << 16) |
      (bytes[offset + 2] << 8) |
      bytes[offset + 3]
    ) >>> 0
  }

  /**
   * 按原图比例构造给 pptxgenjs 的代理尺寸。
   * 说明：pptxgenjs 4.0.1 会把顶层 w/h 当作原图尺寸参与 cover/contain 计算，
   * 若直接传目标盒子尺寸，会得到零裁剪并表现为拉伸。
   * @param box 元素在 slide 中的最终目标尺寸
   * @param intrinsicSize 图片原始尺寸
   */
  private buildIntrinsicProxyBox(box: ElementBox, intrinsicSize: IntrinsicImageSize): Pick<ElementBox, 'w' | 'h'> {
    const width = Number(intrinsicSize.width)
    const height = Number(intrinsicSize.height)
    if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
      return { w: box.w, h: box.h }
    }

    const sourceRatio = height / width
    const boxRatio = box.h / box.w
    if (!Number.isFinite(sourceRatio) || sourceRatio <= 0 || !Number.isFinite(boxRatio) || boxRatio <= 0) {
      return { w: box.w, h: box.h }
    }

    if (sourceRatio >= boxRatio) {
      return {
        w: Math.max(0.01, box.h / sourceRatio),
        h: box.h,
      }
    }

    return {
      w: box.w,
      h: Math.max(0.01, box.w * sourceRatio),
    }
  }

  /**
   * 从 CSS background-image 中提取单个 url。
   * @param value background-image 值
   */
  private extractSingleBackgroundImageUrl(value: string): string {
    const normalized = String(value || '').trim()
    if (!normalized || normalized === 'none' || normalized.includes('gradient(')) {
      return ''
    }

    const match = /^url\(\s*(?:"([^"]+)"|'([^']+)'|([^'")]+))\s*\)$/i.exec(normalized)
    if (!match) {
      return ''
    }

    return (match[1] || match[2] || match[3] || '').trim()
  }

  /**
   * 查找元素内可序列化的 SVG。
   * @param element 源元素
   */
  private findRenderableSvg(element: Element): SVGSVGElement | null {
    if (element instanceof SVGSVGElement) {
      return element
    }
    return element.querySelector?.('svg') as SVGSVGElement | null
  }

  /**
   * 查找元素内全部可序列化 SVG。
   * @param element 源元素
   */
  private findRenderableSvgs(element: Element): SVGSVGElement[] {
    if (element instanceof SVGSVGElement) {
      return [element]
    }
    return Array.from(element.querySelectorAll?.('svg') ?? [])
      .filter((svg): svg is SVGSVGElement => svg instanceof SVGSVGElement)
  }

  /**
   * 当 SVG 含 PowerPoint 不兼容结构时，优先降级为局部截图，避免图形保留但文字丢失。
   * @param host 导出宿主能力
   * @param element 源元素
   * @param svg 当前命中的 SVG 元素
   * @param sourceType 源类型
   * @param context 当前组合上下文
   * @param reason 降级原因
   * @returns 是否已完成降级导出
   */
  private async addUnsupportedSvgScreenshot(
    host: PptxDomMediaExportHost,
    element: Element,
    svg: SVGSVGElement,
    sourceType: PptxReportSourceType,
    context: VisitContext,
    reason: string,
  ): Promise<boolean> {
    if (!this.svgSerializer.shouldRasterizeForPpt(svg)) {
      return false
    }

    const screenshotTarget = this.resolveScreenshotTarget(element)
    if (!screenshotTarget) {
      return false
    }

    await this.addScreenshotBlock(host, screenshotTarget, sourceType, reason, context)
    return true
  }

  /**
   * 为局部截图选择稳定的 HTML 宿主。
   * @param element 当前导出源元素
   * @returns 可供截图的 HTML 元素；不存在时返回 null
   */
  private resolveScreenshotTarget(element: Element): HTMLElement | null {
    if (element instanceof HTMLElement) {
      return element
    }
    return element.parentElement instanceof HTMLElement ? element.parentElement : null
  }

  /**
   * 为 SVG 类资源选择最终的 PPT 定位参考元素。
   * 说明：LaTeX viewer 外层容器通常比公式本体宽很多，若直接按容器盒子落 PPT，
   * PowerPoint 会把公式拉伸到容器大小；这里改为按实际 MathJax SVG 的渲染盒子定位。
   * @param sourceType 源类型
   * @param element 原始媒体元素
   * @param svg 当前命中的 SVG
   * @returns 应作为 PPT 位置尺寸基准的元素
   */
  private resolveSvgPlacementElement(
    sourceType: PptxReportSourceType,
    element: Element,
    svg: SVGSVGElement,
  ): Element {
    if (sourceType === 'formula') {
      return svg
    }
    return element
  }

  /**
   * 解析 SVG 的导出载荷；特殊组件可在这里改用更稳定的视口和定位参考元素。
   * @param svg 当前命中的 SVG
   * @param boxElement 默认定位参考元素
   * @returns 导出 data URL 与定位参考元素
   */
  private resolveSvgExportPayload(svg: SVGSVGElement, boxElement: Element): ResolvedSvgExportPayload {
    const connectorPayload = this.buildConnectorSvgExportPayload(svg)
    if (connectorPayload) {
      return connectorPayload
    }

    return {
      data: this.svgSerializer.svgToDataUrl(svg),
      boxElement,
    }
  }

  /**
   * 为 Connector 组件构造紧边界 SVG，避免把整块父容器带入 PPT 导致偏移和裁剪。
   * @param svg Connector 根 SVG
   * @returns 紧边界 SVG 导出信息；不满足条件时返回 null
   */
  private buildConnectorSvgExportPayload(svg: SVGSVGElement): ResolvedSvgExportPayload | null {
    if (!svg.classList.contains('connector-svg')) {
      return null
    }

    const path = this.findConnectorRenderablePath(svg)
    if (!path) {
      return null
    }

    const viewBox = this.resolveConnectorViewBox(svg, path)
    if (!viewBox) {
      return null
    }
    const viewportElement = svg.parentElement instanceof HTMLElement ? svg.parentElement : svg
    const boxOverride = this.resolveSvgViewBoxPptxBox(svg, viewBox, viewportElement)
    if (!boxOverride) {
      return null
    }

    return {
      data: this.svgSerializer.svgToDataUrl(svg, {
        measured: {
          width: viewBox.width,
          height: viewBox.height,
        },
        viewBox,
        removeResponsiveSizing: true,
      }),
      boxElement: viewportElement,
      boxOverride,
    }
  }

  /**
   * 查找 Connector 中真正可见的连线路径，跳过 defs 里的箭头 marker 图形。
   * @param svg Connector 根 SVG
   * @returns 实际渲染在线条上的 path；未找到时返回 null
   */
  private findConnectorRenderablePath(svg: SVGSVGElement): SVGPathElement | null {
    const candidates = Array.from(svg.querySelectorAll('path'))
    return candidates.find((path) => {
      if (!(path instanceof SVGElement) || path.closest('defs')) {
        return false
      }

      const d = (path.getAttribute('d') || '').trim()
      if (!d) {
        return false
      }

      const stroke = path.getAttribute('stroke') || window.getComputedStyle(path).stroke || ''
      return stroke !== '' && stroke !== 'none'
    }) ?? null
  }

  /**
   * 解析 Connector 的紧边界视口。
   * 说明：优先使用路径几何坐标和线宽/箭头留白，避免竖线或横线在 DOMRect 中退化为 0 宽/0 高；
   * 若宿主环境不支持 getBBox，再退回到页面实际渲染矩形。
   * @param svg Connector 根 SVG
   * @param path 实际连线路径
   * @returns 供 SVG 序列化使用的紧边界 viewBox；不可用时返回 null
   */
  private resolveConnectorViewBox(svg: SVGSVGElement, path: SVGPathElement): { x: number; y: number; width: number; height: number } | null {
    const geometryViewBox = this.resolveConnectorGeometryViewBox(path)
    if (geometryViewBox) {
      return geometryViewBox
    }

    return this.resolveRenderedConnectorViewBox(svg, path)
  }

  /**
   * 根据 SVG 几何坐标计算 Connector 的导出视口，并为线宽与箭头预留留白。
   * @param path 实际连线路径
   * @returns 几何视口；不可用时返回 null
   */
  private resolveConnectorGeometryViewBox(path: SVGPathElement): { x: number; y: number; width: number; height: number } | null {
    const getBBox = (path as SVGPathElement & { getBBox?: () => DOMRect | SVGRect }).getBBox
    if (typeof getBBox !== 'function') {
      return null
    }

    let geometryBox: DOMRect | SVGRect
    try {
      geometryBox = getBBox.call(path)
    } catch {
      return null
    }

    const padding = this.resolveConnectorSvgPadding(path)
    const width = geometryBox.width + padding * 2
    const height = geometryBox.height + padding * 2
    if (width <= 0 || height <= 0) {
      return null
    }

    return {
      x: geometryBox.x - padding,
      y: geometryBox.y - padding,
      width,
      height,
    }
  }

  /**
   * 根据页面渲染矩形回退计算 Connector 的导出视口。
   * @param svg Connector 根 SVG
   * @param path 实际连线路径
   * @returns 渲染视口；不可用时返回 null
   */
  private resolveRenderedConnectorViewBox(svg: SVGSVGElement, path: SVGPathElement): { x: number; y: number; width: number; height: number } | null {
    const svgRect = svg.getBoundingClientRect()
    const pathRect = path.getBoundingClientRect()

    if (svgRect.width <= 0 || svgRect.height <= 0 || pathRect.width <= 0 || pathRect.height <= 0) {
      return null
    }

    return {
      x: pathRect.left - svgRect.left,
      y: pathRect.top - svgRect.top,
      width: pathRect.width,
      height: pathRect.height,
    }
  }

  /**
   * 估算 Connector 导出所需的额外留白，覆盖线宽、圆头和箭头 marker。
   * @param path Connector 路径元素
   * @returns 视口额外留白，单位与 SVG 用户坐标一致
   */
  private resolveConnectorSvgPadding(path: SVGPathElement): number {
    const strokeWidth = Number.parseFloat(
      path.getAttribute('stroke-width')
      || window.getComputedStyle(path).strokeWidth
      || '0',
    )
    const normalizedStrokeWidth = Number.isFinite(strokeWidth) && strokeWidth > 0 ? strokeWidth : 1
    const hasMarker = Boolean(path.getAttribute('marker-start') || path.getAttribute('marker-end'))
    return normalizedStrokeWidth * (hasMarker ? 6 : 2)
  }

  /**
   * 将 SVG 内部视口矩形换算为 PPTX 绝对位置尺寸。
   * @param svg 原始 SVG 根节点
   * @param viewBox 需要导出的内部视口
   * @returns PPTX 盒模型；不可用时返回 null
   */
  private resolveSvgViewBoxPptxBox(
    svg: SVGSVGElement,
    viewBox: { x: number; y: number; width: number; height: number },
    viewportElement: Element,
  ): ElementBox | null {
    const viewportBox = this.layout.getPptxBox(viewportElement)
    const viewportPixels = this.layout.measureElementPixels(viewportElement)
    if (!viewportBox || viewportPixels.width <= 0 || viewportPixels.height <= 0) {
      return null
    }

    const viewportSize = this.resolveSvgViewportSize(svg, viewportElement, viewportPixels)
    if (!viewportSize || viewportSize.width <= 0 || viewportSize.height <= 0) {
      return null
    }

    const scaleX = viewportBox.w / viewportSize.width
    const scaleY = viewportBox.h / viewportSize.height
    const x = viewportBox.x + viewBox.x * scaleX
    const y = viewportBox.y + viewBox.y * scaleY
    const w = viewBox.width * scaleX
    const h = viewBox.height * scaleY

    return {
      x: this.layout.roundInch(Math.max(0, x)),
      y: this.layout.roundInch(Math.max(0, y)),
      w: this.layout.roundInch(Math.max(0.01, w)),
      h: this.layout.roundInch(Math.max(0.01, h)),
    }
  }

  /**
   * 解析 SVG 当前使用的坐标视口尺寸。
   * @param svg SVG 根节点
   * @param measured 当前页面中的渲染尺寸
   * @returns SVG 用户坐标系下的宽高
   */
  private resolveSvgViewportSize(
    svg: SVGSVGElement,
    viewportElement: Element,
    measured: { width: number; height: number },
  ): { width: number; height: number } | null {
    const liveViewBox = svg.viewBox?.baseVal
    if (liveViewBox && liveViewBox.width > 0 && liveViewBox.height > 0) {
      return {
        width: liveViewBox.width,
        height: liveViewBox.height,
      }
    }

    const rawViewBox = svg.getAttribute('viewBox')
    if (rawViewBox) {
      const values = rawViewBox
        .trim()
        .split(/[\s,]+/)
        .map(value => Number.parseFloat(value))
      if (values.length === 4 && values.every(value => Number.isFinite(value)) && values[2] > 0 && values[3] > 0) {
        return {
          width: values[2],
          height: values[3],
        }
      }
    }

    const layoutSize = this.resolveElementLayoutSize(viewportElement)
    if (layoutSize) {
      return layoutSize
    }

    if (measured.width > 0 && measured.height > 0) {
      return {
        width: measured.width,
        height: measured.height,
      }
    }

    return null
  }

  /**
   * 读取元素未受 transform 缩放影响的布局尺寸。
   * 说明：Connector 的 path 坐标由 offsetLeft/offsetWidth 生成，属于布局坐标；
   * 页面预览缩放后 getBoundingClientRect 会变小，不能作为 SVG 内部坐标分母。
   * @param element SVG 视口对应的页面元素
   * @returns 布局尺寸；不可用时返回 null
   */
  private resolveElementLayoutSize(element: Element): { width: number; height: number } | null {
    if (element instanceof HTMLElement) {
      const style = window.getComputedStyle(element)
      const width = this.firstPositiveNumber(
        this.layout.parseCssPixel(style.width),
        element.offsetWidth,
        element.clientWidth,
      )
      const height = this.firstPositiveNumber(
        this.layout.parseCssPixel(style.height),
        element.offsetHeight,
        element.clientHeight,
      )
      if (width > 0 && height > 0) {
        return { width, height }
      }
    }

    const style = window.getComputedStyle(element)
    const width = this.firstPositiveNumber(
      this.layout.parseCssPixel(style.width),
      Number.parseFloat(element.getAttribute('width') || ''),
    )
    const height = this.firstPositiveNumber(
      this.layout.parseCssPixel(style.height),
      Number.parseFloat(element.getAttribute('height') || ''),
    )
    return width > 0 && height > 0 ? { width, height } : null
  }

  /**
   * 从候选值中选择第一个正数。
   * @param values 候选数字
   */
  private firstPositiveNumber(...values: number[]): number {
    return values.find(value => Number.isFinite(value) && value > 0) ?? 0
  }

  /**
   * 解析媒体源类型。
   * @param element 源元素
   */
  private resolveMediaSourceType(element: Element): PptxReportSourceType {
    if (element.matches('.mermaid-viewer')) return 'mermaid'
    if (element.matches('.drawio-viewer')) return 'drawio'
    if (element.matches('.latex-viewer')) return 'formula'
    if (element.matches('.echarts-viewer')) return 'chart'
    if (element.matches('.video-viewer') || element.tagName.toLowerCase() === 'video') return 'video'
    if (element.tagName.toLowerCase() === 'canvas') return 'canvas'
    if (element.tagName.toLowerCase() === 'svg') return 'svg'
    if (element.matches('.image-viewer') || element.tagName.toLowerCase() === 'img') return 'image'
    return 'unknown'
  }
}
