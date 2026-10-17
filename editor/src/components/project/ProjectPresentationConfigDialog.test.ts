/** 文件功能：验证项目配置弹窗保存时提交放映配置，且应用样式不会污染放映草稿。 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/api/styles', () => ({
  createWorkspaceStyle: vi.fn(),
}))

import type { ProjectItem } from '@/types/api'
import ProjectPresentationConfigDialog from './ProjectPresentationConfigDialog.vue'

const project = {
  id: 8,
  workspace_id: 3,
  workspace_name: '空间',
  code: 'PRJ_TEST',
  name: '放映项目',
  description: null,
  is_system_managed: false,
  status: 'active',
  archived_at: null,
  page_width: 1920,
  page_height: 1080,
  base_font_size: '24px',
  icon_default_stroke_width: 2,
  show_pdf_export_button: true,
  menu_mode: 'preview',
  theme_key: null,
  style_spec_markdown: '',
  build_extra_assets_json: { asset_names: [] },
  slideshow: {
    transition: { effect: 'push', duration_ms: 650 },
    advance: { mode: 'timer', delay_ms: 8000 },
    loop: true,
    auto_start: false,
  },
  routed_page_count: 1,
  total_page_count: 1,
  first_page_title: null,
  first_page_screenshot_url: null,
  created_at: '2026-10-17T00:00:00Z',
  updated_at: '2026-10-17T00:00:00Z',
  created_by: 1,
  updated_by: 1,
} as unknown as ProjectItem

const dialogStubs = {
  UiDialog: { template: '<div><slot /><slot name="footer" /></div>' },
  ThemeSelectorField: true,
  WorkspaceStyleApplyField: true,
  WorkspaceStyleEditorDialog: true,
  ProjectPresentationFields: true,
  ProjectSlideshowFields: {
    props: ['draft'],
    emits: ['update:draft'],
    template: '<button type="button" @click="$emit(\'update:draft\', { ...draft, effect: \'none\', durationSeconds: \'0\' })">切换无动画</button>',
  },
}

describe('ProjectPresentationConfigDialog', () => {
  it('保存时应提交表单收敛后的完整放映配置', async () => {
    const { emitted } = render(ProjectPresentationConfigDialog, {
      props: { modelValue: true, project, workspaceId: 3, defaultThemeKey: null },
      global: { stubs: dialogStubs },
    })

    await fireEvent.click(screen.getByRole('button', { name: '切换无动画' }))
    await fireEvent.click(screen.getByRole('button', { name: '保存配置' }))

    const saves = emitted('save') as Array<[Record<string, unknown>]>
    expect(saves).toHaveLength(1)
    expect(saves[0][0].slideshow).toEqual({
      transition: { effect: 'none', duration_ms: 0 },
      advance: { mode: 'timer', delay_ms: 8000 },
      loop: true,
      auto_start: false,
    })
  })

  it('应用样式只覆盖展示字段，不重建放映草稿', async () => {
    const { emitted, getByText } = render(ProjectPresentationConfigDialog, {
      props: { modelValue: true, project, workspaceId: 3, defaultThemeKey: null },
      global: {
        stubs: {
          ...dialogStubs,
          WorkspaceStyleApplyField: {
            emits: ['apply'],
            template: '<button type="button" @click="$emit(\'apply\', { id: 5, page_width: 1600, page_height: 900, base_font_size: \'18px\', icon_default_stroke_width: 3, show_pdf_export_button: false, menu_mode: \'text\', theme_key: null, style_spec_markdown: \'style\' })">应用样式</button>',
          },
        },
      },
    })

    await fireEvent.click(getByText('应用样式'))
    await fireEvent.click(getByText('保存配置'))

    const saves = emitted('save') as Array<[Record<string, unknown>]>
    expect(saves[0][0].slideshow).toEqual(project.slideshow)
  })
})
