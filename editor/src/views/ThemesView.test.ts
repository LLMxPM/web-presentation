/**
 * 文件功能：验证主题与字体页面的分页数据读取和字体注册入口。
 */
import { defineComponent, h } from 'vue'
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ThemesView from '@/views/ThemesView.vue'

const getWorkspaceMock = vi.fn()
const listWorkspaceThemesMock = vi.fn()
const listWorkspaceFontsMock = vi.fn()
const listWorkspaceAssetsMock = vi.fn()
const uploadWorkspaceAssetMock = vi.fn()
const deleteWorkspaceFontMock = vi.fn()
const deleteWorkspaceFontAssetMock = vi.fn()
const routerPushMock = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => ({
    params: {
      workspaceId: '7',
    },
  }),
  useRouter: () => ({
    push: routerPushMock,
  }),
}))

vi.mock('@/api/catalog', () => ({
  getWorkspace: (...args: unknown[]) => getWorkspaceMock(...args),
  updateWorkspace: vi.fn(),
}))

vi.mock('@/api/themes', () => ({
  copyWorkspaceTheme: vi.fn(),
  createWorkspaceTheme: vi.fn(),
  deleteWorkspaceTheme: vi.fn(),
  getWorkspaceTheme: vi.fn(),
  listWorkspaceThemes: (...args: unknown[]) => listWorkspaceThemesMock(...args),
  updateWorkspaceTheme: vi.fn(),
}))

vi.mock('@/api/assets', () => ({
  createWorkspaceFont: vi.fn(),
  deleteWorkspaceFont: (...args: unknown[]) => deleteWorkspaceFontMock(...args),
  deleteWorkspaceFontAsset: (...args: unknown[]) => deleteWorkspaceFontAssetMock(...args),
  listWorkspaceAssets: (...args: unknown[]) => listWorkspaceAssetsMock(...args),
  listWorkspaceFonts: (...args: unknown[]) => listWorkspaceFontsMock(...args),
  replaceWorkspaceAssetFile: vi.fn(),
  restoreWorkspaceAsset: vi.fn(),
  updateWorkspaceFont: vi.fn(),
  uploadWorkspaceAsset: (...args: unknown[]) => uploadWorkspaceAssetMock(...args),
}))

vi.mock('@/utils/message', () => ({
  createConfirm: vi.fn().mockResolvedValue(true),
  Message: {
    error: vi.fn(),
    info: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
  },
}))

