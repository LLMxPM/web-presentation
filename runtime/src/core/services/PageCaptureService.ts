/**
 * 页面捕获服务
 * 负责捕获页面内容并转换为Canvas
 */

import { snapdom } from '@zumer/snapdom'
import type { CaptureOptions } from '@/core/types/pdf-export'
import { waitForPageLoad, waitForImages, getPageDimensions } from '../utils/dom'
import { optimizeCanvas } from '../utils/file'
import { appPageConfig } from '@/core/utils/config'
import { createRuntimePageCaptureTarget } from '@/core/utils/export-dom'
import { getRuntimePreloadedConfig, getRuntimePreviewContext } from '@/core/utils/path'
import { normalizeAssetKey } from '@/core/shared/runtime-preview'

type SnapdomCaptureResult = Awaited<ReturnType<typeof snapdom>>

interface ElementStyleSnapshot {
  position: string
  visibility: string
  opacity: string
  display: string
  transform: string
  transformOrigin: string
  width: string
  height: string
  padding: string
  margin: string
  boxShadow: string
  borderRadius: string
  overflow: string
  backgroundClip: string
  backgroundColor: string
}

export class PageCaptureService {
  private static instance: PageCaptureService
  private defaultOptions: CaptureOptions = {
    scale: 2,
    useCORS: true,
    allowTaint: false, // 先禁用allowTaint，避免污染画布
    backgroundColor: '#ffffff', // 使用白色背景，避免透明背景问题
    timeout: 15000
  }

  /**
   * 获取单例实例
   */
  static getInstance(): PageCaptureService {
    if (!PageCaptureService.instance) {
      PageCaptureService.instance = new PageCaptureService()
    }
    return PageCaptureService.instance
  }

