/**
 * 文件用途：封装 MathJax 渲染前的公式源码规范化、显示模式推断与常用宏配置。
 */

import { mathjax } from '@mathjax/src/js/mathjax.js'
import { liteAdaptor } from '@mathjax/src/js/adaptors/liteAdaptor.js'
import { browserAdaptor } from '@mathjax/src/js/adaptors/browserAdaptor.js'
import { RegisterHTMLHandler } from '@mathjax/src/js/handlers/html.js'
import { TeX } from '@mathjax/src/js/input/tex.js'
import { SVG } from '@mathjax/src/js/output/svg.js'
import '@mathjax/src/js/input/tex/ams/AmsConfiguration.js'
import '@mathjax/src/js/input/tex/configmacros/ConfigMacrosConfiguration.js'
import '@mathjax/src/js/input/tex/noundefined/NoUndefinedConfiguration.js'

export type MathStrictMode = boolean | 'ignore' | 'warn' | 'error'

const BLOCK_ENVIRONMENT_RE = /^\\begin\{(?:equation|equation\*|align|align\*|gather|gather\*|multline|multline\*)\}/
const LATEX_SEGMENT_RE = /(\\begin\{(equation\*?|align\*?|gather\*?|multline\*?)\}[\s\S]*?\\end\{\2\})|\\\[([\s\S]*?)\\\]|\$\$([\s\S]*?)\$\$|\\\(([\s\S]*?)\\\)|(?<!\\)\$(?!\$)([\s\S]*?)(?<!\\)\$/g
const ONLY_LINEBREAKS_RE = /^(?:\\\\\s*)+$/
const LATEX_COMMENT_RE = /(?<!\\)%.*$/

export const DEFAULT_LATEX_MACROS: Record<string, string> = {
  dif: '\\mathop{}\\!\\mathrm{d}',
  diff: '\\mathop{}\\!\\mathrm{d}',
  dd: '\\mathop{}\\!\\mathrm{d}',
}

export interface NormalizedLatexSource {
  /** 可直接传给 MathJax 的公式源码 */
  source: string
  /** 源码是否表达了块级公式语义 */
  displayMode: boolean
}

export type LatexSourceSegment = NormalizedLatexSource

export interface RenderLatexOptions {
  /** 外部显式指定的块级模式 */
  displayMode?: boolean
  /** 解析错误时是否抛出异常，保留为兼容旧组件参数 */
  throwOnError?: boolean
  /** 严格模式，保留为兼容旧组件参数 */
  strict?: MathStrictMode
  /** 是否允许受信任命令，保留为兼容旧组件参数 */
  trust?: boolean
}

const svgFontLoaders: Record<string, () => Promise<unknown>> = {
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/accents-b-i.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/accents-b-i.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/accents.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/accents.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/arabic.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/arabic.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/arrows.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/arrows.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/braille-d.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/braille-d.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/braille.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/braille.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/calligraphic.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/calligraphic.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/cherokee.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/cherokee.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/cyrillic-ss.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/cyrillic-ss.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/cyrillic.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/cyrillic.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/devanagari.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/devanagari.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/double-struck.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/double-struck.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/fraktur.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/fraktur.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/greek-ss.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/greek-ss.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/greek.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/greek.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/hebrew.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/hebrew.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/latin-b.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/latin-b.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/latin-bi.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/latin-bi.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/latin-i.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/latin-i.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/latin.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/latin.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/marrows.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/marrows.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/math.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/math.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/monospace-ex.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/monospace-ex.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/monospace-l.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/monospace-l.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/monospace.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/monospace.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/mshapes.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/mshapes.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/phonetics-ss.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/phonetics-ss.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/phonetics.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/phonetics.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/PUA.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/PUA.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/sans-serif-b.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/sans-serif-b.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/sans-serif-bi.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/sans-serif-bi.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/sans-serif-ex.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/sans-serif-ex.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/sans-serif-i.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/sans-serif-i.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/sans-serif-r.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/sans-serif-r.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/sans-serif.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/sans-serif.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/script.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/script.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/shapes.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/shapes.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/symbols-b-i.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/symbols-b-i.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/symbols.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/symbols.js'),
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/variants.js': () => import('@mathjax/mathjax-newcm-font/js/svg/dynamic/variants.js'),
}

