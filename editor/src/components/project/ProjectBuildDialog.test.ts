/**
 * 文件功能：验证项目构建中心弹窗的默认值、校验逻辑、历史展示与交互事件。
 */

import { fireEvent, render, screen } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ProjectBuildJob } from '@/types/api'
import ProjectBuildDialog from './ProjectBuildDialog.vue'

const listWorkspaceAssetsMock = vi.fn()

vi.mock('@/api/assets', () => ({
  listWorkspaceAssets: (...args: unknown[]) => listWorkspaceAssetsMock(...args),
}))

vi.mock('@/api/http', () => ({
  getErrorMessage: (_error: unknown, fallback: string) => fallback,
}))

function getEmittedEvents(view: ReturnType<typeof render>) {
  return view.emitted() as Record<string, Array<unknown[]>>
}

describe('ProjectBuildDialog', () => {
  beforeEach(() => {
    listWorkspaceAssetsMock.mockResolvedValue({
      items: [
        {
          id: 1,
          workspace_id: 3,
          name: 'hero_bg',
          original_name: 'hero.png',
          file_name: 'hero.png',
          description: null,
          file_size: 10,
          file_hash: 'hash-hero',
          content_type: 'image/png',
          asset_type: 'image',
          asset_role: 'content',
          render_type: 'image',
          tags: [],
          status: 'active',
          archived_at: null,
          archive_reason: null,
          source_asset_id: null,
          history_kind: null,
          url: '/public/assets/3/hash-hero',
          content_editable: false,
          analysis_metadata: null,
          render_metadata: null,
          font_config: null,
          created_at: '2026-04-19T08:00:00+08:00',
          updated_at: '2026-04-19T08:00:00+08:00',
        },
        {
          id: 2,
          workspace_id: 3,
          name: 'brand_font',
          original_name: 'brand.woff2',
          file_name: 'brand.woff2',
          description: null,
          file_size: 20,
          file_hash: 'hash-font',
          content_type: 'font/woff2',
          asset_type: 'font',
          asset_role: 'foundation',
          render_type: 'font',
          tags: [],
          status: 'active',
          archived_at: null,
          archive_reason: null,
          source_asset_id: null,
          history_kind: null,
          url: '/public/assets/3/hash-font',
          content_editable: false,
          analysis_metadata: null,
          render_metadata: null,
          font_config: null,
          created_at: '2026-04-19T08:00:00+08:00',
          updated_at: '2026-04-19T08:00:00+08:00',
        },
      ],
      total: 1,
      page: 1,
      page_size: 100,
    })
  })

  const history: ProjectBuildJob[] = [
    {
      id: 12,
      project_id: 3,
      snapshot_release_id: 8,
      base_url: '/prod/',
      status: 'succeeded',
      error_message: null,
      artifact_storage_key: 'build-artifacts/3/12/dist.zip',
      artifact_download_url: '/api/projects/3/build-jobs/12/artifact',
      artifact_proxy_url: '/build-artifacts/3/12/',
      artifact_entry_file: 'index.html',
      artifact_sha256: 'sha256',
      artifact_size_bytes: 1024,
      created_by: 1,
      created_at: '2026-04-19T08:00:00+08:00',
      updated_at: '2026-04-19T08:01:00+08:00',
      started_at: '2026-04-19T08:00:10+08:00',
      finished_at: '2026-04-19T08:01:00+08:00',
    },
  ]

  it('打开时应默认使用 ./ 作为部署基路径', () => {
    render(ProjectBuildDialog, {
      props: {
        modelValue: true,
      },
    })

    expect(screen.getByDisplayValue('./')).toBeInTheDocument()
  })

  it('非法部署基路径应展示错误并阻止提交', async () => {
    const view = render(ProjectBuildDialog, {
      props: {
        modelValue: true,
      },
    })

    await fireEvent.update(screen.getByPlaceholderText('./ 或 /demo/'), 'https://example.com/demo')
    expect(screen.getByText('部署基路径不能是完整 URL 或双斜杠路径。')).toBeInTheDocument()

    await fireEvent.click(screen.getByText('发起构建'))
    expect(getEmittedEvents(view).submit).toBeUndefined()
  })

  it('提交时应输出规范化后的 base_url', async () => {
    const view = render(ProjectBuildDialog, {
      props: {
        modelValue: true,
      },
    })

    await fireEvent.update(screen.getByPlaceholderText('./ 或 /demo/'), '/demo')
    await fireEvent.click(screen.getByText('发起构建'))

    expect(getEmittedEvents(view).submit?.[0]?.[0]).toEqual({ base_url: '/demo/', extra_asset_names: [] })
  })

  it('存在执行中的构建任务时应禁用再次构建', async () => {
    const runningJob: ProjectBuildJob = {
      ...history[0],
      id: 13,
      status: 'running',
      finished_at: null,
    }
    const view = render(ProjectBuildDialog, {
      props: {
        modelValue: true,
        latestJob: runningJob,
      },
    })

    const submitButton = screen.getByRole('button', { name: '构建中' })
    expect(submitButton).toBeDisabled()

    await fireEvent.click(submitButton)
    expect(getEmittedEvents(view).submit).toBeUndefined()
  })

  it('应支持选择并保存额外构建资源', async () => {
    const view = render(ProjectBuildDialog, {
      props: {
        modelValue: true,
        workspaceId: 3,
        automaticAssetNames: ['brand_font'],
        buildExtraAssetsJson: { asset_names: [] },
      },
    })

    await screen.findByText('hero_bg')
    expect(screen.getByRole('button', { name: /全部2/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /图片1/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /字体1/ })).toBeInTheDocument()
    expect(screen.getByText('自动包含')).toBeInTheDocument()
    expect(screen.getByText('额外资源')).toBeInTheDocument()
    await fireEvent.click(screen.getByText('hero_bg'))
    await fireEvent.click(screen.getByText('保存额外资源'))

    expect(getEmittedEvents(view).saveExtraAssets?.[0]?.[0]).toEqual(['hero_bg'])
  })

  it('发起构建时应携带当前额外资源草稿', async () => {
    const view = render(ProjectBuildDialog, {
      props: {
        modelValue: true,
        workspaceId: 3,
        buildExtraAssetsJson: { asset_names: [] },
      },
    })

    await screen.findByText('hero_bg')
    await fireEvent.click(screen.getByText('hero_bg'))
    await fireEvent.click(screen.getByText('发起构建'))

    expect(getEmittedEvents(view).submit?.[0]?.[0]).toEqual({
      base_url: './',
      extra_asset_names: ['hero_bg'],
    })
  })

  it('资源构建错误应展示动态模块并允许重新构建', async () => {
    const view = render(ProjectBuildDialog, {
      props: {
        modelValue: true,
        workspaceId: 3,
        resourceIssueCode: 'PROJECT_BUILD_DYNAMIC_ASSET_REFERENCE',
        resourceIssue: {
          dynamic_module_paths: ['src/views/Home.vue'],
          candidate_asset_names: ['hero_bg'],
        },
      },
    })

    expect(screen.getByText('构建需要补充动态资源')).toBeInTheDocument()
    expect(screen.getByText(/src\/views\/Home.vue/)).toBeInTheDocument()

    await fireEvent.click(screen.getByText('加入 hero_bg'))
    await fireEvent.click(screen.getByText('重新构建'))

    expect(getEmittedEvents(view).submit?.[0]?.[0]).toEqual({ base_url: './', extra_asset_names: ['hero_bg'] })
  })

  it('应展示构建历史并在点击打开或下载时抛出对应任务', async () => {
    const view = render(ProjectBuildDialog, {
      props: {
        modelValue: true,
        history,
        latestJob: history[0],
        latestJobId: 12,
      },
    })

    expect(screen.getByText('构建历史')).toBeInTheDocument()
    expect(screen.getByText('#12')).toBeInTheDocument()
    expect(screen.getByText('最近一次')).toBeInTheDocument()
    expect(screen.getByText('刷新最新状态')).toBeInTheDocument()

    await fireEvent.click(screen.getByText('打开'))
    expect(getEmittedEvents(view).open?.[0]?.[0]).toEqual(history[0])

    await fireEvent.click(screen.getByText('ZIP'))
    expect(getEmittedEvents(view).download?.[0]?.[0]).toEqual(history[0])
  })
})