  /**
   * 捕获指定元素
   * @param element 要捕获的HTML元素
   * @param options 捕获选项
   * @returns Promise<HTMLCanvasElement>
   */
  async captureElement(
    element: HTMLElement,
    options?: CaptureOptions
  ): Promise<HTMLCanvasElement> {
    const mergedOptions = { ...this.defaultOptions, ...options }

    // console.log('开始捕获元素:', element)
    // console.log('捕获选项:', mergedOptions)

    try {
      // 预处理元素以优化捕获效果
      const cleanup = this.preprocessElement(element)
      const cleanupResourceProxy = this.applyCaptureResourceProxy(element, mergedOptions.proxyUrl)

      try {
        // 等待页面加载完成
        await waitForPageLoad(5000)

        // 页面加载完成后额外等待 500ms，确保异步渲染或过渡动画结束
        await new Promise<void>(resolve => setTimeout(resolve, 500))

        // 始终等待图片加载完成，确保资源就绪
        await waitForImages(element)

        // 获取元素尺寸；jsdom 对离屏元素的 rect 可能为 0，因此同时读取 CSS 与 offset 尺寸
        const captureSize = this.measureElementForCapture(element)
        // console.log('元素尺寸:', captureSize)

        if (captureSize.width === 0 || captureSize.height === 0) {
          throw new Error(`元素尺寸无效: ${captureSize.width}x${captureSize.height}`)
        }

        // 使用 snapdom 捕获（支持 useProxy）
        const capPromise = snapdom(element, {
          scale: mergedOptions.scale ?? 2,
          backgroundColor: mergedOptions.backgroundColor,
          embedFonts: true,
          ...(mergedOptions.proxyUrl ? { useProxy: mergedOptions.proxyUrl } : {})
        })
        const timeout = mergedOptions.timeout ?? 15000
        const timedCap = new Promise<SnapdomCaptureResult>((resolve, reject) => {
          const timer = setTimeout(() => {
            reject(new Error(`捕获超时(${timeout}ms)`))
          }, timeout)
          capPromise.then(res => {
            clearTimeout(timer as unknown as number)
            resolve(res)
          }).catch(err => {
            clearTimeout(timer as unknown as number)
            reject(err)
          })
        })
        const result = await timedCap

        // 生成PNG图片元素
        const output = await result.toPng()

        // 规范化为 HTMLImageElement
        let img: HTMLImageElement = (output instanceof HTMLImageElement)
          ? output
          : (() => {
            const i = new Image()
            i.src = String(output)
            return i
          })()

        const ensureImageLoaded = async (image: HTMLImageElement): Promise<HTMLImageElement> => {
          await new Promise<void>((resolve, reject) => {
            if (image.complete && image.naturalWidth > 0) return resolve()
            const onLoad = () => {
              cleanupLoad()
              resolve()
            }
            const onError = () => {
              cleanupLoad()
              reject(new Error('图片解码失败'))
            }
            const cleanupLoad = () => {
              image.removeEventListener('load', onLoad)
              image.removeEventListener('error', onError)
            }
            image.addEventListener('load', onLoad, { once: true })
            image.addEventListener('error', onError, { once: true })
          })
          if (image.naturalWidth === 0 || image.naturalHeight === 0) {
            throw new Error('图片尺寸无效')
          }
          return image
        }

        let finalImg: HTMLImageElement = img
        try {
          finalImg = await ensureImageLoaded(img)
        } catch (e) {
          // 使用代理重试
          if (mergedOptions.proxyUrl) {
            const proxied = await snapdom(element, {
              scale: mergedOptions.scale ?? 2,
              backgroundColor: mergedOptions.backgroundColor,
              embedFonts: true,
              useProxy: mergedOptions.proxyUrl
            })
            const proxiedOutput = await proxied.toPng()
            img = (proxiedOutput instanceof HTMLImageElement) ? proxiedOutput : (() => {
              const i = new Image()
              i.src = String(proxiedOutput)
              return i
            })()
            finalImg = await ensureImageLoaded(img)
          } else {
            throw e
          }
        }

        // 基础画布：先用图片自然尺寸
        const baseCanvas = document.createElement('canvas')
        const baseCtx = baseCanvas.getContext('2d')
        if (!baseCtx) {
          throw new Error('无法创建Canvas上下文')
        }

        baseCanvas.width = finalImg.naturalWidth
        baseCanvas.height = finalImg.naturalHeight

        // 先填充背景色，避免透明背景问题
        if (mergedOptions.backgroundColor) {
          baseCtx.fillStyle = mergedOptions.backgroundColor
          baseCtx.fillRect(0, 0, baseCanvas.width, baseCanvas.height)
        }

        // 绘制图片到基础Canvas
        baseCtx.imageSmoothingEnabled = true
        baseCtx.imageSmoothingQuality = 'high'
        baseCtx.drawImage(finalImg, 0, 0)

        // 如果指定了目标宽/高，则按照目标尺寸生成最终Canvas
        let finalCanvas = baseCanvas
        const targetWidth = mergedOptions.width
        const targetHeight = mergedOptions.height

        if (targetWidth || targetHeight) {
          const aspect = baseCanvas.width / baseCanvas.height
          let outW = targetWidth ?? Math.round((targetHeight as number) * aspect)
          let outH = targetHeight ?? Math.round((targetWidth as number) / aspect)

          // 保护：避免0或NaN
          outW = Math.max(1, Math.round(outW))
          outH = Math.max(1, Math.round(outH))

          const resized = document.createElement('canvas')
          const rctx = resized.getContext('2d')
          if (rctx) {
            resized.width = outW
            resized.height = outH
            rctx.imageSmoothingEnabled = true
            rctx.imageSmoothingQuality = 'high'
            rctx.drawImage(baseCanvas, 0, 0, resized.width, resized.height)
            finalCanvas = resized
          }
        }

        // console.log('snapdom捕获完成，canvas尺寸:', finalCanvas.width, 'x', finalCanvas.height)

        // 检查canvas是否有效
        if (finalCanvas.width === 0 || finalCanvas.height === 0) {
          throw new Error(`生成的canvas尺寸无效: ${finalCanvas.width}x${finalCanvas.height}`)
        }

        // 检查canvas内容是否为空
        const checkCtx = finalCanvas.getContext('2d')
        if (checkCtx) {
          const imageData = checkCtx.getImageData(0, 0, Math.min(finalCanvas.width, 100), Math.min(finalCanvas.height, 100))
          const isEmpty = imageData.data.every((pixel, index) => {
            // 检查RGBA，如果所有像素都是透明的或者都是黑色，可能有问题
            if (index % 4 === 3) return true // 跳过alpha通道
            return pixel === 0
          })

          if (isEmpty) {
            console.warn('警告：捕获的canvas似乎是空的或全黑的')
          }
        }

        return finalCanvas
      } finally {
        // 清理预处理效果
        cleanupResourceProxy()
        cleanup()
      }
    } catch (error) {
      console.error('页面捕获失败:', error)
      console.error('元素信息:', {
        tagName: element.tagName,
        className: element.className,
        id: element.id,
        offsetWidth: element.offsetWidth,
        offsetHeight: element.offsetHeight
      })
      throw new Error(`页面捕获失败: ${error instanceof Error ? error.message : '未知错误'}`, { cause: error })
    }
  }

