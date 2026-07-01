/**
 * 文件功能：验证资源库页面对 SVG 图片文本资源与位图图片的编辑边界展示。
 */
import { defineComponent, h } from 'vue'
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { AssetReferenceSummary, AssetRenderHintBackfillJobGroup, AssetResponse } from '@/types/api'
import AssetsView from '@/views/AssetsView.vue'

const getWorkspaceMock = vi.fn()
const listWorkspaceAssetsMock = vi.fn()
const listWorkspaceAssetTagsMock = vi.fn()
const getWorkspaceAssetContentMock = vi.fn()
const previewWorkspaceAssetReferencesMock = vi.fn()
const uploadWorkspaceAssetMock = vi.fn()
const updateWorkspaceAssetMock = vi.fn()
const batchArchiveWorkspaceAssetsMock = vi.fn()
const batchDeleteWorkspaceAssetsMock = vi.fn()
const batchRestoreWorkspaceAssetsMock = vi.fn()
const createAssetRenderHintBackfillJobsMock = vi.fn()
const exportWorkspaceAssetPackageMock = vi.fn()
const importWorkspaceAssetPackageMock = vi.fn()
const waitForAssetRenderHintBackfillJobGroupMock = vi.fn()
const createConfirmMock = vi.fn()
const routerPushMock = vi.fn()
const createObjectURLMock = vi.fn()
const revokeObjectURLMock = vi.fn()
const anchorClickMock = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => ({
    params: {
      workspaceId: '7',
    },
    query: {},
  }),
  useRouter: () => ({
    push: routerPushMock,
  }),
}))

vi.mock('@/api/catalog', () => ({
  getWorkspace: (...args: unknown[]) => getWorkspaceMock(...args),
}))

vi.mock('@/api/assets', () => ({
  archiveWorkspaceAsset: vi.fn(),
  batchArchiveWorkspaceAssets: (...args: unknown[]) => batchArchiveWorkspaceAssetsMock(...args),
  batchDeleteWorkspaceAssets: (...args: unknown[]) => batchDeleteWorkspaceAssetsMock(...args),
  batchRestoreWorkspaceAssets: (...args: unknown[]) => batchRestoreWorkspaceAssetsMock(...args),
  copyWorkspaceAsset: vi.fn(),
  createAssetRenderHintBackfillJobs: (...args: unknown[]) => createAssetRenderHintBackfillJobsMock(...args),
  createWorkspaceAssetContent: vi.fn(),
  deleteWorkspaceAsset: vi.fn(),
  exportWorkspaceAssetPackage: (...args: unknown[]) => exportWorkspaceAssetPackageMock(...args),
  getWorkspaceAssetContent: (...args: unknown[]) => getWorkspaceAssetContentMock(...args),
  importWorkspaceAssetPackage: (...args: unknown[]) => importWorkspaceAssetPackageMock(...args),
  listWorkspaceAssetTags: (...args: unknown[]) => listWorkspaceAssetTagsMock(...args),
  listWorkspaceAssets: (...args: unknown[]) => listWorkspaceAssetsMock(...args),
  previewWorkspaceAssetReferences: (...args: unknown[]) => previewWorkspaceAssetReferencesMock(...args),
  replaceWorkspaceAssetFile: vi.fn(),
  restoreWorkspaceAsset: vi.fn(),
  updateWorkspaceAsset: (...args: unknown[]) => updateWorkspaceAssetMock(...args),
  updateWorkspaceAssetContent: vi.fn(),
  uploadWorkspaceAsset: (...args: unknown[]) => uploadWorkspaceAssetMock(...args),
  waitForAssetRenderHintBackfillJobGroup: (...args: unknown[]) => waitForAssetRenderHintBackfillJobGroupMock(...args),
}))

vi.mock('@/utils/message', () => ({
  createConfirm: (...args: unknown[]) => createConfirmMock(...args),
  Message: {
    error: vi.fn(),
    info: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
  },
}))

