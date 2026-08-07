/**
 * 文件功能：验证项目卡片的首屏截图、占位状态、快捷操作和身份复制交互。
 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ProjectCard from './ProjectCard.vue'
import type { ProjectItem } from '@/types/api'

const { messageSuccessMock } = vi.hoisted(() => ({
  messageSuccessMock: vi.fn(),
}))

vi.mock('@/utils/message', () => ({
  Message: {
    success: messageSuccessMock,
    error: vi.fn(),
  },
}))

const baseProject: ProjectItem = {
  id: 7,
  workspace_id: 3,
  workspace_name: '设计空间',
  code: 'PRJ007',
  name: '季度发布会',
  description: '用于季度业务复盘与新品发布。',
  is_system_managed: false,
  status: 'active',
  archived_at: null,
  page_width: 1920,
  page_height: 1080,
  base_font_size: '20px',
  icon_default_stroke_width: 2,
  show_pdf_export_button: true,
  menu_mode: 'preview',
  theme_key: null,
  theme_config_yaml: '',
  style_spec_markdown: '',
  routed_page_count: 2,
  total_page_count: 5,
  first_page_title: '封面',
  first_page_screenshot_url: 'https://example.test/page-7.png',
  created_at: '2026-08-01T08:00:00Z',
  updated_at: '2026-08-06T08:00:00Z',
  created_by: 1,
  updated_by: 1,
}

describe('ProjectCard', () => {
  const clipboardWriteTextMock = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    clipboardWriteTextMock.mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: clipboardWriteTextMock },
    })
  })

  it('展示首个页面截图，并将项目信息和操作保留在卡片中', async () => {
    const { emitted } = render(ProjectCard, { props: { project: baseProject } })

    expect(screen.getByAltText('季度发布会 首个页面截图')).toHaveAttribute(
      'src',
      'https://example.test/page-7.png',
    )
    expect(screen.getByText('1920×1080')).toBeInTheDocument()
    expect(screen.getByText('路由页面 2 / 5')).toHaveClass('project-card-route-count')
    expect(screen.queryByText('用于季度业务复盘与新品发布。')).not.toBeInTheDocument()
    expect(screen.queryByText('封面')).not.toBeInTheDocument()

    await fireEvent.click(screen.getByRole('link', { name: '打开项目：季度发布会' }))
    await fireEvent.click(screen.getByRole('button', { name: '预览项目' }))
    await fireEvent.click(screen.getByRole('button', { name: '导出项目' }))
    await fireEvent.click(screen.getByRole('button', { name: '归档项目' }))

    expect(emitted().open).toEqual([[7]])
    expect(emitted().preview).toEqual([[baseProject]])
    expect(emitted()['export-template']).toEqual([[baseProject]])
    expect(emitted().archive).toEqual([[baseProject]])
  })

  it('无页面时展示占位，并支持分别复制名称与编码', async () => {
    const project = {
      ...baseProject,
      first_page_title: null,
      first_page_screenshot_url: null,
    }
    render(ProjectCard, { props: { project } })

    expect(screen.getByText('项目暂无页面')).toBeInTheDocument()

    await fireEvent.click(screen.getByRole('button', { name: '复制项目名称：季度发布会' }))
    await fireEvent.click(screen.getByRole('button', { name: '复制项目编码：PRJ007' }))

    expect(clipboardWriteTextMock).toHaveBeenNthCalledWith(1, '季度发布会')
    expect(clipboardWriteTextMock).toHaveBeenNthCalledWith(2, 'PRJ007')
    expect(messageSuccessMock).toHaveBeenNthCalledWith(1, '项目名称已复制。')
    expect(messageSuccessMock).toHaveBeenNthCalledWith(2, '项目编码已复制。')
  })

  it('有页面但无截图时展示独立占位文案', () => {
    render(ProjectCard, {
      props: {
        project: { ...baseProject, first_page_screenshot_url: null },
      },
    })

    expect(screen.getByText('首个页面暂无截图')).toBeInTheDocument()
  })

  it('项目名称过长时应限制在卡片名称区域内', () => {
    const longName = '这是一个用于验证项目卡片名称截断行为的超长项目名称'
    render(ProjectCard, {
      props: {
        project: { ...baseProject, name: longName },
      },
    })

    expect(screen.getByText(longName)).toHaveClass('block', 'max-w-full', 'truncate')
  })
})