  /**
   * 捕获当前页面的主要内容区域
   * @param options 捕获选项
   * @returns Promise<HTMLCanvasElement>
   */
  async captureCurrentPage(options?: CaptureOptions): Promise<HTMLCanvasElement> {
    const runtimeTarget = createRuntimePageCaptureTarget({
      routePath: options?.routePath,
      width: appPageConfig.value.width,
      height: appPageConfig.value.height,
      backgroundColor: options?.backgroundColor ?? this.defaultOptions.backgroundColor,
    })

    if (runtimeTarget) {
      const captureOptions = { ...options }
      delete captureOptions.routePath

      try {
        return await this.captureElement(runtimeTarget.captureElement, captureOptions)
      } finally {
        runtimeTarget.cleanup()
      }
    }

    console.warn('未找到运行时页面源节点，将使用旧内容区域选择器兜底')

    // 查找主要内容区域，优先级更高
    const contentElement = this.findBestContentElement()
    if (!contentElement) {
      throw new Error('未找到页面内容区域')
    }

    return this.captureElement(contentElement, options)
  }



  /**
   * 获取页面尺寸
   * @returns 页面尺寸对象
   */
  getPageDimensions(): { width: number; height: number } {
    return getPageDimensions()
  }



  /**
   * 预处理页面元素以优化捕获效果
   * @param element 要处理的元素
   * @returns 清理函数
   */
  private preprocessElement(element: HTMLElement): () => void {
    const cleanupFunctions: Array<() => void> = []

    // console.log('开始预处理元素:', element.tagName, element.className)

    // 1. 确保元素可见
    const originalStyle = this.captureElementStyleSnapshot(element)

    // 强制显示元素
    if (window.getComputedStyle(element).display === 'none') {
      element.style.display = 'block'
    }
    if (window.getComputedStyle(element).visibility === 'hidden') {
      element.style.visibility = 'visible'
    }
    if (window.getComputedStyle(element).opacity === '0') {
      element.style.opacity = '1'
    }

    cleanupFunctions.push(() => {
      Object.assign(element.style, originalStyle)
    })

    // 2. 处理懒加载图片
    const lazyImages = element.querySelectorAll('img[data-src], img[loading="lazy"]')
    // console.log('找到懒加载图片数量:', lazyImages.length)

    lazyImages.forEach(img => {
      const imgElement = img as HTMLImageElement
      const dataSrc = imgElement.getAttribute('data-src')
      if (dataSrc && !imgElement.src) {
        // console.log('加载懒加载图片:', dataSrc)
        imgElement.src = dataSrc
      }
      imgElement.removeAttribute('loading')
    })

    // 3. 等待字体加载
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(() => {
        // console.log('所有字体已加载完成')
      })
    }

