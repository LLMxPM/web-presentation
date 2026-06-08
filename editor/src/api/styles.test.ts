/**
 * 文件功能：验证工作空间样式 API 封装的请求路径与载荷。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { getMock, postMock, patchMock, deleteMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  postMock: vi.fn(),
  patchMock: vi.fn(),
  deleteMock: vi.fn(),
}))

vi.mock('@/api/http', () => ({
  http: {
    get: getMock,
    post: postMock,
    patch: patchMock,
    delete: deleteMock,
  },
}))

import {
  copyWorkspaceStyle,
  createWorkspaceStyle,
  deleteWorkspaceStyle,
  exportWorkspaceStylePackage,
  importWorkspaceStylePackage,
  listWorkspaceStyles,
  updateWorkspaceStyle,
  validateWorkspaceStylePackageExport,
  validateWorkspaceStylePackageImport,
} from '@/api/styles'

describe('styles api', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('查询样式列表时应请求工作空间样式路径', async () => {
    getMock.mockResolvedValueOnce({ data: { items: [], total: 0 } })

    await listWorkspaceStyles(5, { page: 1, page_size: 20, keyword: 'pitch' })

    expect(getMock).toHaveBeenCalledWith('/workspaces/5/styles', {
      params: {
        page: 1,
        page_size: 20,
        keyword: 'pitch',
        status: undefined,
        sort_by: 'updated_at',
        sort_order: 'desc',
      },
    })
  })

  it('创建和更新样式时应保留 Markdown 规范字段', async () => {
    postMock.mockResolvedValueOnce({ data: { id: 1 } })
    patchMock.mockResolvedValueOnce({ data: { id: 1 } })
    const payload = {
      key: 'pitch',
      name: '路演样式',
      description: null,
      page_width: 1600,
      page_height: 900,
      base_font_size: '18px',
      icon_default_stroke_width: 3,
      show_pdf_export_button: false,
      menu_mode: 'bottom-preview' as const,
      theme_key: 'lightblue',
      style_spec_markdown: '## 版式\n- 使用强标题。',
    }

    await createWorkspaceStyle(5, payload)
    await updateWorkspaceStyle(5, 9, { style_spec_markdown: payload.style_spec_markdown })

    expect(postMock).toHaveBeenCalledWith('/workspaces/5/styles', payload)
    expect(patchMock).toHaveBeenCalledWith('/workspaces/5/styles/9', {
      style_spec_markdown: payload.style_spec_markdown,
    })
  })

  it('复制和删除样式时应使用样式 ID 路径', async () => {
    postMock.mockResolvedValueOnce({ data: { id: 2 } })
    deleteMock.mockResolvedValueOnce({ data: { message: '样式已删除。' } })

    await copyWorkspaceStyle(5, 9)
    await deleteWorkspaceStyle(5, 9)

    expect(postMock).toHaveBeenCalledWith('/workspaces/5/styles/9/copy', {})
    expect(deleteMock).toHaveBeenCalledWith('/workspaces/5/styles/9')
  })

  it('导出样式离线包时应请求下载接口并解析文件名', async () => {
    const blob = new Blob(['zip'])
    postMock.mockResolvedValueOnce({
      data: blob,
      headers: { 'content-disposition': 'attachment; filename="workspace-styles-pitch.zip"' },
    })

    const result = await exportWorkspaceStylePackage(5, { style_ids: [9] })

    expect(postMock).toHaveBeenCalledWith(
      '/workspaces/5/styles/export-package',
      { style_ids: [9] },
      { responseType: 'blob' },
    )
    expect(result).toEqual({ blob, filename: 'workspace-styles-pitch.zip' })
  })

  it('预检样式离线包导出时应请求 validate 接口', async () => {
    postMock.mockResolvedValueOnce({ data: { can_export: true } })

    const result = await validateWorkspaceStylePackageExport(5, {
      style_ids: [9],
      manual_asset_names: ['hero-image'],
    })

    expect(postMock).toHaveBeenCalledWith(
      '/workspaces/5/styles/export-package/validate',
      { style_ids: [9], manual_asset_names: ['hero-image'] },
    )
    expect(result).toEqual({ can_export: true })
  })

  it('预检和导入样式离线包时应使用 multipart 请求', async () => {
    const file = new File(['zip'], 'workspace-styles.zip', { type: 'application/zip' })
    postMock.mockResolvedValueOnce({ data: { valid: true } })
    postMock.mockResolvedValueOnce({ data: { styles: [] } })

    await validateWorkspaceStylePackageImport(5, file)
    await importWorkspaceStylePackage(5, file)

    expect(postMock).toHaveBeenNthCalledWith(
      1,
      '/workspaces/5/styles/import-package/validate',
      expect.any(FormData),
      { headers: { 'Content-Type': 'multipart/form-data' } },
    )
    expect(postMock).toHaveBeenNthCalledWith(
      2,
      '/workspaces/5/styles/import-package',
      expect.any(FormData),
      { headers: { 'Content-Type': 'multipart/form-data' } },
    )
  })
})
