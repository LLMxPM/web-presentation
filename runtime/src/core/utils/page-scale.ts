/**
 * 文件用途：统一计算页面内容作用域的 Tailwind 字号与间距 CSS 变量。
 */

import type { CSSProperties } from 'vue'

import { DEFAULT_PAGE_CONFIG } from '@/core/utils/config'

/**
 * 构造页面内容作用域的 Tailwind 字号与间距变量。
 * 说明：页面宽高是真实创作画布，不参与字号换算；基础字号只来自项目页面配置。
 * @returns 可绑定到页面内容容器的 CSS 变量
 */
export function buildPageContentScaleStyles(): CSSProperties {
  return {
    '--tw-font-size-base': `var(--theme-font-size-base, ${DEFAULT_PAGE_CONFIG.baseFontSize})`,
    ...buildPageSpacingScaleStyles(),
  } as CSSProperties
}

/**
 * 构造页面内容作用域的 Tailwind 间距变量。
 * @returns 可绑定到内容容器的间距 CSS 变量
 */
export function buildPageSpacingScaleStyles(): CSSProperties {
  return {
    '--tw-spacing-unit': 'calc(var(--tw-font-size-base) * 0.25)',
  } as CSSProperties
}
