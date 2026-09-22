/**
 * 文件用途：主题系统 Composable，统一处理预加载主题配置、只读 demo 回退与样式变量计算。
 */

import { computed, ref, type ComputedRef, type CSSProperties } from 'vue'

import { DEFAULT_PAGE_CONFIG, appConfig, loadYamlFromUrl } from '@/core/utils/config'
import { resolveThemeFontFamily } from '@/core/utils/font-registry'
import { buildConfigUrl, hasExternalConfigSource, resolveResourcePath, getRuntimePreloadedConfig, getRuntimePreviewContext } from '@/core/utils/path'

export type CustomTheme = string

const availableThemes = ref<string[]>(['white'])

/**
 * 主题调色板结构。
 */
export interface PaletteConfig {
  text: {
    primary: string
    secondary: string
    invert: string
  }
  background: {
    default: string
    invert: string
  }
  border: {
    default: string
    subtle: string
  }
  link: {
    default: string
    hover: string
    visited: string
  }
  accent: string[]
}

/**
 * 排印配置结构。
 */
export interface TypographyConfig {
  headingfont: string
  bodyfont: string
  codefont: string
  baseFontSize?: string
}

/**
 * 图标默认样式配置。
 */
export interface ThemeIconConfig {
  default_stroke_width: number
}

/**
 * 单个主题配置。
 */
export interface ThemeConfig {
  name: string
  description: string
  app?: {
    icon?: string
  }
  logo?: string
  invertLogo?: string
  palette: PaletteConfig
  typography: TypographyConfig
  icon?: ThemeIconConfig
}

/**
 * 样式变量映射结构。
 */
export interface ThemeStyles extends CSSProperties {
  '--theme-text-primary': string
  '--theme-text-secondary': string
  '--theme-text-invert': string
  '--theme-bg-default': string
  '--theme-bg-invert': string
  '--theme-border-default': string
  '--theme-border-subtle': string
  '--theme-link-default': string
  '--theme-link-hover': string
  '--theme-link-visited': string
  '--theme-font-heading': string
  '--theme-font-body': string
  '--theme-font-code': string
  '--theme-font-size-base': string
  '--theme-icon-default-stroke-width': string
  [key: `--theme-accent-${number}`]: string
}

/**
 * 主题配置文件结构。
 */
interface ThemeConfigFile {
  themes: Record<string, ThemeConfig>
  default?: {
    theme?: string
  }
}

type ResolvedThemeConfigFile = {
  themes: Record<string, ThemeConfig>
  default: {
    theme: string
  }
}

const themeConfigs = ref<Record<string, ThemeConfig> | null>(null)
const defaultTheme = ref<string>('white')

/**
 * 默认白色主题，作为本地 demo 的兜底配置。
 */
function buildDefaultThemeConfig(): ResolvedThemeConfigFile {
  return {
    themes: {
      white: {
        name: '白色经典',
        description: '纯净白色，简约经典',
        app: {
          icon: 'slider'
        },
        palette: {
          text: {
            primary: '#4f46e5',
            secondary: '#10b981',
            invert: '#9ca3af'
          },
          background: {
            default: '#ffffff',
            invert: '#f9fafb'
          },
          border: {
            default: '#e5e7eb',
            subtle: '#d1d5db'
          },
          link: {
            default: '#3b82f6',
            hover: '#2563eb',
            visited: '#7c3aed'
          },
          accent: ['#6366f1', '#34d399', '#fbbf24', '#f87171', '#60a5fa', '#a78bfa']
        },
        typography: {
          headingfont: 'platform-sans',
          bodyfont: 'platform-sans',
          codefont: 'platform-mono',
          baseFontSize: DEFAULT_PAGE_CONFIG.baseFontSize
        },
        icon: {
          default_stroke_width: DEFAULT_PAGE_CONFIG.iconDefaultStrokeWidth
        }
      }
    },
    default: {
      theme: 'white'
    }
  }
}

/**
 * 从预加载配置读取主题定义。
 * @returns 预加载主题配置；不存在时返回 undefined
 */
function getPreloadedThemeConfig(): ThemeConfigFile | undefined {
  return getRuntimePreloadedConfig()?.themes as ThemeConfigFile | undefined
}

/**
 * 判断当前是否为 SaaS 预览模式。
 * @returns 是否处于预览模式
 */
