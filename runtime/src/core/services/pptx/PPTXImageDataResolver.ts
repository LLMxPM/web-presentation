/**
 * 文件用途：为 PPTX 图片导出读取远端资源、生成 data URL，并处理 Runtime 资源代理候选。
 */

import {
  buildRuntimeResourceProxyUrl,
  normalizeRuntimeHttpResourceUrl,
} from '@/core/utils/resource-proxy'

/**
 * PPTX 图片 data URL 解析器。
 */
export class PPTXImageDataResolver {
  /**
   * 将可读取的图片 URL 预先转为 data URL，避免 pptxgenjs 写文件阶段被跨域 URL 中断。
   * @param path 图片 URL
   */
  async resolve(path: string): Promise<string> {
    const normalizedPath = String(path || '').trim()
    if (!normalizedPath) {
      return ''
    }

    if (/^data:image\//i.test(normalizedPath)) {
      return normalizedPath
    }

    if (typeof fetch !== 'function') {
      return ''
    }

    const candidates = this.buildFetchCandidates(normalizedPath)
    for (const candidate of candidates) {
      const data = await this.fetchAsDataUrl(candidate)
      if (data) {
        return data
      }
    }

    return ''
  }

  /**
   * 判断图片路径是否不应延迟交给 pptxgenjs 读取。
   * @param path 图片路径
   */
  shouldAvoidDeferredPath(path: string): boolean {
    return /^https?:\/\//i.test(path) || /^blob:/i.test(path)
  }

  /**
   * 构造图片读取候选地址，manifest 资源优先走 Runtime 同源代理。
   * @param path 图片 URL
   */
  private buildFetchCandidates(path: string): string[] {
    const candidates: string[] = []
    const proxyUrl = buildRuntimeResourceProxyUrl(path)
    if (proxyUrl) {
      candidates.push(proxyUrl)
    }

    if (/^blob:/i.test(path)) {
      candidates.push(path)
    } else if (/^https?:\/\//i.test(path)) {
      const httpUrl = normalizeRuntimeHttpResourceUrl(path)
      if (httpUrl) {
        candidates.push(httpUrl)
      }
    }

    return candidates.filter((candidate, index, values) => candidate && values.indexOf(candidate) === index)
  }

  /**
   * 读取图片并转换为 PPTX 可嵌入的 data URL。
   * @param url 可 fetch 的图片地址
   */
  private async fetchAsDataUrl(url: string): Promise<string> {
    try {
      const response = await fetch(url)
      if (!response.ok) {
        return ''
      }

      const buffer = await response.arrayBuffer()
      const bytes = new Uint8Array(buffer)
      const contentType = this.resolveContentType(response.headers.get('content-type') || '', url, bytes)
      if (!contentType) {
        return ''
      }

      return `data:${contentType};base64,${this.arrayBufferToBase64(buffer)}`
    } catch {
      return ''
    }
  }

  /**
   * 解析图片内容类型，支持后端 hash URL 缺少文件扩展名的场景。
   * @param rawContentType 响应 Content-Type
   * @param url 图片 URL
   * @param bytes 图片字节
   */
  private resolveContentType(rawContentType: string, url: string, bytes: Uint8Array): string {
    const contentType = rawContentType.split(';')[0].trim().toLowerCase()
    if (contentType.startsWith('image/')) {
      return contentType
    }

    const pathname = (() => {
      try {
        return new URL(url, window.location.href).pathname.toLowerCase()
      } catch {
        return ''
      }
    })()
    if (pathname.endsWith('.svg')) return 'image/svg+xml'
    if (pathname.endsWith('.png')) return 'image/png'
    if (pathname.endsWith('.jpg') || pathname.endsWith('.jpeg')) return 'image/jpeg'
    if (pathname.endsWith('.webp')) return 'image/webp'
    if (pathname.endsWith('.gif')) return 'image/gif'
    if (pathname.endsWith('.avif')) return 'image/avif'

    if (this.hasPngSignature(bytes)) return 'image/png'
    if (this.hasJpegSignature(bytes)) return 'image/jpeg'
    if (this.hasGifSignature(bytes)) return 'image/gif'
    if (this.hasWebpSignature(bytes)) return 'image/webp'
    if (this.hasSvgSignature(bytes)) return 'image/svg+xml'

    return ''
  }

  /**
   * 将 ArrayBuffer 转为 base64。
   * @param buffer 原始字节
   */
  private arrayBufferToBase64(buffer: ArrayBuffer): string {
    const bytes = new Uint8Array(buffer)
    const chunkSize = 0x8000
    let binary = ''
    for (let index = 0; index < bytes.length; index += chunkSize) {
      const chunk = bytes.subarray(index, index + chunkSize)
      binary += String.fromCharCode(...chunk)
    }
    return window.btoa(binary)
  }

  /**
   * 判断 PNG 文件头。
   * @param bytes 图片字节
   */
  private hasPngSignature(bytes: Uint8Array): boolean {
    return bytes.length >= 8 &&
      bytes[0] === 0x89 &&
      bytes[1] === 0x50 &&
      bytes[2] === 0x4E &&
      bytes[3] === 0x47 &&
      bytes[4] === 0x0D &&
      bytes[5] === 0x0A &&
      bytes[6] === 0x1A &&
      bytes[7] === 0x0A
  }

  /**
   * 判断 JPEG 文件头。
   * @param bytes 图片字节
   */
  private hasJpegSignature(bytes: Uint8Array): boolean {
    return bytes.length >= 3 && bytes[0] === 0xFF && bytes[1] === 0xD8 && bytes[2] === 0xFF
  }

  /**
   * 判断 GIF 文件头。
   * @param bytes 图片字节
   */
  private hasGifSignature(bytes: Uint8Array): boolean {
    if (bytes.length < 6) {
      return false
    }
    const signature = String.fromCharCode(...bytes.subarray(0, 6))
    return signature === 'GIF87a' || signature === 'GIF89a'
  }

  /**
   * 判断 WebP 文件头。
   * @param bytes 图片字节
   */
  private hasWebpSignature(bytes: Uint8Array): boolean {
    if (bytes.length < 12) {
      return false
    }
    return String.fromCharCode(...bytes.subarray(0, 4)) === 'RIFF' &&
      String.fromCharCode(...bytes.subarray(8, 12)) === 'WEBP'
  }

  /**
   * 判断 SVG 文本文件头。
   * @param bytes 图片字节
   */
  private hasSvgSignature(bytes: Uint8Array): boolean {
    try {
      const source = new TextDecoder().decode(bytes.subarray(0, Math.min(bytes.length, 256))).trim()
      return /^<\?xml[\s\S]*<svg[\s>]/i.test(source) || /^<svg[\s>]/i.test(source)
    } catch {
      return false
    }
  }
}