describe('AssetsView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    createObjectURLMock.mockReturnValue('blob:assets-zip')
    Object.defineProperty(window.URL, 'createObjectURL', { configurable: true, value: createObjectURLMock })
    Object.defineProperty(window.URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURLMock })
    Object.defineProperty(HTMLAnchorElement.prototype, 'click', { configurable: true, value: anchorClickMock })
    createConfirmMock.mockResolvedValue(true)
    getWorkspaceMock.mockResolvedValue({ id: 7, name: '默认工作空间' })
    listWorkspaceAssetTagsMock.mockResolvedValue(['封面'])
    listWorkspaceAssetsMock.mockResolvedValue({
      items: [
        createImageAsset({
          id: 1,
          name: 'hero_illustration',
          original_name: 'hero_illustration.svg',
          content_type: 'image/svg+xml',
          content_editable: true,
          file_hash: 'hash-svg-image',
        }),
        createImageAsset({
          id: 2,
          name: 'bitmap_photo',
          original_name: 'bitmap_photo.png',
          content_type: 'image/png',
          content_editable: false,
          file_hash: 'hash-png-image',
          url: 'https://backend.example.com/public/assets/7/hash-png-image',
        }),
      ],
      total: 2,
      page: 1,
      page_size: 24,
    })
    getWorkspaceAssetContentMock.mockResolvedValue({
      asset: createImageAsset({
        id: 1,
        name: 'hero_illustration',
        original_name: 'hero_illustration.svg',
        content_type: 'image/svg+xml',
        content_editable: true,
        file_hash: 'hash-svg-image',
      }),
      content: '<svg xmlns="http://www.w3.org/2000/svg"></svg>',
    })
    previewWorkspaceAssetReferencesMock.mockResolvedValue(createReferenceSummary())
    uploadWorkspaceAssetMock.mockResolvedValue(createImageAsset({
      id: 3,
      name: 'uploaded_cover',
      original_name: 'uploaded_cover.png',
      content_type: 'image/png',
      content_editable: false,
      file_hash: 'hash-uploaded-cover',
    }))
    updateWorkspaceAssetMock.mockImplementation((
      _workspaceId: number,
      _assetId: number,
      name: string,
      originalName: string,
      tags: string[],
      description: string | null,
      approxAspectRatio?: string | null,
    ) => Promise.resolve(createImageAsset({
      name,
      original_name: originalName,
      tags,
      description,
      approx_aspect_ratio: approxAspectRatio === undefined ? '16:9' : approxAspectRatio,
      aspect_ratio_source: approxAspectRatio === undefined ? 'auto' : 'manual',
    })))
    batchArchiveWorkspaceAssetsMock.mockResolvedValue({
      requested_count: 2,
      succeeded_count: 2,
      failed_count: 0,
      asset_ids: [1, 2],
      failures: [],
    })
    batchDeleteWorkspaceAssetsMock.mockResolvedValue({
      requested_count: 1,
      succeeded_count: 1,
      failed_count: 0,
      asset_ids: [1],
      failures: [],
    })
    batchRestoreWorkspaceAssetsMock.mockResolvedValue({
      requested_count: 1,
      succeeded_count: 1,
      failed_count: 0,
      asset_ids: [1],
      failures: [],
    })
    exportWorkspaceAssetPackageMock.mockResolvedValue({
      blob: new Blob(['zip']),
      filename: 'workspace-assets.zip',
    })
    createAssetRenderHintBackfillJobsMock.mockResolvedValue(createBackfillGroup({
      status: 'succeeded',
      requested_count: 0,
    }))
    waitForAssetRenderHintBackfillJobGroupMock.mockResolvedValue(createBackfillGroup({
      status: 'succeeded',
      requested_count: 0,
    }))
    importWorkspaceAssetPackageMock.mockResolvedValue({
      imported_count: 1,
      updated_count: 0,
      reused_count: 0,
      failed_count: 0,
      assets: [],
      failures: [],
    })
  })

  it('SVG 图片应展示为可编辑，位图图片仍不可编辑', async () => {
    renderAssetsView()

    await waitFor(() => {
      expect(screen.getAllByText('hero_illustration').length).toBeGreaterThan(0)
      expect(screen.getByText('bitmap_photo')).toBeInTheDocument()
    })
    await fireEvent.click(screen.getAllByText('hero_illustration')[0])
    await fireEvent.click(screen.getByText('内容编辑'))

    await waitFor(() => {
      expect(screen.getByText('写入内容会自动保留写入前副本。')).toBeInTheDocument()
    })
    expect(screen.getByDisplayValue('<svg xmlns="http://www.w3.org/2000/svg"></svg>')).toBeInTheDocument()

    await fireEvent.click(screen.getByText('关闭'))

    await fireEvent.click(screen.getByText('bitmap_photo'))
    await fireEvent.click(screen.getByText('内容编辑'))

    await waitFor(() => {
      expect(screen.getByText('该资源不支持文本内容编辑')).toBeInTheDocument()
    })
    expect(screen.getByText('位图图标和位图图片只能复制、归档、删除或维护元数据。')).toBeInTheDocument()
  })

  it('资源管理页默认展示全部非字体资源，并不提供字体类型管理入口', async () => {
    renderAssetsView()

    await waitFor(() => {
      expect(listWorkspaceAssetsMock).toHaveBeenCalledWith(7, expect.objectContaining({ excludeAssetType: 'font' }))
      expect(screen.getAllByText('hero_illustration').length).toBeGreaterThan(0)
    })
    expect(screen.getAllByRole('button', { name: '全部' }).length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: '字体' })).toBeNull()

    await fireEvent.click(screen.getByText('上传资源'))
    expect(screen.queryByRole('option', { name: '字体' })).toBeNull()
    await fireEvent.click(screen.getByText('取消'))

    await fireEvent.click(screen.getByText('新建内容资源'))
    expect(screen.queryByRole('option', { name: '字体' })).toBeNull()
  })

  it('选择标签时应按当前状态范围筛选资源列表', async () => {
    renderAssetsView()

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '封面' })).toBeInTheDocument()
    })
    await fireEvent.click(screen.getByRole('button', { name: '封面' }))

    await waitFor(() => {
      expect(listWorkspaceAssetsMock).toHaveBeenLastCalledWith(7, expect.objectContaining({
        status: 'active',
        includeHistory: false,
        historyOnly: false,
        excludeAssetType: 'font',
        tag: '封面',
      }))
    })
  })

  it('切换归档视图时应按归档范围重新读取标签', async () => {
    renderAssetsView()

    await waitFor(() => {
      expect(listWorkspaceAssetTagsMock).toHaveBeenCalledWith(7, expect.objectContaining({
        status: 'active',
        includeHistory: false,
        historyOnly: false,
      }))
    })
    await fireEvent.click(screen.getByText('已归档'))

    await waitFor(() => {
      expect(listWorkspaceAssetTagsMock).toHaveBeenCalledWith(7, expect.objectContaining({
        status: 'archived',
        includeHistory: false,
        historyOnly: false,
      }))
    })
  })

  it('新建内容资源应允许选择图片并默认生成 image.svg', async () => {
    renderAssetsView()

    await waitFor(() => {
      expect(screen.getAllByText('hero_illustration').length).toBeGreaterThan(0)
    })
    await fireEvent.click(screen.getByText('新建内容资源'))

    const imageOption = screen.getByRole('option', { name: '图片' })
    expect(imageOption).toBeInTheDocument()
    await fireEvent.update(imageOption.closest('select')!, 'image')

    expect(screen.getByDisplayValue('image.svg')).toBeInTheDocument()
  })

  it('资源管理页应能按选择类型上传资源', async () => {
    const { container } = renderAssetsView()

    await waitFor(() => {
      expect(screen.getAllByText('hero_illustration').length).toBeGreaterThan(0)
    })
    await fireEvent.click(screen.getByText('上传资源'))
    await fireEvent.update(screen.getByRole('option', { name: '图片' }).closest('select')!, 'image')
    await fireEvent.update(screen.getByPlaceholderText('可留空'), '封面,营销')
    await fireEvent.change(
      container.querySelector('input[type="file"][multiple]')!,
      { target: { files: [new File(['fake'], 'uploaded_cover.png', { type: 'image/png' })] } },
    )

    await waitFor(() => {
      expect(uploadWorkspaceAssetMock).toHaveBeenCalledWith(
        7,
        expect.any(File),
        'image',
        ['封面', '营销'],
      )
    })
  })

  it('资源详情应支持维护近似比例', async () => {
    renderAssetsView()

    await waitFor(() => {
      expect(screen.getAllByText('hero_illustration').length).toBeGreaterThan(0)
    })
    await fireEvent.click(screen.getAllByText('hero_illustration')[0])
    await fireEvent.update(screen.getByPlaceholderText('16:9'), '4:3')
    await fireEvent.click(screen.getByText('保存信息'))

    await waitFor(() => {
      expect(updateWorkspaceAssetMock).toHaveBeenCalledWith(
        7,
        1,
        'hero_illustration',
        'hero_illustration.svg',
        [],
        null,
        '4:3',
      )
    })
  })

  it('资源多选操作应提供比例重算入口', async () => {
    const formulaAsset = createImageAsset({
      id: 10,
      name: 'formula_ratio',
      original_name: 'formula_ratio.tex',
      content_type: 'text/plain',
      asset_type: 'formula',
      render_type: 'formula',
      content_editable: true,
    })
    listWorkspaceAssetsMock.mockResolvedValue({
      items: [formulaAsset],
      total: 1,
      page: 1,
      page_size: 24,
    })

    renderAssetsView()

    await waitFor(() => {
      expect(screen.getByText('formula_ratio')).toBeInTheDocument()
    })
    expect(screen.queryByText('重新计算比例')).toBeNull()
    await fireEvent.click(screen.getByLabelText('选择资源 formula_ratio'))
    await fireEvent.click(screen.getByText('重新计算比例'))

    expect(screen.getByText('重新计算选中资源比例')).toBeInTheDocument()
    expect(screen.getByText('预览结果')).toBeInTheDocument()
    expect(screen.getByText('仅处理当前已勾选的 Image、Video、Draw.io、Formula、Mermaid 资源，其他类型会自动忽略。')).toBeInTheDocument()
  })

  it('图片资源多选后应支持重新计算比例', async () => {
    const imageAsset = createImageAsset({
      id: 13,
      name: 'poster_image',
      original_name: 'poster_image.png',
      content_type: 'image/png',
      asset_type: 'image',
      render_type: 'image',
      content_editable: false,
    })
    listWorkspaceAssetsMock.mockResolvedValue({
      items: [imageAsset],
      total: 1,
      page: 1,
      page_size: 24,
    })
    createAssetRenderHintBackfillJobsMock.mockResolvedValue(createBackfillGroup({
      status: 'succeeded',
      requested_count: 1,
      succeeded_count: 1,
    }))

    renderAssetsView()

    await waitFor(() => {
      expect(screen.getByText('poster_image')).toBeInTheDocument()
    })
    await fireEvent.click(screen.getByLabelText('选择资源 poster_image'))
    await fireEvent.click(screen.getByText('重新计算比例'))
    await fireEvent.click(screen.getByText('开始预览'))

    await waitFor(() => {
      expect(createAssetRenderHintBackfillJobsMock).toHaveBeenCalledWith(7, expect.objectContaining({
        asset_ids: [13],
        asset_types: ['image'],
        mode: 'preview',
      }))
    })
  })

  it('预览比例回填后应支持应用可更新项', async () => {
    const formulaAsset = createImageAsset({
      id: 11,
      name: 'formula_ratio',
      original_name: 'formula_ratio.tex',
      content_type: 'text/plain',
      asset_type: 'formula',
      render_type: 'formula',
      content_editable: true,
    })
    listWorkspaceAssetsMock.mockResolvedValue({
      items: [formulaAsset],
      total: 1,
      page: 1,
      page_size: 24,
    })
    createAssetRenderHintBackfillJobsMock
      .mockResolvedValueOnce(createBackfillGroup({
        job_group_id: 'preview-group',
        status: 'pending',
        requested_count: 1,
        pending_count: 1,
      }))
      .mockResolvedValueOnce(createBackfillGroup({
        job_group_id: 'apply-group',
        status: 'pending',
        requested_count: 1,
        pending_count: 1,
      }))
    waitForAssetRenderHintBackfillJobGroupMock
      .mockResolvedValueOnce(createBackfillGroup({
        job_group_id: 'preview-group',
        status: 'succeeded',
        requested_count: 1,
        succeeded_count: 1,
        jobs: [{
          id: 1,
          job_group_id: 'preview-group',
          workspace_id: 7,
          asset_id: 11,
          asset_name: 'formula_ratio',
          asset_type: 'formula',
          source: 'manual',
          mode: 'preview',
          overwrite_manual: false,
          status: 'succeeded',
          attempt_count: 1,
          current_render_metadata: null,
          next_render_metadata: { aspect_ratio: '2:1' },
          current_approx_aspect_ratio: null,
          next_approx_aspect_ratio: '2:1',
          error_code: null,
          error_message: null,
          created_by: 1,
          created_at: '2026-07-01T10:00:00+08:00',
          updated_at: '2026-07-01T10:00:00+08:00',
          started_at: '2026-07-01T10:00:00+08:00',
          finished_at: '2026-07-01T10:00:01+08:00',
        }],
      }))
      .mockResolvedValueOnce(createBackfillGroup({
        job_group_id: 'apply-group',
        status: 'succeeded',
        requested_count: 1,
        succeeded_count: 1,
      }))

    renderAssetsView()

    await waitFor(() => {
      expect(screen.getByText('formula_ratio')).toBeInTheDocument()
    })
    await fireEvent.click(screen.getByLabelText('选择资源 formula_ratio'))
    await fireEvent.click(screen.getByText('重新计算比例'))
    await fireEvent.click(screen.getByText('开始预览'))

    await waitFor(() => {
      expect(createAssetRenderHintBackfillJobsMock).toHaveBeenCalledWith(7, expect.objectContaining({
        asset_ids: [11],
        asset_types: ['formula'],
        mode: 'preview',
      }))
    })
    await waitFor(() => {
      expect(screen.getByText('应用可更新项')).toBeInTheDocument()
    })
    await fireEvent.click(screen.getByText('应用可更新项'))

    await waitFor(() => {
      expect(createAssetRenderHintBackfillJobsMock).toHaveBeenLastCalledWith(7, expect.objectContaining({
        asset_ids: [11],
        mode: 'apply',
      }))
    })
  })

  it('Formula 资源详情应支持重新计算比例', async () => {
    const formulaAsset = createImageAsset({
      id: 12,
      name: 'detail_formula',
      original_name: 'detail_formula.tex',
      content_type: 'text/plain',
      asset_type: 'formula',
      render_type: 'formula',
      content_editable: true,
      approx_aspect_ratio: null,
      aspect_ratio_source: null,
    })
    listWorkspaceAssetsMock.mockResolvedValue({
      items: [formulaAsset],
      total: 1,
      page: 1,
      page_size: 24,
    })
    createAssetRenderHintBackfillJobsMock.mockResolvedValue(createBackfillGroup({
      status: 'succeeded',
      requested_count: 1,
      succeeded_count: 1,
    }))

    renderAssetsView()

    await waitFor(() => {
      expect(screen.getByText('detail_formula')).toBeInTheDocument()
    })
    await fireEvent.click(screen.getByText('detail_formula'))
    await fireEvent.click(screen.getByText('重新计算比例'))

    await waitFor(() => {
      expect(createAssetRenderHintBackfillJobsMock).toHaveBeenCalledWith(7, expect.objectContaining({
        asset_ids: [12],
        asset_types: ['formula'],
        mode: 'apply',
      }))
    })
  })

  it('替换资源文件时应按当前资源类型限制可选扩展名', async () => {
    const { container } = renderAssetsView()

    await waitFor(() => {
      expect(screen.getAllByText('hero_illustration').length).toBeGreaterThan(0)
    })
    await fireEvent.click(screen.getAllByText('hero_illustration')[0])

    const replaceInput = container.querySelector('input[type="file"]:not([multiple])') as HTMLInputElement
    expect(replaceInput.accept).toContain('.png')
    expect(replaceInput.accept).toContain('.svg')
    expect(replaceInput.accept).not.toContain('.ttf')
  })

  it('启用资源应支持多选后批量归档', async () => {
    renderAssetsView()

    await waitFor(() => {
      expect(screen.getAllByText('hero_illustration').length).toBeGreaterThan(0)
    })
    await fireEvent.click(screen.getByLabelText('选择资源 hero_illustration'))
    await fireEvent.click(screen.getByLabelText('选择资源 bitmap_photo'))
    await fireEvent.click(screen.getByText('批量归档'))

    await waitFor(() => {
      expect(batchArchiveWorkspaceAssetsMock).toHaveBeenCalledWith(7, [1, 2])
    })
  })

  it('选中资源后应支持批量导出 zip', async () => {
    renderAssetsView()

    await waitFor(() => {
      expect(screen.getAllByText('hero_illustration').length).toBeGreaterThan(0)
    })
    await fireEvent.click(screen.getByLabelText('选择资源 hero_illustration'))
    await fireEvent.click(screen.getByLabelText('选择资源 bitmap_photo'))
    await fireEvent.click(screen.getByText('导出选中'))

    await waitFor(() => {
      expect(exportWorkspaceAssetPackageMock).toHaveBeenCalledWith(7, [1, 2])
      expect(anchorClickMock).toHaveBeenCalledTimes(1)
    })
    expect(createObjectURLMock).toHaveBeenCalledWith(expect.any(Blob))
  })

  it('应支持选择资源压缩包导入并刷新列表', async () => {
    const { container } = renderAssetsView()

    await waitFor(() => {
      expect(screen.getAllByText('hero_illustration').length).toBeGreaterThan(0)
    })
    await fireEvent.change(
      container.querySelector('input[type="file"][accept=".zip,application/zip"]')!,
      { target: { files: [new File(['zip'], 'workspace-assets.zip', { type: 'application/zip' })] } },
    )

    await waitFor(() => {
      expect(importWorkspaceAssetPackageMock).toHaveBeenCalledWith(7, expect.any(File))
      expect(listWorkspaceAssetsMock).toHaveBeenCalled()
    })
  })

  it('归档资源应支持多选后批量恢复', async () => {
    listWorkspaceAssetsMock.mockImplementation((_workspaceId: number, options: { status?: string }) => {
      if (options.status === 'archived') {
        return Promise.resolve({
          items: [
            createImageAsset({
              id: 5,
              name: 'archived_restore_cover',
              status: 'archived',
              archived_at: '2026-05-01T11:00:00+08:00',
            }),
          ],
          total: 1,
          page: 1,
          page_size: 24,
        })
      }
      return Promise.resolve({ items: [], total: 0, page: 1, page_size: 24 })
    })
    batchRestoreWorkspaceAssetsMock.mockResolvedValue({
      requested_count: 1,
      succeeded_count: 1,
      failed_count: 0,
      asset_ids: [5],
      failures: [],
    })
    renderAssetsView()

    await fireEvent.click(screen.getByText('已归档'))
    await waitFor(() => {
      expect(screen.getByText('archived_restore_cover')).toBeInTheDocument()
    })
    await fireEvent.click(screen.getByLabelText('选择资源 archived_restore_cover'))
    await fireEvent.click(screen.getByText('批量恢复'))

    await waitFor(() => {
      expect(batchRestoreWorkspaceAssetsMock).toHaveBeenCalledWith(7, [5])
    })
  })

  it('归档资源应支持多选后批量删除', async () => {
    listWorkspaceAssetsMock.mockImplementation((_workspaceId: number, options: { status?: string }) => {
      if (options.status === 'archived') {
        return Promise.resolve({
          items: [
            createImageAsset({
              id: 4,
              name: 'archived_cover',
              status: 'archived',
              archived_at: '2026-05-01T11:00:00+08:00',
            }),
          ],
          total: 1,
          page: 1,
          page_size: 24,
        })
      }
      return Promise.resolve({ items: [], total: 0, page: 1, page_size: 24 })
    })
    batchDeleteWorkspaceAssetsMock.mockResolvedValue({
      requested_count: 1,
      succeeded_count: 1,
      failed_count: 0,
      asset_ids: [4],
      failures: [],
    })
    renderAssetsView()

    await fireEvent.click(screen.getByText('已归档'))
    await waitFor(() => {
      expect(screen.getByText('archived_cover')).toBeInTheDocument()
    })
    await fireEvent.click(screen.getByLabelText('选择资源 archived_cover'))
    await fireEvent.click(screen.getByText('批量删除'))

    await waitFor(() => {
      expect(batchDeleteWorkspaceAssetsMock).toHaveBeenCalledWith(7, [4])
    })
  })
})