describe('ThemesView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getWorkspaceMock.mockResolvedValue({
      id: 7,
      name: '默认工作空间',
      default_theme_key: 'default',
    })
    listWorkspaceThemesMock.mockResolvedValue({
      items: [createThemeItem()],
      total: 1,
      page: 1,
      page_size: 10,
    })
    listWorkspaceFontsMock.mockResolvedValue({
      items: [createFontItem()],
      total: 1,
      page: 1,
      page_size: 10,
    })
    listWorkspaceAssetsMock.mockResolvedValue({
      items: [createFontAsset()],
      total: 1,
      page: 1,
      page_size: 10,
    })
    uploadWorkspaceAssetMock.mockResolvedValue(createUploadedFontAsset())
    deleteWorkspaceFontMock.mockResolvedValue(undefined)
    deleteWorkspaceFontAssetMock.mockResolvedValue(undefined)
  })

  it('应突出主题库主区和字体管理侧栏，并从字体资源打开注册弹窗', async () => {
    renderThemesView()

    await waitFor(() => {
      expect(screen.getAllByText('默认主题卡').length).toBeGreaterThan(0)
      expect(screen.getAllByText('SourceHanSans').length).toBeGreaterThan(0)
    })
    expect(screen.getByText('主题库')).toBeInTheDocument()
    expect(screen.getByText('字体管理')).toBeInTheDocument()
    expect(screen.getByText('字体注册')).toBeInTheDocument()
    expect(screen.getByText('字体文件')).toBeInTheDocument()
    expect(screen.getByText('共 1 个主题')).toBeInTheDocument()
    expect(screen.getByText('注册 1 / 文件 1')).toBeInTheDocument()
    expect(screen.queryByText('默认主题')).not.toBeInTheDocument()
    expect(screen.queryByText('主题数量')).not.toBeInTheDocument()
    const themeCard = screen.getByText('标题字体').closest('article') as HTMLElement
    expect(themeCard).toHaveStyle({ backgroundColor: 'rgb(13, 40, 106)', color: 'rgb(255, 255, 255)' })
    expect(listWorkspaceThemesMock).toHaveBeenCalledWith(7, expect.objectContaining({ page: 1, page_size: 10 }))
    expect(listWorkspaceFontsMock).toHaveBeenCalledWith(7, expect.objectContaining({ page: 1, page_size: 10 }))
    expect(listWorkspaceAssetsMock).toHaveBeenCalledWith(7, expect.objectContaining({ assetType: 'font', page: 1, page_size: 10 }))

    await fireEvent.click(screen.getByRole('button', { name: /^注册$/ }))

    expect(screen.getByRole('option', { name: 'SourceHanSans / SourceHanSans.woff2' })).toBeInTheDocument()
    expect(screen.getByDisplayValue('SourceHanSans')).toBeInTheDocument()
  })

  it('点击主题卡应打开主题详情弹窗', async () => {
    renderThemesView()

    await waitFor(() => {
      expect(screen.getAllByText('主题描述').length).toBeGreaterThan(0)
    })

    await fireEvent.click(screen.getByText('主题描述'))

    expect(screen.getByTestId('theme-detail-dialog')).toHaveTextContent('theme-id:1')
  })

  it('应支持在页面内上传字体文件，并用上传结果打开注册弹窗', async () => {
    const { container } = renderThemesView()

    await waitFor(() => {
      expect(screen.getByText('共 1 个主题')).toBeInTheDocument()
    })

    await fireEvent.click(screen.getByRole('button', { name: /^上传$/ }))
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['font-data'], 'NewFont.woff2', { type: 'font/woff2' })
    await fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(uploadWorkspaceAssetMock).toHaveBeenCalledWith(7, file, 'font')
      expect(screen.getByDisplayValue('NewFont')).toBeInTheDocument()
    })
    expect(listWorkspaceAssetsMock).toHaveBeenCalledWith(7, expect.objectContaining({ assetType: 'font', page: 1, page_size: 10 }))
  })

  it('应展示字体文件页签并允许从未注册文件发起注册', async () => {
    renderThemesView()

    await waitFor(() => {
      expect(screen.getByText('字体文件')).toBeInTheDocument()
    })

    await fireEvent.click(screen.getByText('字体文件'))

    expect(screen.getByText('SourceHanSans.woff2')).toBeInTheDocument()
    expect(screen.getByText('未注册')).toBeInTheDocument()

    await fireEvent.click(screen.getByRole('button', { name: /^注册字体$/ }))

    expect(screen.getByDisplayValue('SourceHanSans')).toBeInTheDocument()
  })

  it('删除字体注册时默认同时删除关联字体文件', async () => {
    renderThemesView()

    await waitFor(() => {
      expect(screen.getAllByText('SourceHanSans').length).toBeGreaterThan(0)
    })

    const deleteButton = screen.getByTitle('删除注册和字体文件')
    await fireEvent.click(deleteButton)

    await waitFor(() => {
      expect(deleteWorkspaceFontMock).toHaveBeenCalledWith(7, 1, { deleteAsset: true })
    })
  })

  it('字体文件页签应直接删除未注册字体文件，不再先归档', async () => {
    renderThemesView()

    await waitFor(() => {
      expect(screen.getByText('字体文件')).toBeInTheDocument()
    })

    await fireEvent.click(screen.getByText('字体文件'))
    expect(screen.queryByTitle('归档字体文件')).not.toBeInTheDocument()

    await fireEvent.click(screen.getByTitle('删除字体文件'))

    await waitFor(() => {
      expect(deleteWorkspaceFontAssetMock).toHaveBeenCalledWith(7, 2)
    })
  })
})

