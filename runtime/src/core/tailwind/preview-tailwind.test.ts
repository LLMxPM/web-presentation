/**
 * 文件用途：验证预览 artifact Tailwind utilities 按需编译与缓存签名。
 */

import { describe, expect, it } from 'vitest'

import {
  buildPreviewTailwindCacheSignature,
  compilePreviewTailwindUtilities,
  inferTailwindRawExtension,
} from './preview-tailwind'

describe('preview tailwind utilities', () => {
  it('应从远程 Vue SFC 源码生成常用布局、背景和主题 utilities', async () => {
    const css = await compilePreviewTailwindUtilities([
      {
        logicalPath: 'src/views/CoverPage.vue',
        content: `
          <template>
            <section class="relative h-full w-full overflow-hidden">
              <div class="absolute inset-0 bg-cover bg-center bg-no-repeat pt-16 text-invert from-background-invert/80"></div>
            </section>
          </template>
        `,
      },
    ])

    expect(css).toContain('.pt-16')
    expect(css).toContain('.bg-cover')
    expect(css).toContain('.bg-no-repeat')
    expect(css).toContain('.text-invert')
    expect(css).toContain('.from-background-invert\\/80')
  })

  it('应为动态字号类生成与 Tailwind 默认比例一致的行高', async () => {
    const css = await compilePreviewTailwindUtilities([
      {
        logicalPath: 'src/views/TypographyPage.vue',
        content: `
          <template>
            <section>
              <p class="text-base">正文</p>
              <span class="size-4"></span>
              <p class="text-xl">强调正文</p>
              <h1 class="text-4xl">标题</h1>
            </section>
          </template>
        `,
      },
    ])

    expect(css).toContain('font-size: var(--tw-font-size-base)')
    expect(css).toContain('width: calc(var(--tw-spacing-unit) * 4)')
    expect(css).toContain('height: calc(var(--tw-spacing-unit) * 4)')
    expect(css).toContain('line-height: calc(var(--tw-font-size-base) * 1.5)')
    expect(css).toContain('font-size: calc(var(--tw-font-size-base) * 1.25)')
    expect(css).toContain('line-height: calc(var(--tw-font-size-base) * 1.75)')
    expect(css).toContain('font-size: calc(var(--tw-font-size-base) * 2.25)')
    expect(css).toContain('line-height: calc(var(--tw-font-size-base) * 2.5)')
  })

  it('无远程模块时应返回空 CSS 注释', async () => {
    await expect(compilePreviewTailwindUtilities([])).resolves.toContain('no remote modules')
  })

  it('应生成稳定缓存签名并支持入口扩展名推断', () => {
    const left = buildPreviewTailwindCacheSignature([
      { logicalPath: 'src/views/A.vue', content: '<div class="pt-16"></div>' },
      { logicalPath: 'src/workspace-components/cmp/v/1.vue', content: '<div class="text-invert"></div>' },
    ])
    const right = buildPreviewTailwindCacheSignature([
      { logicalPath: 'src/workspace-components/cmp/v/1.vue', content: '<div class="text-invert"></div>' },
      { logicalPath: 'src/views/A.vue', content: '<div class="pt-16"></div>' },
    ])

    expect(left).toBe(right)
    expect(inferTailwindRawExtension('src/views/A.vue')).toBe('vue')
    expect(inferTailwindRawExtension('src/views/A.unknown')).toBe('html')
  })
})
