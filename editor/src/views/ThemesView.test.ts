/**
 * 文件功能：验证主题与字体页面的分页读取、字体族分组展示、上传自动注册、族内添加文件、face 删除与字体族重命名交互。
 */
import { defineComponent, h } from 'vue'
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ThemesView from '@/views/ThemesView.vue'

const getWorkspaceMock = vi.fn()
const listWorkspaceThemesMock = vi.fn()
const listWorkspaceAssetsMock = vi.fn()
const listWorkspaceFontFamiliesMock = vi.fn()
const uploadWorkspaceAssetMock = vi.fn()
const createWorkspaceFontMock = vi.fn()
const deleteWorkspaceFontMock = vi.fn()
const deleteWorkspaceFontAssetMock = vi.fn()
const renameWorkspaceFontFamilyMock = vi.fn()
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
  createWorkspaceFont: (...args: unknown[]) => createWorkspaceFontMock(...args),
  deleteWorkspaceFont: (...args: unknown[]) => deleteWorkspaceFontMock(...args),
  deleteWorkspaceFontAsset: (...args: unknown[]) => deleteWorkspaceFontAssetMock(...args),
  listWorkspaceAssets: (...args: unknown[]) => listWorkspaceAssetsMock(...args),
  listWorkspaceFontFamilies: (...args: unknown[]) => listWorkspaceFontFamiliesMock(...args),
  renameWorkspaceFontFamily: (...args: unknown[]) => renameWorkspaceFontFamilyMock(...args),
  replaceWorkspaceAssetFile: vi.fn(),
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
    listWorkspaceFontFamiliesMock.mockResolvedValue({
      items: [createFontFamilyItem()],
      total: 1,
      page: 1,
      page_size: 10,
    })
    listWorkspaceAssetsMock.mockResolvedValue({
      items: [createFontAsset()],
      total: 1,
      page: 1,
      page_size: 100,
    })
    uploadWorkspaceAssetMock.mockResolvedValue(createUploadedFontAsset())
    createWorkspaceFontMock.mockResolvedValue(createFontConfigSummary())
    deleteWorkspaceFontMock.mockResolvedValue(undefined)
    deleteWorkspaceFontAssetMock.mockResolvedValue(undefined)
    renameWorkspaceFontFamilyMock.mockResolvedValue(createFontFamilyItem())
  })

  it('应按字体族分组展示，并支持从 face 编辑入口打开注册弹窗', async () => {
    renderThemesView()

    await waitFor(() => {
      expect(screen.getAllByText('默认主题卡').length).toBeGreaterThan(0)
      expect(screen.getAllByText('SourceHanSans').length).toBeGreaterThan(0)
    })
    expect(screen.getByText('主题库')).toBeInTheDocument()
    expect(screen.getByText('字体管理')).toBeInTheDocument()
    expect(screen.getByText('共 1 个主题')).toBeInTheDocument()
    expect(screen.getByText('共 1 个字体族')).toBeInTheDocument()
    expect(screen.getByText('1 个文件')).toBeInTheDocument()
    expect(screen.queryByText('待注册字体文件')).not.toBeInTheDocument()
    expect(listWorkspaceThemesMock).toHaveBeenCalledWith(7, expect.objectContaining({ page: 1, page_size: 10 }))
    expect(listWorkspaceFontFamiliesMock).toHaveBeenCalledWith(7, expect.objectContaining({ page: 1, page_size: 10 }))
    expect(listWorkspaceAssetsMock).toHaveBeenCalledWith(7, expect.objectContaining({ assetType: 'font', page: 1, page_size: 100 }))

    await fireEvent.click(screen.getByTitle('编辑字体'))

    expect(screen.getByText('编辑字体')).toBeInTheDocument()
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

  it('上传字体文件后应自动完成注册并归入字体族', async () => {
    const { container } = renderThemesView()

    await waitFor(() => {
      expect(screen.getByText('共 1 个主题')).toBeInTheDocument()
    })

    await fireEvent.click(screen.getByRole('button', { name: /上传字体/ }))
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['font-data'], 'NewFont.woff2', { type: 'font/woff2' })
    await fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(uploadWorkspaceAssetMock).toHaveBeenCalledWith(7, file, 'font')
      expect(createWorkspaceFontMock).toHaveBeenCalledWith(7, {
        asset_id: 3,
        family_name: 'NewFont',
        font_format: 'woff2',
        font_weight: '400',
        font_style: 'normal',
        font_display: 'swap',
        status: 'active',
      })
    })
    expect(screen.queryByText('保存字体')).not.toBeInTheDocument()
    expect(listWorkspaceFontFamiliesMock).toHaveBeenCalledWith(7, expect.objectContaining({ page: 1, page_size: 10 }))
  })

  it('自动注册失败时应打开注册弹窗让用户补全', async () => {
    createWorkspaceFontMock.mockRejectedValueOnce(new Error('注册失败'))
    const { container } = renderThemesView()

    await waitFor(() => {
      expect(screen.getByText('共 1 个主题')).toBeInTheDocument()
    })

    await fireEvent.click(screen.getByRole('button', { name: /上传字体/ }))
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['font-data'], 'NewFont.woff2', { type: 'font/woff2' })
    await fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByDisplayValue('NewFont')).toBeInTheDocument()
    })
  })

  it('从字体族卡片添加文件时应强制注册到该族', async () => {
    uploadWorkspaceAssetMock.mockResolvedValueOnce({
      ...createUploadedFontAsset(),
      name: 'NewFont-Bold',
      original_name: 'NewFont-Bold.woff2',
    })
    renderThemesView()

    await waitFor(() => {
      expect(screen.getByText('1 个文件')).toBeInTheDocument()
    })

    await fireEvent.click(screen.getByTitle('添加字体文件'))
    const addInput = screen.getByTestId('font-add-file-input') as HTMLInputElement
    const file = new File(['font-data'], 'NewFont-Bold.woff2', { type: 'font/woff2' })
    await fireEvent.change(addInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(uploadWorkspaceAssetMock).toHaveBeenCalledWith(7, file, 'font')
      // 族名强制为目标字体族，字重/样式仍按文件名推断
      expect(createWorkspaceFontMock).toHaveBeenCalledWith(7, {
        asset_id: 3,
        family_name: 'SourceHanSans',
        font_format: 'woff2',
        font_weight: '700',
        font_style: 'normal',
        font_display: 'swap',
        status: 'active',
      })
    })
  })

  it('族内添加文件注册失败时弹窗应预置目标族名', async () => {
    createWorkspaceFontMock.mockRejectedValueOnce(new Error('字重冲突'))
    uploadWorkspaceAssetMock.mockResolvedValueOnce({
      ...createUploadedFontAsset(),
      name: 'AnotherName-Bold',
      original_name: 'AnotherName-Bold.woff2',
    })
    renderThemesView()

    await waitFor(() => {
      expect(screen.getByText('1 个文件')).toBeInTheDocument()
    })

    await fireEvent.click(screen.getByTitle('添加字体文件'))
    const addInput = screen.getByTestId('font-add-file-input') as HTMLInputElement
    const file = new File(['font-data'], 'AnotherName-Bold.woff2', { type: 'font/woff2' })
    await fireEvent.change(addInput, { target: { files: [file] } })

    // 弹窗族名预置为目标族 SourceHanSans，而非文件名推断的 AnotherName
    await waitFor(() => {
      expect(screen.getByText('注册字体')).toBeInTheDocument()
      expect(screen.getByDisplayValue('SourceHanSans')).toBeInTheDocument()
    })
    expect(screen.queryByDisplayValue('AnotherName')).not.toBeInTheDocument()
  })

  it('删除字体族下的 face 时应连同字体文件一起删除', async () => {
    renderThemesView()

    await waitFor(() => {
      expect(screen.getAllByText('SourceHanSans').length).toBeGreaterThan(0)
    })

    await fireEvent.click(screen.getByTitle('删除字体'))

    await waitFor(() => {
      expect(deleteWorkspaceFontMock).toHaveBeenCalledWith(7, 1, { deleteAsset: true })
    })
    expect(deleteWorkspaceFontAssetMock).not.toHaveBeenCalled()
  })

  it('删除未注册字体文件时应直接硬删除文件', async () => {
    listWorkspaceAssetsMock.mockResolvedValue({
      items: [createPendingFontAsset()],
      total: 1,
      page: 1,
      page_size: 100,
    })
    renderThemesView()

    await waitFor(() => {
      expect(screen.getByText('待注册字体文件')).toBeInTheDocument()
    })

    await fireEvent.click(screen.getByTitle('删除字体文件'))

    await waitFor(() => {
      expect(deleteWorkspaceFontAssetMock).toHaveBeenCalledWith(7, 4)
    })
    expect(deleteWorkspaceFontMock).not.toHaveBeenCalled()
  })

  it('重命名字体族应提交新的族名称', async () => {
    renderThemesView()

    await waitFor(() => {
      expect(screen.getByText('1 个文件')).toBeInTheDocument()
    })

    await fireEvent.click(screen.getByTitle('重命名字体族'))
    const renameInput = screen.getByPlaceholderText('字体族名称') as HTMLInputElement
    await fireEvent.update(renameInput, '思源黑体')
    await fireEvent.click(screen.getByTitle('保存'))

    await waitFor(() => {
      expect(renameWorkspaceFontFamilyMock).toHaveBeenCalledWith(7, 10, '思源黑体')
    })
  })
})

