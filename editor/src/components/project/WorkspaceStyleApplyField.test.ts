/**
 * 文件功能：验证工作空间样式选择器可在项目创建时自动应用默认样式快照。
 */
import { render, waitFor } from '@testing-library/vue'
import { describe, expect, it, vi } from 'vitest'

const { listWorkspaceStylesMock } = vi.hoisted(() => ({
  listWorkspaceStylesMock: vi.fn(),
}))

vi.mock('@/api/styles', () => ({
  listWorkspaceStyles: (...args: unknown[]) => listWorkspaceStylesMock(...args),
}))

import WorkspaceStyleApplyField from './WorkspaceStyleApplyField.vue'

describe('WorkspaceStyleApplyField', () => {
  it('指定 autoApplyKey 时应在首次加载后应用匹配样式', async () => {
    const defaultStyle = {
      id: 9,
      key: 'default',
      name: '默认样式',
      description: null,
      theme_key: 'lightblue',
      page_width: 1920,
      page_height: 1080,
    }
    listWorkspaceStylesMock.mockResolvedValue({ items: [defaultStyle], total: 1 })

    const { emitted } = render(WorkspaceStyleApplyField, {
      props: { workspaceId: 5, autoApplyKey: 'default' },
    })

    await waitFor(() => {
      expect(emitted('apply')?.[0]).toEqual([defaultStyle])
    })
    expect(listWorkspaceStylesMock).toHaveBeenCalledWith(5, { page: 1, page_size: 100 })
  })
})
