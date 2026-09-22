/**
 * 文件用途：声明 Runtime Tailwind 主题扩展配置的公开类型。
 */

import type { Config } from 'tailwindcss'

export const createDynamicFontSizeScale: () => Record<string, [string, { lineHeight: string }]>
export const createDynamicSpacingScale: () => Record<string, string>
export const runtimeTailwindTheme: NonNullable<Config['theme']>
