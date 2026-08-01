/**
 * 文件功能：全局主题（明亮 / 夜间 / 跟随系统）状态管理。
 * 提供跨组件共享的单例主题状态，负责持久化到 localStorage、
 * 监听系统配色变化、在 <html> 上切换 `.dark` 类，并对外暴露用户偏好与实际模式。
 * 代码编辑器（Monaco）主题跟随此全局模式，不再独立控制。
 */
import { computed, readonly, ref } from 'vue'

import type { EditorThemeMode } from '@/types/monaco'

const STORAGE_KEY = 'editor-theme-mode'
const SYSTEM_DARK_QUERY = '(prefers-color-scheme: dark)'

export type ThemePreference = EditorThemeMode | 'system'

/** 获取系统当前实际使用的配色模式。 */
function resolveSystemMode(): EditorThemeMode {
  if (typeof window === 'undefined') return 'light'
  return window.matchMedia?.(SYSTEM_DARK_QUERY).matches ? 'dark' : 'light'
}

/**
 * 读取用户主题偏好；旧用户已保存的明暗选择保持不变，新用户默认跟随系统。
 */
function resolveInitialPreference(): ThemePreference {
  if (typeof window === 'undefined') return 'system'
  const stored = window.localStorage.getItem(STORAGE_KEY)
  if (stored === 'light' || stored === 'dark' || stored === 'system') return stored
  return 'system'
}

// 模块级单例，保证所有调用方共享同一份主题状态。
const preference = ref<ThemePreference>(resolveInitialPreference())
const systemMode = ref<EditorThemeMode>(resolveSystemMode())
const mode = computed<EditorThemeMode>(() => (
  preference.value === 'system' ? systemMode.value : preference.value
))

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

if (typeof window !== 'undefined') {
  const systemTheme = window.matchMedia?.(SYSTEM_DARK_QUERY)
  systemTheme?.addEventListener('change', (event) => {
    systemMode.value = event.matches ? 'dark' : 'light'
    if (preference.value === 'system') applyMode(systemMode.value)
  })
}

/**
 * 设置用户主题偏好并持久化；跟随系统时立即解析当前系统配色。
 * @param next 目标偏好
 */
function setMode(next: ThemePreference): void {
  preference.value = next
  applyMode(mode.value)
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(STORAGE_KEY, next)
  }
}

/** 保留原有二态快捷切换能力；调用后会固定为与当前实际模式相反的主题。 */
function toggle(): void {
  setMode(mode.value === 'dark' ? 'light' : 'dark')
}

/**
 * 全局主题组合式入口。
 * @returns 用户偏好、解析后的实际模式、是否夜间、快捷切换与设置方法
 */
export function useTheme() {
  return {
    preference: readonly(preference),
    mode,
    isDark: computed(() => mode.value === 'dark'),
    toggle,
    setMode,
  }
}
