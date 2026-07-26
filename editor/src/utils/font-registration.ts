// 文件功能：提供字体文件到字体注册的推断工具，供上传自动注册与编辑弹窗共用。

/** 平台支持的字体格式集合，与后端 _normalize_font_format 保持一致。 */
export const FONT_FORMATS = ['woff2', 'woff', 'ttf', 'otf'] as const

export type FontFormat = (typeof FONT_FORMATS)[number]

/**
 * 字重后缀到 CSS 数值字重的映射，用于从文件名推断 face 字重。
 * 键为归一化后的小写 token（去除分隔符），按由长到短匹配避免子串误判。
 */
const FONT_WEIGHT_SUFFIX_MAP: ReadonlyArray<readonly [string, string]> = [
  ['extrablack', '950'],
  ['ultrablack', '950'],
  ['extrabold', '800'],
  ['ultrabold', '800'],
  ['semibold', '600'],
  ['demibold', '600'],
  ['extralight', '200'],
  ['ultralight', '200'],
  ['thin', '100'],
  ['hairline', '100'],
  ['light', '300'],
  ['normal', '400'],
  ['regular', '400'],
  ['medium', '500'],
  ['bold', '700'],
  ['heavy', '900'],
  ['black', '900'],
]

/** 样式后缀集合，命中即视为斜体（italic/oblique）。 */
const FONT_STYLE_ITALIC_SUFFIXES = ['italic', 'oblique'] as const

/** 可变字体标记，命中后字重推断返回全范围 '100 900'。 */
const VARIABLE_FONT_SUFFIXES = ['variable', 'vf'] as const

/** 所有可从文件名剥离的后缀（字重 + 样式 + 可变字体），按长度降序用于反复剥离。 */
const STRIPPABLE_SUFFIXES: readonly string[] = [
  ...FONT_WEIGHT_SUFFIX_MAP.map(([token]) => token),
  ...FONT_STYLE_ITALIC_SUFFIXES,
  ...VARIABLE_FONT_SUFFIXES,
].sort((a, b) => b.length - a.length)

/**
 * 根据字体文件名推断字体格式，未匹配时回退 woff2。
 * @param name 字体资源原文件名
 */
export function inferFontFormat(name: string): FontFormat {
  const lowerName = String(name || '').toLowerCase()
  for (const format of FONT_FORMATS) {
    if (lowerName.endsWith(`.${format}`)) return format
  }
  return 'woff2'
}

/** 去除扩展名并整理分隔符，返回以空格分隔的基础名。 */
function stripExtensionAndNormalize(name: string): string {
  return String(name || '')
    .replace(/\.(woff2|woff|ttf|otf)$/i, '')
    .replace(/[_\s]+/g, ' ')
    .trim()
}

/** 将 token 归一化为纯小写字母数字，便于与后缀表比较。 */
function normalizeToken(token: string): string {
  return token.toLowerCase().replace(/[^a-z0-9]/g, '')
}

/**
 * 从字体文件名推断字体族名：剥离末尾的字重/样式/可变字体后缀，
 * 使 SourceHanSans-Bold 与 SourceHanSans-Regular 归入同一 family。
 * @param name 字体资源原文件名
 */
export function inferFontFamily(name: string): string {
  const base = stripExtensionAndNormalize(name)
  if (!base) return ''
  // 按空格与连字符切分为词，从尾部反复剥离可识别后缀（兼容 BoldItalic 组合词）。
  const tokens = base.split(/[\s-]+/).filter(Boolean)
  while (tokens.length > 1) {
    const last = normalizeToken(tokens[tokens.length - 1])
    if (!last) {
      tokens.pop()
      continue
    }
    if (isStrippableToken(last)) {
      tokens.pop()
      continue
    }
    break
  }
  const result = tokens.join(' ').trim()
  return result || base
}

/** 判断一个归一化 token 是否完全由可剥离后缀拼接而成（如 bolditalic）。 */
function isStrippableToken(token: string): boolean {
  if (!token) return false
  let rest = token
  let stripped = false
  // 贪心地从头部剥离已知后缀，全部消费完则视为纯修饰词。
  let guard = 0
  while (rest && guard < 8) {
    guard += 1
    const match = STRIPPABLE_SUFFIXES.find(suffix => rest.startsWith(suffix))
    if (!match) break
    rest = rest.slice(match.length)
    stripped = true
  }
  return stripped && rest.length === 0
}

/**
 * 从字体文件名推断 face 字重：命中可变字体标记返回 '100 900'，
 * 命中字重后缀返回对应数值，否则回退 '400'。
 * @param name 字体资源原文件名
 */
export function inferFontWeight(name: string): string {
  const base = stripExtensionAndNormalize(name)
  const normalized = normalizeToken(base)
  if (VARIABLE_FONT_SUFFIXES.some(flag => normalized.includes(flag))) {
    return '100 900'
  }
  const tokens = base.split(/[\s-]+/).filter(Boolean)
  // 从尾部优先匹配最靠后的字重后缀，兼容 BoldItalic 组合。
  for (let index = tokens.length - 1; index >= 0; index -= 1) {
    const token = normalizeToken(tokens[index])
    for (const [suffix, weight] of FONT_WEIGHT_SUFFIX_MAP) {
      if (token === suffix || token.startsWith(suffix) || token.endsWith(suffix)) {
        return weight
      }
    }
  }
  return '400'
}

/**
 * 从字体文件名推断 face 样式：命中 Italic/Oblique 返回 italic，否则 normal。
 * @param name 字体资源原文件名
 */
export function inferFontStyle(name: string): string {
  const normalized = normalizeToken(stripExtensionAndNormalize(name))
  return FONT_STYLE_ITALIC_SUFFIXES.some(flag => normalized.includes(flag)) ? 'italic' : 'normal'
}

/**
 * 构建上传后自动注册使用的默认字体声明，输出字体族名与推断的字重/样式。
 * @param originalName 字体资源原文件名
 */
export function buildDefaultFontRegistration(originalName: string): {
  family_name: string
  font_format: FontFormat
  font_weight: string
  font_style: string
  font_display: string
} {
  return {
    family_name: inferFontFamily(originalName),
    font_format: inferFontFormat(originalName),
    font_weight: inferFontWeight(originalName),
    font_style: inferFontStyle(originalName),
    font_display: 'swap',
  }
}
