/**
 * 文件用途：维护页面可视化编辑可选择的版本化 Tailwind 目录，并保证其始终是 Runtime safelist 的受控子集。
 */

import { runtimeTailwindSafelist } from '../../tailwind/runtime-safelist.js'
import type {
  VisualEditTailwindCatalog,
  VisualEditTailwindCatalogGroup,
} from '../protocol'

const safelistClasses = new Set(
  runtimeTailwindSafelist.filter((candidate): candidate is string => typeof candidate === 'string'),
)

const spacingValues = ['0', '1', '2', '3', '4', '5', '6', '8', '10', '12', '16', '20', '24']
const sizeValues = ['0', '2', '4', '6', '8', '10', '12', '16', '20', '24', '32', '40', '48', '64', '80', '96']
const colorValues = [
  'transparent',
  'white',
  'black',
  'primary',
  'secondary',
  'invert',
  'background',
  'background-subtle',
  'background-invert',
  'border',
  'border-subtle',
  'accent1',
  'accent2',
  'accent3',
  'accent4',
  'accent5',
  'accent6',
  ...['slate', 'red', 'amber', 'green', 'blue', 'violet']
    .flatMap(color => ['50', '100', '500', '700', '900'].map(scale => `${color}-${scale}`)),
]

const fixedOptionLabels: Record<string, string> = {
  block: '块级布局',
  'inline-block': '行内块布局',
  flex: '弹性布局',
  'inline-flex': '行内弹性布局',
  inline: '行内布局',
  grid: '网格布局',
  hidden: '隐藏',
  static: '常规定位',
  relative: '相对定位',
  absolute: '绝对定位',
  fixed: '固定到视口',
  sticky: '滚动吸附',
  'flex-row': '水平排列',
  'flex-col': '垂直排列',
  'flex-wrap': '允许换行',
  'flex-nowrap': '保持单行',
  'items-start': '交叉轴起始对齐',
  'items-center': '交叉轴居中',
  'items-end': '交叉轴末端对齐',
  'items-stretch': '交叉轴拉伸',
  'justify-start': '主轴起始对齐',
  'justify-center': '主轴居中',
  'justify-end': '主轴末端对齐',
  'justify-between': '两端分散',
  'justify-around': '环绕分散',
  'text-left': '左对齐',
  'text-center': '居中对齐',
  'text-right': '右对齐',
  'font-normal': '常规字重',
  'font-medium': '中等字重',
  'font-semibold': '半粗字重',
  'font-bold': '粗体',
  'font-black': '特粗字重',
  'leading-none': '紧贴行高',
  'leading-tight': '紧凑行高',
  'leading-snug': '较紧行高',
  'leading-normal': '标准行高',
  'leading-relaxed': '舒展行高',
  'leading-loose': '宽松行高',
  'border-0': '无边框',
  border: '细边框',
  'border-2': '中等边框',
  'border-4': '粗边框',
  'border-solid': '实线边框',
  'border-dashed': '虚线边框',
  'border-dotted': '点线边框',
  'rounded-none': '无圆角',
  'rounded-sm': '轻微圆角',
  rounded: '默认圆角',
  'rounded-md': '中等圆角',
  'rounded-lg': '大圆角',
  'rounded-xl': '加大圆角',
  'rounded-2xl': '超大圆角',
  'rounded-3xl': '特大圆角',
  'rounded-full': '完全圆角',
  'shadow-none': '无阴影',
  'shadow-sm': '轻微阴影',
  shadow: '默认阴影',
  'shadow-md': '中等阴影',
  'shadow-lg': '大阴影',
  'shadow-xl': '加大阴影',
  'shadow-2xl': '超大阴影',
  'w-auto': '自动宽度',
  'w-full': '占满宽度',
  'w-screen': '视口宽度',
  'w-fit': '适应内容宽度',
  'h-auto': '自动高度',
  'h-full': '占满高度',
  'h-screen': '视口高度',
  'h-fit': '适应内容高度',
}

