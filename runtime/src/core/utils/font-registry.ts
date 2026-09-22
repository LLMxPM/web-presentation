/**
 * 文件用途：根据 Backend 下发的预加载字体配置动态注册 @font-face，并提供主题字体引用解析。
 */

import { normalizeAssetKey, type RuntimeFontBundleItem } from '@/core/shared/runtime-preview'

import { getRuntimePreloadedConfig, resolveResourcePath } from './path'

const RUNTIME_FONT_STYLE_ID = 'runtime-dynamic-fonts'
const PLATFORM_SANS_FONT_URL = new URL(
  '../../assets/runtime-shell/fonts/SourceHanSansSC-VF.otf.woff2',
  import.meta.url,
).href
const PLATFORM_MONO_FONT_URL = new URL(
  '../../assets/runtime-shell/fonts/SourceCodePro-Regular.ttf.woff2',
  import.meta.url,
).href
const BUILTIN_THEME_FONT_FAMILIES = {
  'platform-sans': "'Web Presentation Sans', sans-serif",
  'platform-mono': "'Web Presentation Mono', monospace",
} as const
const BUILTIN_FONT_LOAD_DESCRIPTORS = {
  'platform-sans': { descriptor: "16px 'Web Presentation Sans'", sample: '演示文稿 Aa 0123' },
  'platform-mono': { descriptor: "16px 'Web Presentation Mono'", sample: 'Code 0123' },
} as const

/**
 * 读取运行时预加载字体配置。
 * @returns 字体配置表；没有预加载配置时返回空对象
 */
function getRuntimeFontItems(): Record<string, RuntimeFontBundleItem> {
  return getRuntimePreloadedConfig()?.fonts?.items ?? {}
}

/**
 * 按字体资源逻辑名解析运行时已注册字体族。
 * @param assetName 字体资源逻辑名，也就是 workspace asset.name
 * @param fallback 未命中字体注册时返回的兜底 font-family
 * @returns 可直接写入 CSS font-family 的字体族
 */
export function resolveAssetFontFamily(
  assetName: string | null | undefined,
  fallback: string = '',
): string {
  const normalizedAssetName = normalizeAssetKey(String(assetName || ''))
  if (!normalizedAssetName) {
    return fallback
  }

  const fontItems = getRuntimeFontItems()
  const matched = fontItems[normalizedAssetName]
  return matched?.font_family || fallback
}

/**
 * 将主题中的字体引用解析为真实 font-family。
 * 优先按字体资源逻辑名 asset_name 命中，其次兼容历史 font_family 直接匹配。
 * @param rawReference 主题中的原始字体引用
 * @returns 可直接写入 CSS 的 font-family
 */
export function resolveThemeFontFamily(rawReference: string): string {
  const normalizedReference = String(rawReference || '').trim()
  if (!normalizedReference) {
    return normalizedReference
  }

  const builtinFamily = BUILTIN_THEME_FONT_FAMILIES[
    normalizedReference as keyof typeof BUILTIN_THEME_FONT_FAMILIES
  ]
  if (builtinFamily) {
    return builtinFamily
  }

  const fontItems = getRuntimeFontItems()
  const byAssetName = fontItems[normalizedReference]
  if (byAssetName) {
    return byAssetName.font_family
  }

  const matchedByFamily = Object.values(fontItems).find(item => item.font_family === normalizedReference)
  return matchedByFamily?.font_family ?? normalizedReference
}

/**
 * 主动加载当前预加载主题引用的平台字体，并在加载失败时阻止截图进入就绪态。
 * @returns 所有必需平台字体均已可用时完成
 */
export async function waitForRequiredPlatformFonts(): Promise<void> {
  if (typeof document === 'undefined' || !document.fonts) {
    return
  }

  const serializedThemes = JSON.stringify(getRuntimePreloadedConfig()?.themes ?? {})
  const requiredTokens = Object.keys(BUILTIN_FONT_LOAD_DESCRIPTORS).filter(token => serializedThemes.includes(token))
  for (const token of requiredTokens) {
    const item = BUILTIN_FONT_LOAD_DESCRIPTORS[token as keyof typeof BUILTIN_FONT_LOAD_DESCRIPTORS]
    await document.fonts.load(item.descriptor, item.sample)
    if (!document.fonts.check(item.descriptor, item.sample)) {
      throw new Error(`平台字体加载失败：${token}`)
    }
  }
}

/**
 * 启动时根据预加载字体配置注册动态 @font-face。
 * @returns 已写入的 CSS 文本
 */
export function initializeRuntimeFontRegistry(): string {
  if (typeof document === 'undefined') {
    return ''
  }

  const fontItems = Object.values(getRuntimeFontItems())
  let styleElement = document.getElementById(RUNTIME_FONT_STYLE_ID) as HTMLStyleElement | null

  if (!styleElement) {
    styleElement = document.createElement('style')
    styleElement.id = RUNTIME_FONT_STYLE_ID
    document.head.appendChild(styleElement)
  }

  const cssText = [
    buildPlatformFontFaceRules(),
    ...fontItems.map(item => buildFontFaceRule(item)),
  ].filter(Boolean).join('\n')

  styleElement.textContent = cssText
  return cssText
}

/**
 * 生成 Runtime 内置平台字体规则；字体 URL 以当前模块为基准，避免代理预览文档把根路径解析到 Backend。
 * @returns 固定平台无衬线与等宽字体的 @font-face 规则
 */
function buildPlatformFontFaceRules(): string {
  return [
    '@font-face {',
    "  font-family: 'Web Presentation Sans';",
    `  src: url('${escapeCssUrl(PLATFORM_SANS_FONT_URL)}') format('woff2');`,
    '  font-weight: 100 900;',
    '  font-style: normal;',
    '  font-display: swap;',
    '}',
    '@font-face {',
    "  font-family: 'Web Presentation Mono';",
    `  src: url('${escapeCssUrl(PLATFORM_MONO_FONT_URL)}') format('woff2');`,
    '  font-weight: 400;',
    '  font-style: normal;',
    '  font-display: swap;',
    '}',
  ].join('\n')
}

/**
 * 生成单条 @font-face 规则。
 * @param item 字体配置项
 * @returns CSS 规则文本
 */
function buildFontFaceRule(item: RuntimeFontBundleItem): string {
  const fontUrl = resolveResourcePath(item.asset_name)
  if (!fontUrl) {
    return ''
  }

  const escapedFamily = escapeCssString(item.font_family)
  const escapedUrl = escapeCssUrl(fontUrl)
  return [
    '@font-face {',
    `  font-family: '${escapedFamily}';`,
    `  src: url('${escapedUrl}') format('${item.font_format}');`,
    `  font-weight: ${item.font_weight};`,
    `  font-style: ${item.font_style};`,
    `  font-display: ${item.font_display};`,
    '}',
  ].join('\n')
}

/**
 * 转义 CSS url() 单引号字符串，避免资源地址破坏动态字体规则。
 * @param value 字体资源 URL
 * @returns 可安全写入单引号 url() 的字符串
 */
function escapeCssUrl(value: string): string {
  return String(value || '').replace(/'/g, "\\'")
}

/**
 * 转义 CSS 字符串中的单引号。
 * @param value 原始文本
 * @returns 转义后的文本
 */
function escapeCssString(value: string): string {
  return String(value || '').replace(/'/g, "\\'")
}
