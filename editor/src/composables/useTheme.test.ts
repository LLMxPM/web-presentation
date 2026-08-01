/**
 * 文件功能：验证全局主题偏好持久化、实际模式解析与系统配色变更响应。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

interface MatchMediaController {
  setMatches: (matches: boolean) => void
}

describe('useTheme', () => {
  beforeEach(() => {
    vi.resetModules()
    window.localStorage.clear()
    document.documentElement.classList.remove('dark')
    document.documentElement.style.colorScheme = ''
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('无已保存偏好时应默认跟随系统', async () => {
    installMatchMedia(true)
    const { useTheme } = await import('@/composables/useTheme')

    const theme = useTheme()

    expect(theme.preference.value).toBe('system')
    expect(theme.mode.value).toBe('dark')
    expect(document.documentElement).toHaveClass('dark')
    expect(document.documentElement.style.colorScheme).toBe('dark')
  })

  it('跟随系统时应响应系统配色变化', async () => {
    const media = installMatchMedia(false)
    const { useTheme } = await import('@/composables/useTheme')
    const theme = useTheme()

    media.setMatches(true)

    expect(theme.mode.value).toBe('dark')
    expect(theme.isDark.value).toBe(true)
    expect(document.documentElement).toHaveClass('dark')
  })

  it('固定主题偏好不应被系统配色变化覆盖', async () => {
    const media = installMatchMedia(false)
    const { useTheme } = await import('@/composables/useTheme')
    const theme = useTheme()

    theme.setMode('light')
    media.setMatches(true)

    expect(theme.preference.value).toBe('light')
    expect(theme.mode.value).toBe('light')
    expect(window.localStorage.getItem('editor-theme-mode')).toBe('light')
    expect(document.documentElement).not.toHaveClass('dark')
  })
})

/** 安装可主动触发 change 事件的 matchMedia 测试替身。 */
function installMatchMedia(initialMatches: boolean): MatchMediaController {
  let matches = initialMatches
  const listeners = new Set<(event: MediaQueryListEvent) => void>()
  const mediaQuery = {
    get matches() {
      return matches
    },
    media: '(prefers-color-scheme: dark)',
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn((_type: string, listener: (event: MediaQueryListEvent) => void) => listeners.add(listener)),
    removeEventListener: vi.fn((_type: string, listener: (event: MediaQueryListEvent) => void) => listeners.delete(listener)),
    dispatchEvent: vi.fn(() => false),
  }
  vi.stubGlobal('matchMedia', vi.fn(() => mediaQuery))
  return {
    setMatches(nextMatches: boolean) {
      matches = nextMatches
      listeners.forEach(listener => listener({ matches } as MediaQueryListEvent))
    },
  }
}
