/** 文件用途：将主题色写入实际主题 XML，并仅在所有页面拥有一致纯色背景时提升到唯一母版。 */
import { strFromU8, strToU8 } from 'fflate'
import type { PptxPresentationTheme } from '../theme/PptxThemeResolver'
import { PptxMasterSlideStrategy } from '../theme/PptxMasterSlideStrategy'

/** 只替换已声明的主题槽位；页面显式 RGB 图元颜色继续保留。 */
export function patchThemeColors(xml: string, theme: PptxPresentationTheme): string {
  const slots = { dk1: theme.colors.primary, dk2: theme.colors.secondary, lt1: theme.colors.background,
    accent1: theme.colors.accent1, accent2: theme.colors.accent2, accent3: theme.colors.accent3,
    accent4: theme.colors.accent4, accent5: theme.colors.accent5, accent6: theme.colors.accent6 }
  return xml.replace(/<a:clrScheme\b[^>]*>[\s\S]*?<\/a:clrScheme>/, scheme => {
    for (const [slot, color] of Object.entries(slots)) {
      if (color && /^[\da-f]{6}$/i.test(color)) {
        scheme = scheme.replace(new RegExp(`<a:${slot}>[\\s\\S]*?<\\/a:${slot}>`), `<a:${slot}><a:srgbClr val="${color.toUpperCase()}"/></a:${slot}>`)
      }
    }
    return scheme
  })
}

/**
 * 在唯一母版且至少两页纯色背景一致时提升已有背景 XML；图片、缺失或不同背景均保持原页。
 * 保留现成的颜色与 alpha 表达，不改变页面内容、布局关系或备注。
 */
export function promoteSharedSlideBackground(files: Record<string, Uint8Array>): void {
  const masters = Object.keys(files).filter(name => /^ppt\/slideMasters\/slideMaster\d+\.xml$/.test(name))
  const slidePaths = Object.keys(files).filter(name => /^ppt\/slides\/slide\d+\.xml$/.test(name))
  if (masters.length !== 1 || slidePaths.length < 2) return
  const layouts = Object.keys(files).filter(path => /^ppt\/slideLayouts\/slideLayout\d+\.xml$/.test(path)).map(path => {
    const xml = strFromU8(files[path])
    return { path, xml, background: /<p:bg\b[^>]*>[\s\S]*?<\/p:bg>/.exec(xml)?.[0] }
  })
  // 默认布局的 bg1 引用也优先于母版，提升时一起移除；自定义布局背景则保留逐页覆盖。
  if (layouts.some(layout => layout.background && !(
    /<p:cSld name="DEFAULT">/.test(layout.xml) &&
    layout.background === '<p:bg><p:bgRef idx="1001"><a:schemeClr val="bg1"/></p:bgRef></p:bg>'
  ))) return
  const entries = slidePaths.map(path => {
    const xml = strFromU8(files[path])
    const background = /<p:bg\b[^>]*>[\s\S]*?<\/p:bg>/.exec(xml)?.[0]
    const color = background && /<a:solidFill><a:srgbClr val="([\da-f]{6})"/i.exec(background)?.[1]
    const alpha = background && /<a:alpha val="(\d+)"/.exec(background)?.[1]
    return { path, xml, background, parsed: color ? { color, transparency: alpha ? 100 - Number(alpha) / 1000 : 0 } : undefined }
  })
  if (!new PptxMasterSlideStrategy().evaluate(entries.map(entry => entry.parsed)).hasSharedBackground) return
  // 半透明背景会与既有母版混合，不能仅凭颜色相同就提升。
  if (entries.some(entry => entry.parsed!.transparency !== 0)) return
  const firstBackground = entries[0].background!
  const master = strFromU8(files[masters[0]])
  if (!/<p:cSld\b[^>]*>/.test(master)) return
  const updated = /<p:bg\b/.test(master)
    ? master.replace(/<p:bg\b[^>]*>[\s\S]*?<\/p:bg>/, firstBackground)
    : master.replace(/(<p:cSld\b[^>]*>)/, `$1${firstBackground}`)
  files[masters[0]] = strToU8(updated)
  for (const layout of layouts) {
    if (layout.background) files[layout.path] = strToU8(layout.xml.replace(layout.background, ''))
  }
  for (const entry of entries) files[entry.path] = strToU8(entry.xml.replace(entry.background!, ''))
}
