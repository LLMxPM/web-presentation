/**
 * 文件功能：提供弹窗层“素材/组件侧栏抽屉”的全局开关状态，供抽屉宿主、浮层触发与快捷键共享。
 */
import { readonly, ref, type Ref } from 'vue'

export type LibraryDrawerPanelKey = 'assets' | 'components'

const activePanel = ref<LibraryDrawerPanelKey | null>(null)

/**
 * 返回抽屉全局开关状态；activePanel 为 null 表示抽屉关闭。
 * @returns 当前面板引用与开关操作
 */
export function useLibraryDrawerState(): {
  activePanel: Readonly<Ref<LibraryDrawerPanelKey | null>>
  openLibraryDrawer: (panel: LibraryDrawerPanelKey) => void
  toggleLibraryDrawer: (panel: LibraryDrawerPanelKey) => void
  closeLibraryDrawer: () => void
} {
  return {
    activePanel: readonly(activePanel),
    openLibraryDrawer: (panel) => {
      activePanel.value = panel
    },
    toggleLibraryDrawer: (panel) => {
      activePanel.value = activePanel.value === panel ? null : panel
    },
    closeLibraryDrawer: () => {
      activePanel.value = null
    },
  }
}
