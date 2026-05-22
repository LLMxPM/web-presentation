/**
 * 文件功能：验证项目构建中心弹窗的默认值、校验逻辑、历史展示与交互事件。
 */

import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import type { ProjectBuildJob } from '@/types/api'
import ProjectBuildDialog from './ProjectBuildDialog.vue'

function getEmittedEvents(view: ReturnType<typeof render>) {
  return view.emitted() as Record<string, Array<unknown[]>>
}

describe('ProjectBuildDialog', () => {
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

    expect(getEmittedEvents(view).submit?.[0]?.[0]).toEqual({ base_url: '/demo/' })
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

    await fireEvent.click(screen.getByText('打开产物'))
    expect(getEmittedEvents(view).open?.[0]?.[0]).toEqual(history[0])

    await fireEvent.click(screen.getByText('下载 ZIP'))
    expect(getEmittedEvents(view).download?.[0]?.[0]).toEqual(history[0])
  })
})
