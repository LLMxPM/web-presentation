/**
 * 文件用途：管理 PPTX 导出任务级资源缓存、并发请求复用、性能指标统计与脱敏诊断报告生成。
 */

import type {
  PptxExportReport,
  PptxExportResourceMetrics,
  PptxExportTimingMetrics,
} from '@/core/types/pptx-export'
import { PPTXImageDataResolver } from '@/core/services/pptx/PPTXImageDataResolver'
import { throwIfExportAborted } from '@/core/services/export/ExportCancellation'

export interface CachedResourceEntry {
  dataUrl: string
  byteLength: number
  contentType: string
}

/** 任务开始时固定画布和文件标题，后续路由或配置变化不能改变产物尺寸。 */
export interface PptxCanvasSnapshot {
  widthPx: number
  heightPx: number
  widthIn: number
  heightIn: number
  title: string
}

/**
 * 敏感 URL 查询参数键名匹配列表。
 */
const SENSITIVE_QUERY_KEYS = new Set([
  'token',
  'access_token',
  'api_key',
  'key',
  'secret',
  'signature',
  'sig',
  'auth',
])

/**
 * PPTX 单个导出任务专用的资源缓存与诊断上下文。
 */
export class PptxResourceSession {
  private readonly cache = new Map<string, Promise<CachedResourceEntry | null>>()
  private readonly resolver = new PPTXImageDataResolver()
  private hits = 0
  private fetches = 0
  private totalBytes = 0
  private screenshots = 0
  private rasterizedPages: number[] = []

  constructor(readonly taskId: string, readonly signal?: AbortSignal, readonly canvas?: PptxCanvasSnapshot) {}

  /**
   * 读取或通过任务级缓存复用图片资源。
   * 相同的 URL/资源身份在同一任务中只发起一次实际读取，避免重复下载。
   * @param path 图片资源路径或 URL
   * @returns 包含 dataUrl 与字节长度的资源条目
   */
  async resolveImage(path: string): Promise<string> {
    throwIfExportAborted(this.signal)
    const normalized = String(path || '').trim()
    if (!normalized) {
      return ''
    }

    if (/^data:image\//i.test(normalized)) {
      this.totalBytes += this.estimateDataUrlBytes(normalized)
      return normalized
    }

    const cacheKey = this.buildCacheKey(normalized)
    const existing = this.cache.get(cacheKey)
    if (existing) {
      this.hits += 1
      const cached = await existing
      return cached?.dataUrl || ''
    }

    this.fetches += 1
    const fetchPromise = (async (): Promise<CachedResourceEntry | null> => {
      try {
        const dataUrl = await this.resolver.resolve(normalized, this.signal)
        if (!dataUrl) {
          return null
        }
        const byteLength = this.estimateDataUrlBytes(dataUrl)
        this.totalBytes += byteLength
        return {
          dataUrl,
          byteLength,
          contentType: this.extractDataUrlContentType(dataUrl),
        }
      } catch {
        throwIfExportAborted(this.signal)
        return null
      }
    })()

    this.cache.set(cacheKey, fetchPromise)
    const entry = await fetchPromise
    return entry?.dataUrl || ''
  }

  /**
   * 记录一次截图操作（局部降级或整页截图）。
   */
  recordScreenshot(): void {
    this.screenshots += 1
  }

  /**
   * 记录发生整页截图降级的页码。
   * @param pageIndex 页面序号（从 1 开始）
   */
  recordRasterizedPage(pageIndex: number): void {
    if (!this.rasterizedPages.includes(pageIndex)) {
      this.rasterizedPages.push(pageIndex)
    }
  }

  /**
   * 汇总当前任务的资源与性能指标。
   */
  getMetrics(): PptxExportResourceMetrics {
    return {
      cacheHits: this.hits,
      fetchCount: this.fetches,
      totalResourceBytes: this.totalBytes,
      screenshotCount: this.screenshots,
      rasterizedPageIndices: [...this.rasterizedPages],
    }
  }

  /**
   * 释放任务缓存，防止长时间持有大体积 data URL 导致内存泄漏。
   */
  dispose(): void {
    this.cache.clear()
    this.rasterizedPages = []
  }

  /**
   * 针对诊断报告安全脱敏 URL，移除敏感令牌与凭证。
   * @param url 待脱敏的 URL
   */
  sanitizeUrl(url: string): string {
    if (!url || !url.includes('?')) {
      return url
    }

    try {
      const parsed = new URL(url, 'http://localhost')
      let changed = false
      parsed.searchParams.forEach((_, key) => {
        if (SENSITIVE_QUERY_KEYS.has(key.toLowerCase())) {
          parsed.searchParams.set(key, '[REDACTED]')
          changed = true
        }
      })
      if (!changed) {
        return url
      }
      return url.startsWith('http://') || url.startsWith('https://')
        ? parsed.href
        : `${parsed.pathname}?${parsed.searchParams.toString()}`
    } catch {
      return url.replace(/([?&](?:token|key|secret|signature|auth)=)[^&]+/gi, '$1[REDACTED]')
    }
  }

  /**
   * 生成可复制或下载的结构化诊断 JSON 报告。
   */
  generateDiagnosticReport(
    report: PptxExportReport,
    timings?: PptxExportTimingMetrics,
  ): Record<string, unknown> {
    const metrics = this.getMetrics()
    return {
      taskId: this.taskId,
      timings: timings || report.timings || {},
      metrics,
      summary: report.summary,
      pageCount: report.pages.length,
      rasterizedPageIndices: metrics.rasterizedPageIndices,
      pages: report.pages.map(page => ({
        pageIndex: page.pageIndex,
        pageTitle: page.pageTitle,
        pageRoute: page.pageRoute,
        isRasterizedFallback: metrics.rasterizedPageIndices?.includes(page.pageIndex) ?? false,
        itemCount: page.items.length,
        degradations: page.items
          .filter(item => !item.editable && item.result !== 'image')
          .map(item => ({
            sourceType: item.sourceType,
            result: item.result,
            label: item.label,
            reason: item.reason,
            severity: item.severity || 'info',
            code: item.code,
            fallbackScope: item.fallbackScope,
          })),
      })),
    }
  }

  private buildCacheKey(path: string): string {
    return path
  }

  private estimateDataUrlBytes(dataUrl: string): number {
    const commaIndex = dataUrl.indexOf(',')
    if (commaIndex < 0) {
      return 0
    }
    const base64Length = dataUrl.length - (commaIndex + 1)
    return Math.floor((base64Length * 3) / 4)
  }

  private extractDataUrlContentType(dataUrl: string): string {
    const match = /^data:([^;,]+)/i.exec(dataUrl)
    return match ? match[1].toLowerCase() : 'image/png'
  }
}
