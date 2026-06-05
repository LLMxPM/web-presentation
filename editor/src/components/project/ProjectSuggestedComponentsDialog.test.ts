/**
 * 文件功能：验证项目建议组件弹窗会加载、选择并保存项目级建议组件快照。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { SuggestedComponentItem, WorkspaceComponentItem } from '@/types/api'
import ProjectSuggestedComponentsDialog from './ProjectSuggestedComponentsDialog.vue'

const mocked = vi.hoisted(() => ({
  getProjectSuggestedComponents: vi.fn(),
  updateProjectSuggestedComponents: vi.fn(),
  listComponents: vi.fn(),
}))

vi.mock('@/api/catalog', () => ({
  getProjectSuggestedComponents: (...args: unknown[]) => mocked.getProjectSuggestedComponents(...args),
  updateProjectSuggestedComponents: (...args: unknown[]) => mocked.updateProjectSuggestedComponents(...args),
  listComponents: (...args: unknown[]) => mocked.listComponents(...args),
}))

describe('ProjectSuggestedComponentsDialog', () => {
  const savedComponent: SuggestedComponentItem = {
    id: 1,
    code: 'CMP001',
    name: '指标卡片',
    import_name: 'MetricCard',
    component_type: '内容区块',
    summary: '指标展示。',
    current_version_no: 1,
  }
  const availableComponent: WorkspaceComponentItem = {
    id: 2,
    workspace_id: 3,
    workspace_name: '演示空间',
    code: 'CMP002',
    content: '<template><section /></template>',
    preview_schema: null,
    current_version_no: 1,
    draft_base_version_no: 1,
    has_unpublished_changes: false,
    published_at: '2026-06-05T00:00:00Z',
    file_type: 'vue',
    name: '趋势图表',
    import_name: 'TrendChart',
    component_type: '数据展示',
    summary: '趋势展示。',
    status: 'active',
    created_at: '2026-06-05T00:00:00Z',
    updated_at: '2026-06-05T00:00:00Z',
    created_by: 1,
    updated_by: 1,
  }

  beforeEach(() => {
    vi.clearAllMocks()
    mocked.getProjectSuggestedComponents.mockResolvedValue({ items: [savedComponent] })
    mocked.listComponents.mockResolvedValue({
      items: [{ ...availableComponent, id: 1, code: 'CMP001', name: '指标卡片', import_name: 'MetricCard', component_type: '内容区块' }, availableComponent],
      total: 2,
      page: 1,
      page_size: 100,
    })
    mocked.updateProjectSuggestedComponents.mockResolvedValue({
      items: [savedComponent, toSuggestedComponent(availableComponent)],
    })
  })

  it('应保存用户新增选择的项目建议组件', async () => {
    const { emitted } = render(ProjectSuggestedComponentsDialog, {
      props: {
        modelValue: true,
        projectId: 7,
        workspaceId: 3,
        projectName: '年度路演',
      },
    })

    expect((await screen.findAllByText('指标卡片')).length).toBeGreaterThan(0)
    await fireEvent.click(screen.getByRole('button', { name: /趋势图表/ }))
    await fireEvent.click(screen.getByRole('button', { name: '保存组件' }))

    await waitFor(() => {
      expect(mocked.updateProjectSuggestedComponents).toHaveBeenCalledWith(7, [1, 2])
    })
    expect(mocked.listComponents).toHaveBeenCalledWith(expect.objectContaining({
      workspace_id: 3,
      published_only: true,
      status: 'active',
    }))
    const savedEvents = emitted('saved') as Array<[SuggestedComponentItem[]]> | undefined
    expect(savedEvents?.[0]?.[0].map(item => item.id)).toEqual([1, 2])
  })
})

/**
 * 将完整组件转换为建议组件摘要。
 * @param component 工作空间组件
 */
function toSuggestedComponent(component: WorkspaceComponentItem): SuggestedComponentItem {
  return {
    id: component.id,
    code: component.code,
    name: component.name,
    import_name: component.import_name,
    component_type: component.component_type,
    summary: component.summary,
    current_version_no: component.current_version_no,
  }
}