function isPreviewMode(): boolean {
  return Boolean(getRuntimePreviewContext())
}

/**
 * 将主题配置写入响应式状态。
 * @param config 主题配置文件结构
 */
function applyThemeConfig(config: ThemeConfigFile): void {
  const normalizedConfig = normalizeThemeConfig(config)
  themeConfigs.value = normalizedConfig.themes
  defaultTheme.value = normalizedConfig.default.theme
  availableThemes.value = Object.keys(normalizedConfig.themes)
}

/**
 * 规范化主题配置，确保缺省字段不会导致 Runtime 初始化失败。
 * @param rawConfig 原始主题配置
 * @returns 可安全消费的主题配置
 */
function normalizeThemeConfig(rawConfig: ThemeConfigFile): ResolvedThemeConfigFile {
  const fallbackConfig = buildDefaultThemeConfig()
  const rawThemes = rawConfig?.themes && typeof rawConfig.themes === 'object'
    ? rawConfig.themes
    : {}
  const fallbackTheme = fallbackConfig.themes.white
  const resolvedThemes = Object.fromEntries(
    Object.entries(rawThemes).map(([key, theme]) => [
      key,
      {
        ...theme,
        icon: theme?.icon
          ? {
              default_stroke_width: theme.icon.default_stroke_width ?? fallbackTheme.icon?.default_stroke_width ?? DEFAULT_PAGE_CONFIG.iconDefaultStrokeWidth
            }
          : undefined
      }
    ])
  )
  const themeKeys = Object.keys(resolvedThemes)
  if (themeKeys.length === 0) {
    return fallbackConfig
  }

  const candidateDefaultTheme = rawConfig?.default?.theme
  const resolvedDefaultTheme = candidateDefaultTheme && resolvedThemes[candidateDefaultTheme]
    ? candidateDefaultTheme
    : themeKeys[0]

  return {
    themes: resolvedThemes,
    default: {
      theme: resolvedDefaultTheme,
    },
  }
}

/**
 * 加载主题配置。
 */
export async function loadThemeConfigs(): Promise<void> {
  try {
    const preloadedConfig = getPreloadedThemeConfig()
    if (preloadedConfig) {
      applyThemeConfig(preloadedConfig)
      return
    }

    if (isPreviewMode()) {
      throw new Error('预览模式缺少必需的预加载主题配置。')
    }

    const configUrl = buildConfigUrl('themes')
    const yamlConfig = await loadYamlFromUrl<ThemeConfigFile>(configUrl, true)
    applyThemeConfig(yamlConfig)
  } catch (error) {
    if (hasExternalConfigSource() || isPreviewMode()) {
      console.error('加载主题配置失败：', error)
      throw error
    }

    console.warn('加载主题配置失败，回退到默认主题：', error)
    applyThemeConfig(buildDefaultThemeConfig())
  }
}

/**
 * 校验主题名是否存在。
 * @param theme 主题名称
 * @returns 是否可用
 */
export function isValidTheme(theme: string): boolean {
  return availableThemes.value.includes(theme)
}

/**
 * 获取可用主题列表。
 * @returns 主题键名数组
 */
export function getAvailableThemes(): string[] {
  return availableThemes.value
}

/**
 * 获取默认主题键名。
 * @returns 默认主题
 */
export function getDefaultTheme(): string {
  return defaultTheme.value
}

/**
 * 获取当前所有主题配置。
 * @returns 主题配置映射
 */
export function getThemeConfigs(): Record<string, ThemeConfig> | null {
  return themeConfigs.value
}

/**
 * 重新加载主题配置。
 */
export async function reloadThemeConfigs(): Promise<void> {
  themeConfigs.value = null
  await loadThemeConfigs()
}

/**
 * 使用主题配置并生成样式变量。
 * @param theme 主题名称或响应式主题名
 * @returns 主题相关计算属性和辅助方法
 */