function renderThemesView() {
  return render(ThemesView, {
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
        PageTitleBar: defineComponent({
          name: 'PageTitleBar',
          props: {
            title: {
              type: String,
              required: true,
            },
          },
          setup(props, { slots }) {
            return () => h('header', [h('h1', props.title), slots.actions?.()])
          },
        }),
        ThemeEditorDialog: true,
        ThemeDetailDialog: defineComponent({
          name: 'ThemeDetailDialog',
          props: {
            modelValue: Boolean,
            themeId: Number,
          },
          setup(props) {
            return () => props.modelValue
              ? h('aside', { 'data-testid': 'theme-detail-dialog' }, `theme-id:${props.themeId}`)
              : null
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
    key: 'default',
    name: '默认主题卡',
    description: '主题描述',
    palette: createThemePalette(),
    logo_asset: null,
    invert_logo_asset: null,
    project_icon_asset: null,
    project_icon_name: null,
    logo_asset_id: null,
    invert_logo_asset_id: null,
    project_icon_asset_id: null,
    heading_font_id: null,
    body_font_id: null,
    code_font_id: null,
    heading_font_label: 'SourceHanSans',
    body_font_label: 'SourceHanSans',
    code_font_label: 'monospace',
    heading_font: null,
    body_font: null,
    code_font: null,
    resolved_theme_config_yaml: 'themes:\n  default: {}',
    created_by: null,
    updated_by: null,
    created_at: '2026-05-01T10:00:00+08:00',
    updated_at: '2026-05-01T10:00:00+08:00',
  }
}

function createThemePalette() {
  return {
    text: { primary: '#ffffff', secondary: '#bfdbfe', invert: '#0f172a' },
    background: { default: '#0D286A', invert: '#ffffff' },
    border: { default: '#1d4ed8', subtle: '#dbeafe' },
    link: { default: '#2563eb', hover: '#1d4ed8', visited: '#7c3aed' },
    accent: ['#2563eb', '#059669', '#d97706', '#dc2626', '#7c3aed', '#0891b2'],
  }
}

function createFontItem() {
  return {
    id: 1,
    workspace_id: 7,
    asset_id: 2,
    asset_name: 'SourceHanSans',
    font_family: 'SourceHanSans',
    font_format: 'woff2',
    font_weight: '400',
    font_style: 'normal',
    font_display: 'swap',
    status: 'active',
    asset_url: 'https://backend.example.com/public/assets/7/font-hash',
    created_at: '2026-05-01T10:00:00+08:00',
    updated_at: '2026-05-01T10:00:00+08:00',
  }
}

function createFontAsset() {
  return {
    id: 2,
    workspace_id: 7,
    name: 'SourceHanSans',
    file_name: 'font-hash.woff2',
    original_name: 'SourceHanSans.woff2',
    description: null,
    file_size: 256,
    file_hash: 'font-hash',
    content_type: 'font/woff2',
    asset_type: 'font',
    asset_role: 'foundation',
    render_type: 'font',
    tags: [],
    analysis_metadata: null,
    render_metadata: null,
    status: 'active',
    archived_at: null,
    archive_reason: null,
    source_asset_id: null,
    history_kind: null,
    content_editable: false,
    url: 'https://backend.example.com/public/assets/7/font-hash',
    font_config: null,
    rename_block_reason: null,
    delete_block_reason: null,
    archive_block_reason: null,
    archive_warning_reasons: [],
    created_at: '2026-05-01T10:00:00+08:00',
    updated_at: '2026-05-01T10:00:00+08:00',
  }
}

function createUploadedFontAsset() {
  return {
    ...createFontAsset(),
    id: 3,
    name: 'NewFont',
    original_name: 'NewFont.woff2',
    file_name: 'new-font-hash.woff2',
    file_hash: 'new-font-hash',
    url: 'https://backend.example.com/public/assets/7/new-font-hash',
  }
}