function renderAssetsView() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return render(AssetsView, {
    global: {
      plugins: [
        [VueQueryPlugin, { queryClient }] as [typeof VueQueryPlugin, { queryClient: QueryClient }],
      ],
      stubs: {
        AssetPreviewFrame: defineComponent({
          name: 'AssetPreviewFrame',
          props: {
            asset: {
              type: Object,
              default: null,
            },
          },
          setup(props) {
            return () => h('section', `资源预览：${(props.asset as AssetResponse | null)?.name || ''}`)
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
      },
    },
  })
}

function createImageAsset(overrides: Partial<AssetResponse>): AssetResponse {
  return {
    id: 1,
    workspace_id: 7,
    name: 'hero_illustration',
    file_name: 'hash.svg',
    original_name: 'hero_illustration.svg',
    description: null,
    file_size: 128,
    file_hash: 'hash-svg-image',
    content_type: 'image/svg+xml',
    asset_type: 'image',
    asset_role: 'content',
    render_type: 'image',
    tags: [],
    analysis_metadata: null,
    render_metadata: null,
    status: 'active',
    archived_at: null,
    archive_reason: null,
    source_asset_id: null,
    history_kind: null,
    content_editable: true,
    url: 'https://backend.example.com/public/assets/7/hash-svg-image',
    font_config: null,
    rename_block_reason: null,
    delete_block_reason: null,
    archive_block_reason: null,
    archive_warning_reasons: [],
    created_at: '2026-05-01T10:00:00+08:00',
    updated_at: '2026-05-01T10:00:00+08:00',
    ...overrides,
  }
}

function createBackfillGroup(overrides: Partial<AssetRenderHintBackfillJobGroup>): AssetRenderHintBackfillJobGroup {
  return {
    job_group_id: 'group-1',
    status: 'succeeded',
    requested_count: 0,
    pending_count: 0,
    running_count: 0,
    succeeded_count: 0,
    failed_count: 0,
    skipped_count: 0,
    asset_ids: [],
    jobs: [],
    failures: [],
    ...overrides,
  }
}

function createReferenceSummary(): AssetReferenceSummary {
  return {
    theme_count: 0,
    font_count: 0,
    page_count: 0,
    component_count: 0,
    component_version_count: 0,
    references: [],
    has_references: false,
  }
}
