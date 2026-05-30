/**
 * 文件功能：验证项目建议引用内容资源弹窗的内容资源过滤、选择和保存行为。
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { AssetResponse, ProjectSuggestedReferenceAssetItem } from '@/types/api'
import ProjectSuggestedReferenceAssetsDialog from './ProjectSuggestedReferenceAssetsDialog.vue'

const listWorkspaceAssetsMock = vi.fn()
const getProjectSuggestedReferenceAssetsMock = vi.fn()
const updateProjectSuggestedReferenceAssetsMock = vi.fn()

vi.mock('@/api/assets', () => ({
  listWorkspaceAssets: (...args: unknown[]) => listWorkspaceAssetsMock(...args),
}))

vi.mock('@/api/catalog', () => ({
  getProjectSuggestedReferenceAssets: (...args: unknown[]) => getProjectSuggestedReferenceAssetsMock(...args),
  updateProjectSuggestedReferenceAssets: (...args: unknown[]) => updateProjectSuggestedReferenceAssetsMock(...args),
}))

vi.mock('@/api/http', () => ({
  getErrorMessage: (_error: unknown, fallback: string) => fallback,
}))

vi.mock('@/utils/message', () => ({
  Message: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

describe('ProjectSuggestedReferenceAssetsDialog', () => {
  const savedAssets: ProjectSuggestedReferenceAssetItem[] = [
    {
      id: 1,
      name: 'hero_image',
      original_name: 'hero.svg',
      description: '首页主视觉',
      asset_type: 'image',
      content_editable: true,
    },
  ]

  beforeEach(() => {
    vi.clearAllMocks()
    getProjectSuggestedReferenceAssetsMock.mockResolvedValue({ items: savedAssets })
    updateProjectSuggestedReferenceAssetsMock.mockResolvedValue({ items: savedAssets })
    listWorkspaceAssetsMock.mockResolvedValue({
      items: [
        createAsset(1, 'hero_image', 'image'),
        createAsset(2, 'chart_data', 'chart'),
        createAsset(3, 'brand_icon', 'icon'),
      ],
      total: 3,
      page: 1,
      page_size: 100,
    })
  })

  it('打开时应只按内容资源角色加载待选资源', async () => {
    renderDialog()

    await screen.findAllByText('hero_image')

    expect(listWorkspaceAssetsMock).toHaveBeenCalledWith(3, expect.objectContaining({ assetRole: 'content' }))
    expect(screen.getByText('chart_data')).toBeInTheDocument()
    expect(screen.queryByText('brand_icon')).not.toBeInTheDocument()
  })

  it('应支持选择内容资源并保存资源 ID', async () => {
    updateProjectSuggestedReferenceAssetsMock.mockResolvedValue({
      items: [...savedAssets, toSuggestedItem(createAsset(2, 'chart_data', 'chart'))],
    })
    const view = renderDialog()

    await screen.findByText('chart_data')
    await fireEvent.click(screen.getByText('chart_data'))
    await fireEvent.click(screen.getByText('保存资源'))

    await waitFor(() => {
      expect(updateProjectSuggestedReferenceAssetsMock).toHaveBeenCalledWith(7, [1, 2])
    })
    const savedEvents = view.emitted('saved') as [ProjectSuggestedReferenceAssetItem[]][]
    expect(savedEvents[0]?.[0]).toEqual([...savedAssets, toSuggestedItem(createAsset(2, 'chart_data', 'chart'))])
  })
})

function renderDialog() {
  return render(ProjectSuggestedReferenceAssetsDialog, {
    props: {
      modelValue: true,
      projectId: 7,
      workspaceId: 3,
    },
  })
}

function createAsset(id: number, name: string, assetType: AssetResponse['asset_type']): AssetResponse {
  return {
    id,
    workspace_id: 3,
    name,
    file_name: `${name}.dat`,
    original_name: `${name}.dat`,
    description: `${name} 描述`,
    file_size: 10,
    file_hash: `hash-${name}`,
    content_type: 'text/plain',
    asset_type: assetType,
    asset_role: assetType === 'icon' || assetType === 'font' ? 'foundation' : 'content',
    render_type: assetType,
    tags: [],
    analysis_metadata: null,
    render_metadata: null,
    status: 'active',
    archived_at: null,
    archive_reason: null,
    source_asset_id: null,
    history_kind: null,
    content_editable: assetType !== 'video',
    url: `/public/assets/3/hash-${name}`,
    font_config: null,
    rename_block_reason: null,
    delete_block_reason: null,
    archive_block_reason: null,
    archive_warning_reasons: [],
    created_at: '2026-05-29T08:00:00+08:00',
    updated_at: '2026-05-29T08:00:00+08:00',
  }
}

function toSuggestedItem(asset: AssetResponse): ProjectSuggestedReferenceAssetItem {
  return {
    id: asset.id,
    name: asset.name,
    original_name: asset.original_name,
    description: asset.description,
    asset_type: asset.asset_type,
    content_editable: asset.content_editable,
  }
}