const textSizeLabels: Record<string, string> = {
  xs: '极小字号',
  sm: '小字号',
  base: '标准字号',
  lg: '大字号',
  xl: '加大字号',
  '2xl': '二级加大字号',
  '3xl': '三级加大字号',
  '4xl': '四级展示字号',
  '5xl': '五级展示字号',
  '6xl': '六级展示字号',
  '7xl': '七级展示字号',
  '8xl': '八级展示字号',
  '9xl': '最大展示字号',
}

/**
 * Editor 与 apply 引擎共同使用的 Tailwind visual catalog v1。
 */
export const runtimeVisualTailwindCatalog: VisualEditTailwindCatalog = {
  version: 1,
  groups: [
    group('display', '显示方式', ['block', 'inline-block', 'inline-flex', 'flex', 'inline', 'grid', 'hidden']),
    group('position', '定位方式', ['static', 'relative', 'absolute', 'fixed', 'sticky']),
    group('flex-direction', '主轴方向', ['flex-row', 'flex-col']),
    group('flex-wrap', '换行', ['flex-wrap', 'flex-nowrap']),
    group('items', '交叉轴对齐', ['items-start', 'items-center', 'items-end', 'items-stretch']),
    group('justify', '主轴对齐', [
      'justify-start',
      'justify-center',
      'justify-end',
      'justify-between',
      'justify-around',
    ]),
    group('grid-columns', '网格列数', numbered('grid-cols', ['1', '2', '3', '4', '5', '6', '8', '10', '12'])),
    group('gap', '整体间距', spacing('gap')),
    group('gap-x', '水平间距', spacing('gap-x')),
    group('gap-y', '垂直间距', spacing('gap-y')),
    group('padding', '内边距', spacing('p')),
    group('padding-x', '水平内边距', spacing('px')),
    group('padding-y', '垂直内边距', spacing('py')),
    group('margin', '外边距', spacing('m')),
    group('margin-x', '水平外边距', spacing('mx')),
    group('margin-y', '垂直外边距', spacing('my')),
    group('width', '宽度', [
      'w-auto',
      'w-full',
      'w-screen',
      'w-fit',
      ...numbered('w', sizeValues),
    ]),
    group('height', '高度', [
      'h-auto',
      'h-full',
      'h-screen',
      'h-fit',
      ...numbered('h', sizeValues),
    ]),
    group('size', '宽高', numbered('size', sizeValues)),
    group('text-size', '字号', numbered('text', [
      'xs', 'sm', 'base', 'lg', 'xl', '2xl', '3xl', '4xl', '5xl', '6xl', '7xl', '8xl', '9xl',
    ])),
    group('text-alignment', '文本对齐', ['text-left', 'text-center', 'text-right']),
    group('font-weight', '字重', ['font-normal', 'font-medium', 'font-semibold', 'font-bold', 'font-black']),
    group('line-height', '行高', [
      'leading-none', 'leading-tight', 'leading-snug', 'leading-normal', 'leading-relaxed', 'leading-loose',
    ]),
    group('text-color', '文字颜色', colors('text')),
    group('background-color', '背景颜色', colors('bg')),
    group('border-width', '边框宽度', ['border-0', 'border', 'border-2', 'border-4']),
    group('border-style', '边框样式', ['border-solid', 'border-dashed', 'border-dotted']),
    group('border-color', '边框颜色', colors('border')),
    group('radius', '圆角', [
      'rounded-none', 'rounded-sm', 'rounded', 'rounded-md', 'rounded-lg', 'rounded-xl',
      'rounded-2xl', 'rounded-3xl', 'rounded-full',
    ]),
    group('shadow', '阴影', [
      'shadow-none', 'shadow-sm', 'shadow', 'shadow-md', 'shadow-lg', 'shadow-xl', 'shadow-2xl',
    ]),
    group('opacity', '透明度', [
      'opacity-0', 'opacity-10', 'opacity-20', 'opacity-30', 'opacity-40', 'opacity-50',
      'opacity-60', 'opacity-70', 'opacity-80', 'opacity-90', 'opacity-100',
    ]),
  ],
}

/**
 * 按 key 查找可视化 Tailwind 组。
 */
export function findVisualTailwindGroup(groupKey: string): VisualEditTailwindCatalogGroup | undefined {
  return runtimeVisualTailwindCatalog.groups.find(candidate => candidate.key === groupKey)
}

