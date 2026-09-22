/**
 * 文件用途：验证 Runtime 整项目构建 helper 的 baseUrl 规范化与静态资源路径推导逻辑。
 */

import { mkdtemp, mkdir, rm, writeFile } from 'fs/promises'
import os from 'os'
import { join, resolve } from 'path'

import postcss, { type AcceptedPlugin } from 'postcss'
import { describe, expect, it } from 'vitest'

import {
  createBuildReleaseViewModulesSource,
  createDiagnosticsBuildModulesSource,
  buildRuntimeBuildCssConfig,
  buildStaticAssetPath,
  hasForbiddenRootAbsoluteAssetPath,
  normalizeBuildBaseUrl,
  stripInspectableComments,
} from './runtime-build-runner.helpers'

describe('runtime build runner helpers', () => {
  it('Tailwind content 应覆盖构建工作区注入的页面和工作空间组件模块', async () => {
    const tailwindConfigModulePath = '../../../tailwind.config.js'
    const tailwindConfig = await import(tailwindConfigModulePath) as {
      default: {
        content?: {
          relative?: boolean
          files?: string[]
        }
      }
    }

    expect(tailwindConfig.default.content?.relative).toBe(true)
    expect(tailwindConfig.default.content?.files).toEqual(expect.arrayContaining([
      './src/**/*.{js,ts,vue}',
    ]))
  })

  it('临时构建工作区应按自身 Tailwind 配置扫描注入页面源码', async () => {
    const tempRoot = await createTailwindBuildFixture()
    try {
      const cssConfig = buildRuntimeBuildCssConfig(tempRoot)
      const postcssConfig = cssConfig.postcss as { plugins?: AcceptedPlugin[] }
      const result = await postcss(postcssConfig.plugins || []).process('@tailwind utilities;', {
        from: resolve(tempRoot, 'src/styles.css'),
      })
      const css = result.css

      expect(css).toContain('.w-1\\/3')
      expect(css).toMatch(/width:\s*33\.333333%/)
      expect(css).toContain('.w-2\\/3')
      expect(css).toMatch(/width:\s*66\.666667%/)
      expect(css).toMatch(/background-color:\s*rgb\(18 52 86/)
    } finally {
      await rm(tempRoot, { recursive: true, force: true })
    }
  })

  it('应规范化构建 baseUrl', () => {
    expect(normalizeBuildBaseUrl(undefined)).toBe('./')
    expect(normalizeBuildBaseUrl('./')).toBe('./')
    expect(normalizeBuildBaseUrl('/demo')).toBe('/demo/')
    expect(normalizeBuildBaseUrl('/nested/path/')).toBe('/nested/path/')
  })

  it('应拒绝非法的构建 baseUrl', () => {
    expect(() => normalizeBuildBaseUrl('https://example.com/demo')).toThrow('base_url')
    expect(() => normalizeBuildBaseUrl('//cdn.example.com/demo')).toThrow('base_url')
    expect(() => normalizeBuildBaseUrl('demo')).toThrow('base_url')
  })

  it('应优先使用原始文件名或逻辑名推导静态资源扩展名', () => {
    expect(buildStaticAssetPath('hash-logo', 'logo.svg')).toBe('__build_assets/hash-logo.svg')
    expect(buildStaticAssetPath('hash-photo', undefined, 'img/photo/banner.webp')).toBe(
      '__build_assets/hash-photo.webp',
    )
    expect(buildStaticAssetPath('hash-font')).toBe('__build_assets/hash-font')
  })

  it('应按 manifest 生成 build release 页面模块映射', () => {
    const source = createBuildReleaseViewModulesSource([
      'src/views/Home.vue',
      '@/views/Nested/About.vue',
      '/src/views/Home.vue',
      'src/workspace-components/Card/v/1.vue',
      'src/examples/local/views/Demo.vue',
      'src/views/../runtime-shell/fallback/NotFoundPage.vue',
    ])

    expect(source).toContain('"@/views/Home.vue": () => import("@/views/Home.vue")')
    expect(source).toContain('"/src/views/Home.vue": () => import("@/views/Home.vue")')
    expect(source).toContain('"@/views/Nested/About.vue": () => import("@/views/Nested/About.vue")')
    expect(source).not.toContain('workspace-components')
    expect(source).not.toContain('examples/local')
    expect(source).not.toContain('runtime-shell')
  })

  it('应按 manifest 生成 diagnostics 页面与工作空间组件模块加载器', () => {
    const source = createDiagnosticsBuildModulesSource([
      'src/views/Home.vue',
      '@/views/Nested/About.vue',
      '/src/views/Home.vue',
      '@workspace-components/Card/v/1',
      'src/workspace-components/Chart/v/2.vue',
      '@runtime-kit/public/components/assets/AssetImage.v1.vue',
      'src/examples/local/views/Demo.vue',
      'src/views/../runtime-shell/fallback/NotFoundPage.vue',
    ])

    expect(source).toContain('BUILD_DIAGNOSTICS_MODULE_LOADERS')
    expect(source).toContain('() => import("@/views/Home.vue")')
    expect(source).toContain('() => import("@/views/Nested/About.vue")')
    expect(source).toContain('() => import("@workspace-components/Card/v/1")')
    expect(source).toContain('() => import("@workspace-components/Chart/v/2")')
    expect(source).not.toContain('@runtime-kit')
    expect(source).not.toContain('examples/local')
    expect(source).not.toContain('runtime-shell')
  })

  it('缺少资源 hash 时应抛错', () => {
    expect(() => buildStaticAssetPath('')).toThrow('资源 hash')
  })

  it('应识别真实源码中的根绝对静态资源引用', () => {
    expect(hasForbiddenRootAbsoluteAssetPath("const icon = { src: '/img/logo/custom-logo.svg' }")).toBe(true)
    expect(hasForbiddenRootAbsoluteAssetPath(".hero { background-image: url('/img/bg.png'); }")).toBe(true)
  })

  it('应忽略注释中的根绝对静态资源示例', () => {
    const sourceCode = [
      "// src: '/img/logo/custom-logo.svg'",
      "/* url('/img/background.png') */",
      "<!-- <img src=\"/img/demo.png\" /> -->",
      "const icon = { src: './img/logo.svg' }",
    ].join('\n')

    const sanitizedCode = stripInspectableComments(sourceCode)

    expect(sanitizedCode).not.toContain("'/img/")
    expect(sanitizedCode).not.toContain('"/img/')
    expect(hasForbiddenRootAbsoluteAssetPath(sourceCode)).toBe(false)
  })
})

/**
 * 创建最小 Vue/Tailwind 临时构建工作区。
 * @returns 临时工作区路径
 */
async function createTailwindBuildFixture(): Promise<string> {
  const tempRoot = await mkdtemp(join(os.tmpdir(), 'runtime-tailwind-build-'))
  await mkdir(resolve(tempRoot, 'src/views'), { recursive: true })

  await writeFile(
    resolve(tempRoot, 'index.html'),
    '<div id="app"></div><script type="module" src="/src/main.ts"></script>',
    'utf-8',
  )
  await writeFile(
    resolve(tempRoot, 'src/main.ts'),
    [
      "import { createApp } from 'vue'",
      "import Page from './views/Page.vue'",
      "import './styles.css'",
      "createApp(Page).mount('#app')",
    ].join('\n'),
    'utf-8',
  )
  await writeFile(resolve(tempRoot, 'src/styles.css'), '@tailwind utilities;', 'utf-8')
  await writeFile(
    resolve(tempRoot, 'src/views/Page.vue'),
    '<template><div class="w-1/3 w-2/3 bg-probe-500"><span>ok</span></div></template>',
    'utf-8',
  )
  await writeFile(
    resolve(tempRoot, 'tailwind.config.js'),
    [
      'export default {',
      '  content: {',
      '    relative: true,',
      "    files: ['./index.html', './src/**/*.{js,ts,vue}'],",
      '  },',
      "  safelist: ['bg-probe-500'],",
      "  theme: { extend: { colors: { probe: { 500: '#123456' } } } },",
      '  plugins: [],',
      '}',
    ].join('\n'),
    'utf-8',
  )

  return tempRoot
}
