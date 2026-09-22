// @vitest-environment jsdom

/**
 * 文件用途：验证 ThemeLogo 按主题配置渲染常规 Logo、反色 Logo 与空渲染行为。
 */

import { createApp, type App } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'

import { reloadThemeConfigs } from '@/core/composables/useTheme'
import { setRuntimePreloadedConfig, setRuntimePreviewContext } from '@/core/utils/path'

import ThemeLogo from './ThemeLogo.v1.vue'

afterEach(async () => {
  setRuntimePreviewContext(undefined)
  setRuntimePreloadedConfig({
    themes: {
      themes: {
        white: buildThemeConfig(),
      },
      default: {
        theme: 'white',
      },
    },
  })
  await reloadThemeConfigs()
  setRuntimePreloadedConfig(undefined)
  document.body.innerHTML = ''
})

describe('ThemeLogo', () => {
  it('默认应渲染当前主题的常规 Logo', async () => {
    await loadThemeWithLogo({
      logo: 'https://cdn.example.com/logo.svg',
      invertLogo: 'https://cdn.example.com/logo-invert.svg',
    })

    const { app, host } = mountThemeLogo()
    const img = host.querySelector('img') as HTMLImageElement | null

    expect(img?.getAttribute('src')).toBe('https://cdn.example.com/logo.svg')
    expect(img?.getAttribute('alt')).toBe('主题 Logo')

    app.unmount()
  })

  it('variant 为 invert 时应渲染当前主题的反色 Logo', async () => {
    await loadThemeWithLogo({
      logo: 'https://cdn.example.com/logo.svg',
      invertLogo: 'https://cdn.example.com/logo-invert.svg',
    })

    const { app, host } = mountThemeLogo({ variant: 'invert' })
    const img = host.querySelector('img') as HTMLImageElement | null

    expect(img?.getAttribute('src')).toBe('https://cdn.example.com/logo-invert.svg')
    expect(img?.getAttribute('alt')).toBe('主题反色 Logo')

    app.unmount()
  })

  it('没有对应主题 Logo 时应空渲染', async () => {
    await loadThemeWithLogo({})

    const { app, host } = mountThemeLogo()

    expect(host.querySelector('img')).toBeNull()
    expect(host.innerHTML).toBe('<!--v-if-->')

    app.unmount()
  })

  it('应使用单一 size 控制高度，并保持宽度自适应和不裁切', async () => {
    await loadThemeWithLogo({
      logo: 'https://cdn.example.com/logo.svg',
    })

    const { app, host } = mountThemeLogo({
      class: 'h-10 w-auto',
      style: { opacity: '0.8', width: '999px', objectFit: 'cover' },
      size: 12,
      alt: '',
      'data-testid': 'theme-logo',
    })
    const img = host.querySelector('img') as HTMLImageElement | null

    expect(img?.classList.contains('theme-logo')).toBe(true)
    expect(img?.classList.contains('h-10')).toBe(true)
    expect(img?.getAttribute('data-testid')).toBe('theme-logo')
    expect(img?.getAttribute('alt')).toBe('')
    expect(img?.style.width).toBe('auto')
    expect(img?.getAttribute('style')).toContain(
      'height: calc(var(--tw-spacing-unit, calc(var(--tw-font-size-base, 24px) * 0.25)) * 12)'
    )
    expect(img?.style.objectFit).toBe('contain')
    expect(img?.style.opacity).toBe('0.8')

    app.unmount()
  })

  it('size 支持直接传入 CSS 尺寸字符串', async () => {
    await loadThemeWithLogo({
      logo: 'https://cdn.example.com/logo.svg',
    })

    const { app, host } = mountThemeLogo({
      size: '48px',
    })
    const img = host.querySelector('img') as HTMLImageElement | null

    expect(img?.style.height).toBe('48px')
    expect(img?.style.width).toBe('auto')

    app.unmount()
  })
})

/**
 * 按指定 Logo 配置加载测试主题。
 * @param logoConfig 常规 Logo 与反色 Logo 配置
 */
async function loadThemeWithLogo(logoConfig: { logo?: string; invertLogo?: string }) {
  setRuntimePreloadedConfig({
    themes: {
      themes: {
        brand: buildThemeConfig(logoConfig),
      },
      default: {
        theme: 'brand',
      },
    },
  })
  await reloadThemeConfigs()
}

/**
 * 挂载 ThemeLogo 测试实例。
 * @param props 组件 props 与透传 attrs
 * @returns Vue 应用实例与宿主节点
 */
function mountThemeLogo(props: Record<string, unknown> = {}): { app: App<Element>, host: HTMLElement } {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const app = createApp(ThemeLogo, props)
  app.mount(host)
  return { app, host }
}

/**
 * 构造满足主题系统约束的最小主题配置。
 * @param logoConfig 常规 Logo 与反色 Logo 配置
 * @returns 测试主题配置
 */
function buildThemeConfig(logoConfig: { logo?: string; invertLogo?: string } = {}) {
  return {
    name: '品牌主题',
    description: '测试主题 Logo',
    ...logoConfig,
    palette: {
      text: { primary: '#111111', secondary: '#222222', invert: '#ffffff' },
      background: { default: '#ffffff', invert: '#111111' },
      border: { default: '#dddddd', subtle: '#cccccc' },
      link: { default: '#3b82f6', hover: '#2563eb', visited: '#7c3aed' },
      accent: ['#111111', '#222222', '#333333', '#444444', '#555555', '#666666'],
    },
    typography: {
      headingfont: 'system-ui',
      bodyfont: 'system-ui',
      codefont: 'monospace',
    },
  }
}