function renderThemesView() {
  return render(ThemesView, {
    global: {
      stubs: {
        UiButton: defineComponent({
          name: 'UiButton',
          props: {
            disabled: Boolean,
          },
          setup(props, { attrs, slots }) {
            return () => h('button', { ...attrs, disabled: props.disabled }, slots.default?.())
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
    heading_font_family_id: null,
    body_font_family_id: null,
    code_font_family_id: null,
    heading_font_label: 'SourceHanSans',
    body_font_label: 'SourceHanSans',
    code_font_label: 'monospace',
    heading_font_family: null,
    body_font_family: null,
    code_font_family: null,
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

function createFontConfigSummary() {
  return {
    id: 1,
    family_id: 10,
    asset_id: 2,
    asset_name: 'SourceHanSans',
    font_family: 'SourceHanSans',
    font_format: 'woff2',
    font_weight: '400',
    font_style: 'normal',
    font_display: 'swap',
    status: 'active',
  }
}

function createFontFace() {
  return {
    ...createFontConfigSummary(),
    workspace_id: 7,
    asset_url: 'https://backend.example.com/public/assets/7/font-hash',
    created_at: '2026-05-01T10:00:00+08:00',
    updated_at: '2026-05-01T10:00:00+08:00',
  }
}

function createFontFamilyItem() {
  return {
    id: 10,
    workspace_id: 7,
    name: 'SourceHanSans',
    faces: [createFontFace()],
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
    font_config: createFontConfigSummary(),
    rename_block_reason: null,
    delete_block_reason: null,
    archive_block_reason: null,
    archive_warning_reasons: [],
    created_at: '2026-05-01T10:00:00+08:00',
    updated_at: '2026-05-01T10:00:00+08:00',
  }
}

function createPendingFontAsset() {
  return {
    ...createFontAsset(),
    id: 4,
    name: 'PendingFont',
    original_name: 'PendingFont.woff2',
    file_name: 'pending-hash.woff2',
    file_hash: 'pending-hash',
    url: 'https://backend.example.com/public/assets/7/pending-hash',
    font_config: null,
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
    font_config: null,
  }
}
