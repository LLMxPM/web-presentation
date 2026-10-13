/**
 * 文件用途：解析图片原始像素尺寸（支持 HTMLImageElement、Data URL 二进制魔数头与 SVG 视口），并计算 PptxGenJS cover/contain 代理盒尺寸。
 */

import { isHTMLImageElement } from '@/core/services/pptx/dom/PPTXDomEnvironment'

import type { ElementBox } from '@/core/services/pptx/PPTXDomConverter.types'

export interface IntrinsicImageSize {
  width: number
  height: number
}

/**
 * 解析图片元素的原始宽高，优先读取已加载 HTMLImageElement，回退解析 Data URL 二进制文件头或异步加载 Image。
 * @param element 图片元素或背景图容器
 * @param source 图片源地址或 Data URL
 * @returns 原始宽高，无法解析时返回 null
 */
export async function resolveIntrinsicImageSize(
  element: Element,
  source?: string,
): Promise<IntrinsicImageSize | null> {
  const image = isHTMLImageElement(element) ? element : element.querySelector?.('img')
  if (isHTMLImageElement(image) && image.naturalWidth > 0 && image.naturalHeight > 0) {
    return {
      width: image.naturalWidth,
      height: image.naturalHeight,
    }
  }

  if (!source) {
    return null
  }

  if (/^data:image\//i.test(source)) {
    return parseIntrinsicSizeFromDataUrl(source)
  }

  return loadImageSizeFromSource(source)
}

/**
 * 按原图比例构造给 PptxGenJS 的代理尺寸。
 * 说明：PptxGenJS 4.0.1 会把顶层 w/h 当作原图尺寸参与 cover/contain 计算，
 * 若直接传目标盒子尺寸，会得到零裁剪并表现为拉伸。
 * @param box 元素在 slide 中的最终目标尺寸
 * @param intrinsicSize 图片原始尺寸
 * @returns 按原图比例缩放后的代理宽高
 */
export function buildIntrinsicProxyBox(
  box: ElementBox,
  intrinsicSize: IntrinsicImageSize,
): Pick<ElementBox, 'w' | 'h'> {
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
 * 从 Data URL 中直接解析图片尺寸，避免测试环境或跨域场景依赖 Image.onload。
 * @param source Data URL 字符串
 * @returns 原始宽高，无法解析时返回 null
 */
export function parseIntrinsicSizeFromDataUrl(source: string): IntrinsicImageSize | null {
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
    return parsePngSize(bytes)
  }
  if (subtype === 'gif') {
    return parseGifSize(bytes)
  }
  if (subtype === 'jpeg' || subtype === 'jpg') {
    return parseJpegSize(bytes)
  }
  if (subtype === 'svg+xml') {
    return parseSvgSize(binary)
  }

  return null
}

/**
 * 使用脱离 DOM 的 Image 读取图片尺寸。
 * @param source 图片源地址或 Data URL
 * @returns 原始宽高，加载失败时返回 null
 */
async function loadImageSizeFromSource(source: string): Promise<IntrinsicImageSize | null> {
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
 * 解析 PNG IHDR 块中的原始尺寸。
 * @param bytes PNG 原始字节
 * @returns 原始宽高
 */
function parsePngSize(bytes: Uint8Array): IntrinsicImageSize | null {
  if (bytes.length < 24) {
    return null
  }

  const width = readUint32BigEndian(bytes, 16)
  const height = readUint32BigEndian(bytes, 20)
  if (width <= 0 || height <= 0) {
    return null
  }

  return { width, height }
}

/**
 * 解析 GIF 逻辑屏幕描述符中的尺寸。
 * @param bytes GIF 原始字节
 * @returns 原始宽高
 */
function parseGifSize(bytes: Uint8Array): IntrinsicImageSize | null {
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
 * @param bytes JPEG 原始字节
 * @returns 原始宽高
 */
function parseJpegSize(bytes: Uint8Array): IntrinsicImageSize | null {
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
 * 解析 SVG 文本中的宽高属性或 viewBox。
 * @param source SVG XML 文本
 * @returns 原始宽高
 */
function parseSvgSize(source: string): IntrinsicImageSize | null {
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
 * 读取大端序 32 位无符号整数。
 * @param bytes 字节数组
 * @param offset 起始偏移量
 * @returns 32 位无符号整数
 */
function readUint32BigEndian(bytes: Uint8Array, offset: number): number {
  return (
    (bytes[offset] << 24) |
    (bytes[offset + 1] << 16) |
    (bytes[offset + 2] << 8) |
    bytes[offset + 3]
  ) >>> 0
}
