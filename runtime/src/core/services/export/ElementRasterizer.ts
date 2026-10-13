/**
 * 文件用途：提供针对已就绪页面局部 DOM 元素的快速光栅化能力，跳过整页等待并自动注入同源资源代理。
 */

import { pageCaptureService } from '@/core/services/PageCaptureService'
import { RUNTIME_SNAPDOM_RESOURCE_PROXY_PATH } from '@/core/shared/runtime-preview'
import type { CaptureOptions } from '@/core/types/export-common'
import { getRuntimePreviewContext, getRuntimePreviewToken } from '@/core/utils/path'

const DEFAULT_RASTER_SCALE = 2
const DEFAULT_RASTER_TIMEOUT = 15000

/**
 * 解析 snapDOM 跨域资源代理地址。
 * 优先使用显式环境变量或配置；SaaS 预览下自动回退到 Runtime 同源代理，避免远端图片缺少 CORS 时截图空白。
 * @param configuredProxyUrl 可选的预设代理地址
 * @returns 解析后的代理 URL，不可用时返回 undefined
 */
export function resolveSnapdomProxyUrl(configuredProxyUrl?: string): string | undefined {
  const explicitProxyUrl = String(
    import.meta.env.VITE_SNAPDOM_PROXY_URL
    || configuredProxyUrl
    || '',
  ).trim()
  if (explicitProxyUrl) {
    return explicitProxyUrl
  }

  if (typeof window === 'undefined') {
    return undefined
  }

  const previewContext = getRuntimePreviewContext()
  const previewToken = getRuntimePreviewToken()
  if (!previewContext?.artifactId || !previewToken) {
    return undefined
  }

  const runtimePublicBaseUrl = resolveRuntimePublicBaseUrl()
  const proxyBaseUrl = runtimePublicBaseUrl || window.location.origin
  const proxyUrl = new URL(
    RUNTIME_SNAPDOM_RESOURCE_PROXY_PATH.replace(/^\/+/, ''),
    `${proxyBaseUrl.replace(/\/+$/, '')}/`,
  )
  proxyUrl.searchParams.set('artifactId', previewContext.artifactId)
  proxyUrl.searchParams.set('token', previewToken)
  proxyUrl.searchParams.set('url', '')

  return proxyUrl.href
}

/**
 * 读取预览 HTML 注入的 Runtime 公开基址。
 * @returns 规范化后的 Runtime 公开基址，缺失或非法时返回空串
 */
export function resolveRuntimePublicBaseUrl(): string {
  if (typeof window === 'undefined') {
    return ''
  }
  const runtimePublicBaseUrl = String(window.__RUNTIME_PUBLIC_BASE_URL__ || '').trim()
  if (!runtimePublicBaseUrl) {
    return ''
  }

  try {
    return new URL(runtimePublicBaseUrl, window.location.href).href.replace(/\/+$/, '')
  } catch {
    return ''
  }
}

/**
 * 局部元素光栅化器：专门服务于已处于就绪态的页面内部节点截图（如 PPTX 3D/复杂 CSS 降级块）。
 */
export class ElementRasterizer {
  /**
   * 捕获已就绪页面中的局部元素并返回透明背景 PNG data URL。
   * 约束：默认开启 skipPageWait，避免每个局部降级块重复触发 500ms 全局等待，并自动接入同源资源代理。
   * @param element 目标 DOM 元素
   * @param options 可选覆盖参数
   * @returns PNG data URL
   */
  async captureElementAsPng(
    element: HTMLElement,
    options?: Partial<CaptureOptions>,
  ): Promise<string> {
    const canvas = await pageCaptureService.captureElement(element, {
      scale: DEFAULT_RASTER_SCALE,
      backgroundColor: 'transparent',
      timeout: DEFAULT_RASTER_TIMEOUT,
      skipPageWait: true,
      ...options,
      // 代理地址必须最后落定：调用方传空串时应回退到环境变量或预览同源代理，而不是覆盖成空值。
      proxyUrl: resolveSnapdomProxyUrl(options?.proxyUrl),
    })
    return canvas.toDataURL('image/png')
  }
}

export const elementRasterizer = new ElementRasterizer()
