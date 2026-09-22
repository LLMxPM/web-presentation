// @vitest-environment jsdom

/**
 * 文件用途：验证运行时动态字体注册与主题字体引用解析逻辑。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { reloadThemeConfigs, useTheme } from '@/core/composables/useTheme'

import {
  initializeRuntimeFontRegistry,
  resolveAssetFontFamily,
  resolveThemeFontFamily,
  waitForRequiredPlatformFonts,
} from './font-registry'
import { loadAppConfig } from './config'
import { setRuntimePreloadedConfig, setRuntimePreviewContext } from './path'

beforeEach(() => {
  vi.stubGlobal('window', window)
  document.head.innerHTML = ''
  document.body.innerHTML = ''
})

afterEach(async () => {
  Reflect.deleteProperty(document, 'fonts')
  setRuntimePreviewContext(undefined)
  setRuntimePreloadedConfig({
    app: {
      app: {
        icon: 'slider',
        title: '测试项目',
        description: '测试重置项目',
          page: {
            width: 1920,
            height: 1080,
            baseFontSize: '16px',
            iconDefaultStrokeWidth: 2,
          },
      },
    },
    themes: {
      themes: {
        white: {
          name: '白色经典',
          description: '测试重置主题',
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
            baseFontSize: '16px',
          },
        },
      },
      default: {
        theme: 'white',
      },
    },
  })
  await loadAppConfig(true)
  await reloadThemeConfigs()
  setRuntimePreloadedConfig(undefined)
  vi.unstubAllGlobals()
})

describe('runtime font registry', () => {
  it('应通过 Runtime 模块地址注册固定平台字体，避免相对预览文档 origin 加载', () => {
    const cssText = initializeRuntimeFontRegistry()
    const styleElement = document.getElementById('runtime-dynamic-fonts')

    expect(styleElement).not.toBeNull()
    expect(cssText).toContain("font-family: 'Web Presentation Sans'")
    expect(cssText).toContain('SourceHanSansSC-VF.otf.woff2')
    expect(cssText).toContain("font-family: 'Web Presentation Mono'")
    expect(cssText).toContain('SourceCodePro-Regular.ttf.woff2')
    expect(cssText).not.toContain("url('/src/assets/runtime-shell/fonts/")
  })

  it('应主动加载主题引用的平台字体并验证可用性', async () => {
    const load = vi.fn().mockResolvedValue([])
    const check = vi.fn().mockReturnValue(true)
    Object.defineProperty(document, 'fonts', {
      configurable: true,
      value: { load, check },
    })
    setRuntimePreloadedConfig({
      themes: {
        themes: {
          lightblue: {
            typography: {
              headingfont: 'platform-sans',
              bodyfont: 'platform-sans',
              codefont: 'platform-mono',
            },
          },
        },
      },
    })

    await waitForRequiredPlatformFonts()

    expect(load).toHaveBeenCalledTimes(2)
    expect(check).toHaveBeenCalledTimes(2)
  })

  it('应根据预加载字体配置注入动态 @font-face', () => {
    setRuntimePreviewContext({
      artifactId: 'artifact_font',
      tenantId: 'tenant_font',
      previewKind: 'project',
      scopeType: 'project',
      workspaceId: 'workspace_font',
      projectId: 'project_font',
      entryDescriptor: { entry_type: 'route', route: '/home' },
      assetBaseUrl: 'https://assets.example/runtime-font',
      traceId: 'trace_font',
    })
    setRuntimePreloadedConfig({
      manifest: {
        artifact_id: 'artifact_font',
        artifact_kind: 'preview_artifact',
        tenant_id: 'tenant_font',
        preview_kind: 'project',
        asset_base_url: 'https://assets.example/runtime-font',
        owner_scope: {
          scope_type: 'project',
          project_id: 'project_font',
          workspace_id: 'workspace_font',
        },
        entry_descriptor: { entry_type: 'route', route: '/home' },
        project_id: 'project_font',
        modules: {},
        assets: {
          'SourceHanSansSC-VF': 'hash-source-han-sans',
        },
      },
      fonts: {
        items: {
          'SourceHanSansSC-VF': {
            asset_name: 'SourceHanSansSC-VF',
            font_family: '思源黑体',
            font_format: 'woff2',
            font_weight: '100 900',
            font_style: 'normal',
            font_display: 'swap',
          },
        },
      },
    })

    const cssText = initializeRuntimeFontRegistry()
    const styleElement = document.getElementById('runtime-dynamic-fonts')

    expect(styleElement).not.toBeNull()
    expect(cssText).toContain("font-family: '思源黑体'")
    expect(cssText).toContain("url('https://assets.example/runtime-font/hash-source-han-sans')")
    expect(cssText).toContain("font-weight: 100 900;")
  })

  it('应为同一字体族的多个 face 生成多条 @font-face 并原样写入范围字重', () => {
    setRuntimePreviewContext({
      artifactId: 'artifact_family',
      tenantId: 'tenant_family',
      previewKind: 'project',
      scopeType: 'project',
      workspaceId: 'workspace_family',
      projectId: 'project_family',
      entryDescriptor: { entry_type: 'route', route: '/home' },
      assetBaseUrl: 'https://assets.example/runtime-family',
      traceId: 'trace_family',
    })
    setRuntimePreloadedConfig({
      manifest: {
        artifact_id: 'artifact_family',
        artifact_kind: 'preview_artifact',
        tenant_id: 'tenant_family',
        preview_kind: 'project',
        asset_base_url: 'https://assets.example/runtime-family',
        owner_scope: {
          scope_type: 'project',
          project_id: 'project_family',
          workspace_id: 'workspace_family',
        },
        entry_descriptor: { entry_type: 'route', route: '/home' },
        project_id: 'project_family',
        modules: {},
        assets: {
          'SourceHanSans-Regular': 'hash-han-regular',
          'SourceHanSans-Bold': 'hash-han-bold',
          'SourceHanSans-VF': 'hash-han-vf',
        },
      },
      fonts: {
        items: {
          'SourceHanSans-Regular': {
            asset_name: 'SourceHanSans-Regular',
            font_family: '思源黑体',
            font_format: 'woff2',
            font_weight: '400',
            font_style: 'normal',
            font_display: 'swap',
          },
          'SourceHanSans-Bold': {
            asset_name: 'SourceHanSans-Bold',
            font_family: '思源黑体',
            font_format: 'woff2',
            font_weight: '700',
            font_style: 'normal',
            font_display: 'swap',
          },
          'SourceHanSans-VF': {
            asset_name: 'SourceHanSans-VF',
            font_family: '思源黑体',
            font_format: 'woff2',
            font_weight: '100 900',
            font_style: 'normal',
            font_display: 'swap',
          },
        },
      },
    })

    const cssText = initializeRuntimeFontRegistry()

    // 同一字体族的三个 face 应各自生成一条 @font-face
    expect(cssText.match(/@font-face/g)).toHaveLength(5)
    expect(cssText.match(/font-family: '思源黑体';/g)).toHaveLength(3)
    expect(cssText).toContain("url('https://assets.example/runtime-family/hash-han-regular')")
    expect(cssText).toContain("url('https://assets.example/runtime-family/hash-han-bold')")
    expect(cssText).toContain("url('https://assets.example/runtime-family/hash-han-vf')")
    // 每个 face 的字重原样写入，范围字重不被拆分或改写
    expect(cssText).toContain('font-weight: 400;')
    expect(cssText).toContain('font-weight: 700;')
    expect(cssText).toContain('font-weight: 100 900;')
  })

  it('应先按 asset_name 再按历史 font_family 解析主题字体引用', () => {
    setRuntimePreloadedConfig({
      fonts: {
        items: {
          'SourceHanSansSC-VF': {
            asset_name: 'SourceHanSansSC-VF',
            font_family: '思源黑体',
            font_format: 'woff2',
            font_weight: '400',
            font_style: 'normal',
            font_display: 'swap',
          },
        },
      },
    })

    expect(resolveThemeFontFamily('SourceHanSansSC-VF')).toBe('思源黑体')
    expect(resolveThemeFontFamily('思源黑体')).toBe('思源黑体')
    expect(resolveThemeFontFamily('system-ui')).toBe('system-ui')
    expect(resolveThemeFontFamily('platform-sans')).toBe("'Web Presentation Sans', sans-serif")
    expect(resolveThemeFontFamily('platform-mono')).toBe("'Web Presentation Mono', monospace")
  })

  it('主题 token 为字体族名时应命中该族下任意 face 并解析为族名', () => {
    setRuntimePreloadedConfig({
      fonts: {
        items: {
          'SourceHanSans-Regular': {
            asset_name: 'SourceHanSans-Regular',
            font_family: '思源黑体',
            font_format: 'woff2',
            font_weight: '400',
            font_style: 'normal',
            font_display: 'swap',
          },
          'SourceHanSans-Bold': {
            asset_name: 'SourceHanSans-Bold',
            font_family: '思源黑体',
            font_format: 'woff2',
            font_weight: '700',
            font_style: 'normal',
            font_display: 'swap',
          },
        },
      },
    })

    // 主题下发字体族名，Runtime 无需改动即可命中该族并解析为族名
    expect(resolveThemeFontFamily('思源黑体')).toBe('思源黑体')
    // 仍兼容按单个 face 的 asset_name 命中
    expect(resolveThemeFontFamily('SourceHanSans-Bold')).toBe('思源黑体')
  })

  it('应按字体资源逻辑名解析页面显式声明字体', () => {
    setRuntimePreloadedConfig({
      fonts: {
        items: {
          'BrandSerif': {
            asset_name: 'BrandSerif',
            font_family: 'Brand Serif',
            font_format: 'woff2',
            font_weight: '400',
            font_style: 'normal',
            font_display: 'swap',
          },
        },
      },
    })

    expect(resolveAssetFontFamily('BrandSerif', 'sans-serif')).toBe('Brand Serif')
    expect(resolveAssetFontFamily('./BrandSerif', 'sans-serif')).toBe('Brand Serif')
    expect(resolveAssetFontFamily('MissingFont', 'sans-serif')).toBe('sans-serif')
  })

  it('useTheme 应把主题中的字体资源名解析为实际 font-family', async () => {
    setRuntimePreloadedConfig({
      themes: {
        themes: {
          lightblue: {
            name: '白底蓝色',
            description: '测试主题',
            palette: {
              text: { primary: '#111111', secondary: '#222222', invert: '#ffffff' },
              background: { default: '#ffffff', invert: '#111111' },
              border: { default: '#dddddd', subtle: '#cccccc' },
              link: { default: '#3b82f6', hover: '#2563eb', visited: '#7c3aed' },
              accent: ['#111111', '#222222', '#333333', '#444444', '#555555', '#666666'],
            },
            typography: {
              headingfont: 'SourceHanSansSC-VF',
              bodyfont: '思源黑体',
              codefont: 'SourceCodePro-Regular',
              baseFontSize: '16px',
            },
          },
        },
        default: {
          theme: 'lightblue',
        },
      },
      fonts: {
        items: {
          'SourceHanSansSC-VF': {
            asset_name: 'SourceHanSansSC-VF',
            font_family: '思源黑体',
            font_format: 'woff2',
            font_weight: '100 900',
            font_style: 'normal',
            font_display: 'swap',
          },
          'SourceCodePro-Regular': {
            asset_name: 'SourceCodePro-Regular',
            font_family: 'SourceCodePro',
            font_format: 'woff2',
            font_weight: '400',
            font_style: 'normal',
            font_display: 'swap',
          },
        },
      },
    })

    await reloadThemeConfigs()
    const { themeStyles } = useTheme('lightblue')

    expect(themeStyles.value['--theme-font-heading']).toBe('思源黑体')
    expect(themeStyles.value['--theme-font-body']).toBe('思源黑体')
    expect(themeStyles.value['--theme-font-code']).toBe('SourceCodePro')
  })

  it('useTheme 无字体包时应直接使用浏览器默认字体族', async () => {
    setRuntimePreloadedConfig({
      app: {
        app: {
          icon: 'slider',
          title: '浏览器默认字体项目',
          description: '测试无字体包主题',
          page: {
            width: 1440,
            height: 900,
            baseFontSize: '20px',
            iconDefaultStrokeWidth: 2,
          },
        },
      },
      themes: {
        themes: {
          browserDefault: {
            name: '浏览器默认字体',
            description: '测试主题',
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
          },
        },
        default: {
          theme: 'browserDefault',
        },
      },
    })

    await loadAppConfig(true)
    await reloadThemeConfigs()
    const { themeStyles } = useTheme('browserDefault')

    expect(themeStyles.value['--theme-font-heading']).toBe('system-ui')
    expect(themeStyles.value['--theme-font-body']).toBe('system-ui')
    expect(themeStyles.value['--theme-font-code']).toBe('monospace')
  })

  it('useTheme 应优先使用 app.page 提供的字号与默认图标规格', async () => {
    setRuntimePreloadedConfig({
      app: {
        app: {
          icon: 'slider',
          title: '页面规格项目',
          description: '测试项目页面规格',
          page: {
            width: 1440,
            height: 900,
            baseFontSize: '18px',
            iconDefaultStrokeWidth: 3,
          },
        },
      },
      themes: {
        themes: {
          lightblue: {
            name: '白底蓝色',
            description: '测试主题',
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
              baseFontSize: '12px',
            },
            icon: {
              default_stroke_width: 1,
            },
          },
        },
        default: {
          theme: 'lightblue',
        },
      },
    })

    await loadAppConfig(true)
    await reloadThemeConfigs()
    const { themeStyles } = useTheme('lightblue')

    expect(themeStyles.value['--theme-font-size-base']).toBe('18px')
    expect(themeStyles.value['--theme-icon-default-stroke-width']).toBe('3')
  })
})
