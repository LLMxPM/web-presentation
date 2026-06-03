/**
 * 文件功能：验证静态资源 API 请求参数中 description 字段的传递行为。
 */
import { describe, expect, it, vi } from 'vitest'

const { getMock, postMock, putMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  postMock: vi.fn(),
  putMock: vi.fn(),
}))

vi.mock('@/api/http', () => ({
  http: {
    get: getMock,
    post: postMock,
    put: putMock,
  },
}))

import {
  batchArchiveWorkspaceAssets,
  batchDeleteWorkspaceAssets,
  listWorkspaceAssets,
  listWorkspaceAssetTags,
  listWorkspaceFonts,
  replaceWorkspaceAssetFile,
  updateWorkspaceAsset,
  uploadWorkspaceAsset,
} from '@/api/assets'

describe('assets api', () => {
  it('上传资源时传入 description，应写入 multipart form data', async () => {
    postMock.mockResolvedValueOnce({ data: { id: 1 } })

    const file = new File(['hello'], 'cover.png', { type: 'image/png' })
    await uploadWorkspaceAsset(3, file, 'image', ['首页'], 'home-cover', '首页封面插图')

    const [url, formData] = postMock.mock.calls[0]
    expect(url).toBe('/workspaces/3/assets/upload')
    expect(formData).toBeInstanceOf(FormData)
    expect((formData as FormData).get('description')).toBe('首页封面插图')
  })

  it('确认覆盖同名资源时，应写入 overwrite 标记', async () => {
    postMock.mockResolvedValueOnce({ data: { id: 1 } })

    const file = new File(['hello'], 'cover.png', { type: 'image/png' })
    await uploadWorkspaceAsset(3, file, 'image', [], undefined, undefined, true)

    const [, formData] = postMock.mock.calls[postMock.mock.calls.length - 1]
    expect((formData as FormData).get('overwrite')).toBe('true')
  })

  it('更新资源时传入 description，应写入请求体', async () => {
    putMock.mockResolvedValueOnce({ data: { id: 1 } })

    await updateWorkspaceAsset(5, 9, 'hero', 'hero.png', ['封面'], '首页头图')

    expect(putMock).toHaveBeenCalledWith('/workspaces/5/assets/9', {
      name: 'hero',
      original_name: 'hero.png',
      tags: ['封面'],
      description: '首页头图',
    })
  })

  it('替换资源文件时，应按资源 ID 上传 multipart form data', async () => {
    postMock.mockResolvedValueOnce({ data: { id: 9 } })

    const file = new File(['new'], 'hero-new.webp', { type: 'image/webp' })
    await replaceWorkspaceAssetFile(5, 9, file)

    const [url, formData, config] = postMock.mock.calls[postMock.mock.calls.length - 1]
    expect(url).toBe('/workspaces/5/assets/9/replace')
    expect((formData as FormData).get('file')).toBe(file)
    expect(config).toEqual({
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
  })

  it('读取资源标签时应传递资源类型和状态范围筛选参数', async () => {
    getMock.mockResolvedValueOnce({ data: ['品牌'] })

    await listWorkspaceAssetTags(5, { assetType: 'icon', status: 'archived', includeHistory: true, historyOnly: true })

    expect(getMock).toHaveBeenCalledWith('/workspaces/5/assets/tags', {
      params: {
        asset_type: 'icon',
        status: 'archived',
        include_history: 'true',
        history_only: 'true',
      },
    })
  })

  it('读取资源列表时应支持排除指定资源类型', async () => {
    getMock.mockResolvedValueOnce({ data: { items: [], total: 0, page: 1, page_size: 24 } })

    await listWorkspaceAssets(5, { excludeAssetType: 'font', page: 1, page_size: 24 })

    expect(getMock).toHaveBeenCalledWith('/workspaces/5/assets', {
      params: expect.objectContaining({
        exclude_asset_type: 'font',
      }),
    })
  })

  it('批量归档和删除资源时应传递资源 ID 列表', async () => {
    postMock.mockResolvedValue({ data: { requested_count: 2, succeeded_count: 2, failed_count: 0, asset_ids: [1, 2], failures: [] } })

    await batchArchiveWorkspaceAssets(5, [1, 2], '批量整理')
    await batchDeleteWorkspaceAssets(5, [1, 2])

    expect(postMock).toHaveBeenCalledWith('/workspaces/5/assets/batch-archive', {
      asset_ids: [1, 2],
      archive_reason: '批量整理',
    })
    expect(postMock).toHaveBeenCalledWith('/workspaces/5/assets/batch-delete', {
      asset_ids: [1, 2],
    })
  })

  it('读取字体注册列表时应过滤空状态筛选，避免后端枚举校验失败', async () => {
    getMock.mockResolvedValueOnce({ data: { items: [], total: 0, page: 1, page_size: 10 } })

    await listWorkspaceFonts(5, { page: 1, page_size: 10, keyword: '', status: '' })

    expect(getMock).toHaveBeenCalledWith('/workspaces/5/fonts', {
      params: {
        page: 1,
        page_size: 10,
        keyword: undefined,
        status: undefined,
        sort_by: undefined,
        sort_order: undefined,
      },
    })
  })
})
