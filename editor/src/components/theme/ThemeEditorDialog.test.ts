/**
 * 文件功能：验证主题编辑弹窗只维护主题资源、字体绑定和颜色配置。
 */
import { defineComponent, h } from 'vue'
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ThemeEditorDialog from './ThemeEditorDialog.vue'

const listWorkspaceAssetsMock = vi.fn()
const listWorkspaceFontsMock = vi.fn()

vi.mock('@/api/assets', () => ({
  listWorkspaceAssets: (...args: unknown[]) => listWorkspaceAssetsMock(...args),
  listWorkspaceFonts: (...args: unknown[]) => listWorkspaceFontsMock(...args),
}))

vi.mock('@/utils/message', () => ({
  Message: {
    error: vi.fn(),
    success: vi.fn(),
  },
}))

describe('ThemeEditorDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listWorkspaceAssetsMock.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 })
    listWorkspaceFontsMock.mockResolvedValue({
      items: [createFontItem(2, '思源黑体'), createFontItem(3, 'Monaco'), createFontItem(4, 'SourceCodePro')],
      total: 3,
      page: 1,
      page_size: 100,
    })
  })

  it('保存编辑主题时应归一化 key，并且不再提交项目页面规格字段', async () => {
    const { emitted } = renderDialog()

    await waitFor(() => {
      expect(screen.getByDisplayValue('Default_Theme')).toBeInTheDocument()
      expect(listWorkspaceFontsMock).toHaveBeenCalledWith(7, expect.objectContaining({ page: 1, page_size: 100 }))
    })

    expect(screen.getByText('品牌资源与字体绑定')).toBeInTheDocument()
    expect(screen.queryByText('字号与图标规格')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('基础字号')).not.toBeInTheDocument()

    await fireEvent.update(screen.getByLabelText('主题 key'), 'BlueTheme')
    await fireEvent.click(screen.getByRole('button', { name: /保存主题/ }))

    const events = emitted() as Record<string, unknown[][]>
    const savePayload = events.save[0][0] as {
      key: string
      name: string
      description: string | null
      heading_font_id: number | null
      body_font_id: number | null
      code_font_id: number | null
    }

    expect(savePayload).toMatchObject({
      key: 'bluetheme',
      name: '默认主题卡',
      description: '主题描述',
      heading_font_id: 2,
      body_font_id: 2,
      code_font_id: 3,
    })
    expect(savePayload).not.toHaveProperty('base_font_size')
    expect(savePayload).not.toHaveProperty('icon_default_size')
    expect(savePayload).not.toHaveProperty('icon_default_stroke_width')
  })
})

function renderDialog() {
  return render(ThemeEditorDialog, {
    props: {
      modelValue: true,
      workspaceId: 7,
      theme: createThemeItem(),
      saving: false,
    },
    global: {
      stubs: {
        BaseDialog: defineComponent({
          name: 'BaseDialog',
          props: {
            modelValue: Boolean,
            title: String,
          },
          setup(props, { slots }) {
            return () => props.modelValue
              ? h('section', [h('h2', props.title), slots.default?.(), h('footer', slots.footer?.())])
              : null
          },
        }),
        BaseButton: defineComponent({
          name: 'BaseButton',
          props: {
            disabled: Boolean,
          },
          setup(props, { attrs, slots }) {
            return () => h('button', { ...attrs, disabled: props.disabled }, slots.default?.())
          },
        }),
        SearchableSelect: defineComponent({
          name: 'SearchableSelect',
          props: {
            modelValue: [String, Number],
          },
          setup(props) {
            return () => h('div', { 'data-testid': 'searchable-select' }, String(props.modelValue ?? ''))
          },
        }),
        IconPicker: defineComponent({
          name: 'IconPicker',
          setup() {
            return () => h('div', { 'data-testid': 'icon-picker' }, '图标选择器')
          },
        }),
        ThemePreviewCard: defineComponent({
          name: 'ThemePreviewCard',
          props: {
            name: String,
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
  return {
    id: 1,
    workspace_id: 7,
    key: 'Default_Theme',
    name: '默认主题卡',
    description: '主题描述',
    logo_asset_id: null,
    invert_logo_asset_id: null,
    project_icon_asset_id: null,
    heading_font_id: 2,
    body_font_id: 2,
    code_font_id: 3,
    heading_font_label: '思源黑体',
    body_font_label: '思源黑体',
    code_font_label: 'Monaco',
    palette: createThemePalette(),
    logo_asset: null,
    invert_logo_asset: null,
    project_icon_asset: null,
    project_icon_name: 'slider',
    heading_font: createFontItem(2, '思源黑体'),
    body_font: createFontItem(2, '思源黑体'),
    code_font: createFontItem(3, 'Monaco'),
    resolved_theme_config_yaml: 'themes:\n  default: {}',
    created_by: null,
    updated_by: null,
    created_at: '2026-05-01T10:00:00+08:00',
    updated_at: '2026-05-01T10:00:00+08:00',
  }
}

function createFontItem(id: number, family: string) {
  return {
    id,
    workspace_id: 7,
    asset_id: id + 10,
    asset_name: family,
    font_family: family,
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
