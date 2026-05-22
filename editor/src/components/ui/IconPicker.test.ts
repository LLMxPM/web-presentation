/**
 * 文件功能：验证图标选择器的搜索过滤、预览确认与返回值模式行为。
 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it, vi } from 'vitest'

import type { AssetResponse } from '@/types/api'
import IconPicker from './IconPicker.vue'

vi.mock('@/api/assets', () => ({
  listWorkspaceAssets: vi.fn(),
}))

function getEmittedEvents(view: ReturnType<typeof render>) {
  return view.emitted() as Record<string, Array<unknown[]>>
}

describe('IconPicker', () => {
  const iconAssets: AssetResponse[] = [
    {
      id: 1,
      workspace_id: 1,
      name: 'home',
      file_name: 'home.svg',
      original_name: 'home.svg',
      description: null,
      file_size: 100,
      file_hash: 'hash-home',
      content_type: 'image/svg+xml',
      asset_type: 'icon',
      asset_role: 'foundation',
      render_type: 'icon',
      tags: ['导航', '常用'],
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
      url: 'https://example.com/home.svg',
      font_config: null,
      rename_block_reason: null,
      delete_block_reason: null,
      archive_block_reason: null,
      archive_warning_reasons: [],
      created_at: '2026-04-19T00:00:00Z',
      updated_at: '2026-04-19T00:00:00Z',
    },
    {
      id: 2,
      workspace_id: 1,
      name: 'mail',
      file_name: 'mail.svg',
      original_name: 'mail.svg',
      description: null,
      file_size: 100,
      file_hash: 'hash-mail',
      content_type: 'image/svg+xml',
      asset_type: 'icon',
      asset_role: 'foundation',
      render_type: 'icon',
      tags: ['通信'],
      analysis_metadata: {
        schema_version: 1,
        kind: 'icon',
        icon: {
          format: 'svg',
          render_mode: 'inline_svg',
          style: 'fill',
          inline_safe: true,
          stroke_width_editable: false,
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
      url: 'https://example.com/mail.svg',
      font_config: null,
      rename_block_reason: null,
      delete_block_reason: null,
      archive_block_reason: null,
      archive_warning_reasons: [],
      created_at: '2026-04-19T00:00:00Z',
      updated_at: '2026-04-19T00:00:00Z',
    },
    {
      id: 3,
      workspace_id: 1,
      name: 'cover',
      file_name: 'cover.png',
      original_name: 'cover.png',
      description: null,
      file_size: 100,
      file_hash: 'hash-cover',
      content_type: 'image/png',
      asset_type: 'image',
      asset_role: 'content',
      render_type: 'image',
      tags: ['封面'],
      analysis_metadata: null,
      render_metadata: null,
      status: 'active',
      archived_at: null,
      archive_reason: null,
      source_asset_id: null,
      history_kind: null,
      content_editable: false,
      url: 'https://example.com/cover.png',
      font_config: null,
      rename_block_reason: null,
      delete_block_reason: null,
      archive_block_reason: null,
      archive_warning_reasons: [],
      created_at: '2026-04-19T00:00:00Z',
      updated_at: '2026-04-19T00:00:00Z',
    },
  ]

  it('应支持按标签和类型搜索，并按名称输出选中图标', async () => {
    const view = render(IconPicker, {
      props: {
        modelValue: null,
        assets: [...iconAssets],
        valueMode: 'name',
        placeholder: '请选择路由图标',
      },
    })

    await fireEvent.click(screen.getAllByRole('button', { name: '选择' })[0])
    await fireEvent.update(screen.getByPlaceholderText('按名称、标签、类型搜索图标'), 'fill')

    expect(screen.getByText('mail')).toBeInTheDocument()
    expect(screen.queryByText('home')).not.toBeInTheDocument()

    await fireEvent.click(screen.getByText('mail'))
    await fireEvent.click(screen.getByRole('button', { name: '确认选择' }))

    expect(getEmittedEvents(view)['update:modelValue']?.[0]?.[0]).toBe('mail')
    expect(getEmittedEvents(view)['select']?.[0]?.[0]).toMatchObject({ id: 2, name: 'mail' })
  })

  it('应支持按资源 ID 输出，并过滤非图标资源', async () => {
    const view = render(IconPicker, {
      props: {
        modelValue: null,
        assets: [...iconAssets],
        valueMode: 'id',
      },
    })

    await fireEvent.click(screen.getAllByRole('button', { name: '选择' })[0])

    expect(screen.queryByText('cover')).not.toBeInTheDocument()

    await fireEvent.update(screen.getByPlaceholderText('按名称、标签、类型搜索图标'), '导航')
    await fireEvent.click(screen.getByText('home'))
    await fireEvent.click(screen.getByRole('button', { name: '确认选择' }))

    expect(getEmittedEvents(view)['update:modelValue']?.[0]?.[0]).toBe(1)
    expect(getEmittedEvents(view)['select']?.[0]?.[0]).toMatchObject({ id: 1, name: 'home' })
  })
})
