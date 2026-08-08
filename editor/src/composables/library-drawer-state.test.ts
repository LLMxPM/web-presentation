/**
 * 文件功能：验证弹窗层素材/组件侧栏抽屉的全局开关状态与只读约束。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

describe('useLibraryDrawerState', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  it('初始应为关闭状态，并可按面板打开', async () => {
    const { useLibraryDrawerState } = await import('@/composables/library-drawer-state')
    const state = useLibraryDrawerState()

    expect(state.activePanel.value).toBeNull()

    state.openLibraryDrawer('assets')
    expect(state.activePanel.value).toBe('assets')

    state.openLibraryDrawer('components')
    expect(state.activePanel.value).toBe('components')
  })

  it('toggle 应在同一面板上切换开关', async () => {
    const { useLibraryDrawerState } = await import('@/composables/library-drawer-state')
    const state = useLibraryDrawerState()

    state.toggleLibraryDrawer('assets')
    expect(state.activePanel.value).toBe('assets')

    state.toggleLibraryDrawer('assets')
    expect(state.activePanel.value).toBeNull()

    state.closeLibraryDrawer()
    expect(state.activePanel.value).toBeNull()
  })

  it('activePanel 对外应保持只读，不允许外部直接赋值', async () => {
    const { useLibraryDrawerState } = await import('@/composables/library-drawer-state')
    const state = useLibraryDrawerState()

    state.activePanel.value = 'assets'
    expect(state.activePanel.value).toBeNull()
  })
})
