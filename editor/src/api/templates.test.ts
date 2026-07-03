/**
 * 文件功能：验证项目模板包 API 封装的请求路径、载荷和下载文件名解析。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { postMock } = vi.hoisted(() => ({
  postMock: vi.fn(),
}))

vi.mock('@/api/http', () => ({
  http: {
    post: postMock,
  },
}))

import {
  createProjectTemplatePackagePreviewArtifact,
  exportProjectTemplatePackage,
  importProjectTemplatePackage,
  validateProjectTemplatePackageExport,
  validateProjectTemplatePackageImport,
} from '@/api/templates'

describe('templates api', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('预检和导出模板包时应使用项目模板包路径', async () => {
    const payload = {
      metadata: { name: '模板' },
      refresh_screenshots: true,
    }
    const blob = new Blob(['zip'])
    postMock.mockResolvedValueOnce({ data: { can_export: true } })
    postMock.mockResolvedValueOnce({
      data: blob,
      headers: { 'content-disposition': "attachment; filename=\"fallback.wptemplate.zip\"; filename*=UTF-8''%E5%B9%B4%E5%BA%A6%E5%A4%8D%E7%9B%98.wptemplate.zip" },
    })

    const validation = await validateProjectTemplatePackageExport(12, payload)
    const download = await exportProjectTemplatePackage(12, payload)

    expect(postMock).toHaveBeenNthCalledWith(
      1,
      '/projects/12/template-package/export/validate',
      payload,
    )
    expect(postMock).toHaveBeenNthCalledWith(
      2,
      '/projects/12/template-package/export',
      payload,
      { responseType: 'blob', timeout: 600000 },
    )
    expect(validation).toEqual({ can_export: true })
    expect(download).toEqual({ blob, filename: '年度复盘.wptemplate.zip' })
  })

  it('预检、预览和导入模板包时应使用 multipart archive 字段', async () => {
    const file = new File(['zip'], 'demo.wptemplate.zip', { type: 'application/zip' })
    postMock.mockResolvedValueOnce({ data: { valid: true } })
    postMock.mockResolvedValueOnce({ data: { artifact_id: 'tpl_demo' } })
    postMock.mockResolvedValueOnce({ data: { project_id: 20 } })

    await validateProjectTemplatePackageImport(7, file)
    await createProjectTemplatePackagePreviewArtifact(7, file)
    await importProjectTemplatePackage(7, file)

    expect(postMock).toHaveBeenNthCalledWith(
      1,
      '/workspaces/7/template-packages/import/validate',
      expect.any(FormData),
      { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 180000 },
    )
    expect(postMock).toHaveBeenNthCalledWith(
      2,
      '/workspaces/7/template-packages/preview-artifact',
      expect.any(FormData),
      { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 180000 },
    )
    expect(postMock).toHaveBeenNthCalledWith(
      3,
      '/workspaces/7/template-packages/import',
      expect.any(FormData),
      { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 180000 },
    )
    const firstFormData = postMock.mock.calls[0]?.[1] as FormData
    expect(firstFormData.get('archive')).toBe(file)
  })
})
