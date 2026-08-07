/**
 * 文件功能：验证项目写入 API 将样式快照应用与展示配置补丁拆成合法的新契约请求。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { getMock, postMock, patchMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  postMock: vi.fn(),
  patchMock: vi.fn(),
}))

vi.mock('@/api/http', () => ({
  http: {
    get: getMock,
    post: postMock,
    patch: patchMock,
  },
}))

import { createProject, listPages, listProjects, updateProject } from '@/api/catalog'

const presentation = {
  page_width: 1600,
  page_height: 900,
  base_font_size: '18px',
  icon_default_stroke_width: 3,
  show_pdf_export_button: false,
  menu_mode: 'bottom-preview' as const,
  theme_key: 'lightblue',
  style_spec_markdown: '## 项目规范',
}

describe('catalog project api', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('列表 API 应透传项目分页搜索和页面项目归属过滤参数', async () => {
    getMock
      .mockResolvedValueOnce({ data: { items: [], total: 0, page: 2, page_size: 24 } })
      .mockResolvedValueOnce({ data: { items: [], total: 0, page: 1, page_size: 24 } })

    await listProjects({
      page: 2,
      page_size: 24,
      workspace_id: 7,
      status: 'active',
      keyword: '项目',
    })
    await listPages({
      page: 1,
      page_size: 24,
      workspace_id: 7,
      project_assigned: true,
      status: 'active',
    })

    expect(getMock).toHaveBeenNthCalledWith(1, '/projects', {
      params: expect.objectContaining({
        page: 2,
        page_size: 24,
        workspace_id: 7,
        status: 'active',
        keyword: '项目',
      }),
    })
    expect(getMock).toHaveBeenNthCalledWith(2, '/pages', {
      params: expect.objectContaining({
        page: 1,
        page_size: 24,
        workspace_id: 7,
        project_assigned: true,
        status: 'active',
      }),
    })
  })

  it('创建项目时应先复制样式快照，再提交允许的展示补丁', async () => {
    postMock.mockResolvedValueOnce({ data: { id: 31 } })
    patchMock.mockResolvedValueOnce({ data: { id: 31, page_width: 1600 } })

    await createProject({
      workspace_id: 5,
      name: '季度汇报',
      description: null,
      status: 'active',
      ...presentation,
      source_style_id: 23,
    })

    expect(postMock).toHaveBeenCalledWith('/projects', {
      workspace_id: 5,
      name: '季度汇报',
      description: null,
      status: 'active',
      configuration: { mode: 'style', style_id: 23 },
    })
    expect(patchMock).toHaveBeenCalledWith('/projects/31', {
      configuration: { mode: 'patch', presentation },
    })
  })

  it('更新项目时应先应用完整样式，再保留用户调整后的展示字段', async () => {
    patchMock.mockResolvedValueOnce({ data: { id: 31 } })
    patchMock.mockResolvedValueOnce({ data: { id: 31, page_width: 1600 } })

    await updateProject(31, { ...presentation, source_style_id: 23 })

    expect(patchMock).toHaveBeenNthCalledWith(1, '/projects/31', {
      configuration: { mode: 'style', style_id: 23 },
    })
    expect(patchMock).toHaveBeenNthCalledWith(2, '/projects/31', {
      configuration: { mode: 'patch', presentation },
    })
  })
})
