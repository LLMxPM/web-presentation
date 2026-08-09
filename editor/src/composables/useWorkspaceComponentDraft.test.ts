/**
 * 文件功能：验证工作空间组件草稿在提交前统一执行 previewSchema 契约校验。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useWorkspaceComponentDraft } from '@/composables/useWorkspaceComponentDraft'

const catalogMocks = vi.hoisted(() => ({
  createComponent: vi.fn(),
  updateComponent: vi.fn(),
}))

vi.mock('@/api/catalog', () => catalogMocks)

describe('useWorkspaceComponentDraft', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it.each(['页面组件', '原子组件'] as const)('%s 缺少 previewSchema 时不应提交', async (componentType) => {
    const draft = useWorkspaceComponentDraft({ workspaceId: () => 11 })
    draft.replaceForm({
      name: '测试组件',
      import_name: 'TestComponent',
      component_type: componentType,
      summary: '',
      status: 'active',
      content: '<template><div /></template>',
      preview_schema: '',
    })

    await expect(draft.saveDraft()).resolves.toBeNull()
    expect(draft.errors.preview_schema).toContain('组件必须配置 previewSchema')
    expect(catalogMocks.createComponent).not.toHaveBeenCalled()
  })

  it('原子组件提供空 props Schema 时可以提交', async () => {
    const draft = useWorkspaceComponentDraft({ workspaceId: () => 11 })
    draft.replaceForm({
      name: '测试组件',
      import_name: 'TestComponent',
      component_type: '原子组件',
      summary: '',
      status: 'active',
      content: '<template><div /></template>',
      preview_schema: '{"props":{}}',
    })
    catalogMocks.createComponent.mockResolvedValue({
      id: 21,
      name: '测试组件',
      import_name: 'TestComponent',
      component_type: '原子组件',
      summary: null,
      status: 'active',
      content: '<template><div /></template>',
      preview_schema: '{"props":{}}',
    })

    await expect(draft.saveDraft()).resolves.toMatchObject({ id: 21 })
    expect(catalogMocks.createComponent).toHaveBeenCalledWith(expect.objectContaining({
      preview_schema: '{\n  "props": {}\n}',
    }))
  })
})
