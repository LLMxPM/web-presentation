/**
 * 文件功能：验证项目写入 API 将样式快照应用与展示配置补丁拆成合法的新契约请求。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { postMock, patchMock } = vi.hoisted(() => ({
  postMock: vi.fn(),
  patchMock: vi.fn(),
}))

vi.mock('@/api/http', () => ({
  http: {
    post: postMock,
    patch: patchMock,
  },
}))

import { createProject, updateProject } from '@/api/catalog'

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
