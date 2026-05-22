/**
 * 文件功能：验证主题详情抽屉会加载详情、展示关键配置，并把操作事件交回父组件。
 */
import { defineComponent, h } from 'vue'
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ThemeDetailDrawer from './ThemeDetailDrawer.vue'

const getWorkspaceThemeMock = vi.fn()

vi.mock('@/api/themes', () => ({
  getWorkspaceTheme: (...args: unknown[]) => getWorkspaceThemeMock(...args),
}))

describe('ThemeDetailDrawer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getWorkspaceThemeMock.mockResolvedValue(createThemeItem())
  })

  it('应加载并展示主题详情、颜色 token、字体绑定和 Runtime YAML', async () => {
    renderDrawer()

    await waitFor(() => {
      expect(getWorkspaceThemeMock).toHaveBeenCalledWith(7, 1)
      expect(screen.getAllByText('默认主题卡').length).toBeGreaterThan(0)
    })

    expect(screen.getByText('颜色 token')).toBeInTheDocument()
    expect(screen.getAllByText('标题字体').length).toBeGreaterThan(0)
    expect(screen.getAllByText('思源黑体').length).toBeGreaterThan(0)
    expect(screen.getByText('Runtime YAML')).toBeInTheDocument()
    expect(screen.getByText(/themes:/)).toBeInTheDocument()
  })

  it('应通过事件暴露设为默认、编辑、复制和删除操作', async () => {
    const { emitted } = renderDrawer({ defaultThemeKey: 'other' })

    await waitFor(() => {
      expect(screen.getAllByText('默认主题卡').length).toBeGreaterThan(0)
    })

    await fireEvent.click(screen.getByRole('button', { name: /设为默认/ }))
    await fireEvent.click(screen.getByRole('button', { name: /编辑/ }))
    await fireEvent.click(screen.getByRole('button', { name: /复制/ }))
    await fireEvent.click(screen.getByRole('button', { name: /删除主题/ }))

    const events = emitted() as Record<string, unknown[][]>
    const setDefaultPayload = events.setDefault[0][0] as { id: number; key: string }
    const editPayload = events.edit[0][0] as { id: number; key: string }
    const copyPayload = events.copy[0][0] as { id: number; key: string }
    const deletePayload = events.delete[0][0] as { id: number; key: string }

    expect(setDefaultPayload).toMatchObject({ id: 1, key: 'default' })
    expect(editPayload).toMatchObject({ id: 1, key: 'default' })
    expect(copyPayload).toMatchObject({ id: 1, key: 'default' })
    expect(deletePayload).toMatchObject({ id: 1, key: 'default' })
  })
})

function renderDrawer(options: { defaultThemeKey?: string } = {}) {
  return render(ThemeDetailDrawer, {
    props: {
      modelValue: true,
      workspaceId: 7,
      themeId: 1,
      defaultThemeKey: options.defaultThemeKey ?? 'default',
    },
    global: {
      stubs: {
        BaseButton: defineComponent({
          name: 'BaseButton',
          props: {
            disabled: Boolean,
          },
          setup(props, { attrs, slots }) {
            return () => h('button', { ...attrs, disabled: props.disabled }, slots.default?.())
          },
        }),
        ThemePreviewCard: defineComponent({
          name: 'ThemePreviewCard',
          props: {
            name: {
              type: String,
              required: true,
            },
          },
          setup(props) {
            return () => h('section', { 'data-testid': 'theme-preview-card' }, props.name)
          },
        }),
      },
    },
  })
}

function createThemeItem() {
  const font = createFontItem()
  return {
    id: 1,
    workspace_id: 7,
    key: 'default',
    name: '默认主题卡',
    description: '主题描述',
    logo_asset_id: null,
    invert_logo_asset_id: null,
    project_icon_asset_id: null,
    heading_font_id: font.id,
    body_font_id: font.id,
    code_font_id: font.id,
    heading_font_label: font.font_family,
    body_font_label: font.font_family,
    code_font_label: font.font_family,
    palette: createThemePalette(),
    logo_asset: null,
    invert_logo_asset: null,
    project_icon_asset: null,
    project_icon_name: 'slider',
    heading_font: font,
    body_font: font,
    code_font: font,
    resolved_theme_config_yaml: 'themes:\n  default:\n    colors: {}',
    created_by: null,
    updated_by: null,
    created_at: '2026-05-01T10:00:00+08:00',
    updated_at: '2026-05-01T10:00:00+08:00',
  }
}

function createFontItem() {
  return {
    id: 2,
    workspace_id: 7,
    asset_id: 3,
    asset_name: 'SourceHanSans',
    font_family: '思源黑体',
    font_format: 'woff2',
    font_weight: '400',
    font_style: 'normal',
    font_display: 'swap',
    status: 'active' as const,
    asset_url: 'https://backend.example.com/public/assets/7/font-hash',
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
    accent: ['#2563eb', '#059669', '#d97706', '#dc2626', '#7c3aed', '#0891b2'],
  }
}
