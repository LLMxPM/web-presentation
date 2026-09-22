/**
 * 文件用途：验证 Runtime 全局样式中的 shell 字号基准不会被页面基础字号污染。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

describe('global runtime shell styles', () => {
  it('应使用固定 root 字号基准隔离 Runtime shell UI', () => {
    const css = readFileSync(resolve(process.cwd(), 'src/styles/global.css'), 'utf-8')
    const rootBlock = css.match(/:root\s*\{(?<body>[\s\S]*?)\n\}/)?.groups?.body || ''

    expect(rootBlock).toContain('--tw-font-size-base: 16px;')
    expect(rootBlock).not.toContain('--theme-font-size-base')
    expect(rootBlock).not.toContain('--tw-font-size-base: var(--theme-font-size-base')
  })

  it('应加载固定平台字体并作为主题变量默认值', () => {
    const css = readFileSync(resolve(process.cwd(), 'src/styles/global.css'), 'utf-8')
    const fontRegistry = readFileSync(resolve(process.cwd(), 'src/core/utils/font-registry.ts'), 'utf-8')

    expect(css).not.toContain("@import './platform-fonts.css';")
    expect(css).toContain("'Web Presentation Sans', sans-serif")
    expect(css).toContain("'Web Presentation Mono', monospace")
    expect(fontRegistry).toContain("SourceHanSansSC-VF.otf.woff2")
    expect(fontRegistry).toContain('font-weight: 100 900;')
  })
})