    // 4. 全幅捕获（移除装饰性的边距与阴影）
    try {
      const isRuntimePageSource = element.classList.contains('runtime-page-print-source')
      const isExportSandbox = element.classList.contains('runtime-export-capture-sandbox')
      const isLikelyPageContent = !isRuntimePageSource &&
        !isExportSandbox &&
        (element.classList.contains('page-content') ||
          element.classList.contains('page-content-wrapper') ||
          element.classList.contains('fixed-ratio-container'))
      if (isLikelyPageContent) {
        // 记录直接子元素的样式（路由视图容器）
        const child = element.firstElementChild as HTMLElement | null
        const childOriginal = child ? this.captureElementStyleSnapshot(child) : null

        // 去除容器和其子元素的装饰确保无边距
        element.style.padding = '0'
        element.style.margin = '0'
        element.style.boxShadow = 'none'
        element.style.borderRadius = '0'
        element.style.overflow = 'hidden'
        element.style.backgroundClip = 'border-box'

        if (child) {
          child.style.padding = '0'
          child.style.margin = '0'
          child.style.boxShadow = 'none'
          child.style.borderRadius = '0'
          child.style.overflow = 'hidden'
        }

        cleanupFunctions.push(() => {
          if (child && childOriginal) {
            Object.assign(child.style, childOriginal)
          }
        })
      }
    } catch (e) {
      console.warn('应用全幅捕获样式时出错:', e)
    }

