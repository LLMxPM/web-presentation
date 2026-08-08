/**
 * 文件功能：验证右侧 Dock 底部素材/组件抽屉入口胶囊的展示与开关行为。
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import WorkspaceDock from './WorkspaceDock.vue'
import { useLibraryDrawerState } from '@/composables/library-drawer-state'

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => {
  cleanup()
  useLibraryDrawerState().closeLibraryDrawer()
})

describe('WorkspaceDock', () => {
  it('应展示底部素材/组件入口胶囊，点击后打开素材页签', async () => {
    const { activePanel } = useLibraryDrawerState()
    render(WorkspaceDock, { props: { workspaceId: 1, activeKey: 'projects' } })

    await fireEvent.click(screen.getByRole('button', { name: '打开素材 / 组件侧栏' }))
    expect(activePanel.value).toBe('assets')
  })

  it('抽屉打开后入口胶囊应隐藏', async () => {
    const { openLibraryDrawer } = useLibraryDrawerState()
    openLibraryDrawer('components')
    render(WorkspaceDock, { props: { workspaceId: 1, activeKey: 'projects' } })

    expect(screen.queryByRole('button', { name: '打开素材 / 组件侧栏' })).not.toBeInTheDocument()
  })
})
