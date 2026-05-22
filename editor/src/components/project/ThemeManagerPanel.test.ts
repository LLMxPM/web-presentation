/**
 * 文件功能：验证主题字体侧栏的只读浏览、字体预览与字体名称复制行为。
 */
import { defineComponent, h } from 'vue'
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ThemeManagerPanel from '@/components/project/ThemeManagerPanel.vue'

const getWorkspaceMock = vi.fn()
const listWorkspaceThemesMock = vi.fn()
const listWorkspaceFontsMock = vi.fn()
const routerPushMock = vi.fn()
const clipboardWriteTextMock = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: routerPushMock,
  }),
}))

vi.mock('@/api/catalog', () => ({
  getWorkspace: (...args: unknown[]) => getWorkspaceMock(...args),
}))

vi.mock('@/api/themes', () => ({
  listWorkspaceThemes: (...args: unknown[]) => listWorkspaceThemesMock(...args),
}))

vi.mock('@/api/assets', () => ({
  listWorkspaceFonts: (...args: unknown[]) => listWorkspaceFontsMock(...args),
}))

vi.mock('@/utils/message', () => ({
  Message: {
    error: vi.fn(),
    success: vi.fn(),
  },
}))

describe('ThemeManagerPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: clipboardWriteTextMock,
      },
    })
    clipboardWriteTextMock.mockResolvedValue(undefined)
    getWorkspaceMock.mockResolvedValue({
      id: 7,
      code: 'default',
      name: '默认工作空间',
      description: null,
      status: 'active',
      last_opened_at: null,
      default_theme_key: 'default',
      created_at: '2026-05-01T10:00:00+08:00',
      updated_at: '2026-05-01T10:00:00+08:00',
      created_by: null,
      updated_by: null,
    })
    listWorkspaceThemesMock.mockResolvedValue({
      items: [createThemeItem()],
      total: 1,
      page: 1,
      page_size: 100,
    })
    listWorkspaceFontsMock.mockResolvedValue({
      items: [createFontItem()],
      total: 1,
      page: 1,
      page_size: 100,
    })
  })

  it('应只读展示主题和字体，并支持字体预览与复制名称', async () => {
    renderThemePanel()

    await waitFor(() => {
      expect(screen.getByText('默认主题卡')).toBeInTheDocument()
    })
    expect(screen.queryByTitle('新建主题')).toBeNull()
    expect(screen.queryByTitle('编辑')).toBeNull()
    expect(screen.queryByTitle('删除')).toBeNull()

    await fireEvent.click(screen.getByText('字体'))

    expect(screen.getAllByText('SourceHanSans').length).toBeGreaterThan(0)
    await fireEvent.click(screen.getByTitle('预览字体'))
    expect(screen.getByText('字体效果预览：主题标题、正文与数字展示')).toBeInTheDocument()

    await fireEvent.click(screen.getByTitle('复制 font-family'))
    expect(clipboardWriteTextMock).toHaveBeenCalledWith('SourceHanSans')
  })

  it('管理按钮应跳转到主题与字体页面', async () => {
    const { emitted } = renderThemePanel()

    await waitFor(() => {
      expect(screen.getByText('默认主题卡')).toBeInTheDocument()
    })
    await fireEvent.click(screen.getByTitle('打开主题与字体管理页'))

    expect(routerPushMock).toHaveBeenCalledWith('/workspaces/7/themes')
    expect(emitted()['update:modelValue']).toEqual([[false]])
  })
})

function renderThemePanel() {
  return render(ThemeManagerPanel, {
    props: {
      modelValue: true,
      workspaceId: 7,
    },
    global: {
      stubs: {
        ThemePreviewCard: defineComponent({
          name: 'ThemePreviewCard',
          props: {
            name: {
              type: String,
              required: true,
            },
          },
          setup(props, { slots }) {
            return () => h('article', [h('h3', props.name), slots['title-suffix']?.()])
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
    logo_asset_id: null,
    invert_logo_asset_id: null,
    project_icon_asset_id: null,
    project_icon_name: null,
    heading_font_id: null,
    body_font_id: null,
    code_font_id: null,
    heading_font_label: 'Inter',
    body_font_label: 'Inter',
    code_font_label: 'monospace',
    palette: {},
    logo_asset: null,
    invert_logo_asset: null,
    project_icon_asset: null,
    heading_font: null,
    body_font: null,
    code_font: null,
    resolved_theme_config_yaml: '',
    created_at: '2026-05-01T10:00:00+08:00',
    updated_at: '2026-05-01T10:00:00+08:00',
    created_by: null,
    updated_by: null,
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
