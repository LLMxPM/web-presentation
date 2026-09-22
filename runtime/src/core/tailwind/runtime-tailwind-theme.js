/**
 * 文件用途：集中维护 Runtime Tailwind 主题扩展，供全局构建和预览按需编译共用。
 */

/**
 * 生成基于 CSS 变量的 Tailwind 间距刻度。
 * @returns Tailwind spacing 配置，默认 4 等于 1 个页面基础字号
 */
export const createDynamicSpacingScale = () => {
  const spacingKeys = [
    '0',
    '0.5',
    '1',
    '1.5',
    '2',
    '2.5',
    '3',
    '3.5',
    '4',
    '5',
    '6',
    '7',
    '8',
    '9',
    '10',
    '11',
    '12',
    '14',
    '16',
    '20',
    '24',
    '28',
    '32',
    '36',
    '40',
    '44',
    '48',
    '52',
    '56',
    '60',
    '64',
    '72',
    '80',
    '96',
  ]

  return {
    // 保持 Tailwind 的 px 语义，避免边框级细间距随页面字号放大。
    px: '1px',
    ...Object.fromEntries(
      spacingKeys.map((key) => [
        key,
        key === '0' ? '0px' : `calc(var(--tw-spacing-unit) * ${key})`,
      ]),
    ),
  }
}

/**
 * 生成基于 CSS 变量的 Tailwind 字号刻度，并保留 Tailwind 默认行高比例。
 * @returns Tailwind fontSize 配置，字号与行高都跟随页面基础字号变化
 */
export const createDynamicFontSizeScale = () => ({
  xs: ['calc(var(--tw-font-size-base) * 0.75)', { lineHeight: 'calc(var(--tw-font-size-base) * 1)' }],
  sm: ['calc(var(--tw-font-size-base) * 0.875)', { lineHeight: 'calc(var(--tw-font-size-base) * 1.25)' }],
  base: ['var(--tw-font-size-base)', { lineHeight: 'calc(var(--tw-font-size-base) * 1.5)' }],
  lg: ['calc(var(--tw-font-size-base) * 1.125)', { lineHeight: 'calc(var(--tw-font-size-base) * 1.75)' }],
  xl: ['calc(var(--tw-font-size-base) * 1.25)', { lineHeight: 'calc(var(--tw-font-size-base) * 1.75)' }],
  '2xl': ['calc(var(--tw-font-size-base) * 1.5)', { lineHeight: 'calc(var(--tw-font-size-base) * 2)' }],
  '3xl': ['calc(var(--tw-font-size-base) * 1.875)', { lineHeight: 'calc(var(--tw-font-size-base) * 2.25)' }],
  '4xl': ['calc(var(--tw-font-size-base) * 2.25)', { lineHeight: 'calc(var(--tw-font-size-base) * 2.5)' }],
  '5xl': ['calc(var(--tw-font-size-base) * 3)', { lineHeight: '1' }],
  '6xl': ['calc(var(--tw-font-size-base) * 3.75)', { lineHeight: '1' }],
  '7xl': ['calc(var(--tw-font-size-base) * 4.5)', { lineHeight: '1' }],
  '8xl': ['calc(var(--tw-font-size-base) * 6)', { lineHeight: '1' }],
  '9xl': ['calc(var(--tw-font-size-base) * 8)', { lineHeight: '1' }],
})

/**
 * 创建基于 CSS 变量的主题色阶。
 * @param {string} cssVar 主题 CSS 变量名
 * @returns Tailwind 色阶配置
 */
const createColorScale = (cssVar) => ({
  50: `rgb(from var(${cssVar}) calc(r + (255 - r) * 0.9) calc(g + (255 - g) * 0.9) calc(b + (255 - b) * 0.9) / <alpha-value>)`,
  100: `rgb(from var(${cssVar}) calc(r + (255 - r) * 0.8) calc(g + (255 - g) * 0.8) calc(b + (255 - b) * 0.8) / <alpha-value>)`,
  200: `rgb(from var(${cssVar}) calc(r + (255 - r) * 0.65) calc(g + (255 - g) * 0.65) calc(b + (255 - b) * 0.65) / <alpha-value>)`,
  300: `rgb(from var(${cssVar}) calc(r + (255 - r) * 0.5) calc(g + (255 - g) * 0.5) calc(b + (255 - b) * 0.5) / <alpha-value>)`,
  400: `rgb(from var(${cssVar}) calc(r + (255 - r) * 0.3) calc(g + (255 - g) * 0.3) calc(b + (255 - b) * 0.3) / <alpha-value>)`,
  500: `rgb(from var(${cssVar}) r g b / <alpha-value>)`,
  600: `rgb(from var(${cssVar}) calc(r * 0.85) calc(g * 0.85) calc(b * 0.85) / <alpha-value>)`,
  700: `rgb(from var(${cssVar}) calc(r * 0.7) calc(g * 0.7) calc(b * 0.7) / <alpha-value>)`,
  800: `rgb(from var(${cssVar}) calc(r * 0.55) calc(g * 0.55) calc(b * 0.55) / <alpha-value>)`,
  900: `rgb(from var(${cssVar}) calc(r * 0.4) calc(g * 0.4) calc(b * 0.4) / <alpha-value>)`,
  DEFAULT: `rgb(from var(${cssVar}) r g b / <alpha-value>)`,
})

export const runtimeTailwindTheme = {
  container: {
    center: true,
  },
  extend: {
    colors: {
      primary: createColorScale('--tw-color-text-primary'),
      secondary: createColorScale('--tw-color-text-secondary'),
      invert: createColorScale('--tw-color-text-invert'),
      default: createColorScale('--tw-color-bg-default'),
      background: {
        ...createColorScale('--tw-color-bg-default'),
        subtle: createColorScale('--tw-color-bg-subtle'),
        invert: createColorScale('--tw-color-bg-invert'),
      },
      border: {
        ...createColorScale('--tw-color-border-default'),
        subtle: createColorScale('--tw-color-border-subtle'),
      },
      link: {
        ...createColorScale('--tw-color-link-default'),
        hover: createColorScale('--tw-color-link-hover'),
        visited: createColorScale('--tw-color-link-visited'),
      },
      accent1: createColorScale('--tw-color-accent1'),
      accent2: createColorScale('--tw-color-accent2'),
      accent3: createColorScale('--tw-color-accent3'),
      accent4: createColorScale('--tw-color-accent4'),
      accent5: createColorScale('--tw-color-accent5'),
      accent6: createColorScale('--tw-color-accent6'),
    },
    fontFamily: {
      heading: ['var(--tw-font-heading)', 'sans-serif'],
      body: ['var(--tw-font-body)', 'sans-serif'],
      code: ['var(--tw-font-code)', 'monospace'],
    },
    fontSize: createDynamicFontSizeScale(),
    spacing: createDynamicSpacingScale(),
  },
}
