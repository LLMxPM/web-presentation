/**
 * 文件功能：验证资源侧边栏按需弹窗预览与多选模式点击行为。
 */
import { defineComponent, h } from 'vue'
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AssetManagerPanel from '@/components/project/AssetManagerPanel.vue'
import type { AssetResponse } from '@/types/api'

const listWorkspaceAssetsMock = vi.fn()
const listWorkspaceAssetTagsMock = vi.fn()
const routerPushMock = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: routerPushMock,
  }),
}))

vi.mock('@/api/assets', () => ({
  archiveWorkspaceAsset: vi.fn(),
  createWorkspaceAssetContent: vi.fn(),
  createWorkspaceFont: vi.fn(),
  deleteWorkspaceAsset: vi.fn(),
  deleteWorkspaceFont: vi.fn(),
  listWorkspaceAssetTags: (...args: unknown[]) => listWorkspaceAssetTagsMock(...args),
  listWorkspaceAssets: (...args: unknown[]) => listWorkspaceAssetsMock(...args),
  replaceWorkspaceAssetFile: vi.fn(),
  updateWorkspaceAsset: vi.fn(),
  updateWorkspaceFont: vi.fn(),
  uploadWorkspaceAsset: vi.fn(),
}))

describe('AssetManagerPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listWorkspaceAssetsMock.mockResolvedValue({
      items: [createSvgAsset()],
      total: 1,
      page: 1,
      page_size: 24,
    })
    listWorkspaceAssetTagsMock.mockResolvedValue([])
  })

  it('点击 SVG 图标缩略区应按需打开 Runtime 预览弹窗', async () => {
    const { container } = renderPanel()

    await waitFor(() => {
      expect(screen.getByText('brand_icon')).toBeInTheDocument()
    })
    expect(screen.queryByTestId('asset-preview-frame')).toBeNull()

    await fireEvent.click(container.querySelector('img')!)

    expect(screen.getByTestId('asset-preview-frame')).toHaveTextContent('Runtime 资源预览：brand_icon')
  })

  it('侧边栏不再提供多选模式，点击缩略区直接打开预览', async () => {
    const { container } = renderPanel()

    await waitFor(() => {
      expect(screen.getByText('brand_icon')).toBeInTheDocument()
    })
    expect(screen.queryByTitle('多选模式')).toBeNull()
    await fireEvent.click(container.querySelector('img')!)

    expect(screen.getByTestId('asset-preview-frame')).toHaveTextContent('Runtime 资源预览：brand_icon')
  })

  it('资源库侧边栏不再展示字体资源类型', async () => {
    renderPanel()

    await waitFor(() => {
      expect(screen.getByText('brand_icon')).toBeInTheDocument()
    })
    expect(screen.queryByText('字体')).toBeNull()
  })

  it('图标资源只有单一类型时不展示冗余二级类型栏', async () => {
    renderPanel()

    await waitFor(() => {
      expect(screen.getByText('brand_icon')).toBeInTheDocument()
    })

    expect(screen.getByText('图标资源')).toBeInTheDocument()
    expect(screen.queryByText('图标')).toBeNull()
  })

  it('收到智能体资源写入事件后应刷新资源列表和标签', async () => {
    renderPanel()

    await waitFor(() => {
      expect(screen.getByText('brand_icon')).toBeInTheDocument()
    })
    const initialAssetCallCount = listWorkspaceAssetsMock.mock.calls.length
    const initialTagCallCount = listWorkspaceAssetTagsMock.mock.calls.length

    window.dispatchEvent(new CustomEvent('agent:asset-updated', {
      detail: {
        workspaceId: 7,
        assetId: 1,
        toolName: 'apply_resource_content_diff',
        result: { success: true, asset_id: 1 },
      },
    }))

    await waitFor(() => {
      expect(listWorkspaceAssetsMock.mock.calls.length).toBeGreaterThan(initialAssetCallCount)
      expect(listWorkspaceAssetTagsMock.mock.calls.length).toBeGreaterThan(initialTagCallCount)
    })
  })

  it('图片快速预览应提供可切换的背景画布', async () => {
    listWorkspaceAssetsMock.mockResolvedValue({
      items: [createRasterAsset()],
      total: 1,
      page: 1,
      page_size: 24,
    })

    const { container } = renderPanel()

    await waitFor(() => {
      expect(screen.getByText('cover_image')).toBeInTheDocument()
    })

    await fireEvent.click(container.querySelector('img')!)

    const panel = document.body.querySelector('.dialog-panel')
    expect(panel).toHaveStyle({ background: 'transparent' })
    expect(panel).toHaveClass('!pointer-events-none', '!border-0', '!bg-transparent', '!shadow-none')
    expect(document.querySelector('[data-preview-background]')).toHaveAttribute('data-preview-background', 'checker')

    await fireEvent.click(screen.getByRole('radio', { name: '深色' }))
    expect(document.querySelector('[data-preview-background]')).toHaveAttribute('data-preview-background', 'dark')
    expect(screen.getByLabelText('关闭资源预览')).toBeInTheDocument()
  })
})

function renderPanel() {
  return render(AssetManagerPanel, {
    props: {
      modelValue: true,
      workspaceId: 7,
    },
    global: {
      stubs: {
        teleport: true,
        AssetPreviewFrame: createAssetPreviewFrameStub(),
      },
    },
  })
}

function createAssetPreviewFrameStub() {
  return defineComponent({
    name: 'AssetPreviewFrame',
    props: {
      asset: {
        type: Object,
        default: null,
      },
    },
    setup(props) {
      return () => {
        const asset = props.asset as AssetResponse | null
        return h('section', { 'data-testid': 'asset-preview-frame' }, `Runtime 资源预览：${asset?.name || ''}`)
      }
    },
  })
}

function createSvgAsset(): AssetResponse {
  return {
    id: 1,
    workspace_id: 7,
    name: 'brand_icon',
    file_name: 'hash.svg',
    original_name: 'brand_icon.svg',
    description: null,
    file_size: 128,
    file_hash: 'hash-svg',
    content_type: 'image/svg+xml',
    asset_type: 'icon',
    asset_role: 'foundation',
    render_type: 'icon',
    tags: [],
    analysis_metadata: {
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
    },
    render_metadata: null,
    status: 'active',
    archived_at: null,
    archive_reason: null,
    source_asset_id: null,
    history_kind: null,
    content_editable: true,
    url: 'https://backend.example.com/public/assets/7/hash-svg',
    font_config: null,
    rename_block_reason: null,
    delete_block_reason: null,
    archive_block_reason: null,
    archive_warning_reasons: [],
    created_at: '2026-05-01T10:00:00+08:00',
    updated_at: '2026-05-01T10:00:00+08:00',
  }
}

function createRasterAsset(): AssetResponse {
  return {
    ...createSvgAsset(),
    name: 'cover_image',
    original_name: 'cover-image.png',
    file_hash: 'hash-png',
    content_type: 'image/png',
    asset_type: 'image',
    render_type: 'image',
    url: 'https://backend.example.com/public/assets/7/hash-png',
  }
}
