/**
 * 文件用途：封装 Backend 托管资源的 Vue 3 响应式辅助函数。
 *
 * 工作原理：
 *   SaaS 预览启动时，Backend 把工作空间内所有资源按逻辑名注册到 manifest.assets：
 *     { "background": "a3f8b2c1...", "logo-mark": "b5c8d3e2..." }
 *   同时 assetBaseUrl 已包含 workspaceId：
 *     "http://backend/public/assets/{workspaceId}"
 *
 *   resolveResourcePath(asset.name) 会自动完成：
 *     asset.name → manifest 查 file_hash → assetBaseUrl + file_hash → 完整 URL
 *
 *   因此 Vue 页面只需传入资源逻辑名 `asset.name`，无需关心任何 ID、hash 或地址。
 */

import { computed, type ComputedRef, type MaybeRefOrGetter, toValue } from 'vue'
import { getRuntimePreloadedConfig, resolveResourcePath } from '@/core/utils/path'
import { normalizeAssetKey } from '@/core/shared/runtime-preview'
import type { RuntimePreviewAssetMetadata } from '@/core/shared/runtime-preview'
import { resolveAssetFontFamily } from '@/core/utils/font-registry'

/**
 * 将资源逻辑名解析为响应式完整 URL。
 *
 * @param name 资源的逻辑名 `asset.name`（如 "background"）
 * @param fallback name 未命中时的兜底 URL，默认空串；支持响应式输入
 * @returns 响应式 URL ComputedRef
 *
 * @example
 * const src = useAssetSrc('background')
 * <img :src="src" />
 */
export function useAssetSrc(
  name: MaybeRefOrGetter<string | null | undefined>,
  fallback: MaybeRefOrGetter<string | null | undefined> = '',
): ComputedRef<string> {
  return computed(() => {
    const fallbackSrc = String(toValue(fallback) || '')
    const n = toValue(name)
    if (!n) return fallbackSrc
    const resolved = resolveResourcePath(n)
    return resolved || fallbackSrc
  })
}

/**
 * 将资源逻辑名解析为响应式 CSS background-image 样式对象。
 *
 * @param name 资源的逻辑名 `asset.name`（如 "background"）
 * @param fallback name 未命中时的兜底 URL；支持响应式输入
 * @returns 响应式 { backgroundImage: string } CSSProperties
 *
 * @example
 * const bgStyle = useAssetBackground('background')
 * <div :style="bgStyle" />
 */
export function useAssetBackground(
  name: MaybeRefOrGetter<string | null | undefined>,
  fallback: MaybeRefOrGetter<string | null | undefined> = '',
): ComputedRef<{ backgroundImage: string }> {
  return computed(() => {
    const fallbackSrc = String(toValue(fallback) || '')
    const n = toValue(name)
    if (!n) return { backgroundImage: fallbackSrc ? `url(${fallbackSrc})` : '' }
    const resolved = resolveResourcePath(n)
    const url = resolved || fallbackSrc
    return { backgroundImage: url ? `url(${url})` : '' }
  })
}

/**
 * 将字体资源逻辑名解析为响应式 font-family。
 *
 * @param name 字体资源的逻辑名 `asset.name`
 * @param fallback name 未命中字体注册时的兜底 font-family；支持响应式输入
 * @returns 响应式 font-family 字符串
 *
 * @example
 * const titleFont = useAssetFontFamily('BrandSerif')
 * <h1 :style="{ fontFamily: titleFont }" />
 */
export function useAssetFontFamily(
  name: MaybeRefOrGetter<string | null | undefined>,
  fallback: MaybeRefOrGetter<string | null | undefined> = '',
): ComputedRef<string> {
  return computed(() => resolveAssetFontFamily(toValue(name), String(toValue(fallback) || '')))
}

/**
 * 读取 manifest 中某个资源逻辑名对应的结构化元数据。
 *
 * @param name 资源的逻辑名 `asset.name`
 * @returns 响应式资源元数据；未命中时返回 null
 */
export function useAssetMetadata(
  name: MaybeRefOrGetter<string | null | undefined>,
): ComputedRef<RuntimePreviewAssetMetadata | null> {
  return computed(() => {
    const n = toValue(name)
    if (!n) return null
    const assetKey = normalizeAssetKey(n)
    return getRuntimePreloadedConfig()?.manifest?.asset_metadata?.[assetKey] ?? null
  })
}
