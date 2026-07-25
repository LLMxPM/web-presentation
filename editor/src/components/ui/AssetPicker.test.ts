/**
 * 文件功能：验证通用资源选择器的类型过滤、服务端搜索分页、跨页回显与选择确认。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { AssetResponse } from '@/types/api'
import AssetPicker from './AssetPicker.vue'

const { listWorkspaceAssetsMock } = vi.hoisted(() => ({
  listWorkspaceAssetsMock: vi.fn(),
}))

vi.mock('@/api/assets', () => ({
  listWorkspaceAssets: (...args: unknown[]) => listWorkspaceAssetsMock(...args),
}))

function getEmittedEvents(view: ReturnType<typeof render>) {
  return view.emitted() as Record<string, Array<unknown[]>>
}

describe('AssetPicker', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listWorkspaceAssetsMock.mockResolvedValue({
      items: [createAsset(1, 'home', 'icon'), createAsset(2, 'mail', 'icon')],
      total: 25,
      page: 1,
      page_size: 24,
    })
  })

  it('应按配置类型请求资源，并使用服务端关键词搜索', async () => {
    listWorkspaceAssetsMock.mockImplementation((_workspaceId: number, options: { keyword?: string }) => {
      const items = options.keyword ? [createAsset(2, 'mail', 'icon')] : [createAsset(1, 'home', 'icon')]
      return Promise.resolve({ items, total: items.length, page: 1, page_size: 24 })
    })
    const view = render(AssetPicker, {
      props: {
        modelValue: null,
        workspaceId: 1,
        assetType: 'icon',
        valueMode: 'name',
      },
    })

    await fireEvent.click(screen.getByRole('button', { name: '选择' }))
    await waitFor(() => {
      expect(listWorkspaceAssetsMock).toHaveBeenCalledWith(1, {
        assetType: 'icon',
        keyword: undefined,
        page: 1,
        page_size: 24,
      })
    })

    await fireEvent.update(screen.getByPlaceholderText('按名称、文件名或标签搜索图标'), '通信')
    await waitFor(() => {
      expect(listWorkspaceAssetsMock).toHaveBeenLastCalledWith(1, expect.objectContaining({
        assetType: 'icon',
        keyword: '通信',
        page: 1,
      }))
    }, { timeout: 1000 })

    await fireEvent.click(screen.getByText('mail'))
    await fireEvent.click(screen.getByRole('button', { name: '确认选择' }))

    expect(getEmittedEvents(view)['update:modelValue']?.[0]?.[0]).toBe('mail')
    expect(getEmittedEvents(view).select?.[0]?.[0]).toMatchObject({ id: 2, name: 'mail' })
  })

  it('图片模式应使用图片文案，并稳定回显不在当前页的已选资源', async () => {
    const selectedImage = createAsset(3, 'brand_logo', 'image')
    selectedImage.name = 'brand_logo_with_a_very_long_resource_name'
    selectedImage.original_name = 'brand_logo_with_a_very_long_original_file_name.png'
    listWorkspaceAssetsMock.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 24 })
    render(AssetPicker, {
      props: {
        modelValue: 3,
        workspaceId: 1,
        assetType: 'image',
        selectedAsset: selectedImage,
        valueMode: 'id',
      },
    })

    expect(screen.getByTitle(selectedImage.name)).toBeInTheDocument()
    await fireEvent.click(screen.getByRole('button', { name: '选择' }))

    expect(await screen.findByRole('heading', { name: '选择图片' })).toBeInTheDocument()
    expect(screen.getByText('图片预览')).toBeInTheDocument()
    expect(screen.getAllByTitle(selectedImage.name)).toHaveLength(2)
    expect(screen.getByTitle(selectedImage.original_name)).toBeInTheDocument()
    expect(document.querySelector('[data-dialog-body-preset="dense"]')).toBeInTheDocument()
    expect(listWorkspaceAssetsMock).toHaveBeenCalledWith(1, expect.objectContaining({ assetType: 'image' }))
  })

  it('应根据总数翻页并请求目标页', async () => {
    render(AssetPicker, {
      props: {
        modelValue: null,
        workspaceId: 1,
        assetType: 'icon',
        valueMode: 'id',
      },
    })

    await fireEvent.click(screen.getByRole('button', { name: '选择' }))
    await screen.findByText('1 / 2')
    await fireEvent.click(screen.getByRole('button', { name: '下一页' }))

    await waitFor(() => {
      expect(listWorkspaceAssetsMock).toHaveBeenLastCalledWith(1, expect.objectContaining({
        assetType: 'icon',
        page: 2,
        page_size: 24,
      }))
    })
  })

  it('预览区域应支持切换浅色、深色和网格背景', async () => {
    render(AssetPicker, {
      props: {
        modelValue: 1,
        workspaceId: 1,
        assetType: 'icon',
        selectedAsset: createAsset(1, 'white_icon', 'icon'),
      },
    })

    await fireEvent.click(screen.getByRole('button', { name: '选择' }))
    const preview = document.querySelector('[data-preview-background]')
    expect(preview).toHaveAttribute('data-preview-background', 'checker')

    await fireEvent.click(screen.getByRole('radio', { name: '深色' }))
    expect(preview).toHaveAttribute('data-preview-background', 'dark')

    await fireEvent.click(screen.getByRole('radio', { name: '浅色' }))
    expect(preview).toHaveAttribute('data-preview-background', 'light')
  })

  it('关闭选择弹窗后应恢复触发按钮焦点', async () => {
    render(AssetPicker, {
      props: {
        modelValue: null,
        workspaceId: 1,
        assetType: 'icon',
      },
    })

    const trigger = screen.getByRole('button', { name: '选择' })
    trigger.focus()
    await fireEvent.click(trigger)
    await nextTick()

    await fireEvent.click(screen.getByRole('button', { name: '关闭选择图标' }))
    await nextTick()
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(trigger).toHaveFocus()
  })
})

/**
 * 创建选择器测试使用的资源响应。
 * @param id 资源 ID
 * @param name 资源名称
 * @param assetType 资源类型
 */
function createAsset(id: number, name: string, assetType: 'icon' | 'image'): AssetResponse {
  return {
    id,
    workspace_id: 1,
    name,
    file_name: `${name}.${assetType === 'icon' ? 'svg' : 'png'}`,
    original_name: `${name}.${assetType === 'icon' ? 'svg' : 'png'}`,
    description: null,
    file_size: 100,
    file_hash: `hash-${name}`,
    content_type: assetType === 'icon' ? 'image/svg+xml' : 'image/png',
    asset_type: assetType,
    asset_role: assetType === 'icon' ? 'foundation' : 'content',
    render_type: assetType,
    tags: assetType === 'icon' ? ['通信'] : ['品牌'],
    analysis_metadata: assetType === 'icon'
      ? {
          schema_version: 1,
          kind: 'icon',
          icon: {
            format: 'svg',
            render_mode: 'inline_svg',
            style: 'stroke',
            inline_safe: true,
            stroke_width_editable: true,
            analysis_status: 'analyzed',
            reasons: [],
          },
        }
      : null,
    render_metadata: null,
    status: 'active',
    archived_at: null,
    archive_reason: null,
    source_asset_id: null,
    history_kind: null,
    content_editable: assetType === 'icon',
    url: `https://example.com/${name}.${assetType === 'icon' ? 'svg' : 'png'}`,
    font_config: null,
    rename_block_reason: null,
    delete_block_reason: null,
    archive_block_reason: null,
    archive_warning_reasons: [],
    created_at: '2026-04-19T00:00:00Z',
    updated_at: '2026-04-19T00:00:00Z',
  }
}
