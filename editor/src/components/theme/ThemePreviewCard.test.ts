/**
 * 文件功能：验证主题预览卡会注册完整字体 face，并使用 Editor 隔离字体族渲染文字。
 */
import { render, screen, waitFor } from '@testing-library/vue'
import { afterEach, describe, expect, it } from 'vitest'

import ThemePreviewCard from './ThemePreviewCard.vue'

describe('ThemePreviewCard', () => {
  afterEach(() => {
    document.getElementById('editor-font-preview-registry')?.remove()
  })

  it('应注册字体族全部 active face 并应用到标题和正文', async () => {
    const family = createFontFamily()
    render(ThemePreviewCard, {
      props: {
        keyName: 'brand',
        name: '品牌主题',
        description: '字体预览',
        palette: createThemePalette(),
        headingFontLabel: family.name,
        bodyFontLabel: family.name,
        codeFontLabel: 'monospace',
        headingFontFamily: family,
        bodyFontFamily: family,
      },
    })

    await waitFor(() => {
      const styleText = document.getElementById('editor-font-preview-registry')?.textContent || ''
      expect(styleText).toContain('font-family: "editor-preview-font-7-20"')
      expect(styleText).toContain('font-weight: 400')
      expect(styleText).toContain('font-weight: 700')
      expect(styleText).not.toContain('Archived.woff2')
    })

    const title = screen.getByText('品牌主题')
    expect(title.getAttribute('style')).toContain('editor-preview-font-7-20')
  })
})

function createFontFamily() {
  const baseFace = {
    family_id: 20,
    workspace_id: 7,
    font_family: '思源黑体',
    font_format: 'woff2',
    font_style: 'normal',
    font_display: 'swap',
    created_at: '2026-05-01T10:00:00+08:00',
    updated_at: '2026-05-01T10:00:00+08:00',
  }
  return {
    id: 20,
    workspace_id: 7,
    name: '思源黑体',
    faces: [
      {
        ...baseFace,
        id: 1,
        asset_id: 11,
        asset_name: 'SourceHanSans-Regular',
        font_weight: '400',
        status: 'active' as const,
        asset_url: 'https://backend.example.com/Regular.woff2',
      },
      {
        ...baseFace,
        id: 2,
        asset_id: 12,
        asset_name: 'SourceHanSans-Bold',
        font_weight: '700',
        status: 'active' as const,
        asset_url: 'https://backend.example.com/Bold.woff2',
      },
      {
        ...baseFace,
        id: 3,
        asset_id: 13,
        asset_name: 'SourceHanSans-Archived',
        font_weight: '300',
        status: 'archived' as const,
        asset_url: 'https://backend.example.com/Archived.woff2',
      },
    ],
    created_at: '2026-05-01T10:00:00+08:00',
    updated_at: '2026-05-01T10:00:00+08:00',
  }
}

function createThemePalette() {
  return {
    text: { primary: '#0f172a', secondary: '#475569', invert: '#ffffff' },
    background: { default: '#ffffff', invert: '#0f172a' },
    border: { default: '#cbd5e1', subtle: '#e2e8f0' },
    link: { default: '#2563eb', hover: '#1d4ed8', visited: '#7c3aed' },
    accent: ['#2563eb'],
  }
}
