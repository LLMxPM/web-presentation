/** 文件功能：验证项目配置弹窗保存时提交放映配置，且应用样式不会污染放映草稿。 */
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/styles', () => ({
  createWorkspaceStyle: vi.fn(),
}))

vi.mock('@/api/system', () => ({
  fetchDefaultStyleSpec: vi.fn().mockResolvedValue({ style_spec_markdown: '' }),
  fetchSystemSettings: vi.fn().mockResolvedValue({ app_timezone: 'Asia/Shanghai' }),
  fetchSlideshowCapabilities: vi.fn().mockResolvedValue({
    schema_version: 2,
    transition_effects: ['none', 'fade', 'push'],
    advance_modes: ['manual', 'timer', 'media_end'],
    single_window_auto_play: true,
    presenter_auto_play: false,
    capture_auto_play: false,
    transition_duration_ms: { min: 100, max: 2000, none: 0 },
    delay_ms: { min: 1000, max: 3600000 },
    media_timeout_ms: { min: 1000, max: 3600000 },
    audio: { schema_version: 1, audio_assets: true, page_narration: false, audio_cues: true },
  }),
}))

import type { ProjectItem } from '@/types/api'
import { fetchSlideshowCapabilities } from '@/api/system'
import { resetSlideshowCapabilitiesForTests } from '@/composables/useSlideshowCapabilities'
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
    advance: { mode: 'timer', delay_ms: 8000, media_timeout_ms: 300000 },
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
  ProjectAudioSettingsPanel: {
    props: ['draft'],
    emits: ['update:draft'],
    template: '<button type="button" @click="$emit(\'update:draft\', { ...draft, masterVolume: \'80\', transitionForward: { key: \'\', assetId: \'51\', gainPercent: \'75\' } })">修改音频</button>',
  },
}

describe('ProjectPresentationConfigDialog', () => {
  beforeEach(() => {
    resetSlideshowCapabilitiesForTests()
    vi.mocked(fetchSlideshowCapabilities).mockResolvedValue({
      schema_version: 2,
      transition_effects: ['none', 'fade', 'push'],
      advance_modes: ['manual', 'timer', 'media_end'],
      single_window_auto_play: true,
      presenter_auto_play: false,
      capture_auto_play: false,
      transition_duration_ms: { min: 100, max: 2000, none: 0 },
      delay_ms: { min: 1000, max: 3600000 },
      media_timeout_ms: { min: 1000, max: 3600000 },
      audio: { schema_version: 1, audio_assets: true, page_narration: false, audio_cues: true },
    })
  })

  it('分区包含展示、放映与已开放音频', async () => {
    render(ProjectPresentationConfigDialog, {
      props: { modelValue: true, project, workspaceId: 3, defaultThemeKey: null },
      global: { stubs: dialogStubs },
    })

    await waitFor(() => {
      expect(screen.getAllByRole('tab').map(tab => tab.textContent?.trim())).toEqual(['展示', '放映', '音频'])
    })
    expect(screen.getByText('样式规范 Markdown')).toBeInTheDocument()
  })

  it('保存时应提交表单收敛后的完整放映配置', async () => {
    const { emitted } = render(ProjectPresentationConfigDialog, {
      props: { modelValue: true, project, workspaceId: 3, defaultThemeKey: null, initialTab: 'slideshow' },
      global: { stubs: dialogStubs },
    })

    await fireEvent.click(screen.getByRole('button', { name: '切换无动画' }))
    await fireEvent.click(screen.getByRole('button', { name: '保存配置' }))

    const saves = emitted('save') as Array<[Record<string, unknown>]>
    expect(saves).toHaveLength(1)
    expect(saves[0][0].slideshow).toEqual({
      transition: { effect: 'none', duration_ms: 0 },
      advance: { mode: 'timer', delay_ms: 8000, media_timeout_ms: 300000 },
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

  it('保存时应提交音频草稿中的音量与 cue 绑定', async () => {
    const { emitted } = render(ProjectPresentationConfigDialog, {
      props: { modelValue: true, project, workspaceId: 3, defaultThemeKey: null },
      global: { stubs: dialogStubs },
    })

    await fireEvent.mouseDown(await screen.findByRole('tab', { name: '音频' }), { button: 0 })
    await fireEvent.click(await screen.findByRole('button', { name: '修改音频' }))
    await fireEvent.click(screen.getByRole('button', { name: '保存配置' }))

    const saves = emitted('save') as Array<[Record<string, unknown>]>
    expect(saves).toHaveLength(1)
    expect(saves[0][0].audio_settings).toEqual({
      master_volume_percent: 80,
      narration_volume_percent: 100,
      effects_volume_percent: 30,
      cue_bindings: [
        { key: 'transition.forward', asset_id: 51, gain_percent: 75 },
      ],
    })
  })

  it('能力关闭时隐藏音频分区且保存不提交音频配置', async () => {
    vi.mocked(fetchSlideshowCapabilities).mockResolvedValueOnce({
      schema_version: 2,
      transition_effects: ['none', 'fade', 'push'],
      advance_modes: ['manual', 'timer', 'media_end'],
      single_window_auto_play: true,
      presenter_auto_play: false,
      capture_auto_play: false,
      transition_duration_ms: { min: 100, max: 2000, none: 0 },
      delay_ms: { min: 1000, max: 3600000 },
      media_timeout_ms: { min: 1000, max: 3600000 },
      audio: { schema_version: 1, audio_assets: true, page_narration: false, audio_cues: false },
    })
    const { emitted } = render(ProjectPresentationConfigDialog, {
      props: { modelValue: true, project, workspaceId: 3, defaultThemeKey: null },
      global: { stubs: dialogStubs },
    })

    await waitFor(() => {
      expect(screen.queryByRole('tab', { name: '音频' })).not.toBeInTheDocument()
    })
    await fireEvent.click(screen.getByRole('button', { name: '保存配置' }))

    const saves = emitted('save') as Array<[Record<string, unknown>]>
    expect(saves).toHaveLength(1)
    expect(saves[0][0]).not.toHaveProperty('audio_settings')
  })
})