    // 返回统一的清理函数
    return () => {
      cleanupFunctions.forEach(cleanup => {
        try {
          cleanup()
        } catch (error) {
          console.warn('清理预处理效果时出错:', error)
        }
      })
    }
  }

  /**
   * 获取用于截图校验的元素尺寸。
   * @param element 目标元素
   * @returns 有效宽高，优先使用浏览器布局尺寸
   */
  private measureElementForCapture(element: HTMLElement): { width: number; height: number } {
    const rect = element.getBoundingClientRect()
    const style = window.getComputedStyle(element)
    const width = rect.width || element.offsetWidth || Number.parseFloat(style.width) || 0
    const height = rect.height || element.offsetHeight || Number.parseFloat(style.height) || 0

    return {
      width: Math.max(0, width),
      height: Math.max(0, height),
    }
  }

  /**
   * 记录元素内联样式快照，便于截图后恢复原始状态。
   * @param element 目标元素
   * @returns 当前内联样式值
   */
  private captureElementStyleSnapshot(element: HTMLElement): ElementStyleSnapshot {
    return {
      position: element.style.position,
      visibility: element.style.visibility,
      opacity: element.style.opacity,
      display: element.style.display,
      transform: element.style.transform,
      transformOrigin: element.style.transformOrigin,
      width: element.style.width,
      height: element.style.height,
      padding: element.style.padding,
      margin: element.style.margin,
      boxShadow: element.style.boxShadow,
      borderRadius: element.style.borderRadius,
      overflow: element.style.overflow,
      backgroundClip: element.style.backgroundClip,
      backgroundColor: element.style.backgroundColor,
    }
  }

  /**
   * 将截图沙箱中的工作空间资源 URL 改写为 Runtime 同源代理。
   * @param element 目标元素
   * @param proxyUrl snapDOM 资源代理 URL
   * @returns 清理函数
   */
  private applyCaptureResourceProxy(element: HTMLElement, proxyUrl?: string): () => void {
    if (!proxyUrl) {
      return () => {}
    }

    const cleanupFunctions: Array<() => void> = []
    this.proxyImageElementSources(element, proxyUrl, cleanupFunctions)
    this.proxyCssImageSources(element, proxyUrl, cleanupFunctions)

    return () => {
      cleanupFunctions.forEach(cleanup => {
        try {
          cleanup()
        } catch (error) {
          console.warn('恢复截图资源代理改写失败:', error)
        }
      })
    }
  }

  /**
   * 改写 img / source / SVG image 的资源地址。
   * @param root 查询根节点
   * @param proxyUrl 代理 URL
   * @param cleanupFunctions 清理函数集合
   */
  private proxyImageElementSources(
    root: HTMLElement,
    proxyUrl: string,
    cleanupFunctions: Array<() => void>,
  ): void {
    const imageElements = [
      ...Array.from(root.querySelectorAll<HTMLImageElement | HTMLSourceElement>('img, source')),
      ...(root.matches('img, source') ? [root as HTMLImageElement | HTMLSourceElement] : []),
    ]
    imageElements.forEach(image => {
      const originalSrc = image.getAttribute('src')
      const originalSrcset = image.getAttribute('srcset')
      const nextSrc = originalSrc ? this.buildCaptureProxyUrl(originalSrc, proxyUrl) : ''
      const nextSrcset = originalSrcset ? this.rewriteSrcsetUrls(originalSrcset, proxyUrl) : ''

      if (nextSrc || nextSrcset) {
        cleanupFunctions.push(() => {
          this.restoreAttribute(image, 'src', originalSrc)
          this.restoreAttribute(image, 'srcset', originalSrcset)
        })
      }
      if (nextSrc) {
        image.setAttribute('src', nextSrc)
      }
      if (nextSrcset) {
        image.setAttribute('srcset', nextSrcset)
      }
    })

    const svgImages = Array.from(root.querySelectorAll<SVGImageElement>('image'))
    svgImages.forEach(image => {
      const originalHref = image.getAttribute('href')
      const originalXlinkHref = image.getAttribute('xlink:href')
      const nextHref = originalHref ? this.buildCaptureProxyUrl(originalHref, proxyUrl) : ''
      const nextXlinkHref = originalXlinkHref ? this.buildCaptureProxyUrl(originalXlinkHref, proxyUrl) : ''

      if (nextHref || nextXlinkHref) {
        cleanupFunctions.push(() => {
          this.restoreAttribute(image, 'href', originalHref)
          this.restoreAttribute(image, 'xlink:href', originalXlinkHref)
        })
      }
      if (nextHref) {
        image.setAttribute('href', nextHref)
      }
      if (nextXlinkHref) {
        image.setAttribute('xlink:href', nextXlinkHref)
      }
    })
  }

  /**
   * 改写背景图和 mask 相关 CSS URL。
   * @param root 查询根节点
   * @param proxyUrl 代理 URL
   * @param cleanupFunctions 清理函数集合
   */
  private proxyCssImageSources(
    root: HTMLElement,
    proxyUrl: string,
    cleanupFunctions: Array<() => void>,
  ): void {
    const elements = [root, ...Array.from(root.querySelectorAll<HTMLElement>('*'))]
    const properties = [
      'background-image',
      'border-image-source',
      'list-style-image',
      'mask-image',
      '-webkit-mask-image',
    ]

    elements.forEach(item => {
      const computedStyle = window.getComputedStyle(item)
      const originalInlineValues = new Map<string, string>()
      let changed = false

      properties.forEach(property => {
        const cssValue = computedStyle.getPropertyValue(property)
        const rewrittenValue = this.rewriteCssUrlValue(cssValue, proxyUrl)
        if (!rewrittenValue || rewrittenValue === cssValue) {
          return
        }

        originalInlineValues.set(property, item.style.getPropertyValue(property))
        item.style.setProperty(property, rewrittenValue)
        changed = true
      })

      if (changed) {
        cleanupFunctions.push(() => {
          originalInlineValues.forEach((value, property) => {
            if (value) {
              item.style.setProperty(property, value)
            } else {
              item.style.removeProperty(property)
            }
          })
        })
      }
    })
  }

  /**
   * 改写 srcset 中的资源 URL。
   * @param srcset 原始 srcset
   * @param proxyUrl 代理 URL
   */
  private rewriteSrcsetUrls(srcset: string, proxyUrl: string): string {
    return srcset
      .split(',')
      .map(candidate => {
        const trimmedCandidate = candidate.trim()
        if (!trimmedCandidate) {
          return ''
        }
        const [rawUrl, ...descriptors] = trimmedCandidate.split(/\s+/)
        const proxiedUrl = this.buildCaptureProxyUrl(rawUrl, proxyUrl)
        return proxiedUrl ? [proxiedUrl, ...descriptors].join(' ') : trimmedCandidate
      })
      .filter(Boolean)
      .join(', ')
  }

  /**
   * 改写 CSS url(...) 中的资源 URL。
   * @param cssValue 原始 CSS 属性值
   * @param proxyUrl 代理 URL
   */
  private rewriteCssUrlValue(cssValue: string, proxyUrl: string): string {
    if (!cssValue || cssValue === 'none' || !cssValue.includes('url(')) {
      return cssValue
    }

    return cssValue.replace(/url\((?:"([^"]*)"|'([^']*)'|([^)]*))\)/g, (match, doubleQuoted, singleQuoted, unquoted) => {
      const rawUrl = String(doubleQuoted || singleQuoted || unquoted || '').trim()
      const proxiedUrl = this.buildCaptureProxyUrl(rawUrl, proxyUrl)
      return proxiedUrl ? `url("${proxiedUrl}")` : match
    })
  }

  /**
   * 为当前 artifact 声明的资源构造截图代理 URL。
   * @param rawUrl 原始资源 URL
   * @param proxyUrl 代理 URL
   */
  private buildCaptureProxyUrl(rawUrl: string, proxyUrl: string): string {
    const sourceUrl = this.normalizeCaptureResourceUrl(rawUrl)
    if (!sourceUrl || !this.isManifestAssetUrl(sourceUrl)) {
      return ''
    }

    try {
      const nextUrl = new URL(proxyUrl, window.location.href)
      nextUrl.searchParams.set('url', sourceUrl)
      return nextUrl.href
    } catch {
      return ''
    }
  }

  /**
   * 判断 URL 是否属于当前 manifest 声明的工作空间资源。
   * @param sourceUrl 绝对资源 URL
   */
  private isManifestAssetUrl(sourceUrl: string): boolean {
    const previewContext = getRuntimePreviewContext()
    const manifest = getRuntimePreloadedConfig()?.manifest
    if (!previewContext || !manifest) {
      return false
    }

    const normalizedSourceUrl = this.normalizeComparableUrl(sourceUrl)
    if (!normalizedSourceUrl) {
      return false
    }

    const allowedUrls = new Set<string>()
    const assetBaseUrls = [
      previewContext.assetBaseUrl,
      manifest.asset_base_url,
    ]
      .map(value => String(value || '').trim().replace(/\/+$/, ''))
      .filter((value, index, values) => value && values.indexOf(value) === index)

    Object.entries(manifest.assets || {}).forEach(([logicalName, mappedValue]) => {
      const normalizedMappedValue = String(mappedValue || '').trim()
      if (!normalizedMappedValue) {
        return
      }

      this.addComparableUrl(allowedUrls, normalizedMappedValue)

      const metadata = manifest.asset_metadata?.[logicalName] || manifest.asset_metadata?.[normalizeAssetKey(logicalName)]
      const fileHash = String(metadata?.file_hash || normalizedMappedValue || '').trim()
      if (!fileHash || /^https?:\/\//i.test(fileHash)) {
        return
      }

      assetBaseUrls.forEach(assetBaseUrl => {
        this.addComparableUrl(allowedUrls, this.joinAssetUrl(assetBaseUrl, fileHash, false))
        this.addComparableUrl(allowedUrls, this.joinAssetUrl(assetBaseUrl, fileHash, true))
      })
    })

    return allowedUrls.has(normalizedSourceUrl)
  }

  /**
   * 解析为绝对 http(s) URL。
   * @param rawUrl 原始资源 URL
   */
  private normalizeCaptureResourceUrl(rawUrl: string): string {
    const normalized = String(rawUrl || '').trim()
    if (!normalized || /^(data|blob|about|#):?/i.test(normalized)) {
      return ''
    }

    try {
      const url = new URL(normalized, window.location.href)
      return /^https?:$/i.test(url.protocol) ? url.href : ''
    } catch {
      return ''
    }
  }

  /**
   * 拼接资源基址和资源路径。
   * @param assetBaseUrl 资源基址
   * @param assetPath 资源路径或文件 hash
   * @param encodePath 是否编码路径
   */
  private joinAssetUrl(assetBaseUrl: string, assetPath: string, encodePath: boolean): string {
    const normalizedBaseUrl = String(assetBaseUrl || '').trim().replace(/\/+$/, '')
    const normalizedAssetPath = normalizeAssetKey(assetPath)
    if (!normalizedBaseUrl || !normalizedAssetPath) {
      return ''
    }
    return `${normalizedBaseUrl}/${encodePath ? encodeURIComponent(normalizedAssetPath) : normalizedAssetPath}`
  }

  /**
   * 添加可比较 URL。
   * @param target 目标集合
   * @param rawUrl 原始 URL
   */
  private addComparableUrl(target: Set<string>, rawUrl: string): void {
    const normalizedUrl = this.normalizeComparableUrl(rawUrl)
    if (normalizedUrl && /^https?:\/\//i.test(normalizedUrl)) {
      target.add(normalizedUrl)
    }
  }

  /**
   * 规范化 URL，便于与 manifest 派生 URL 精确比较。
   * @param rawUrl 原始 URL
   */
  private normalizeComparableUrl(rawUrl: string): string {
    try {
      return new URL(rawUrl, window.location.href).href
    } catch {
      return ''
    }
  }

  /**
   * 恢复属性值。
   * @param element 目标元素
   * @param name 属性名
   * @param value 原始值
   */
  private restoreAttribute(element: Element, name: string, value: string | null): void {
    if (value === null) {
      element.removeAttribute(name)
      return
    }
    element.setAttribute(name, value)
  }

  /**
   * 优化Canvas质量
   * @param canvas 原始canvas
   * @param quality 质量参数(0-1)
   * @returns 优化后的canvas
   */
  optimizeCanvas(canvas: HTMLCanvasElement, quality: number = 0.9): HTMLCanvasElement {
    return optimizeCanvas(canvas, quality)
  }

  /**
   * 清理资源
   */
  cleanup(): void {
    // 清理可能的内存泄漏
    // 这里可以添加清理逻辑
  }

  /**
   * 创建优化的Canvas元素
   * @param element 目标元素
   * @param scale 缩放比例
   * @returns 优化的Canvas元素
   */
  private createOptimizedCanvas(element: HTMLElement, scale: number): HTMLCanvasElement | undefined {
    try {
      const rect = element.getBoundingClientRect()
      const canvas = document.createElement('canvas')
      const ctx = canvas.getContext('2d')

      if (!ctx) return undefined

      // 设置高分辨率
      canvas.width = rect.width * scale
      canvas.height = rect.height * scale

      // 优化渲染设置
      ctx.imageSmoothingEnabled = true
      ctx.imageSmoothingQuality = 'high'

      return canvas
    } catch (error) {
      console.warn('创建优化Canvas失败:', error)
      return undefined
    }
  }

  /**
   * 查找最佳的内容区域
   * @returns HTMLElement | null
   */
  private findBestContentElement(): HTMLElement | null {
    // 扩展的查找选择器，按优先级排序
    const selectors = [
      '.page-content-wrapper .fixed-ratio-container',
      'main .fixed-ratio-container',
      '.fixed-ratio-container',
      '.page-content-wrapper',
      // Vue应用特定选择器
      '.page-content',
      '.main-content',
      '.content-wrapper',
      '.container',
      '.app-content',

      // 通用内容选择器
      '[data-content]',
      '[role="main"]',
      '.content',
      'main',

      // Vue应用结构
      '#app > div:first-child',
      '#app > .layout',
      '#app > main',
      '#app'
    ]

    for (const selector of selectors) {
      try {
        const element = document.querySelector(selector) as HTMLElement
        if (this.isValidContentElement(element)) {
          // 优先选择 .page-content 的直接子元素作为真实页面内容，避免容器装饰
          if (selector === '.page-content') {
            const child = element.firstElementChild as HTMLElement | null
            if (child && this.isValidContentElement(child)) {
              return child
            }
          }
          // console.log(`找到内容元素: ${selector}`)
          return element
        }
      } catch (error) {
        console.warn(`查找元素失败: ${selector}`, error)
      }
    }

    // 如果都没找到，使用body作为备选
    console.warn('未找到理想的内容元素，使用body')
    return document.body
  }

  /**
   * 验证元素是否为有效的内容元素
   * @param element 要验证的元素
   * @returns 是否有效
   */
  private isValidContentElement(element: HTMLElement | null): element is HTMLElement {
    if (!element) return false

    // 检查元素是否可见且有尺寸
    const rect = element.getBoundingClientRect()
    const computedStyle = window.getComputedStyle(element)

    const isVisible = (
      rect.width > 0 &&
      rect.height > 0 &&
      computedStyle.visibility !== 'hidden' &&
      computedStyle.display !== 'none' &&
      parseFloat(computedStyle.opacity) > 0
    )

    // 检查元素尺寸是否合理（至少100x100像素）
    const hasReasonableSize = rect.width >= 100 && rect.height >= 100

    return isVisible && hasReasonableSize
  }

  /**
   * 确保CSS变量和自定义属性可用
   * @param element 目标元素
   */
  private ensureCSSVariables(element: HTMLElement): void {
    void element
    try {
      // 获取所有CSS自定义属性
      const computedStyle = window.getComputedStyle(document.documentElement)
      const cssVariables: Record<string, string> = {}

      // 提取CSS变量
      for (let i = 0; i < computedStyle.length; i++) {
        const property = computedStyle[i]
        if (property.startsWith('--')) {
          cssVariables[property] = computedStyle.getPropertyValue(property)
        }
      }

      // 如果有CSS变量，确保它们可用
      if (Object.keys(cssVariables).length > 0) {
        // 创建一个临时样式表来确保CSS变量在捕获时可用
        const style = document.createElement('style')
        const cssText = `:root { ${Object.entries(cssVariables)
          .map(([key, value]) => `${key}: ${value}`)
          .join('; ')} }`
        style.textContent = cssText
        style.setAttribute('data-html2canvas-css-vars', 'true')

        document.head.appendChild(style)

        // 记录清理函数以便后续移除
        setTimeout(() => {
          if (style.parentNode) {
            style.parentNode.removeChild(style)
          }
        }, 1000)
      }

      // 处理Tailwind CSS类名确保样式正常加载
      this.ensureTailwindStyles()

    } catch (error) {
      console.warn('处理CSS变量时出错:', error)
    }
  }

  /**
   * 确保Tailwind CSS样式正常加载
   */
  private ensureTailwindStyles(): void {
    try {
      // 检查是否有Tailwind CSS
      const tailwindStylesheet = Array.from(document.styleSheets).find(sheet => {
        try {
          return sheet.href && (sheet.href.includes('tailwind') ||
            Array.from(sheet.cssRules || []).some(rule =>
              rule.cssText.includes('tailwind') ||
              rule.cssText.includes('tw-')
            ))
        } catch {
          return false
        }
      })

      if (tailwindStylesheet) {
        // console.log('Tailwind CSS样式表已找到，样式应该正常加载')
      }
    } catch (error) {
      console.warn('检查Tailwind CSS时出错:', error)
    }
  }
}

// 导出单例实例
export const pageCaptureService = PageCaptureService.getInstance()