/**
 * 构造目录组，并在模块加载时拒绝任何未被 Runtime safelist 覆盖的选项。
 */
function group(key: string, label: string, classNames: string[]): VisualEditTailwindCatalogGroup {
  const uniqueClassNames = [...new Set(classNames)]
  const unsupported = uniqueClassNames.filter(className => !safelistClasses.has(className))
  if (unsupported.length > 0) {
    throw new Error(`Tailwind visual catalog 包含未进入 Runtime safelist 的类：${unsupported.join(', ')}`)
  }
  return {
    key,
    label,
    options: uniqueClassNames.map(className => ({ className, label: formatOptionLabel(key, className) })),
  }
}

/**
 * 将协议 class 转为面向用户的选项名称，className 仅作为辅助信息和写入值。
 */
function formatOptionLabel(groupKey: string, className: string): string {
  if (fixedOptionLabels[className]) {
    return fixedOptionLabels[className]
  }
  if (['gap', 'gap-x', 'gap-y', 'padding', 'padding-x', 'padding-y', 'margin', 'margin-x', 'margin-y'].includes(groupKey)) {
    return `间距 ${className.slice(className.lastIndexOf('-') + 1)} 级`
  }
  if (groupKey === 'width' || groupKey === 'height' || groupKey === 'size') {
    return `尺寸 ${className.slice(className.lastIndexOf('-') + 1)} 级`
  }
  if (groupKey === 'grid-columns') {
    return `${className.slice(className.lastIndexOf('-') + 1)} 列网格`
  }
  if (groupKey === 'text-size') {
    const sizeToken = className.replace(/^text-/, '')
    if (textSizeLabels[sizeToken]) {
      return textSizeLabels[sizeToken]
    }
  }
  if (groupKey.endsWith('color')) {
    return formatColorLabel(className)
  }
  if (groupKey === 'opacity') {
    const percentage = className.replace(/^opacity-/, '')
    return percentage === '0'
      ? '完全透明'
      : percentage === '100' ? '完全不透明' : `不透明度 ${percentage}%`
  }
  throw new Error(`Tailwind visual catalog 缺少中文语义标签：${groupKey}/${className}`)
}

/**
 * 为主题语义色和常用色阶生成用户可读名称。
 */
function formatColorLabel(className: string): string {
  const colorToken = className.replace(/^(?:text|bg|border)-/, '')
  const semanticLabels: Record<string, string> = {
    transparent: '透明',
    white: '白色',
    black: '黑色',
    primary: '主题主色',
    secondary: '主题次色',
    invert: '反色文字',
    background: '主题背景',
    'background-subtle': '柔和背景',
    'background-invert': '反色背景',
    border: '主题边框',
    'border-subtle': '柔和边框',
  }
  if (semanticLabels[colorToken]) {
    return semanticLabels[colorToken]
  }
  const accentMatch = colorToken.match(/^accent([1-6])$/)
  if (accentMatch) {
    return `强调色 ${accentMatch[1]}`
  }
  const colorNames: Record<string, string> = {
    slate: '灰蓝',
    red: '红色',
    amber: '琥珀',
    green: '绿色',
    blue: '蓝色',
    violet: '紫色',
  }
  const scaleMatch = colorToken.match(/^([a-z]+)-(\d+)$/)
  if (scaleMatch && colorNames[scaleMatch[1]]) {
    return `${colorNames[scaleMatch[1]]} ${scaleMatch[2]} 色阶`
  }
  throw new Error(`Tailwind visual catalog 缺少颜色语义标签：${className}`)
}

/**
 * 生成常用间距类。
 */
function spacing(prefix: string): string[] {
  return numbered(prefix, spacingValues)
}

/**
 * 生成受控颜色类。
 */
function colors(prefix: 'text' | 'bg' | 'border'): string[] {
  return colorValues.map(color => `${prefix}-${color}`)
}

/**
 * 生成带统一前缀的候选类。
 */
function numbered(prefix: string, values: string[]): string[] {
  return values.map(value => `${prefix}-${value}`)
}
