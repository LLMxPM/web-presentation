// 文件功能：集中注册 Editor 字体预览使用的 @font-face，并为主题卡提供隔离的字体族别名。
import { onBeforeUnmount, watch, type ComputedRef } from 'vue'

import type { WorkspaceFontFamilyItem } from '@/types/api'

const STYLE_ELEMENT_ID = 'editor-font-preview-registry'
const familyOwners = new Map<symbol, WorkspaceFontFamilyItem[]>()

/**
 * 注册当前组件需要预览的字体族，并在组件卸载时释放对应声明。
 * @param families 当前组件实际引用的字体族
 */
export function useFontPreviewRegistry(
  families: ComputedRef<Array<WorkspaceFontFamilyItem | null>>,
): void {
  const owner = Symbol('font-preview-owner')

  watch(
    families,
    items => {
      familyOwners.set(owner, items.filter((item): item is WorkspaceFontFamilyItem => Boolean(item)))
      rebuildFontPreviewStyles()
    },
    { immediate: true, deep: true },
  )

  onBeforeUnmount(() => {
    familyOwners.delete(owner)
    rebuildFontPreviewStyles()
  })
}

/**
 * 返回字体族在 Editor 预览中的隔离 CSS 名称。
 * @param family 工作空间字体族
 */
export function getFontPreviewFamilyAlias(family: WorkspaceFontFamilyItem): string {
  return `editor-preview-font-${family.workspace_id}-${family.id}`
}

/**
 * 生成主题预览实际使用的 font-family 值；字体不可用时回退到主题标签。
 * @param family 完整字体族配置
 * @param fallbackFamily 主题配置中的字体展示名或通用字体族
 */
export function resolveFontPreviewFamily(
  family: WorkspaceFontFamilyItem | null | undefined,
  fallbackFamily: string,
): string {
  if (!family || !family.faces.some(face => face.status === 'active' && face.asset_url)) {
    return fallbackFamily
  }
  return `"${getFontPreviewFamilyAlias(family)}", ${fallbackFamily}`
}

/** 汇总所有预览组件的字体依赖并重建唯一 style 节点。 */
function rebuildFontPreviewStyles(): void {
  if (typeof document === 'undefined') {
    return
  }

  const families = new Map<string, WorkspaceFontFamilyItem>()
  for (const ownerFamilies of familyOwners.values()) {
    for (const family of ownerFamilies) {
      families.set(getFontPreviewFamilyAlias(family), family)
    }
  }

  const rules = Array.from(families.values()).flatMap(buildFontFaceRules)
  const existingStyle = document.getElementById(STYLE_ELEMENT_ID)
  if (rules.length === 0) {
    existingStyle?.remove()
    return
  }

  const styleElement = existingStyle ?? document.createElement('style')
  styleElement.id = STYLE_ELEMENT_ID
  styleElement.textContent = rules.join('\n')
  if (!existingStyle) {
    document.head.appendChild(styleElement)
  }
}

/**
 * 为字体族内全部 active face 生成声明，保留字重、样式和加载策略。
 * @param family 工作空间字体族
 */
function buildFontFaceRules(family: WorkspaceFontFamilyItem): string[] {
  const alias = getFontPreviewFamilyAlias(family)
  return family.faces
    .filter(face => face.status === 'active' && Boolean(face.asset_url))
    .map(face => [
      '@font-face {',
      `  font-family: "${alias}";`,
      `  src: url(${JSON.stringify(face.asset_url)}) format("${face.font_format}");`,
      `  font-weight: ${face.font_weight};`,
      `  font-style: ${face.font_style};`,
      `  font-display: ${face.font_display};`,
      '}',
    ].join('\n'))
}