mathjax.asyncLoad = (file: string) => {
  const loader = svgFontLoaders[file]
  if (!loader) {
    return Promise.reject(new Error(`未注册 MathJax 动态字体文件：${file}`))
  }
  return loader()
}

const adaptor = (
  typeof document === 'undefined' ? liteAdaptor() : browserAdaptor()
) as Parameters<typeof RegisterHTMLHandler>[0]
RegisterHTMLHandler(adaptor)

const tex = new TeX({
  packages: ['base', 'ams', 'configmacros', 'noundefined'],
  macros: DEFAULT_LATEX_MACROS,
})
const svg = new SVG({ fontCache: 'local' })
const htmlDocument = mathjax.document(typeof document === 'undefined' ? '' : document, {
  InputJax: tex,
  OutputJax: svg,
})

/**
 * 移除未转义百分号引出的 TeX 行注释，避免纯注释资源生成空 SVG。
 *
 * @param rawSource 原始公式源码
 * @returns 去除注释后的公式源码
 */
function stripLatexComments(rawSource: string): string {
  return rawSource
    .split(/\r?\n/)
    .map(line => line.replace(LATEX_COMMENT_RE, '').trimEnd())
    .join('\n')
    .trim()
}

/**
 * 去除用户常输入的外层数学定界符，并记录是否需要块级显示。
 *
 * @param rawSource 原始公式源码
 * @returns 规范化源码和显示模式推断结果
 */
export function normalizeLatexSource(rawSource: string): NormalizedLatexSource {
  const source = stripLatexComments(rawSource)
  if (!source) {
    return { source: '', displayMode: false }
  }

  if (source.startsWith('$$') && source.endsWith('$$')) {
    return { source: source.slice(2, -2).trim(), displayMode: true }
  }
  if (source.startsWith('\\[') && source.endsWith('\\]')) {
    return { source: source.slice(2, -2).trim(), displayMode: true }
  }
  if (source.startsWith('\\(') && source.endsWith('\\)')) {
    return { source: source.slice(2, -2).trim(), displayMode: false }
  }

  return {
    source,
    displayMode: BLOCK_ENVIRONMENT_RE.test(source),
  }
}

/**
 * 将包含多个数学定界符的源码拆成可独立渲染的公式片段。
 *
 * @param rawSource 原始公式源码
 * @returns 按出现顺序排列的公式片段
 */
export function splitLatexSource(rawSource: string): LatexSourceSegment[] {
  const source = stripLatexComments(rawSource)
  if (!source) {
    return []
  }

  LATEX_SEGMENT_RE.lastIndex = 0
  const segments: LatexSourceSegment[] = []
  let lastIndex = 0
  let matched = false

  for (const match of source.matchAll(LATEX_SEGMENT_RE)) {
    matched = true
    const plainSource = source.slice(lastIndex, match.index).trim()
    if (plainSource && !ONLY_LINEBREAKS_RE.test(plainSource)) {
      segments.push(normalizeLatexSource(plainSource))
    }

    const displaySource = match[1] ?? match[3] ?? match[4]
    const inlineSource = match[5] ?? match[6]
    segments.push({
      source: (displaySource ?? inlineSource ?? '').trim(),
      displayMode: inlineSource === undefined,
    })
    lastIndex = match.index + match[0].length
  }

  if (!matched) {
    return [normalizeLatexSource(source)].filter((segment) => Boolean(segment.source))
  }

  const remainingSource = source.slice(lastIndex).trim()
  if (remainingSource && !ONLY_LINEBREAKS_RE.test(remainingSource)) {
    segments.push(normalizeLatexSource(remainingSource))
  }

  return segments.filter((segment) => Boolean(segment.source))
}

/**
 * 使用 MathJax 和 Runtime 默认宏渲染 LaTeX 源码。
 *
 * @param rawSource 原始公式源码
 * @param options 渲染选项
 * @returns MathJax SVG HTML 字符串
 */
export async function renderLatexToString(rawSource: string, options: RenderLatexOptions = {}): Promise<string> {
  const segments = splitLatexSource(rawSource)
  if (segments.length === 0) {
    return ''
  }

  const htmlSegments: string[] = []
  for (const segment of segments) {
    const node = await htmlDocument.convertPromise(segment.source, {
      display: Boolean(options.displayMode || segment.displayMode),
    })
    htmlSegments.push(adaptor.outerHTML(node))
  }
  return htmlSegments.join('\n')
}