export function useTheme(theme?: string | ComputedRef<string>) {
  if (!themeConfigs.value) {
    loadThemeConfigs()
  }

  const resolvedTheme = computed(() => {
    if (!theme) {
      return getDefaultTheme()
    }
    return typeof theme === 'string' ? theme : theme.value
  })

  const themeConfig = computed(() => {
    const currentTheme = resolvedTheme.value
    const configs = themeConfigs.value
    if (!configs) {
      return undefined
    }
    return configs[currentTheme] || configs.white
  })

  const themeClass = computed(() => {
    const currentTheme = resolvedTheme.value
    const configs = themeConfigs.value
    if (!configs) {
      return 'theme-white'
    }
    return `theme-${configs[currentTheme] ? currentTheme : 'white'}`
  })

  const themeStyles = computed((): ThemeStyles => {
    const config = themeConfig.value
    if (!config) {
      return {} as ThemeStyles
    }
    const pageVisualSpecs = resolvePageVisualSpecs(config)

    const styles: ThemeStyles = {
      '--theme-text-primary': config.palette.text.primary,
      '--theme-text-secondary': config.palette.text.secondary,
      '--theme-text-invert': config.palette.text.invert,
      '--theme-bg-default': config.palette.background.default,
      '--theme-bg-invert': config.palette.background.invert,
      '--theme-border-default': config.palette.border.default,
      '--theme-border-subtle': config.palette.border.subtle,
      '--theme-link-default': config.palette.link.default,
      '--theme-link-hover': config.palette.link.hover,
      '--theme-link-visited': config.palette.link.visited,
      '--theme-font-heading': resolveThemeFontFamily(config.typography.headingfont),
      '--theme-font-body': resolveThemeFontFamily(config.typography.bodyfont),
      '--theme-font-code': resolveThemeFontFamily(config.typography.codefont),
      '--theme-font-size-base': pageVisualSpecs.baseFontSize,
      '--theme-icon-default-stroke-width': String(pageVisualSpecs.iconDefaultStrokeWidth)
    } as ThemeStyles

    config.palette.accent.forEach((color, index) => {
      ;(styles as unknown as Record<string, string>)[`--theme-accent-${index + 1}`] = color
    })

    return styles
  })

  const themeLogo = computed(() => {
    const logoPath = String(themeConfig.value?.logo || '').trim()
    return logoPath ? resolveResourcePath(logoPath) : ''
  })

  const themeInvertLogo = computed(() => {
    const invertLogo = String(themeConfig.value?.invertLogo || '').trim()
    return invertLogo ? resolveResourcePath(invertLogo) : ''
  })

  return {
    themeConfig,
    themeClass,
    themeStyles,
    themeLogo,
    themeInvertLogo,
    loadThemeConfigs,
    reloadThemeConfigs,
    getThemeConfigs,
    getAvailableThemes,
    getDefaultTheme,
    isValidTheme
  }
}

/**
 * 解析项目页面默认视觉规格，兼容旧 themes.config.yaml 中的主题字段。
 * @param config 当前主题配置
 * @returns 可用于 CSS 变量和图标默认值的规格
 */
function resolvePageVisualSpecs(config: ThemeConfig): {
  baseFontSize: string
  iconDefaultStrokeWidth: number
} {
  const rawPageConfig = appConfig.value.app.page
  return {
    baseFontSize: normalizeBaseFontSize(
      rawPageConfig?.baseFontSize,
      normalizeBaseFontSize(config.typography.baseFontSize, DEFAULT_PAGE_CONFIG.baseFontSize),
    ),
    iconDefaultStrokeWidth: normalizePositiveNumber(
      rawPageConfig?.iconDefaultStrokeWidth,
      normalizePositiveNumber(config.icon?.default_stroke_width, DEFAULT_PAGE_CONFIG.iconDefaultStrokeWidth),
    ),
  }
}

/**
 * 将字号归一为 px 字符串。
 * @param value 原始字号
 * @param fallback 默认字号
 * @returns 可写入 CSS 变量的字号
 */
function normalizeBaseFontSize(value: unknown, fallback: string): string {
  const normalized = String(value || '').trim().toLowerCase()
  const match = normalized.match(/^(\d+)(px)?$/)
  if (!match) {
    return fallback
  }
  const numericValue = Number.parseInt(match[1], 10)
  if (!Number.isFinite(numericValue) || numericValue < 1 || numericValue > 200) {
    return fallback
  }
  return `${numericValue}px`
}

/**
 * 将规格数字归一为正数。
 * @param value 原始数值
 * @param fallback 默认值
 * @returns 合法正数
 */
function normalizePositiveNumber(value: unknown, fallback: number): number {
  const numericValue = Number(value)
  return Number.isFinite(numericValue) && numericValue > 0 ? numericValue : fallback
}
