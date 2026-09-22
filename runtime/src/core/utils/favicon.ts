/**
 * 文件用途：根据 Runtime 的 app.config.app.icon 动态同步浏览器 favicon，
 *           让标签页图标与运行时配置、预览注入资源保持同一条解析链。
 */

import {
  addChangeListener,
  loadAppConfig,
  loadIconConfig,
  type ConfigChangeListener,
  type IconConfigYaml,
  type StaticIconConfigItem,
} from '@/core/utils/config'
import { resolveResourcePath } from '@/core/utils/path'

const DEFAULT_FAVICON_HREF = [
  'data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 32 32%22%3E',
  '%3Crect width=%2232%22 height=%2232%22 rx=%227%22 fill=%22%230f172a%22/%3E',
  '%3Cpath d=%22M9 17h14M9 11h14M9 23h8%22 stroke=%22%23fff%22 stroke-width=%222.4%22 stroke-linecap=%22round%22/%3E',
  '%3C/svg%3E',
].join('')
const FAVICON_REL = 'icon'

let initialFaviconHref = ''
let dynamicFaviconObjectUrl = ''
let faviconSyncInitialized = false

const faviconConfigChangeListener: ConfigChangeListener = (configType) => {
  if (configType === 'app' || configType === 'icons') {
    void syncRuntimeFavicon()
  }
}

/**
 * 初始化 Runtime favicon 同步，仅注册一次配置监听。
 */
export function initializeRuntimeFaviconSync(): void {
  if (typeof document === 'undefined' || faviconSyncInitialized) {
    return
  }

  faviconSyncInitialized = true
  addChangeListener(faviconConfigChangeListener)
  void syncRuntimeFavicon()
}

/**
 * 根据当前 app.config 与 icons.config 同步浏览器标签页图标。
 */
export async function syncRuntimeFavicon(): Promise<void> {
  if (typeof document === 'undefined') {
    return
  }

  const faviconLink = ensureFaviconLink()
  if (!faviconLink) {
    return
  }
  if (!initialFaviconHref) {
    initialFaviconHref = faviconLink.href || DEFAULT_FAVICON_HREF
  }

  const appConfig = await loadAppConfig()
  const iconName = String(appConfig?.app?.icon || '').trim()
  if (!iconName) {
    applyResolvedFavicon({ href: initialFaviconHref, type: 'image/svg+xml' })
    return
  }

  const resolvedFavicon = await resolveConfiguredFavicon(iconName)
  if (!resolvedFavicon) {
    applyResolvedFavicon({ href: initialFaviconHref, type: 'image/svg+xml' })
    return
  }

  applyResolvedFavicon(resolvedFavicon)
}

/**
 * 确保页面中存在 favicon link 标签。
 * @returns favicon 对应的 link 元素
 */
function ensureFaviconLink(): HTMLLinkElement | null {
  if (typeof document === 'undefined') {
    return null
  }

  const existingLink = document.querySelector<HTMLLinkElement>('link[rel~="icon"]')
  if (existingLink) {
    return existingLink
  }

  const createdLink = document.createElement('link')
  createdLink.rel = FAVICON_REL
  createdLink.type = 'image/svg+xml'
  createdLink.href = DEFAULT_FAVICON_HREF
  document.head.appendChild(createdLink)
  return createdLink
}

/**
 * 解析 app.config.icon 对应的最终 favicon 资源。
 * 关键约束：
 * 1. 图标名必须来自 icons.config/static_icons；
 * 2. 优先把资源下载为 blob URL，避免浏览器对相同地址的 favicon 强缓存；
 * 3. 下载失败时回退为直接资源地址，尽量保证图标仍可显示。
 * @param iconName app.config 中声明的图标名称
 */
async function resolveConfiguredFavicon(iconName: string): Promise<{ href: string; type?: string } | null> {
  const iconConfig = await loadIconConfig()
  const targetIcon = findStaticIcon(iconConfig, iconName)
  if (!targetIcon?.src) {
    return null
  }

  const resolvedIconHref = resolveResourcePath(targetIcon.src)
  if (!resolvedIconHref) {
    return null
  }

  try {
    const response = await fetch(resolvedIconHref)
    if (!response.ok) {
      throw new Error(`favicon fetch failed: ${response.status}`)
    }
    const blob = await response.blob()
    const objectUrl = URL.createObjectURL(blob)
    return {
      href: objectUrl,
      type: blob.type || inferFaviconMimeType(targetIcon, resolvedIconHref),
    }
  } catch {
    return {
      href: resolvedIconHref,
      type: inferFaviconMimeType(targetIcon, resolvedIconHref),
    }
  }
}

/**
 * 根据图标名称从静态图标配置中查找目标项。
 * @param iconConfig Runtime 图标配置
 * @param iconName 配置声明的图标名称
 */
function findStaticIcon(iconConfig: IconConfigYaml, iconName: string): StaticIconConfigItem | undefined {
  return iconConfig.static_icons.find((item) => item.name === iconName)
}

/**
 * 推断 favicon 的 MIME 类型，优先使用结构化分析元数据。
 * @param icon 静态图标配置项
 * @param resolvedHref 解析后的资源地址
 */
function inferFaviconMimeType(icon: StaticIconConfigItem, resolvedHref: string): string | undefined {
  if (icon.analysis?.icon.format === 'svg') {
    return 'image/svg+xml'
  }
  const normalizedHref = resolvedHref.toLowerCase()
  if (normalizedHref.endsWith('.png')) {
    return 'image/png'
  }
  if (normalizedHref.endsWith('.jpg') || normalizedHref.endsWith('.jpeg')) {
    return 'image/jpeg'
  }
  if (normalizedHref.endsWith('.ico')) {
    return 'image/x-icon'
  }
  if (normalizedHref.endsWith('.svg')) {
    return 'image/svg+xml'
  }
  return undefined
}

/**
 * 把新的 favicon 资源写入文档头，并清理上一轮动态创建的 blob URL。
 * @param resolvedFavicon 已解析出的 favicon 地址与类型
 */
function applyResolvedFavicon(resolvedFavicon: { href: string; type?: string }): void {
  const faviconLink = ensureFaviconLink()
  if (!faviconLink) {
    return
  }

  revokeDynamicFaviconObjectUrl()
  if (resolvedFavicon.href.startsWith('blob:')) {
    dynamicFaviconObjectUrl = resolvedFavicon.href
  }

  faviconLink.rel = FAVICON_REL
  faviconLink.href = resolvedFavicon.href
  if (resolvedFavicon.type) {
    faviconLink.type = resolvedFavicon.type
  } else {
    faviconLink.removeAttribute('type')
  }
}

/**
 * 释放上一轮 favicon 使用的 blob URL，避免热更新场景下堆积。
 */
function revokeDynamicFaviconObjectUrl(): void {
  if (!dynamicFaviconObjectUrl) {
    return
  }
  URL.revokeObjectURL(dynamicFaviconObjectUrl)
  dynamicFaviconObjectUrl = ''
}
