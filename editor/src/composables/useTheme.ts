/**
 * 文件功能：全局主题（明亮 / 夜间）状态管理。
 * 提供跨组件共享的单例主题状态，负责持久化到 localStorage、
 * 在 <html> 上切换 `.dark` 类，并对外暴露只读的当前模式与切换方法。
 * 代码编辑器（Monaco）主题跟随此全局模式，不再独立控制。
 */
import { computed, readonly, ref } from 'vue'

import type { EditorThemeMode } from '@/types/monaco'

const STORAGE_KEY = 'editor-theme-mode'

/**
 * 读取初始主题：优先 localStorage，其次跟随系统偏好，默认明亮。
 */
function resolveInitialMode(): EditorThemeMode {
  if (typeof window === 'undefined') return 'light'
  const stored = window.localStorage.getItem(STORAGE_KEY)
  if (stored === 'light' || stored === 'dark') return stored
  if (window.matchMedia?.('(prefers-color-scheme: dark)').matches) return 'dark'
  return 'light'
}

// 模块级单例，保证所有调用方共享同一份主题状态。
const mode = ref<EditorThemeMode>(resolveInitialMode())

/**
 * 将当前模式同步到 <html> 的 `.dark` 类与 color-scheme。
 */
function applyMode(next: EditorThemeMode): void {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  root.classList.toggle('dark', next === 'dark')
  root.style.colorScheme = next
}

applyMode(mode.value)

/**
 * 设置全局主题模式并持久化。
 * @param next 目标模式
 */
function setMode(next: EditorThemeMode): void {
  mode.value = next
  applyMode(next)
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(STORAGE_KEY, next)
  }
}

/**
 * 在明亮与夜间之间切换。
 */
function toggle(): void {
  setMode(mode.value === 'dark' ? 'light' : 'dark')
}

/**
 * 全局主题组合式入口。
 * @returns 当前模式（只读）、是否夜间、切换与设置方法
 */
export function useTheme() {
  return {
    mode: readonly(mode),
    isDark: computed(() => mode.value === 'dark'),
    toggle,
    setMode,
  }
}
