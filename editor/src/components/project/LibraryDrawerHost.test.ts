/**
 * 文件功能：验证素材/组件侧栏抽屉的页签切换、关闭按钮与全局快捷键行为。
 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import LibraryDrawerHost from './LibraryDrawerHost.vue'
import { useLibraryDrawerState } from '@/composables/library-drawer-state'

vi.mock('@/components/project/AssetManagerPanel.vue', () => ({
  name: 'AssetManagerPanel',
  __isTeleport: false,
  __isKeepAlive: false,
  default: {
    name: 'AssetManagerPanel',
    props: ['modelValue', 'workspaceId', 'layerIndex', 'hideNavigation', 'hidePanelHeader'],
    template: '<div data-testid="asset-panel-mock" />',
  },
}))

vi.mock('@/components/project/ComponentManagerPanel.vue', () => ({
  name: 'ComponentManagerPanel',
  __isTeleport: false,
  __isKeepAlive: false,
  default: {
    name: 'ComponentManagerPanel',
    props: ['modelValue', 'workspaceId', 'layerIndex', 'hideNavigation', 'hidePanelHeader'],
    template: '<div data-testid="component-panel-mock" />',
  },
}))

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => {
  cleanup()
  useLibraryDrawerState().closeLibraryDrawer()
})

describe('LibraryDrawerHost', () => {
  it('快捷键可打开抽屉，并可在抽屉内切换页签与关闭', async () => {
    render(LibraryDrawerHost, { props: { workspaceId: 1 } })

    fireEvent.keyDown(window, { key: 'k', ctrlKey: true, shiftKey: true })
    expect(await screen.findByTestId('asset-panel-mock')).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()

    await fireEvent.click(screen.getByRole('radio', { name: '组件' }))
    expect(await screen.findByTestId('component-panel-mock')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.queryByTestId('asset-panel-mock')).not.toBeInTheDocument()
    })

    await fireEvent.click(screen.getByRole('button', { name: '关闭侧栏' }))
    await waitFor(() => {
      expect(screen.queryByTestId('component-panel-mock')).not.toBeInTheDocument()
    })
  })

  it('Ctrl+Shift+K 再次按下应关闭抽屉', async () => {
    render(LibraryDrawerHost, { props: { workspaceId: 1 } })

    fireEvent.keyDown(window, { key: 'k', ctrlKey: true, shiftKey: true })
    expect(await screen.findByTestId('asset-panel-mock')).toBeInTheDocument()

    fireEvent.keyDown(window, { key: 'k', ctrlKey: true, shiftKey: true })
    await waitFor(() => {
      expect(screen.queryByTestId('asset-panel-mock')).not.toBeInTheDocument()
    })
  })

  it('快捷键应吞掉组合键避免触发浏览器默认行为', async () => {
    render(LibraryDrawerHost, { props: { workspaceId: 1 } })

    const preventDefaultSpy = vi.spyOn(KeyboardEvent.prototype, 'preventDefault')
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true, shiftKey: true })
    expect(preventDefaultSpy).toHaveBeenCalled()
    preventDefaultSpy.mockRestore()

    expect(await screen.findByTestId('asset-panel-mock')).toBeInTheDocument()
  })

  it('无工作空间上下文时快捷键不生效', async () => {
    render(LibraryDrawerHost, { props: { workspaceId: null } })

    fireEvent.keyDown(window, { key: 'k', ctrlKey: true, shiftKey: true })

    expect(screen.queryByTestId('asset-panel-mock')).not.toBeInTheDocument()
  })

  it('离开工作空间后应关闭已打开的抽屉', async () => {
    const { openLibraryDrawer } = useLibraryDrawerState()
    const view = render(LibraryDrawerHost, { props: { workspaceId: 1 } })
    openLibraryDrawer('assets')
    expect(await screen.findByTestId('asset-panel-mock')).toBeInTheDocument()

    await view.rerender({ workspaceId: null })

    await waitFor(() => {
      expect(screen.queryByTestId('asset-panel-mock')).not.toBeInTheDocument()
    })
  })
})
