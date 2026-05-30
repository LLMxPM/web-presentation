/**
 * 文件功能：验证工作空间样式库页面的详情查看、导出和导入入口。
 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocked = vi.hoisted(() => ({
  push: vi.fn(),
  copyWorkspaceStyle: vi.fn(),
  createWorkspaceStyle: vi.fn(),
  deleteWorkspaceStyle: vi.fn(),
  exportWorkspaceStylePackage: vi.fn(),
  importWorkspaceStylePackage: vi.fn(),
  listWorkspaceStyles: vi.fn(),
  updateWorkspaceStyle: vi.fn(),
  validateWorkspaceStylePackageImport: vi.fn(),
  style: {
    id: 9,
    workspace_id: 1,
    key: 'pitch',
    name: '路演样式',
    description: '适合路演展示。',
    page_width: 1920,
    page_height: 1080,
    base_font_size: '18px',
    icon_default_stroke_width: 2,
    show_pdf_export_button: true,
    menu_mode: 'preview',
    theme_key: 'default',
    style_spec_markdown: '## 版式\n- 使用强标题。',
    created_at: '2026-05-16T00:00:00Z',
    updated_at: '2026-05-16T00:00:00Z',
    created_by: 1,
    updated_by: 1,
  },
}))
const anchorClickMock = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { workspaceId: '1' } }),
  useRouter: () => ({ push: mocked.push }),
}))

vi.mock('@/api/catalog', () => ({
  getWorkspace: vi.fn().mockResolvedValue({
    id: 1,
    name: '演示空间',
    default_theme_key: 'default',
  }),
}))

vi.mock('@/api/styles', () => ({
  copyWorkspaceStyle: (...args: unknown[]) => mocked.copyWorkspaceStyle(...args),
  createWorkspaceStyle: (...args: unknown[]) => mocked.createWorkspaceStyle(...args),
  deleteWorkspaceStyle: (...args: unknown[]) => mocked.deleteWorkspaceStyle(...args),
  exportWorkspaceStylePackage: (...args: unknown[]) => mocked.exportWorkspaceStylePackage(...args),
  importWorkspaceStylePackage: (...args: unknown[]) => mocked.importWorkspaceStylePackage(...args),
  listWorkspaceStyles: (...args: unknown[]) => mocked.listWorkspaceStyles(...args),
  updateWorkspaceStyle: (...args: unknown[]) => mocked.updateWorkspaceStyle(...args),
  validateWorkspaceStylePackageImport: (...args: unknown[]) => mocked.validateWorkspaceStylePackageImport(...args),
}))

vi.mock('@/components/project/WorkspaceStyleEditorDialog.vue', () => ({
  default: {
    props: ['modelValue'],
    emits: ['update:modelValue', 'save'],
    template: '<div data-testid="style-editor-dialog"></div>',
  },
}))

import WorkspaceStylesView from './WorkspaceStylesView.vue'

describe('WorkspaceStylesView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocked.listWorkspaceStyles.mockResolvedValue({
      items: [mocked.style],
      total: 1,
      page: 1,
      page_size: 100,
    })
    mocked.exportWorkspaceStylePackage.mockResolvedValue({
      blob: new Blob(['zip']),
      filename: 'workspace-styles.zip',
    })
    mocked.validateWorkspaceStylePackageImport.mockResolvedValue({
      valid: true,
      schema_version: 2,
      styles: [{ key: 'pitch', name: '路演样式', theme_key: 'default', action: 'create' }],
      themes: [],
      assets: [],
      fonts: [],
      errors: [],
    })
    mocked.importWorkspaceStylePackage.mockResolvedValue({
      styles: [{ key: 'pitch', name: '路演样式', theme_key: 'default', action: 'create' }],
      themes: [],
      assets: [],
      fonts: [],
    })
    anchorClickMock.mockImplementation(() => undefined)
    Object.defineProperty(HTMLAnchorElement.prototype, 'click', { configurable: true, value: anchorClickMock })
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:styles')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
  })

  it('应在样式卡片上提供详情查看按钮', async () => {
    render(WorkspaceStylesView, {
      global: {
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
        },
      },
    })

    expect(await screen.findByText('路演样式')).toBeInTheDocument()

    await fireEvent.click(screen.getByRole('button', { name: '查看 路演样式 详情' }))

    expect(await screen.findByText('路演样式 · 样式详情')).toBeInTheDocument()
    expect(screen.getAllByText('1920 x 1080').length).toBeGreaterThan(0)
    expect(screen.getByText('使用强标题。')).toBeInTheDocument()
  })

  it('勾选样式后应允许导出离线包', async () => {
    renderWorkspaceStylesView()

    const exportButton = await screen.findByRole('button', { name: '导出样式' })
    expect(exportButton).toBeDisabled()

    await screen.findByText('路演样式')
    await fireEvent.click(screen.getByRole('checkbox', { name: '选择导出 路演样式' }))
    expect(exportButton).not.toBeDisabled()

    await fireEvent.click(exportButton)

    expect(mocked.exportWorkspaceStylePackage).toHaveBeenCalledWith(1, { style_ids: [9] })
    expect(anchorClickMock).toHaveBeenCalledTimes(1)
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:styles')
  })

  it('选择 Zip 后应展示预检结果并确认导入', async () => {
    const { container } = renderWorkspaceStylesView()
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['zip'], 'workspace-styles.zip', { type: 'application/zip' })

    await fireEvent.change(fileInput, { target: { files: [file] } })

    expect(await screen.findByText('样式 1 个，主题 0 个，资源 0 个，字体 0 个')).toBeInTheDocument()
    expect(screen.getAllByText('路演样式').length).toBeGreaterThan(0)

    await fireEvent.click(screen.getByRole('button', { name: '确认导入' }))

    expect(mocked.validateWorkspaceStylePackageImport).toHaveBeenCalledWith(1, file)
    expect(mocked.importWorkspaceStylePackage).toHaveBeenCalledWith(1, file)
  })
})

function renderWorkspaceStylesView() {
  return render(WorkspaceStylesView, {
    global: {
      stubs: {
        RouterLink: { template: '<a><slot /></a>' },
      },
    },
  })
}
